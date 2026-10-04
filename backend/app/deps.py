"""Dependências de autenticação e autorização."""
import jwt
from fastapi import Depends, HTTPException, Request

from . import repo
from .security import decode_token


def _bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    return header[7:] if header.startswith("Bearer ") else None


def sessao_cortada(user: dict, payload: dict) -> bool:
    """O token foi emitido antes do corte de sessões do usuário?

    O corte é gravado quando a senha muda ou o administrador altera o acesso.
    Sem ele, trocar a senha de uma conta vazada não adiantaria nada por até
    sete dias: o token de quem já estava dentro continuaria valendo.

    Compara com fração de segundo (`emitido_em`). Token sem esse campo —
    emitido antes dele existir — cai no `iat` inteiro, arredondado para cima
    a favor de derrubar: na dúvida, a sessão antiga não passa.
    """
    corte = user.get("sessoes_desde")
    if not corte:
        return False
    emitido = payload.get("emitido_em")
    if emitido is None:
        emitido = float(payload.get("iat") or 0)
        return emitido <= corte.timestamp()
    return float(emitido) < corte.timestamp()


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

    # O `sub` era um ObjectId do Mongo e precisava ser convertido — uma string
    # torta levantava InvalidId, que virava 500 em vez de 401. Agora é o mesmo
    # uuid em texto que está na coluna `id`: não há conversão, e token forjado
    # simplesmente não encontra usuário.
    uid = payload.get("sub") or ""
    if not uid:
        raise HTTPException(status_code=401, detail="Token inválido")

    user = await repo.pegar("users", uid)
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if user.get("active") is False:
        raise HTTPException(status_code=403, detail="Conta desativada")
    if sessao_cortada(user, payload):
        raise HTTPException(
            status_code=401, detail="Sua sessão foi encerrada. Entre novamente."
        )

    # O hash da senha nunca sai daqui: este dicionário é devolvido em /auth/me
    # e circula por todo router como `user`.
    user.pop("password_hash", None)
    # Telas liberadas, já resolvidas (admin = todas; NULL = todas). É o que o
    # painel usa para montar o menu. Import local: permissoes importa deps.
    from .permissoes import modulos_de

    user["modulos"] = modulos_de(user)
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador")
    return user
