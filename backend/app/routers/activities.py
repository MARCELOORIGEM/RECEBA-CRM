"""Atividades: tarefas com prazo e interações registradas.

É o que transforma cadastro em relacionamento — quem ligou, quando, o que ficou
combinado e o que vence hoje.
"""
import uuid

from fastapi import APIRouter, Depends

from .. import audit, pg, repo, tempo
from ..consulta import Filtro
from ..deps import get_current_user, require_admin
from ..permissoes import acesso
from ..models import ActivityInput
from ..repo import get_or_404
from ..security import now_utc

router = APIRouter(
    prefix="/activities", tags=["atividades"],
    dependencies=[Depends(acesso("atividades", tambem=("funil", "restaurantes", "entregadores")))],
)


def _recorte(f: Filtro, scope: str) -> Filtro:
    """Aplica o recorte de agenda ao filtro.

    Fronteiras no fuso do negócio: em UTC, uma tarefa marcada para as 22h em
    São Paulo já caía no dia seguinte. A mesma função serve à lista e ao
    contador da aba — os dois precisam bater.
    """
    inicio_hoje, fim_hoje = tempo.inicio_do_dia(), tempo.fim_do_dia()
    if scope == "hoje":
        # "Hoje" é o que vence hoje. O que já venceu tem aba própria; sem o
        # limite inferior, as duas abas mostravam exatamente a mesma lista.
        f.verdadeiro("done", False).desde("due_at", inicio_hoje).ate("due_at", fim_hoje)
    elif scope == "atrasadas":
        f.verdadeiro("done", False).antes_de("due_at", now_utc())
    elif scope == "proximas":
        f.verdadeiro("done", False).bruto('"due_at" > {}', fim_hoje)
    elif scope == "semana":
        f.verdadeiro("done", False).bruto('"due_at" > {}', fim_hoje).ate(
            "due_at", tempo.fim_do_dia(7)
        )
    elif scope == "concluidas":
        f.verdadeiro("done", True)
    elif scope == "abertas":
        f.verdadeiro("done", False)
    return f


@router.get("")
async def list_activities(
    scope: str = "todas",  # hoje | atrasadas | proximas | concluidas | todas
    related_type: str = "",
    related_id: str = "",
    kind: str = "todas",
    page: int = 1,
    page_size: int = 100,
    user: dict = Depends(get_current_user),
):
    f = repo.filtro("activities")
    f.igual("related_type", related_type)
    f.igual("related_id", related_id)
    if kind != "todas":
        f.igual("kind", kind)
    _recorte(f, scope)

    concluidas = scope == "concluidas"
    return await repo.paginar(
        "activities", f, page=page, page_size=page_size,
        ordenar_por="completed_at" if concluidas else "due_at",
        direcao="desc" if concluidas else "asc",
    )


@router.get("/summary")
async def summary(user: dict = Depends(get_current_user)):
    # Uma ida ao banco para os quatro números, com os mesmos recortes da lista.
    partes, args = [], []
    for nome in ("atrasadas", "hoje", "semana", "abertas"):
        # Os recortes vão todos no mesmo comando: cada um numera os próprios
        # parâmetros a partir de onde o anterior parou.
        f = _recorte(Filtro("activities", primeiro_parametro=len(args) + 1), nome)
        onde, a = f.onde()
        args.extend(a)
        partes.append(f"count(*) FILTER ({onde}) AS {nome}")
    return await pg.um(f"SELECT {', '.join(partes)} FROM activities", *args)


@router.post("", status_code=201)
async def create_activity(data: ActivityInput, user: dict = Depends(get_current_user)):
    doc = data.model_dump()
    doc["due_at"] = tempo.com_fuso(doc["due_at"])
    # Interação é um registro do que já aconteceu; nasce concluída.
    if doc["kind"] == "interacao":
        doc["done"] = True
    doc.update({
        "id": str(uuid.uuid4()),
        "owner_name": doc.get("owner_name") or user["name"],
        "completed_at": now_utc() if doc["done"] else None,
        "created_by": user["name"],
    })
    criado = await repo.inserir("activities", doc)
    await audit.record(user, "criou", "atividade", criado["id"], label=criado["title"],
                       after=criado)
    return criado


@router.put("/{aid}")
async def update_activity(aid: str, data: ActivityInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("activities", aid, "Atividade")
    patch = data.model_dump()
    patch["due_at"] = tempo.com_fuso(patch["due_at"])
    patch["updated_at"] = now_utc()
    patch["completed_at"] = before.get("completed_at") if patch["done"] else None
    if patch["done"] and not patch["completed_at"]:
        patch["completed_at"] = now_utc()
    after = await repo.atualizar("activities", aid, patch)
    await audit.record(user, "atualizou", "atividade", aid, label=after["title"],
                       before=before, after=after)
    return after


@router.patch("/{aid}/toggle")
async def toggle_done(aid: str, user: dict = Depends(get_current_user)):
    before = await get_or_404("activities", aid, "Atividade")
    done = not before.get("done", False)
    agora = now_utc()
    return await repo.atualizar(
        "activities", aid,
        {"done": done, "completed_at": agora if done else None, "updated_at": agora},
    )


@router.delete("/{aid}")
async def delete_activity(aid: str, user: dict = Depends(get_current_user)):
    doc = await get_or_404("activities", aid, "Atividade")
    # Interação já registrada é histórico: só o admin apaga.
    if doc.get("kind") == "interacao" and user.get("role") != "admin":
        await require_admin(user)
    await repo.remover("activities", aid)
    await audit.record(user, "removeu", "atividade", aid, label=doc["title"], before=doc)
    return {"message": "Removido"}
