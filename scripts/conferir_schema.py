"""Confere se o schema SQL cobre todo campo que o código grava.

    python scripts/conferir_schema.py

Durante a migração de MongoDB para PostgreSQL, a falha mais provável não é o
SQL estar errado — é o schema estar *incompleto*. No Mongo, gravar um campo que
ninguém declarou funciona: o documento simplesmente ganha mais uma chave. No
Postgres, a mesma linha vira `UndefinedColumnError` em produção, na hora em que
alguém salva um pedido.

Este script lê os dois lados e compara:

  - o SQL, pelo parser de verdade do PostgreSQL (pglast), tirando as colunas
    declaradas em cada CREATE TABLE;
  - o código Python, por AST, tirando os campos de cada insert/update e dos
    modelos Pydantic que viram documento via `model_dump()`.

Achou dois buracos reais na primeira execução: `orders.credited_*` (a
fotografia que torna o estorno exato) não estava no schema, e `created_at_dt`
estava no código sendo uma duplicata BSON de `created_at` — resíduo do Mongo,
que no Postgres não tem mais razão de existir.

Sai com código 1 quando falta coluna, para servir no CI.
"""
import ast
import collections
import glob
import sys
from pathlib import Path

try:
    import pglast
except ImportError:
    print("pglast não instalado. Rode: pip install -r backend/requirements-dev.txt")
    raise SystemExit(2)

RAIZ = Path(__file__).resolve().parent.parent

# Campos que existem no código e NÃO devem virar coluna, com o motivo.
IGNORAR = {
    "_id": "chave interna do Mongo; o Postgres usa a coluna id",
    "created_at_dt": "era uma data BSON duplicando created_at, que no Mongo era "
                     "string; com TIMESTAMPTZ a duplicata deixa de ter função",
}

# Funções que montam um registro e escolhem a tabela em tempo de execução: o
# AST vê `db[colecao].insert_one(doc)`, não `db.leads.insert_one(...)`, então
# os campos passariam despercebidos. `_criar_cadastro`, do formulário público,
# grava nos três destinos — e foi por aqui que `origem_form_id` e
# `extra_fields` quase ficaram de fora do schema.
#
# `comum` recebe o que é montado fora dos ramos (o dicionário `base`); `ramos`
# liga cada `if destino == "..."` à sua tabela. Sem essa separação, os campos
# bancários do entregador apareceriam como "faltando" em leads e restaurantes.
FUNCOES_MULTI_TABELA = {
    "_criar_cadastro": {
        "comum": ("leads", "restaurants", "drivers"),
        "ramos": {"lead": "leads", "restaurante": "restaurants"},
        "senao": "drivers",          # o `else:` do encadeamento
    },
}

# Modelos Pydantic que viram documento inteiro via model_dump().
MODELO_TABELA = {
    "OrderInput": "orders",
    "FormInput": "forms",
    "RestaurantInput": "restaurants",
    "DriverInput": "drivers",
    "ContractInput": "contracts",
    "PaymentInput": "payments",
    "LeadInput": "leads",
    "ActivityInput": "activities",
}


def colunas_do_schema() -> dict[str, set[str]]:
    """Colunas declaradas, lidas com o parser do próprio PostgreSQL."""
    tabelas: dict[str, set[str]] = {}
    for arquivo in sorted((RAIZ / "backend/app/sql").glob("*.sql")):
        sql = arquivo.read_text(encoding="utf-8")
        for bruto in pglast.parse_sql(sql):          # levanta se o SQL for inválido
            stmt = bruto.stmt
            if type(stmt).__name__ != "CreateStmt":
                continue
            tabelas[stmt.relation.relname] = {
                el.colname
                for el in (stmt.tableElts or ())
                if type(el).__name__ == "ColumnDef"
            }
    return tabelas


class ColetorDeCampos(ast.NodeVisitor):
    """Campos gravados em cada coleção, por insert_one/update_one."""

    def __init__(self, campos: dict[str, set[str]]) -> None:
        # `campos` é compartilhado entre os arquivos; `vars` NÃO pode ser.
        # Nomes como `doc` e `patch` se repetem em quase todo router: um
        # coletor único faria o `doc` de pedidos emprestar campos ao de
        # usuários, e o resultado acusaria dezenas de colunas inexistentes.
        self.campos = campos
        self.vars: dict[str, set[str]] = {}

    def _chaves(self, node) -> set[str]:
        out: set[str] = set()
        if isinstance(node, ast.Dict):
            for chave, valor in zip(node.keys, node.values):
                if chave is None:                      # {**outro}
                    out |= self._chaves(valor)
                elif isinstance(chave, ast.Constant) and isinstance(chave.value, str):
                    out.add(chave.value)
        elif isinstance(node, ast.Name):
            out |= self.vars.get(node.id, set())
        return out

    def visit_Assign(self, node):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            nome = node.targets[0].id
            chaves = self._chaves(node.value)
            if chaves:
                self.vars[nome] = self.vars.get(nome, set()) | chaves
        self.generic_visit(node)

    def visit_Subscript(self, node):
        # doc["campo"] = ...
        if (
            isinstance(node.value, ast.Name)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            self.vars.setdefault(node.value.id, set()).add(node.slice.value)
        self.generic_visit(node)

    def visit_Call(self, node):
        f = node.func
        if (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Attribute)
            and isinstance(f.value.value, ast.Name)
            and f.value.value.id == "db"
        ):
            colecao = f.value.attr
            if f.attr in ("insert_one", "insert_many"):
                for arg in node.args:
                    if isinstance(arg, ast.List):
                        for el in arg.elts:
                            self.campos[colecao] |= self._chaves(el)
                    else:
                        self.campos[colecao] |= self._chaves(arg)
            elif f.attr in ("update_one", "update_many") and len(node.args) >= 2:
                alteracao = node.args[1]
                if isinstance(alteracao, ast.Dict):
                    for chave, valor in zip(alteracao.keys, alteracao.values):
                        if isinstance(chave, ast.Constant) and chave.value in ("$set", "$inc"):
                            self.campos[colecao] |= self._chaves(valor)
        self.generic_visit(node)


