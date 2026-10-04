"""Carga inicial: contas, formulário padrão e, se pedido, dados de demonstração.

A versão do Mongo também consertava, a cada boot, documentos gravados por
versões antigas da API (comissão negativa, status fora da lista, vínculos só
por nome). No Postgres esses estados não existem: os CHECK do schema recusam o
valor torto na gravação. O conserto dos dados herdados acontece uma vez, na
transferência — ver `scripts/mongo_para_postgres.py`.
"""
import logging
import random
import secrets
import uuid
from datetime import timedelta

from . import financials, pg, repo
from .config import settings
from .form_templates import MODELOS
from .routers.integrations import hash_key
from .security import hash_password, now_utc

logger = logging.getLogger("miliano")

RESTAURANTS = [
    ("Brito Burguer", "Hamburgueria", "João Brito", "(11) 99812-3344", "ativo", 15.0),
    ("Pizzaria Bella Napoli", "Pizzaria", "Marco Rossi", "(11) 99711-2200", "ativo", 18.0),
    ("Sabor Mineiro", "Comida Caseira", "Dona Cida", "(31) 99655-1010", "ativo", 12.0),
    ("Sushi House", "Japonesa", "Ken Tanaka", "(11) 99400-7788", "ativo", 20.0),
    ("Açaí do Ponto", "Açaiteria", "Bruno Lima", "(11) 99333-4455", "em_analise", 10.0),
    ("Cantina da Nonna", "Italiana", "Paola Ferri", "(11) 99222-8899", "suspenso", 16.0),
]

DRIVERS = [
    ("Carlos Eduardo", "moto", "(11) 98111-2233", "ABC1D23", "disponivel", 4.9),
    ("Matheus Oliveira", "moto", "(11) 98222-3344", "XYZ4E56", "em_entrega", 4.7),
    ("Fernanda Lima", "bike", "(11) 98333-4455", "", "disponivel", 5.0),
    ("Roberto Santos", "bike", "(11) 98444-5566", "", "offline", 4.5),
    ("Juliana Costa", "carro", "(11) 98555-6677", "DEF7G89", "disponivel", 4.8),
]

LEADS = [
    ("Padaria Estrela", "Seu Antônio", "Padaria", "São Paulo", "indicacao", "negociacao", 3200.0),
    ("Temakeria Onda", "Vivian Sato", "Japonesa", "Santo André", "instagram", "proposta", 5400.0),
    ("Burger do Vale", "Diego Prado", "Hamburgueria", "São Bernardo", "prospeccao", "contatado", 4100.0),
    ("Marmitaria Bom Prato", "Cleide Alves", "Comida Caseira", "Guarulhos", "whatsapp", "novo", 2600.0),
    ("Pastelaria Central", "Wang Li", "Pastelaria", "São Paulo", "site", "novo", 1900.0),
    ("Doce Encanto", "Renata Dias", "Confeitaria", "Osasco", "indicacao", "ganho", 2300.0),
    ("Espeto do Zé", "José Carlos", "Churrascaria", "Diadema", "evento", "perdido", 1500.0),
]


# Contas cujo e-mail mudou junto com a marca. Sem esta migração, alterar
# MANAGER_EMAIL no .env faria o seed criar uma conta nova e deixar a antiga
# órfã: dois gestores, com senhas diferentes e um deles sem ninguém usando.
RENOMEACOES_DE_CONTA = [
    ("gestor@recebalogistica.com", "gestor@recompensalogistica.com"),
]


async def migrar_emails() -> None:
    """Renomeia a conta preservando senha, perfil e histórico."""
    for antigo, novo in RENOMEACOES_DE_CONTA:
        if await repo.existe("users", "email", novo):
            continue
        conta = await repo.um_por("users", "email", antigo)
        if not conta:
            continue
        await repo.atualizar("users", conta["id"], {"email": novo, "updated_at": now_utc()})
        logger.info("Conta %s renomeada para %s", antigo, novo)


def _email_entra(email: str) -> bool:
    """O mesmo validador da tela de login (`LoginInput.email`)."""
    from pydantic import EmailStr, TypeAdapter, ValidationError

    try:
        TypeAdapter(EmailStr).validate_python(email)
        return True
    except ValidationError:
        return False


