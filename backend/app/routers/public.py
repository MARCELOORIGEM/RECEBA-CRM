"""Rotas abertas à internet.

Tudo aqui responde sem sessão, então cada endpoint é tratado como se um robô
estivesse do outro lado: só devolve o que precisa aparecer no formulário, limita
envios por IP, valida cada resposta contra a definição do campo e ignora
qualquer chave que o cliente invente.
"""
import uuid
from datetime import timedelta
from typing import Any, get_args

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import funil, repo
from ..config import settings
from ..models import LeadSource
from ..rede import ip_do_cliente
from ..security import now_iso, now_utc
from .forms import CAMPOS_DO_DESTINO, COLECAO_DO_DESTINO

router = APIRouter(prefix="/public", tags=["público"])

# Um formulário de cadastro legítimo é preenchido uma ou duas vezes por pessoa.
# Teto de envios por dispositivo na janela. Configurável porque o número
# certo depende do uso: um posto de cadastro numa ação de rua coloca dezenas de
# entregadores atrás do mesmo IP, e 10 travaria a fila.
MAX_ENVIOS_POR_IP = settings.max_envios_por_ip
JANELA_MINUTOS = 60

# Campo invisível no HTML. Pessoa nenhuma preenche; robô que varre o formulário
# preenche tudo que encontra.
CAMPO_ISCA = "_website"

VALOR_MAX = 2000


class Envio(BaseModel):
    respostas: dict[str, Any] = Field(default_factory=dict)


@router.get("/forms/{slug}")
async def ver_formulario(slug: str):
    """Só o necessário para desenhar o formulário — nada de contadores,
    autor, destino ou datas internas."""
    form = await repo.um_por("forms", "slug", slug)
    if not form:
        raise HTTPException(status_code=404, detail="Formulário não encontrado")
    if not form.get("active", True):
        raise HTTPException(
            status_code=410, detail="Este formulário não está mais recebendo respostas."
        )
    return {
        "slug": form["slug"],
        "title": form["title"],
        "description": form.get("description", ""),
        "fields": form.get("fields", []),
        "success_message": form.get("success_message", ""),
        # O formulário coleta CPF e conta bancária: quem preenche precisa saber
        # para que os dados vão antes de enviar.
        "privacidade": {
            "texto": settings.privacidade_texto,
            "url": settings.privacidade_url,
        },
    }


# A pessoa escolhe o rótulo bonito ("Conta Corrente"); o cadastro guarda o
# valor curto. Sem esta tradução, o campo chegaria como texto livre e a tela de
# entregadores não saberia exibi-lo.
CONTAS = {"conta corrente": "corrente", "corrente": "corrente",
          "conta poupança": "poupanca", "conta poupanca": "poupanca", "poupança": "poupanca",
          "poupanca": "poupanca"}
CHAVES_PIX = {"cpf": "cpf", "celular": "celular", "telefone": "celular",
              "e-mail": "email", "email": "email",
              "chave aleatória": "aleatoria", "chave aleatoria": "aleatoria",
              "aleatória": "aleatoria", "aleatoria": "aleatoria"}
MODAIS = {"moto": "moto", "motocicleta": "moto", "bicicleta": "bike", "bike": "bike",
          "carro": "carro", "van": "van"}


def _normalizar(bruto: Any, mapa: dict) -> str:
    return mapa.get(str(bruto or "").strip().lower(), "")


def _modal(bruto: Any) -> str:
    return _normalizar(bruto, MODAIS) or "moto"


def _validar(campo: dict, bruto: Any) -> Any:
    """Converte e confere um valor conforme a definição do campo."""
    rotulo = campo.get("label") or campo["key"]
    vazio = bruto is None or (isinstance(bruto, str) and not bruto.strip())

    if vazio:
        if campo.get("required"):
            raise HTTPException(status_code=422, detail=f'"{rotulo}" é obrigatório.')
        return ""

    if campo["type"] == "numero":
        try:
            return float(str(bruto).replace(".", "").replace(",", ".")
                         if isinstance(bruto, str) else bruto)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f'"{rotulo}" precisa ser um número.')

    texto = str(bruto).strip()
    if len(texto) > VALOR_MAX:
        raise HTTPException(status_code=422, detail=f'"{rotulo}" ficou longo demais.')

    if campo["type"] == "email" and ("@" not in texto or "." not in texto.split("@")[-1]):
        raise HTTPException(status_code=422, detail=f'"{rotulo}" precisa ser um e-mail válido.')

    if campo["type"] in ("selecao", "escolha"):
        opcoes = campo.get("options") or []
        if opcoes and texto not in opcoes and not campo.get("allow_other"):
            raise HTTPException(status_code=422, detail=f'"{rotulo}" tem um valor fora da lista.')

    if campo["type"] == "cpf":
        digitos = "".join(c for c in texto if c.isdigit())
        if len(digitos) != 11:
            raise HTTPException(
                status_code=422, detail=f'"{rotulo}" precisa ter 11 números.'
            )
        return digitos

    return texto


ORIGENS = set(get_args(LeadSource))


def _origem(valor: Any) -> str:
    texto = str(valor or "").strip().lower()
    if not texto:
        return "site"
    return texto if texto in ORIGENS else "outro"


def _numero(valor: Any) -> float:
    """Valor estimado digitado à mão: "abc" vira 0, não um erro 500."""
    try:
        return max(0.0, float(valor or 0))
    except (TypeError, ValueError):
        return 0.0


