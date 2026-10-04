#!/bin/sh
# Cria o papel da APLICAÇÃO na primeira subida do banco.
#
# O superusuário (POSTGRES_USER) serve para administrar; a API não deve usá-lo.
# Este papel é dono só do banco do CRM: cria as próprias tabelas no boot (o
# schema é aplicado pela API, de forma idempotente) e não enxerga mais nada —
# se a credencial da API vazar, o estrago fica contido a esse banco.
#
# Roda uma única vez, quando o volume de dados está vazio.
set -eu

if [ -z "${APP_USER:-}" ] || [ -z "${APP_PASSWORD:-}" ]; then
  echo "APP_USER/APP_PASSWORD ausentes — papel da aplicação não foi criado."
  exit 0
fi

# Nome e senha entram como variáveis do psql (:"usuario" e :'senha'), que o
# próprio psql cita: uma senha com aspas não quebra — nem injeta — o SQL.
psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v usuario="$APP_USER" -v senha="$APP_PASSWORD" -v banco="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"usuario" LOGIN PASSWORD :'senha';
ALTER DATABASE :"banco" OWNER TO :"usuario";
-- Desde o PostgreSQL 15, ninguém além do dono cria tabela no schema public.
ALTER SCHEMA public OWNER TO :"usuario";
SQL

echo "Papel '$APP_USER' criado como dono do banco '$POSTGRES_DB'."
