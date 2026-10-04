import uuid

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, financials, pg, repo, tempo
from ..deps import get_current_user, require_admin
from ..permissoes import acesso
from ..models import OrderAssign, OrderInput, OrderStatusPatch
from ..repo import get_or_404
from ..security import now_utc

router = APIRouter(prefix="/orders", tags=["pedidos"], dependencies=[Depends(acesso("pedidos"))])

# Fluxo do pedido. Pular etapas escondia erros de operação — agora a API recusa.
FLOW = {
    "criado": {"aguardando_coleta", "cancelado"},
    "aguardando_coleta": {"em_transito", "cancelado", "criado"},
    "em_transito": {"entregue", "cancelado", "aguardando_coleta"},
    "entregue": {"em_transito"},  # só para corrigir um lançamento errado
    "cancelado": {"criado"},
}


async def _resolve_party(tabela: str, pid: str, name: str, label: str) -> tuple[str, str]:
    """Aceita id ou nome e devolve o par (id, nome) coerente."""
    if pid:
        doc = await repo.pegar(tabela, pid)
        if not doc:
            raise HTTPException(status_code=404, detail=f"{label} não encontrado")
        return doc["id"], doc["name"]
    if name:
        doc = await repo.um_por(tabela, "name", name)
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
    f = repo.filtro("orders")
    if status != "todos":
        f.igual("status", status)
    f.igual("restaurant_id", restaurant_id)
    f.igual("driver_id", driver_id)
    # As datas do filtro são dias do calendário local. O corte em UTC jogava
    # para o dia seguinte o pedido das 21h às 23h59 — o pico do delivery.
    inicio, fim = tempo.data_do_filtro(date_from), tempo.data_do_filtro(date_to)
    if inicio:
        f.desde("created_at", tempo.inicio_da_data(inicio))
    if fim:
        f.ate("created_at", tempo.fim_da_data(fim))
    f.busca(search, ["code", "customer_name", "restaurant_name", "driver_name"])
    return await repo.paginar("orders", f, page=page, page_size=page_size)


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
    seq = await pg.proximo_numero("order_code")
    doc.update({
        "id": str(uuid.uuid4()),
        "code": f"PED-{1000 + seq}",
        "created_by": user["name"],
    })
    pedido = await repo.inserir("orders", doc)
    if pedido["status"] == "entregue":
        await financials.apply_delivery(pedido)
        pedido = await repo.pegar("orders", pedido["id"])
    await audit.record(user, "criou", "pedido", pedido["id"], label=pedido["code"], after=pedido)
    return pedido


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
    patch["updated_at"] = now_utc()
    after = await repo.atualizar("orders", oid, patch)
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

    fresh = await repo.atualizar("orders", oid, {"status": novo, "updated_at": now_utc()})
    if novo == "entregue":
        await financials.apply_delivery(fresh)
    elif atual == "entregue":
        await financials.revert_delivery(before)

    after = await repo.pegar("orders", oid)
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
    after = await repo.atualizar(
        "orders", oid, {"driver_id": did, "driver_name": dname, "updated_at": now_utc()}
    )
    await audit.record(
        user, "atribuiu entregador", "pedido", oid, label=after["code"], before=before, after=after
    )
    return after


@router.delete("/{oid}")
async def delete_order(oid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("orders", oid, "Pedido")
    await financials.revert_delivery(doc)
    await repo.remover("orders", oid)
    await audit.record(admin, "removeu", "pedido", oid, label=doc["code"], before=doc)
    return {"message": "Removido"}
