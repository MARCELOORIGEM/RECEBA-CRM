"""Recebimento de eventos dos marketplaces.

As chaves de API eram decorativas: a tela gerava e revogava, mas nenhuma rota
as aceitava como credencial. Aqui elas passam a valer — é por elas que o iFood,
a Rappi ou a Keeta empurram pedido para dentro do CRM.

A rota não usa sessão: quem chama é um servidor, não uma pessoa. A credencial
vai no cabeçalho `Authorization: Bearer <chave>` e é conferida contra o HASH
guardado no banco (o valor da chave nunca é armazenado).
"""
import hashlib
import uuid
from typing import Annotated, Any, Literal

import asyncpg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import financials, pg, repo
from ..rede import ip_do_cliente
from ..security import now_utc

router = APIRouter(prefix="/integracoes", tags=["entrada de eventos"])

EVENTOS = Literal["pedido.criado", "pedido.aceito", "pedido.entregue", "pedido.cancelado"]

# Como cada evento mapeia para o status interno do pedido.
STATUS_DO_EVENTO = {
    "pedido.criado": "criado",
    "pedido.aceito": "aguardando_coleta",
    "pedido.entregue": "entregue",
    "pedido.cancelado": "cancelado",
}

Texto = Annotated[str, Field(default="", max_length=200, strip_whitespace=True)]


class EventoPedido(BaseModel):
    evento: EVENTOS
    # Id do pedido no sistema de origem. É por ele que o mesmo pedido é
    # reconhecido nas chamadas seguintes.
    referencia: Annotated[str, Field(min_length=1, max_length=120, strip_whitespace=True)]
    restaurante: Texto = ""
    cliente: Texto = ""
    endereco: Texto = ""
    telefone: Texto = ""
    valor: Annotated[float, Field(ge=0, le=1_000_000)] = 0.0
    taxa_entrega: Annotated[float, Field(ge=0, le=100_000)] = 0.0
    distancia_km: Annotated[float, Field(ge=0, le=500)] = 0.0


async def _autenticar(request: Request) -> dict:
    """Confere a chave de API do cabeçalho contra os hashes guardados."""
    cabecalho = request.headers.get("authorization", "")
    if not cabecalho.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Envie a chave em Authorization: Bearer <chave>"
        )

    bruta = cabecalho[7:].strip()
    chave = await repo.um_por(
        "api_keys", "key_hash", hashlib.sha256(bruta.encode("utf-8")).hexdigest()
    )
    if not chave:
        raise HTTPException(status_code=401, detail="Chave de API inválida")

    await repo.atualizar("api_keys", chave["id"], {"last_used": now_utc()})
    return chave


async def _registrar(provider: str, evento: str, codigo: int, ip: str, detalhe: str = "") -> None:
    await repo.inserir("webhook_logs", {
        "id": str(uuid.uuid4()),
        "provider": provider,
        "event": evento,
        "status_code": codigo,
        "detalhe": detalhe,
        "ip": ip,
    })


@router.post("/eventos/{provider}", status_code=202)
async def receber_evento(provider: str, corpo: EventoPedido, request: Request) -> dict[str, Any]:
    """Cria ou atualiza um pedido a partir de um evento do marketplace."""
    chave = await _autenticar(request)
    ip = ip_do_cliente(request)
    provider = provider.lower()[:40]

    # A referência é única POR provedor: dois marketplaces podem usar o mesmo
    # número sem colidir.
    externo = f"{provider}:{corpo.referencia}"
    pedido = await repo.um_por("orders", "external_ref", externo)

    novo_status = STATUS_DO_EVENTO[corpo.evento]

    if not pedido:
        if corpo.evento != "pedido.criado":
            await _registrar(provider, corpo.evento, 404, ip, "referência desconhecida")
            raise HTTPException(
                status_code=404,
                detail=f"Nenhum pedido com a referência {corpo.referencia}. "
                       "Envie 'pedido.criado' antes.",
            )

        restaurante = None
        if corpo.restaurante:
            restaurante = await repo.um_por("restaurants", "name", corpo.restaurante)

        seq = await pg.proximo_numero("order_code")
        novo = {
            "id": str(uuid.uuid4()),
            "code": f"PED-{1000 + seq}",
            "external_ref": externo,
            "origem": provider,
            "restaurant_id": restaurante["id"] if restaurante else "",
            "restaurant_name": corpo.restaurante or (restaurante["name"] if restaurante else ""),
            "customer_name": corpo.cliente or "Cliente",
            "customer_address": corpo.endereco,
            "customer_phone": corpo.telefone,
            "driver_id": "",
            "driver_name": "",
            "amount": corpo.valor,
            "delivery_fee": corpo.taxa_entrega,
            "distance_km": corpo.distancia_km,
            "status": "criado",
            "created_by": f"Integração: {chave['name']}",
        }
        try:
            pedido = await repo.inserir("orders", novo)
        except asyncpg.UniqueViolationError:
            # O marketplace reenvia o evento quando não recebe resposta a
            # tempo, e às vezes os dois envios chegam juntos: os dois passam
            # pela busca acima sem achar nada. O UNIQUE de `external_ref`
            # barra o segundo; ele responde como o primeiro, sem duplicar.
            pedido = await repo.um_por("orders", "external_ref", externo)
            await _registrar(provider, corpo.evento, 202, ip, pedido["code"])
            return {"pedido": pedido["code"], "status": pedido["status"], "criado": False}
        await _registrar(provider, corpo.evento, 202, ip, pedido["code"])
        return {"pedido": pedido["code"], "status": pedido["status"], "criado": True}

    # Pedido já existe: só muda o status, sem reescrever valores já lançados.
    if pedido["status"] != novo_status:
        atual = await repo.atualizar(
            "orders", pedido["id"], {"status": novo_status, "updated_at": now_utc()}
        )
        # O motor financeiro é o mesmo usado pela tela: entrega lança repasse e
        # comissão, reversão estorna.
        if novo_status == "entregue":
            await financials.apply_delivery(atual)
        elif pedido["status"] == "entregue":
            await financials.revert_delivery(pedido)

    await _registrar(provider, corpo.evento, 202, ip, pedido["code"])
    final = await repo.pegar("orders", pedido["id"])
    return {"pedido": final["code"], "status": final["status"], "criado": False}
