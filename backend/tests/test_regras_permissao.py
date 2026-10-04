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
