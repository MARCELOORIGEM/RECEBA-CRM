"""Formulários públicos de cadastro.

A entrada de restaurantes e entregadores era 100% digitação da equipe. Aqui o
gestor monta um formulário, escolhe os campos, copia o link e manda para quem
vai se cadastrar — a resposta entra direto no CRM.

A rota pública fica em `routers/public.py`, separada de propósito: tudo neste
arquivo exige sessão, tudo lá é aberto à internet.
"""
import re
import unicodedata
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import audit, pg, repo
from ..deps import get_current_user, require_admin
from ..permissoes import acesso
from ..form_templates import MODELOS
from ..models import FormInput, FormPatch
from ..repo import get_or_404
from ..security import now_utc

router = APIRouter(prefix="/forms", tags=["formulários"], dependencies=[Depends(acesso("formularios"))])

# Campos que o formulário consegue gravar direto no cadastro de destino.
# Qualquer outra chave vira informação extra, guardada no registro e na
# resposta, em vez de ser descartada em silêncio.
CAMPOS_DO_DESTINO = {
    "lead": {
        "name", "contact_name", "phone", "email", "city", "category",
        "source", "estimated_value", "notes",
    },
    "restaurante": {
        "name", "category", "contact_person", "phone", "email", "cnpj",
        "address", "notes",
    },
    "entregador": {
        "name", "phone", "email", "vehicle_type", "plate", "notes",
        # Dados de pagamento: é com eles que o repasse sai.
        "cpf", "bank", "bank_agency", "bank_account", "account_type",
        "pix_key_type", "pix_key",
    },
}

COLECAO_DO_DESTINO = {
    "lead": "leads",
    "restaurante": "restaurants",
    "entregador": "drivers",
}


def gerar_slug(texto: str) -> str:
    """Título vira endereço: 'Cadastro de Restaurantes' -> 'cadastro-de-restaurantes'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^a-zA-Z0-9]+", "-", sem_acento).strip("-").lower()
    return limpo[:60] or "formulario"


async def slug_livre(base: str, ignorar_id: str = "") -> str:
    """Garante unicidade sem estourar erro na cara do usuário."""
    candidato, n = base, 2
    while True:
        existente = await repo.um_por("forms", "slug", candidato)
        if not existente or existente.get("id") == ignorar_id:
            return candidato
        candidato = f"{base}-{n}"
        n += 1


@router.get("/templates")
async def list_templates(user: dict = Depends(get_current_user)):
    """Modelos padrão por destino.

    O construtor parte daqui em vez de uma folha em branco: quem cria um
    formulário de entregador já encontra as perguntas do processo montadas, e
    edita a partir delas.
    """
    return MODELOS


@router.get("")
async def list_forms(
    page: int = 1, page_size: int = 50, user: dict = Depends(get_current_user)
):
    return await repo.paginar("forms", page=page, page_size=page_size)


@router.get("/{fid}")
async def get_form(fid: str, user: dict = Depends(get_current_user)):
    return await get_or_404("forms", fid, "Formulário")


@router.get("/{fid}/submissions")
async def list_submissions(
    fid: str, page: int = 1, page_size: int = 50, user: dict = Depends(get_current_user)
):
    await get_or_404("forms", fid, "Formulário")
    return await repo.paginar(
        "form_submissions", repo.filtro("form_submissions").igual("form_id", fid),
        page=page, page_size=page_size,
    )


@router.delete("/{fid}/submissions/{sid}")
async def delete_submission(fid: str, sid: str, admin: dict = Depends(require_admin)):
    """Apaga uma resposta recebida.

    Existe por causa do pedido de exclusão previsto na LGPD: quem se cadastrou
    pode pedir para sair, e a resposta guarda CPF, conta e chave PIX. Apagar só
    o cadastro no CRM não bastava — a cópia continuava aqui.

    O cadastro que a resposta gerou **não** é tocado: ele vive no CRM, com
    pedidos e pagamentos pendurados nele. Quem quiser apagar os dois apaga cada
    um na sua tela, e a auditoria registra as duas ações.
    """
    await get_or_404("forms", fid, "Formulário")
    # O DELETE devolve a linha apagada: lê e remove num passo só, e a
    # condição em `form_id` impede apagar resposta de outro formulário.
    resposta = await pg.um(
        "DELETE FROM form_submissions WHERE id = $1 AND form_id = $2 RETURNING *", sid, fid
    )
    if not resposta:
        raise HTTPException(status_code=404, detail="Resposta não encontrada")

    # O contador do formulário acompanha, sem descer abaixo de zero.
    await pg.executar(
        "UPDATE forms SET submissions_count = submissions_count - 1 "
        "WHERE id = $1 AND submissions_count > 0",
        fid,
    )
    await audit.record(
        admin, "removeu resposta de", "formulário", fid,
        label=resposta.get("record_name") or sid, before=resposta,
    )
    return {"message": "Resposta removida"}


def exigir_campo_nome(data: FormInput) -> None:
    """Restaurante, entregador e lead são identificados pelo nome. Um formulário
    sem esse campo geraria uma fila de cadastros "Sem nome"."""
    if not any(f.key == "name" for f in data.fields):
        raise HTTPException(
            status_code=422,
            detail='O formulário precisa de um campo com a chave "name" (o nome de quem se cadastra).',
        )


@router.post("", status_code=201)
async def create_form(data: FormInput, user: dict = Depends(get_current_user)):
    exigir_campo_nome(data)
    doc = data.model_dump()
    doc.update({
        "id": str(uuid.uuid4()),
        "slug": await slug_livre(gerar_slug(data.title)),
        "created_by": user["name"],
    })
    criado = await repo.inserir("forms", doc)
    await audit.record(user, "criou", "formulário", criado["id"], label=criado["title"],
                       after=criado)
    return criado


@router.put("/{fid}")
async def update_form(fid: str, data: FormInput, user: dict = Depends(get_current_user)):
    exigir_campo_nome(data)
    before = await get_or_404("forms", fid, "Formulário")
    patch = data.model_dump()
    # O slug é o link que já foi distribuído: mudar o título não pode quebrar
    # o endereço que está no WhatsApp de dezenas de pessoas.
    patch["slug"] = before["slug"]
    patch["updated_at"] = now_utc()
    after = await repo.atualizar("forms", fid, patch)
    await audit.record(
        user, "atualizou", "formulário", fid, label=after["title"], before=before, after=after
    )
    return after


@router.patch("/{fid}/active")
async def toggle_active(fid: str, body: FormPatch, user: dict = Depends(get_current_user)):
    await get_or_404("forms", fid, "Formulário")
    return await repo.atualizar("forms", fid, {"active": body.active, "updated_at": now_utc()})


@router.delete("/{fid}")
async def delete_form(
    fid: str, force: bool = Query(False), admin: dict = Depends(require_admin)
):
    doc = await get_or_404("forms", fid, "Formulário")
    if doc.get("submissions_count") and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Este formulário já recebeu {doc['submissions_count']} resposta(s). "
                "Desative-o para parar de receber sem perder o histórico, "
                "ou confirme a exclusão definitiva."
            ),
        )
    # As respostas são o histórico DESTE formulário: sem ele, viram órfãs, e
    # saem junto pelo ON DELETE CASCADE da chave estrangeira. Os cadastros já
    # gerados continuam no CRM, que é onde eles importam.
    await repo.remover("forms", fid)
    await audit.record(admin, "removeu", "formulário", fid, label=doc["title"], before=doc)
    return {"message": "Removido"}
