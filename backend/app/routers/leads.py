"""Funil comercial.

A Miliano prospecta restaurantes e recruta entregadores, mas o sistema só sabia
lidar com quem já era cliente. Sem funil não há previsão de receita, não há
motivo de perda e não há como saber quem precisa de follow-up hoje.
"""
import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from .. import audit, funil, pg, repo
from ..deps import get_current_user, require_admin
from ..permissoes import acesso
from ..models import LeadInput, LeadStagePatch
from ..planilha_leads import PlanilhaInvalida, gerar_modelo, interpretar, ler_arquivo
from ..repo import get_or_404
from ..security import now_iso, now_utc

router = APIRouter(prefix="/leads", tags=["funil"], dependencies=[Depends(acesso("funil"))])

# Colunas da busca livre: o LEAD ID e o bairro são o que o BD digita para
# achar um restaurante na carteira.
BUSCA = ["name", "codigo_externo", "contact_name", "endereco", "bairro", "city", "phone",
         "email", "bd_nome", "lider"]


def _etapa(stage: str, autor: str) -> dict:
    """Entrada do histórico. A data fica em texto ISO porque vive dentro do
    JSONB, onde não há tipo de data — é o mesmo formato que o painel já lê."""
    return {"stage": stage, "at": now_iso(), "by": autor}


async def _mover(lid: str, campos: dict, entrada: dict) -> dict:
    """Atualiza o lead e acrescenta a entrada ao histórico no mesmo comando.

    Era `$set` + `$push`. A concatenação `||` é feita pelo banco: ler a lista,
    acrescentar e regravar perderia uma etapa se duas pessoas movessem o mesmo
    card ao mesmo tempo.
    """
    args: list = []
    atribuicoes = []
    for k, v in campos.items():
        args.append(v)
        atribuicoes.append(f"{repo.coluna('leads', k)} = ${len(args)}")
    args.append([entrada])
    atribuicoes.append(f"stage_history = stage_history || ${len(args)}::jsonb")
    args.append(lid)
    return await pg.um(
        f"UPDATE leads SET {', '.join(atribuicoes)} WHERE id = ${len(args)} RETURNING *", *args
    )


@router.get("")
async def list_leads(
    search: str = "",
    stage: str = "todos",
    source: str = "todos",
    lider: str = "",
    bd: str = "",
    bairro: str = "",
    page: int = 1,
    page_size: int = 200,
    user: dict = Depends(get_current_user),
):
    f = repo.filtro("leads")
    if stage != "todos":
        f.igual("stage", stage)
    if source != "todos":
        f.igual("source", source)
    f.igual("lider", lider)
    f.igual("bd_nome", bd)
    f.igual("bairro", bairro)
    f.busca(search, BUSCA)
    return await repo.paginar("leads", f, page=page, page_size=page_size,
                              ordenar_por="updated_at", direcao="desc")


@router.get("/filtros")
async def filtros(user: dict = Depends(get_current_user)):
    """Valores existentes de líder, BD e bairro, para os filtros da tela.

    Vêm do próprio funil (o que a planilha trouxe), não de um cadastro à
    parte: um líder novo aparece no filtro assim que o primeiro lead dele
    entra.
    """
    linhas = await pg.um(
        """
        SELECT
          COALESCE(array_agg(DISTINCT lider)   FILTER (WHERE lider   <> ''), '{}') AS lideres,
          COALESCE(array_agg(DISTINCT bd_nome) FILTER (WHERE bd_nome <> ''), '{}') AS bds,
          COALESCE(array_agg(DISTINCT bairro)  FILTER (WHERE bairro  <> ''), '{}') AS bairros
        FROM leads
        """
    )
    return {k: sorted(v, key=str.casefold) for k, v in linhas.items()}


@router.get("/funnel")
async def funnel(user: dict = Depends(get_current_user)):
    """Resumo por status: quantidade, valor estimado e taxa de conversão."""
    buckets = {
        r["stage"]: r
        for r in await pg.varios(
            "SELECT stage, count(*) AS qtd, COALESCE(SUM(estimated_value), 0) AS valor "
            "FROM leads GROUP BY stage"
        )
    }
    stages = [
        {
            "stage": s.chave,
            "label": s.rotulo,
            "grupo": s.grupo,
            "qtd": buckets.get(s.chave, {}).get("qtd", 0),
            "valor": round(float(buckets.get(s.chave, {}).get("valor", 0.0)), 2),
        }
        for s in funil.STATUS
    ]
    ganhos = sum(s["qtd"] for s in stages if s["grupo"] == "ganho")
    perdidos = sum(s["qtd"] for s in stages if s["grupo"] == "perdido")
    fechados = ganhos + perdidos
    abertos = [s for s in stages if s["grupo"] == "aberto"]
    return {
        "stages": stages,
        "em_aberto": sum(s["qtd"] for s in abertos),
        "valor_em_aberto": round(sum(s["valor"] for s in abertos), 2),
        "taxa_conversao": round(ganhos / fechados * 100, 1) if fechados else 0.0,
        "ganhos": ganhos,
        "perdidos": perdidos,
    }


