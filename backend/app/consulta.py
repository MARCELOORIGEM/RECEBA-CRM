"""Construtor de filtros SQL.

Os routers montavam dicionários no dialeto do Mongo:

    query = {"status": "entregue", "created_at": {"$gte": inicio}}
    query.update(regex_filter(busca, ["code", "customer_name"]))

Aqui o mesmo filtro é montado com métodos nomeados:

    f = Filtro("orders")
    f.igual("status", "entregue")
    f.desde("created_at", inicio)
    f.busca(termo, ["code", "customer_name"])

Três coisas que este módulo garante, e que valem mais que a economia de
digitação:

VALOR NUNCA ENTRA NO SQL. Todo valor vira `$1`, `$2`… e viaja separado, pelo
protocolo. Não existe caminho em que o que o usuário digitou seja interpretado
como SQL — nem o "(11) 9" que quebrava o regex na versão anterior, nem um
`'; DROP TABLE` colado no campo de busca.

NOME DE COLUNA É CONFERIDO. Identificador não pode ser parâmetro em SQL, então
o nome da coluna é interpolado no texto da consulta. Ele é validado contra o
schema (`COLUNAS`) antes disso: um `sort_field` vindo da query string que não
seja coluna de verdade é recusado, em vez de virar SQL.

A CONSTRUÇÃO É PURA. `Filtro.onde()` devolve (texto, argumentos) sem tocar em
banco nenhum, o que permite testar cada caso sem servidor — é o que
`tests/test_consulta.py` faz.
"""
from __future__ import annotations

import re
from pathlib import Path

# ----------------------------------------------------------------- colunas
# Lidas do próprio schema: a lista de colunas válidas não pode ser uma segunda
# cópia, mantida à mão, do que o SQL já declara — as duas divergiriam no
# primeiro ALTER TABLE.
_DIR_SQL = Path(__file__).resolve().parent / "sql"
_RE_TABELA = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);", re.S)
_RE_COLUNA = re.compile(r"^\s{4}(\w+)\s+[A-Z]", re.M)


def _carregar_colunas() -> dict[str, frozenset[str]]:
    schema = (_DIR_SQL / "001_schema.sql").read_text(encoding="utf-8")
    tabelas: dict[str, frozenset[str]] = {}
    for nome, corpo in _RE_TABELA.findall(schema):
        tabelas[nome] = frozenset(_RE_COLUNA.findall(corpo))
    return tabelas


COLUNAS: dict[str, frozenset[str]] = _carregar_colunas()


class ColunaInvalida(ValueError):
    """Pedido de coluna que não existe. Erro de programação, não do usuário."""


def coluna(tabela: str, nome: str) -> str:
    """Nome de coluna conferido e entre aspas, pronto para entrar no SQL."""
    validas = COLUNAS.get(tabela)
    if validas is None:
        raise ColunaInvalida(f"tabela desconhecida: {tabela}")
    if nome not in validas:
        raise ColunaInvalida(f"{tabela} não tem a coluna {nome!r}")
    return f'"{nome}"'


