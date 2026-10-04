"""Permissões por tela e controle do administrador sobre as contas.

O que estes testes travam: a escolha de telas vale na API, não só no menu; a
leitura de apoio não vira escrita; e trocar a senha derruba quem estava
logado com a antiga.
"""
import uuid

import pytest
import requests

from .conftest import API, TIMEOUT

SENHA = "Senha-Teste-2026"


def _entrar(email: str, senha: str = SENHA) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": senha}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.cookies.get('access_token')}"
    s.me = r.json()
    return s


@pytest.fixture
def conta(admin):
    """Gestor com acesso só a Pedidos. Apagado no fim."""
    email = f"perm-{uuid.uuid4().hex[:8]}@miliano-teste.com.br"
    r = admin.post(
        f"{API}/users",
        json={"name": "Gestor Restrito", "email": email, "password": SENHA,
              "role": "manager", "permissoes": ["pedidos"]},
        timeout=TIMEOUT,
    )
    assert r.status_code == 201, r.text
    criado = r.json()
    yield criado
    admin.delete(f"{API}/users/{criado['id']}", timeout=TIMEOUT)


class TestTelasPorUsuario:
    def test_login_devolve_so_as_telas_liberadas(self, conta):
        s = _entrar(conta["email"])
        assert s.me["modulos"] == ["pedidos"]
        assert s.get(f"{API}/auth/me", timeout=TIMEOUT).json()["modulos"] == ["pedidos"]

    def test_tela_liberada_abre(self, conta):
        s = _entrar(conta["email"])
        assert s.get(f"{API}/orders", timeout=TIMEOUT).status_code == 200

    def test_tela_nao_liberada_e_bloqueada_na_api(self, conta):
        s = _entrar(conta["email"])
        for rota in ("/leads", "/dashboard/stats", "/payments", "/forms", "/activities"):
            assert s.get(f"{API}{rota}", timeout=TIMEOUT).status_code == 403, rota

    def test_leitura_de_apoio_nao_vira_escrita(self, conta):
        """Quem tem Pedidos lê restaurantes (o seletor do pedido precisa), mas
        não cria nem edita restaurante."""
        s = _entrar(conta["email"])
        assert s.get(f"{API}/restaurants", timeout=TIMEOUT).status_code == 200
        r = s.post(f"{API}/restaurants", json={"name": "Não Pode", "category": "X"},
                   timeout=TIMEOUT)
        assert r.status_code == 403

    def test_busca_global_respeita_as_telas(self, conta, admin, restaurante):
        s = _entrar(conta["email"])
        achados = s.get(f"{API}/search", params={"q": restaurante["name"]},
                        timeout=TIMEOUT).json()["results"]
        assert not [a for a in achados if a["tipo"] == "Restaurante"]

    def test_mudanca_de_acesso_vale_na_hora(self, conta, admin):
        s = _entrar(conta["email"])
        assert s.get(f"{API}/leads", timeout=TIMEOUT).status_code == 403
        admin.put(f"{API}/users/{conta['id']}", json={"permissoes": ["pedidos", "funil"]},
                  timeout=TIMEOUT)
        # A mesma sessão, sem sair e entrar de novo.
        assert s.get(f"{API}/leads", timeout=TIMEOUT).status_code == 200

    def test_todas_as_telas(self, conta, admin):
        admin.put(f"{API}/users/{conta['id']}", json={"todas_as_telas": True}, timeout=TIMEOUT)
        s = _entrar(conta["email"])
        assert "financeiro" in s.me["modulos"] and "dashboard" in s.me["modulos"]

    def test_tela_inexistente_e_recusada(self, admin):
        r = admin.post(
            f"{API}/users",
            json={"name": "X", "email": f"x-{uuid.uuid4().hex[:6]}@miliano-teste.com.br",
                  "password": SENHA, "permissoes": ["usuarios"]},
            timeout=TIMEOUT,
        )
        # "usuarios" é sempre só do administrador: não se dá a um gestor.
        assert r.status_code == 422

    def test_gestor_nao_gerencia_usuarios(self, conta):
        s = _entrar(conta["email"])
        assert s.get(f"{API}/users", timeout=TIMEOUT).status_code == 403


class TestControleDaSenha:
    def test_admin_troca_a_senha_e_a_sessao_antiga_cai(self, conta, admin):
        s = _entrar(conta["email"])
        assert s.get(f"{API}/auth/me", timeout=TIMEOUT).status_code == 200

        nova = "Outra-Senha-2026"
        r = admin.put(f"{API}/users/{conta['id']}", json={"password": nova}, timeout=TIMEOUT)
        assert r.status_code == 200

        # Quem estava logado com a senha antiga é posto para fora...
        assert s.get(f"{API}/auth/me", timeout=TIMEOUT).status_code == 401
        # ...a senha antiga não entra mais, e a nova entra.
        r = requests.post(f"{API}/auth/login",
                          json={"email": conta["email"], "password": SENHA}, timeout=TIMEOUT)
        assert r.status_code == 401
        _entrar(conta["email"], nova)

    def test_senha_nunca_volta_na_listagem(self, conta, admin):
        usuarios = admin.get(f"{API}/users", timeout=TIMEOUT).json()
        alvo = next(u for u in usuarios if u["id"] == conta["id"])
        assert "password_hash" not in alvo and "password" not in alvo

    def test_admin_desativa_e_a_sessao_cai(self, conta, admin):
        s = _entrar(conta["email"])
        admin.put(f"{API}/users/{conta['id']}", json={"active": False}, timeout=TIMEOUT)
        assert s.get(f"{API}/orders", timeout=TIMEOUT).status_code in (401, 403)
