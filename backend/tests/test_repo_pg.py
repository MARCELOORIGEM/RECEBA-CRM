"""Testes da camada de dados contra um PostgreSQL de verdade.

Diferente de `test_consulta.py`, que confere o SQL gerado sem banco, estes
executam. É a única forma de pegar o que o construtor não vê: coluna que o
schema não tem, tipo que não converte, COALESCE faltando numa soma vazia.

Pulam quando `DATABASE_URL` não está definida, para que a suíte continue
rodando em máquina sem banco. No CI e com o .env preenchido, rodam.

Cada teste limpa o que criou. Os ids levam o prefixo `zz-teste-` para que, se
algum deixar sujeira, ela seja reconhecível e não se confunda com dado real.
"""
import os
import uuid

import pytest
import pytest_asyncio

from app import pg, repo
from app.consulta import Filtro

pytestmark = [
    pytest.mark.asyncio(loop_scope="module"),
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL não definida — testes de banco pulados",
    ),
]

PREFIXO = "zz-teste-"


def _id() -> str:
    return PREFIXO + uuid.uuid4().hex[:12]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def banco():
    await pg.abrir()
    yield
    # Varre qualquer sobra, mesmo de um teste que falhou no meio.
    for tabela in ("orders", "restaurants", "drivers", "leads", "counters"):
        campo = "name" if tabela == "counters" else "id"
        await pg.executar(f"DELETE FROM {tabela} WHERE {campo} LIKE $1", PREFIXO + "%")
    await pg.fechar()


# ------------------------------------------------------------------ básico
async def test_inserir_devolve_a_linha_gravada(banco):
    """`inserir` devolve a linha em vez de obrigar a reler: a 200 ms de
    distância, cada ida ao banco conta."""
    rid = _id()
    linha = await repo.inserir("restaurants", {"id": rid, "name": "Cantina Teste"})
    assert linha["id"] == rid
    assert linha["name"] == "Cantina Teste"
    # Os DEFAULT do schema vêm aplicados.
    assert linha["commission_rate"] == 15.0
    assert linha["status"] == "ativo"
    assert linha["created_at"] is not None
    await repo.remover("restaurants", rid)


async def test_pegar_e_remover(banco):
    rid = _id()
    await repo.inserir("restaurants", {"id": rid, "name": "Para apagar"})
    assert (await repo.pegar("restaurants", rid))["name"] == "Para apagar"
    assert await repo.remover("restaurants", rid) is True
    assert await repo.pegar("restaurants", rid) is None
    # Remover o que não existe não é erro, mas devolve False.
    assert await repo.remover("restaurants", rid) is False


async def test_get_or_404_levanta_404(banco):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        await repo.get_or_404("orders", "nao-existe", "Pedido")
    assert e.value.status_code == 404
    assert "Pedido" in e.value.detail


async def test_atualizar(banco):
    rid = _id()
    await repo.inserir("restaurants", {"id": rid, "name": "Antes"})
    linha = await repo.atualizar("restaurants", rid, {"name": "Depois", "status": "suspenso"})
    assert (linha["name"], linha["status"]) == ("Depois", "suspenso")
    await repo.remover("restaurants", rid)


async def test_atualizar_sem_campos_nao_gera_sql(banco):
    """Dicionário vazio viraria `SET  WHERE`, que é erro de sintaxe."""
    rid = _id()
    await repo.inserir("restaurants", {"id": rid, "name": "Intacto"})
    assert (await repo.atualizar("restaurants", rid, {}))["name"] == "Intacto"
    await repo.remover("restaurants", rid)


# -------------------------------------------------------------- incremento
async def test_incrementar_soma_no_banco(banco):
    """Era `$inc`. Precisa ser feito pelo banco: ler-somar-gravar perderia um
    lançamento quando dois pedidos são entregues ao mesmo tempo."""
    did = _id()
    await repo.inserir("drivers", {"id": did, "name": "Entregador Teste"})
    await repo.incrementar("drivers", did, {"balance_due": 25.50, "total_deliveries": 1})
    await repo.incrementar("drivers", did, {"balance_due": 10.00, "total_deliveries": 1})
    linha = await repo.pegar("drivers", did)
    assert round(linha["balance_due"], 2) == 35.50
    assert linha["total_deliveries"] == 2
    # Estorno: o mesmo caminho, com valor negativo.
    await repo.incrementar("drivers", did, {"balance_due": -35.50, "total_deliveries": -2})
    linha = await repo.pegar("drivers", did)
    assert round(linha["balance_due"], 2) == 0.0
    assert linha["total_deliveries"] == 0
    await repo.remover("drivers", did)


