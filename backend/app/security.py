"""Senhas, tokens e cookies."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Response

from .config import settings


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "type": "access",
        "iat": now_utc(),
        # Instante de emissão com fração de segundo. O `iat` do JWT é inteiro:
        # um login e uma troca de senha no mesmo segundo ficavam empatados, e
        # a sessão aberta com a senha antiga sobrevivia à troca. É contra este
        # valor que o corte do usuário (`users.sessoes_desde`) é comparado.
        "emitido_em": now_utc().timestamp(),
        "exp": now_utc() + timedelta(minutes=settings.access_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now_utc(),
        "emitido_em": now_utc().timestamp(),
        "exp": now_utc() + timedelta(days=settings.refresh_ttl_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def _cookie_kwargs(max_age: int) -> dict:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "max_age": max_age,
        "path": "/",
    }


def set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie("access_token", token, **_cookie_kwargs(settings.access_ttl_minutes * 60))


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    set_access_cookie(response, access)
    response.set_cookie(
        "refresh_token", refresh, **_cookie_kwargs(settings.refresh_ttl_days * 86400)
    )


def clear_auth_cookies(response: Response) -> None:
    for name in ("access_token", "refresh_token"):
        response.delete_cookie(
            name, path="/", secure=settings.cookie_secure, samesite=settings.cookie_samesite
        )
