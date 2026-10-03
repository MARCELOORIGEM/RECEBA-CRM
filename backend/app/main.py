import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, PyMongoError
from starlette.middleware.cors import CORSMiddleware

from . import seed
from .config import settings
from .db import client, ensure_indexes
from .observabilidade import configurar_logs, iniciar_sentry, middleware_requisicao
from .routers import (
    activities,
    auth,
    contracts,
    dashboard,
    drivers,
    entrada,
    forms,
    integrations,
    leads,
    misc,
    orders,
    payments,
    public,
    restaurants,
    senha,
    users,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
configurar_logs()
logger = logging.getLogger("miliano")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # `@app.on_event` está descontinuado no FastAPI; lifespan é o substituto.
    iniciar_sentry()
    await ensure_indexes()
    await seed.run()
    logger.info(
        "API pronta — banco %s, ambiente %s, dados de exemplo %s",
        settings.db_name,
        settings.ambiente,
        "ligados" if settings.seed_demo else "desligados",
    )
    yield
    client.close()


app = FastAPI(
    title="Miliano CRM",
    version="2.0.0",
    description="CRM de operação logística: funil comercial, cadastros, pedidos e financeiro.",
    lifespan=lifespan,
)

api_router = APIRouter(prefix="/api")
for module in (
    auth, restaurants, drivers, contracts, payments, orders,
    leads, activities, dashboard, users, integrations, forms, public,
    entrada, senha, misc,
):
    api_router.include_router(module.router)
app.include_router(api_router)

# Carimba o id da requisição e transforma exceção solta em resposta com código
# rastreável, em vez de um 500 sem identidade.
app.middleware("http")(middleware_requisicao)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Erro de validação em português e em uma frase, no lugar do array cru do
    Pydantic que o frontend exibia como JSON."""
    partes = []
    for err in exc.errors():
        campo = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query"))
        partes.append(f"{campo}: {err.get('msg', 'valor inválido')}" if campo else err.get("msg", ""))
    return JSONResponse(status_code=422, content={"detail": " | ".join(partes) or "Dados inválidos"})


@app.exception_handler(DuplicateKeyError)
async def duplicate_handler(request: Request, exc: DuplicateKeyError):
    return JSONResponse(status_code=409, content={"detail": "Registro duplicado"})


@app.exception_handler(PyMongoError)
async def mongo_handler(request: Request, exc: PyMongoError):
    logger.exception("Falha no banco em %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503, content={"detail": "Banco de dados indisponível. Tente novamente."}
    )
