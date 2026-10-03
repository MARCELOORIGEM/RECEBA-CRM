"""Recursos que só existem por causa da operação real.

Três coisas que o sistema não tinha e que travariam o primeiro mês em produção:
quem perde a senha depende de alguém digitar outra por ele; a chave de API era
decorativa, sem nenhuma rota que a aceitasse; e não havia como um marketplace
empurrar pedido para dentro do CRM.
"""
import os
import uuid

import pytest
import requests

from .conftest import API, TIMEOUT

anon = requests


@pytest.fixture
def conta_descartavel(admin):
    """Conta criada só para o teste.

    Mexer na senha de uma conta compartilhada derruba o outro worker do pytest
    no meio da rodada — foi o que aconteceu uma vez com o gestor.
    """
    sufixo = uuid.uuid4().hex[:8]
    r = admin.post(
        f"{API}/users",
        json={
            "name": f"Descartavel {sufixo}",
            "email": f"descartavel.{sufixo}@exemplo.com",
            "password": "SenhaInicial@2026",
            "role": "manager",
        },
        timeout=TIMEOUT,
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    doc["password"] = "SenhaInicial@2026"
    yield doc
    admin.delete(f"{API}/users/{doc['id']}", timeout=TIMEOUT)


def _entrar(email, senha):
    return anon.post(f"{API}/auth/login", json={"email": email, "password": senha}, timeout=TIMEOUT)


def _token(link):
    return link.rsplit("/", 1)[-1]


# ------------------------------------------------------------- nova senha
class TestLinkDeNovaSenha:
    def test_fluxo_completo(self, admin, conta_descartavel):
        gerado = admin.post(f"{API}/senha/link/{conta_descartavel['id']}", timeout=TIMEOUT)
        assert gerado.status_code == 200, gerado.text
        corpo = gerado.json()
        assert "/redefinir-senha/" in corpo["link"]
        assert corpo["usuario"]["email"] == conta_descartavel["email"]

        nova = "TrocadaPeloLink@2026"
        r = anon.post(
            f"{API}/senha/redefinir",
            json={"token": _token(corpo["link"]), "nova_senha": nova},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text

        assert _entrar(conta_descartavel["email"], nova).status_code == 200
        antiga = _entrar(conta_descartavel["email"], conta_descartavel["password"])
        assert antiga.status_code in (401, 429), "a senha antiga tinha de ter morrido"

    def test_link_vale_uma_vez_so(self, admin, conta_descartavel):
        corpo = admin.post(
            f"{API}/senha/link/{conta_descartavel['id']}", timeout=TIMEOUT
        ).json()
        token = _token(corpo["link"])

        assert anon.post(
            f"{API}/senha/redefinir",
            json={"token": token, "nova_senha": "PrimeiroUso@2026"},
            timeout=TIMEOUT,
        ).status_code == 200
        # Link vazado depois do uso não serve para nada.
        repetido = anon.post(
            f"{API}/senha/redefinir",
            json={"token": token, "nova_senha": "SegundoUso@2026"},
            timeout=TIMEOUT,
        )
        assert repetido.status_code == 400

    def test_gerar_de_novo_derruba_o_anterior(self, admin, conta_descartavel):
        """Senão, cada pedido deixaria mais uma chave válida solta por aí."""
        primeiro = _token(
            admin.post(f"{API}/senha/link/{conta_descartavel['id']}", timeout=TIMEOUT).json()["link"]
        )
        segundo = _token(
            admin.post(f"{API}/senha/link/{conta_descartavel['id']}", timeout=TIMEOUT).json()["link"]
        )
        assert primeiro != segundo

        assert anon.post(
            f"{API}/senha/redefinir",
            json={"token": primeiro, "nova_senha": "Antigo@2026"},
            timeout=TIMEOUT,
        ).status_code == 400
        assert anon.post(
            f"{API}/senha/redefinir",
            json={"token": segundo, "nova_senha": "Atual@2026"},
            timeout=TIMEOUT,
        ).status_code == 200

    def test_token_inventado_nao_passa(self):
        r = anon.post(
            f"{API}/senha/redefinir",
            json={"token": "x" * 43, "nova_senha": "QualquerCoisa@2026"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 400
        # A mensagem é a mesma de token vencido: distinguir os dois contaria a
        # um atacante que aquele token existiu.
        assert "inválido ou expirado" in r.json()["detail"]

    def test_senha_curta_recusada(self, admin, conta_descartavel):
        token = _token(
            admin.post(f"{API}/senha/link/{conta_descartavel['id']}", timeout=TIMEOUT).json()["link"]
        )
        assert anon.post(
            f"{API}/senha/redefinir", json={"token": token, "nova_senha": "curta"}, timeout=TIMEOUT
        ).status_code == 422

    def test_so_administrador_gera(self, manager, conta_descartavel):
        assert manager.post(
            f"{API}/senha/link/{conta_descartavel['id']}", timeout=TIMEOUT
        ).status_code == 403

    def test_anonimo_nao_gera(self, conta_descartavel):
        assert anon.post(
            f"{API}/senha/link/{conta_descartavel['id']}", timeout=TIMEOUT
        ).status_code == 401

    def test_usuario_inexistente(self, admin):
        assert admin.post(f"{API}/senha/link/nao-existe", timeout=TIMEOUT).status_code == 404


# ---------------------------------------------------- entrada de eventos
@pytest.fixture
def chave_api(admin):
    r = admin.post(
        f"{API}/integrations/keys",
        json={"name": f"Entrada {uuid.uuid4().hex[:6]}", "environment": "sandbox"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    yield doc
    admin.delete(f"{API}/integrations/keys/{doc['id']}", timeout=TIMEOUT)


class TestEntradaDeEventos:
    """A rota por onde o marketplace empurra pedido para dentro do CRM."""

    def _enviar(self, chave, corpo, provider="keeta"):
        return anon.post(
            f"{API}/integracoes/eventos/{provider}",
            json=corpo,
            headers={"Authorization": f"Bearer {chave}"},
            timeout=TIMEOUT,
        )

    def _apagar(self, admin, referencia, provider="keeta"):
        pedidos = admin.get(f"{API}/orders", params={"page_size": 200}, timeout=TIMEOUT).json()
        for p in pedidos["items"]:
            if p.get("external_ref") == f"{provider}:{referencia}":
                admin.delete(f"{API}/orders/{p['id']}", timeout=TIMEOUT)

    def test_sem_chave_nao_entra(self):
        r = anon.post(
            f"{API}/integracoes/eventos/keeta",
            json={"evento": "pedido.criado", "referencia": "X1"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 401

    def test_chave_errada_nao_entra(self):
        r = self._enviar("mln_test_chave_que_nao_existe", {
            "evento": "pedido.criado", "referencia": "X2",
        })
        assert r.status_code == 401

    def test_cria_pedido(self, admin, chave_api, restaurante):
        ref = f"REF-{uuid.uuid4().hex[:8]}"
        try:
            r = self._enviar(chave_api["key"], {
                "evento": "pedido.criado",
                "referencia": ref,
                "restaurante": restaurante["name"],
                "cliente": "Cliente da Integração",
                "endereco": "Rua Teste, 100",
                "valor": 80.0,
                "taxa_entrega": 10.0,
                "distancia_km": 4.0,
            })
            assert r.status_code == 202, r.text
            assert r.json()["criado"] is True

            pedidos = admin.get(
                f"{API}/orders", params={"restaurant_id": restaurante["id"]}, timeout=TIMEOUT
            ).json()["items"]
            pedido = next(p for p in pedidos if p["external_ref"] == f"keeta:{ref}")
            assert pedido["status"] == "criado"
            assert pedido["origem"] == "keeta"
            assert pedido["amount"] == 80.0
        finally:
            self._apagar(admin, ref)

    def test_mesma_referencia_atualiza_em_vez_de_duplicar(self, admin, chave_api, restaurante):
        """Reenvio é rotina: a rede cai, o marketplace repete. Duplicar aqui
        viraria pedido pago duas vezes."""
        ref = f"REF-{uuid.uuid4().hex[:8]}"
        try:
            self._enviar(chave_api["key"], {
                "evento": "pedido.criado", "referencia": ref,
                "restaurante": restaurante["name"], "valor": 50.0, "taxa_entrega": 8.0,
            })
            segundo = self._enviar(chave_api["key"], {
                "evento": "pedido.aceito", "referencia": ref,
            })
            assert segundo.status_code == 202
            assert segundo.json()["criado"] is False
            assert segundo.json()["status"] == "aguardando_coleta"

            pedidos = admin.get(
                f"{API}/orders", params={"restaurant_id": restaurante["id"]}, timeout=TIMEOUT
            ).json()["items"]
            iguais = [p for p in pedidos if p["external_ref"] == f"keeta:{ref}"]
            assert len(iguais) == 1, "a mesma referência não pode virar dois pedidos"
        finally:
            self._apagar(admin, ref)

    def test_evento_de_pedido_desconhecido(self, chave_api):
        r = self._enviar(chave_api["key"], {
            "evento": "pedido.entregue", "referencia": f"INEXISTENTE-{uuid.uuid4().hex[:6]}",
        })
        assert r.status_code == 404

    def test_evento_invalido_recusado(self, chave_api):
        r = self._enviar(chave_api["key"], {"evento": "pedido.explodiu", "referencia": "X3"})
        assert r.status_code == 422

    def test_entrega_movimenta_o_financeiro(self, admin, chave_api, restaurante):
        """O mesmo motor da tela: entregue lança repasse e comissão."""
        ref = f"REF-{uuid.uuid4().hex[:8]}"
        try:
            self._enviar(chave_api["key"], {
                "evento": "pedido.criado", "referencia": ref,
                "restaurante": restaurante["name"], "valor": 100.0, "taxa_entrega": 12.0,
            })
            r = self._enviar(chave_api["key"], {"evento": "pedido.entregue", "referencia": ref})
            assert r.status_code == 202

            pedidos = admin.get(
                f"{API}/orders", params={"restaurant_id": restaurante["id"]}, timeout=TIMEOUT
            ).json()["items"]
            pedido = next(p for p in pedidos if p["external_ref"] == f"keeta:{ref}")
            assert pedido["status"] == "entregue"
            assert pedido["financials_applied"] is True
            assert pedido["platform_commission"] > 0
        finally:
            self._apagar(admin, ref)

    def test_registra_log(self, admin, chave_api, restaurante):
        """Integração sem registro é integração que ninguém consegue depurar."""
        ref = f"REF-{uuid.uuid4().hex[:8]}"
        try:
            self._enviar(chave_api["key"], {
                "evento": "pedido.criado", "referencia": ref,
                "restaurante": restaurante["name"],
            })
            logs = admin.get(
                f"{API}/integrations/logs", params={"page_size": 50}, timeout=TIMEOUT
            ).json()
            itens = logs["items"] if isinstance(logs, dict) else logs
            assert any(l.get("provider") == "keeta" for l in itens)
        finally:
            self._apagar(admin, ref)


# -------------------------------------------------------- limite por IP
class TestLimitePorIp:
    """Freio do formulário público.

    A rota grava cadastro sem sessão: sem teto por dispositivo, um robô enche
    a base de entregadores falsos numa noite.
    """

    LIMITE = int(os.environ.get("MAX_ENVIOS_POR_IP", "10"))

    @pytest.fixture
    def formulario_simples(self, admin):
        r = admin.post(
            f"{API}/forms",
            json={
                "title": f"Limite {uuid.uuid4().hex[:8]}",
                "target": "lead",
                "fields": [{"key": "name", "label": "Nome", "required": True}],
            },
            timeout=TIMEOUT,
        )
        doc = r.json()
        yield doc
        admin.delete(f"{API}/forms/{doc['id']}", params={"force": "true"}, timeout=TIMEOUT)

    def test_fecha_a_torneira_no_teto(self, admin, formulario_simples):
        if self.LIMITE > 15:
            pytest.skip(
                f"MAX_ENVIOS_POR_IP={self.LIMITE}: alto demais para exercitar sem poluir a base."
            )

        criados = []
        try:
            bateu = False
            for i in range(self.LIMITE + 3):
                r = anon.post(
                    f"{API}/public/forms/{formulario_simples['slug']}",
                    json={"respostas": {"name": f"Enxurrada {i}", "_consentimento": True}},
                    timeout=TIMEOUT,
                )
                if r.status_code == 429:
                    bateu = True
                    break
                if r.status_code == 201 and r.json().get("id"):
                    criados.append(r.json()["id"])
            assert bateu, "o teto por IP não travou nada"
        finally:
            for lid in criados:
                admin.delete(f"{API}/leads/{lid}", timeout=TIMEOUT)


# --------------------------------------------------- exclusão de resposta
class TestExclusaoDeResposta:
    """Pedido de exclusão previsto na LGPD.

    A resposta guarda CPF, conta e chave PIX. Apagar só o cadastro no CRM
    deixava essa cópia para trás, e era a cópia que ninguém lembrava.
    """

    @pytest.fixture
    def formulario_com_resposta(self, admin):
        criado = admin.post(
            f"{API}/forms",
            json={
                "title": f"Exclusao {uuid.uuid4().hex[:8]}",
                "target": "lead",
                "fields": [{"key": "name", "label": "Nome", "required": True}],
            },
            timeout=TIMEOUT,
        ).json()
        envio = anon.post(
            f"{API}/public/forms/{criado['slug']}",
            json={"respostas": {"name": "Pediu para sair", "_consentimento": True}},
            timeout=TIMEOUT,
        )
        assert envio.status_code == 201, envio.text
        respostas = admin.get(f"{API}/forms/{criado['id']}/submissions", timeout=TIMEOUT).json()
        yield criado, respostas["items"][0], envio.json()["id"]
        admin.delete(f"{API}/forms/{criado['id']}", params={"force": "true"}, timeout=TIMEOUT)
        admin.delete(f"{API}/leads/{envio.json()['id']}", timeout=TIMEOUT)

    def test_administrador_apaga_e_contador_acompanha(self, admin, formulario_com_resposta):
        form, resposta, _ = formulario_com_resposta
        antes = admin.get(f"{API}/forms/{form['id']}", timeout=TIMEOUT).json()["submissions_count"]

        r = admin.delete(
            f"{API}/forms/{form['id']}/submissions/{resposta['id']}", timeout=TIMEOUT
        )
        assert r.status_code == 200, r.text

        depois = admin.get(f"{API}/forms/{form['id']}", timeout=TIMEOUT).json()
        assert depois["submissions_count"] == antes - 1
        itens = admin.get(
            f"{API}/forms/{form['id']}/submissions", timeout=TIMEOUT
        ).json()["items"]
        assert all(i["id"] != resposta["id"] for i in itens)

    def test_cadastro_gerado_sobrevive(self, admin, formulario_com_resposta):
        """O cadastro vive no CRM, com pedidos e pagamentos pendurados nele.
        Apagar a resposta não pode levá-lo junto."""
        form, resposta, lead_id = formulario_com_resposta
        admin.delete(f"{API}/forms/{form['id']}/submissions/{resposta['id']}", timeout=TIMEOUT)
        assert admin.get(f"{API}/leads/{lead_id}", timeout=TIMEOUT).status_code == 200

    def test_gestor_nao_apaga(self, manager, formulario_com_resposta):
        form, resposta, _ = formulario_com_resposta
        assert manager.delete(
            f"{API}/forms/{form['id']}/submissions/{resposta['id']}", timeout=TIMEOUT
        ).status_code == 403

    def test_anonimo_nao_apaga(self, formulario_com_resposta):
        form, resposta, _ = formulario_com_resposta
        assert anon.delete(
            f"{API}/forms/{form['id']}/submissions/{resposta['id']}", timeout=TIMEOUT
        ).status_code == 401

    def test_resposta_de_outro_formulario_nao_some(self, admin, formulario_com_resposta):
        """O id do formulário faz parte da rota: sem conferi-lo, um id de
        resposta solto apagaria registro de qualquer formulário."""
        form, resposta, _ = formulario_com_resposta
        outro = admin.post(
            f"{API}/forms",
            json={"title": f"Outro {uuid.uuid4().hex[:6]}", "target": "lead",
                  "fields": [{"key": "name", "label": "Nome", "required": True}]},
            timeout=TIMEOUT,
        ).json()
        try:
            r = admin.delete(
                f"{API}/forms/{outro['id']}/submissions/{resposta['id']}", timeout=TIMEOUT
            )
            assert r.status_code == 404
        finally:
            admin.delete(f"{API}/forms/{outro['id']}", params={"force": "true"}, timeout=TIMEOUT)
