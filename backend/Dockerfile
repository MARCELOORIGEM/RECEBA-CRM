# API do Miliano CRM.
FROM python:3.12-slim AS base

# Não gera .pyc e não bufferiza a saída: log aparece na hora no docker logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependências antes do código: trocar uma linha de Python não refaz a
# instalação inteira.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Processo sem privilégio: se a aplicação for comprometida, o invasor não
# começa como root dentro do contêiner.
RUN useradd --create-home --uid 10001 miliano && chown -R miliano:miliano /app
USER miliano

EXPOSE 8000

# Dois workers dão conta do volume previsto e mantêm a API de pé enquanto um
# reinicia. Ajuste conforme a CPU da máquina.
#
# A porta vem de $PORT quando a plataforma a injeta (Railway, Render) e cai
# em 8000 no docker compose, que não a define. Com 8000 fixo, um serviço do
# Railway apontado para esta pasta subia "Online" e respondia 502 a tudo: a
# API ouvia numa porta e o roteador do Railway batia em outra. Forma shell
# porque a forma exec não expande variável.
CMD uvicorn server:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-2} \
    --proxy-headers \
    --forwarded-allow-ips '*'
