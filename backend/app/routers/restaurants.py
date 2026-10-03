import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import audit
from ..db import db
from ..deps import get_current_user, require_admin
from ..models import RestaurantInput
from .. import tempo
from ..repo import PROJECTION, get_or_404, paginate, regex_filter
from ..security import now_iso

router = APIRouter(prefix="/restaurants", tags=["restaurantes"])


async def _orders_this_month(ids: list[str]) -> dict[str, int]:
    """Pedidos do mês corrente, por restaurante.

    O campo `orders_month` costumava ser gravado no documento e incrementado para
    sempre — nunca virava o mês, então mostrava o acumulado histórico rotulado
    como "Pedidos/Mês". Agora vem da fonte real, os pedidos.
    """
    if not ids:
        return {}
    inicio = tempo.inicio_do_mes().isoformat()
    pipeline = [
        {"$match": {"restaurant_id": {"$in": ids}, "status": "entregue",
                    "created_at": {"$gte": inicio}}},
        {"$group": {"_id": "$restaurant_id", "qtd": {"$sum": 1}}},
    ]
    return {r["_id"]: r["qtd"] async for r in db.orders.aggregate(pipeline)}


async def _enrich(docs: list[dict]) -> list[dict]:
    counts = await _orders_this_month([d["id"] for d in docs])
    for d in docs:
        d["orders_month"] = counts.get(d["id"], 0)
    return docs


@router.get("")
async def list_restaurants(
    search: str = "",
    status: str = "todos",
    page: int = 1,
    page_size: int = 25,
    sort_field: str = "created_at",
    sort_dir: str = "desc",
    user: dict = Depends(get_current_user),
):
    query: dict = {}
    if status and status != "todos":
        query["status"] = status
    if search.strip():
        query.update(regex_filter(search, ["name", "cnpj", "contact_person", "phone", "category"]))
    result = await paginate(
        "restaurants", query, page=page, page_size=page_size,
        sort_field=sort_field, sort_dir=sort_dir,
    )
    result["items"] = await _enrich(result["items"])
    return result


@router.get("/{rid}")
async def get_restaurant(rid: str, user: dict = Depends(get_current_user)):
    doc = await get_or_404("restaurants", rid, "Restaurante")
    return (await _enrich([doc]))[0]


@router.post("", status_code=201)
async def create_restaurant(data: RestaurantInput, user: dict = Depends(get_current_user)):
    doc = data.model_dump()
    if doc.get("cnpj") and await db.restaurants.find_one({"cnpj": doc["cnpj"]}):
        raise HTTPException(status_code=409, detail="Já existe um restaurante com este CNPJ")
    doc.update({
        "id": str(uuid.uuid4()),
        "orders_total": 0,
        "revenue_total": 0.0,
        "commission_due": 0.0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["name"],
    })
    await db.restaurants.insert_one(dict(doc))
    await audit.record(user, "criou", "restaurante", doc["id"], label=doc["name"], after=doc)
    return await get_or_404("restaurants", doc["id"], "Restaurante")


@router.put("/{rid}")
async def update_restaurant(rid: str, data: RestaurantInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("restaurants", rid, "Restaurante")
    patch = data.model_dump()
    patch["updated_at"] = now_iso()
    await db.restaurants.update_one({"id": rid}, {"$set": patch})
    after = await db.restaurants.find_one({"id": rid}, PROJECTION)

    # O nome aparece em pedidos, contratos e pagamentos antigos. Sem propagar,
    # o histórico passa a apontar para um nome que não existe mais.
    if before["name"] != after["name"]:
        await db.orders.update_many(
            {"restaurant_id": rid}, {"$set": {"restaurant_name": after["name"]}}
        )
        await db.contracts.update_many(
            {"party_id": rid, "party_type": "restaurante"}, {"$set": {"party_name": after["name"]}}
        )
        await db.payments.update_many(
            {"creditor_id": rid, "creditor_type": "restaurante"},
            {"$set": {"creditor": after["name"]}},
        )

    await audit.record(
        user, "atualizou", "restaurante", rid, label=after["name"], before=before, after=after
    )
    return after


@router.delete("/{rid}")
async def delete_restaurant(
    rid: str, force: bool = Query(False), admin: dict = Depends(require_admin)
):
    doc = await get_or_404("restaurants", rid, "Restaurante")
    linked = await db.orders.count_documents({"restaurant_id": rid})
    if linked and not force:
        nome = doc["name"]
        raise HTTPException(
            status_code=409,
            detail=(
                f"{nome} tem {linked} pedido(s) no histórico. "
                "Mude o status para 'inativo' ou confirme a exclusão definitiva."
            ),
        )
    await db.restaurants.delete_one({"id": rid})
    await audit.record(admin, "removeu", "restaurante", rid, label=doc["name"], before=doc)
    return {"message": "Removido"}