# ------------------------------------------------------------------ filtro
class Filtro:
    """Condições de um WHERE, acumuladas e combinadas com AND."""

    def __init__(self, tabela: str, *, primeiro_parametro: int = 1) -> None:
        """`primeiro_parametro` desloca a numeração: com 4, o primeiro valor
        vira `$4`. Serve para juntar vários filtros num mesmo comando — os
        contadores da agenda saem todos de um SELECT só."""
        if tabela not in COLUNAS:
            raise ColunaInvalida(f"tabela desconhecida: {tabela}")
        self.tabela = tabela
        self._cond: list[str] = []
        self._args: list[object] = []
        self._base = primeiro_parametro - 1

    # -- internos ---------------------------------------------------------
    def _marcador(self, valor: object) -> str:
        """Guarda o valor e devolve o `$n` que o representa."""
        self._args.append(valor)
        return f"${len(self._args) + self._base}"

    def _col(self, nome: str) -> str:
        return coluna(self.tabela, nome)

    # -- condições --------------------------------------------------------
    def igual(self, nome: str, valor, *, ignorar_vazio: bool = True) -> "Filtro":
        """`coluna = valor`.

        Vazio é ignorado por padrão porque os routers recebem filtros opcionais
        da query string: `status=""` significa "não filtre por status", não
        "traga quem tem status vazio".
        """
        if ignorar_vazio and (valor is None or valor == ""):
            return self
        self._cond.append(f"{self._col(nome)} = {self._marcador(valor)}")
        return self

    def diferente(self, nome: str, valor) -> "Filtro":
        self._cond.append(f"{self._col(nome)} <> {self._marcador(valor)}")
        return self

    def em(self, nome: str, valores) -> "Filtro":
        """`coluna = ANY(...)`. Lista vazia não filtra nada."""
        valores = list(valores)
        if not valores:
            return self
        self._cond.append(f"{self._col(nome)} = ANY({self._marcador(valores)})")
        return self

    def fora(self, nome: str, valores) -> "Filtro":
        valores = list(valores)
        if not valores:
            return self
        self._cond.append(f"NOT ({self._col(nome)} = ANY({self._marcador(valores)}))")
        return self

    def desde(self, nome: str, valor) -> "Filtro":
        """`coluna >= valor`. Nulo não filtra."""
        if valor is None or valor == "":
            return self
        self._cond.append(f"{self._col(nome)} >= {self._marcador(valor)}")
        return self

    def ate(self, nome: str, valor) -> "Filtro":
        """`coluna <= valor`."""
        if valor is None or valor == "":
            return self
        self._cond.append(f"{self._col(nome)} <= {self._marcador(valor)}")
        return self

    def antes_de(self, nome: str, valor) -> "Filtro":
        """`coluna < valor` — fronteira exclusiva, para recortes de dia."""
        if valor is None or valor == "":
            return self
        self._cond.append(f"{self._col(nome)} < {self._marcador(valor)}")
        return self

    def verdadeiro(self, nome: str, valor: bool) -> "Filtro":
        self._cond.append(f"{self._col(nome)} = {self._marcador(bool(valor))}")
        return self

    def nulo(self, nome: str, *, e_nulo: bool = True) -> "Filtro":
        self._cond.append(f"{self._col(nome)} IS {'' if e_nulo else 'NOT '}NULL")
        return self

    def busca(self, termo: str, colunas: list[str]) -> "Filtro":
        """Busca parcial, sem diferenciar maiúsculas, em várias colunas.

        O índice GIN com pg_trgm atende este ILIKE. No Mongo a busca usava
        regex — que índice nenhum atendia, então varria a coleção — e o índice
        TEXT que existia casava só palavra inteira: "cant" não achava
        "Cantina". Aqui acha.

        O `%` e o `_` do termo são escapados: quem digita "100%" procura o
        texto "100%", não "100 seguido de qualquer coisa".
        """
        termo = (termo or "").strip()
        if not termo or not colunas:
            return self
        escapado = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        marcador = self._marcador(f"%{escapado}%")
        partes = [f"{self._col(c)} ILIKE {marcador}" for c in colunas]
        self._cond.append("(" + " OR ".join(partes) + ")")
        return self

    def bruto(self, sql: str, *valores) -> "Filtro":
        """Condição que os métodos acima não cobrem.

        O SQL vem do código, nunca do usuário; os valores continuam indo como
        parâmetro. Use `{}` no lugar de cada `$n` — a numeração é resolvida
        aqui, porque ela depende de quantas condições já entraram antes.
        """
        marcadores = [self._marcador(v) for v in valores]
        self._cond.append("(" + sql.format(*marcadores) + ")")
        return self

    # -- saída ------------------------------------------------------------
    def onde(self) -> tuple[str, list]:
        """(trecho WHERE, argumentos). Sem condições, o trecho é vazio."""
        if not self._cond:
            return "", []
        return "WHERE " + " AND ".join(self._cond), list(self._args)

    @property
    def argumentos(self) -> list:
        return list(self._args)

    def __len__(self) -> int:
        return len(self._cond)


# ------------------------------------------------------------- ordenação
def ordenacao(tabela: str, campo: str, direcao: str = "desc") -> str:
    """`ORDER BY` com a coluna conferida.

    A direção não é interpolada a partir da entrada: só existem dois valores
    possíveis e qualquer outra coisa vira DESC. `NULLS LAST` deixa a linha sem
    data no fim, e não no topo, que é onde o Postgres a põe por padrão em DESC
    — numa agenda ordenada por vencimento, a tarefa sem prazo encabeçando a
    lista seria lida como a mais urgente.
    """
    col = coluna(tabela, campo)
    asc = str(direcao).lower() == "asc"
    return f"ORDER BY {col} {'ASC' if asc else 'DESC'} NULLS LAST"
