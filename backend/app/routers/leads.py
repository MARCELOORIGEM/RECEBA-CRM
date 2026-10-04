"""Funil comercial.

A Miliano prospecta restaurantes e recruta entregadores, mas o sistema só sabia
lidar com quem já era cliente. Sem funil não há previsão de receita, não há
motivo de perda e não há como saber quem precisa de follow-up hoje.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, pg, repo
from ..deps import get_current_user, require_admin
from ..permissoes import acesso
from ..models import LeadInput, LeadStagePatch
from ..repo import get_or_404
from ..security import now_iso, now_utc

router = APIRouter(prefix="/leads", tags=["funil"], dependencies=[Depends(acesso("funil"))])

STAGES = ["novo", "contatado", "negociacao", "proposta", "ganho", "perdido"]
STAGE_LABEL = {
    "novo": "Novo",
    "contatado": "Contatado",
    "negociacao": "Em negociação",
    "proposta": "Proposta enviada",
    "ganho": "Ganho",
    "perdido": "Perdido",
}


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
    page: int = 1,
    page_size: int = 200,
    user: dict = Depends(get_current_user),
):
    f = repo.filtro("leads")
    if stage != "todos":
        f.igual("stage", stage)
    if source != "todos":
        f.igual("source", source)
    f.busca(search, ["name", "contact_name", "city", "phone", "email"])
    return await repo.paginar("leads", f, page=page, page_size=page_size,
                              ordenar_por="updated_at", direcao="desc")


@router.get("/funnel")
async def funnel(user: dict = Depends(get_current_user)):
    """Resumo por etapa: quantidade, valor estimado e taxa de conversão."""
    buckets = {
        r["stage"]: r
        for r in await pg.varios(
            "SELECT stage, count(*) AS qtd, COALESCE(SUM(estimated_value), 0) AS valor "
            "FROM leads GROUP BY stage"
        )
    }
    stages = [
        {
            "stage": s,
            "label": STAGE_LABEL[s],
            "qtd": buckets.get(s, {}).get("qtd", 0),
            "valor": round(float(buckets.get(s, {}).get("valor", 0.0)), 2),
        }
        for s in STAGES
    ]
    ganhos = buckets.get("ganho", {}).get("qtd", 0)
    perdidos = buckets.get("perdido", {}).get("qtd", 0)
    fechados = ganhos + perdidos
    abertos = [s for s in stages if s["stage"] not in ("ganho", "perdido")]
    return {
        "stages": stages,
        "em_aberto": sum(s["qtd"] for s in abertos),
        "valor_em_aberto": round(sum(s["valor"] for s in abertos), 2),
        "taxa_conversao": round(ganhos / fechados * 100, 1) if fechados else 0.0,
        "ganhos": ganhos,
        "perdidos": perdidos,
    }


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
    patch["stage"] = before["stage"]  # etapa muda só pelo endpoint dedicado
    patch["updated_at"] = now_utc()
    after = await repo.atualizar("leads", lid, patch)
    await audit.record(user, "atualizou", "lead", lid, label=after["name"],
                       before=before, after=after)
    return after


@router.patch("/{lid}/stage")
async def move_stage(lid: str, body: LeadStagePatch, user: dict = Depends(get_current_user)):
    before = await get_or_404("leads", lid, "Lead")
    if body.stage == "perdido" and not body.lost_reason.strip():
        raise HTTPException(
            status_code=422, detail="Informe o motivo da perda para mover o lead para 'Perdido'."
        )
    after = await _mover(
        lid,
        {"stage": body.stage, "updated_at": now_utc(),
         "lost_reason": body.lost_reason if body.stage == "perdido" else ""},
        _etapa(body.stage, user["name"]),
    )
    await audit.record(user, "moveu no funil", "lead", lid, label=after["name"],
                       before=before, after=after)
    return after


@router.post("/{lid}/convert")
async def convert_lead(lid: str, user: dict = Depends(get_current_user)):
    """Vira cliente: cria o restaurante já preenchido e fecha o lead como ganho."""
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
        "address": lead.get("city", ""),
        "commission_rate": 15.0,
        "status": "em_analise",
        "notes": f"Convertido do funil. Origem: {lead.get('source', '-')}.",
        "created_by": user["name"],
    })
    lead_atualizado = await _mover(
        lid,
        {"stage": "ganho", "converted_restaurant_id": restaurante["id"],
         "updated_at": now_utc()},
        _etapa("ganho", user["name"]),
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
