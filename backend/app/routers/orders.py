import uuid

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, financials
from ..db import db, next_sequence
from ..deps import get_current_user, require_admin
from ..models import OrderAssign, OrderInput, OrderStatusPatch
from ..repo import PROJECTION, get_or_404, paginate, regex_filter
from ..security import now_iso

router = APIRouter(prefix="/orders", tags=["pedidos"])

# Fluxo do pedido. Pular etapas escondia erros de operação — agora a API recusa.
FLOW = {
    "criado": {"aguardando_coleta", "cancelado"},
    "aguardando_coleta": {"em_transito", "cancelado", "criado"},
    "em_transito": {"entregue", "cancelado", "aguardando_coleta"},
    "entregue": {"em_transito"},  # só para corrigir um lançamento errado
    "cancelado": {"criado"},
}


async def _resolve_party(collection: str, pid: str, name: str, label: str) -> tuple[str, str]:
    """Aceita id ou nome e devolve o par (id, nome) coerente."""
    if pid:
        doc = await db[collection].find_one({"id": pid}, PROJECTION)
        if not doc:
            raise HTTPException(status_code=404, detail=f"{label} não encontrado")
        return doc["id"], doc["name"]
    if name:
        doc = await db[collection].find_one({"name": name}, PROJECTION)
        if doc:
            return doc["id"], doc["name"]
        return "", name
    return "", ""


@router.get("")
async def list_orders(
    search: str = "",
    status: str = "todos",
    restaurant_id: str = "",
    driver_id: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user),
):
    query: dict = {}
    if status and status != "todos":
        query["status"] = status
    if restaurant_id:
        query["restaurant_id"] = restaurant_id
    if driver_id:
        query["driver_id"] = driver_id
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59.999999+00:00"
        query["created_at"] = rng
    if search.strip():
        query.update(
            regex_filter(search, ["code", "customer_name", "restaurant_name", "driver_name"])
        )
    return await paginate("orders", query, page=page, page_size=page_size)


@router.get("/{oid}")
async def get_order(oid: str, user: dict = Depends(get_current_user)):
    return await get_or_404("orders", oid, "Pedido")


@router.post("", status_code=201)
async def create_order(data: OrderInput, user: dict = Depends(get_current_user)):
    doc = data.model_dump()
    doc["restaurant_id"], doc["restaurant_name"] = await _resolve_party(
        "restaurants", doc["restaurant_id"], doc["restaurant_name"], "Restaurante"
    )
    doc["driver_id"], doc["driver_name"] = await _resolve_party(
        "drivers", doc["driver_id"], doc["driver_name"], "Entregador"
    )
    seq = await next_sequence("order_code")
    doc.update({
        "id": str(uuid.uuid4()),
        "code": f"PED-{1000 + seq}",
        "financials_applied": False,
        "driver_earning": 0.0,
        "platform_commission": 0.0,
        "delivered_at": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["name"],
    })
    await db.orders.insert_one(dict(doc))
    if doc["status"] == "entregue":
        await financials.apply_delivery(doc)
    await audit.record(user, "criou", "pedido", doc["id"], label=doc["code"], after=doc)
    return await get_or_404("orders", doc["id"], "Pedido")


@router.put("/{oid}")
async def update_order(oid: str, data: OrderInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("orders", oid, "Pedido")
    patch = data.model_dump()
    patch["restaurant_id"], patch["restaurant_name"] = await _resolve_party(
        "restaurants", patch["restaurant_id"], patch["restaurant_name"], "Restaurante"
    )
    patch["driver_id"], patch["driver_name"] = await _resolve_party(
        "drivers", patch["driver_id"], patch["driver_name"], "Entregador"
    )
    patch["status"] = before["status"]  # status muda só pelo endpoint dedicado
    patch["updated_at"] = now_iso()
    await db.orders.update_one({"id": oid}, {"$set": patch})
    after = await db.orders.find_one({"id": oid}, PROJECTION)
    await audit.record(
        user, "atualizou", "pedido", oid, label=after["code"], before=before, after=after
    )
    return after


@router.patch("/{oid}/status")
async def update_status(oid: str, body: OrderStatusPatch, user: dict = Depends(get_current_user)):
    before = await get_or_404("orders", oid, "Pedido")
    atual, novo = before["status"], body.status
    if novo == atual:
        return before
    if novo not in FLOW.get(atual, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Transição inválida: de '{atual}' para '{novo}'.",
        )
    if novo == "entregue" and not (before.get("driver_id") or before.get("driver_name")):
        raise HTTPException(
            status_code=409, detail="Atribua um entregador antes de marcar como entregue."
        )

    await db.orders.update_one(
        {"id": oid}, {"$set": {"status": novo, "updated_at": now_iso()}}
    )
    fresh = await db.orders.find_one({"id": oid}, PROJECTION)
    if novo == "entregue":
        await financials.apply_delivery(fresh)
    elif atual == "entregue":
        await financials.revert_delivery(before)

    after = await db.orders.find_one({"id": oid}, PROJECTION)
    await audit.record(
        user, "mudou status", "pedido", oid, label=after["code"], before=before, after=after
    )
    return after


@router.patch("/{oid}/assign")
async def assign_driver(oid: str, body: OrderAssign, user: dict = Depends(get_current_user)):
    before = await get_or_404("orders", oid, "Pedido")
    if before["status"] in ("entregue", "cancelado"):
        raise HTTPException(
            status_code=409, detail="Pedido finalizado não aceita troca de entregador."
        )
    did, dname = await _resolve_party("drivers", body.driver_id, body.driver_name, "Entregador")
    await db.orders.update_one(
        {"id": oid},
        {"$set": {"driver_id": did, "driver_name": dname, "updated_at": now_iso()}},
    )
    after = await db.orders.find_one({"id": oid}, PROJECTION)
    await audit.record(
        user, "atribuiu entregador", "pedido", oid, label=after["code"], before=before, after=after
    )
    return after


@router.delete("/{oid}")
async def delete_order(oid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("orders", oid, "Pedido")
    await financials.revert_delivery(doc)
    await db.orders.delete_one({"id": oid})
    await audit.record(admin, "removeu", "pedido", oid, label=doc["code"], before=doc)
    return {"message": "Removido"}
