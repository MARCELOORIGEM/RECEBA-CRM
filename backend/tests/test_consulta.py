"""Testes do construtor de filtros SQL.

Diferente do resto da suíte, estes não falam com a API nem com banco nenhum:
`Filtro.onde()` é função pura, e dá para conferir o SQL gerado caractere a
caractere. É a única parte da migração para PostgreSQL que pode ser verificada
antes de existir um servidor.

Cada teste trava um comportamento que, errado, vira falha em produção:
injeção de SQL, filtro opcional que filtra quando não devia, numeração de
parâmetro trocada entre condições.
"""
import re

import pytest

from app.consulta import COLUNAS, ColunaInvalida, Filtro, coluna, ordenacao


# --------------------------------------------------------- colunas válidas
def test_colunas_vem_do_schema():
    """A lista de colunas é lida do SQL, não mantida à mão em paralelo."""
    assert "orders" in COLUNAS
    assert {"id", "code", "status", "created_at"} <= COLUNAS["orders"]
    # Campo que só existe no Mongo não pode ter sobrevivido à tradução.
    assert "created_at_dt" not in COLUNAS["form_submissions"]
    # A fotografia do estorno precisa estar lá: sem ela o estorno é aproximado.
    assert {"credited_driver_id", "credited_restaurant_id", "credited_amount"} <= COLUNAS["orders"]


def test_leitura_do_schema_bate_com_o_parser_do_postgres():
    """`COLUNAS` lê o schema por expressão regular, porque carregar o parser do
    PostgreSQL só para subir a API seria peso desnecessário em produção. Aqui,
    onde o parser está disponível, as duas leituras são comparadas: se um
    `CREATE TABLE` futuro for escrito num formato que a regex não entende, este
    teste falha antes de alguma coluna sumir silenciosamente da validação.
    """
    pglast = pytest.importorskip("pglast")
    from pathlib import Path

    schema = Path(__file__).resolve().parents[1] / "app" / "sql" / "001_schema.sql"
    real = {}
    for bruto in pglast.parse_sql(schema.read_text(encoding="utf-8")):
        stmt = bruto.stmt
        if type(stmt).__name__ == "CreateStmt":
            real[stmt.relation.relname] = {
                el.colname for el in (stmt.tableElts or ()) if type(el).__name__ == "ColumnDef"
            }

    assert set(COLUNAS) == set(real), "a regex perdeu ou inventou tabelas"
    for tabela, colunas_reais in real.items():
        assert set(COLUNAS[tabela]) == colunas_reais, f"colunas divergentes em {tabela}"


def test_rls_cobre_todas_as_tabelas():
    """Toda tabela precisa de RLS ligado — uma esquecida fica legível por quem
    tiver a chave `anon` do Supabase, que é pública por design (vai no bundle
    do navegador). Em `drivers` isso significaria CPF, conta bancária e chave
    PIX abertos na internet.
    """
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1] / "app" / "sql" / "003_rls.sql").read_text(
        encoding="utf-8"
    )
    protegidas = set(re.findall(r"ALTER TABLE (\w+)\s+ENABLE ROW LEVEL SECURITY", sql))
    assert set(COLUNAS) - protegidas == set(), "tabela sem RLS ficaria pública"
    assert protegidas - set(COLUNAS) == set(), "RLS em tabela que não existe"


def test_rls_nao_usa_force():
    """`FORCE ROW LEVEL SECURITY` sujeitaria também o dono da tabela ao RLS — e
    é como dono que a API conecta. Ligado, derrubaria o sistema inteiro."""
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1] / "app" / "sql" / "003_rls.sql").read_text(
        encoding="utf-8"
    )
    comandos = [l for l in sql.splitlines() if l.strip().upper().startswith("ALTER TABLE")]
    assert comandos, "o arquivo de RLS está vazio"
    assert not any("FORCE" in c.upper() for c in comandos)


def test_coluna_inexistente_e_recusada():
    with pytest.raises(ColunaInvalida):
        coluna("orders", "coluna_que_nao_existe")


def test_tabela_inexistente_e_recusada():
    with pytest.raises(ColunaInvalida):
        Filtro("tabela_que_nao_existe")


def test_nome_de_coluna_malicioso_nao_vira_sql():
    """`sort_field` chega pela query string. Sem a conferência, viraria SQL."""
    with pytest.raises(ColunaInvalida):
        coluna("orders", 'id"; DROP TABLE orders; --')
    with pytest.raises(ColunaInvalida):
        ordenacao("orders", "created_at; DELETE FROM orders")


# ------------------------------------------------------------- condições
def test_filtro_vazio_nao_gera_where():
    onde, args = Filtro("orders").onde()
    assert onde == ""
    assert args == []


def test_igual_parametriza_o_valor():
    f = Filtro("orders").igual("status", "entregue")
    onde, args = f.onde()
    assert onde == 'WHERE "status" = $1'
    assert args == ["entregue"]


