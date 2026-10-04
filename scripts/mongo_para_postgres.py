"""Transfere os dados de uma instalação MongoDB para o PostgreSQL.

    pip install pymongo
    MONGO_URL=mongodb://usuario:senha@host:27017/miliano_crm?authSource=miliano_crm \\
    DB_NAME=miliano_crm \\
    DATABASE_URL=postgresql://... \\
    python scripts/mongo_para_postgres.py [--simular]

Roda UMA vez, com a API parada, contra um PostgreSQL vazio. O schema é aplicado
antes (o mesmo SQL que a API aplica no boot), então o destino pode ser um banco
recém-criado.

O que este script garante:

TUDO OU NADA. A cópia inteira acontece numa transação só. Se algo inesperado
falhar no meio, o PostgreSQL fica como estava — sem metade dos pedidos e
nenhum pagamento.

NADA SOME CALADO. Uma linha que o schema recusa (um CHECK, uma resposta de
formulário cujo formulário foi apagado) não derruba a transferência: vai para
`backups/transferencia_recusados.json`, com o motivo. Campos que existiam no
documento e não têm coluna são contados por tabela no relatório final.

OS IDS SE MANTÊM. Pedidos, cadastros e formulários já tinham `id` em texto. Os
usuários usavam o `_id` do Mongo; ele vira o `id` em texto. Assim os vínculos
(auditoria por autor, links de redefinição) continuam apontando para a mesma
pessoa, e os tokens de sessão emitidos antes da troca continuam valendo.

O CONSERTO DO LEGADO ACONTECE AQUI. A API antiga aceitava comissão de -50%,
status "voando" e CPF com pontuação; o seed do Mongo consertava isso a cada
boot. No PostgreSQL os CHECK recusam esses valores, então eles são corrigidos
na passagem, com as mesmas regras.

Com `--simular`, tudo roda e o relatório sai, mas a transação é desfeita no
fim: serve para ver quantas linhas seriam recusadas antes de transferir de
verdade.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import asyncpg

RAIZ = Path(__file__).resolve().parent.parent
DIR_SQL = RAIZ / "backend/app/sql"

# Ordem de inserção: quem é referenciado vem antes (form_submissions aponta
# para forms). As efêmeras — tentativas de login e links de redefinição — não
# são copiadas: vencem em minutos e não fazem falta.
ORDEM = [
    "users", "restaurants", "drivers", "contracts", "payments", "orders", "leads",
    "activities", "forms", "form_submissions", "audit_logs", "api_keys", "webhooks",
    "webhook_logs", "counters",
]
IGNORADAS = {"login_attempts", "password_resets", "migrations"}

# Restrições do schema que o Mongo nunca impôs. Valor fora destas listas é
# trocado pelo padrão indicado, como o `_sanitize` do seed antigo fazia.
ENUMS: dict[tuple[str, str], tuple[set[str], str | None]] = {
    ("users", "role"): ({"admin", "manager"}, "manager"),
    ("restaurants", "status"): ({"ativo", "em_analise", "suspenso", "inativo"}, "em_analise"),
    ("drivers", "status"): ({"disponivel", "em_entrega", "offline", "indisponivel"}, "offline"),
    ("drivers", "vehicle_type"): ({"moto", "bike", "carro", "van"}, "moto"),
    ("drivers", "account_type"): ({"corrente", "poupanca", ""}, ""),
    ("drivers", "pix_key_type"): ({"cpf", "celular", "email", "aleatoria", ""}, ""),
    ("orders", "status"): ({"criado", "aguardando_coleta", "em_transito", "entregue",
                            "cancelado"}, "criado"),
    ("contracts", "status"): ({"ativo", "encerrado", "suspenso"}, "suspenso"),
    ("payments", "status"): ({"pendente", "pago", "atrasado", "cancelado"}, "pendente"),
    ("payments", "method"): ({"PIX", "Transferência", "Dinheiro", "Boleto"}, "PIX"),
    ("leads", "source"): ({"indicacao", "instagram", "prospeccao", "site", "whatsapp",
                           "evento", "outro"}, "outro"),
    ("leads", "stage"): ({"novo", "contatado", "negociacao", "proposta", "ganho",
                          "perdido"}, "novo"),
    ("activities", "kind"): ({"tarefa", "interacao"}, "tarefa"),
    ("activities", "type"): ({"ligacao", "whatsapp", "email", "reuniao", "visita", "nota",
                              "tarefa"}, "tarefa"),
    ("activities", "related_type"): ({"lead", "restaurante", "entregador", "pedido"}, None),
    ("forms", "target"): ({"lead", "restaurante", "entregador"}, "lead"),
    ("api_keys", "environment"): ({"production", "sandbox"}, "sandbox"),
}

# Faixas numéricas dos CHECK: valor fora é trazido para dentro.
FAIXAS: dict[tuple[str, str], tuple[float | None, float | None]] = {
    ("restaurants", "commission_rate"): (0, 100),
    ("drivers", "rating"): (0, 5),
    ("orders", "amount"): (0, None),
    ("orders", "delivery_fee"): (0, None),
    ("orders", "distance_km"): (0, 500),
    ("leads", "estimated_value"): (0, None),
    ("contracts", "value"): (0, None),
}


# ------------------------------------------------------------- conversão
def _para_datetime(valor: Any) -> datetime | None:
    """ISO em texto (como a API gravava) ou datetime do BSON (sempre UTC)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day, tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(valor).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _para_date(valor: Any) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor).strip()[:10])
    except ValueError:
        return None


