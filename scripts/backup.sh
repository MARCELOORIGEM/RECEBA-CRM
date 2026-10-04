#!/usr/bin/env bash
# Backup do banco do Miliano CRM.
#
#   ./scripts/backup.sh
#
# Guarda um dump comprimido em ./backups e apaga os mais velhos que
# RETENCAO_DIAS. Pensado para rodar no cron:
#
#   0 3 * * *  cd /caminho/do/projeto && ./scripts/backup.sh >> backups/backup.log 2>&1
#
# O dump sai com CPF e dados bancários dentro. Trate o arquivo como o próprio
# banco: acesso restrito e, de preferência, cópia num destino fora da máquina.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

RETENCAO_DIAS="${RETENCAO_DIAS:-14}"
CARIMBO="$(date +%Y-%m-%d_%H%M)"
ARQUIVO="miliano_${CARIMBO}.dump"

echo "[$(date '+%F %T')] iniciando backup de ${DB_NAME}"

# Formato custom (-Fc): já sai comprimido, e o pg_restore consegue restaurar
# tabela a tabela ou listar o conteúdo sem restaurar nada. `--no-owner` deixa
# o arquivo restaurável num servidor onde o papel da aplicação tem outro nome.
docker compose exec -T db pg_dump \
  --username "${PG_ROOT_USER}" \
  --dbname "${DB_NAME}" \
  --format=custom \
  --no-owner \
  --file="/backups/${ARQUIVO}"

TAMANHO="$(du -h "backups/${ARQUIVO}" | cut -f1)"
echo "[$(date '+%F %T')] backup concluído: backups/${ARQUIVO} (${TAMANHO})"

# Um backup que nunca foi restaurado não é um backup. Confere se o arquivo é
# legível antes de dar o serviço por feito.
if ! docker compose exec -T db pg_restore --list "/backups/${ARQUIVO}" >/dev/null 2>&1; then
  echo "[$(date '+%F %T')] ERRO: o arquivo gerado está corrompido" >&2
  exit 1
fi

# Cópia para fora da máquina. Um backup guardado no mesmo disco do banco não
# sobrevive ao que mais importa: a perda do servidor. Falhar aqui NÃO invalida
# o backup local, mas grita no log — é o tipo de erro que passa meses sem
# ninguém ver e só aparece no dia em que o backup é necessário.
DESTINO_REMOTO="${DESTINO_REMOTO:-}"
if [ -n "${DESTINO_REMOTO}" ]; then
  echo "[$(date '+%F %T')] enviando cópia para ${DESTINO_REMOTO}"
  if command -v rclone >/dev/null 2>&1 && printf '%s' "${DESTINO_REMOTO}" | grep -q ':'  && ! printf '%s' "${DESTINO_REMOTO}" | grep -q '@'; then
    # Destino no formato "remoto:caminho" — é do rclone (bucket, Drive, S3).
    rclone copy "backups/${ARQUIVO}" "${DESTINO_REMOTO}"       || echo "[$(date '+%F %T')] ERRO: a cópia remota falhou (o backup local está íntegro)" >&2
  elif command -v rsync >/dev/null 2>&1; then
    rsync -a "backups/${ARQUIVO}" "${DESTINO_REMOTO}"       || echo "[$(date '+%F %T')] ERRO: a cópia remota falhou (o backup local está íntegro)" >&2
  else
    echo "[$(date '+%F %T')] ERRO: DESTINO_REMOTO definido, mas nem rclone nem rsync estão instalados" >&2
  fi
else
  echo "[$(date '+%F %T')] AVISO: DESTINO_REMOTO vazio — só existe cópia local, no mesmo disco do banco" >&2
fi

APAGADOS="$(find backups -name 'miliano_*.dump' -mtime "+${RETENCAO_DIAS}" -print -delete | wc -l)"
[ "${APAGADOS}" -gt 0 ] && echo "[$(date '+%F %T')] ${APAGADOS} backup(s) antigo(s) removido(s)"
exit 0
