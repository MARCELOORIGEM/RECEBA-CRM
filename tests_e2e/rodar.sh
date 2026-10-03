#!/usr/bin/env bash
# Roda todos os roteiros de navegador contra uma instalação já no ar.
#
#   BASE=http://localhost:3000 ./tests_e2e/rodar.sh
#
# BASE é o endereço do PAINEL (não o da API). Os roteiros usam o Chrome que já
# está instalado na máquina, via playwright-core.
set -uo pipefail

cd "$(dirname "$0")"
export BASE="${BASE:-http://localhost:3000}"
mkdir -p shots

falhou=0
for roteiro in [0-9]*.js; do
  echo "######## ${roteiro}"
  if ! node "${roteiro}"; then falhou=1; fi
  echo
done

[ "${falhou}" -eq 0 ] && echo "todos os roteiros passaram" || echo "algum roteiro falhou"
exit "${falhou}"
