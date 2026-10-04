#!/usr/bin/env bash
# Restaura um backup do Miliano CRM.
#
#   ./scripts/restaurar.sh backups/miliano_2026-09-30_0300.dump
#
# SUBSTITUI o conteúdo atual do banco pelo do arquivo. Rode um backup novo
# antes, para poder voltar atrás se restaurar o arquivo errado.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

ARQUIVO="${1:-}"
if [ -z "${ARQUIVO}" ] || [ ! -f "${ARQUIVO}" ]; then
  echo "uso: $0 <arquivo.dump>" >&2
  echo "backups disponíveis:" >&2
  ls -1t backups/miliano_*.dump 2>/dev/null | head -10 >&2 || echo "  nenhum" >&2
  exit 1
fi

echo "Isto vai SUBSTITUIR o banco '${DB_NAME}' pelo conteúdo de ${ARQUIVO}."
read -r -p "Digite RESTAURAR para confirmar: " resposta
[ "${resposta}" = "RESTAURAR" ] || { echo "cancelado"; exit 1; }

# A API segura conexões abertas no banco; parar antes evita que ela grave no
# meio da restauração e que o DROP das tabelas espere por um lock.
docker compose stop api
# Religa a API em qualquer saída, inclusive se a restauração falhar: o banco
# fica como estava (a transação é única) e o sistema volta ao ar.
trap 'docker compose start api' EXIT

# --clean --if-exists apaga cada objeto antes de recriá-lo (o --drop do
# mongorestore). --single-transaction faz tudo ou nada: um arquivo corrompido
# na metade não deixa o banco meio restaurado. --no-owner com --role deixa as
# tabelas com o papel da aplicação como dono — senão ficariam do superusuário
# e a API não conseguiria aplicar o schema no próximo boot.
docker compose exec -T db pg_restore \
  --username "${PG_ROOT_USER}" \
  --dbname "${DB_NAME}" \
  --clean --if-exists \
  --single-transaction \
  --no-owner --role="${PG_APP_USER}" \
  "/backups/$(basename "${ARQUIVO}")"

echo "restauração concluída"
