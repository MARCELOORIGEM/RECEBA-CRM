from datetime import timedelta

import jwt
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..config import settings
from ..db import db
from ..deps import get_current_user
from .. import audit
from ..rede import ip_do_cliente
from ..models import LoginInput, PasswordChange, ProfileUpdate, RegisterInput
from ..security import (
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    now_iso,
    now_utc,
    set_access_cookie,
    set_auth_cookies,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _throttle(request: Request, email: str) -> None:
    """Trava força bruta por e-mail + IP. Antes era possível testar senhas sem limite."""
    since = now_utc() - timedelta(minutes=settings.login_window_minutes)
    tries = await db.login_attempts.count_documents(
        {"email": email, "ip": ip_do_cliente(request), "created_at": {"$gte": since}}
    )
    if tries >= settings.login_max_attempts:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de login. Aguarde alguns minutos e tente de novo.",
        )


@router.post("/login")
async def login(data: LoginInput, request: Request, response: Response):
    email = data.email.lower()
    await _throttle(request, email)

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        # `created_at` precisa ser um datetime BSON: o índice TTL da coleção só
        # expira campos de data. Gravado como texto ISO, o índice existia mas
        # nunca apagava nada e a coleção crescia sem limite.
        await db.login_attempts.insert_one(
            {"email": email, "ip": ip_do_cliente(request), "created_at": now_utc()}
        )
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    if user.get("active") is False:
        raise HTTPException(status_code=403, detail="Conta desativada")

    uid = str(user["_id"])
    role = user.get("role", "manager")
    set_auth_cookies(response, create_access_token(uid, email, role), create_refresh_token(uid))
    await db.login_attempts.delete_many({"email": email})
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": now_iso()}})
    return {"id": uid, "name": user["name"], "email": email, "role": role}


@router.post("/register")
async def register(data: RegisterInput, response: Response):
    """Cadastro público — desligado por padrão.

    Antes este endpoint era aberto e aceitava `role` do corpo da requisição:
    qualquer pessoa com a URL da API criava uma conta de administrador.
    """
    if not settings.allow_public_register:
        raise HTTPException(
            status_code=403, detail="Cadastro público desativado. Peça acesso a um administrador."
        )
    email = data.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    doc = {
        "name": data.name,
        "email": email,
        "password_hash": hash_password(data.password),
        "role": "manager",  # nunca vem do cliente
        "active": True,
        "created_at": now_iso(),
    }
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    set_auth_cookies(response, create_access_token(uid, email, "manager"), create_refresh_token(uid))
    return {"id": uid, "name": data.name, "email": email, "role": "manager"}


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"message": "Logout realizado"}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.put("/me")
async def update_profile(data: ProfileUpdate, user: dict = Depends(get_current_user)):
    """Cada pessoa edita o próprio nome, sem depender do administrador."""
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"name": data.name}})
    return {**user, "name": data.name}


@router.post("/password")
async def change_password(data: PasswordChange, user: dict = Depends(get_current_user)):
    """Troca da própria senha.

    Antes só existia a edição de usuários, restrita ao administrador: um gestor
    não tinha como trocar a senha com que tinha sido cadastrado.
    """
    doc = await db.users.find_one({"_id": ObjectId(user["id"])})
    if not doc or not verify_password(data.current_password, doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Senha atual incorreta")
    if verify_password(data.new_password, doc["password_hash"]):
        raise HTTPException(status_code=400, detail="A nova senha é igual à atual")

    await db.users.update_one(
        {"_id": doc["_id"]}, {"$set": {"password_hash": hash_password(data.new_password)}}
    )
    await audit.record(user, "trocou a senha", "usuário", user["id"], label=user["email"])
    return {"message": "Senha alterada"}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Sem token de atualização")
    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token inválido")

    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user or user.get("active") is False:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")

    uid = str(user["_id"])
    role = user.get("role", "manager")
    set_access_cookie(response, create_access_token(uid, user["email"], role))
    return {"id": uid, "name": user["name"], "email": user["email"], "role": role}