def _json(valor: Any) -> Any:
    """Deixa o valor serializável para JSONB (datas e ObjectId viram texto)."""
    if isinstance(valor, dict):
        return {str(k): _json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json(v) for v in valor]
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def _converter_valor(tipo: str, valor: Any) -> Any:
    if valor is None:
        return None
    if tipo == "timestamp with time zone":
        return _para_datetime(valor)
    if tipo == "date":
        return _para_date(valor)
    if tipo == "jsonb":
        return _json(valor)
    if tipo == "boolean":
        return bool(valor)
    if tipo in ("double precision", "numeric", "real"):
        try:
            return float(valor)
        except (TypeError, ValueError):
            return None
    if tipo in ("integer", "bigint", "smallint"):
        try:
            return int(float(valor))
        except (TypeError, ValueError):
            return None
    return valor if isinstance(valor, str) else str(valor)


def sanear(tabela: str, linha: dict, extras: dict) -> None:
    """Regras de conserto do legado. Altera `linha` no lugar.

    `extras` recebe o valor original de um campo que precisou ser apagado,
    quando a tabela tem `extra_fields` — o dado não se perde, só sai da
    coluna que o recusaria.
    """
    for (t, col), (validos, padrao) in ENUMS.items():
        if t == tabela and col in linha and linha[col] not in validos:
            if linha[col] not in (None, ""):
                extras[f"{col}_original"] = linha[col]
            linha[col] = padrao

    for (t, col), (minimo, maximo) in FAIXAS.items():
        if t == tabela and isinstance(linha.get(col), (int, float)):
            if minimo is not None:
                linha[col] = max(minimo, linha[col])
            if maximo is not None:
                linha[col] = min(maximo, linha[col])

    if tabela == "drivers" and "cpf" in linha:
        digitos = "".join(c for c in str(linha["cpf"] or "") if c.isdigit())
        if digitos and len(digitos) != 11:
            extras["cpf_original"] = linha["cpf"]
            digitos = ""
        linha["cpf"] = digitos

    if tabela == "contracts" and linha.get("rule_type") == "comissao_entrega":
        linha["value"] = min(100.0, linha.get("value") or 0.0)

    if tabela == "payments" and (linha.get("amount") or 0) <= 0:
        # Pagamento sem valor positivo não passa no CHECK. O seed antigo já os
        # marcava como cancelados; aqui são recusados com o motivo registrado.
        linha["_recusar"] = "pagamento com valor zero ou negativo"

    if tabela == "orders" and not linha.get("external_ref"):
        # Vazio vira NULL: UNIQUE ignora NULL, e dois pedidos sem referência
        # não podem colidir por causa de um "".
        linha["external_ref"] = None


