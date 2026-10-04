"""Núcleo da API: autenticação, cadastros, pedidos, financeiro e painel."""
import uuid

import pytest

from .conftest import ADMIN, API, MANAGER, TIMEOUT


# --------------------------------------------------------------- autenticação
class TestAuth:
    def test_login_admin(self, admin):
        assert admin.me["role"] == "admin"
        assert admin.me["email"] == ADMIN["email"]

    def test_login_gestor(self, manager):
        assert manager.me["role"] == "manager"

    def test_senha_errada(self):
        import requests

        r = requests.post(
            f"{API}/auth/login",
            json={"email": ADMIN["email"], "password": "senha-errada"},
            timeout=TIMEOUT,
        )
        assert r.status_code in (401, 429)

    def test_sem_token(self):
        import requests

        assert requests.get(f"{API}/restaurants", timeout=TIMEOUT).status_code == 401

    def test_me(self, admin):
        r = admin.get(f"{API}/auth/me", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "password_hash" not in r.json()

    def test_cadastro_publico_bloqueado(self):
        """Regressão: o endpoint era aberto e aceitava `role` do corpo, o que
        deixava qualquer um criar uma conta de administrador."""
        import requests

        r = requests.post(
            f"{API}/auth/register",
            json={
                "name": "Invasor",
                "email": "invasor-teste@exemplo.com",
                "password": "senhaforte123",
                "role": "admin",
            },
            timeout=TIMEOUT,
        )
        assert r.status_code == 403


# ------------------------------------------------------------------ validação
class TestValidacao:
    @pytest.mark.parametrize(
        "payload",
        [
            {"name": "X", "category": "Y", "commission_rate": -50},
            {"name": "X", "category": "Y", "commission_rate": 150},
            {"name": "X", "category": "Y", "status": "status_inexistente"},
            {"name": "", "category": "Y"},
        ],
    )
    def test_restaurante_invalido(self, admin, payload):
        r = admin.post(f"{API}/restaurants", json=payload, timeout=TIMEOUT)
        assert r.status_code == 422, f"aceitou {payload}: {r.text}"

    @pytest.mark.parametrize(
        "payload",
        [
            {"creditor": "X", "creditor_type": "extraterrestre", "amount": 10, "due_date": "2026-01-01"},
            {"creditor": "X", "creditor_type": "entregador", "amount": -999, "due_date": "2026-01-01"},
            {"creditor": "X", "creditor_type": "entregador", "amount": 10, "due_date": "nao-e-data"},
        ],
    )
    def test_pagamento_invalido(self, admin, payload):
        assert admin.post(f"{API}/payments", json=payload, timeout=TIMEOUT).status_code == 422

    def test_webhook_url_invalida(self, admin):
        r = admin.post(
            f"{API}/integrations/webhooks",
            json={"provider": "x", "url": "javascript:alert(1)"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422

    def test_mensagem_de_erro_e_texto(self, admin):
        """O frontend exibe `detail` direto; um array do Pydantic aparecia como JSON cru."""
        r = admin.post(f"{API}/restaurants", json={"name": "X"}, timeout=TIMEOUT)
        assert r.status_code == 422
        assert isinstance(r.json()["detail"], str)


# --------------------------------------------------------- recursos ausentes
class TestNaoEncontrado:
    @pytest.mark.parametrize(
        "metodo,rota,corpo",
        [
            ("get", "/restaurants/nao-existe", None),
            ("put", "/restaurants/nao-existe", {"name": "x", "category": "y"}),
            ("delete", "/restaurants/nao-existe", None),
            ("get", "/drivers/nao-existe", None),
            ("get", "/orders/nao-existe", None),
            ("post", "/payments/nao-existe/settle", None),
            ("get", "/leads/nao-existe", None),
        ],
    )
    def test_404(self, admin, metodo, rota, corpo):
        """Regressão: todas essas rotas devolviam 200 para ids inexistentes."""
        r = getattr(admin, metodo)(f"{API}{rota}", json=corpo, timeout=TIMEOUT)
        assert r.status_code == 404, f"{metodo.upper()} {rota} -> {r.status_code}"


# ------------------------------------------------------------------- permissões
class TestPermissoes:
    @pytest.mark.parametrize(
        "rota", ["/restaurants/qualquer", "/drivers/qualquer", "/contracts/qualquer"]
    )
    def test_gestor_nao_exclui(self, manager, rota):
        assert manager.delete(f"{API}{rota}", timeout=TIMEOUT).status_code == 403

    def test_gestor_nao_lista_usuarios(self, manager):
        assert manager.get(f"{API}/users", timeout=TIMEOUT).status_code == 403

    def test_gestor_nao_gera_chave(self, manager):
        r = manager.post(
            f"{API}/integrations/keys",
            json={"name": "hack", "environment": "production"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 403

    def test_gestor_nao_ve_auditoria(self, manager):
        assert manager.get(f"{API}/audit", timeout=TIMEOUT).status_code == 403

    def test_gestor_cadastra_e_edita(self, manager, admin, nome_unico):
        r = manager.post(
            f"{API}/restaurants",
            json={"name": nome_unico("Gestor Rest"), "category": "Teste"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 201
        rid = r.json()["id"]
        try:
            atual = manager.put(
                f"{API}/restaurants/{rid}",
                json={"name": nome_unico("Renomeado"), "category": "Teste"},
                timeout=TIMEOUT,
            )
            assert atual.status_code == 200
        finally:
            # O gestor não pode excluir — a limpeza sai pelo admin.
            admin.delete(f"{API}/restaurants/{rid}", timeout=TIMEOUT)


# ---------------------------------------------------------------- listagens
class TestListagens:
    @pytest.mark.parametrize(
        "rota", ["/restaurants", "/drivers", "/orders", "/contracts", "/payments", "/leads"]
    )
    def test_formato_paginado(self, admin, rota):
        r = admin.get(f"{API}{rota}", params={"page_size": 5}, timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert {"items", "total", "page", "pages", "page_size"} <= set(body)
        assert len(body["items"]) <= 5
        assert all("_id" not in item for item in body["items"])

    def test_busca_servidor(self, admin, restaurante):
        r = admin.get(
            f"{API}/restaurants", params={"search": restaurante["name"][:12]}, timeout=TIMEOUT
        )
        assert r.status_code == 200
        assert any(x["id"] == restaurante["id"] for x in r.json()["items"])

    def test_busca_com_caractere_especial(self, admin):
        """Um termo como '(11) 9' quebraria a query se o regex não fosse escapado."""
        r = admin.get(f"{API}/restaurants", params={"search": "(11) 9["}, timeout=TIMEOUT)
        assert r.status_code == 200

    def test_filtro_status(self, admin):
        r = admin.get(f"{API}/restaurants", params={"status": "ativo"}, timeout=TIMEOUT)
        assert all(x["status"] == "ativo" for x in r.json()["items"])


# ------------------------------------------------------------------- cadastros
class TestCadastros:
    def test_ciclo_restaurante(self, admin, nome_unico):
        nome = nome_unico("Ciclo")
        criado = admin.post(
            f"{API}/restaurants", json={"name": nome, "category": "Teste"}, timeout=TIMEOUT
        ).json()
        assert criado["commission_due"] == 0

        lido = admin.get(f"{API}/restaurants/{criado['id']}", timeout=TIMEOUT)
        assert lido.status_code == 200

        novo_nome = f"{nome} editado"
        editado = admin.put(
            f"{API}/restaurants/{criado['id']}",
            json={"name": novo_nome, "category": "Outra"},
            timeout=TIMEOUT,
        ).json()
        assert editado["name"] == novo_nome

        assert admin.delete(f"{API}/restaurants/{criado['id']}", timeout=TIMEOUT).status_code == 200
        assert admin.get(f"{API}/restaurants/{criado['id']}", timeout=TIMEOUT).status_code == 404

    def test_cnpj_duplicado(self, admin, nome_unico):
        # CNPJ sorteado a cada rodada: com um valor fixo, qualquer cadastro
        # sobrevivente de uma rodada anterior fazia esta falhar logo no
        # primeiro POST, por um 409 que não é o que o teste investiga.
        cnpj = f"11.222.{uuid.uuid4().int % 1000:03d}/0001-44"
        base = {"category": "Teste", "cnpj": cnpj}
        a = admin.post(f"{API}/restaurants", json={**base, "name": nome_unico("A")}, timeout=TIMEOUT)
        assert a.status_code == 201
        b = admin.post(f"{API}/restaurants", json={**base, "name": nome_unico("B")}, timeout=TIMEOUT)
        assert b.status_code == 409
        admin.delete(f"{API}/restaurants/{a.json()['id']}", timeout=TIMEOUT)

    def test_renomear_propaga_para_pedidos(self, admin, restaurante, entregador):
        """Regressão: o vínculo era só pelo nome em texto, então renomear o
        cadastro deixava o histórico apontando para um nome inexistente."""
        pedido = admin.post(
            f"{API}/orders",
            json={
                "restaurant_id": restaurante["id"],
                "restaurant_name": restaurante["name"],
                "customer_name": "Cliente",
                "amount": 50,
            },
            timeout=TIMEOUT,
        ).json()

        novo = f"{restaurante['name']} REBATIZADO"
        admin.put(
            f"{API}/restaurants/{restaurante['id']}",
            json={"name": novo, "category": "Teste"},
            timeout=TIMEOUT,
        )
        atualizado = admin.get(f"{API}/orders/{pedido['id']}", timeout=TIMEOUT).json()
        assert atualizado["restaurant_name"] == novo
        admin.delete(f"{API}/orders/{pedido['id']}", timeout=TIMEOUT)

    def test_status_entregador_por_endpoint_dedicado(self, admin, entregador):
        r = admin.patch(
            f"{API}/drivers/{entregador['id']}/status", json={"status": "em_entrega"}, timeout=TIMEOUT
        )
        assert r.status_code == 200
        assert r.json()["status"] == "em_entrega"

    def test_status_entregador_invalido(self, admin, entregador):
        r = admin.patch(
            f"{API}/drivers/{entregador['id']}/status", json={"status": "voando"}, timeout=TIMEOUT
        )
        assert r.status_code == 422


# --------------------------------------------------------------------- pedidos
class TestPedidos:
    def _pedido(self, admin, restaurante, **extra):
        corpo = {
            "restaurant_id": restaurante["id"],
            "restaurant_name": restaurante["name"],
            "customer_name": "Cliente Teste",
            "customer_address": "Rua Teste, 1",
            "amount": 100.0,
            "delivery_fee": 10.0,
            "distance_km": 5.0,
            **extra,
        }
        r = admin.post(f"{API}/orders", json=corpo, timeout=TIMEOUT)
        assert r.status_code == 201, r.text
        return r.json()

    def test_codigo_unico_e_sequencial(self, admin, restaurante):
        """Regressão: o código vinha de count_documents()+1, que repetia o
        número quando dois pedidos nasciam ao mesmo tempo."""
        pedidos = [self._pedido(admin, restaurante) for _ in range(5)]
        try:
            codigos = {p["code"] for p in pedidos}
            assert len(codigos) == 5
            for c in codigos:
                assert c.startswith("PED-")
        finally:
            for p in pedidos:
                admin.delete(f"{API}/orders/{p['id']}", timeout=TIMEOUT)

    def test_fluxo_de_status(self, admin, restaurante, entregador):
        pedido = self._pedido(admin, restaurante)
        pular = admin.patch(
            f"{API}/orders/{pedido['id']}/status", json={"status": "entregue"}, timeout=TIMEOUT
        )
        assert pular.status_code == 409, "pular etapas deveria ser recusado"

        for etapa in ("aguardando_coleta", "em_transito"):
            r = admin.patch(
                f"{API}/orders/{pedido['id']}/status", json={"status": etapa}, timeout=TIMEOUT
            )
            assert r.status_code == 200, r.text

        sem_entregador = admin.patch(
            f"{API}/orders/{pedido['id']}/status", json={"status": "entregue"}, timeout=TIMEOUT
        )
        assert sem_entregador.status_code == 409

        admin.patch(
            f"{API}/orders/{pedido['id']}/assign",
            json={"driver_id": entregador["id"]},
            timeout=TIMEOUT,
        )
        entregue = admin.patch(
            f"{API}/orders/{pedido['id']}/status", json={"status": "entregue"}, timeout=TIMEOUT
        )
        assert entregue.status_code == 200
        admin.delete(f"{API}/orders/{pedido['id']}", timeout=TIMEOUT)

    def test_entrega_move_saldo_e_contadores(self, admin, restaurante, entregador):
        """Regressão: entregar um pedido não mexia em nada — `total_deliveries`
        e `balance_due` eram números fixos do seed."""
        contrato = admin.post(
            f"{API}/contracts",
            json={
                "party_type": "entregador",
                "party_id": entregador["id"],
                "party_name": entregador["name"],
                "rule_type": "valor_km",
                "value": 2.0,
            },
            timeout=TIMEOUT,
        ).json()
        pedido = self._pedido(admin, restaurante, driver_id=entregador["id"])
        for etapa in ("aguardando_coleta", "em_transito", "entregue"):
            admin.patch(f"{API}/orders/{pedido['id']}/status", json={"status": etapa}, timeout=TIMEOUT)

        final = admin.get(f"{API}/orders/{pedido['id']}", timeout=TIMEOUT).json()
        assert final["driver_earning"] == 10.0, "5 km x R$ 2,00"
        assert final["platform_commission"] == 10.0, "10% de R$ 100,00"

        d = admin.get(f"{API}/drivers/{entregador['id']}", timeout=TIMEOUT).json()
        assert d["total_deliveries"] == 1
        assert d["balance_due"] == 10.0

        r = admin.get(f"{API}/restaurants/{restaurante['id']}", timeout=TIMEOUT).json()
        assert r["orders_total"] == 1
        assert r["commission_due"] == 10.0

        # Reverter devolve tudo ao lugar.
        admin.patch(f"{API}/orders/{pedido['id']}/status", json={"status": "em_transito"}, timeout=TIMEOUT)
        d2 = admin.get(f"{API}/drivers/{entregador['id']}", timeout=TIMEOUT).json()
        assert d2["balance_due"] == 0.0
        assert d2["total_deliveries"] == 0
        admin.delete(f"{API}/orders/{pedido['id']}", timeout=TIMEOUT)
        admin.delete(f"{API}/contracts/{contrato['id']}", timeout=TIMEOUT)

    def test_nao_troca_entregador_de_pedido_finalizado(self, admin, restaurante, entregador):
        pedido = self._pedido(admin, restaurante)
        admin.patch(f"{API}/orders/{pedido['id']}/status", json={"status": "cancelado"}, timeout=TIMEOUT)
        r = admin.patch(
            f"{API}/orders/{pedido['id']}/assign",
            json={"driver_id": entregador["id"]},
            timeout=TIMEOUT,
        )
        assert r.status_code == 409
        admin.delete(f"{API}/orders/{pedido['id']}", timeout=TIMEOUT)


# ------------------------------------------------------------------ financeiro
class TestFinanceiro:
    def test_liquidar_baixa_saldo_do_credor(self, admin, entregador):
        """Regressão: marcar o repasse como pago não mexia no saldo devido."""
        pagamento = admin.post(
            f"{API}/payments",
            json={
                "creditor": entregador["name"],
                "creditor_id": entregador["id"],
                "creditor_type": "entregador",
                "amount": 50.0,
                "due_date": "2026-12-31",
            },
            timeout=TIMEOUT,
        )
        assert pagamento.status_code == 201
        pid = pagamento.json()["id"]

        liquidado = admin.post(f"{API}/payments/{pid}/settle", timeout=TIMEOUT)
        assert liquidado.status_code == 200
        assert liquidado.json()["status"] == "pago"

        d = admin.get(f"{API}/drivers/{entregador['id']}", timeout=TIMEOUT).json()
        assert d["paid_total"] == 50.0

        assert admin.post(f"{API}/payments/{pid}/settle", timeout=TIMEOUT).status_code == 409
        assert admin.delete(f"{API}/payments/{pid}", timeout=TIMEOUT).status_code == 409

        estorno = admin.post(f"{API}/payments/{pid}/reopen", timeout=TIMEOUT)
        assert estorno.status_code == 200
        assert estorno.json()["status"] == "pendente"
        admin.delete(f"{API}/payments/{pid}", timeout=TIMEOUT)

    def test_totais_vem_do_servidor(self, admin):
        body = admin.get(f"{API}/payments", timeout=TIMEOUT).json()
        assert "totals" in body
        assert set(body["totals"]) >= {"pendente", "pago", "atrasado", "geral"}
        assert all(v >= 0 for v in body["totals"].values())

    def test_contrato_ativo_unico_por_parte(self, admin, entregador):
        base = {
            "party_type": "entregador",
            "party_id": entregador["id"],
            "party_name": entregador["name"],
            "rule_type": "taxa_fixa",
            "value": 100,
        }
        primeiro = admin.post(f"{API}/contracts", json=base, timeout=TIMEOUT)
        assert primeiro.status_code == 201
        assert admin.post(f"{API}/contracts", json=base, timeout=TIMEOUT).status_code == 409
        admin.delete(f"{API}/contracts/{primeiro.json()['id']}", timeout=TIMEOUT)

    def test_comissao_acima_de_100(self, admin, entregador):
        r = admin.post(
            f"{API}/contracts",
            json={
                "party_type": "entregador",
                "party_name": entregador["name"],
                "rule_type": "comissao_entrega",
                "value": 250,
            },
            timeout=TIMEOUT,
        )
        assert r.status_code == 422


# --------------------------------------------------------------------- painel
class TestDashboard:
    def test_estrutura(self, admin):
        d = admin.get(f"{API}/dashboard/stats", timeout=TIMEOUT).json()
        assert {"kpi", "financeiro", "funil", "agenda", "trend", "hourly"} <= set(d)
        assert len(d["trend"]) == 14

    def test_taxa_de_sucesso_e_percentual_valido(self, admin):
        """Regressão: a taxa dividia entregues pelo total de pedidos, então caía
        sozinha a cada pedido novo ainda em rota."""
        kpi = admin.get(f"{API}/dashboard/stats", timeout=TIMEOUT).json()["kpi"]
        assert 0 <= kpi["taxa_sucesso"] <= 100

    def test_entregas_hoje_nao_e_a_base_inteira(self, admin):
        """Regressão: `entregas_hoje` contava todos os pedidos já registrados."""
        d = admin.get(f"{API}/dashboard/stats", timeout=TIMEOUT).json()
        total_base = admin.get(f"{API}/orders", params={"page_size": 1}, timeout=TIMEOUT).json()["total"]
        assert d["kpi"]["entregas_hoje"] <= total_base

    def test_financeiro_sem_valores_negativos(self, admin):
        f = admin.get(f"{API}/dashboard/stats", timeout=TIMEOUT).json()["financeiro"]
        for campo in ("gmv_mes", "receita_mes", "repasse_pendente", "ticket_medio"):
            assert f[campo] >= 0, f"{campo} negativo: {f[campo]}"


def test_health_sem_autenticacao():
    import requests

    r = requests.get(f"{API}/health", timeout=TIMEOUT)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


class TestEstorno:
    """Regressão: `apply_delivery` creditava o entregador achado pelo nome quando
    o pedido não tinha `driver_id`, mas `revert_delivery` só debitava quando o id
    existia. Todo pedido migrado sem id inflava o saldo de forma permanente."""

    def test_estorno_devolve_mesmo_sem_id_no_pedido(self, admin, restaurante, entregador):
        import asyncio
        import os

        import asyncpg

        if not os.environ.get("DATABASE_URL"):
            pytest.skip("DATABASE_URL não definida — o teste precisa mexer no banco direto")

        pedido = admin.post(
            f"{API}/orders",
            json={
                "restaurant_id": restaurante["id"],
                "restaurant_name": restaurante["name"],
                "customer_name": "Cliente",
                "amount": 100.0,
                "delivery_fee": 20.0,
                "driver_id": entregador["id"],
                "driver_name": entregador["name"],
            },
            timeout=TIMEOUT,
        ).json()

        # Estado de um pedido migrado cujo nome não casou: só os nomes em texto.
        # A API não deixa gravar esse estado, então ele é forçado no banco.
        async def _tirar_ids():
            con = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
            try:
                await con.execute(
                    "UPDATE orders SET driver_id = '', restaurant_id = '' WHERE id = $1",
                    pedido["id"],
                )
            finally:
                await con.close()

        asyncio.run(_tirar_ids())

        antes = admin.get(f"{API}/drivers/{entregador['id']}", timeout=TIMEOUT).json()
        for etapa in ("aguardando_coleta", "em_transito", "entregue"):
            admin.patch(
                f"{API}/orders/{pedido['id']}/status", json={"status": etapa}, timeout=TIMEOUT
            )
        creditado = admin.get(f"{API}/drivers/{entregador['id']}", timeout=TIMEOUT).json()
        assert creditado["balance_due"] > antes["balance_due"], "a entrega deveria creditar"

        admin.patch(
            f"{API}/orders/{pedido['id']}/status", json={"status": "em_transito"}, timeout=TIMEOUT
        )
        final = admin.get(f"{API}/drivers/{entregador['id']}", timeout=TIMEOUT).json()
        assert final["balance_due"] == antes["balance_due"], "o estorno não devolveu o valor"
        assert final["total_deliveries"] == antes["total_deliveries"]

        admin.delete(f"{API}/orders/{pedido['id']}", timeout=TIMEOUT)

    def test_estorno_usa_o_valor_creditado_na_epoca(self, admin, restaurante, entregador):
        """Editar o valor do pedido entre a entrega e o estorno não pode fazer o
        estorno devolver um número diferente do que foi lançado."""
        pedido = admin.post(
            f"{API}/orders",
            json={
                "restaurant_id": restaurante["id"],
                "restaurant_name": restaurante["name"],
                "customer_name": "Cliente",
                "amount": 200.0,
                "driver_id": entregador["id"],
            },
            timeout=TIMEOUT,
        ).json()
        antes = admin.get(f"{API}/restaurants/{restaurante['id']}", timeout=TIMEOUT).json()
        for etapa in ("aguardando_coleta", "em_transito", "entregue"):
            admin.patch(
                f"{API}/orders/{pedido['id']}/status", json={"status": etapa}, timeout=TIMEOUT
            )
        admin.put(
            f"{API}/orders/{pedido['id']}",
            json={
                "restaurant_id": restaurante["id"],
                "restaurant_name": restaurante["name"],
                "customer_name": "Cliente",
                "amount": 999.0,
            },
            timeout=TIMEOUT,
        )
        admin.patch(
            f"{API}/orders/{pedido['id']}/status", json={"status": "em_transito"}, timeout=TIMEOUT
        )
        final = admin.get(f"{API}/restaurants/{restaurante['id']}", timeout=TIMEOUT).json()
        assert final["revenue_total"] == antes["revenue_total"]
        assert final["commission_due"] == antes["commission_due"]
        admin.delete(f"{API}/orders/{pedido['id']}", timeout=TIMEOUT)


class TestDesempenho:
    def test_dashboard_responde_rapido(self, admin):
        """Regressão: a tendência de 14 dias era montada com 28 count_documents
        em laço e respondia por quase todo o tempo do painel."""
        import time

        admin.get(f"{API}/dashboard/stats", timeout=TIMEOUT)  # aquece
        t0 = time.time()
        for _ in range(3):
            assert admin.get(f"{API}/dashboard/stats", timeout=TIMEOUT).status_code == 200
        media = (time.time() - t0) / 3
        assert media < 1.0, f"painel levou {media * 1000:.0f} ms por chamada"
