"""Atividades: tarefas com prazo e interações registradas.

É o que transforma cadastro em relacionamento — quem ligou, quando, o que ficou
combinado e o que vence hoje.
"""
import uuid

from fastapi import APIRouter, Depends

from .. import audit, tempo
from ..db import db
from ..deps import get_current_user, require_admin
from ..models import ActivityInput
from ..repo import PROJECTION, get_or_404, paginate
from ..security import now_iso, now_utc

router = APIRouter(prefix="/activities", tags=["atividades"])


@router.get("")
async def list_activities(
    scope: str = "todas",  # hoje | atrasadas | proximas | concluidas | todas
    related_type: str = "",
    related_id: str = "",
    kind: str = "todas",
    page: int = 1,
    page_size: int = 100,
    user: dict = Depends(get_current_user),
):
    query: dict = {}
    if related_type:
        query["related_type"] = related_type
    if related_id:
        query["related_id"] = related_id
    if kind != "todas":
        query["kind"] = kind

    # Fronteiras no fuso do negócio: em UTC, uma tarefa marcada para as 22h em
    # São Paulo já caía no dia seguinte.
    agora = now_utc()
    inicio_hoje = tempo.inicio_do_dia().isoformat()
    fim_hoje = tempo.fim_do_dia().isoformat()
    if scope == "hoje":
        # "Hoje" é o que vence hoje. O que já venceu tem aba própria; sem o
        # limite inferior, as duas abas mostravam exatamente a mesma lista.
        query.update({"done": False, "due_at": {"$gte": inicio_hoje, "$lte": fim_hoje}})
    elif scope == "atrasadas":
        query.update({"done": False, "due_at": {"$ne": None, "$lt": agora.isoformat()}})
    elif scope == "proximas":
        query.update({"done": False, "due_at": {"$gt": fim_hoje}})
    elif scope == "concluidas":
        query["done"] = True
    elif scope == "abertas":
        query["done"] = False

    sort_dir = "desc" if scope == "concluidas" else "asc"
    sort_field = "completed_at" if scope == "concluidas" else "due_at"
    return await paginate("activities", query, page=page, page_size=page_size,
                          sort_field=sort_field, sort_dir=sort_dir)


@router.get("/summary")
async def summary(user: dict = Depends(get_current_user)):
    agora = now_utc()
    inicio_hoje = tempo.inicio_do_dia().isoformat()
    fim_hoje = tempo.fim_do_dia().isoformat()
    semana = tempo.fim_do_dia(7).isoformat()
    # Os mesmos limites usados em `list_activities`: o contador da aba e a lista
    # que ela abre precisam bater.
    return {
        "atrasadas": await db.activities.count_documents(
            {"done": False, "due_at": {"$ne": None, "$lt": agora.isoformat()}}
        ),
        "hoje": await db.activities.count_documents(
            {"done": False, "due_at": {"$gte": inicio_hoje, "$lte": fim_hoje}}
        ),
        "semana": await db.activities.count_documents(
            {"done": False, "due_at": {"$gt": fim_hoje, "$lte": semana}}
        ),
        "abertas": await db.activities.count_documents({"done": False}),
    }


@router.post("", status_code=201)
async def create_activity(data: ActivityInput, user: dict = Depends(get_current_user)):
    doc = data.model_dump()
    # Interação é um registro do que já aconteceu; nasce concluída.
    if doc["kind"] == "interacao":
        doc["done"] = True
    doc.update({
        "id": str(uuid.uuid4()),
        "owner_name": doc.get("owner_name") or user["name"],
        "completed_at": now_iso() if doc["done"] else None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["name"],
    })
    await db.activities.insert_one(dict(doc))
    await audit.record(user, "criou", "atividade", doc["id"], label=doc["title"], after=doc)
    return await get_or_404("activities", doc["id"], "Atividade")


@router.put("/{aid}")
async def update_activity(aid: str, data: ActivityInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("activities", aid, "Atividade")
    patch = data.model_dump()
    patch["updated_at"] = now_iso()
    patch["completed_at"] = before.get("completed_at") if patch["done"] else None
    if patch["done"] and not patch["completed_at"]:
        patch["completed_at"] = now_iso()
    await db.activities.update_one({"id": aid}, {"$set": patch})
    after = await db.activities.find_one({"id": aid}, PROJECTION)
    await audit.record(user, "atualizou", "atividade", aid, label=after["title"],
                       before=before, after=after)
    return after


@router.patch("/{aid}/toggle")
async def toggle_done(aid: str, user: dict = Depends(get_current_user)):
    before = await get_or_404("activities", aid, "Atividade")
    done = not before.get("done", False)
    await db.activities.update_one(
        {"id": aid},
        {"$set": {"done": done, "completed_at": now_iso() if done else None,
                  "updated_at": now_iso()}},
    )
    return await db.activities.find_one({"id": aid}, PROJECTION)


@router.delete("/{aid}")
async def delete_activity(aid: str, user: dict = Depends(get_current_user)):
    doc = await get_or_404("activities", aid, "Atividade")
    # Interação já registrada é histórico: só o admin apaga.
    if doc.get("kind") == "interacao" and user.get("role") != "admin":
        await require_admin(user)
    await db.activities.delete_one({"id": aid})
    await audit.record(user, "removeu", "atividade", aid, label=doc["title"], before=doc)
    return {"message": "Removido"}
