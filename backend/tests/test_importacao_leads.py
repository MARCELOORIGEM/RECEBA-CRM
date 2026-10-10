"""Importação de planilha no Funil, pela API.

A leitura do arquivo tem testes próprios (test_planilha_leads.py). Aqui fica o
que só a rota garante: simular não grava; importar grava de uma vez; LEAD ID
que já existe ATUALIZA o lead (é assim que a operação devolve a planilha com
o status novo) sem apagar o que a planilha deixou em branco; e o modelo baixa
como Excel.
"""
import uuid

from .conftest import API, TIMEOUT

CABECALHO = "LEAD ID;NOME LEAD;ENDEREÇO;BAIRRO;BD ID;NOME BD;LIDER;DATA VISITA;STATUS;OBS"


def _csv(*linhas: str) -> bytes:
    return ("\r\n".join(linhas) + "\r\n").encode("cp1252")


def _importar(sessao, dados: bytes, simular: bool):
    return sessao.post(
        f"{API}/leads/importar",
        params={"simular": str(simular).lower()},
        files={"arquivo": ("leads.csv", dados, "text/csv")},
        timeout=60,
    )


def _leads_da_marca(admin, marca):
    return admin.get(f"{API}/leads", params={"search": marca, "page_size": 200},
                     timeout=TIMEOUT).json()["items"]


def _apagar(admin, marca):
    for lead in _leads_da_marca(admin, marca):
        admin.delete(f"{API}/leads/{lead['id']}", timeout=TIMEOUT)


class TestImportacao:
    def test_modelo_baixa_como_excel(self, admin):
        r = admin.get(f"{API}/leads/modelo", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.content[:2] == b"PK"
        assert "spreadsheetml" in r.headers["content-type"]

    def test_simular_nao_grava_e_importar_grava(self, admin):
        marca = uuid.uuid4().hex[:6]
        dados = _csv(
            CABECALHO,
            f"{marca}01;Importado {marca} A;RUA H, 357;UNIÃO;BD01;JUNIAO;TARCÍSIO;;NÃO LOCALIZADO;",
            f"{marca}02;Importado {marca} B;AV. X, 10;CENTRO;BD02;MARIANA;TARCÍSIO;05/10/2026;REUNIÃO;ok",
            f"{marca}03;Linha Torta;;;;;;;FECHADO;",
        )
        try:
            corpo = _importar(admin, dados, simular=True).json()
            assert (corpo["novos"], len(corpo["erros"]), corpo["importados"]) == (2, 1, 0)
            assert _leads_da_marca(admin, marca) == [], "simular gravou leads"

            assert _importar(admin, dados, simular=False).json()["importados"] == 2
            por_codigo = {l["codigo_externo"]: l for l in _leads_da_marca(admin, marca)}
            a, b = por_codigo[f"{marca}01"], por_codigo[f"{marca}02"]
            assert (a["stage"], a["bairro"], a["lider"], a["origem"]) == (
                "nao_localizado", "UNIÃO", "TARCÍSIO", "planilha")
            assert (b["stage"], b["data_visita"], b["bd_nome"]) == ("reuniao", "2026-10-05", "MARIANA")
        finally:
            _apagar(admin, marca)

    def test_mesmo_lead_id_atualiza_em_vez_de_duplicar(self, admin):
        """O BD devolve a planilha com o status novo: o lead muda, não duplica."""
        marca = uuid.uuid4().hex[:6]
        primeira = _csv(
            CABECALHO,
            f"{marca}01;Lead {marca};RUA H, 357;UNIÃO;BD01;JUNIAO;TARCÍSIO;;A VISITAR;anotação antiga",
        )
        # Volta com status e data novos e o ENDEREÇO e a OBS em branco.
        segunda = _csv(
            CABECALHO,
            f"{marca}01;Lead {marca};;UNIÃO;BD01;JUNIAO;TARCÍSIO;06/10/2026;SEGUNDA VISITA;",
        )
        try:
            _importar(admin, primeira, simular=False)
            previa = _importar(admin, segunda, simular=True).json()
            assert previa["novos"] == 0
            [mudou] = previa["atualizados"]
            assert "Status: A visitar → Segunda visita" in mudou["mudancas"]
            assert any(m.startswith("Data visita:") for m in mudou["mudancas"])

            assert _importar(admin, segunda, simular=False).json()["atualizados_gravados"] == 1
            [lead] = _leads_da_marca(admin, marca)
            assert (lead["stage"], lead["data_visita"]) == ("segunda_visita", "2026-10-06")
            # Célula vazia não apagou o que estava gravado.
            assert (lead["endereco"], lead["notes"]) == ("RUA H, 357", "anotação antiga")
            assert [h["stage"] for h in lead["stage_history"]] == ["a_visitar", "segunda_visita"]

            # Reimportar igual: nada muda.
            de_novo = _importar(admin, segunda, simular=True).json()
            assert (de_novo["novos"], len(de_novo["atualizados"]), de_novo["inalterados"]) == (0, 0, 1)
        finally:
            _apagar(admin, marca)

    def test_arquivo_sem_coluna_de_nome_explica(self, admin):
        r = _importar(admin, _csv("BAIRRO;STATUS", "X;REUNIÃO"), simular=True)
        assert r.status_code == 422
        assert "NOME LEAD" in r.json()["detail"]