async def seed_users() -> None:
    pares = [
        (settings.admin_email, settings.admin_password, "Rafael (Admin)", "admin"),
        (settings.manager_email, settings.manager_password, "Gestor Operacional", "manager"),
    ]
    for email, pwd, name, role in pares:
        if not email or not pwd:
            continue
        if not _email_entra(email):
            # A conta seria criada, mas a tela de login recusa o e-mail antes
            # de conferir a senha — ninguém conseguiria entrar com ela. Foi o
            # que derrubou o CI: `admin@ci.local` (".local" é domínio reservado).
            logger.error(
                "E-mail %r não é aceito no login (domínio reservado ou inválido). "
                "A conta NÃO foi criada; corrija ADMIN_EMAIL/MANAGER_EMAIL.", email
            )
            continue
        # A senha do .env só vale na criação da conta. Reescrevê-la a cada boot
        # desfazia silenciosamente qualquer troca feita pelo próprio usuário em
        # /auth/password. O ON CONFLICT torna isso seguro também quando duas
        # réplicas sobem ao mesmo tempo.
        await pg.executar(
            """
            INSERT INTO users (id, name, email, password_hash, role, active)
            VALUES ($1, $2, $3, $4, $5, TRUE)
            ON CONFLICT (email) DO NOTHING
            """,
            str(uuid.uuid4()), name, email, hash_password(pwd), role,
        )


async def alinhar_contador() -> None:
    """O contador de códigos precisa começar acima do maior PED- já usado.

    Só age quando o contador ainda não existe — numa base que acabou de
    receber os pedidos do Mongo, por exemplo. Depois disso, quem manda é
    `pg.proximo_numero`.
    """
    await pg.executar(
        """
        INSERT INTO counters (name, value)
        SELECT 'order_code',
               COALESCE(MAX(NULLIF(substring(code FROM '([0-9]+)$'), '')::bigint) - 1000, 0)
          FROM orders WHERE code LIKE 'PED-%'
        ON CONFLICT (name) DO NOTHING
        """
    )


SLUG_FORM_ENTREGADORES = "cadastro-de-entregadores"


async def atualizar_form_entregadores() -> None:
    """Realinha o formulário de entregadores ao modelo quando ele nunca foi
    mexido na tela.

    Só roda se o formulário ainda for o que a carga inicial criou (`created_by`
    = seed) e tiver exatamente as mesmas perguntas. Se a equipe editou, o
    trabalho dela vale mais do que o modelo e nada é tocado.
    """
    atual = await repo.um_por("forms", "slug", SLUG_FORM_ENTREGADORES)
    if not atual or atual.get("created_by") != "seed":
        return

    modelo = MODELOS["entregador"]
    if [c["key"] for c in atual.get("fields", [])] != [c["key"] for c in modelo["fields"]]:
        logger.info("Formulário de entregadores foi editado na tela; modelo não aplicado.")
        return
    if atual.get("fields") == modelo["fields"]:
        return

    await repo.atualizar(
        "forms", atual["id"], {"fields": modelo["fields"], "updated_at": now_utc()}
    )
    logger.info("Formulário de entregadores realinhado ao modelo.")


async def seed_forms() -> None:
    """Cria o formulário de entregadores se ele ainda não existir.

    A trava é pelo SLUG, não por "a tabela está vazia": a equipe pode já ter
    criado os formulários dela, e nesse caso este entra ao lado, sem apagar nem
    sobrescrever nada. Editado ou apagado depois, também não volta.
    """
    if await repo.existe("forms", "slug", SLUG_FORM_ENTREGADORES):
        return
    await pg.executar(
        """
        INSERT INTO forms (id, slug, title, description, target, fields, active,
                           success_message, seed, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7, TRUE, 'seed')
        ON CONFLICT (slug) DO NOTHING
        """,
        str(uuid.uuid4()),
        SLUG_FORM_ENTREGADORES,
        MODELOS["entregador"]["title"],
        MODELOS["entregador"].get("description", ""),
        MODELOS["entregador"].get("target", "entregador"),
        MODELOS["entregador"]["fields"],
        MODELOS["entregador"].get("success_message", ""),
    )


async def _vazia(tabela: str) -> bool:
    return await repo.contar(tabela) == 0


