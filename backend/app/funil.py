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
    # ---------------------------------------------------------- em trabalho
    Status("a_visitar", "A visitar", "aberto",
           descricao="Lead na carteira, visita ainda não feita"),
    Status("agendado_visita", "Agendado visita", "aberto",
           descricao="Visita marcada com o estabelecimento"),
    Status("nao_localizado", "Não localizado", "aberto",
           descricao="O BD não encontrou o endereço; vale tentar de novo"),
    Status("fechado_no_local", "Fechado (horário de funcionamento)", "aberto",
           descricao="Estava fechado na hora da visita; voltar no horário de funcionamento"),
    Status("responsavel_ausente", "Responsável ausente", "aberto",
           descricao="Aberto, mas sem quem decide no local"),
    Status("segunda_visita", "Segunda visita", "aberto",
           descricao="Precisa voltar ao local para concluir"),
    Status("colhendo_dados", "Colhendo dados", "aberto",
           descricao="Interessado; levantando cardápio, CNPJ e dados de contato"),
    Status("agendado_reuniao", "Agendado reunião", "aberto",
           descricao="Reunião marcada com o responsável"),
    Status("reuniao", "Reunião", "aberto",
           descricao="Reunião feita, em negociação"),
    Status("taxa_especial", "Taxa especial", "aberto",
           descricao="Pediu condição ou taxa diferenciada; em avaliação"),
    Status("pendencia_cnpj", "Pendência regularização CNPJ", "aberto",
           descricao="Tem CNPJ, mas com pendência a regularizar antes do cadastro"),
    Status("aguardando_documentos", "Aguardando documentos", "aberto",
           descricao="Aceitou; falta enviar documentos ou dados bancários"),
    Status("cadastro_enviado", "Cadastro enviado", "aberto",
           descricao="Cadastro submetido, em análise"),
    Status("aguardando_assinatura", "Aguardando assinatura cliente", "aberto",
           descricao="Contrato enviado, falta o cliente assinar"),
    # -------------------------------------------------------------- ganhos
    Status("contrato_assinado", "Contrato assinado", "ganho",
           descricao="Cliente assinou o contrato"),
    Status("entrando_na_base", "Entrando na base", "ganho",
           descricao="Em cadastro na base da plataforma"),
    Status("aguardando_inicio_operacao", "No aguardo início operação", "ganho",
           descricao="Tudo pronto; esperando o restaurante começar a operar"),
    Status("ativado", "Ativado", "ganho",
           descricao="Restaurante operando na plataforma"),
    # ---------------------------------------------------------- descartados
    Status("sem_interesse", "Sem interesse", "perdido", pede_motivo=True,
           descricao="Recusou — informe o motivo"),
    Status("sem_interesse_delivery", "Não tem interesse em delivery", "perdido",
           descricao="Não quer trabalhar com delivery"),
    Status("sem_cnpj", "Não possui CNPJ", "perdido",
           descricao="Não tem CNPJ para se cadastrar"),
    Status("estabelecimento_inexistente", "Estabelecimento inexistente", "perdido",
           descricao="O estabelecimento não existe (fechou ou nunca existiu no endereço)"),
    Status("exclusividade_ifood", "Exclusividade iFood", "perdido",
           descricao="Tem contrato de exclusividade com o iFood"),
    Status("exclusividade_99food", "Exclusividade 99Food", "perdido",
           descricao="Tem contrato de exclusividade com o 99Food"),
    Status("ja_parceiro", "Já é parceiro", "perdido",
           descricao="Já opera com a plataforma; não é lead novo"),
    Status("fora_da_area", "Fora do perímetro", "perdido",
           descricao="Fora do perímetro de cobertura da operação"),
]

POR_CHAVE: dict[str, Status] = {s.chave: s for s in STATUS}
CHAVES: tuple[str, ...] = tuple(POR_CHAVE)
INICIAL = "a_visitar"
GANHO = "ativado"
# Para onde vai o lead que vira cliente ("Virar cliente") sem já estar num
# status de ganho: o contrato assinado é o fechamento.
CONVERSAO = "contrato_assinado"
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
