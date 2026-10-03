"""Modelos de entrada. Tudo que o cliente manda passa por aqui.

A versão anterior aceitava `commission_rate: float` e `status: str` livres — a API
gravava comissão -50% e status "voando" sem reclamar.
"""
from datetime import date
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

Str1 = Annotated[str, Field(min_length=1, max_length=160, strip_whitespace=True)]
StrOpt = Annotated[str, Field(default="", max_length=400, strip_whitespace=True)]
Money = Annotated[float, Field(ge=0, le=10_000_000)]
Percent = Annotated[float, Field(ge=0, le=100)]

RestaurantStatus = Literal["ativo", "em_analise", "suspenso", "inativo"]
DriverStatus = Literal["disponivel", "em_entrega", "offline", "indisponivel"]
VehicleType = Literal["moto", "bike", "carro", "van"]
OrderStatus = Literal["criado", "aguardando_coleta", "em_transito", "entregue", "cancelado"]
PartyType = Literal["restaurante", "entregador"]
RuleType = Literal["taxa_fixa", "valor_km", "comissao_entrega"]
PaymentStatus = Literal["pendente", "pago", "atrasado", "cancelado"]
PaymentMethod = Literal["PIX", "Transferência", "Dinheiro", "Boleto"]
Role = Literal["admin", "manager"]
LeadStage = Literal["novo", "contatado", "negociacao", "proposta", "ganho", "perdido"]
LeadSource = Literal["indicacao", "instagram", "prospeccao", "site", "whatsapp", "evento", "outro"]
ActivityKind = Literal["tarefa", "interacao"]
ActivityType = Literal["ligacao", "whatsapp", "email", "reuniao", "visita", "nota", "tarefa"]
RelatedType = Literal["lead", "restaurante", "entregador", "pedido"]


class LoginInput(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=200)]


class RegisterInput(BaseModel):
    name: Str1
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=200)]


class PasswordChange(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=200)]
    new_password: Annotated[str, Field(min_length=8, max_length=200)]


class ProfileUpdate(BaseModel):
    name: Str1


class UserCreate(BaseModel):
    name: Str1
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=200)]
    role: Role = "manager"


class UserUpdate(BaseModel):
    name: Optional[Str1] = None
    role: Optional[Role] = None
    password: Optional[Annotated[str, Field(min_length=8, max_length=200)]] = None
    active: Optional[bool] = None


class RestaurantInput(BaseModel):
    name: Str1
    category: Str1
    contact_person: StrOpt = ""
    email: StrOpt = ""
    phone: StrOpt = ""
    cnpj: StrOpt = ""
    address: StrOpt = ""
    commission_rate: Percent = 15.0
    status: RestaurantStatus = "ativo"
    notes: StrOpt = ""


# Dados de pagamento do entregador. Viraram campos de verdade do cadastro, em
# vez de texto solto: é com eles que o repasse é feito, e antes o formulário de
# recrutamento vivia fora do CRM (numa planilha do Google).
TipoConta = Literal["corrente", "poupanca", ""]
TipoChavePix = Literal["cpf", "celular", "email", "aleatoria", ""]


class DriverInput(BaseModel):
    name: Str1
    vehicle_type: VehicleType = "moto"
    phone: StrOpt = ""
    email: StrOpt = ""
    plate: StrOpt = ""
    status: DriverStatus = "disponivel"
    rating: Annotated[float, Field(ge=0, le=5)] = 5.0
    photo: StrOpt = ""
    notes: StrOpt = ""

    cpf: Annotated[str, Field(default="", max_length=20, strip_whitespace=True)] = ""
    bank: StrOpt = ""
    bank_agency: Annotated[str, Field(default="", max_length=30, strip_whitespace=True)] = ""
    bank_account: Annotated[str, Field(default="", max_length=40, strip_whitespace=True)] = ""
    account_type: TipoConta = ""
    pix_key_type: TipoChavePix = ""
    pix_key: Annotated[str, Field(default="", max_length=160, strip_whitespace=True)] = ""

    @field_validator("cpf")
    @classmethod
    def cpf_so_digitos(cls, v: str) -> str:
        """O formulário pede 11 números; gente digita ponto e traço mesmo assim."""
        digitos = "".join(c for c in v if c.isdigit())
        if digitos and len(digitos) != 11:
            raise ValueError("CPF deve ter 11 dígitos")
        return digitos


