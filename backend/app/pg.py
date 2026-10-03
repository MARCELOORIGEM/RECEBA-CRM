"""Conexão com o PostgreSQL (Supabase).

Substitui o cliente Motor de `db.py`. Enquanto a migração não termina, os dois
convivem: os routers ainda não traduzidos continuam falando Mongo, e este
módulo não quebra nada por existir.

Três detalhes aqui custam caro quando descobertos em produção:

POOL, NÃO CONEXÃO. Abrir conexão por requisição contra um banco a 200 ms de
distância somaria esse tempo a cada chamada, antes de qualquer consulta. O pool
mantém um punhado aberta e empresta.

PGBOUNCER EM MODO TRANSAÇÃO. O Supabase oferece a porta 6543 com pgbouncer em
modo transação, onde a conexão volta ao pool a cada commit. O asyncpg usa
prepared statements por padrão e eles não sobrevivem a isso: o sintoma é um
`DuplicatePreparedStatementError` intermitente, que aparece sob carga e some
quando você vai investigar. Detectado pela porta, o cache é desligado.

JSONB VOLTA COMO TEXTO. Sem registrar o codec, `fields` e `stage_history`
chegariam como string JSON e o router entregaria texto onde o frontend espera
lista. O codec abaixo resolve no nível da conexão, uma vez.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable

import asyncpg

logger = logging.getLogger("miliano")

DIR_SQL = Path(__file__).resolve().parent / "sql"

_pool: asyncpg.Pool | None = None


def _url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL não definida. É a URI do Supabase, em "
            "Project Settings > Database > Connection string."
        )
    # O Supabase mostra o modelo com [YOUR-PASSWORD]; os colchetes não fazem
    # parte da senha. Mantidos, a autenticação falha reclamando de credencial
    # inválida, sem mencionar colchete — meia hora de depuração no lugar errado.
    if "[" in url.split("@")[0]:
        raise RuntimeError(
            "DATABASE_URL tem colchetes na senha. Eles vêm do modelo "
            "[YOUR-PASSWORD] do Supabase e precisam ser removidos."
        )
    return url


async def _preparar(con: asyncpg.Connection) -> None:
    """Codecs aplicados a cada conexão nova do pool."""
    # Sem isto, jsonb chega como str e o router devolve texto onde o painel
    # espera lista ou objeto.
    for tipo in ("json", "jsonb"):
        await con.set_type_codec(
            tipo, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )


async def abrir() -> asyncpg.Pool:
    """Cria o pool. Chamado uma vez, no lifespan."""
    global _pool
    if _pool is not None:
        return _pool

    url = _url()
    # Porta 6543 é o pooler em modo transação: prepared statement não sobrevive
    # ao retorno da conexão ao pool entre uma requisição e outra.
    modo_transacao = ":6543" in url
    _pool = await asyncpg.create_pool(
        url,
        min_size=int(os.environ.get("PG_POOL_MIN", "1")),
        max_size=int(os.environ.get("PG_POOL_MAX", "10")),
        # Conexão parada é derrubada pelo Supabase; reciclar antes evita o
        # primeiro uso do dia falhar com "connection was closed".
        max_inactive_connection_lifetime=300.0,
        command_timeout=30.0,
        init=_preparar,
        statement_cache_size=0 if modo_transacao else 100,
    )
    logger.info(
        "PostgreSQL conectado (pooler em modo %s)",
        "transação, cache de statements desligado" if modo_transacao else "sessão",
    )
    return _pool


async def fechar() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("O pool não foi aberto. `abrir()` roda no lifespan.")
    return _pool


# ------------------------------------------------------------- consultas
def _dict(registro: asyncpg.Record | None) -> dict | None:
    return dict(registro) if registro is not None else None


async def um(sql: str, *args) -> dict | None:
    """Primeira linha, como dicionário, ou None."""
    async with pool().acquire() as con:
        return _dict(await con.fetchrow(sql, *args))


async def varios(sql: str, *args) -> list[dict]:
    async with pool().acquire() as con:
        return [dict(r) for r in await con.fetch(sql, *args)]


async def valor(sql: str, *args) -> Any:
    """Uma única célula — contagens, somas, existência."""
    async with pool().acquire() as con:
        return await con.fetchval(sql, *args)


async def executar(sql: str, *args) -> str:
    async with pool().acquire() as con:
        return await con.execute(sql, *args)


async def proximo_numero(nome: str) -> int:
    """Contador atômico dos códigos de pedido.

    Era `find_one_and_update` com `$inc`, que substituiu um
    `count_documents()+1` — este gerava códigos duplicados quando dois pedidos
    nasciam ao mesmo tempo. O `ON CONFLICT DO UPDATE ... RETURNING` tem a mesma
    garantia: a linha fica travada durante a atualização, e dois pedidos
    simultâneos recebem números diferentes.
    """
    return int(
        await valor(
            """
            INSERT INTO counters (name, value) VALUES ($1, 1)
            ON CONFLICT (name) DO UPDATE SET value = counters.value + 1
            RETURNING value
            """,
            nome,
        )
    )


# --------------------------------------------------------------- schema
async def aplicar_schema() -> None:
    """Roda os arquivos de SQL na ordem, a cada boot.

    Tudo ali é `IF NOT EXISTS` ou idempotente, então rodar de novo não faz
    nada — é o mesmo contrato que `ensure_indexes()` tinha no Mongo. Assim uma
    instalação nova não depende de alguém lembrar de colar o SQL no painel do
    Supabase, e uma tabela acrescentada depois entra sozinha no próximo deploy.
    """
    arquivos = sorted(DIR_SQL.glob("*.sql"))
    if not arquivos:
        raise RuntimeError(f"Nenhum .sql em {DIR_SQL}")

    async with pool().acquire() as con:
        for arquivo in arquivos:
            try:
                await con.execute(arquivo.read_text(encoding="utf-8"))
            except asyncpg.InsufficientPrivilegeError:
                # Supabase com papel restrito: as tabelas já foram criadas pelo
                # SQL Editor e o papel da aplicação não pode alterar schema.
                # Não é motivo para a API não subir.
                logger.warning(
                    "Sem privilégio para aplicar %s — seguindo com o schema "
                    "que já está no banco.", arquivo.name
                )
            else:
                logger.info("schema aplicado: %s", arquivo.name)


async def conferir() -> dict:
    """Diagnóstico do que está do outro lado. Usado no boot e no /api/health."""
    async with pool().acquire() as con:
        return {
            "versao": (await con.fetchval("SHOW server_version")),
            "banco": await con.fetchval("SELECT current_database()"),
            "tabelas": await con.fetchval(
                "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
            ),
            "sem_rls": await con.fetchval(
                "SELECT count(*) FROM pg_tables "
                "WHERE schemaname = 'public' AND NOT rowsecurity"
            ),
        }
