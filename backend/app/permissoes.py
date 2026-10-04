"""O que cada usuário pode ver e fazer.

O administrador escolhe, por usuário, quais telas ele enxerga. A escolha vale
na API, não só no menu: esconder o item de navegação sem bloquear a rota
deixaria os dados a uma chamada de distância de quem souber o endereço.

Regras:

- **Administrador** vê e faz tudo. A lista dele é ignorada.
- **Gestor** vê só os módulos marcados. `permissoes` NULL (contas criadas
  antes desta escolha existir) significa todos — atualizar o sistema não pode
  trancar ninguém do lado de fora.
- **Leitura de apoio.** Algumas telas precisam LER a lista de outro módulo:
  o pedido escolhe restaurante e entregador num seletor; o financeiro escolhe
  o credor; relatórios somam pedidos e pagamentos. Quem tem o módulo que
  precisa ganha a leitura do outro, mas não a escrita: o gestor de pedidos vê
  o nome do restaurante no seletor e não consegue editar o cadastro dele.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from .deps import get_current_user

# Chave -> rótulo. A ordem é a do menu. "usuarios" não entra: é sempre só do
# administrador, e dar esse acesso a um gestor seria dar o controle de tudo.
MODULOS: dict[str, str] = {
    "dashboard": "Dashboard",
    "pedidos": "Pedidos",
    "funil": "Funil",
    "atividades": "Atividades",
    "restaurantes": "Restaurantes",
    "entregadores": "Entregadores",
    "formularios": "Formulários",
    "financeiro": "Financeiro",
    "relatorios": "Relatórios",
    "integracoes": "Integrações",
}

# Módulo -> quem mais pode LER os dados dele, como apoio.
LEITURA_DE_APOIO: dict[str, set[str]] = {
    "restaurantes": {"pedidos", "financeiro", "atividades"},
    "entregadores": {"pedidos", "financeiro"},
    "funil": {"atividades"},
    "pedidos": {"relatorios", "restaurantes", "entregadores"},  # ficha do cadastro
    "financeiro": {"relatorios"},
}

METODOS_DE_LEITURA = {"GET", "HEAD", "OPTIONS"}


def modulos_de(user: dict) -> list[str]:
    """Módulos efetivos do usuário, na ordem do menu."""
    if user.get("role") == "admin":
        return list(MODULOS)
    escolhidos = user.get("permissoes")
    if escolhidos is None:
        return list(MODULOS)
    return [m for m in MODULOS if m in set(escolhidos)]


def pode(user: dict, modulo: str, *, escrita: bool = False) -> bool:
    meus = set(modulos_de(user))
    if modulo in meus:
        return True
    if escrita:
        return False
    return bool(meus & LEITURA_DE_APOIO.get(modulo, set()))


def acesso(modulo: str, *, tambem: tuple[str, ...] = ()):
    """Dependência de router: leitura pelas regras de apoio, escrita só com o
    próprio módulo (ou um dos `tambem`, que contam como donos).

    Vai em `APIRouter(dependencies=[...])`, então cobre toda rota do arquivo —
    inclusive as que forem acrescentadas depois, sem ninguém lembrar.
    """
    async def verificar(request: Request, user: dict = Depends(get_current_user)) -> None:
        escrita = request.method not in METODOS_DE_LEITURA
        if pode(user, modulo, escrita=escrita):
            return
        # Os `tambem` contam só se o usuário TEM o módulo. Com a leitura de
        # apoio deles, o acesso vazava em cadeia: Pedidos lê Restaurantes como
        # apoio, Restaurantes é dono de Atividades — e um gestor só de Pedidos
        # acabava lendo a agenda inteira.
        meus = set(modulos_de(user))
        if meus & set(tambem):
            return
        rotulo = MODULOS.get(modulo, modulo)
        raise HTTPException(
            status_code=403,
            detail=f"Seu usuário não tem acesso a {rotulo}. Peça ao administrador.",
        )

    return verificar
