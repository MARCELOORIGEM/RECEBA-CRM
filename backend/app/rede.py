"""IP real do cliente.

Atrás de um balanceador, `request.client.host` é o IP do próprio balanceador:
todo mundo chega com o mesmo endereço e os limites por IP passam a valer para o
site inteiro em vez de por pessoa.

`X-Forwarded-For` resolve isso, mas é um cabeçalho que qualquer cliente pode
forjar. Por isso só é lido quando `TRUSTED_PROXY` está ligado — ou seja, quando
quem opera afirma que existe um proxy confiável na frente reescrevendo o
cabeçalho. Ligado sem proxy, um atacante escaparia do limite trocando o valor a
cada requisição.
"""
from fastapi import Request

from .config import settings


def ip_do_cliente(request: Request) -> str:
    direto = request.client.host if request.client else "?"
    if not settings.trusted_proxy:
        return direto

    encaminhado = request.headers.get("x-forwarded-for", "")
    if encaminhado:
        # O proxy anexa à direita; o cliente original é o primeiro da lista.
        primeiro = encaminhado.split(",")[0].strip()
        if primeiro:
            return primeiro

    return request.headers.get("x-real-ip", "").strip() or direto