def converter(
    tabela: str, doc: dict, colunas: dict[str, dict]
) -> tuple[dict, set[str]]:
    """Documento do Mongo -> linha da tabela. Devolve (linha, chaves descartadas)."""
    doc = dict(doc)
    _id = doc.pop("_id", None)

    if tabela == "users":
        # O usuário era identificado pelo ObjectId; ele vira o id em texto.
        doc["id"] = str(_id)
    if tabela == "api_keys" and doc.get("key") and not doc.get("key_hash"):
        # Chave antiga em texto puro: guarda só o hash, como a API faz hoje.
        bruta = doc.pop("key")
        doc["key_hash"] = hashlib.sha256(bruta.encode("utf-8")).hexdigest()
        doc.setdefault("key_preview", f"{bruta[:13]}…{bruta[-4:]}")
    doc.pop("key", None)

    linha: dict = {}
    descartadas: set[str] = set()
    for chave, valor in doc.items():
        coluna = colunas.get(chave)
        if coluna is None:
            descartadas.add(chave)
            continue
        convertido = _converter_valor(coluna["tipo"], valor)
        # NULL numa coluna NOT NULL com DEFAULT: deixa o DEFAULT agir.
        if convertido is None and not coluna["nulo"]:
            continue
        linha[chave] = convertido

    extras: dict = {}
    sanear(tabela, linha, extras)
    if extras and "extra_fields" in colunas:
        linha["extra_fields"] = {**(linha.get("extra_fields") or {}), **extras}
    return linha, descartadas


# ------------------------------------------------------------- banco
async def colunas_do_destino(con: asyncpg.Connection) -> dict[str, dict[str, dict]]:
    linhas = await con.fetch(
        """
        SELECT table_name, column_name, data_type, is_nullable = 'YES' AS nulo
          FROM information_schema.columns
         WHERE table_schema = current_schema()
        """
    )
    out: dict[str, dict[str, dict]] = {}
    for r in linhas:
        out.setdefault(r["table_name"], {})[r["column_name"]] = {
            "tipo": r["data_type"], "nulo": r["nulo"]
        }
    return out


async def _inserir(con: asyncpg.Connection, tabela: str, linha: dict) -> None:
    campos = ", ".join(f'"{c}"' for c in linha)
    marcadores = ", ".join(f"${i}" for i in range(1, len(linha) + 1))
    await con.execute(
        f'INSERT INTO "{tabela}" ({campos}) VALUES ({marcadores})', *linha.values()
    )


async def _copiar_tabela(
    con: asyncpg.Connection, tabela: str, linhas: list[dict], recusados: list[dict]
) -> int:
    """Insere as linhas; a que o banco recusar vai para `recusados`.

    Primeiro em lote (`executemany`, que manda tudo de uma vez): com o banco
    remoto, uma ida por linha transformaria mil pedidos em minutos. Se o lote
    for recusado, ele é desfeito no seu SAVEPOINT e refeito linha a linha,
    cada uma no seu — assim só a linha problemática fica de fora, e a
    transação inteira segue.
    """
    erros = (asyncpg.IntegrityConstraintViolationError, asyncpg.DataError)
    grupos: dict[tuple, list[dict]] = {}
    for linha in linhas:
        motivo = linha.pop("_recusar", None)
        if motivo:
            recusados.append({"tabela": tabela, "motivo": motivo, "linha": _json(linha)})
            continue
        # executemany exige as mesmas colunas em todas as linhas do lote.
        grupos.setdefault(tuple(linha), []).append(linha)

    inseridas = 0
    for chaves, grupo in grupos.items():
        campos = ", ".join(f'"{c}"' for c in chaves)
        marcadores = ", ".join(f"${i}" for i in range(1, len(chaves) + 1))
        sql = f'INSERT INTO "{tabela}" ({campos}) VALUES ({marcadores})'
        try:
            async with con.transaction():
                await con.executemany(sql, [tuple(l.values()) for l in grupo])
            inseridas += len(grupo)
            continue
        except erros:
            pass
        for linha in grupo:
            try:
                async with con.transaction():
                    await _inserir(con, tabela, linha)
                inseridas += 1
            except erros as erro:
                recusados.append({
                    "tabela": tabela,
                    "motivo": f"{type(erro).__name__}: {erro}",
                    "linha": _json(linha),
                })
    return inseridas


async def aplicar_schema(con: asyncpg.Connection) -> None:
    for arquivo in sorted(DIR_SQL.glob("*.sql")):
        await con.execute(arquivo.read_text(encoding="utf-8"))


