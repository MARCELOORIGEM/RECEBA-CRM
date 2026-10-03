from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException

from .. import audit
from ..db import db
from ..deps import require_admin
from ..models import UserCreate, UserUpdate
from ..security import hash_password, now_iso

router = APIRouter(prefix="/users", tags=["usuários"])

SAFE = {"password_hash": 0}


def _oid(uid: str) -> ObjectId:
    try:
        return ObjectId(uid)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")


def _public(u: dict) -> dict:
    u["id"] = str(u.pop("_id"))
    u.setdefault("active", True)
    return u


@router.get("")
async def list_users(admin: dict = Depends(require_admin)):
    users = await db.users.find({}, SAFE).sort("created_at", 1).to_list(500)
    return [_public(u) for u in users]


@router.post("", status_code=201)
async def create_user(data: UserCreate, admin: dict = Depends(require_admin)):
    email = data.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    doc = {
        "name": data.name,
        "email": email,
        "password_hash": hash_password(data.password),
        "role": data.role,
        "active": True,
        "created_at": now_iso(),
    }
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    await audit.record(admin, "criou", "usuário", uid, label=email)
    return {"id": uid, "name": data.name, "email": email, "role": data.role,
            "active": True, "created_at": doc["created_at"]}


@router.put("/{uid}")
async def update_user(uid: str, data: UserUpdate, admin: dict = Depends(require_admin)):
    oid = _oid(uid)
    before = await db.users.find_one({"_id": oid}, SAFE)
    if not before:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    update: dict = {}
    if data.name is not None:
        update["name"] = data.name
    if data.role is not None:
        update["role"] = data.role
    if data.password:
        update["password_hash"] = hash_password(data.password)
    if data.active is not None:
        update["active"] = data.active

    # Evita que o último admin se rebaixe ou se desative e tranque a operação.
    perde_admin = (update.get("role") == "manager") or (update.get("active") is False)
    if uid == admin["id"] and perde_admin:
        raise HTTPException(
            status_code=400, detail="Você não pode remover o próprio acesso de administrador"
        )
    if before.get("role") == "admin" and perde_admin:
        outros = await db.users.count_documents(
            {"role": "admin", "active": {"$ne": False}, "_id": {"$ne": oid}}
        )
        if outros == 0:
            raise HTTPException(
                status_code=400, detail="É preciso manter ao menos um administrador ativo"
            )

    if update:
        await db.users.update_one({"_id": oid}, {"$set": update})
    after = await db.users.find_one({"_id": oid}, SAFE)
    await audit.record(admin, "atualizou", "usuário", uid, label=after["email"],
                       before=dict(before), after=dict(after))
    return _public(after)


@router.delete("/{uid}")
async def delete_user(uid: str, admin: dict = Depends(require_admin)):
    oid = _oid(uid)
    if uid == admin["id"]:
        raise HTTPException(status_code=400, detail="Você não pode remover sua própria conta")
    doc = await db.users.find_one({"_id": oid}, SAFE)
    if not doc:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if doc.get("role") == "admin":
        outros = await db.users.count_documents(
            {"role": "admin", "active": {"$ne": False}, "_id": {"$ne": oid}}
        )
        if outros == 0:
            raise HTTPException(
                status_code=400, detail="É preciso manter ao menos um administrador ativo"
            )
    await db.users.delete_one({"_id": oid})
    await audit.record(admin, "removeu", "usuário", uid, label=doc["email"])
    return {"message": "Removido"}
