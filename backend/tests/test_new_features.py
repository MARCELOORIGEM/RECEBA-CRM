"""Funil comercial, atividades, auditoria, busca global, usuários e integrações."""
import re
import uuid

import pytest
import requests

from .conftest import API, TIMEOUT


# ----------------------------------------------------------------- funil
class TestFunil:
    @pytest.fixture
    def lead(self, admin):
        r = admin.post(
            f"{API}/leads",
            json={
                "name": f"Lead Teste {uuid.uuid4().hex[:8]}",
                "contact_name": "Contato",
                "source": "indicacao",
                "estimated_value": 1500,
            },
            timeout=TIMEOUT,
        )
        assert r.status_code == 201, r.text
        doc = r.json()
        yield doc
        admin.delete(f"{API}/leads/{doc['id']}", timeout=TIMEOUT)

    def test_nasce_a_visitar_com_historico(self, lead):
        assert lead["stage"] == "a_visitar"
        assert lead["stage_history"][0]["stage"] == "a_visitar"

    def test_mover_status_registra_historico(self, admin, lead):
        r = admin.patch(f"{API}/leads/{lead['id']}/stage", json={"stage": "reuniao"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["stage"] == "reuniao"
        assert len(r.json()["stage_history"]) == 2

    def test_sem_interesse_exige_motivo(self, admin, lead):
        sem_motivo = admin.patch(
            f"{API}/leads/{lead['id']}/stage", json={"stage": "sem_interesse"}, timeout=TIMEOUT
        )
        assert sem_motivo.status_code == 422

        com_motivo = admin.patch(
            f"{API}/leads/{lead['id']}/stage",
            json={"stage": "sem_interesse", "lost_reason": "Achou a comissão alta"},
            timeout=TIMEOUT,
        )
        assert com_motivo.status_code == 200
        assert com_motivo.json()["lost_reason"] == "Achou a comissão alta"

        # Voltar a trabalhar no lead limpa o motivo antigo.
        de_volta = admin.patch(
            f"{API}/leads/{lead['id']}/stage", json={"stage": "segunda_visita"}, timeout=TIMEOUT
        )
        assert de_volta.json()["lost_reason"] == ""

    def test_descarte_que_se_explica_nao_pede_motivo(self, admin, lead):
        r = admin.patch(
            f"{API}/leads/{lead['id']}/stage", json={"stage": "fora_da_area"}, timeout=TIMEOUT
        )
        assert r.status_code == 200

    def test_campos_de_campo_e_filtros(self, admin, nome_unico):
        lider = nome_unico("Lider")
        r = admin.post(
            f"{API}/leads",
            json={"name": nome_unico("Lead Campo"), "codigo_externo": nome_unico("ID")[-8:],
                  "endereco": "RUA H, 357", "bairro": "UNIÃO", "bd_id": "BD9",
                  "bd_nome": "JUNIAO", "lider": lider, "data_visita": "2026-10-05",
                  "stage": "nao_localizado"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 201, r.text
        lead = r.json()
        try:
            assert (lead["bairro"], lead["data_visita"], lead["stage"]) == (
                "UNIÃO", "2026-10-05", "nao_localizado")
            assert lider in admin.get(f"{API}/leads/filtros", timeout=TIMEOUT).json()["lideres"]
            filtrados = admin.get(f"{API}/leads", params={"lider": lider}, timeout=TIMEOUT).json()
            assert [l["id"] for l in filtrados["items"]] == [lead["id"]]
            por_codigo = admin.get(f"{API}/leads", params={"search": lead["codigo_externo"]},
                                   timeout=TIMEOUT).json()
            assert por_codigo["total"] == 1
        finally:
            admin.delete(f"{API}/leads/{lead['id']}", timeout=TIMEOUT)

    def test_lead_id_repetido_e_recusado(self, admin, nome_unico):
        codigo = nome_unico("X")[-8:]
        a = admin.post(f"{API}/leads", json={"name": nome_unico("A"), "codigo_externo": codigo},
                       timeout=TIMEOUT).json()
        try:
            b = admin.post(f"{API}/leads", json={"name": nome_unico("B"), "codigo_externo": codigo},
                           timeout=TIMEOUT)
            assert b.status_code == 409
        finally:
            admin.delete(f"{API}/leads/{a['id']}", timeout=TIMEOUT)

    def test_etapa_invalida(self, admin, lead):
        r = admin.patch(f"{API}/leads/{lead['id']}/stage", json={"stage": "quase"}, timeout=TIMEOUT)
        assert r.status_code == 422

    def test_conversao_cria_restaurante(self, admin, lead):
        r = admin.post(f"{API}/leads/{lead['id']}/convert", timeout=TIMEOUT)
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["lead"]["stage"] == "ativado"
        assert corpo["restaurant"]["name"] == lead["name"]
        assert corpo["restaurant"]["status"] == "em_analise"

        assert admin.post(f"{API}/leads/{lead['id']}/convert", timeout=TIMEOUT).status_code == 409
        admin.delete(
            f"{API}/restaurants/{corpo['restaurant']['id']}", params={"force": "true"}, timeout=TIMEOUT
        )

    def test_resumo_do_funil(self, admin):
        f = admin.get(f"{API}/leads/funnel", timeout=TIMEOUT).json()
        assert len(f["stages"]) == 13
        assert {s["grupo"] for s in f["stages"]} == {"aberto", "ganho", "perdido"}
        assert 0 <= f["taxa_conversao"] <= 100
        assert f["valor_em_aberto"] >= 0

    def test_gestor_nao_exclui_lead(self, manager, lead):
        assert manager.delete(f"{API}/leads/{lead['id']}", timeout=TIMEOUT).status_code == 403


# ------------------------------------------------------------- atividades
class TestAtividades:
    @pytest.fixture
    def tarefa(self, admin):
        r = admin.post(
            f"{API}/activities",
            json={
                "kind": "tarefa",
                "type": "ligacao",
                "title": f"Tarefa {uuid.uuid4().hex[:8]}",
                "due_at": "2026-12-31T12:00:00+00:00",
            },
            timeout=TIMEOUT,
        )
        assert r.status_code == 201, r.text
        doc = r.json()
        yield doc
        admin.delete(f"{API}/activities/{doc['id']}", timeout=TIMEOUT)

    def test_tarefa_nasce_aberta(self, tarefa):
        assert tarefa["done"] is False
        assert tarefa["completed_at"] is None

    def test_interacao_nasce_concluida(self, admin):
        r = admin.post(
            f"{API}/activities",
            json={"kind": "interacao", "type": "nota", "title": "Conversa registrada"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 201
        assert r.json()["done"] is True
        assert r.json()["completed_at"] is not None
        admin.delete(f"{API}/activities/{r.json()['id']}", timeout=TIMEOUT)

    def test_concluir_e_reabrir(self, admin, tarefa):
        feito = admin.patch(f"{API}/activities/{tarefa['id']}/toggle", timeout=TIMEOUT).json()
        assert feito["done"] is True and feito["completed_at"]

        reaberto = admin.patch(f"{API}/activities/{tarefa['id']}/toggle", timeout=TIMEOUT).json()
        assert reaberto["done"] is False and reaberto["completed_at"] is None

    @pytest.mark.parametrize("escopo", ["hoje", "atrasadas", "proximas", "concluidas", "todas"])
    def test_filtros_por_escopo(self, admin, escopo):
        r = admin.get(f"{API}/activities", params={"scope": escopo}, timeout=TIMEOUT)
        assert r.status_code == 200
        if escopo == "concluidas":
            assert all(a["done"] for a in r.json()["items"])

    def test_resumo(self, admin):
        s = admin.get(f"{API}/activities/summary", timeout=TIMEOUT).json()
        assert {"atrasadas", "hoje", "semana", "abertas"} <= set(s)
        assert all(v >= 0 for v in s.values())


# ----------------------------------------------------------- busca e timeline
class TestBuscaETimeline:
    def test_busca_exige_dois_caracteres(self, admin):
        assert admin.get(f"{API}/search", params={"q": "a"}, timeout=TIMEOUT).json()["results"] == []

    def test_busca_cruza_cadastros(self, admin, restaurante):
        r = admin.get(f"{API}/search", params={"q": restaurante["name"][:12]}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert any(x["titulo"] == restaurante["name"] for x in r.json()["results"])

    def test_timeline_reune_interacoes_e_alteracoes(self, admin, restaurante):
        admin.post(
            f"{API}/activities",
            json={
                "kind": "interacao",
                "type": "ligacao",
                "title": "Ligação de acompanhamento",
                "related_type": "restaurante",
                "related_id": restaurante["id"],
                "related_name": restaurante["name"],
            },
            timeout=TIMEOUT,
        )
        eventos = admin.get(f"{API}/timeline/restaurante/{restaurante['id']}", timeout=TIMEOUT).json()[
            "eventos"
        ]
        origens = {e["origem"] for e in eventos}
        assert "atividade" in origens, "a interação registrada deveria aparecer"
        assert "sistema" in origens, "a criação do cadastro deveria aparecer"
        assert eventos == sorted(eventos, key=lambda e: e["at"], reverse=True)


# ------------------------------------------------------------------ auditoria
class TestAuditoria:
    def test_registra_criacao(self, admin, nome_unico):
        nome = nome_unico("Auditado")
        criado = admin.post(
            f"{API}/restaurants", json={"name": nome, "category": "Teste"}, timeout=TIMEOUT
        ).json()

        logs = admin.get(f"{API}/audit", params={"entity": "restaurante"}, timeout=TIMEOUT).json()
        assert any(l["entity_id"] == criado["id"] and l["action"] == "criou" for l in logs["items"])
        admin.delete(f"{API}/restaurants/{criado['id']}", timeout=TIMEOUT)

    def test_registra_o_que_mudou(self, admin, restaurante):
        admin.put(
            f"{API}/restaurants/{restaurante['id']}",
            json={"name": restaurante["name"], "category": "Categoria Nova"},
            timeout=TIMEOUT,
        )
        logs = admin.get(f"{API}/audit", timeout=TIMEOUT).json()["items"]
        alteracao = next(
            (l for l in logs if l["entity_id"] == restaurante["id"] and l["action"] == "atualizou"),
            None,
        )
        assert alteracao is not None
        assert "category" in alteracao["changes"]

    def test_nao_guarda_segredo(self, admin):
        logs = admin.get(f"{API}/audit", timeout=TIMEOUT).json()["items"]
        for l in logs:
            assert not {"password", "password_hash", "key", "key_hash"} & set(l.get("changes", {}))


# ------------------------------------------------------------------- usuários
class TestUsuarios:
    def test_ciclo(self, admin):
        email = f"teste-{uuid.uuid4().hex[:8]}@exemplo.com"
        criado = admin.post(
            f"{API}/users",
            json={"name": "Usuário Teste", "email": email, "password": "senhaforte123"},
            timeout=TIMEOUT,
        )
        assert criado.status_code == 201
        uid = criado.json()["id"]
        assert criado.json()["role"] == "manager"

        duplicado = admin.post(
            f"{API}/users",
            json={"name": "Outro", "email": email, "password": "senhaforte123"},
            timeout=TIMEOUT,
        )
        assert duplicado.status_code == 400

        promovido = admin.put(f"{API}/users/{uid}", json={"role": "admin"}, timeout=TIMEOUT)
        assert promovido.status_code == 200 and promovido.json()["role"] == "admin"

        desativado = admin.put(f"{API}/users/{uid}", json={"active": False}, timeout=TIMEOUT)
        assert desativado.status_code == 200 and desativado.json()["active"] is False

        assert admin.delete(f"{API}/users/{uid}", timeout=TIMEOUT).status_code == 200

    def test_senha_curta_recusada(self, admin):
        r = admin.post(
            f"{API}/users",
            json={"name": "Curta", "email": f"c-{uuid.uuid4().hex[:6]}@x.com", "password": "123"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422

    def test_nao_remove_a_propria_conta(self, admin):
        r = admin.delete(f"{API}/users/{admin.me['id']}", timeout=TIMEOUT)
        assert r.status_code == 400

    def test_nao_se_rebaixa(self, admin):
        """Sem esta trava, o admin podia virar gestor e trancar a operação."""
        r = admin.put(f"{API}/users/{admin.me['id']}", json={"role": "manager"}, timeout=TIMEOUT)
        assert r.status_code == 400

    def test_id_invalido_da_404(self, admin):
        assert admin.put(f"{API}/users/nao-e-objectid", json={"name": "x"}, timeout=TIMEOUT).status_code == 404

    def test_listagem_nao_expoe_hash(self, admin):
        for u in admin.get(f"{API}/users", timeout=TIMEOUT).json():
            assert "password_hash" not in u


# --------------------------------------------------------------- integrações
class TestIntegracoes:
    def test_chave_aparece_uma_vez_e_some_da_listagem(self, admin):
        """Regressão: a chave era guardada e devolvida em texto puro em toda
        listagem, então um acesso de leitura ao painel levava a credencial."""
        criada = admin.post(
            f"{API}/integrations/keys",
            json={"name": f"Chave {uuid.uuid4().hex[:6]}", "environment": "sandbox"},
            timeout=TIMEOUT,
        )
        assert criada.status_code == 201
        corpo = criada.json()
        assert corpo["key"].startswith("mln_test_")
        assert "key_hash" not in corpo

        listagem = admin.get(f"{API}/integrations/keys", timeout=TIMEOUT).json()
        registro = next(k for k in listagem if k["id"] == corpo["id"])
        assert "key" not in registro, "o valor completo não pode voltar na listagem"
        assert "key_hash" not in registro
        assert "…" in registro["key_preview"]

        assert admin.delete(f"{API}/integrations/keys/{corpo['id']}", timeout=TIMEOUT).status_code == 200

    def test_revogar_chave_inexistente(self, admin):
        assert admin.delete(f"{API}/integrations/keys/nao-existe", timeout=TIMEOUT).status_code == 404

    def test_webhook_ciclo(self, admin):
        criado = admin.post(
            f"{API}/integrations/webhooks",
            json={
                "provider": "ifood",
                "url": "https://exemplo.com/webhook",
                "events": ["pedido.criado"],
            },
            timeout=TIMEOUT,
        )
        assert criado.status_code == 201
        wid = criado.json()["id"]

        desligado = admin.put(
            f"{API}/integrations/webhooks/{wid}",
            json={"provider": "ifood", "url": "https://exemplo.com/webhook", "active": False},
            timeout=TIMEOUT,
        )
        assert desligado.json()["active"] is False
        assert admin.delete(f"{API}/integrations/webhooks/{wid}", timeout=TIMEOUT).status_code == 200

    def test_logs_visiveis_para_gestor(self, manager):
        assert manager.get(f"{API}/integrations/logs", timeout=TIMEOUT).status_code == 200

    def test_chaves_ocultas_do_gestor(self, manager):
        assert manager.get(f"{API}/integrations/keys", timeout=TIMEOUT).status_code == 403


# ------------------------------------------------------- conta do usuário
class TestContaPropria:
    """Regressão: trocar a senha só existia na gestão de usuários, restrita ao
    administrador — um gestor ficava preso à senha com que foi cadastrado.

    Os testes usam uma conta DESCARTÁVEL, não a do gestor compartilhado. Trocar
    a senha de uma conta que as outras classes usam faz um worker do pytest
    receber 401 quando tenta logar bem na janela da troca — foi o que
    aconteceu, e o paralelismo escondia a causa.
    """

    SENHA = "SenhaInicial@2026"

    @pytest.fixture
    def conta(self, admin):
        email = f"conta-{uuid.uuid4().hex[:8]}@exemplo.com"
        r = admin.post(
            f"{API}/users",
            json={"name": "Conta Descartável", "email": email, "password": self.SENHA},
            timeout=TIMEOUT,
        )
        assert r.status_code == 201, r.text
        uid = r.json()["id"]

        sessao = requests.Session()
        entrada = sessao.post(
            f"{API}/auth/login", json={"email": email, "password": self.SENHA}, timeout=TIMEOUT
        )
        assert entrada.status_code == 200, entrada.text
        token = re.search(r"access_token=([^;]+)", entrada.headers.get("set-cookie", ""))
        if token:
            sessao.headers["Authorization"] = f"Bearer {token.group(1)}"
        sessao.email = email
        yield sessao
        admin.delete(f"{API}/users/{uid}", timeout=TIMEOUT)

    def test_troca_a_propria_senha(self, conta):
        nova = "SenhaTrocada@2026"
        r = conta.post(
            f"{API}/auth/password",
            json={"current_password": self.SENHA, "new_password": nova},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text

        entrada = requests.post(
            f"{API}/auth/login", json={"email": conta.email, "password": nova}, timeout=TIMEOUT
        )
        assert entrada.status_code == 200, "a senha nova precisa valer no login"

        antiga = requests.post(
            f"{API}/auth/login", json={"email": conta.email, "password": self.SENHA}, timeout=TIMEOUT
        )
        assert antiga.status_code in (401, 429), "a senha antiga não pode continuar valendo"

    def test_senha_atual_errada(self, conta):
        r = conta.post(
            f"{API}/auth/password",
            json={"current_password": "chute-errado", "new_password": "OutraSenha@2026"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 401

    def test_nova_senha_curta(self, conta):
        r = conta.post(
            f"{API}/auth/password",
            json={"current_password": self.SENHA, "new_password": "123"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 422

    def test_nova_igual_a_atual(self, conta):
        r = conta.post(
            f"{API}/auth/password",
            json={"current_password": self.SENHA, "new_password": self.SENHA},
            timeout=TIMEOUT,
        )
        assert r.status_code == 400

    def test_edita_o_proprio_nome(self, conta):
        r = conta.put(f"{API}/auth/me", json={"name": "Nome Alterado"}, timeout=TIMEOUT)
        assert r.status_code == 200 and r.json()["name"] == "Nome Alterado"

    def test_exige_autenticacao(self):
        r = requests.post(
            f"{API}/auth/password",
            json={"current_password": "x", "new_password": "senhaforte123"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 401


class TestAgendaCoerente:
    """Regressão: `scope="hoje"` não tinha limite inferior, então a aba "Hoje"
    devolvia também tudo o que estava atrasado — e mostrava um número diferente
    do contador da própria aba, que vinha de /activities/summary."""

    def test_aba_hoje_bate_com_o_contador(self, admin):
        resumo = admin.get(f"{API}/activities/summary", timeout=TIMEOUT).json()
        lista = admin.get(f"{API}/activities", params={"scope": "hoje"}, timeout=TIMEOUT).json()
        assert lista["total"] == resumo["hoje"]

    def test_hoje_nao_inclui_atrasadas(self, admin):
        hoje = admin.get(f"{API}/activities", params={"scope": "hoje"}, timeout=TIMEOUT).json()
        atrasadas = {
            a["id"]
            for a in admin.get(
                f"{API}/activities", params={"scope": "atrasadas"}, timeout=TIMEOUT
            ).json()["items"]
        }
        assert not {a["id"] for a in hoje["items"]} & atrasadas

    def test_escopos_nao_se_sobrepoem(self, admin):
        def ids(escopo):
            return {
                a["id"]
                for a in admin.get(
                    f"{API}/activities", params={"scope": escopo, "page_size": 200}, timeout=TIMEOUT
                ).json()["items"]
            }

        atrasadas, hoje, proximas = ids("atrasadas"), ids("hoje"), ids("proximas")
        assert not atrasadas & hoje
        assert not hoje & proximas
        assert not atrasadas & proximas
