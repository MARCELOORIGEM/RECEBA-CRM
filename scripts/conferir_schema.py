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
  - o código Python, por AST, tirando os campos de cada escrita
    (`repo.inserir`, `repo.atualizar`, `repo.incrementar`,
    `repo.atualizar_onde`), as colunas usadas em filtros e buscas
    (`repo.filtro("t").igual("coluna", ...)`, `um_por`, `existe`, `somar`) e
    os campos dos modelos Pydantic que viram linha via `model_dump()`.

Os filtros entram porque um nome de coluna errado ali não falha no import nem
no teste que não passa por aquela rota: só quando alguém clica no filtro, em
produção, como erro 500.

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


# Métodos de `repo` que gravam: nome -> (posição do dicionário de campos).
ESCRITAS = {"inserir": 1, "atualizar": 2, "incrementar": 2, "atualizar_onde": 2}
# Métodos de `repo` que recebem (tabela, coluna, ...).
LEITURAS_POR_COLUNA = {"um_por", "existe", "somar", "campo_de_ordenacao", "coluna"}
# Métodos de `Filtro` cujo primeiro argumento é uma coluna.
CONDICOES = {"igual", "diferente", "em", "fora", "desde", "ate", "antes_de",
             "verdadeiro", "nulo"}


def _texto(no) -> str | None:
    return no.value if isinstance(no, ast.Constant) and isinstance(no.value, str) else None


def _tabela_do_filtro(no) -> str | None:
    """Desce a cadeia `repo.filtro("t").igual(...).desde(...)` até o início.

    Devolve a tabela de `repo.filtro("t")` ou `Filtro("t")`, ou None quando a
    cadeia começa numa variável (`f.igual(...)`), resolvida à parte.
    """
    while isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute):
        if no.func.attr == "filtro" and no.args:
            return _texto(no.args[0])
        no = no.func.value
    if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "Filtro":
        return _texto(no.args[0]) if no.args else None
    return None


class ColetorDeCampos(ast.NodeVisitor):
    """Colunas usadas em cada tabela: gravadas, filtradas ou buscadas."""

    def __init__(self, campos: dict[str, set[str]]) -> None:
        # `campos` é compartilhado entre os arquivos; `vars` NÃO pode ser.
        # Nomes como `doc` e `patch` se repetem em quase todo router: um
        # coletor único faria o `doc` de pedidos emprestar campos ao de
        # usuários, e o resultado acusaria dezenas de colunas inexistentes.
        self.campos = campos
        self.vars: dict[str, set[str]] = {}
        # `f = repo.filtro("orders")` -> {"f": "orders"}, para resolver as
        # condições acrescentadas depois em linhas separadas.
        self.filtros: dict[str, str] = {}

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
            tabela = _tabela_do_filtro(node.value)
            if tabela:
                self.filtros[nome] = tabela
            chaves = self._chaves(node.value)
            if chaves:
                self.vars[nome] = self.vars.get(nome, set()) | chaves
        self.generic_visit(node)

    def visit_Subscript(self, node):
        # doc["campo"] = ... — só atribuição. Ler `doc["name"]` não grava
        # nada; contado, acusava `orders.name` porque o `doc` de um cadastro
        # lido em `_resolve_party` tem o mesmo nome do `doc` do pedido.
        if (
            isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            self.vars.setdefault(node.value.id, set()).add(node.slice.value)
        self.generic_visit(node)

    def visit_Call(self, node):
        f = node.func
        if isinstance(f, ast.Attribute):
            tabela = _texto(node.args[0]) if node.args else None
            dono = f.value

            # repo.inserir("t", {...}), repo.atualizar("t", id, {...}), ...
            if isinstance(dono, ast.Name) and dono.id == "repo" and tabela:
                pos = ESCRITAS.get(f.attr)
                if pos is not None and len(node.args) > pos:
                    self.campos[tabela] |= self._chaves(node.args[pos])
                for kw in node.keywords:
                    if f.attr == "incrementar" and kw.arg == "definir":
                        self.campos[tabela] |= self._chaves(kw.value)
                if f.attr in LEITURAS_POR_COLUNA and len(node.args) > 1:
                    coluna = _texto(node.args[1])
                    if coluna:
                        self.campos[tabela].add(coluna)
                if f.attr in ("listar", "paginar"):
                    for kw in node.keywords:
                        if kw.arg == "ordenar_por" and _texto(kw.value):
                            self.campos[tabela].add(kw.value.value)

            # <filtro>.igual("coluna", ...) e <filtro>.busca(termo, [...])
            if f.attr in CONDICOES or f.attr == "busca":
                alvo = _tabela_do_filtro(dono)
                if alvo is None and isinstance(dono, ast.Name):
                    alvo = self.filtros.get(dono.id)
                if alvo:
                    if f.attr == "busca" and len(node.args) > 1 and isinstance(node.args[1], ast.List):
                        self.campos[alvo] |= {c for c in map(_texto, node.args[1].elts) if c}
                    elif f.attr in CONDICOES and node.args and _texto(node.args[0]):
                        self.campos[alvo].add(node.args[0].value)
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

    # Tabela que o código nunca toca pelo `repo` é suspeita: ou sobrou do
    # Mongo, ou só é usada por SQL escrito à mão — que este script não lê.
    orfas = sorted(t for t in tabelas if t not in codigo)
    escritas_sem_tabela = sorted(c for c in codigo if c not in tabelas)

    print(f"\ntabelas no schema: {len(tabelas)}")
    print(f"tabelas com coluna faltando: {problemas}")
    if orfas:
        print(f"tabelas só usadas por SQL à mão (não conferidas): {', '.join(orfas)}")
    if escritas_sem_tabela:
        problemas += 1
        print(f"  ESCRITA SEM TABELA: {', '.join(escritas_sem_tabela)}")

    print("OK — schema cobre o código." if not problemas else "\nFalta ajustar o schema.")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
