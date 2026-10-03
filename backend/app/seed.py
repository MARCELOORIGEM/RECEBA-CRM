"""Carga inicial e migração dos dados já existentes."""
import random
import uuid
from datetime import timedelta

from .config import settings
from .db import db, next_sequence
from .form_templates import MODELOS
from .routers.integrations import hash_key
from .security import hash_password, now_iso, now_utc

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
    import logging

    for antigo, novo in RENOMEACOES_DE_CONTA:
        if await db.users.find_one({"email": novo}):
            continue
        conta = await db.users.find_one({"email": antigo})
        if not conta:
            continue
        await db.users.update_one({"_id": conta["_id"]}, {"$set": {"email": novo}})
        logging.getLogger("miliano").info("Conta %s renomeada para %s", antigo, novo)


async def seed_users() -> None:
    pares = [
        (settings.admin_email, settings.admin_password, "Rafael (Admin)", "admin"),
        (settings.manager_email, settings.manager_password, "Gestor Operacional", "manager"),
    ]
    for email, pwd, name, role in pares:
        if not email or not pwd:
            continue
        existing = await db.users.find_one({"email": email})
        if not existing:
            await db.users.insert_one({
                "name": name, "email": email, "password_hash": hash_password(pwd),
                "role": role, "active": True, "created_at": now_iso(),
            })
        else:
            # A senha do .env só vale na criação da conta. Reescrevê-la a cada
            # boot desfazia silenciosamente qualquer troca feita pelo próprio
            # usuário em /auth/password.
            if "active" not in existing:
                await db.users.update_one({"email": email}, {"$set": {"active": True}})


async def migrate() -> None:
    """Traz os documentos antigos para o formato novo.

    O modelo anterior ligava pedidos, contratos e pagamentos ao cadastro apenas
    pelo nome em texto. Aqui esses vínculos viram id, e os campos que passaram a
    existir (contadores, updated_at) ganham valor inicial.
    """
    rest_by_name = {r["name"]: r["id"] async for r in db.restaurants.find({}, {"_id": 0, "id": 1, "name": 1})}
    drv_by_name = {d["name"]: d["id"] async for d in db.drivers.find({}, {"_id": 0, "id": 1, "name": 1})}

    await db.restaurants.update_many(
        {"orders_total": {"$exists": False}},
        {"$set": {"orders_total": 0, "revenue_total": 0.0, "commission_due": 0.0,
                  "email": "", "notes": "", "updated_at": now_iso()}},
    )
    await db.drivers.update_many(
        {"paid_total": {"$exists": False}},
        {"$set": {"paid_total": 0.0, "email": "", "notes": "", "updated_at": now_iso()}},
    )
    await db.drivers.update_many({"balance_due": {"$exists": False}}, {"$set": {"balance_due": 0.0}})

    async for o in db.orders.find({"restaurant_id": {"$exists": False}}, {"_id": 0}):
        await db.orders.update_one(
            {"id": o["id"]},
            {"$set": {
                "restaurant_id": rest_by_name.get(o.get("restaurant_name"), ""),
                "driver_id": drv_by_name.get(o.get("driver_name"), ""),
                "delivery_fee": 0.0,
                "distance_km": 0.0,
                "customer_phone": "",
                "notes": "",
                "financials_applied": False,
                "driver_earning": 0.0,
                "platform_commission": 0.0,
                "delivered_at": o.get("created_at") if o.get("status") == "entregue" else None,
                "updated_at": o.get("created_at", now_iso()),
            }},
        )

    async for c in db.contracts.find({"party_id": {"$exists": False}}, {"_id": 0}):
        origem = rest_by_name if c.get("party_type") == "restaurante" else drv_by_name
        await db.contracts.update_one(
            {"id": c["id"]},
            {"$set": {"party_id": origem.get(c.get("party_name"), ""), "updated_at": now_iso()}},
        )

    async for p in db.payments.find({"creditor_id": {"$exists": False}}, {"_id": 0}):
        origem = rest_by_name if p.get("creditor_type") == "restaurante" else drv_by_name
        await db.payments.update_one(
            {"id": p["id"]},
            {"$set": {"creditor_id": origem.get(p.get("creditor"), ""), "notes": "",
                      "updated_at": now_iso()}},
        )

    # Chaves de API em texto puro viram hash + prévia.
    async for k in db.api_keys.find({"key": {"$exists": True}}, {"_id": 0}):
        raw = k["key"]
        await db.api_keys.update_one(
            {"id": k["id"]},
            {"$set": {"key_hash": hash_key(raw), "key_preview": f"{raw[:13]}…{raw[-4:]}"},
             "$unset": {"key": ""}},
        )

    # Tentativas de login antigas gravadas como texto: o índice TTL não as
    # remove, porque só expira campo de data. Saem de uma vez.
    await db.login_attempts.delete_many({"created_at": {"$type": "string"}})

    await _sanitize()
    await _backfill_financials()

    # O contador de códigos precisa começar acima do maior PED- já usado.
    if await db.counters.count_documents({"name": "order_code"}) == 0:
        maior = 0
        async for o in db.orders.find({}, {"_id": 0, "code": 1}):
            try:
                maior = max(maior, int(str(o.get("code", "")).split("-")[-1]) - 1000)
            except (ValueError, IndexError):
                continue
        await db.counters.insert_one({"name": "order_code", "value": maior})