# ----------------------------------------------------------------- somas
async def test_somar_conjunto_vazio_devolve_zero(banco):
    """SUM de nada é NULL no SQL. Sem COALESCE, viraria "R$ None" na tela."""
    f = Filtro("orders").igual("restaurant_id", "nao-existe-mesmo")
    assert await repo.somar("orders", "amount", f) == 0.0


async def test_somar_e_contar_com_filtro(banco):
    rest = _id()
    for valor in (10.0, 20.0, 30.0):
        await repo.inserir("orders", {
            "id": _id(), "code": _id(), "customer_name": "Cliente",
            "restaurant_id": rest, "amount": valor, "status": "entregue",
        })
    f = Filtro("orders").igual("restaurant_id", rest).igual("status", "entregue")
    assert await repo.somar("orders", "amount", f) == 60.0
    assert await repo.contar("orders", f) == 3

    # Um pedido cancelado não entra na conta.
    await repo.inserir("orders", {
        "id": _id(), "code": _id(), "customer_name": "Cliente",
        "restaurant_id": rest, "amount": 999.0, "status": "cancelado",
    })
    assert await repo.somar("orders", "amount", f) == 60.0

    await repo.remover_onde("orders", Filtro("orders").igual("restaurant_id", rest))


# ------------------------------------------------------------------ busca
async def test_busca_acha_pedaco_de_palavra(banco):
    """O índice TEXT do Mongo casava palavra inteira: "cant" não achava
    "Cantina". Este é o ganho concreto da migração, verificado no banco."""
    rid = _id()
    await repo.inserir("restaurants", {"id": rid, "name": "Cantina da Esquina " + rid})
    f = Filtro("restaurants").busca("antina da Esq", ["name", "cnpj", "contact_person"])
    achados = await repo.listar("restaurants", f)
    assert any(a["id"] == rid for a in achados)
    await repo.remover("restaurants", rid)


async def test_busca_nao_diferencia_maiuscula(banco):
    rid = _id()
    await repo.inserir("restaurants", {"id": rid, "name": "PIZZARIA " + rid})
    f = Filtro("restaurants").busca("pizzaria", ["name"])
    assert any(a["id"] == rid for a in await repo.listar("restaurants", f))
    await repo.remover("restaurants", rid)


async def test_busca_com_pontuacao_nao_quebra(banco):
    """"(11) 9" quebrava a consulta na versão com regex."""
    did = _id()
    await repo.inserir("drivers", {"id": did, "name": "Teste", "phone": "(11) 98888-0000"})
    f = Filtro("drivers").busca("(11) 9", ["phone", "name"])
    assert any(a["id"] == did for a in await repo.listar("drivers", f))
    await repo.remover("drivers", did)


# --------------------------------------------------------------- paginação
async def test_paginar(banco):
    rest = _id()
    for i in range(7):
        await repo.inserir("orders", {
            "id": _id(), "code": f"{rest}-{i}", "customer_name": f"Cliente {i}",
            "restaurant_id": rest, "amount": float(i),
        })
    f = lambda: Filtro("orders").igual("restaurant_id", rest)

    p1 = await repo.paginar("orders", f(), page=1, page_size=3)
    assert (p1["total"], p1["pages"], len(p1["items"])) == (7, 3, 3)

    p3 = await repo.paginar("orders", f(), page=3, page_size=3)
    assert len(p3["items"]) == 1

    # Nenhum item se repete entre as páginas.
    p2 = await repo.paginar("orders", f(), page=2, page_size=3)
    ids = [i["id"] for p in (p1, p2, p3) for i in p["items"]]
    assert len(ids) == len(set(ids)) == 7

    await repo.remover_onde("orders", f())


async def test_paginar_respeita_teto_de_pagina(banco):
    """`page_size` vem da query string: sem teto, um cliente pediria 1 milhão
    de linhas numa requisição."""
    p = await repo.paginar("orders", Filtro("orders").igual("id", "x"), page_size=99999)
    assert p["page_size"] == repo.PAGINA_MAXIMA


# ------------------------------------------------------------------ guarda
async def test_remover_onde_sem_filtro_e_recusado(banco):
    """Um filtro vazio apagaria a tabela inteira."""
    with pytest.raises(ValueError):
        await repo.remover_onde("orders", Filtro("orders"))


async def test_coluna_inexistente_e_recusada_antes_do_banco(banco):
    from app.consulta import ColunaInvalida

    with pytest.raises(ColunaInvalida):
        await repo.inserir("restaurants", {"id": _id(), "nao_existe": 1})


async def test_contador_atomico(banco):
    nome = _id()
    a = await pg.proximo_numero(nome)
    b = await pg.proximo_numero(nome)
    assert b == a + 1
    await pg.executar("DELETE FROM counters WHERE name = $1", nome)
