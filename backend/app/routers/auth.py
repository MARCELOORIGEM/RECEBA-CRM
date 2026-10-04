import uuid
from datetime import timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import audit, pg, repo
from ..config import settings
from ..deps import get_current_user, sessao_cortada
from ..models import LoginInput, PasswordChange, ProfileUpdate, RegisterInput
from ..permissoes import modulos_de
from ..rede import ip_do_cliente
from ..security import (
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    now_utc,
    set_access_cookie,
    set_auth_cookies,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _publico(user: dict) -> dict:
    """O que volta para o navegador. Sem hash de senha, nunca."""
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user.get("role", "manager"),
        "modulos": modulos_de(user),
    }


async def _limpar_tentativas_velhas() -> None:
    """Apaga as tentativas fora da janela.

    No Mongo, um índice TTL fazia isso sozinho. O PostgreSQL não tem TTL, e
    deixar a limpeza para uma tarefa de fundo acrescentaria uma peça que pode
    não estar rodando — o sintoma seria uma tabela crescendo sem limite, sem
    ninguém perceber. Limpar aqui, na própria consulta que usa a tabela, custa
    um DELETE barato (há índice em created_at) e não depende de nada externo.
    """
    await pg.executar(
        "DELETE FROM login_attempts WHERE created_at < $1",
        now_utc() - timedelta(minutes=settings.login_window_minutes),
    )


async def _throttle(request: Request, email: str) -> None:
    """Trava força bruta por e-mail + IP. Antes era possível testar senhas sem limite."""
    await _limpar_tentativas_velhas()
    desde = now_utc() - timedelta(minutes=settings.login_window_minutes)
    tentativas = await pg.valor(
        "SELECT count(*) FROM login_attempts "
        "WHERE email = $1 AND ip = $2 AND created_at >= $3",
        email,
        ip_do_cliente(request),
        desde,
    )
    if int(tentativas or 0) >= settings.login_max_attempts:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de login. Aguarde alguns minutos e tente de novo.",
        )


@router.post("/login")
async def login(data: LoginInput, request: Request, response: Response):
    email = data.email.lower()
    await _throttle(request, email)

    user = await repo.um_por("users", "email", email)
    if not user or not verify_password(data.password, user["password_hash"]):
        await pg.executar(
            "INSERT INTO login_attempts (email, ip) VALUES ($1, $2)",
            email,
            ip_do_cliente(request),
        )
        # A mesma mensagem para e-mail inexistente e senha errada: distingui-las
        # entregaria quais e-mails têm conta.
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    if user.get("active") is False:
        raise HTTPException(status_code=403, detail="Conta desativada")

    uid, role = user["id"], user.get("role", "manager")
    set_auth_cookies(response, create_access_token(uid, email, role), create_refresh_token(uid))
    await pg.executar("DELETE FROM login_attempts WHERE email = $1", email)
    await repo.atualizar("users", uid, {"last_login_at": now_utc()})
    return _publico(user)


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
    if await repo.existe("users", "email", email):
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")

    user = await repo.inserir("users", {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "email": email,
        "password_hash": hash_password(data.password),
        "role": "manager",  # nunca vem do cliente
        "active": True,
    })
    set_auth_cookies(
        response,
        create_access_token(user["id"], email, "manager"),
        create_refresh_token(user["id"]),
    )
    return _publico(user)


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
    await repo.atualizar("users", user["id"], {"name": data.name, "updated_at": now_utc()})
    return {**user, "name": data.name}


@router.post("/password")
async def change_password(
    data: PasswordChange, response: Response, user: dict = Depends(get_current_user)
):
    """Troca da própria senha.

    Antes só existia a edição de usuários, restrita ao administrador: um gestor
    não tinha como trocar a senha com que tinha sido cadastrado.
    """
    doc = await repo.pegar("users", user["id"])
    if not doc or not verify_password(data.current_password, doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Senha atual incorreta")
    if verify_password(data.new_password, doc["password_hash"]):
        raise HTTPException(status_code=400, detail="A nova senha é igual à atual")

    agora = now_utc()
    await repo.atualizar("users", user["id"], {
        "password_hash": hash_password(data.new_password),
        "sessoes_desde": agora,
        "updated_at": agora,
    })
    # O corte derruba as sessões abertas com a senha antiga — inclusive num
    # celular esquecido logado. Esta aqui ganha cookies novos, para quem
    # acabou de trocar a senha não ser posto para fora junto.
    set_auth_cookies(
        response,
        create_access_token(user["id"], user["email"], user.get("role", "manager")),
        create_refresh_token(user["id"]),
    )
    # Trocar a senha invalida os links de redefinição pendentes: quem pediu um
    # link e depois lembrou a senha não deixa uma porta aberta para trás.
    await pg.executar("DELETE FROM password_resets WHERE user_id = $1", user["id"])
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

    user = await repo.pegar("users", payload.get("sub") or "")
    if not user or user.get("active") is False:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if sessao_cortada(user, payload):
        raise HTTPException(status_code=401, detail="Sua sessão foi encerrada. Entre novamente.")

    set_access_cookie(
        response,
        create_access_token(user["id"], user["email"], user.get("role", "manager")),
    )
    return _publico(user)
