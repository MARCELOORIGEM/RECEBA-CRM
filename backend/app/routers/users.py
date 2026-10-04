import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import audit, pg, repo
from ..deps import require_admin
from ..models import UserCreate, UserUpdate
from ..permissoes import MODULOS, modulos_de
from ..security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    now_utc,
    set_auth_cookies,
)

router = APIRouter(prefix="/users", tags=["usuários"])


def _public(u: dict) -> dict:
    """Sem o hash da senha: esta lista vai inteira para o navegador.

    `permissoes` é o que está gravado (None = todas as telas); `modulos` é o
    efeito disso, já resolvido — a tela usa um para editar e o outro para
    mostrar.
    """
    publico = {k: v for k, v in u.items() if k != "password_hash"}
    publico["modulos"] = modulos_de(u)
    return publico


def _normalizar(permissoes: list[str] | None) -> list[str] | None:
    """Sem repetição e na ordem do menu, para o diff da auditoria não acusar
    mudança onde só a ordem dos cliques mudou."""
    if permissoes is None:
        return None
    marcados = set(permissoes)
    return [m for m in MODULOS if m in marcados]


async def _outros_admins_ativos(uid: str) -> int:
    return int(await pg.valor(
        "SELECT count(*) FROM users WHERE role = 'admin' AND active AND id <> $1", uid
    ) or 0)


async def _get_or_404(uid: str) -> dict:
    # Um id que não existe é 404, como antes. No Mongo, um id fora do formato
    # de ObjectId precisava de tratamento à parte; aqui é só texto que não casa.
    doc = await repo.pegar("users", uid)
    if not doc:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return doc


@router.get("")
async def list_users(admin: dict = Depends(require_admin)):
    usuarios = await repo.listar("users", ordenar_por="created_at", direcao="asc", limite=500)
    return [_public(u) for u in usuarios]


@router.post("", status_code=201)
async def create_user(data: UserCreate, admin: dict = Depends(require_admin)):
    email = data.email.lower()
    if await repo.existe("users", "email", email):
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    criado = await repo.inserir("users", {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "email": email,
        "password_hash": hash_password(data.password),
        "role": data.role,
        "active": True,
        # Administrador vê tudo de qualquer jeito; a lista só vale para gestor.
        "permissoes": None if data.role == "admin" else _normalizar(data.permissoes),
    })
    await audit.record(admin, "criou", "usuário", criado["id"], label=email)
    return _public(criado)


@router.put("/{uid}")
async def update_user(
    uid: str, data: UserUpdate, response: Response, admin: dict = Depends(require_admin)
):
    before = await _get_or_404(uid)

    update: dict = {}
    if data.name is not None:
        update["name"] = data.name
    if data.role is not None:
        update["role"] = data.role
    if data.password:
        update["password_hash"] = hash_password(data.password)
        # Senha trocada pelo administrador: quem estava logado com a antiga
        # cai na próxima requisição. É o que se espera ao trocar a senha de
        # uma conta comprometida.
        update["sessoes_desde"] = now_utc()
    if data.active is not None:
        update["active"] = data.active
    if data.todas_as_telas:
        update["permissoes"] = None
    elif data.permissoes is not None:
        update["permissoes"] = _normalizar(data.permissoes)

    # Evita que o último admin se rebaixe ou se desative e tranque a operação.
    perde_admin = (update.get("role") == "manager") or (update.get("active") is False)
    if uid == admin["id"] and perde_admin:
        raise HTTPException(
            status_code=400, detail="Você não pode remover o próprio acesso de administrador"
        )
    if before.get("role") == "admin" and perde_admin and await _outros_admins_ativos(uid) == 0:
        raise HTTPException(
            status_code=400, detail="É preciso manter ao menos um administrador ativo"
        )

    if update:
        update["updated_at"] = now_utc()
    after = await repo.atualizar("users", uid, update)
    if data.password and uid == admin["id"]:
        # O administrador trocou a PRÓPRIA senha por esta tela: o corte acima
        # o derrubaria junto. Sessão nova para quem fez a troca.
        set_auth_cookies(
            response,
            create_access_token(admin["id"], admin["email"], admin.get("role", "admin")),
            create_refresh_token(admin["id"]),
        )
    await audit.record(admin, "atualizou", "usuário", uid, label=after["email"],
                       before=_public(before), after=_public(after))
    return _public(after)


@router.delete("/{uid}")
async def delete_user(uid: str, admin: dict = Depends(require_admin)):
    if uid == admin["id"]:
        raise HTTPException(status_code=400, detail="Você não pode remover sua própria conta")
    doc = await _get_or_404(uid)
    if doc.get("role") == "admin" and await _outros_admins_ativos(uid) == 0:
        raise HTTPException(
            status_code=400, detail="É preciso manter ao menos um administrador ativo"
        )
    await repo.remover("users", uid)
    await audit.record(admin, "removeu", "usuário", uid, label=doc["email"])
    return {"message": "Removido"}
