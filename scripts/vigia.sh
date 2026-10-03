#!/usr/bin/env bash
# Vigia externo do Miliano CRM.
#
#   ./scripts/vigia.sh
#
# O healthcheck do docker compose só reinicia contêiner: ele não avisa
# ninguém. Se a API cair às 2h da manhã, sem isto você descobre pela
# reclamação da equipe às 8h.
#
# Consulta /api/health e, quando a resposta não for saudável N vezes seguidas,
# dispara um webhook (Slack, Discord, Teams, ou qualquer URL que aceite POST
# com JSON). Pensado para o cron, de 5 em 5 minutos:
#
#   */5 * * * *  cd /caminho/do/projeto && ./scripts/vigia.sh >> backups/vigia.log 2>&1
#
# Configure WEBHOOK_ALERTA no .env. Vazio, o script só registra no log.
set -uo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

ALVO="${URL_HEALTH:-http://127.0.0.1:${PORTA_HTTP:-8080}/api/health}"
WEBHOOK="${WEBHOOK_ALERTA:-}"
# Quantas falhas seguidas antes de avisar. Uma só costuma ser reinício ou
# rede piscando; avisar nela treina a equipe a ignorar o alerta.
FALHAS_PARA_ALERTAR="${FALHAS_PARA_ALERTAR:-2}"
ESTADO="backups/.vigia_falhas"
AGORA="$(date '+%F %T')"

resposta="$(curl -fsS --max-time 10 "${ALVO}" 2>/dev/null || true)"

if printf '%s' "${resposta}" | grep -q '"database":"up"'; then
  # Voltou ao normal depois de ter alertado? Avisa também — senão ninguém
  # sabe se o problema passou.
  if [ -f "${ESTADO}" ] && [ "$(cat "${ESTADO}")" -ge "${FALHAS_PARA_ALERTAR}" ]; then
    echo "[${AGORA}] RECUPERADO: ${ALVO} respondendo de novo"
    [ -n "${WEBHOOK}" ] && curl -fsS --max-time 10 -X POST "${WEBHOOK}" \
      -H 'Content-Type: application/json' \
      -d "{\"text\":\"✅ Miliano CRM voltou ao ar (${ALVO})\"}" >/dev/null 2>&1
  fi
  rm -f "${ESTADO}"
  exit 0
fi

mkdir -p backups
falhas=$(( $( [ -f "${ESTADO}" ] && cat "${ESTADO}" || echo 0 ) + 1 ))
echo "${falhas}" > "${ESTADO}"
echo "[${AGORA}] FALHA ${falhas}: ${ALVO} não respondeu saudável"

if [ "${falhas}" -eq "${FALHAS_PARA_ALERTAR}" ]; then
  if [ -n "${WEBHOOK}" ]; then
    curl -fsS --max-time 10 -X POST "${WEBHOOK}" \
      -H 'Content-Type: application/json' \
      -d "{\"text\":\"🔴 Miliano CRM fora do ar: ${ALVO} falhou ${falhas}x seguidas em ${AGORA}\"}" \
      >/dev/null 2>&1 || echo "[${AGORA}] ERRO: o webhook de alerta também falhou" >&2
  else
    echo "[${AGORA}] AVISO: WEBHOOK_ALERTA vazio — ninguém foi notificado" >&2
  fi
fi
# Só alerta uma vez por incidente: repetir a cada 5 min vira ruído e a equipe
# silencia o canal, que é o pior desfecho possível.
exit 1
