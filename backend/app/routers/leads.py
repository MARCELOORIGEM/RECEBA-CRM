"""Funil comercial.

A Miliano prospecta restaurantes e recruta entregadores, mas o sistema só sabia
lidar com quem já era cliente. Sem funil não há previsão de receita, não há
motivo de perda e não há como saber quem precisa de follow-up hoje.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from .. import audit
from ..db import db
from ..deps import get_current_user, require_admin
from ..models import LeadInput, LeadStagePatch
from ..repo import PROJECTION, get_or_404, paginate, regex_filter
from ..security import now_iso

router = APIRouter(prefix="/leads", tags=["funil"])

STAGES = ["novo", "contatado", "negociacao", "proposta", "ganho", "perdido"]
STAGE_LABEL = {
    "novo": "Novo",
    "contatado": "Contatado",
    "negociacao": "Em negociação",
    "proposta": "Proposta enviada",
    "ganho": "Ganho",
    "perdido": "Perdido",
}


@router.get("")
async def list_leads(
    search: str = "",
    stage: str = "todos",
    source: str = "todos",
    page: int = 1,
    page_size: int = 200,
    user: dict = Depends(get_current_user),
):
    query: dict = {}
    if stage != "todos":
        query["stage"] = stage
    if source != "todos":
        query["source"] = source
    if search.strip():
        query.update(regex_filter(search, ["name", "contact_name", "city", "phone", "email"]))
    return await paginate("leads", query, page=page, page_size=page_size,
                          sort_field="updated_at", sort_dir="desc")


@router.get("/funnel")
async def funnel(user: dict = Depends(get_current_user)):
    """Resumo por etapa: quantidade, valor estimado e taxa de conversão."""
    pipeline = [
        {"$group": {"_id": "$stage", "qtd": {"$sum": 1}, "valor": {"$sum": "$estimated_value"}}}
    ]
    buckets = {r["_id"]: r async for r in db.leads.aggregate(pipeline)}
    stages = [
        {
            "stage": s,
            "label": STAGE_LABEL[s],
            "qtd": buckets.get(s, {}).get("qtd", 0),
            "valor": round(buckets.get(s, {}).get("valor", 0.0), 2),
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
        "stage_history": [{"stage": doc["stage"], "at": now_iso(), "by": user["name"]}],
        "converted_restaurant_id": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["name"],
    })
    await db.leads.insert_one(dict(doc))
    await audit.record(user, "criou", "lead", doc["id"], label=doc["name"], after=doc)
    return await get_or_404("leads", doc["id"], "Lead")


@router.put("/{lid}")
async def update_lead(lid: str, data: LeadInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("leads", lid, "Lead")
    patch = data.model_dump()
    patch["stage"] = before["stage"]  # etapa muda só pelo endpoint dedicado
    patch["updated_at"] = now_iso()
    await db.leads.update_one({"id": lid}, {"$set": patch})
    after = await db.leads.find_one({"id": lid}, PROJECTION)
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
    patch = {"stage": body.stage, "updated_at": now_iso(),
             "lost_reason": body.lost_reason if body.stage == "perdido" else ""}
    await db.leads.update_one(
        {"id": lid},
        {"$set": patch,
         "$push": {"stage_history": {"stage": body.stage, "at": now_iso(), "by": user["name"]}}},
    )
    after = await db.leads.find_one({"id": lid}, PROJECTION)
    await audit.record(user, "moveu no funil", "lead", lid, label=after["name"],
                       before=before, after=after)
    return after


@router.post("/{lid}/convert")
async def convert_lead(lid: str, user: dict = Depends(get_current_user)):
    """Vira cliente: cria o restaurante já preenchido e fecha o lead como ganho."""
    lead = await get_or_404("leads", lid, "Lead")
    if lead.get("converted_restaurant_id"):
        raise HTTPException(status_code=409, detail="Este lead já foi convertido")

    restaurant = {
        "id": str(uuid.uuid4()),
        "name": lead["name"],
        "category": lead.get("category") or "Outros",
        "contact_person": lead.get("contact_name", ""),
        "email": lead.get("email", ""),
        "phone": lead.get("phone", ""),
        "cnpj": "",
        "address": lead.get("city", ""),
        "commission_rate": 15.0,
        "status": "em_analise",
        "notes": f"Convertido do funil. Origem: {lead.get('source', '-')}.",
        "orders_total": 0,
        "revenue_total": 0.0,
        "commission_due": 0.0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["name"],
    }
    await db.restaurants.insert_one(dict(restaurant))
    await db.leads.update_one(
        {"id": lid},
        {"$set": {"stage": "ganho", "converted_restaurant_id": restaurant["id"],
                  "updated_at": now_iso()},
         "$push": {"stage_history": {"stage": "ganho", "at": now_iso(), "by": user["name"]}}},
    )
    await db.activities.update_many(
        {"related_type": "lead", "related_id": lid},
        {"$set": {"related_type": "restaurante", "related_id": restaurant["id"]}},
    )
    await audit.record(user, "converteu lead", "lead", lid, label=lead["name"], after=restaurant)
    return {"lead": await get_or_404("leads", lid, "Lead"),
            "restaurant": await get_or_404("restaurants", restaurant["id"], "Restaurante")}


@router.delete("/{lid}")
async def delete_lead(lid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("leads", lid, "Lead")
    await db.leads.delete_one({"id": lid})
    await db.activities.delete_many({"related_type": "lead", "related_id": lid})
    await audit.record(admin, "removeu", "lead", lid, label=doc["name"], before=doc)
    return {"message": "Removido"}
