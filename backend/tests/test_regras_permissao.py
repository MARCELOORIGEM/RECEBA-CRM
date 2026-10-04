"""Regras de `app/permissoes.py`, sem servidor.

O caso que motivou o arquivo: a leitura de apoio vazava em cadeia (Pedidos
lia Restaurantes como apoio, Restaurantes é dono de Atividades, e um gestor só
de Pedidos lia a agenda inteira).
"""
import asyncio
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET", "teste")

from app.permissoes import MODULOS, acesso, modulos_de  # noqa: E402


class _Req:
    def __init__(self, method):
        self.method = method


def _status(dep, user, metodo):
    try:
        asyncio.run(dep(_Req(metodo), user))
        return 200
    except HTTPException as e:
        return e.status_code


def _gestor(*mods):
    return {"role": "manager", "permissoes": list(mods)}


ATIVIDADES = acesso("atividades", tambem=("funil", "restaurantes", "entregadores"))


@pytest.mark.parametrize("user,dep,metodo,esperado", [
    # a cadeia que vazava
    (_gestor("pedidos"), ATIVIDADES, "GET", 403),
    # dono indireto de atividades: a ficha do restaurante registra interação
    (_gestor("restaurantes"), ATIVIDADES, "POST", 200),
    # leitura de apoio sim, escrita não
    (_gestor("pedidos"), acesso("restaurantes"), "GET", 200),
    (_gestor("pedidos"), acesso("restaurantes"), "POST", 403),
    (_gestor("relatorios"), acesso("financeiro"), "GET", 200),
    (_gestor("relatorios"), acesso("financeiro"), "PUT", 403),
    # conta antiga (NULL) e administrador veem tudo
    ({"role": "manager", "permissoes": None}, acesso("financeiro"), "POST", 200),
    ({"role": "admin", "permissoes": []}, acesso("integracoes"), "DELETE", 200),
    # lista vazia: entra e não vê nada
    (_gestor(), acesso("dashboard"), "GET", 403),
])
def test_regras(user, dep, metodo, esperado):
    assert _status(dep, user, metodo) == esperado


def test_modulos_sempre_na_ordem_do_menu():
    assert modulos_de(_gestor("integracoes", "pedidos")) == ["pedidos", "integracoes"]
    assert modulos_de({"role": "admin"}) == list(MODULOS)


def test_corte_de_sessao_no_mesmo_segundo():
    """Login e troca de senha no mesmo segundo: a sessão antiga tem de cair.

    Com o `iat` inteiro do JWT os dois empatavam e ela sobrevivia — passou
    despercebido aqui (banco a 380 ms separa os dois) e quebrou no CI.
    """
    from datetime import datetime, timedelta, timezone

    from app.deps import sessao_cortada

    login = datetime(2026, 10, 4, 21, 0, 0, 100_000, tzinfo=timezone.utc)
    troca = login + timedelta(milliseconds=300)
    novo_login = troca + timedelta(milliseconds=200)
    user = {"sessoes_desde": troca}

    antigo = {"iat": int(login.timestamp()), "emitido_em": login.timestamp()}
    novo = {"iat": int(novo_login.timestamp()), "emitido_em": novo_login.timestamp()}
    assert sessao_cortada(user, antigo)
    assert not sessao_cortada(user, novo)
    # Token de antes do `emitido_em` existir: na dúvida, derruba.
    assert sessao_cortada(user, {"iat": int(login.timestamp())})
    # Sem corte gravado, nada cai.
    assert not sessao_cortada({"sessoes_desde": None}, antigo)
