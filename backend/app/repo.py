"""Acesso a dados — o que os routers usam no lugar das chamadas ao Mongo.

Cada função aqui existe porque a mesma linha se repetia em treze arquivos. A
tradução de Mongo para SQL ficou contida neste módulo e em `consulta.py`: os
routers passam a pedir "o pedido X" em vez de montar `{"id": x}` e lembrar da
projeção que esconde o `_id`.

Uma diferença de comportamento vale registrar: no Mongo, gravar um campo que
ninguém declarou simplesmente acrescentava uma chave ao documento. Aqui, uma
coluna inexistente é erro — e é por isso que `scripts/conferir_schema.py`
existe, para que esse erro apareça no CI e não em produção.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from . import pg
from .consulta import Filtro, coluna, ordenacao

# Tabelas cujo `id` é gerado pela aplicação (uuid4) — todas, menos as efêmeras.
PAGINA_MAXIMA = 200


# ------------------------------------------------------------------ leitura
async def pegar(tabela: str, doc_id: str) -> dict | None:
    return await pg.um(f'SELECT * FROM "{_tabela(tabela)}" WHERE id = $1', doc_id)


async def get_or_404(tabela: str, doc_id: str, rotulo: str) -> dict:
    doc = await pegar(tabela, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"{rotulo} não encontrado")
    return doc


async def um_por(tabela: str, campo: str, valor) -> dict | None:
    """Primeira linha com `campo = valor` — e-mail, slug, código, hash."""
    col = coluna(tabela, campo)
    return await pg.um(f'SELECT * FROM "{_tabela(tabela)}" WHERE {col} = $1 LIMIT 1', valor)


async def existe(tabela: str, campo: str, valor) -> bool:
    col = coluna(tabela, campo)
    return bool(
        await pg.valor(f'SELECT 1 FROM "{_tabela(tabela)}" WHERE {col} = $1 LIMIT 1', valor)
    )


async def listar(
    tabela: str,
    filtro: Filtro | None = None,
    *,
    ordenar_por: str = "created_at",
    direcao: str = "desc",
    limite: int | None = None,
) -> list[dict]:
    onde, args = (filtro.onde() if filtro else ("", []))
    sql = (
        f'SELECT * FROM "{_tabela(tabela)}" {onde} '
        f"{ordenacao(tabela, ordenar_por, direcao)}"
    )
    if limite:
        args = [*args, int(limite)]
        sql += f" LIMIT ${len(args)}"
    return await pg.varios(sql, *args)


async def contar(tabela: str, filtro: Filtro | None = None) -> int:
    onde, args = (filtro.onde() if filtro else ("", []))
    return int(await pg.valor(f'SELECT count(*) FROM "{_tabela(tabela)}" {onde}', *args) or 0)


async def somar(tabela: str, campo: str, filtro: Filtro | None = None) -> float:
    """Soma de uma coluna.

    `COALESCE` porque `SUM` de conjunto vazio devolve NULL, não zero — e um
    None escapando daqui viraria "R$ None" na tela do financeiro.
    """
    col = coluna(tabela, campo)
    onde, args = (filtro.onde() if filtro else ("", []))
    total = await pg.valor(
        f'SELECT COALESCE(SUM({col}), 0) FROM "{_tabela(tabela)}" {onde}', *args
    )
    return round(float(total or 0), 2)


async def paginar(
    tabela: str,
    filtro: Filtro | None = None,
    *,
    page: int = 1,
    page_size: int = 25,
    ordenar_por: str = "created_at",
    direcao: str = "desc",
) -> dict[str, Any]:
    """Página de resultados, no mesmo formato que o painel já consome."""
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 25), PAGINA_MAXIMA))
    onde, args = (filtro.onde() if filtro else ("", []))

    total = int(await pg.valor(f'SELECT count(*) FROM "{_tabela(tabela)}" {onde}', *args) or 0)
    itens = await pg.varios(
        f'SELECT * FROM "{_tabela(tabela)}" {onde} '
        f"{ordenacao(tabela, ordenar_por, direcao)} "
        f"LIMIT ${len(args) + 1} OFFSET ${len(args) + 2}",
        *args,
        page_size,
        (page - 1) * page_size,
    )
    return {
        "items": itens,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


# ------------------------------------------------------------------ escrita
async def inserir(tabela: str, dados: dict) -> dict:
    """INSERT com as colunas conferidas, devolvendo a linha gravada.

    Devolver a linha (em vez de reler depois) economiza uma ida ao banco — que
    a 200 ms de distância não é detalhe — e garante que o que volta é o que
    ficou gravado, com os DEFAULT do schema já aplicados.
    """
    campos = [coluna(tabela, k) for k in dados]
    marcadores = [f"${i}" for i in range(1, len(dados) + 1)]
    sql = (
        f'INSERT INTO "{_tabela(tabela)}" ({", ".join(campos)}) '
        f'VALUES ({", ".join(marcadores)}) RETURNING *'
    )
    return await pg.um(sql, *dados.values())


async def atualizar(tabela: str, doc_id: str, campos: dict) -> dict | None:
    """UPDATE por id. Dicionário vazio não vira SQL — devolve a linha atual."""
    if not campos:
        return await pegar(tabela, doc_id)
    atribuicoes = [f"{coluna(tabela, k)} = ${i}" for i, k in enumerate(campos, start=1)]
    sql = (
        f'UPDATE "{_tabela(tabela)}" SET {", ".join(atribuicoes)} '
        f"WHERE id = ${len(campos) + 1} RETURNING *"
    )
    return await pg.um(sql, *campos.values(), doc_id)


async def incrementar(
    tabela: str, doc_id: str, campos: dict[str, float], *, definir: dict | None = None
) -> dict | None:
    """Soma valores a colunas numéricas, no banco.

    Era `$inc`. Importa ser feito pelo banco, e não lendo-somando-gravando: dois
    pedidos entregues ao mesmo tempo para o mesmo entregador perderiam um dos
    lançamentos, e a diferença só apareceria no fechamento do mês.

    `definir` grava outras colunas no mesmo UPDATE — o `$set` que andava junto
    do `$inc`, quase sempre o `updated_at`.
    """
    definir = definir or {}
    if not campos and not definir:
        return await pegar(tabela, doc_id)
    args: list = []
    atribuicoes = []
    for k, v in campos.items():
        args.append(v)
        atribuicoes.append(f"{coluna(tabela, k)} = {coluna(tabela, k)} + ${len(args)}")
    for k, v in definir.items():
        args.append(v)
        atribuicoes.append(f"{coluna(tabela, k)} = ${len(args)}")
    args.append(doc_id)
    sql = (
        f'UPDATE "{_tabela(tabela)}" SET {", ".join(atribuicoes)} '
        f"WHERE id = ${len(args)} RETURNING *"
    )
    return await pg.um(sql, *args)


async def atualizar_onde(tabela: str, filtro: Filtro, campos: dict) -> int:
    """UPDATE em lote — o `update_many`. Devolve quantas linhas mudaram.

    As condições do filtro já ocupam `$1..$n`; os valores do SET entram depois
    deles, por isso a numeração parte de onde o filtro parou.
    """
    onde, args = filtro.onde()
    if not onde:
        # Mesmo motivo de `remover_onde`: sem condição, seria a tabela inteira.
        raise ValueError(f"atualizar_onde em {tabela} sem nenhuma condição")
    if not campos:
        return 0
    atribuicoes = []
    for k, v in campos.items():
        args.append(v)
        atribuicoes.append(f"{coluna(tabela, k)} = ${len(args)}")
    resultado = await pg.executar(
        f'UPDATE "{_tabela(tabela)}" SET {", ".join(atribuicoes)} {onde}', *args
    )
    return int(resultado.rsplit(" ", 1)[-1] or 0)


async def remover(tabela: str, doc_id: str) -> bool:
    resultado = await pg.executar(f'DELETE FROM "{_tabela(tabela)}" WHERE id = $1', doc_id)
    return resultado.endswith(" 1")


async def remover_onde(tabela: str, filtro: Filtro) -> int:
    onde, args = filtro.onde()
    if not onde:
        # Um filtro vazio aqui apagaria a tabela inteira. Nenhuma chamada do
        # sistema quer isso, então é erro de programação, não operação válida.
        raise ValueError(f"remover_onde em {tabela} sem nenhuma condição")
    resultado = await pg.executar(f'DELETE FROM "{_tabela(tabela)}" {onde}', *args)
    return int(resultado.rsplit(" ", 1)[-1] or 0)


# ------------------------------------------------------------------ apoio
def _tabela(nome: str) -> str:
    from .consulta import COLUNAS

    if nome not in COLUNAS:
        raise ValueError(f"tabela desconhecida: {nome}")
    return nome


def campo_de_ordenacao(tabela: str, campo: str, padrao: str = "created_at") -> str:
    """O `sort_field` da query string, ou o padrão se não for coluna da tabela.

    O Mongo ordenava por campo inexistente sem reclamar. Aqui o nome entra no
    texto do SQL e é conferido antes (ver `consulta.coluna`), então um valor
    torto vindo do navegador viraria 500. Cai no padrão, como antes.
    """
    from .consulta import COLUNAS

    return campo if campo in COLUNAS.get(tabela, ()) else padrao


def filtro(tabela: str) -> Filtro:
    """Atalho, para o router não precisar importar `consulta`."""
    return Filtro(tabela)
