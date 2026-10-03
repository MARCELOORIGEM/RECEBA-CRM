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
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
