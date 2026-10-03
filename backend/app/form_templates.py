"""Modelos padrão de formulário.

Fonte única das perguntas: a carga inicial (`seed.py`) e o construtor da tela
leem daqui. Enquanto isso vivia duplicado em Python e em JavaScript, bastava
alguém ajustar um lado para os dois desandarem.

Nada aqui é obrigatório para quem monta o formulário — é o ponto de partida.
Toda pergunta pode ser editada, removida, reordenada, e novas podem ser
acrescentadas na tela.
"""

BANCOS = [
    "Banco do Brasil", "Bradesco", "Caixa Econômica Federal", "Itaú", "Santander",
    "Nubank", "Banco Inter", "C6 Bank", "PicPay", "Mercado Pago", "PagBank",
    "Banco PAN", "Sicredi", "Sicoob",
    # Sem "Outro" na lista: o campo tem escrita livre (allow_other), que já
    # desenha o botão "Outro:" do formulário original. Os dois juntos viravam
    # duas opções com o mesmo nome, e uma delas não abria nada.
]


def campo(key, label, tipo="texto", obrigatorio=False, ajuda="", opcoes=None, dica="",
          outro=False):
    return {
        "key": key,
        "label": label,
        "type": tipo,
        "required": obrigatorio,
        "placeholder": dica,
        "help": ajuda,
        "options": opcoes or [],
        "allow_other": outro,
    }


# Reproduz o formulário que a operação usava no Google Forms: mesmo texto,
# mesma ordem, mesmas instruções e a mesma lista de bancos.
MODELO_ENTREGADOR = {
    "title": "Cadastro de Entregadores",
    "description": (
        "Preencha as informações abaixo com atenção. Os dados serão utilizados "
        "para cadastro e processamento dos pagamentos relacionados à operação."
    ),
    "target": "entregador",
    "success_message": (
        "Cadastro recebido! Nossa equipe vai conferir os dados e entrar em contato."
    ),
    "active": True,
    "fields": [
        campo("name", "Nome completo", "texto", True),
        campo("cpf", "CPF", "cpf", True,
              "Informe apenas os 11 números do CPF, sem pontos ou traços.",
              dica="00000000000"),
        campo("phone", "Celular / WhatsApp", "telefone", True,
              "Informe o número com DDD", dica="(00) 00000-0000"),
        campo("vehicle_type", "Modal", "escolha", True, opcoes=["Moto", "Bicicleta"]),
        # Múltipla escolha com "Outro:", como no original — a lista não cobre
        # todo banco que aparece.
        campo("bank", "Banco", "escolha", True, opcoes=BANCOS, outro=True),
        campo("bank_agency", "Agência", "texto", True,
              "Informe o número da agência. Caso sua instituição não utilize agência, "
              "informe “Não se aplica”."),
        campo("account_type", "Tipo de Conta", "escolha", True,
              'Para bancos digitais (Nubank, C6, entre outros) escolha a opção '
              '"Conta Corrente"',
              opcoes=["Conta Corrente", "Conta Poupança"]),
        campo("bank_account", "Número da Conta", "texto", True,
              "Informe o número da conta com o dígito, quando houver. "
              "Exemplo: 12345678-9",
              dica="12345678-9"),
        campo("pix_key_type", "Tipo de chave PIX", "escolha", True,
              opcoes=["CPF", "Celular", "E-mail", "Chave aleatória"]),
        campo("pix_key", "Chave PIX", "texto", False,
              "Digite exatamente a chave PIX cadastrada em sua instituição financeira."),
    ],
}

MODELO_RESTAURANTE = {
    "title": "Cadastro de Restaurantes",
    "description": (
        "Preencha os dados do estabelecimento. Nossa equipe entra em contato para "
        "concluir o credenciamento."
    ),
    "target": "restaurante",
    "success_message": "Cadastro recebido! Em breve entramos em contato.",
    "active": True,
    "fields": [
        campo("name", "Nome do restaurante", "texto", True),
        campo("cnpj", "CNPJ", "texto", True, dica="00.000.000/0001-00"),
        campo("category", "Tipo de cozinha", "selecao", True,
              opcoes=["Hamburgueria", "Pizzaria", "Japonesa", "Comida Caseira",
                      "Açaiteria", "Padaria", "Lanchonete", "Doceria", "Outro"]),
        campo("contact_person", "Nome do responsável", "texto", True),
        campo("phone", "Celular / WhatsApp", "telefone", True,
              "Informe o número com DDD", dica="(00) 00000-0000"),
        campo("email", "E-mail", "email", False),
        campo("address", "Endereço completo", "texto", True,
              "Rua, número, bairro e cidade"),
        campo("notes", "Observações", "textarea", False,
              "Horário de funcionamento, média de pedidos por dia, o que mais quiser contar"),
    ],
}

MODELO_LEAD = {
    "title": "Quero ser parceiro",
    "description": "Deixe seus dados que nosso time comercial entra em contato.",
    "target": "lead",
    "success_message": "Recebemos seu contato! Falaremos com você em breve.",
    "active": True,
    "fields": [
        campo("name", "Nome do estabelecimento", "texto", True),
        campo("contact_name", "Seu nome", "texto", True),
        campo("phone", "Celular / WhatsApp", "telefone", True,
              "Informe o número com DDD", dica="(00) 00000-0000"),
        campo("email", "E-mail", "email", False),
        campo("city", "Cidade", "texto", True),
        campo("category", "Tipo de estabelecimento", "texto", False),
        campo("notes", "Como podemos ajudar?", "textarea", False),
    ],
}

MODELOS = {
    "entregador": MODELO_ENTREGADOR,
    "restaurante": MODELO_RESTAURANTE,
    "lead": MODELO_LEAD,
}