async def transferir(
    con: asyncpg.Connection,
    fonte: dict[str, Iterable[dict]],
    *,
    simular: bool = False,
    forcar: bool = False,
) -> dict:
    """Copia `fonte` (coleção -> documentos) para o banco de `con`.

    Separado da leitura do Mongo para poder ser testado com dicionários.
    """
    await con.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads,
                             schema="pg_catalog")
    await aplicar_schema(con)
    colunas = await colunas_do_destino(con)

    if not forcar:
        for tabela in ORDEM:
            if await con.fetchval(f'SELECT EXISTS (SELECT 1 FROM "{tabela}")'):
                raise SystemExit(
                    f"A tabela {tabela} já tem dados. A transferência é para um banco "
                    "vazio — rodar duas vezes duplicaria tudo. Use --forcar só se "
                    "souber o que está fazendo."
                )

    relatorio: dict = {"tabelas": {}, "recusados": []}
    transacao = con.transaction()
    await transacao.start()
    try:
        for tabela in ORDEM:
            docs = list(fonte.get(tabela, ()))
            linhas, descartadas = [], {}
            for doc in docs:
                linha, fora = converter(tabela, doc, colunas[tabela])
                for chave in fora:
                    descartadas[chave] = descartadas.get(chave, 0) + 1
                linhas.append(linha)
            if tabela == "form_submissions":
                # Resposta de formulário já apagado: a chave estrangeira a
                # recusaria. Vai para os recusados com motivo claro.
                existentes = {r["id"] for r in await con.fetch("SELECT id FROM forms")}
                for linha in linhas:
                    if linha.get("form_id") not in existentes:
                        linha["_recusar"] = "formulário de origem não existe mais"
            inseridas = await _copiar_tabela(con, tabela, linhas, relatorio["recusados"])
            relatorio["tabelas"][tabela] = {
                "origem": len(docs), "inseridas": inseridas, "campos_sem_coluna": descartadas,
            }

        # O contador precisa ficar acima do maior PED- já usado, venha ele do
        # Mongo ou não.
        await con.execute(
            """
            INSERT INTO counters (name, value)
            SELECT 'order_code',
                   COALESCE(MAX(NULLIF(substring(code FROM '([0-9]+)$'), '')::bigint) - 1000, 0)
              FROM orders WHERE code LIKE 'PED-%'
            ON CONFLICT (name) DO UPDATE SET value = GREATEST(counters.value, EXCLUDED.value)
            """
        )
    except BaseException:
        await transacao.rollback()
        raise
    if simular:
        await transacao.rollback()
    else:
        await transacao.commit()
    return relatorio


def ler_mongo(url: str, banco: str) -> dict[str, list[dict]]:
    try:
        from pymongo import MongoClient
    except ImportError:
        raise SystemExit("pymongo não instalado. Rode: pip install pymongo")
    cliente = MongoClient(url, serverSelectionTimeoutMS=10_000)
    base = cliente[banco]
    existentes = set(base.list_collection_names())
    desconhecidas = existentes - set(ORDEM) - IGNORADAS
    if desconhecidas:
        print(f"aviso: coleções sem tabela, não copiadas: {', '.join(sorted(desconhecidas))}")
    return {nome: list(base[nome].find({})) for nome in ORDEM if nome in existentes}


def imprimir(relatorio: dict, simular: bool) -> None:
    print(f"\n{'tabela':<18}{'origem':>8}{'inseridas':>11}  campos sem coluna")
    for tabela, r in relatorio["tabelas"].items():
        fora = ", ".join(f"{k} ({n})" for k, n in sorted(r["campos_sem_coluna"].items()))
        print(f"{tabela:<18}{r['origem']:>8}{r['inseridas']:>11}  {fora}")
    recusados = relatorio["recusados"]
    print(f"\nrecusados: {len(recusados)}")
    if recusados:
        destino = RAIZ / "backups/transferencia_recusados.json"
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(json.dumps(recusados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"detalhes em {destino} — contém dado pessoal, trate como o próprio banco.")
    print("\nSIMULAÇÃO: nada foi gravado." if simular else "\nTransferência concluída.")


async def main() -> None:
    args = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    args.add_argument("--simular", action="store_true", help="roda e desfaz no fim")
    args.add_argument("--forcar", action="store_true", help="aceita destino com dados")
    opcoes = args.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for var in ("MONGO_URL", "DB_NAME", "DATABASE_URL"):
        if not os.environ.get(var):
            raise SystemExit(f"Defina {var}.")

    fonte = ler_mongo(os.environ["MONGO_URL"], os.environ["DB_NAME"])
    print("lido do Mongo: " + ", ".join(f"{k} {len(v)}" for k, v in fonte.items()))
    con = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    try:
        relatorio = await transferir(con, fonte, simular=opcoes.simular, forcar=opcoes.forcar)
    finally:
        await con.close()
    imprimir(relatorio, opcoes.simular)


if __name__ == "__main__":
    asyncio.run(main())
