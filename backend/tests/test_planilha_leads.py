"""Leitura da planilha do Funil, sem servidor.

Os casos aqui são os que aparecem na vida real: o modelo voltando preenchido,
o CSV do Excel em português (ponto e vírgula, Windows-1252), dinheiro escrito
de cinco jeitos e cabeçalho digitado à mão.
"""
import io
import os

import pytest

os.environ.setdefault("JWT_SECRET", "teste")

from app.planilha_leads import (  # noqa: E402
    COLUNAS, PlanilhaInvalida, _dinheiro, gerar_modelo, interpretar, ler_arquivo,
)


def _ler(dados, nome="x.csv"):
    return interpretar(ler_arquivo(dados, nome))


def test_modelo_em_branco_volta_valido():
    """Baixar o modelo e importar sem mexer: os dois exemplos entram."""
    res = _ler(gerar_modelo(), "modelo.xlsx")
    assert res.erros == []
    assert [v["name"] for v in res.validos] == ["Padaria Estrela", "Temakeria Onda"]
    assert res.validos[0]["source"] == "indicacao"
    assert res.validos[1]["stage"] == "negociacao"
    assert res.validos[1]["estimated_value"] == 5400.0


def test_funil_atual_exportado_volta_igual():
    leads = [{"name": "Lead Exportado", "phone": "11999990000", "source": "whatsapp",
              "stage": "proposta", "estimated_value": 1500.5}]
    res = _ler(gerar_modelo(leads), "funil.xlsx")
    v = res.validos[0]
    assert (v["name"], v["source"], v["stage"], v["estimated_value"]) == (
        "Lead Exportado", "whatsapp", "proposta", 1500.5)


def test_csv_do_excel_brasileiro():
    """Ponto e vírgula e Windows-1252, como o Excel em português salva."""
    texto = "Nome do estabelecimento;Origem;Etapa;Valor estimado (R$)\n" \
            "Pastelaria São João;Prospecção ativa;Em negociação;R$ 3.200,00\n"
    res = _ler(texto.encode("cp1252"))
    assert res.erros == []
    v = res.validos[0]
    assert v["name"] == "Pastelaria São João"
    assert (v["source"], v["stage"], v["estimated_value"]) == ("prospeccao", "negociacao", 3200.0)


def test_cabecalho_digitado_a_mao():
    texto = "NOME;  celular ;E-MAIL;Cidade\nBar do Zé;11 98888-0000;ze@bar.com.br;Osasco\n"
    v = _ler(texto.encode()).validos[0]
    assert (v["name"], v["phone"], v["email"], v["city"]) == (
        "Bar do Zé", "11 98888-0000", "ze@bar.com.br", "Osasco")


@pytest.mark.parametrize("bruto,esperado", [
    ("3200", 3200.0), ("3.200", 3200.0), ("3.200,50", 3200.5), ("R$ 1.250.000,00", 1250000.0),
    ("3,2 mil", 3200.0), (1500, 1500.0), ("", 0.0), (None, 0.0), ("12.5", 12.5),
])
def test_dinheiro(bruto, esperado):
    assert _dinheiro(bruto) == esperado


def test_erros_por_linha_com_numero_do_excel():
    texto = ("Nome;Etapa;Origem;Valor estimado\n"
             "Ok Bar;Novo;Site;100\n"
             ";Novo;;\n"                          # sem nome
             "Etapa Torta;Fechado;;\n"            # etapa que não existe
             "Perdido Sem Motivo;Perdido;;\n"     # perdido exige motivo
             "Valor Torto;Novo;;dez reais\n")     # valor ilegível
    res = _ler(texto.encode())
    assert [v["name"] for v in res.validos] == ["Ok Bar"]
    linhas = {e["linha"]: e["motivo"] for e in res.erros}
    assert set(linhas) == {3, 4, 5, 6}
    assert "obrigatório" in linhas[3]
    assert '"Fechado" não existe' in linhas[4]
    assert "Motivo da perda" in linhas[5]
    assert "não é um valor em reais" in linhas[6]


def test_linhas_em_branco_e_titulo_em_cima_sao_ignorados():
    texto = "\n\nNome;Cidade\nA;X\n;\nB;Y\n"
    res = _ler(texto.encode())
    assert [v["name"] for v in res.validos] == ["A", "B"]
    assert res.total == 2


def test_colunas_desconhecidas_sao_avisadas_e_nao_quebram():
    res = _ler("Nome;CNPJ;Faturamento anual\nA;123;9\n".encode())
    assert res.validos and res.colunas_ignoradas == ["CNPJ", "Faturamento anual"]


@pytest.mark.parametrize("dados,nome,trecho", [
    (b"", "x.csv", "vazio"),
    (b"Cidade;Telefone\nX;1\n", "x.csv", "Nome do estabelecimento"),
    (b"\xd0\xcf\x11\xe0qualquer", "antigo.xls", ".xls"),
    (b"PK\x03\x04lixo", "quebrado.xlsx", "Excel"),
])
def test_arquivo_invalido_explica_o_que_fazer(dados, nome, trecho):
    with pytest.raises(PlanilhaInvalida, match=trecho):
        _ler(dados, nome)


def test_telefone_numerico_do_excel_nao_vira_decimal():
    """O Excel guarda 11988881234 como número; não pode voltar '11988881234.0'."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Nome do estabelecimento", "Telefone"])
    ws.append(["Lanchonete", 11988881234])
    buf = io.BytesIO()
    wb.save(buf)
    assert _ler(buf.getvalue(), "x.xlsx").validos[0]["phone"] == "11988881234"


def test_modelo_tem_todas_as_colunas_e_listas():
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(gerar_modelo()))
    ws = wb["Leads"]
    assert [c.value for c in ws[1]] == [c.titulo for c in COLUNAS]
    assert len(ws.data_validations.dataValidation) == 2  # Origem e Etapa
    assert "Instruções" in wb.sheetnames
