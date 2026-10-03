import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from .. import audit
from ..db import db
from ..deps import get_current_user, require_admin
from ..models import PaymentInput
from ..repo import PROJECTION, get_or_404, paginate, regex_filter
from ..security import now_iso

router = APIRouter(prefix="/payments", tags=["pagamentos"])

COLLECTION = {"restaurante": "restaurants", "entregador": "drivers"}


def _serialize(doc: dict) -> dict:
    if isinstance(doc.get("due_date"), date):
        doc["due_date"] = doc["due_date"].isoformat()
    return doc


async def _link_creditor(data: dict) -> dict:
    coll = COLLECTION[data["creditor_type"]]
    party = None
    if data.get("creditor_id"):
        party = await db[coll].find_one({"id": data["creditor_id"]}, PROJECTION)
        if not party:
            raise HTTPException(status_code=404, detail="Credor não encontrado")
    else:
        party = await db[coll].find_one({"name": data["creditor"]}, PROJECTION)
    if party:
        data["creditor_id"] = party["id"]
        data["creditor"] = party["name"]
    return data


@router.get("")
async def list_payments(
    search: str = "",
    status: str = "todos",
    creditor_type: str = "todos",
    creditor_id: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user),
):
    query: dict = {}
    if status != "todos":
        query["status"] = status
    if creditor_type != "todos":
        query["creditor_type"] = creditor_type
    if creditor_id:
        query["creditor_id"] = creditor_id
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        query["due_date"] = rng
    if search.strip():
        query.update(regex_filter(search, ["creditor", "notes"]))

    result = await paginate("payments", query, page=page, page_size=page_size,
                            sort_field="due_date", sort_dir="asc")

    # Totais do filtro inteiro, não só da página — o resumo financeiro precisa do
    # conjunto todo. Antes o frontend somava apenas o que estava carregado.
    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$status", "total": {"$sum": "$amount"}, "qtd": {"$sum": 1}}},
    ]
    buckets = {r["_id"]: r async for r in db.payments.aggregate(pipeline)}
    result["totals"] = {
        k: round(buckets.get(k, {}).get("total", 0.0), 2)
        for k in ("pendente", "pago", "atrasado", "cancelado")
    }
    result["totals"]["geral"] = round(sum(result["totals"].values()), 2)
    return result


@router.get("/{pid}")
async def get_payment(pid: str, user: dict = Depends(get_current_user)):
    return await get_or_404("payments", pid, "Pagamento")


@router.post("", status_code=201)
async def create_payment(data: PaymentInput, user: dict = Depends(get_current_user)):
    doc = _serialize(await _link_creditor(data.model_dump()))
    doc.update({"id": str(uuid.uuid4()), "paid_at": None, "created_at": now_iso(),
                "updated_at": now_iso(), "created_by": user["name"]})
    await db.payments.insert_one(dict(doc))
    await audit.record(user, "criou", "pagamento", doc["id"], label=doc["creditor"], after=doc)
    return await get_or_404("payments", doc["id"], "Pagamento")


@router.put("/{pid}")
async def update_payment(pid: str, data: PaymentInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("payments", pid, "Pagamento")
    if before["status"] == "pago":
        raise HTTPException(
            status_code=409, detail="Pagamento liquidado não pode ser editado. Estorne antes."
        )
    patch = _serialize(await _link_creditor(data.model_dump()))
    patch["updated_at"] = now_iso()
    await db.payments.update_one({"id": pid}, {"$set": patch})
    after = await db.payments.find_one({"id": pid}, PROJECTION)
    await audit.record(
        user, "atualizou", "pagamento", pid, label=after["creditor"], before=before, after=after
    )
    return after


@router.post("/{pid}/settle")
async def settle_payment(pid: str, user: dict = Depends(get_current_user)):
    """Liquida e baixa o saldo do credor.

    Antes o saldo a receber do entregador ficava congelado mesmo depois do repasse
    ser marcado como pago.
    """
    before = await get_or_404("payments", pid, "Pagamento")
    if before["status"] == "pago":
        raise HTTPException(status_code=409, detail="Pagamento já está liquidado")

    await db.payments.update_one(
        {"id": pid}, {"$set": {"status": "pago", "paid_at": now_iso(), "updated_at": now_iso()}}
    )
    amount = float(before.get("amount") or 0)
    if before.get("creditor_id"):
        if before["creditor_type"] == "entregador":
            await db.drivers.update_one(
                {"id": before["creditor_id"]},
                {"$inc": {"balance_due": -amount, "paid_total": amount}},
            )
        else:
            await db.restaurants.update_one(
                {"id": before["creditor_id"]}, {"$inc": {"commission_due": -amount}}
            )

    after = await db.payments.find_one({"id": pid}, PROJECTION)
    await audit.record(
        user, "liquidou", "pagamento", pid, label=after["creditor"], before=before, after=after
    )
    return after


@router.post("/{pid}/reopen")
async def reopen_payment(pid: str, admin: dict = Depends(require_admin)):
    """Estorna uma liquidação feita por engano, devolvendo o saldo ao credor."""
    before = await get_or_404("payments", pid, "Pagamento")
    if before["status"] != "pago":
        raise HTTPException(status_code=409, detail="Só é possível estornar pagamento liquidado")

    amount = float(before.get("amount") or 0)
    if before.get("creditor_id"):
        if before["creditor_type"] == "entregador":
            await db.drivers.update_one(
                {"id": before["creditor_id"]},
                {"$inc": {"balance_due": amount, "paid_total": -amount}},
            )
        else:
            await db.restaurants.update_one(
                {"id": before["creditor_id"]}, {"$inc": {"commission_due": amount}}
            )
    await db.payments.update_one(
        {"id": pid}, {"$set": {"status": "pendente", "paid_at": None, "updated_at": now_iso()}}
    )
    after = await db.payments.find_one({"id": pid}, PROJECTION)
    await audit.record(
        admin, "estornou", "pagamento", pid, label=after["creditor"], before=before, after=after
    )
    return after


@router.delete("/{pid}")
async def delete_payment(pid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("payments", pid, "Pagamento")
    if doc["status"] == "pago":
        raise HTTPException(
            status_code=409,
            detail="Pagamento liquidado faz parte do histórico financeiro. Estorne antes de excluir.",
        )
    await db.payments.delete_one({"id": pid})
    await audit.record(admin, "removeu", "pagamento", pid, label=doc["creditor"], before=doc)
    return {"message": "Removido"}
