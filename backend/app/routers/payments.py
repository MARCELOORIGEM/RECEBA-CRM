import uuid

from fastapi import APIRouter, Depends, HTTPException

from .. import audit, pg, repo, tempo
from ..deps import get_current_user, require_admin
from ..models import PaymentInput
from ..repo import get_or_404
from ..security import now_utc

router = APIRouter(prefix="/payments", tags=["pagamentos"])

COLLECTION = {"restaurante": "restaurants", "entregador": "drivers"}


async def _link_creditor(data: dict) -> dict:
    tabela = COLLECTION[data["creditor_type"]]
    if data.get("creditor_id"):
        party = await repo.pegar(tabela, data["creditor_id"])
        if not party:
            raise HTTPException(status_code=404, detail="Credor não encontrado")
    else:
        party = await repo.um_por(tabela, "name", data["creditor"])
    if party:
        data["creditor_id"] = party["id"]
        data["creditor"] = party["name"]
    return data


async def _mover_saldo(pagamento: dict, sinal: int) -> None:
    """Baixa (sinal -1) ou devolve (sinal +1) o saldo do credor."""
    if not pagamento.get("creditor_id"):
        return
    valor = float(pagamento.get("amount") or 0)
    if pagamento["creditor_type"] == "entregador":
        await repo.incrementar(
            "drivers", pagamento["creditor_id"],
            {"balance_due": sinal * valor, "paid_total": -sinal * valor},
        )
    else:
        await repo.incrementar(
            "restaurants", pagamento["creditor_id"], {"commission_due": sinal * valor}
        )


@router.get("")
async def list_payments(
    search: str = "",
    status: str = "todos",
    creditor_type: str = "todos",
    creditor_id: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user),
):
    f = repo.filtro("payments")
    if status != "todos":
        f.igual("status", status)
    if creditor_type != "todos":
        f.igual("creditor_type", creditor_type)
    f.igual("creditor_id", creditor_id)
    f.desde("due_date", tempo.data_do_filtro(date_from))
    f.ate("due_date", tempo.data_do_filtro(date_to))
    f.busca(search, ["creditor", "notes"])

    result = await repo.paginar("payments", f, page=page, page_size=page_size,
                                ordenar_por="due_date", direcao="asc")

    # Totais do filtro inteiro, não só da página — o resumo financeiro precisa do
    # conjunto todo. Antes o frontend somava apenas o que estava carregado.
    onde, args = f.onde()
    buckets = {
        r["status"]: r["total"]
        for r in await pg.varios(
            f"SELECT status, COALESCE(SUM(amount), 0) AS total FROM payments {onde} "
            "GROUP BY status",
            *args,
        )
    }
    result["totals"] = {
        k: round(float(buckets.get(k, 0.0)), 2)
        for k in ("pendente", "pago", "atrasado", "cancelado")
    }
    result["totals"]["geral"] = round(sum(result["totals"].values()), 2)
    return result


@router.get("/{pid}")
async def get_payment(pid: str, user: dict = Depends(get_current_user)):
    return await get_or_404("payments", pid, "Pagamento")


@router.post("", status_code=201)
async def create_payment(data: PaymentInput, user: dict = Depends(get_current_user)):
    doc = await _link_creditor(data.model_dump())
    doc.update({"id": str(uuid.uuid4()), "created_by": user["name"]})
    criado = await repo.inserir("payments", doc)
    await audit.record(user, "criou", "pagamento", criado["id"], label=criado["creditor"],
                       after=criado)
    return criado


@router.put("/{pid}")
async def update_payment(pid: str, data: PaymentInput, user: dict = Depends(get_current_user)):
    before = await get_or_404("payments", pid, "Pagamento")
    if before["status"] == "pago":
        raise HTTPException(
            status_code=409, detail="Pagamento liquidado não pode ser editado. Estorne antes."
        )
    patch = await _link_creditor(data.model_dump())
    patch["updated_at"] = now_utc()
    after = await repo.atualizar("payments", pid, patch)
    await audit.record(
        user, "atualizou", "pagamento", pid, label=after["creditor"], before=before, after=after
    )
    return after


@router.post("/{pid}/settle")
async def settle_payment(pid: str, user: dict = Depends(get_current_user)):
    """Liquida e baixa o saldo do credor.

    Antes o saldo a receber do entregador ficava congelado mesmo depois do repasse
    ser marcado como pago.
    """
    before = await get_or_404("payments", pid, "Pagamento")
    if before["status"] == "pago":
        raise HTTPException(status_code=409, detail="Pagamento já está liquidado")

    # A troca de status é condicional: dois cliques em "liquidar" ao mesmo
    # tempo passariam os dois pela checagem acima, e o saldo seria baixado em
    # dobro. Só quem de fato mudou a linha move o saldo.
    agora = now_utc()
    after = await pg.um(
        "UPDATE payments SET status = 'pago', paid_at = $2, updated_at = $2 "
        "WHERE id = $1 AND status <> 'pago' RETURNING *",
        pid, agora,
    )
    if not after:
        raise HTTPException(status_code=409, detail="Pagamento já está liquidado")
    await _mover_saldo(before, -1)

    await audit.record(
        user, "liquidou", "pagamento", pid, label=after["creditor"], before=before, after=after
    )
    return after


@router.post("/{pid}/reopen")
async def reopen_payment(pid: str, admin: dict = Depends(require_admin)):
    """Estorna uma liquidação feita por engano, devolvendo o saldo ao credor."""
    before = await get_or_404("payments", pid, "Pagamento")
    if before["status"] != "pago":
        raise HTTPException(status_code=409, detail="Só é possível estornar pagamento liquidado")

    after = await pg.um(
        "UPDATE payments SET status = 'pendente', paid_at = NULL, updated_at = $2 "
        "WHERE id = $1 AND status = 'pago' RETURNING *",
        pid, now_utc(),
    )
    if not after:
        raise HTTPException(status_code=409, detail="Só é possível estornar pagamento liquidado")
    await _mover_saldo(before, +1)

    await audit.record(
        admin, "estornou", "pagamento", pid, label=after["creditor"], before=before, after=after
    )
    return after


@router.delete("/{pid}")
async def delete_payment(pid: str, admin: dict = Depends(require_admin)):
    doc = await get_or_404("payments", pid, "Pagamento")
    if doc["status"] == "pago":
        raise HTTPException(
            status_code=409,
            detail="Pagamento liquidado faz parte do histórico financeiro. Estorne antes de excluir.",
        )
    await repo.remover("payments", pid)
    await audit.record(admin, "removeu", "pagamento", pid, label=doc["creditor"], before=doc)
    return {"message": "Removido"}