def _chaves_de_dicts(no) -> set[str]:
    """Chaves de PRIMEIRO NÍVEL dos dicionários atribuídos no trecho.

    Não desce nos valores de propósito: `stage_history` guarda
    `[{"stage": ..., "at": ..., "by": ...}]`, e `at`/`by` são chaves dentro do
    JSONB, não colunas da tabela. Descendo, o conferidor as cobraria como
    colunas que faltam — ruído que ensina a ignorar o relatório.
    """
    out: set[str] = set()
    for filho in ast.walk(no):
        if not isinstance(filho, ast.Assign) or not isinstance(filho.value, ast.Dict):
            continue
        for chave in filho.value.keys:
            if isinstance(chave, ast.Constant) and isinstance(chave.value, str):
                out.add(chave.value)
    return out


def _campos_multi_tabela(func, regra: dict, campos: dict[str, set[str]]) -> None:
    """Separa o que a função monta em comum do que monta em cada ramo."""
    ramos = regra.get("ramos", {})
    senao = regra.get("senao")

    def tabela_do_teste(teste) -> str | None:
        """`destino == "lead"` -> 'leads'."""
        if isinstance(teste, ast.Compare) and len(teste.comparators) == 1:
            alvo = teste.comparators[0]
            if isinstance(alvo, ast.Constant) and isinstance(alvo.value, str):
                return ramos.get(alvo.value)
        return None

    def percorrer(corpo: list, dentro_de_ramo: str | None) -> None:
        for stmt in corpo:
            if isinstance(stmt, ast.If):
                destino = tabela_do_teste(stmt.test)
                percorrer(stmt.body, destino or dentro_de_ramo)
                # O `else:` final é o destino que sobra (aqui, entregador).
                resto_e_elif = len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If)
                percorrer(stmt.orelse, dentro_de_ramo if resto_e_elif else senao)
                continue
            chaves = _chaves_de_dicts(stmt)
            if not chaves:
                continue
            if dentro_de_ramo:
                campos[dentro_de_ramo] |= chaves
            else:
                for tabela in regra["comum"]:
                    campos[tabela] |= chaves

    percorrer(func.body, None)


def campos_do_codigo() -> dict[str, set[str]]:
    campos: dict[str, set[str]] = collections.defaultdict(set)

    for caminho in glob.glob(str(RAIZ / "backend/app/**/*.py"), recursive=True):
        arvore = ast.parse(Path(caminho).read_text(encoding="utf-8"))
        coletor = ColetorDeCampos(campos)       # escopo de variáveis por arquivo
        # Duas passadas: a primeira aprende as variáveis, a segunda resolve os
        # inserts que as usam antes de o visitor tê-las visto.
        coletor.visit(arvore)
        coletor.visit(arvore)

    for caminho in glob.glob(str(RAIZ / "backend/app/**/*.py"), recursive=True):
        arvore = ast.parse(Path(caminho).read_text(encoding="utf-8"))
        for node in ast.walk(arvore):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            regra = FUNCOES_MULTI_TABELA.get(node.name)
            if regra:
                _campos_multi_tabela(node, regra, campos)

    modelos = ast.parse((RAIZ / "backend/app/models.py").read_text(encoding="utf-8"))
    for node in modelos.body:
        if isinstance(node, ast.ClassDef) and node.name in MODELO_TABELA:
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    campos[MODELO_TABELA[node.name]].add(item.target.id)
    return campos


def main() -> int:
    tabelas = colunas_do_schema()
    codigo = campos_do_codigo()

    problemas = 0
    for tabela in sorted(tabelas):
        faltando = sorted((codigo.get(tabela, set()) - tabelas[tabela]) - set(IGNORAR))
        if faltando:
            problemas += 1
            print(f"  FALTA em {tabela}: {', '.join(faltando)}")

    # Tabela que o código nunca escreve é suspeita: ou sobrou do Mongo, ou a
    # rota que deveria usá-la ainda não foi migrada.
    orfas = sorted(t for t in tabelas if t not in codigo)
    escritas_sem_tabela = sorted(c for c in codigo if c not in tabelas)

    print(f"\ntabelas no schema: {len(tabelas)}")
    print(f"tabelas com coluna faltando: {problemas}")
    if orfas:
        print(f"tabelas que o código não escreve: {', '.join(orfas)}")
    if escritas_sem_tabela:
        problemas += 1
        print(f"  ESCRITA SEM TABELA: {', '.join(escritas_sem_tabela)}")

    print("OK — schema cobre o código." if not problemas else "\nFalta ajustar o schema.")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
