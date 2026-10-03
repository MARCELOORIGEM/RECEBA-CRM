"""Fixtures compartilhadas pelos testes de API.

Os testes falam HTTP com a API, então rodam tanto contra o backend local
(`REACT_APP_BACKEND_URL=http://localhost:8001`) quanto contra o preview.
"""
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# As credenciais saíram do código (ver abaixo), mas rodar a suíte local não
# deveria exigir exportar quatro variáveis à mão. O backend/.env já tem as
# contas desta instalação e já é ignorado pelo Git: ler dele é o caminho que
# funciona sem configuração e sem segredo versionado.
# `override=False`: o que já estiver no ambiente ganha — é assim que o CI
# aponta a suíte para as contas dele.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001"
).rstrip("/")
API = f"{BASE_URL}/api"
TIMEOUT = 20

# Os padrões eram o e-mail e a senha REAIS do administrador. Num repositório
# publicado, isso é a conta do sistema entregue a quem clonar — e os testes
# rodam igual lendo do ambiente, que é de onde o CI já os passa.
ADMIN = {
    "email": os.environ.get("ADMIN_EMAIL", "admin@local.test"),
    "password": os.environ.get("ADMIN_PASSWORD", "SenhaLocal@2026"),
}
MANAGER = {
    "email": os.environ.get("MANAGER_EMAIL", "gestor@local.test"),
    "password": os.environ.get("MANAGER_PASSWORD", "SenhaLocal@2026"),
}


def _sessao(credenciais):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=credenciais, timeout=TIMEOUT)
    if r.status_code == 429:
        pytest.skip("Bloqueio de força bruta ativo; rode a suíte de novo em alguns minutos.")
    assert r.status_code == 200, f"login falhou: {r.status_code} {r.text}"
    # Cookie Secure não gruda em HTTP: o Bearer cobre os dois cenários.
    token = r.cookies.get("access_token")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    s.me = r.json()
    return s


@pytest.fixture(scope="session")
def admin():
    return _sessao(ADMIN)


@pytest.fixture(scope="session")
def manager():
    return _sessao(MANAGER)


@pytest.fixture
def nome_unico():
    return lambda prefixo: f"{prefixo} {uuid.uuid4().hex[:8]}"


@pytest.fixture
def restaurante(admin, nome_unico):
    """Cria um restaurante e apaga no fim do teste."""
    r = admin.post(
        f"{API}/restaurants",
        json={"name": nome_unico("Rest Teste"), "category": "Teste", "commission_rate": 10},
        timeout=TIMEOUT,
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    yield doc
    # Apaga os pedidos do teste antes do cadastro: excluir só o restaurante
    # deixaria pedidos órfãos acumulando na base a cada rodada.
    pedidos = admin.get(
        f"{API}/orders", params={"restaurant_id": doc["id"], "page_size": 200}, timeout=TIMEOUT
    )
    if pedidos.status_code == 200:
        for p in pedidos.json()["items"]:
            admin.delete(f"{API}/orders/{p['id']}", timeout=TIMEOUT)
    atividades = admin.get(
        f"{API}/activities",
        params={"related_type": "restaurante", "related_id": doc["id"]},
        timeout=TIMEOUT,
    )
    if atividades.status_code == 200:
        for a in atividades.json()["items"]:
            admin.delete(f"{API}/activities/{a['id']}", timeout=TIMEOUT)
    admin.delete(f"{API}/restaurants/{doc['id']}", params={"force": "true"}, timeout=TIMEOUT)


@pytest.fixture
def entregador(admin, nome_unico):
    r = admin.post(
        f"{API}/drivers", json={"name": nome_unico("Entregador Teste")}, timeout=TIMEOUT
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    yield doc
    admin.delete(f"{API}/drivers/{doc['id']}", params={"force": "true"}, timeout=TIMEOUT)
