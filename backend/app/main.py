import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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


# --------------------------------------------------------------- o painel
# Em plataforma de um serviço só (Railway, Render, Fly), a própria API serve o
# bundle do React. Isso elimina a classe inteira de problema que dois domínios
# criam: sem CORS, sem SameSite=None, sem cookie que o navegador descarta em
# silêncio — o painel e a API passam a ser a mesma origem.
#
# No docker compose continuam separados, com o Nginx na frente; lá esta pasta
# não existe e o bloco inteiro é ignorado.
PASTA_PAINEL = Path(__file__).resolve().parent.parent / "painel"

if (PASTA_PAINEL / "index.html").is_file():
    # Os arquivos com hash no nome ficam sob /static e podem ir para cache
    # eterno; o StaticFiles cuida de Content-Type e Range.
    if (PASTA_PAINEL / "static").is_dir():
        app.mount(
            "/static", StaticFiles(directory=PASTA_PAINEL / "static"), name="painel-estatico"
        )

    @app.get("/{caminho:path}", include_in_schema=False)
    async def servir_painel(caminho: str):
        """Aplicação de página única: qualquer rota cai no index."""
        # Esta rota é registrada por último, então /api/... já casou antes de
        # chegar aqui. A exceção é um caminho de API que não existe: sem a
        # guarda abaixo ele receberia o index.html com status 200, e o cliente
        # tentaria ler HTML como JSON em vez de ver um 404 honesto.
        if caminho.startswith("api/"):
            raise HTTPException(status_code=404, detail="Rota não encontrada")

        alvo = (PASTA_PAINEL / caminho).resolve()
        # `resolve()` + verificação de prefixo: sem isso, "../../etc/passwd"
        # sairia da pasta do painel.
        dentro = PASTA_PAINEL.resolve() in alvo.parents
        if caminho and dentro and alvo.is_file():
            return FileResponse(alvo)
        return FileResponse(PASTA_PAINEL / "index.html")

    logger.info("Painel servido pela API, a partir de %s", PASTA_PAINEL)
