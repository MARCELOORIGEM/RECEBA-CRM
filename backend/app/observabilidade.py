"""Rastro de erro em produção.

Antes, uma exceção virava um traceback solto no log do servidor, sem jeito de
ligar o que o usuário viu ao que aconteceu. Aqui cada requisição ganha um
identificador que vai no log, no cabeçalho da resposta e na mensagem de erro —
quem relata o problema diz o código e o log é achado em um grep.

Sentry é opcional: sem `SENTRY_DSN`, nada é importado nem enviado.
"""
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import settings

logger = logging.getLogger("miliano")

# Disponível para qualquer ponto do código durante a requisição.
id_requisicao: ContextVar[str] = ContextVar("id_requisicao", default="-")


class FiltroIdRequisicao(logging.Filter):
    """Carimba o id em toda linha de log emitida durante a requisição."""

    def filter(self, record):
        record.req = id_requisicao.get()
        return True


def configurar_logs() -> None:
    formato = "%(asctime)s %(levelname)s [%(req)s] %(name)s %(message)s"
    raiz = logging.getLogger()
    for handler in raiz.handlers:
        handler.setFormatter(logging.Formatter(formato))
        handler.addFilter(FiltroIdRequisicao())


def iniciar_sentry() -> bool:
    """Liga o Sentry se houver DSN e o pacote estiver instalado."""
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN definido, mas o pacote sentry-sdk não está instalado.")
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.ambiente,
        # Dado de pagamento não pode sair da casa nem dentro de um relatório
        # de erro.
        send_default_pii=False,
        traces_sample_rate=0.0,
    )
    logger.info("Sentry ligado (ambiente %s)", settings.ambiente)
    return True


async def middleware_requisicao(request: Request, call_next):
    """Identifica a requisição, mede a duração e registra o que falhou."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    id_requisicao.set(rid)
    comeco = time.perf_counter()

    try:
        resposta = await call_next(request)
    except Exception:
        ms = (time.perf_counter() - comeco) * 1000
        # `exception` leva o traceback junto; o id liga este log ao que o
        # usuário viu na tela.
        logger.exception(
            "Falha não tratada em %s %s (%.0f ms)", request.method, request.url.path, ms
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": (
                    "Erro inesperado. Se precisar de suporte, informe o código "
                    f"{rid}."
                ),
                "request_id": rid,
            },
            headers={"X-Request-ID": rid},
        )

    ms = (time.perf_counter() - comeco) * 1000
    if resposta.status_code >= 500:
        logger.error("%s %s -> %s (%.0f ms)", request.method, request.url.path, resposta.status_code, ms)
    elif ms > 1500:
        # Lento o bastante para alguém reclamar.
        logger.warning("%s %s demorou %.0f ms", request.method, request.url.path, ms)

    resposta.headers["X-Request-ID"] = rid
    return resposta