async def seed_demo() -> None:
    if not settings.seed_demo:
        return

    if await _vazia("restaurants"):
        for name, cat, person, phone, status, comm in RESTAURANTS:
            await repo.inserir("restaurants", {
                "id": str(uuid.uuid4()), "name": name, "category": cat,
                "contact_person": person, "phone": phone,
                "cnpj": f"12.345.{random.randint(100, 999)}/0001-{random.randint(10, 99)}",
                "address": "Av. Paulista, 1000 - São Paulo/SP", "commission_rate": comm,
                "status": status, "created_by": "seed",
            })

    if await _vazia("drivers"):
        for name, veh, phone, plate, status, rating in DRIVERS:
            await repo.inserir("drivers", {
                "id": str(uuid.uuid4()), "name": name, "vehicle_type": veh, "phone": phone,
                "plate": plate, "status": status, "rating": rating, "created_by": "seed",
            })

    rests = await repo.listar("restaurants", limite=50)
    drvs = await repo.listar("drivers", limite=50)
    by_rest = {r["name"]: r for r in rests}
    by_drv = {d["name"]: d for d in drvs}

    if await _vazia("contracts"):
        combos = [
            ("restaurante", "Brito Burguer", "comissao_entrega", 15.0),
            ("restaurante", "Pizzaria Bella Napoli", "comissao_entrega", 18.0),
            ("entregador", "Carlos Eduardo", "valor_km", 1.80),
            ("entregador", "Juliana Costa", "taxa_fixa", 1800.0),
        ]
        for pt, pn, rt, val in combos:
            origem = by_rest if pt == "restaurante" else by_drv
            await repo.inserir("contracts", {
                "id": str(uuid.uuid4()), "party_type": pt, "party_name": pn,
                "party_id": origem.get(pn, {}).get("id", ""), "rule_type": rt, "value": val,
                "status": "ativo", "created_by": "seed",
            })

    if await _vazia("orders") and rests and drvs:
        statuses = ["criado", "aguardando_coleta", "em_transito", "entregue",
                    "entregue", "entregue", "cancelado"]
        clientes = ["Ana Souza", "Pedro Alves", "Marina Dias", "Lucas Rocha", "Beatriz Melo",
                    "Rafael Gomes", "Camila Torres", "Diego Nunes", "Larissa Pinto", "Thiago Barros"]
        ruas = ["das Flores", "Aurora", "Consolação", "Augusta", "Cardeal Arcoverde"]
        agora = now_utc()
        for _ in range(60):
            st = random.choice(statuses)
            r = random.choice(rests)
            d = random.choice(drvs) if st != "criado" else None
            criado = (agora - timedelta(days=random.randint(0, 13))).replace(
                hour=random.randint(8, 22), minute=random.randint(0, 59)
            )
            seq = await pg.proximo_numero("order_code")
            pedido = await repo.inserir("orders", {
                "id": str(uuid.uuid4()), "code": f"PED-{1000 + seq}",
                "restaurant_id": r["id"], "restaurant_name": r["name"],
                "customer_name": random.choice(clientes),
                "customer_address": f"Rua {random.choice(ruas)}, {random.randint(10, 999)}",
                "driver_id": d["id"] if d else "",
                "driver_name": d["name"] if d else "",
                "amount": round(random.uniform(25, 180), 2),
                "delivery_fee": round(random.uniform(6, 14), 2),
                "distance_km": round(random.uniform(1, 12), 1),
                "status": st, "created_at": criado, "updated_at": criado,
                "created_by": "seed",
            })
            if st == "entregue":
                await financials.apply_delivery(pedido)

    if await _vazia("payments"):
        pays = [
            ("Carlos Eduardo", "entregador", 120.50, "pendente", "PIX", 2),
            ("Matheus Oliveira", "entregador", 85.00, "pendente", "PIX", -1),
            ("Brito Burguer", "restaurante", 4200.00, "pago", "Transferência", 5),
            ("Pizzaria Bella Napoli", "restaurante", 5800.00, "atrasado", "Transferência", -3),
            ("Juliana Costa", "entregador", 210.75, "pendente", "PIX", 4),
        ]
        for cred, ct, amt, st, method, offset in pays:
            origem = by_rest if ct == "restaurante" else by_drv
            await repo.inserir("payments", {
                "id": str(uuid.uuid4()), "creditor": cred, "creditor_type": ct,
                "creditor_id": origem.get(cred, {}).get("id", ""), "amount": amt,
                "due_date": (now_utc() + timedelta(days=offset)).date(),
                "method": method, "status": st,
                "paid_at": now_utc() if st == "pago" else None,
                "created_by": "seed",
            })

    if await _vazia("leads"):
        for name, contato, cat, cidade, origem, etapa, valor in LEADS:
            criado = now_utc() - timedelta(days=random.randint(1, 40))
            await repo.inserir("leads", {
                "id": str(uuid.uuid4()), "name": name, "contact_name": contato,
                "phone": f"(11) 9{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
                "city": cidade, "category": cat, "source": origem, "stage": etapa,
                "estimated_value": valor, "owner_name": "Gestor Operacional",
                "lost_reason": "Achou a comissão alta" if etapa == "perdido" else "",
                "stage_history": [{"stage": etapa, "at": criado.isoformat(), "by": "seed"}],
                "created_at": criado, "updated_at": criado, "created_by": "seed",
            })

    if await _vazia("activities"):
        leads = await repo.listar("leads", limite=20)
        modelos = [
            ("tarefa", "ligacao", "Ligar para fechar proposta", -1),
            ("tarefa", "whatsapp", "Enviar tabela de comissões", 0),
            ("tarefa", "visita", "Visita técnica para instalar tablet", 2),
            ("interacao", "ligacao", "Ligação: pediu para retornar na sexta", -3),
            ("tarefa", "reuniao", "Reunião de alinhamento operacional", 5),
            ("interacao", "nota", "Indicado pelo Brito Burguer", -6),
        ]
        for i, (kind, tipo, titulo, offset) in enumerate(modelos):
            alvo = leads[i % len(leads)] if leads else None
            due = now_utc() + timedelta(days=offset)
            concluida = kind == "interacao"
            await repo.inserir("activities", {
                "id": str(uuid.uuid4()), "kind": kind, "type": tipo, "title": titulo,
                "due_at": due, "done": concluida,
                "related_type": "lead" if alvo else None,
                "related_id": alvo["id"] if alvo else "",
                "related_name": alvo["name"] if alvo else "",
                "owner_name": "Gestor Operacional",
                "completed_at": due if concluida else None,
                "created_by": "seed",
            })

    if await _vazia("api_keys"):
        for nome, env in [("Chave Produção", "production"), ("Chave Sandbox", "sandbox")]:
            prefix = "mln_live_" if env == "production" else "mln_test_"
            raw = prefix + secrets.token_hex(20)
            await repo.inserir("api_keys", {
                "id": str(uuid.uuid4()), "name": nome, "environment": env,
                "key_hash": hash_key(raw), "key_preview": f"{raw[:len(prefix) + 4]}…{raw[-4:]}",
                "created_by": "seed",
            })

    if await _vazia("webhooks"):
        for prov, url, events in [
            ("ifood", "https://api.miliano.com.br/webhooks/ifood", ["pedido.criado", "pedido.entregue"]),
            ("rappi", "https://api.miliano.com.br/webhooks/rappi", ["pedido.criado", "pedido.cancelado"]),
        ]:
            await repo.inserir("webhooks", {
                "id": str(uuid.uuid4()), "provider": prov, "url": url, "events": events,
                "active": True, "created_by": "seed",
            })

    if await _vazia("webhook_logs"):
        samples = [("ifood", "pedido.criado", 200), ("rappi", "pedido.entregue", 200),
                   ("ifood", "pedido.cancelado", 200), ("pos", "sync.estoque", 500),
                   ("rappi", "pedido.criado", 200), ("delivery_much", "pedido.criado", 404),
                   ("ifood", "pedido.entregue", 200), ("rappi", "pedido.criado", 200)]
        for i, (prov, ev, code) in enumerate(samples):
            await repo.inserir("webhook_logs", {
                "id": str(uuid.uuid4()), "provider": prov, "event": ev,
                "status_code": code, "created_at": now_utc() - timedelta(minutes=i * 7),
            })


async def run() -> None:
    # A renomeação vem antes do seed: se rodasse depois, o seed já teria criado
    # a conta com o e-mail novo e a antiga ficaria para trás.
    await migrar_emails()
    await seed_users()
    await alinhar_contador()
    await seed_demo()
    await seed_forms()
    await atualizar_form_entregadores()