def _para_coluna(chave: str, valor: Any) -> Any:
    """Ajusta o tipo ao da coluna de destino.

    No Mongo, um campo do tipo "número" apontado para `phone` gravava um float
    no documento e ninguém reclamava. No Postgres a coluna é TEXT e o driver
    recusa o float — o envio do formulário inteiro cairia num 500. Só
    `estimated_value` é numérica; todo o resto é texto.
    """
    if chave == "estimated_value" or isinstance(valor, str):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


async def _criar_cadastro(form: dict, valores: dict, extras: dict) -> dict:
    """Monta o registro no destino escolhido pelo formulário."""
    destino = form["target"]
    base = {
        "id": str(uuid.uuid4()),
        "created_by": f"Formulário: {form['title']}",
        # Marca a procedência: um cadastro vindo da rua não é igual a um
        # cadastro conferido pela equipe.
        "origem": "formulario",
        "origem_form_id": form["id"],
        "extra_fields": extras,
        "notes": valores.get("notes", ""),
        "email": valores.get("email", ""),
        "phone": valores.get("phone", ""),
        "name": valores.get("name") or "Sem nome",
    }

    if destino == "lead":
        doc = {
            **base,
            "contact_name": valores.get("contact_name", ""),
            "city": valores.get("city", ""),
            "category": valores.get("category", ""),
            # O banco só aceita as origens da lista; texto livre vira "outro".
            "source": _origem(valores.get("source")),
            "stage": funil.INICIAL,
            "estimated_value": _numero(valores.get("estimated_value")),
            "owner_name": "",
            "lost_reason": "",
            "stage_history": [{"stage": funil.INICIAL, "at": now_iso(), "by": "formulário"}],
            "endereco": valores.get("endereco", ""),
            "bairro": valores.get("bairro", ""),
        }
    elif destino == "restaurante":
        doc = {
            **base,
            "category": valores.get("category") or "Outros",
            "contact_person": valores.get("contact_person", ""),
            "cnpj": valores.get("cnpj", ""),
            "address": valores.get("address", ""),
            "commission_rate": 15.0,
            # Nunca entra ativo: quem chega pelo formulário passa por conferência.
            "status": "em_analise",
        }
    else:
        doc = {
            **base,
            "vehicle_type": _modal(valores.get("vehicle_type")),
            "plate": (valores.get("plate") or "").upper(),
            "status": "offline",
            "rating": 5.0,
            "photo": "",
            # Dados de pagamento vindos do formulário de recrutamento.
            "cpf": "".join(c for c in str(valores.get("cpf") or "") if c.isdigit()),
            "bank": valores.get("bank", ""),
            "bank_agency": valores.get("bank_agency", ""),
            "bank_account": valores.get("bank_account", ""),
            "account_type": _normalizar(valores.get("account_type"), CONTAS),
            "pix_key_type": _normalizar(valores.get("pix_key_type"), CHAVES_PIX),
            "pix_key": valores.get("pix_key", ""),
        }

    return await repo.inserir(COLECAO_DO_DESTINO[destino], doc)


@router.post("/forms/{slug}", status_code=201)
async def responder_formulario(slug: str, envio: Envio, request: Request):
    form = await repo.um_por("forms", "slug", slug)
    if not form:
        raise HTTPException(status_code=404, detail="Formulário não encontrado")
    if not form.get("active", True):
        raise HTTPException(
            status_code=410, detail="Este formulário não está mais recebendo respostas."
        )

    ip = ip_do_cliente(request)
    desde = now_utc() - timedelta(minutes=JANELA_MINUTOS)
    recentes = await repo.contar(
        "form_submissions",
        repo.filtro("form_submissions").igual("ip", ip).desde("created_at", desde),
    )
    if recentes >= MAX_ENVIOS_POR_IP:
        raise HTTPException(
            status_code=429,
            detail="Muitos envios deste dispositivo. Tente novamente mais tarde.",
        )

    respostas = envio.respostas or {}

    # Isca: responde como se tivesse dado certo, mas não grava nada. Dizer "você
    # é um robô" só ensina o robô a contornar.
    if str(respostas.get(CAMPO_ISCA) or "").strip():
        return {"message": form.get("success_message") or "Cadastro recebido!", "id": None}

    if settings.privacidade_texto and not respostas.get("_consentimento"):
        raise HTTPException(
            status_code=422,
            detail="É preciso aceitar o aviso de privacidade para enviar o cadastro.",
        )

    valores, extras = {}, {}
    conhecidos = CAMPOS_DO_DESTINO[form["target"]]
    for campo in form.get("fields", []):
        valor = _validar(campo, respostas.get(campo["key"]))
        if campo["key"] in conhecidos:
            valores[campo["key"]] = _para_coluna(campo["key"], valor)
        elif valor != "":
            extras[campo["label"] or campo["key"]] = valor

    criado = await _criar_cadastro(form, valores, extras)

    # Registra o aceite junto da resposta: sem isso não há como demonstrar
    # depois que a pessoa foi informada.
    consentimento = {
        "aceito": bool(respostas.get("_consentimento")),
        "texto": settings.privacidade_texto,
        "em": now_iso(),
    }

    await repo.inserir("form_submissions", {
        "id": str(uuid.uuid4()),
        "form_id": form["id"],
        "form_title": form["title"],
        "target": form["target"],
        "created_record_id": criado["id"],
        "record_name": criado["name"],
        "answers": {**valores, **extras},
        "consentimento": consentimento,
        "ip": ip,
    })
    await repo.incrementar("forms", form["id"], {"submissions_count": 1})

    return {
        "message": form.get("success_message") or "Cadastro recebido! Em breve entramos em contato.",
        "id": criado["id"],
    }
