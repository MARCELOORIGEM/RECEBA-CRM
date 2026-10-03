"""Dependências de autenticação e autorização."""
import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, Request

from .db import db
from .security import decode_token


def _bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    return header[7:] if header.startswith("Bearer ") else None


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token") or _bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessão expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Tipo de token inválido")
    try:
        oid = ObjectId(payload["sub"])
    except (InvalidId, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="Token inválido")

    user = await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if user.get("active") is False:
        raise HTTPException(status_code=403, detail="Conta desativada")

    user["id"] = str(user.pop("_id"))
    user.pop("password_hash", None)
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador")
    return user
