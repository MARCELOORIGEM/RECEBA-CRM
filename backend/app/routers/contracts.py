import uuid

from fastapi import APIRouter, Depends, HTTPException

from .. import audit
from ..db import db
from ..deps import get_current_user, require_admin
from ..models import ContractInput
from ..repo import PROJECTION, get_or_404, paginate
from ..security import now_iso

router = APIRouter(prefix="/contracts", tags=["contratos"])

COLLECTION = {"restaurante": "restaurants", "entregador": "drivers"}


async def _link_party(data: dict) -> dict:
    """Amarra o contrato ao cadastro por id, não só pelo nome digitado."""
    coll = COLLECTION[data["party_type"]]
    party = None
    if data.get("party_id"):
        party = await db[coll].find_one({"id": data["party_id"]}, PROJECTION)
        if not party:
            raise HTTPException(status_code=404, detail="Parte do contrato não encontrada")
    else:
        party = await db[coll].find_one({"name": data["party_name"]}, PROJECTION)
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
    query: dict = {}
    if party_type != "todos":
        query["party_type"] = party_type
    if status != "todos":
        query["status"] = status
    return await paginate("contracts", query, page=page, page_size=page_size)


@router.get("/{cid}")
async def get_contract(cid: str, user: dict = Depends(get_current_user)):
    return await get_or_404("contracts", cid, "Contrato")


@router.post("", status_code=201)
async def create_contract(data: ContractInput, user: dict = Depends(get_current_user)):
    doc = await _link_party(data.model_dump())
    if doc["status"] == "ativo":
        clash = await db.contracts.find_one(
            {"party_type": doc["party_type"], "party_name": doc["party_name"], "status": "ativo"}
        )
        if clash:
            raise HTTPException(
                status_code=409,
                detail="Já existe contrato ativo para esta parte. Encerre o atual antes de criar outro.",
            )
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(), "updated_at": now_iso(),
                "created_by": user["name"]})
    await db.contracts.insert_one(dict(doc))
    await audit.record(user, "criou", "contrato", doc["id"], label=doc["party_name"], after=doc)
    return await get_or_404("contracts", doc["id"], "Contrato")


@router.put("/{cid}")
async def update_contract(cid: str, data: ContractInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("contracts", cid, "Contrato")
    patch = await _link_party(data.model_dump())
    patch["updated_at"] = now_iso()
    await db.contracts.update_one({"id": cid}, {"$set": patch})
    after = await db.contracts.find_one({"id": cid}, PROJECTION)
    await audit.record(
        user, "atualizou", "contrato", cid, label=after["party_name"], before=before, after=after
    )
    return after


@router.delete("/{cid}")
async def delete_contract(cid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("contracts", cid, "Contrato")
    await db.contracts.delete_one({"id": cid})
    await audit.record(admin, "removeu", "contrato", cid, label=doc["party_name"], before=doc)
    return {"message": "Removido"}
