#!/usr/bin/env bash
# Agenda backup e vigia no cron do servidor.
#
#   ./scripts/instalar_cron.sh
#
# O guia mandava colar duas linhas no crontab à mão — e o que depende de
# alguém lembrar de colar não acontece. Este script instala as duas entradas,
# é idempotente (rodar de novo não duplica) e mostra o resultado.
#
# Rode NA VPS, com o usuário que sobe o docker compose.
set -euo pipefail

PROJETO="$(cd "$(dirname "$0")/.." && pwd)"
MARCA="# miliano-crm"

if ! command -v crontab >/dev/null 2>&1; then
  echo "ERRO: crontab não está instalado nesta máquina." >&2
  echo "No Debian/Ubuntu: sudo apt install cron" >&2
  exit 1
fi

atual="$(crontab -l 2>/dev/null || true)"
# Tira as entradas antigas desta instalação antes de regravar.
limpo="$(printf '%s\n' "${atual}" | grep -v "${MARCA}" || true)"

novas="$(cat <<CRON
${MARCA} backup diário do banco, às 3h
0 3 * * * cd ${PROJETO} && ./scripts/backup.sh >> ${PROJETO}/backups/backup.log 2>&1
${MARCA} vigia do /api/health, de 5 em 5 minutos
*/5 * * * * cd ${PROJETO} && ./scripts/vigia.sh >> ${PROJETO}/backups/vigia.log 2>&1
CRON
)"

printf '%s\n%s\n' "${limpo}" "${novas}" | sed '/^$/d' | crontab -

echo "Agendado no cron:"
crontab -l | grep -A1 "${MARCA}"
echo
echo "Confira depois da primeira execução:"
echo "  tail -f ${PROJETO}/backups/backup.log"
echo "  tail -f ${PROJETO}/backups/vigia.log"
