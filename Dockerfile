# Imagem única: o painel compilado dentro da API.
#
# É esta a imagem que o Railway (e Render, Fly, qualquer plataforma de um
# serviço só) constrói. O docker-compose.yml continua existindo para quem
# instala numa VPS, com Nginx e Caddy separados — são dois desenhos para dois
# destinos, não um substituindo o outro.
#
# POR QUE UM SERVIÇO SÓ, E NÃO DOIS
#
# Com painel e API em domínios diferentes, o cookie de sessão vira cross-site:
# precisa de SameSite=None, que exige Secure, que exige HTTPS em tudo — e
# quando alguma peça não encaixa, o navegador descarta o cookie em SILÊNCIO.
# O login responde 200, a sessão não gruda, e não há mensagem de erro em lugar
# nenhum. Servindo os dois da mesma origem, essa classe inteira de problema
# deixa de existir: sem CORS, sem SameSite=None, sem terceiro domínio.

# --------------------------------------------------------- etapa 1: painel
FROM node:20-alpine AS painel

WORKDIR /app

COPY frontend/package.json frontend/yarn.lock ./
RUN yarn install --frozen-lockfile --network-timeout 600000

COPY frontend/ ./

# Vazio de propósito: `api.js` usa `REACT_APP_BACKEND_URL || ""`, então a URL
# sai relativa (`/api/...`) e aponta para quem serviu a página. Preencher aqui
# com o domínio quebraria justamente a vantagem da origem única.
ENV REACT_APP_BACKEND_URL=""
# Credenciais de demonstração nunca entram numa imagem de produção.
ENV REACT_APP_SHOW_DEMO_LOGIN=false
# O CRA trata aviso como erro quando CI=true, e um import não usado passa a
# derrubar o deploy. Avisos são para o editor, não para a esteira.
ENV CI=false

RUN yarn build

# ------------------------------------------------------------ etapa 2: API
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependências antes do código: mexer numa linha de Python não refaz a
# instalação inteira.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# O bundle entra como `painel/`, que é onde `app/main.py` procura. Achando,
# a API passa a servir o index e os estáticos; não achando (dev, compose),
# o bloco inteiro é ignorado.
COPY --from=painel /app/build ./painel

# Processo sem privilégio: comprometida a aplicação, o invasor não começa root.
RUN useradd --create-home --uid 10001 miliano && chown -R miliano:miliano /app
USER miliano

EXPOSE 8000

# A porta vem da plataforma. O Railway injeta $PORT e muda o valor entre
# deploys; fixar 8000 faz o healthcheck falhar e o contêiner ser derrubado
# em laço, sem que o log diga o motivo. Forma shell porque `exec form` não
# expande variável.
CMD uvicorn server:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-2} \
    --proxy-headers \
    --forwarded-allow-ips '*'
