#!/usr/bin/env bash
# Restaura um backup do Miliano CRM.
#
#   ./scripts/restaurar.sh backups/miliano_2026-09-30_0300.archive.gz
#
# SUBSTITUI o conteúdo atual do banco pelo do arquivo. Rode um backup novo
# antes, para poder voltar atrás se restaurar o arquivo errado.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

ARQUIVO="${1:-}"
if [ -z "${ARQUIVO}" ] || [ ! -f "${ARQUIVO}" ]; then
  echo "uso: $0 <arquivo.archive.gz>" >&2
  echo "backups disponíveis:" >&2
  ls -1t backups/miliano_*.archive.gz 2>/dev/null | head -10 >&2 || echo "  nenhum" >&2
  exit 1
fi

echo "Isto vai SUBSTITUIR o banco '${DB_NAME}' pelo conteúdo de ${ARQUIVO}."
read -r -p "Digite RESTAURAR para confirmar: " resposta
[ "${resposta}" = "RESTAURAR" ] || { echo "cancelado"; exit 1; }

docker compose exec -T mongo mongorestore \
  --username "${MONGO_ROOT_USER}" \
  --password "${MONGO_ROOT_PASSWORD}" \
  --authenticationDatabase admin \
  --archive="/backups/$(basename "${ARQUIVO}")" \
  --gzip \
  --drop

echo "restauração concluída"
