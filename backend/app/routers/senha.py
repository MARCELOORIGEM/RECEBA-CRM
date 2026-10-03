"""Redefinição de senha por link de uso único.

Um gestor que esquece a senha ficava dependendo de um administrador digitar
outra por ele — e contá-la por WhatsApp. Aqui o administrador gera um link, a
pessoa escolhe a própria senha e ninguém mais fica sabendo qual é.

Sem e-mail no caminho de propósito: SMTP é mais uma peça para configurar,
monitorar e falhar. O administrador entrega o link pelo canal que já usa.

O que guarda o link:
- o banco só tem o HASH do token; vazando a coleção, ninguém reconstrói o link;
- vale 30 minutos;
- um uso só — some assim que a senha é trocada;
- gerar um novo invalida o anterior.
"""
import hashlib
import secrets
import uuid
from datetime import timedelta

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Annotated

from .. import audit
from ..config import settings
from ..db import db
from ..deps import require_admin
from ..security import hash_password, now_iso, now_utc

router = APIRouter(prefix="/senha", tags=["senha"])

VALIDADE_MINUTOS = 30


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class NovaSenha(BaseModel):
    token: Annotated[str, Field(min_length=20, max_length=200)]
    nova_senha: Annotated[str, Field(min_length=8, max_length=200)]


@router.post("/link/{uid}")
async def gerar_link(uid: str, admin: dict = Depends(require_admin)):
    """Cria um link de redefinição para a conta indicada."""
    try:
        oid = ObjectId(uid)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    usuario = await db.users.find_one({"_id": oid}, {"password_hash": 0})
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    token = secrets.token_urlsafe(32)
    # Um pedido ativo por conta: gerar outro derruba o anterior.
    await db.password_resets.delete_many({"user_id": uid})
    await db.password_resets.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "token_hash": _hash(token),
        "expira_em": now_utc() + timedelta(minutes=VALIDADE_MINUTOS),
        "criado_por": admin["name"],
        "created_at": now_iso(),
    })
    await audit.record(
        admin, "gerou link de redefinição", "usuário", uid, label=usuario["email"]
    )

    base = settings.frontend_url.rstrip("/")
    return {
        # Única vez que o token aparece: o banco só guarda o hash.
        "link": f"{base}/redefinir-senha/{token}",
        "expira_em_minutos": VALIDADE_MINUTOS,
        "usuario": {"nome": usuario["name"], "email": usuario["email"]},
    }


@router.post("/redefinir")
async def redefinir(data: NovaSenha):
    """Troca a senha usando o token do link. Rota aberta — o token é a chave."""
    pedido = await db.password_resets.find_one({"token_hash": _hash(data.token)})
    # Mesma resposta para token inexistente e token vencido: distinguir os dois
    # contaria a um atacante que o token existiu.
    invalido = HTTPException(
        status_code=400, detail="Link inválido ou expirado. Peça outro ao administrador."
    )
    if not pedido:
        raise invalido

    expira = pedido["expira_em"]
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=now_utc().tzinfo)
    if expira < now_utc():
        await db.password_resets.delete_one({"id": pedido["id"]})
        raise invalido

    try:
        oid = ObjectId(pedido["user_id"])
    except InvalidId:
        raise invalido
    usuario = await db.users.find_one({"_id": oid})
    if not usuario:
        raise invalido

    await db.users.update_one(
        {"_id": oid}, {"$set": {"password_hash": hash_password(data.nova_senha)}}
    )
    # Uso único.
    await db.password_resets.delete_many({"user_id": pedido["user_id"]})
    # As tentativas de login erradas somem junto: quem acabou de redefinir não
    # pode cair no bloqueio de força bruta logo na primeira tentativa.
    await db.login_attempts.delete_many({"email": usuario["email"]})

    await audit.record(
        {"id": pedido["user_id"], "name": usuario["name"], "email": usuario["email"]},
        "redefiniu a senha",
        "usuário",
        pedido["user_id"],
        label=usuario["email"],
    )
    return {"message": "Senha redefinida. Já pode entrar com a nova senha."}
