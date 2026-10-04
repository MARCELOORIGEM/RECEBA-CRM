"""Testes de `scripts/mongo_para_postgres.py`.

A transferência roda uma vez só, num dia que importa — não dá para descobrir
ali que uma data em texto não converte. Os testes de conversão rodam sem
banco; o de ponta a ponta usa um schema temporário no PostgreSQL de
`DATABASE_URL` e o apaga no fim, sem tocar nas tabelas de verdade.
"""
import importlib.util
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

_CAMINHO = Path(__file__).resolve().parents[2] / "scripts/mongo_para_postgres.py"
_spec = importlib.util.spec_from_file_location("mongo_para_postgres", _CAMINHO)
mpp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mpp)

# Recorte das colunas reais, no formato que `colunas_do_destino` devolve.
COL_DRIVERS = {
    "id": {"tipo": "text", "nulo": False},
    "name": {"tipo": "text", "nulo": False},
    "cpf": {"tipo": "text", "nulo": False},
    "status": {"tipo": "text", "nulo": False},
    "rating": {"tipo": "double precision", "nulo": False},
    "extra_fields": {"tipo": "jsonb", "nulo": False},
    "created_at": {"tipo": "timestamp with time zone", "nulo": False},
}


class TestConversao:
    def test_data_iso_em_texto_vira_datetime_com_fuso(self):
        assert mpp._para_datetime("2026-03-01T12:30:00+00:00") == datetime(
            2026, 3, 1, 12, 30, tzinfo=timezone.utc
        )
        # Sem fuso, como o BSON devolve: é UTC.
        assert mpp._para_datetime(datetime(2026, 3, 1, 12)).tzinfo is timezone.utc
        assert mpp._para_datetime("lixo") is None

    def test_vencimento_em_texto_vira_date(self):
        assert mpp._para_date("2026-10-04") == date(2026, 10, 4)

    def test_legado_e_consertado_sem_perder_o_original(self):
        linha, fora = mpp.converter(
            "drivers",
            {"_id": "x", "id": "d1", "name": "Ana", "cpf": "123.456", "status": "voando",
             "rating": 9, "created_at": "2026-01-01T00:00:00+00:00", "campo_velho": 1},
            COL_DRIVERS,
        )
        assert linha["status"] == "offline"
        assert linha["rating"] == 5
        assert linha["cpf"] == ""
        assert linha["extra_fields"] == {"status_original": "voando", "cpf_original": "123.456"}
        assert fora == {"campo_velho"}

    def test_usuario_ganha_o_objectid_como_id(self):
        linha, _ = mpp.converter(
            "users", {"_id": "65f0c0ffee", "name": "A", "email": "a@a", "password_hash": "h"},
            {"id": {"tipo": "text", "nulo": False}, "name": {"tipo": "text", "nulo": False},
             "email": {"tipo": "text", "nulo": False},
             "password_hash": {"tipo": "text", "nulo": False}},
        )
        assert linha["id"] == "65f0c0ffee"

    def test_chave_em_texto_puro_vira_hash(self):
        linha, fora = mpp.converter(
            "api_keys", {"id": "k", "name": "n", "key": "mln_live_abcdef1234567890"},
            {"id": {"tipo": "text", "nulo": False}, "name": {"tipo": "text", "nulo": False},
             "key_hash": {"tipo": "text", "nulo": False},
             "key_preview": {"tipo": "text", "nulo": False}},
        )
        assert len(linha["key_hash"]) == 64
        assert "key" not in linha and "key" not in fora


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL não definida")
def test_transferencia_de_ponta_a_ponta():
    import asyncio

    import asyncpg

    esquema = f"zz_teste_transf_{uuid.uuid4().hex[:8]}"
    fonte = {
        "users": [{"_id": "65f0c0ffee000000000000aa", "name": "Admin", "email": "a@x.test",
                   "password_hash": "h", "role": "admin", "created_at": "2026-01-01T10:00:00"}],
        "restaurants": [{"_id": 1, "id": "r1", "name": "Brito", "category": "Burguer",
                         "commission_rate": -50, "status": "ativo",
                         "created_at": "2026-01-02T10:00:00+00:00"}],
        "orders": [
            {"_id": 2, "id": "o1", "code": "PED-1041", "customer_name": "C", "amount": 50.0,
             "status": "entregue", "restaurant_id": "r1", "external_ref": "",
             "delivered_at": "2026-01-03T10:00:00+00:00", "created_at_dt": "x"},
            {"_id": 3, "id": "o2", "code": "PED-1007", "customer_name": "D", "amount": 10.0,
             "status": "criado", "external_ref": ""},
        ],
        "payments": [
            {"_id": 4, "id": "p1", "creditor": "Brito", "creditor_type": "restaurante",
             "amount": 100.0, "due_date": "2026-02-01", "status": "pago"},
            {"_id": 5, "id": "p2", "creditor": "X", "creditor_type": "restaurante",
             "amount": -3, "due_date": "2026-02-01"},
        ],
        "leads": [{"_id": 6, "id": "l1", "name": "Lead", "stage": "ganho",
                   "stage_history": [{"stage": "novo", "at": "2026-01-01", "by": "x"}],
                   "converted_restaurant_id": None}],
        "forms": [{"_id": 7, "id": "f1", "slug": "s", "title": "F",
                   "fields": [{"key": "name", "label": "Nome"}]}],
        "form_submissions": [
            {"_id": 8, "id": "s1", "form_id": "f1", "answers": {"name": "A"}},
            {"_id": 9, "id": "s2", "form_id": "apagado", "answers": {}},
        ],
        # O segundo contrato tem regra fora do CHECK, que o saneamento não
        # cobre: o lote é recusado pelo banco e refeito linha a linha.
        "contracts": [
            {"_id": 11, "id": "c1", "party_type": "restaurante", "party_name": "Brito",
             "rule_type": "taxa_fixa", "value": 10},
            {"_id": 12, "id": "c2", "party_type": "restaurante", "party_name": "Brito",
             "rule_type": "inventada", "value": 10},
        ],
        "audit_logs": [{"_id": 10, "id": "a1", "action": "criou", "entity": "pedido",
                        "changes": {"status": {"de": None, "para": "criado"}}}],
    }

    async def rodar():
        con = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
        try:
            await con.execute(f'CREATE SCHEMA "{esquema}"')
            # As tabelas vão para o schema temporário; `public` fica no fim só
            # para achar a extensão pg_trgm, que já está instalada lá.
            await con.execute(f'SET search_path TO "{esquema}", public')
            relatorio = await mpp.transferir(con, fonte)
            dados = {
                "pedidos": await con.fetch("SELECT * FROM orders ORDER BY code"),
                "rest": await con.fetchrow("SELECT * FROM restaurants"),
                "pag": await con.fetch("SELECT * FROM payments"),
                "lead": await con.fetchrow("SELECT * FROM leads"),
                "user": await con.fetchrow("SELECT * FROM users"),
                "contratos": await con.fetch("SELECT id FROM contracts"),
                "contador": await con.fetchval(
                    "SELECT value FROM counters WHERE name = 'order_code'"
                ),
            }
            return relatorio, dados
        finally:
            await con.execute(f'DROP SCHEMA IF EXISTS "{esquema}" CASCADE')
            await con.close()

    relatorio, d = asyncio.run(rodar())

    assert [p["code"] for p in d["pedidos"]] == ["PED-1007", "PED-1041"]
    assert d["pedidos"][1]["delivered_at"] == datetime(2026, 1, 3, 10, tzinfo=timezone.utc)
    # "" virou NULL: os dois pedidos sem referência não colidem no UNIQUE.
    assert all(p["external_ref"] is None for p in d["pedidos"])
    assert relatorio["tabelas"]["orders"]["campos_sem_coluna"] == {"created_at_dt": 1}
    # Comissão negativa trazida para dentro da faixa.
    assert d["rest"]["commission_rate"] == 0
    # O pagamento negativo e a resposta órfã foram recusados, não perdidos.
    assert [p["id"] for p in d["pag"]] == ["p1"]
    assert d["pag"][0]["due_date"] == date(2026, 2, 1)
    motivos = {r["linha"].get("id"): r["motivo"] for r in relatorio["recusados"]}
    assert set(motivos) == {"p2", "s2", "c2"}
    assert "CheckViolation" in motivos["c2"]
    assert [c["id"] for c in d["contratos"]] == ["c1"]
    # NULL em coluna NOT NULL caiu no DEFAULT do schema.
    assert d["lead"]["converted_restaurant_id"] == ""
    assert d["user"]["id"] == "65f0c0ffee000000000000aa"
    # O contador fica acima do maior código copiado.
    assert d["contador"] == 41
