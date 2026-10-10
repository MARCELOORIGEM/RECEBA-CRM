"""Planilha do Funil: o modelo para baixar e a leitura do que volta preenchido.

Tudo aqui é puro — bytes entram, linhas saem —, sem tocar no banco. Quem
decide o que gravar (e o que já existe) é a rota em `routers/leads.py`.

Três cuidados que custam caro quando faltam:

O CABEÇALHO É DE GENTE. A coluna chama "Nome do estabelecimento", não `name`,
e quem preenche escreve "Origem", "origem", "ORIGEM " ou "Origem do lead".
Os nomes são comparados sem acento, caixa ou pontuação, e cada coluna aceita
alguns apelidos.

O CSV É O DO EXCEL BRASILEIRO. "Salvar como CSV" no Excel em português grava
com ponto e vírgula e em Windows-1252, não em UTF-8 com vírgula. As duas
coisas são detectadas; sem isso, "Prospecção" chegaria como "ProspecÃ§Ã£o"
e a planilha inteira seria uma coluna só.

DINHEIRO VEM ESCRITO DE QUALQUER JEITO. "R$ 3.200,00", "3200", "3.200" e
"3,2 mil" aparecem na mesma planilha. O que dá para ler com segurança é lido;
o resto vira erro na linha, em vez de um número errado gravado em silêncio.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError

from . import funil
from .models import LeadInput

LIMITE_LINHAS = 2000
LIMITE_BYTES = 5 * 1024 * 1024

# Origem e status com os MESMOS nomes da tela do Funil. A planilha mostra o
# rótulo; o banco guarda a chave.
ORIGENS = {
    "indicacao": "Indicação",
    "instagram": "Instagram",
    "prospeccao": "Prospecção ativa",
    "site": "Site",
    "whatsapp": "WhatsApp",
    "evento": "Evento",
    "outro": "Outro",
}
# Em maiúsculas, como a planilha da operação escreve ("NÃO LOCALIZADO").
# Na leitura, caixa e acento não importam.
ETAPAS = {st.chave: st.rotulo.upper() for st in funil.STATUS}


@dataclass(frozen=True)
class Coluna:
    campo: str
    titulo: str
    largura: int
    apelidos: tuple[str, ...] = ()


# As dez primeiras são a planilha da operação, na mesma ordem (LEAD ID ... OBS).
# As demais são opcionais e ficam à direita: quem não usa, apaga.
COLUNAS: list[Coluna] = [
    Coluna("codigo_externo", "LEAD ID", 12, ("id do lead", "lead", "codigo", "id")),
    Coluna("name", "NOME LEAD", 30,
           ("nome", "nome do estabelecimento", "estabelecimento", "restaurante", "empresa",
            "razao social", "nome do lead")),
    Coluna("endereco", "ENDEREÇO", 32, ("endereco completo", "logradouro", "rua")),
    Coluna("bairro", "BAIRRO", 18, ()),
    Coluna("bd_id", "BD ID", 10, ("id bd", "id do bd")),
    Coluna("bd_nome", "NOME BD", 18, ("bd", "nome do bd", "vendedor", "consultor")),
    Coluna("lider", "LIDER", 16, ("lider do bd", "supervisor", "coordenador")),
    Coluna("data_visita", "DATA VISITA", 14, ("data da visita", "visita", "data")),
    Coluna("stage", "STATUS", 24, ("etapa", "estagio", "fase", "situacao")),
    Coluna("notes", "OBS", 40, ("observacao", "observacoes", "obs.", "notas", "anotacoes")),
    Coluna("phone", "TELEFONE", 18, ("celular", "whatsapp", "fone", "tel")),
    Coluna("contact_name", "CONTATO", 20, ("nome do contato", "responsavel pelo local", "dono")),
    Coluna("email", "E-MAIL", 26, ("email", "e mail", "correio")),
    Coluna("city", "CIDADE", 16, ("municipio",)),
    Coluna("category", "CATEGORIA", 16, ("segmento", "tipo", "ramo")),
    Coluna("source", "ORIGEM", 18, ("origem do lead", "fonte", "canal")),
    Coluna("estimated_value", "VALOR ESTIMADO (R$)", 18,
           ("valor estimado", "valor", "potencial", "valor mensal")),
    Coluna("lost_reason", "MOTIVO", 24, ("motivo da perda", "motivo perda", "motivo do descarte")),
    Coluna("owner_name", "RESPONSÁVEL", 18, ("responsavel", "dono do lead")),
]

EXEMPLOS = [
    {"codigo_externo": "12345678", "name": "Restaurante 123", "endereco": "RUA H, 357 - UNIÃO",
     "bairro": "UNIÃO", "bd_id": "BD01", "bd_nome": "JUNIAO", "lider": "TARCÍSIO",
     "data_visita": "", "stage": "NÃO LOCALIZADO", "notes": ""},
    {"codigo_externo": "12345679", "name": "Pizzaria Bella", "endereco": "AV. BRASIL, 1200",
     "bairro": "CENTRO", "bd_id": "BD02", "bd_nome": "MARIANA", "lider": "TARCÍSIO",
     "data_visita": date(2026, 10, 5), "stage": "REUNIÃO", "notes": "Dono pediu retorno às 15h",
     "phone": "(11) 98888-1234"},
]


def _chave(texto: Any) -> str:
    """'Valor estimado (R$)' -> 'valor estimado r'. Sem acento, caixa ou sinais."""
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# Cabeçalho normalizado -> campo. O título oficial, a chave em inglês (quem
# exportou de outro sistema) e os apelidos.
_CABECALHO: dict[str, str] = {}
for _c in COLUNAS:
    for _nome in (_c.titulo, _c.campo, *_c.apelidos):
        _CABECALHO.setdefault(_chave(_nome), _c.campo)

_ROTULOS = {"source": ORIGENS, "stage": ETAPAS}
# Rótulo ou chave, normalizados -> chave. "Prospecção ativa", "prospecção",
# "prospeccao" e "PROSPECCAO" viram todos `prospeccao`.
_VALORES: dict[str, dict[str, str]] = {
    campo: {**{_chave(k): k for k in mapa}, **{_chave(v): k for k, v in mapa.items()}}
    for campo, mapa in _ROTULOS.items()
}
_VALORES["source"].update({"prospeccao ativa": "prospeccao", "insta": "instagram",
                           "zap": "whatsapp", "wpp": "whatsapp"})
# Etapas da versão anterior ("Novo", "Em negociação"...) e jeitos comuns de
# escrever os status: uma planilha antiga ainda importa.
_VALORES["stage"].update({_chave(k): v for k, v in funil.LEGADO.items()})
_VALORES["stage"].update({
    "em negociacao": "reuniao", "proposta enviada": "cadastro_enviado",
    "reuniao agendada": "reuniao", "2a visita": "segunda_visita", "2 visita": "segunda_visita",
    "retornar": "segunda_visita", "fechado no local": "fechado_no_local",
    "estabelecimento fechado": "fechado_no_local", "nao encontrado": "nao_localizado",
    "aguardando documentacao": "aguardando_documentos", "ativo": "ativado",
    "parceiro": "ja_parceiro", "sem interesse": "sem_interesse", "recusou": "sem_interesse",
})


# ------------------------------------------------------------------ leitura
class PlanilhaInvalida(ValueError):
    """Problema com o arquivo inteiro (formato, tamanho, cabeçalho)."""


def _linhas_xlsx(dados: bytes) -> list[list[Any]]:
    from openpyxl import load_workbook

    try:
        livro = load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
    except Exception:
        raise PlanilhaInvalida("Não consegui abrir o arquivo como planilha do Excel (.xlsx).")
    # A aba "Leads" do modelo; se o usuário renomeou, a primeira aba.
    aba = livro["Leads"] if "Leads" in livro.sheetnames else livro.worksheets[0]
    linhas = [list(r) for r in aba.iter_rows(values_only=True)]
    livro.close()
    return linhas


def _linhas_csv(dados: bytes) -> list[list[Any]]:
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            texto = dados.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise PlanilhaInvalida("Não consegui ler o texto do CSV.")
    primeira = texto.split("\n", 1)[0]
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    return [linha for linha in csv.reader(io.StringIO(texto), delimiter=separador)]


def ler_arquivo(dados: bytes, nome: str) -> list[list[Any]]:
    """Linhas cruas do arquivo, cabeçalho incluído."""
    if len(dados) > LIMITE_BYTES:
        raise PlanilhaInvalida("Arquivo maior que 5 MB. Divida em partes menores.")
    if not dados:
        raise PlanilhaInvalida("O arquivo está vazio.")
    # Pelo conteúdo, não pela extensão: .xlsx é um zip e começa com "PK".
    if dados[:2] == b"PK":
        return _linhas_xlsx(dados)
    if (nome or "").lower().endswith((".xls",)):
        raise PlanilhaInvalida(
            "Formato .xls (Excel antigo) não é aceito. No Excel, use "
            "Arquivo > Salvar como > Pasta de Trabalho do Excel (.xlsx)."
        )
    return _linhas_csv(dados)


# ------------------------------------------------------------- interpretação
def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        # Telefone digitado como número no Excel volta como 11988881234.0.
        return str(int(valor))
    return str(valor).strip()


def _dinheiro(valor: Any) -> float:
    """'R$ 3.200,00' -> 3200.0. Levanta ValueError se não der para ler."""
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip().lower().replace("r$", "").replace(" ", "")
    mil = s.endswith("mil")
    if mil:
        s = s[:-3]
    if "," in s:
        # Formato brasileiro: ponto é milhar, vírgula é decimal.
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):
        # "3.200" ou "1.250.000": pontos de milhar, sem decimal.
        s = s.replace(".", "")
    numero = float(s)
    return numero * 1000 if mil else numero


def _data(valor: Any):
    """DATA VISITA: célula de data do Excel, "05/10/2026", "5/10/26" ou ISO."""
    from datetime import datetime

    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(texto[:10] if formato == "%Y-%m-%d" else texto, formato).date()
        except ValueError:
            continue
    raise ValueError(texto)


@dataclass
class Resultado:
    validos: list[dict] = field(default_factory=list)
    erros: list[dict] = field(default_factory=list)
    colunas_ignoradas: list[str] = field(default_factory=list)
    total: int = 0


_ROTULO_DO_CAMPO = {c.campo: c.titulo for c in COLUNAS}


def interpretar(linhas: list[list[Any]]) -> Resultado:
    """Linhas cruas -> leads validados e erros por linha.

    A numeração das linhas é a do Excel (o cabeçalho é a linha 1), para quem
    for corrigir achar a linha certa sem fazer conta.
    """
    res = Resultado()
    # O cabeçalho é a primeira linha com algum texto: há quem deixe um título
    # ou linha em branco em cima.
    inicio = next((i for i, l in enumerate(linhas) if any(_texto(v) for v in l)), None)
    if inicio is None:
        raise PlanilhaInvalida("A planilha não tem nenhuma linha preenchida.")

    mapa: dict[int, str] = {}
    for idx, titulo in enumerate(linhas[inicio]):
        campo = _CABECALHO.get(_chave(titulo))
        if campo and campo not in mapa.values():
            mapa[idx] = campo
        elif _texto(titulo):
            res.colunas_ignoradas.append(_texto(titulo))
    if "name" not in mapa.values():
        raise PlanilhaInvalida(
            'Não achei a coluna "NOME LEAD" no cabeçalho. '
            "Baixe o modelo e use os mesmos títulos de coluna."
        )

    corpo = linhas[inicio + 1:]
    for deslocamento, linha in enumerate(corpo):
        numero = inicio + 2 + deslocamento
        bruto = {campo: (linha[idx] if idx < len(linha) else None) for idx, campo in mapa.items()}
        if not any(_texto(v) for v in bruto.values()):
            continue  # linha em branco no meio da planilha
        res.total += 1
        if res.total > LIMITE_LINHAS:
            raise PlanilhaInvalida(
                f"A planilha tem mais de {LIMITE_LINHAS} leads. Divida em arquivos menores."
            )

        dados: dict[str, Any] = {}
        problemas: list[str] = []
        for campo, valor in bruto.items():
            if campo == "estimated_value":
                try:
                    dados[campo] = _dinheiro(valor)
                except ValueError:
                    problemas.append(f'"{_texto(valor)}" não é um valor em reais')
            elif campo == "data_visita":
                try:
                    dados[campo] = _data(valor)
                except ValueError:
                    problemas.append(f'DATA VISITA "{_texto(valor)}" não é uma data (use 05/10/2026)')
            elif campo in _VALORES:
                texto = _texto(valor)
                if not texto:
                    continue  # vazio: o padrão do modelo (Prospecção / Novo)
                chave = _VALORES[campo].get(_chave(texto))
                if chave:
                    dados[campo] = chave
                else:
                    opcoes = ", ".join(_ROTULOS[campo].values())
                    problemas.append(f'{_ROTULO_DO_CAMPO[campo]} "{texto}" não existe ({opcoes})')
            else:
                dados[campo] = _texto(valor)

        if funil.pede_motivo(dados.get("stage", "")) and not dados.get("lost_reason"):
            rotulo = funil.POR_CHAVE[dados["stage"]].rotulo.upper()
            problemas.append(f'STATUS "{rotulo}" precisa da coluna MOTIVO preenchida')

        if not problemas:
            try:
                lead = LeadInput(**dados).model_dump()
            except ValidationError as e:
                for err in e.errors():
                    campo = str(err["loc"][0]) if err.get("loc") else ""
                    problemas.append(f"{_ROTULO_DO_CAMPO.get(campo, campo)}: {_msg(err)}")
            else:
                # Quais células vieram preenchidas: na atualização de um lead
                # que já existe, célula vazia não apaga o que está gravado.
                preenchidos = [c for c, v in bruto.items() if _texto(v)]
                res.validos.append({"linha": numero, "_preenchidos": preenchidos, **lead})
                continue
        res.erros.append({
            "linha": numero,
            "nome": _texto(bruto.get("name")) or "(sem nome)",
            "motivo": "; ".join(problemas),
        })
    return res


def _msg(err: dict) -> str:
    tipo = err.get("type", "")
    if tipo in ("string_too_short", "missing"):
        return "obrigatório"
    if tipo == "string_too_long":
        return "texto longo demais"
    if tipo.startswith("greater_than") or tipo.startswith("less_than"):
        return "valor fora do permitido"
    return err.get("msg", "valor inválido")


# ------------------------------------------------------------------ modelo
def gerar_modelo(leads: list[dict] | None = None) -> bytes:
    """O .xlsx para baixar, no formato da planilha da operação.

    Sem `leads`, o modelo com duas linhas de exemplo. Com `leads`, o funil
    atual no mesmo formato — dá para editar e importar de volta: o LEAD ID
    reconhece cada lead e a linha atualiza em vez de duplicar.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    livro = Workbook()
    aba = livro.active
    aba.title = "Leads"

    # As cores da planilha da operação: verde-escuro com letra branca.
    fundo = PatternFill("solid", fgColor="1F4E4C")
    fundo_opcional = PatternFill("solid", fgColor="3B6B68")
    fino = Side(style="thin", color="BBBBBB")
    for i, col in enumerate(COLUNAS, start=1):
        celula = aba.cell(row=1, column=i, value=col.titulo)
        celula.font = Font(bold=True, color="FFFFFF")
        # As dez primeiras são as da operação; as opcionais, um tom mais claro.
        celula.fill = fundo if i <= 10 else fundo_opcional
        celula.alignment = Alignment(horizontal="center", vertical="center")
        celula.border = Border(bottom=fino)
        aba.column_dimensions[get_column_letter(i)].width = col.largura
    aba.row_dimensions[1].height = 22
    aba.freeze_panes = "B2"
    aba.auto_filter.ref = f"A1:{get_column_letter(len(COLUNAS))}1"

    def celula_de(lead: dict, c: Coluna):
        valor = lead.get(c.campo)
        if c.campo == "source":
            return ORIGENS.get(valor, valor or "")
        if c.campo == "stage":
            return ETAPAS.get(valor, valor or "")
        if c.campo == "estimated_value":
            return valor or None
        if c.campo == "data_visita":
            return valor or None
        return valor or ""

    registros = EXEMPLOS if leads is None else leads
    for registro in registros:
        aba.append([celula_de(registro, c) for c in COLUNAS])

    coluna_data = next(i for i, c in enumerate(COLUNAS, 1) if c.campo == "data_visita")
    for linha in range(2, len(registros) + 2):
        aba.cell(row=linha, column=coluna_data).number_format = "DD/MM/YYYY"

    # Listas suspensas: o BD escolhe o status e a origem em vez de digitar —
    # e não inventa "Fechou" ou "Insta".
    ultima = max(LIMITE_LINHAS + 1, len(registros) + 1)
    for campo, mapa in _ROTULOS.items():
        letra = get_column_letter(next(i for i, c in enumerate(COLUNAS, 1) if c.campo == campo))
        lista = DataValidation(
            type="list", formula1='"' + ",".join(mapa.values()) + '"', allow_blank=True,
            showErrorMessage=True, errorTitle="Valor fora da lista",
            error="Escolha um valor da lista.",
        )
        lista.add(f"{letra}2:{letra}{ultima}")
        aba.add_data_validation(lista)

    instrucoes = livro.create_sheet("Instruções")
    instrucoes.column_dimensions["A"].width = 24
    instrucoes.column_dimensions["B"].width = 90
    texto = [
        ("Como preencher", ""),
        ("Uma linha por lead", "Comece na linha 2 da aba Leads. Linhas em branco são ignoradas."),
        ("Obrigatório", "Só NOME LEAD. As outras colunas podem ficar vazias."),
        ("LEAD ID", "Código do lead na operação. Se o LEAD ID já existir no funil, a linha "
                    "ATUALIZA esse lead (status, data da visita, OBS...) em vez de criar outro. "
                    "Célula vazia não apaga o que já está gravado."),
        ("DATA VISITA", "Formato 05/10/2026."),
        ("STATUS", "Escolha na lista. Vazio = A VISITAR."),
    ]
    for st in funil.STATUS:
        detalhe = st.descricao + (" — exige MOTIVO." if st.pede_motivo else "")
        texto.append(("   " + st.rotulo.upper(), detalhe))
    texto += [
        ("MOTIVO", "Obrigatório quando o STATUS for SEM INTERESSE."),
        ("Colunas opcionais", "TELEFONE em diante (cabeçalho mais claro). Pode apagar as que "
                              "não usa."),
        ("Sem LEAD ID", "Lead com o mesmo e-mail ou telefone de um que já está no funil não "
                        "é importado de novo."),
        ("Limite", f"Até {LIMITE_LINHAS} leads por arquivo. Salve como .xlsx ou .csv."),
        ("Antes de gravar", "O sistema mostra uma prévia do que entra, do que muda e do que "
                            "tem erro, linha por linha. Nada é gravado até você confirmar."),
    ]
    for i, (a, b) in enumerate(texto, start=1):
        instrucoes.cell(row=i, column=1, value=a).font = Font(bold=not a.startswith("   "))
        instrucoes.cell(row=i, column=2, value=b).alignment = Alignment(wrap_text=True)

    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()
