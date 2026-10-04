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

from .. import audit, repo
from ..deps import get_current_user, require_admin
from ..models import ApiKeyInput, WebhookInput
from ..repo import get_or_404

router = APIRouter(prefix="/integrations", tags=["integrações"])


def _sem_hash(chave: dict) -> dict:
    return {k: v for k, v in chave.items() if k != "key_hash"}


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.get("/keys")
async def list_keys(admin: dict = Depends(require_admin)):
    return [_sem_hash(k) for k in await repo.listar("api_keys", limite=200)]


@router.post("/keys", status_code=201)
async def create_key(data: ApiKeyInput, admin: dict = Depends(require_admin)):
    prefix = "mln_live_" if data.environment == "production" else "mln_test_"
    raw = prefix + secrets.token_hex(20)
    criada = await repo.inserir("api_keys", {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "environment": data.environment,
        "key_hash": hash_key(raw),
        "key_preview": f"{raw[:len(prefix) + 4]}…{raw[-4:]}",
        "created_by": admin["name"],
    })
    await audit.record(admin, "criou", "chave de API", criada["id"], label=data.name)
    # Única vez que o valor completo trafega.
    return {**_sem_hash(criada), "key": raw}


@router.delete("/keys/{kid}")
async def delete_key(kid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("api_keys", kid, "Chave")
    await repo.remover("api_keys", kid)
    await audit.record(admin, "revogou", "chave de API", kid, label=doc.get("name", ""))
    return {"message": "Revogada"}


@router.get("/webhooks")
async def list_webhooks(user: dict = Depends(get_current_user)):
    return await repo.listar("webhooks", limite=200)


@router.post("/webhooks", status_code=201)
async def create_webhook(data: WebhookInput, admin: dict = Depends(require_admin)):
    doc = data.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_by": admin["name"]})
    criado = await repo.inserir("webhooks", doc)
    await audit.record(admin, "criou", "webhook", criado["id"], label=criado["provider"])
    return criado


@router.put("/webhooks/{wid}")
async def update_webhook(wid: str, data: WebhookInput, admin: dict = Depends(require_admin)):
    before = await get_or_404("webhooks", wid, "Webhook")
    after = await repo.atualizar("webhooks", wid, data.model_dump())
    await audit.record(admin, "atualizou", "webhook", wid, label=after["provider"],
                       before=before, after=after)
    return after


@router.delete("/webhooks/{wid}")
async def delete_webhook(wid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("webhooks", wid, "Webhook")
    await repo.remover("webhooks", wid)
    await audit.record(admin, "removeu", "webhook", wid, label=doc["provider"])
    return {"message": "Removido"}


@router.get("/logs")
async def list_logs(provider: str = "todos", user: dict = Depends(get_current_user)):
    f = repo.filtro("webhook_logs")
    if provider != "todos":
        f.igual("provider", provider)
    return await repo.listar("webhook_logs", f, limite=100)
