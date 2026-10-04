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

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import audit, pg, repo
from ..config import settings
from ..deps import require_admin
from ..security import hash_password, now_utc

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
    usuario = await repo.pegar("users", uid)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    token = secrets.token_urlsafe(32)
    # Um pedido ativo por conta: gerar outro derruba o anterior.
    await pg.executar("DELETE FROM password_resets WHERE user_id = $1", uid)
    await repo.inserir("password_resets", {
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "token_hash": _hash(token),
        "expira_em": now_utc() + timedelta(minutes=VALIDADE_MINUTOS),
        "criado_por": admin["name"],
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
    # Sem índice TTL no Postgres: os pedidos vencidos saem aqui, na própria
    # rota que os consulta (mesmo raciocínio das tentativas de login).
    await pg.executar("DELETE FROM password_resets WHERE expira_em < $1", now_utc())
    pedido = await repo.um_por("password_resets", "token_hash", _hash(data.token))
    # Mesma resposta para token inexistente e token vencido: distinguir os dois
    # contaria a um atacante que o token existiu.
    invalido = HTTPException(
        status_code=400, detail="Link inválido ou expirado. Peça outro ao administrador."
    )
    if not pedido:
        raise invalido

    if pedido["expira_em"] < now_utc():
        await repo.remover("password_resets", pedido["id"])
        raise invalido

    usuario = await repo.pegar("users", pedido["user_id"])
    if not usuario:
        raise invalido

    await repo.atualizar("users", usuario["id"], {
        "password_hash": hash_password(data.nova_senha),
        "updated_at": now_utc(),
    })
    # Uso único.
    await pg.executar("DELETE FROM password_resets WHERE user_id = $1", usuario["id"])
    # As tentativas de login erradas somem junto: quem acabou de redefinir não
    # pode cair no bloqueio de força bruta logo na primeira tentativa.
    await pg.executar("DELETE FROM login_attempts WHERE email = $1", usuario["email"])

    await audit.record(
        {"id": pedido["user_id"], "name": usuario["name"], "email": usuario["email"]},
        "redefiniu a senha",
        "usuário",
        pedido["user_id"],
        label=usuario["email"],
    )
    return {"message": "Senha redefinida. Já pode entrar com a nova senha."}
