import uuid

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, repo
from ..deps import get_current_user, require_admin
from ..permissoes import acesso
from ..models import ContractInput
from ..repo import get_or_404
from ..security import now_utc

router = APIRouter(
    prefix="/contracts", tags=["contratos"],
    dependencies=[Depends(acesso("financeiro"))],
)

COLLECTION = {"restaurante": "restaurants", "entregador": "drivers"}


async def _link_party(data: dict) -> dict:
    """Amarra o contrato ao cadastro por id, não só pelo nome digitado."""
    tabela = COLLECTION[data["party_type"]]
    if data.get("party_id"):
        party = await repo.pegar(tabela, data["party_id"])
        if not party:
            raise HTTPException(status_code=404, detail="Parte do contrato não encontrada")
    else:
        party = await repo.um_por(tabela, "name", data["party_name"])
    if party:
        data["party_id"] = party["id"]
        data["party_name"] = party["name"]
    return data


@router.get("")
async def list_contracts(
    party_type: str = "todos",
    status: str = "todos",
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user),
):
    f = repo.filtro("contracts")
    if party_type != "todos":
        f.igual("party_type", party_type)
    if status != "todos":
        f.igual("status", status)
    return await repo.paginar("contracts", f, page=page, page_size=page_size)


@router.get("/{cid}")
async def get_contract(cid: str, user: dict = Depends(get_current_user)):
    return await get_or_404("contracts", cid, "Contrato")


@router.post("", status_code=201)
async def create_contract(data: ContractInput, user: dict = Depends(get_current_user)):
    doc = await _link_party(data.model_dump())
    if doc["status"] == "ativo":
        clash = await repo.contar(
            "contracts",
            repo.filtro("contracts")
            .igual("party_type", doc["party_type"])
            .igual("party_name", doc["party_name"])
            .igual("status", "ativo"),
        )
        if clash:
            raise HTTPException(
                status_code=409,
                detail="Já existe contrato ativo para esta parte. Encerre o atual antes de criar outro.",
            )
    doc.update({"id": str(uuid.uuid4()), "created_by": user["name"]})
    criado = await repo.inserir("contracts", doc)
    await audit.record(
        user, "criou", "contrato", criado["id"], label=criado["party_name"], after=criado
    )
    return criado


@router.put("/{cid}")
async def update_contract(cid: str, data: ContractInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("contracts", cid, "Contrato")
    patch = await _link_party(data.model_dump())
    patch["updated_at"] = now_utc()
    after = await repo.atualizar("contracts", cid, patch)
    await audit.record(
        user, "atualizou", "contrato", cid, label=after["party_name"], before=before, after=after
    )
    return after


@router.delete("/{cid}")
async def delete_contract(cid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("contracts", cid, "Contrato")
    await repo.remover("contracts", cid)
    await audit.record(admin, "removeu", "contrato", cid, label=doc["party_name"], before=doc)
    return {"message": "Removido"}