async def _sanitize() -> None:
    """Conserta registros que a API antiga aceitou por não validar entrada.

    Encontrados na base: restaurante com comissão -50%, status fora da lista e
    pagamento com valor negativo — todos gravados por chamadas que retornaram 200.
    """
    await db.restaurants.update_many({"commission_rate": {"$lt": 0}}, {"$set": {"commission_rate": 0.0}})
    await db.restaurants.update_many({"commission_rate": {"$gt": 100}}, {"$set": {"commission_rate": 100.0}})
    await db.restaurants.update_many(
        {"status": {"$nin": ["ativo", "em_analise", "suspenso", "inativo"]}},
        {"$set": {"status": "em_analise"}},
    )
    await db.drivers.update_many(
        {"status": {"$nin": ["disponivel", "em_entrega", "offline", "indisponivel"]}},
        {"$set": {"status": "offline"}},
    )
    await db.drivers.update_many({"rating": {"$gt": 5}}, {"$set": {"rating": 5.0}})
    await db.drivers.update_many({"rating": {"$lt": 0}}, {"$set": {"rating": 0.0}})
    await db.orders.update_many(
        {"status": {"$nin": ["criado", "aguardando_coleta", "em_transito", "entregue", "cancelado"]}},
        {"$set": {"status": "criado"}},
    )
    await db.orders.update_many({"amount": {"$lt": 0}}, {"$set": {"amount": 0.0}})
    # Valor negativo não é pagamento: marca como cancelado em vez de apagar,
    # para que o registro continue auditável.
    await db.payments.update_many(
        {"amount": {"$lte": 0}}, {"$set": {"status": "cancelado", "amount": 0.0}}
    )


async def _backfill_financials() -> None:
    """Recalcula contadores e saldos a partir dos pedidos reais.

    Duas coisas são resolvidas aqui. A primeira: entregas antigas nunca passaram
    pelo motor financeiro, então o painel mostrava receita zero para pedidos já
    entregues. A segunda: `total_deliveries` e `balance_due` vinham de números
    inventados no seed (`random.randint(50, 900)`), sem relação com a operação —
    somar em cima disso só perpetuaria o número errado, então a base é zerada e
    reconstruída a partir dos pedidos.

    Roda uma vez só, marcada em `migrations`.
    """
    import logging

    from . import financials

    if await db.migrations.find_one({"name": "recompute_financials_v2"}):
        return

    await db.drivers.update_many({}, {"$set": {"total_deliveries": 0, "balance_due": 0.0,
                                               "paid_total": 0.0}})
    await db.restaurants.update_many({}, {"$set": {"orders_total": 0, "revenue_total": 0.0,
                                                   "commission_due": 0.0}})
    await db.orders.update_many(
        {}, {"$set": {"financials_applied": False, "driver_earning": 0.0,
                      "platform_commission": 0.0}}
    )

    entregues = await db.orders.find({"status": "entregue"}, {"_id": 0}).to_list(20000)
    for pedido in entregues:
        await financials.apply_delivery(pedido)

    # Repasses já liquidados não podem continuar contando como saldo a pagar.
    async for p in db.payments.find({"status": "pago", "creditor_id": {"$ne": ""}}, {"_id": 0}):
        valor = float(p.get("amount") or 0)
        if p.get("creditor_type") == "entregador":
            await db.drivers.update_one(
                {"id": p["creditor_id"]},
                {"$inc": {"balance_due": -valor, "paid_total": valor}},
            )
        else:
            await db.restaurants.update_one(
                {"id": p["creditor_id"]}, {"$inc": {"commission_due": -valor}}
            )

    # Saldo negativo significa que já se pagou mais do que se devia: zera o piso.
    await db.drivers.update_many({"balance_due": {"$lt": 0}}, {"$set": {"balance_due": 0.0}})
    await db.restaurants.update_many({"commission_due": {"$lt": 0}}, {"$set": {"commission_due": 0.0}})

    await db.migrations.insert_one({"name": "recompute_financials_v2", "at": now_iso()})
    logging.getLogger("miliano").info(
        "Financeiro recalculado a partir de %d entrega(s)", len(entregues)
    )


