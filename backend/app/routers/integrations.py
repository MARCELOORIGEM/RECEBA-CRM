"""Chaves de API e webhooks.

A versão anterior guardava a chave em texto puro e devolvia o valor completo em
toda listagem: quem tivesse acesso de leitura ao painel (ou um dump do banco)
levava embora as credenciais de produção. Agora só o hash é armazenado, o valor
aparece uma única vez na criação e a lista mostra apenas o prefixo.
"""
import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends

from .. import audit
from ..db import db
from ..deps import get_current_user, require_admin
from ..models import ApiKeyInput, WebhookInput
from ..repo import PROJECTION, get_or_404
from ..security import now_iso

router = APIRouter(prefix="/integrations", tags=["integrações"])

KEY_SAFE = {"_id": 0, "key_hash": 0}


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.get("/keys")
async def list_keys(admin: dict = Depends(require_admin)):
    return await db.api_keys.find({}, KEY_SAFE).sort("created_at", -1).to_list(200)


@router.post("/keys", status_code=201)
async def create_key(data: ApiKeyInput, admin: dict = Depends(require_admin)):
    prefix = "mln_live_" if data.environment == "production" else "mln_test_"
    raw = prefix + secrets.token_hex(20)
    doc = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "environment": data.environment,
        "key_hash": hash_key(raw),
        "key_preview": f"{raw[:len(prefix) + 4]}…{raw[-4:]}",
        "created_at": now_iso(),
        "created_by": admin["name"],
        "last_used": None,
    }
    await db.api_keys.insert_one(dict(doc))
    await audit.record(admin, "criou", "chave de API", doc["id"], label=data.name)
    public = {k: v for k, v in doc.items() if k not in ("key_hash", "_id")}
    # Única vez que o valor completo trafega.
    return {**public, "key": raw}


@router.delete("/keys/{kid}")
async def delete_key(kid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("api_keys", kid, "Chave")
    await db.api_keys.delete_one({"id": kid})
    await audit.record(admin, "revogou", "chave de API", kid, label=doc.get("name", ""))
    return {"message": "Revogada"}


@router.get("/webhooks")
async def list_webhooks(user: dict = Depends(get_current_user)):
    return await db.webhooks.find({}, PROJECTION).sort("created_at", -1).to_list(200)


@router.post("/webhooks", status_code=201)
async def create_webhook(data: WebhookInput, admin: dict = Depends(require_admin)):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": now_iso(), "created_by": admin["name"]})
    await db.webhooks.insert_one(dict(doc))
    await audit.record(admin, "criou", "webhook", doc["id"], label=doc["provider"])
    return await get_or_404("webhooks", doc["id"], "Webhook")


@router.put("/webhooks/{wid}")
async def update_webhook(wid: str, data: WebhookInput, admin: dict = Depends(require_admin)):
    before = await get_or_404("webhooks", wid, "Webhook")
    await db.webhooks.update_one({"id": wid}, {"$set": data.model_dump()})
    after = await db.webhooks.find_one({"id": wid}, PROJECTION)
    await audit.record(admin, "atualizou", "webhook", wid, label=after["provider"],
                       before=before, after=after)
    return after


@router.delete("/webhooks/{wid}")
async def delete_webhook(wid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("webhooks", wid, "Webhook")
    await db.webhooks.delete_one({"id": wid})
    await audit.record(admin, "removeu", "webhook", wid, label=doc["provider"])
    return {"message": "Removido"}


@router.get("/logs")
async def list_logs(provider: str = "todos", user: dict = Depends(get_current_user)):
    query = {} if provider == "todos" else {"provider": provider}
    return await db.webhook_logs.find(query, PROJECTION).sort("created_at", -1).to_list(100)
