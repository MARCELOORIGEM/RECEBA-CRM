import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import audit, repo
from ..deps import get_current_user, require_admin
from ..models import DriverInput, DriverStatusPatch
from ..repo import get_or_404
from ..security import now_utc

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
    f = repo.filtro("drivers")
    if status != "todos":
        f.igual("status", status)
    f.busca(search, ["name", "plate", "phone"])
    return await repo.paginar(
        "drivers", f, page=page, page_size=page_size,
        ordenar_por=repo.campo_de_ordenacao("drivers", sort_field), direcao=sort_dir,
    )


@router.get("/{did}")
async def get_driver(did: str, user: dict = Depends(get_current_user)):
    return await get_or_404("drivers", did, "Entregador")


@router.post("", status_code=201)
async def create_driver(data: DriverInput, user: dict = Depends(get_current_user)):
    doc = data.model_dump()
    if doc.get("plate") and await repo.existe("drivers", "plate", doc["plate"]):
        raise HTTPException(status_code=409, detail="Já existe um entregador com esta placa")
    doc.update({"id": str(uuid.uuid4()), "created_by": user["name"]})
    # Contadores, saldos e datas vêm dos DEFAULT do schema.
    criado = await repo.inserir("drivers", doc)
    await audit.record(user, "criou", "entregador", criado["id"], label=criado["name"], after=criado)
    return criado


@router.put("/{did}")
async def update_driver(did: str, data: DriverInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("drivers", did, "Entregador")
    patch = data.model_dump()
    patch["updated_at"] = now_utc()
    after = await repo.atualizar("drivers", did, patch)
    if before["name"] != after["name"]:
        await repo.atualizar_onde(
            "orders", repo.filtro("orders").igual("driver_id", did),
            {"driver_name": after["name"]},
        )
        await repo.atualizar_onde(
            "contracts",
            repo.filtro("contracts").igual("party_id", did).igual("party_type", "entregador"),
            {"party_name": after["name"]},
        )
        await repo.atualizar_onde(
            "payments",
            repo.filtro("payments").igual("creditor_id", did).igual("creditor_type", "entregador"),
            {"creditor": after["name"]},
        )
    await audit.record(
        user, "atualizou", "entregador", did, label=after["name"], before=before, after=after
    )
    return after


@router.patch("/{did}/status")
async def patch_status(did: str, body: DriverStatusPatch, user: dict = Depends(get_current_user)):
    before = await get_or_404("drivers", did, "Entregador")
    after = await repo.atualizar("drivers", did, {"status": body.status, "updated_at": now_utc()})
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
    await repo.remover("drivers", did)
    await audit.record(admin, "removeu", "entregador", did, label=doc["name"], before=doc)
    return {"message": "Removido"}