SLUG_FORM_ENTREGADORES = "cadastro-de-entregadores"


async def atualizar_form_entregadores() -> None:
    """Realinha o formulário de entregadores ao modelo quando ele nunca foi
    mexido na tela.

    Só roda se o formulário ainda for o que a carga inicial criou (`created_by`
    = seed) e tiver exatamente as mesmas perguntas. Se a equipe editou, o
    trabalho dela vale mais do que o modelo e nada é tocado.
    """
    import logging

    atual = await db.forms.find_one({"slug": SLUG_FORM_ENTREGADORES})
    if not atual or atual.get("created_by") != "seed":
        return

    modelo = MODELOS["entregador"]
    if [c["key"] for c in atual.get("fields", [])] != [c["key"] for c in modelo["fields"]]:
        logging.getLogger("miliano").info(
            "Formulário de entregadores foi editado na tela; modelo não aplicado."
        )
        return
    if atual.get("fields") == modelo["fields"]:
        return

    await db.forms.update_one(
        {"slug": SLUG_FORM_ENTREGADORES},
        {"$set": {"fields": modelo["fields"], "updated_at": now_iso()}},
    )
    logging.getLogger("miliano").info("Formulário de entregadores realinhado ao modelo.")


async def seed_forms() -> None:
    """Cria o formulário de entregadores se ele ainda não existir.

    A trava é pelo SLUG, não por "a coleção está vazia": a equipe pode já ter
    criado os formulários dela, e nesse caso este entra ao lado, sem apagar nem
    sobrescrever nada. Editado ou apagado depois, também não volta.
    """
    if await db.forms.find_one({"slug": SLUG_FORM_ENTREGADORES}):
        return
    doc = {
        **MODELOS["entregador"],
        "id": str(uuid.uuid4()),
        "slug": SLUG_FORM_ENTREGADORES,
        "submissions_count": 0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": "seed",
    }
    await db.forms.insert_one(dict(doc))


