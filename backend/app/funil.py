"""Status do Funil — a régua da visita de campo.

O funil deixou de ser o de venda consultiva genérica (novo, contatado,
negociação, proposta) e passou a seguir o trabalho dos BDs na rua: o lead é um
restaurante a visitar, e cada status diz o que aconteceu na visita ou o que
falta para ele ser ativado.

Fonte única: o CHECK do banco (sql/005), o `Literal` da API, a planilha e o
painel (frontend/src/lib/funil.js) seguem esta lista. A coluna no banco
continua chamada `stage` — o nome é interno; para quem usa, é "Status".

Grupos:
- **aberto**: ainda em trabalho. É o que conta como "em aberto" nos números.
- **ganho**: ativado — o que vira cliente.
- **perdido**: descartado. Entra na taxa de conversão como não convertido.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Status:
    chave: str
    rotulo: str
    grupo: str           # aberto | ganho | perdido
    pede_motivo: bool = False
    descricao: str = ""


STATUS: list[Status] = [
    Status("a_visitar", "A visitar", "aberto",
           descricao="Lead na carteira, visita ainda não feita"),
    Status("nao_localizado", "Não localizado", "aberto",
           descricao="Endereço não encontrado ou estabelecimento não existe mais no local"),
    Status("fechado_no_local", "Fechado no local", "aberto",
           descricao="Estabelecimento estava fechado na hora da visita"),
    Status("responsavel_ausente", "Responsável ausente", "aberto",
           descricao="Aberto, mas sem quem decide no local"),
    Status("colhendo_dados", "Colhendo dados", "aberto",
           descricao="Interessado; levantando cardápio, CNPJ e dados de contato"),
    Status("reuniao", "Reunião", "aberto",
           descricao="Reunião marcada ou feita com o responsável"),
    Status("segunda_visita", "Segunda visita", "aberto",
           descricao="Precisa voltar ao local para concluir"),
    Status("aguardando_documentos", "Aguardando documentos", "aberto",
           descricao="Aceitou; falta enviar documentos ou dados bancários"),
    Status("cadastro_enviado", "Cadastro enviado", "aberto",
           descricao="Cadastro submetido, em análise/aprovação"),
    Status("ativado", "Ativado", "ganho",
           descricao="Restaurante ativo na plataforma"),
    Status("sem_interesse", "Sem interesse", "perdido", pede_motivo=True,
           descricao="Recusou — informe o motivo"),
    Status("ja_parceiro", "Já é parceiro", "perdido",
           descricao="Já opera com a plataforma; não é lead novo"),
    Status("fora_da_area", "Fora da área", "perdido",
           descricao="Fora da área de cobertura da operação"),
]

POR_CHAVE: dict[str, Status] = {s.chave: s for s in STATUS}
CHAVES: tuple[str, ...] = tuple(POR_CHAVE)
INICIAL = "a_visitar"
GANHO = "ativado"
ABERTOS: tuple[str, ...] = tuple(s.chave for s in STATUS if s.grupo == "aberto")
GANHOS: tuple[str, ...] = tuple(s.chave for s in STATUS if s.grupo == "ganho")
PERDIDOS: tuple[str, ...] = tuple(s.chave for s in STATUS if s.grupo == "perdido")

# As seis etapas da versão anterior, para converter o que já estava gravado e
# aceitar planilhas antigas. Usado pelo sql/005 (escrito à mão, conferido no
# teste) e pela leitura de planilha.
LEGADO: dict[str, str] = {
    "novo": "a_visitar",
    "contatado": "colhendo_dados",
    "negociacao": "reuniao",
    "proposta": "cadastro_enviado",
    "ganho": "ativado",
    "perdido": "sem_interesse",
}


def pede_motivo(chave: str) -> bool:
    s = POR_CHAVE.get(chave)
    return bool(s and s.pede_motivo)


def e_perdido(chave: str) -> bool:
    return chave in PERDIDOS
