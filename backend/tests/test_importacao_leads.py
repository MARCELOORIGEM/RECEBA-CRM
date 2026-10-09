"""Importação de planilha no Funil, pela API.

A leitura do arquivo tem testes próprios (test_planilha_leads.py). Aqui fica o
que só a rota garante: simular não grava, importar grava tudo de uma vez, o
que já existe não duplica e o modelo baixa como Excel.
"""
import uuid

from .conftest import API, TIMEOUT


def _csv(*linhas: str) -> bytes:
    return ("\r\n".join(linhas) + "\r\n").encode("cp1252")


def _importar(sessao, dados: bytes, simular: bool):
    return sessao.post(
        f"{API}/leads/importar",
        params={"simular": str(simular).lower()},
        files={"arquivo": ("leads.csv", dados, "text/csv")},
        timeout=60,
    )


def _apagar_por_nome(admin, nomes):
    leads = admin.get(f"{API}/leads", params={"page_size": 200}, timeout=TIMEOUT).json()["items"]
    for lead in leads:
        if lead["name"] in nomes:
            admin.delete(f"{API}/leads/{lead['id']}", timeout=TIMEOUT)


class TestImportacao:
    def test_modelo_baixa_como_excel(self, admin):
        r = admin.get(f"{API}/leads/modelo", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.content[:2] == b"PK"
        assert "spreadsheetml" in r.headers["content-type"]

    def test_simular_nao_grava_e_importar_grava(self, admin):
        marca = uuid.uuid4().hex[:6]
        nomes = [f"Importado {marca} A", f"Importado {marca} B"]
        dados = _csv(
            "Nome do estabelecimento;Telefone;Origem;Etapa;Valor estimado (R$)",
            f"{nomes[0]};(11) 9{marca[:4]}-0001;Indicação;Novo;1.000,00",
            f"{nomes[1]};(11) 9{marca[:4]}-0002;Site;Proposta;250",
            "Linha Torta;;;Fechado;",
        )
        try:
            r = _importar(admin, dados, simular=True)
            assert r.status_code == 200, r.text
            corpo = r.json()
            assert (corpo["novos"], len(corpo["erros"]), corpo["importados"]) == (2, 1, 0)
            visiveis = admin.get(f"{API}/leads", params={"search": marca}, timeout=TIMEOUT).json()
            assert visiveis["total"] == 0, "simular gravou leads"

            r = _importar(admin, dados, simular=False)
            assert r.json()["importados"] == 2
            leads = admin.get(f"{API}/leads", params={"search": marca}, timeout=TIMEOUT).json()["items"]
            por_nome = {l["name"]: l for l in leads}
            assert por_nome[nomes[0]]["source"] == "indicacao"
            assert por_nome[nomes[1]]["stage"] == "proposta"
            assert por_nome[nomes[0]]["origem"] == "planilha"
            assert por_nome[nomes[0]]["stage_history"][0]["stage"] == "novo"

            # Reimportar o mesmo arquivo não duplica.
            de_novo = _importar(admin, dados, simular=True).json()
            assert de_novo["novos"] == 0 and len(de_novo["duplicados"]) == 2
        finally:
            _apagar_por_nome(admin, nomes)

    def test_arquivo_sem_coluna_de_nome_explica(self, admin):
        r = _importar(admin, _csv("Cidade;Telefone", "X;1"), simular=True)
        assert r.status_code == 422
        assert "Nome do estabelecimento" in r.json()["detail"]
