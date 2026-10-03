import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import audit
from ..db import db
from ..deps import get_current_user, require_admin
from ..models import DriverInput, DriverStatusPatch
from ..repo import PROJECTION, get_or_404, paginate, regex_filter
from ..security import now_iso

router = APIRouter(prefix="/drivers", tags=["entregadores"])


@router.get("")
async def list_drivers(
    search: str = "",
    status: str = "todos",
    page: int = 1,
    page_size: int = 50,
    sort_field: str = "created_at",
    sort_dir: str = "desc",
    user: dict = Depends(get_current_user),
):
    query: dict = {}
    if status and status != "todos":
        query["status"] = status
    if search.strip():
        query.update(regex_filter(search, ["name", "plate", "phone"]))
    return await paginate(
        "drivers", query, page=page, page_size=page_size,
        sort_field=sort_field, sort_dir=sort_dir,
    )


@router.get("/{did}")
async def get_driver(did: str, user: dict = Depends(get_current_user)):
    return await get_or_404("drivers", did, "Entregador")


@router.post("", status_code=201)
async def create_driver(data: DriverInput, user: dict = Depends(get_current_user)):
    doc = data.model_dump()
    if doc.get("plate") and await db.drivers.find_one({"plate": doc["plate"]}):
        raise HTTPException(status_code=409, detail="Já existe um entregador com esta placa")
    doc.update({
        "id": str(uuid.uuid4()),
        "total_deliveries": 0,
        "balance_due": 0.0,
        "paid_total": 0.0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["name"],
    })
    await db.drivers.insert_one(dict(doc))
    await audit.record(user, "criou", "entregador", doc["id"], label=doc["name"], after=doc)
    return await get_or_404("drivers", doc["id"], "Entregador")


@router.put("/{did}")
async def update_driver(did: str, data: DriverInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("drivers", did, "Entregador")
    patch = data.model_dump()
    patch["updated_at"] = now_iso()
    await db.drivers.update_one({"id": did}, {"$set": patch})
    after = await db.drivers.find_one({"id": did}, PROJECTION)
    if before["name"] != after["name"]:
        await db.orders.update_many({"driver_id": did}, {"$set": {"driver_name": after["name"]}})
        await db.contracts.update_many(
            {"party_id": did, "party_type": "entregador"}, {"$set": {"party_name": after["name"]}}
        )
        await db.payments.update_many(
            {"creditor_id": did, "creditor_type": "entregador"},
            {"$set": {"creditor": after["name"]}},
        )
    await audit.record(
        user, "atualizou", "entregador", did, label=after["name"], before=before, after=after
    )
    return after


@router.patch("/{did}/status")
async def patch_status(did: str, body: DriverStatusPatch, user: dict = Depends(get_current_user)):
    before = await get_or_404("drivers", did, "Entregador")
    await db.drivers.update_one(
        {"id": did}, {"$set": {"status": body.status, "updated_at": now_iso()}}
    )
    after = await db.drivers.find_one({"id": did}, PROJECTION)
    await audit.record(
        user, "mudou status", "entregador", did, label=after["name"], before=before, after=after
    )
    return after


@router.delete("/{did}")
async def delete_driver(
    did: str, force: bool = Query(False), admin: dict = Depends(require_admin)
):
    doc = await get_or_404("drivers", did, "Entregador")
    if doc.get("balance_due", 0) > 0 and not force:
        nome = doc["name"]
        raise HTTPException(
            status_code=409,
            detail=f"{nome} tem saldo a receber em aberto. Liquide o repasse antes de excluir.",
        )
    await db.drivers.delete_one({"id": did})
    await audit.record(admin, "removeu", "entregador", did, label=doc["name"], before=doc)
    return {"message": "Removido"}
