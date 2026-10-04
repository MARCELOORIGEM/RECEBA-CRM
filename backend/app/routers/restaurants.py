import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import audit, pg, repo, tempo
from ..deps import get_current_user, require_admin
from ..models import RestaurantInput
from ..repo import get_or_404
from ..security import now_utc

router = APIRouter(prefix="/restaurants", tags=["restaurantes"])


async def _orders_this_month(ids: list[str]) -> dict[str, int]:
    """Pedidos do mês corrente, por restaurante.

    O campo `orders_month` costumava ser gravado no documento e incrementado para
    sempre — nunca virava o mês, então mostrava o acumulado histórico rotulado
    como "Pedidos/Mês". Agora vem da fonte real, os pedidos.
    """
    if not ids:
        return {}
    linhas = await pg.varios(
        """
        SELECT restaurant_id, count(*) AS qtd FROM orders
         WHERE restaurant_id = ANY($1) AND status = 'entregue' AND created_at >= $2
         GROUP BY restaurant_id
        """,
        ids,
        tempo.inicio_do_mes(),
    )
    return {r["restaurant_id"]: r["qtd"] for r in linhas}


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
    f = repo.filtro("restaurants")
    if status != "todos":
        f.igual("status", status)
    f.busca(search, ["name", "cnpj", "contact_person", "phone", "category"])
    result = await repo.paginar(
        "restaurants", f, page=page, page_size=page_size,
        ordenar_por=repo.campo_de_ordenacao("restaurants", sort_field), direcao=sort_dir,
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
    if doc.get("cnpj") and await repo.existe("restaurants", "cnpj", doc["cnpj"]):
        raise HTTPException(status_code=409, detail="Já existe um restaurante com este CNPJ")
    doc.update({"id": str(uuid.uuid4()), "created_by": user["name"]})
    # Contadores, saldos e datas vêm dos DEFAULT do schema.
    criado = await repo.inserir("restaurants", doc)
    await audit.record(user, "criou", "restaurante", criado["id"], label=criado["name"], after=criado)
    return (await _enrich([criado]))[0]


@router.put("/{rid}")
async def update_restaurant(rid: str, data: RestaurantInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("restaurants", rid, "Restaurante")
    patch = data.model_dump()
    patch["updated_at"] = now_utc()
    after = await repo.atualizar("restaurants", rid, patch)

    # O nome aparece em pedidos, contratos e pagamentos antigos. Sem propagar,
    # o histórico passa a apontar para um nome que não existe mais.
    if before["name"] != after["name"]:
        await repo.atualizar_onde(
            "orders", repo.filtro("orders").igual("restaurant_id", rid),
            {"restaurant_name": after["name"]},
        )
        await repo.atualizar_onde(
            "contracts",
            repo.filtro("contracts").igual("party_id", rid).igual("party_type", "restaurante"),
            {"party_name": after["name"]},
        )
        await repo.atualizar_onde(
            "payments",
            repo.filtro("payments").igual("creditor_id", rid).igual("creditor_type", "restaurante"),
            {"creditor": after["name"]},
        )

    await audit.record(
        user, "atualizou", "restaurante", rid, label=after["name"], before=before, after=after
    )
    return (await _enrich([after]))[0]


@router.delete("/{rid}")
async def delete_restaurant(
    rid: str, force: bool = Query(False), admin: dict = Depends(require_admin)
):
    doc = await get_or_404("restaurants", rid, "Restaurante")
    linked = await repo.contar("orders", repo.filtro("orders").igual("restaurant_id", rid))
    if linked and not force:
        nome = doc["name"]
        raise HTTPException(
            status_code=409,
            detail=(
                f"{nome} tem {linked} pedido(s) no histórico. "
                "Mude o status para 'inativo' ou confirme a exclusão definitiva."
            ),
        )
    await repo.remover("restaurants", rid)
    await audit.record(admin, "removeu", "restaurante", rid, label=doc["name"], before=doc)
    return {"message": "Removido"}