# ------------------------------------------------------------- planilha
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Colunas gravadas na importação, nesta ordem (o executemany precisa de todas
# as linhas com as mesmas colunas).
_COLUNAS_IMPORTACAO = (
    "id", "name", "contact_name", "phone", "email", "city", "category", "source", "stage",
    "estimated_value", "owner_name", "notes", "lost_reason", "stage_history", "origem",
    "created_by", "codigo_externo", "endereco", "bairro", "bd_id", "bd_nome", "lider",
    "data_visita",
)

# Campos que a planilha pode alterar num lead que já existe (mesmo LEAD ID).
_ATUALIZAVEIS = (
    "name", "endereco", "bairro", "bd_id", "bd_nome", "lider", "data_visita", "stage", "notes",
    "phone", "contact_name", "email", "city", "category", "source", "estimated_value",
    "lost_reason", "owner_name",
)
_ROTULO_IMPORTACAO = {
    "name": "Nome", "endereco": "Endereço", "bairro": "Bairro", "bd_id": "BD ID",
    "bd_nome": "Nome BD", "lider": "Líder", "data_visita": "Data visita", "stage": "Status",
    "notes": "Obs", "phone": "Telefone", "contact_name": "Contato", "email": "E-mail",
    "city": "Cidade", "category": "Categoria", "source": "Origem",
    "estimated_value": "Valor estimado", "lost_reason": "Motivo", "owner_name": "Responsável",
}


def _mostrar(campo: str, valor) -> str:
    if valor in (None, ""):
        return "—"
    if campo == "stage":
        return funil.POR_CHAVE[valor].rotulo if valor in funil.POR_CHAVE else str(valor)
    if campo == "data_visita":
        return valor.strftime("%d/%m/%Y")
    return str(valor)


def _digitos(telefone: str) -> str:
    """Telefone só com números, sem o 55 do país: "(11) 9 8888-1234" e
    "+55 11 988881234" são o mesmo número."""
    d = re.sub(r"\D", "", telefone or "")
    if len(d) > 11 and d.startswith("55"):
        d = d[2:]
    return d if len(d) >= 8 else ""


@router.get("/modelo")
async def baixar_modelo(atual: bool = Query(False)):
    """Planilha para preencher e importar.

    `atual=true` devolve o funil de hoje no mesmo formato — dá para editar e
    importar de volta, e o que já existe é reconhecido em vez de duplicar.
    """
    leads = await repo.listar("leads", ordenar_por="created_at", direcao="asc") if atual else None
    nome = f"funil-{date.today().isoformat()}.xlsx" if atual else "modelo-importacao-funil.xlsx"
    return Response(
        content=gerar_modelo(leads),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("/importar")
async def importar_planilha(
    arquivo: UploadFile = File(...),
    simular: bool = Query(True),
    user: dict = Depends(get_current_user),
):
    """Importa leads de uma planilha (.xlsx ou .csv).

    Por padrão SIMULA: devolve o que entraria, o que tem erro e o que já
    existe, sem gravar nada. Com `simular=false`, grava os novos de uma vez,
    numa transação só — ou entram todos, ou nenhum.
    """
    dados = await arquivo.read()
    try:
        resultado = interpretar(ler_arquivo(dados, arquivo.filename or ""))
    except PlanilhaInvalida as e:
        raise HTTPException(status_code=422, detail=str(e))

    # LEAD ID que já está no funil: a linha ATUALIZA aquele lead. É assim
    # que a operação trabalha — o BD muda o STATUS na planilha e ela volta.
    codigos = [l["codigo_externo"] for l in resultado.validos if l["codigo_externo"]]
    atuais = {
        r["codigo_externo"]: r
        for r in await pg.varios("SELECT * FROM leads WHERE codigo_externo = ANY($1)", codigos)
    } if codigos else {}

    # Sem LEAD ID, o que já existe é reconhecido por e-mail ou telefone. Nome
    # sozinho não serve: há mais de uma "Pizzaria Bella" na mesma cidade.
    existentes = await pg.varios("SELECT email, phone FROM leads")
    emails = {(e["email"] or "").strip().lower() for e in existentes} - {""}
    fones = {_digitos(e["phone"]) for e in existentes} - {""}

    novos, atualizacoes, duplicados = [], [], []
    inalterados = 0
    vistos: set[str] = set()
    for lead in resultado.validos:
        codigo = lead["codigo_externo"]
        if codigo and codigo in vistos:
            duplicados.append({"linha": lead["linha"], "nome": lead["name"],
                               "motivo": f"LEAD ID {codigo} repetido na planilha"})
            continue
        if codigo:
            vistos.add(codigo)

        if codigo in atuais:
            atual = atuais[codigo]
            mudancas = {
                campo: lead[campo]
                for campo in _ATUALIZAVEIS
                # Célula vazia não apaga o que está gravado.
                if campo in lead["_preenchidos"] and lead[campo] != atual[campo]
            }
            if "stage" in mudancas and not funil.e_perdido(mudancas["stage"]):
                mudancas["lost_reason"] = ""
            if mudancas:
                atualizacoes.append({"lead": atual, "linha": lead["linha"], "mudancas": mudancas})
            else:
                inalterados += 1
            continue

        email = (lead.get("email") or "").strip().lower()
        fone = _digitos(lead.get("phone") or "")
        if email and email in emails:
            motivo = f"e-mail {email} já está no funil"
        elif fone and fone in fones:
            motivo = f"telefone {lead.get('phone')} já está no funil"
        else:
            novos.append(lead)
            # Também barra a repetição dentro da própria planilha.
            if email:
                emails.add(email)
            if fone:
                fones.add(fone)
            continue
        duplicados.append({"linha": lead["linha"], "nome": lead["name"], "motivo": motivo})

    def _descrever(a: dict) -> list[str]:
        antes = a["lead"]
        return [
            f"{_ROTULO_IMPORTACAO[c]}: {_mostrar(c, antes[c])} → {_mostrar(c, v)}"
            for c, v in a["mudancas"].items()
            # Limpar o motivo é consequência da troca de status, não notícia.
            if c in _ROTULO_IMPORTACAO and not (c == "lost_reason" and v == "")
        ]

    resposta = {
        "total": resultado.total,
        "novos": len(novos),
        "atualizados": [
            {"linha": a["linha"], "nome": a["lead"]["name"],
             "codigo": a["lead"]["codigo_externo"], "mudancas": _descrever(a)}
            for a in atualizacoes
        ],
        "inalterados": inalterados,
        "duplicados": duplicados,
        "erros": resultado.erros,
        "colunas_ignoradas": resultado.colunas_ignoradas,
        "previa": [
            {k: lead.get(k) for k in ("linha", "codigo_externo", "name", "bairro", "bd_nome",
                                      "lider", "data_visita", "stage")}
            for lead in novos[:15]
        ],
        "importados": 0,
        "atualizados_gravados": 0,
    }
    if simular or not (novos or atualizacoes):
        return resposta

    agora_iso, agora = now_iso(), now_utc()
    autor = f"Planilha ({user['name']})"
    linhas = [
        (
            str(uuid.uuid4()), lead["name"], lead["contact_name"], lead["phone"], lead["email"],
            lead["city"], lead["category"], lead["source"], lead["stage"],
            lead["estimated_value"], lead["owner_name"] or user["name"], lead["notes"],
            lead["lost_reason"] if funil.e_perdido(lead["stage"]) else "",
            [{"stage": lead["stage"], "at": agora_iso, "by": autor}],
            "planilha", user["name"], lead["codigo_externo"], lead["endereco"], lead["bairro"],
            lead["bd_id"], lead["bd_nome"], lead["lider"], lead["data_visita"],
        )
        for lead in novos
    ]
    campos = ", ".join(_COLUNAS_IMPORTACAO)
    marcadores = ", ".join(f"${i}" for i in range(1, len(_COLUNAS_IMPORTACAO) + 1))
    # Tudo numa transação: um erro no lead 300 não deixa 299 gravados e a
    # pessoa sem saber de onde recomeçar.
    async with pg.pool().acquire() as con:
        async with con.transaction():
            if linhas:
                await con.executemany(
                    f"INSERT INTO leads ({campos}) VALUES ({marcadores})", linhas
                )
            for a in atualizacoes:
                sets, args = [], []
                for campo, valor in a["mudancas"].items():
                    args.append(valor)
                    sets.append(f"{repo.coluna('leads', campo)} = ${len(args)}")
                args.append(agora)
                sets.append(f"updated_at = ${len(args)}")
                if "stage" in a["mudancas"]:
                    # A troca de status entra no histórico, como na tela.
                    args.append([{"stage": a["mudancas"]["stage"], "at": agora_iso, "by": autor}])
                    sets.append(f"stage_history = stage_history || ${len(args)}::jsonb")
                args.append(a["lead"]["id"])
                await con.execute(
                    f"UPDATE leads SET {', '.join(sets)} WHERE id = ${len(args)}", *args
                )

    await audit.record(
        user, "importou planilha", "lead", "",
        label=(f"{len(novos)} novo(s), {len(atualizacoes)} atualizado(s) de "
               f"{arquivo.filename or 'planilha'}"),
    )
    resposta["importados"] = len(novos)
    resposta["atualizados_gravados"] = len(atualizacoes)
    return resposta


@router.get("/{lid}")
async def get_lead(lid: str, user: dict = Depends(get_current_user)):
    return await get_or_404("leads", lid, "Lead")


@router.post("", status_code=201)
async def create_lead(data: LeadInput, user: dict = Depends(get_current_user)):
    doc = data.model_dump()
    doc.update({
        "id": str(uuid.uuid4()),
        "owner_name": doc.get("owner_name") or user["name"],
        "stage_history": [_etapa(doc["stage"], user["name"])],
        "created_by": user["name"],
    })
    criado = await repo.inserir("leads", doc)
    await audit.record(user, "criou", "lead", criado["id"], label=criado["name"], after=criado)
    return criado


@router.put("/{lid}")
async def update_lead(lid: str, data: LeadInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("leads", lid, "Lead")
    patch = data.model_dump()
    patch["stage"] = before["stage"]  # status muda só pelo endpoint dedicado
    patch["lost_reason"] = before["lost_reason"]
    patch["updated_at"] = now_utc()
    after = await repo.atualizar("leads", lid, patch)
    await audit.record(user, "atualizou", "lead", lid, label=after["name"],
                       before=before, after=after)
    return after


@router.patch("/{lid}/stage")
async def move_stage(lid: str, body: LeadStagePatch, user: dict = Depends(get_current_user)):
    before = await get_or_404("leads", lid, "Lead")
    status = funil.POR_CHAVE[body.stage]
    if status.pede_motivo and not body.lost_reason.strip():
        raise HTTPException(
            status_code=422,
            detail=f"Informe o motivo para mover o lead para '{status.rotulo}'.",
        )
    after = await _mover(
        lid,
        # O motivo só fica gravado enquanto o lead está descartado: voltar a
        # trabalhar nele limpa o motivo antigo.
        {"stage": body.stage, "updated_at": now_utc(),
         "lost_reason": body.lost_reason.strip() if funil.e_perdido(body.stage) else ""},
        _etapa(body.stage, user["name"]),
    )
    await audit.record(user, "moveu no funil", "lead", lid, label=after["name"],
                       before=before, after=after)
    return after


@router.post("/{lid}/convert")
async def convert_lead(lid: str, user: dict = Depends(get_current_user)):
    """Vira cliente: cria o restaurante já preenchido e marca o lead como ativado."""
    lead = await get_or_404("leads", lid, "Lead")
    if lead.get("converted_restaurant_id"):
        raise HTTPException(status_code=409, detail="Este lead já foi convertido")

    restaurante = await repo.inserir("restaurants", {
        "id": str(uuid.uuid4()),
        "name": lead["name"],
        "category": lead.get("category") or "Outros",
        "contact_person": lead.get("contact_name", ""),
        "email": lead.get("email", ""),
        "phone": lead.get("phone", ""),
        # Endereço completo que o BD levantou na visita, quando houver.
        "address": " - ".join(
            p for p in (lead.get("endereco"), lead.get("bairro"), lead.get("city")) if p
        ),
        "commission_rate": 15.0,
        "status": "em_analise",
        "notes": " ".join(filter(None, [
            f"Convertido do funil. Origem: {lead.get('source', '-')}.",
            f"Lead ID {lead['codigo_externo']}." if lead.get("codigo_externo") else "",
            f"BD: {lead['bd_nome']}." if lead.get("bd_nome") else "",
        ])),
        "created_by": user["name"],
    })
    lead_atualizado = await _mover(
        lid,
        {"stage": funil.GANHO, "converted_restaurant_id": restaurante["id"],
         "updated_at": now_utc()},
        _etapa(funil.GANHO, user["name"]),
    )
    await repo.atualizar_onde(
        "activities",
        repo.filtro("activities").igual("related_type", "lead").igual("related_id", lid),
        {"related_type": "restaurante", "related_id": restaurante["id"]},
    )
    await audit.record(user, "converteu lead", "lead", lid, label=lead["name"], after=restaurante)
    return {"lead": lead_atualizado, "restaurant": restaurante}


@router.delete("/{lid}")
async def delete_lead(lid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("leads", lid, "Lead")
    await repo.remover("leads", lid)
    await repo.remover_onde(
        "activities",
        repo.filtro("activities").igual("related_type", "lead").igual("related_id", lid),
    )
    await audit.record(admin, "removeu", "lead", lid, label=doc["name"], before=doc)
    return {"message": "Removido"}