async def seed_demo() -> None:
    if not settings.seed_demo:
        return

    if await db.restaurants.count_documents({}) == 0:
        for name, cat, person, phone, status, comm in RESTAURANTS:
            await db.restaurants.insert_one({
                "id": str(uuid.uuid4()), "name": name, "category": cat,
                "contact_person": person, "phone": phone, "email": "",
                "cnpj": f"12.345.{random.randint(100, 999)}/0001-{random.randint(10, 99)}",
                "address": "Av. Paulista, 1000 - São Paulo/SP", "commission_rate": comm,
                "status": status, "notes": "", "orders_total": 0,
                "revenue_total": 0.0, "commission_due": 0.0,
                "created_at": now_iso(), "updated_at": now_iso(), "created_by": "seed",
            })

    if await db.drivers.count_documents({}) == 0:
        for name, veh, phone, plate, status, rating in DRIVERS:
            await db.drivers.insert_one({
                "id": str(uuid.uuid4()), "name": name, "vehicle_type": veh, "phone": phone,
                "email": "", "plate": plate, "status": status, "rating": rating, "photo": "",
                "notes": "", "total_deliveries": 0, "balance_due": 0.0, "paid_total": 0.0,
                "created_at": now_iso(), "updated_at": now_iso(), "created_by": "seed",
            })

    rests = await db.restaurants.find({}, {"_id": 0}).to_list(50)
    drvs = await db.drivers.find({}, {"_id": 0}).to_list(50)
    by_rest = {r["name"]: r for r in rests}
    by_drv = {d["name"]: d for d in drvs}

    if await db.contracts.count_documents({}) == 0:
        combos = [
            ("restaurante", "Brito Burguer", "comissao_entrega", 15.0),
            ("restaurante", "Pizzaria Bella Napoli", "comissao_entrega", 18.0),
            ("entregador", "Carlos Eduardo", "valor_km", 1.80),
            ("entregador", "Juliana Costa", "taxa_fixa", 1800.0),
        ]
        for pt, pn, rt, val in combos:
            origem = by_rest if pt == "restaurante" else by_drv
            await db.contracts.insert_one({
                "id": str(uuid.uuid4()), "party_type": pt, "party_name": pn,
                "party_id": origem.get(pn, {}).get("id", ""), "rule_type": rt, "value": val,
                "status": "ativo", "notes": "", "created_at": now_iso(),
                "updated_at": now_iso(), "created_by": "seed",
            })

    if await db.orders.count_documents({}) == 0 and rests and drvs:
        from . import financials

        statuses = ["criado", "aguardando_coleta", "em_transito", "entregue",
                    "entregue", "entregue", "cancelado"]
        clientes = ["Ana Souza", "Pedro Alves", "Marina Dias", "Lucas Rocha", "Beatriz Melo",
                    "Rafael Gomes", "Camila Torres", "Diego Nunes", "Larissa Pinto", "Thiago Barros"]
        ruas = ["das Flores", "Aurora", "Consolação", "Augusta", "Cardeal Arcoverde"]
        agora = now_utc()
        for i in range(60):
            st = random.choice(statuses)
            r = random.choice(rests)
            d = random.choice(drvs) if st != "criado" else None
            dias = random.randint(0, 13)
            criado = (agora - timedelta(days=dias)).replace(
                hour=random.randint(8, 22), minute=random.randint(0, 59)
            )
            seq = await next_sequence("order_code")
            pedido = {
                "id": str(uuid.uuid4()), "code": f"PED-{1000 + seq}",
                "restaurant_id": r["id"], "restaurant_name": r["name"],
                "customer_name": random.choice(clientes),
                "customer_address": f"Rua {random.choice(ruas)}, {random.randint(10, 999)}",
                "customer_phone": "", "driver_id": d["id"] if d else "",
                "driver_name": d["name"] if d else "",
                "amount": round(random.uniform(25, 180), 2),
                "delivery_fee": round(random.uniform(6, 14), 2),
                "distance_km": round(random.uniform(1, 12), 1),
                "status": st, "notes": "", "financials_applied": False,
                "driver_earning": 0.0, "platform_commission": 0.0, "delivered_at": None,
                "created_at": criado.isoformat(), "updated_at": criado.isoformat(),
                "created_by": "seed",
            }
            await db.orders.insert_one(dict(pedido))
            if st == "entregue":
                await financials.apply_delivery(pedido)

    if await db.payments.count_documents({}) == 0:
        pays = [
            ("Carlos Eduardo", "entregador", 120.50, "pendente", "PIX", 2),
            ("Matheus Oliveira", "entregador", 85.00, "pendente", "PIX", -1),
            ("Brito Burguer", "restaurante", 4200.00, "pago", "Transferência", 5),
            ("Pizzaria Bella Napoli", "restaurante", 5800.00, "atrasado", "Transferência", -3),
            ("Juliana Costa", "entregador", 210.75, "pendente", "PIX", 4),
        ]
        for cred, ct, amt, st, method, offset in pays:
            origem = by_rest if ct == "restaurante" else by_drv
            due = (now_utc() + timedelta(days=offset)).date().isoformat()
            await db.payments.insert_one({
                "id": str(uuid.uuid4()), "creditor": cred, "creditor_type": ct,
                "creditor_id": origem.get(cred, {}).get("id", ""), "amount": amt,
                "due_date": due, "method": method, "status": st, "notes": "",
                "paid_at": now_iso() if st == "pago" else None,
                "created_at": now_iso(), "updated_at": now_iso(), "created_by": "seed",
            })

    if await db.leads.count_documents({}) == 0:
        for name, contato, cat, cidade, origem, etapa, valor in LEADS:
            criado = (now_utc() - timedelta(days=random.randint(1, 40))).isoformat()
            await db.leads.insert_one({
                "id": str(uuid.uuid4()), "name": name, "contact_name": contato,
                "phone": f"(11) 9{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
                "email": "", "city": cidade, "category": cat, "source": origem, "stage": etapa,
                "estimated_value": valor, "owner_name": "Gestor Operacional", "notes": "",
                "lost_reason": "Achou a comissão alta" if etapa == "perdido" else "",
                "stage_history": [{"stage": etapa, "at": criado, "by": "seed"}],
                "converted_restaurant_id": None, "created_at": criado,
                "updated_at": criado, "created_by": "seed",
            })

    if await db.activities.count_documents({}) == 0:
        leads = await db.leads.find({}, {"_id": 0}).to_list(20)
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
            due = (now_utc() + timedelta(days=offset)).isoformat()
            concluida = kind == "interacao"
            await db.activities.insert_one({
                "id": str(uuid.uuid4()), "kind": kind, "type": tipo, "title": titulo,
                "description": "", "due_at": due, "done": concluida,
                "related_type": "lead" if alvo else None,
                "related_id": alvo["id"] if alvo else "",
                "related_name": alvo["name"] if alvo else "",
                "owner_name": "Gestor Operacional",
                "completed_at": due if concluida else None,
                "created_at": now_iso(), "updated_at": now_iso(), "created_by": "seed",
            })

    if await db.api_keys.count_documents({}) == 0:
        import secrets

        for nome, env in [("Chave Produção", "production"), ("Chave Sandbox", "sandbox")]:
            prefix = "mln_live_" if env == "production" else "mln_test_"
            raw = prefix + secrets.token_hex(20)
            await db.api_keys.insert_one({
                "id": str(uuid.uuid4()), "name": nome, "environment": env,
                "key_hash": hash_key(raw), "key_preview": f"{raw[:len(prefix) + 4]}…{raw[-4:]}",
                "created_at": now_iso(), "created_by": "seed", "last_used": None,
            })

    if await db.webhooks.count_documents({}) == 0:
        for prov, url, events in [
            ("ifood", "https://api.miliano.com.br/webhooks/ifood", ["pedido.criado", "pedido.entregue"]),
            ("rappi", "https://api.miliano.com.br/webhooks/rappi", ["pedido.criado", "pedido.cancelado"]),
        ]:
            await db.webhooks.insert_one({
                "id": str(uuid.uuid4()), "provider": prov, "url": url, "events": events,
                "active": True, "created_at": now_iso(), "created_by": "seed",
            })

    if await db.webhook_logs.count_documents({}) == 0:
        samples = [("ifood", "pedido.criado", 200), ("rappi", "pedido.entregue", 200),
                   ("ifood", "pedido.cancelado", 200), ("pos", "sync.estoque", 500),
                   ("rappi", "pedido.criado", 200), ("delivery_much", "pedido.criado", 404),
                   ("ifood", "pedido.entregue", 200), ("rappi", "pedido.criado", 200)]
        for i, (prov, ev, code) in enumerate(samples):
            ts = (now_utc() - timedelta(minutes=i * 7)).isoformat()
            await db.webhook_logs.insert_one({
                "id": str(uuid.uuid4()), "provider": prov, "event": ev,
                "status_code": code, "created_at": ts,
            })


async def run() -> None:
    # A renomeação vem antes do seed: se rodasse depois, o seed já teria criado
    # a conta com o e-mail novo e a antiga ficaria para trás.
    await migrar_emails()
    await seed_users()
    await migrate()
    await seed_demo()
    await seed_forms()
    await atualizar_form_entregadores()