class StatusPatch(BaseModel):
    status: str


class DriverStatusPatch(BaseModel):
    status: DriverStatus


class OrderStatusPatch(BaseModel):
    status: OrderStatus


class ContractInput(BaseModel):
    party_type: PartyType
    party_name: Str1
    party_id: StrOpt = ""
    rule_type: RuleType
    value: Annotated[float, Field(ge=0, le=1_000_000)]
    status: Literal["ativo", "encerrado", "suspenso"] = "ativo"
    notes: StrOpt = ""

    @field_validator("value")
    @classmethod
    def percent_range(cls, v, info):
        if info.data.get("rule_type") == "comissao_entrega" and v > 100:
            raise ValueError("Comissão por entrega não pode passar de 100%")
        return v


class PaymentInput(BaseModel):
    creditor: Str1
    creditor_type: PartyType
    creditor_id: StrOpt = ""
    amount: Annotated[float, Field(gt=0, le=10_000_000)]
    due_date: date
    method: PaymentMethod = "PIX"
    status: PaymentStatus = "pendente"
    notes: StrOpt = ""


class OrderInput(BaseModel):
    restaurant_id: StrOpt = ""
    restaurant_name: Str1
    customer_name: Str1
    customer_address: StrOpt = ""
    customer_phone: StrOpt = ""
    driver_id: StrOpt = ""
    driver_name: StrOpt = ""
    amount: Money = 0.0
    delivery_fee: Money = 0.0
    distance_km: Annotated[float, Field(ge=0, le=500)] = 0.0
    status: OrderStatus = "criado"
    notes: StrOpt = ""


class OrderAssign(BaseModel):
    driver_id: StrOpt = ""
    driver_name: StrOpt = ""


class LeadInput(BaseModel):
    name: Str1
    contact_name: StrOpt = ""
    phone: StrOpt = ""
    email: StrOpt = ""
    city: StrOpt = ""
    category: StrOpt = ""
    source: LeadSource = "prospeccao"
    stage: LeadStage = "novo"
    estimated_value: Money = 0.0
    owner_name: StrOpt = ""
    notes: StrOpt = ""
    lost_reason: StrOpt = ""


class LeadStagePatch(BaseModel):
    stage: LeadStage
    lost_reason: StrOpt = ""


class ActivityInput(BaseModel):
    kind: ActivityKind = "tarefa"
    type: ActivityType = "tarefa"
    title: Str1
    description: StrOpt = ""
    due_at: Optional[str] = None
    related_type: Optional[RelatedType] = None
    related_id: StrOpt = ""
    related_name: StrOpt = ""
    owner_name: StrOpt = ""
    done: bool = False


# ------------------------------------------------------------ formulários
FormFieldType = Literal[
    "texto", "email", "telefone", "numero", "textarea", "selecao", "escolha", "cpf", "data"
]
FormTarget = Literal["lead", "restaurante", "entregador"]

# Chave de campo: vira nome de propriedade no cadastro gerado, então precisa ser
# um identificador simples — sem espaço, acento ou maiúscula.
FieldKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]


class FormField(BaseModel):
    key: FieldKey
    label: Str1
    type: FormFieldType = "texto"
    required: bool = False
    placeholder: StrOpt = ""
    help: StrOpt = ""
    options: Annotated[list[Annotated[str, Field(max_length=120)]], Field(max_length=40)] = []
    # "Outro:" com escrita livre, como no Google Forms. Sem isso, uma lista de
    # bancos que não previsse o banco da pessoa a deixaria sem como responder.
    allow_other: bool = False


class FormInput(BaseModel):
    title: Str1
    description: StrOpt = ""
    target: FormTarget = "lead"
    fields: Annotated[list[FormField], Field(min_length=1, max_length=30)]
    active: bool = True
    success_message: StrOpt = ""

    @field_validator("fields")
    @classmethod
    def chaves_unicas(cls, v):
        chaves = [f.key for f in v]
        if len(chaves) != len(set(chaves)):
            raise ValueError("Há campos com a mesma chave no formulário")
        return v


class FormPatch(BaseModel):
    active: bool


class ApiKeyInput(BaseModel):
    name: Str1
    environment: Literal["production", "sandbox"] = "sandbox"


class WebhookInput(BaseModel):
    provider: Str1
    url: Annotated[str, Field(min_length=8, max_length=500, pattern=r"^https?://")]
    events: list[str] = []
    active: bool = True