def test_valor_malicioso_viaja_como_parametro():
    """O conteúdo é dado, não código — mesmo parecendo um comando."""
    ataque = "'; DROP TABLE orders; --"
    onde, args = Filtro("orders").igual("customer_name", ataque).onde()
    assert onde == 'WHERE "customer_name" = $1'
    assert args == [ataque]
    assert "DROP" not in onde


def test_igual_ignora_vazio():
    """Filtro opcional não preenchido não pode virar `status = ''`."""
    onde, args = Filtro("orders").igual("status", "").igual("driver_id", None).onde()
    assert onde == ""
    assert args == []


def test_igual_aceita_vazio_quando_pedido():
    onde, args = Filtro("orders").igual("driver_id", "", ignorar_vazio=False).onde()
    assert onde == 'WHERE "driver_id" = $1'
    assert args == [""]


def test_condicoes_combinam_com_and_e_numeram_em_ordem():
    f = Filtro("orders")
    f.igual("status", "entregue")
    f.igual("restaurant_id", "r1")
    f.desde("created_at", "2026-01-01")
    onde, args = f.onde()
    assert onde == ('WHERE "status" = $1 AND "restaurant_id" = $2 '
                    'AND "created_at" >= $3')
    assert args == ["entregue", "r1", "2026-01-01"]


def test_em_usa_any_e_lista_vazia_nao_filtra():
    onde, args = Filtro("orders").em("status", ["em_transito", "aguardando_coleta"]).onde()
    assert onde == 'WHERE "status" = ANY($1)'
    assert args == [["em_transito", "aguardando_coleta"]]

    onde, args = Filtro("orders").em("status", []).onde()
    assert onde == ""


def test_intervalo_de_dia_usa_fronteira_exclusiva():
    """`antes_de` existe para o recorte de "ontem" não invadir "hoje"."""
    f = Filtro("orders").desde("created_at", "A").antes_de("created_at", "B")
    onde, args = f.onde()
    assert onde == 'WHERE "created_at" >= $1 AND "created_at" < $2'
    assert args == ["A", "B"]


def test_nulo():
    assert Filtro("orders").nulo("delivered_at").onde()[0] == 'WHERE "delivered_at" IS NULL'
    assert (Filtro("orders").nulo("delivered_at", e_nulo=False).onde()[0]
            == 'WHERE "delivered_at" IS NOT NULL')


# ---------------------------------------------------------------- busca
def test_busca_usa_ilike_em_varias_colunas_com_um_parametro_so():
    f = Filtro("orders").busca("cant", ["code", "customer_name"])
    onde, args = f.onde()
    assert onde == 'WHERE ("code" ILIKE $1 OR "customer_name" ILIKE $1)'
    # Um marcador só: o mesmo termo nas duas colunas.
    assert args == ["%cant%"]


def test_busca_acha_pedaco_de_palavra():
    """O índice TEXT do Mongo casava palavra inteira: "cant" não achava
    "Cantina". O ILIKE com % dos dois lados acha."""
    _, args = Filtro("restaurants").busca("cant", ["name"]).onde()
    assert args == ["%cant%"]


def test_busca_escapa_curinga_do_like():
    """Quem digita "100%" procura o texto "100%", não "100 seguido de tudo"."""
    _, args = Filtro("restaurants").busca("100%", ["name"]).onde()
    assert args == ["%100\\%%"]

    _, args = Filtro("restaurants").busca("a_b", ["name"]).onde()
    assert args == ["%a\\_b%"]


def test_busca_vazia_nao_filtra():
    assert Filtro("orders").busca("", ["code"]).onde()[0] == ""
    assert Filtro("orders").busca("   ", ["code"]).onde()[0] == ""


def test_busca_com_pontuacao_nao_quebra():
    """"(11) 9" quebrava a query na versão com regex. Aqui é só texto."""
    onde, args = Filtro("drivers").busca("(11) 9", ["phone"]).onde()
    assert onde == 'WHERE ("phone" ILIKE $1)'
    assert args == ["%(11) 9%"]


# ----------------------------------------------------------------- bruto
def test_bruto_numera_a_partir_do_que_ja_existe():
    """A numeração depende de quantas condições vieram antes — é justamente o
    que erraria se cada trecho cuidasse da própria."""
    f = Filtro("payments")
    f.igual("status", "pendente")
    f.bruto("due_date < {} OR paid_at IS NULL", "2026-10-03")
    onde, args = f.onde()
    assert onde == 'WHERE "status" = $1 AND (due_date < $2 OR paid_at IS NULL)'
    assert args == ["pendente", "2026-10-03"]


# ------------------------------------------------------------- ordenação
def test_ordenacao_padrao_e_desc_com_nulos_no_fim():
    assert ordenacao("orders", "created_at") == 'ORDER BY "created_at" DESC NULLS LAST'


def test_ordenacao_asc():
    assert ordenacao("payments", "due_date", "asc") == 'ORDER BY "due_date" ASC NULLS LAST'


def test_direcao_desconhecida_vira_desc():
    """A direção nunca é interpolada a partir da entrada."""
    assert ordenacao("orders", "created_at", "; DROP TABLE") .endswith("DESC NULLS LAST")
