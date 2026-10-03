"""Conexão Mongo e índices."""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, TEXT

from .config import settings

client = AsyncIOMotorClient(settings.mongo_url)
db = client[settings.db_name]


async def ensure_indexes() -> None:
    """Índices para toda coleção que é filtrada/ordenada. Sem isso o Mongo faz
    varredura completa em cada listagem."""
    await db.users.create_index("email", unique=True)

    await db.restaurants.create_index("id", unique=True)
    await db.restaurants.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    await db.restaurants.create_index([("name", TEXT), ("cnpj", TEXT), ("contact_person", TEXT)])

    await db.drivers.create_index("id", unique=True)
    await db.drivers.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    await db.drivers.create_index([("name", TEXT), ("plate", TEXT)])

    await db.orders.create_index("id", unique=True)
    await db.orders.create_index("code", unique=True)
    await db.orders.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    await db.orders.create_index("restaurant_id")
    await db.orders.create_index("driver_id")
    await db.orders.create_index("created_at")

    await db.contracts.create_index("id", unique=True)
    await db.contracts.create_index([("party_type", ASCENDING), ("status", ASCENDING)])
    await db.contracts.create_index("party_id")

    await db.payments.create_index("id", unique=True)
    await db.payments.create_index([("status", ASCENDING), ("due_date", ASCENDING)])
    await db.payments.create_index("creditor_id")

    await db.leads.create_index("id", unique=True)
    await db.leads.create_index([("stage", ASCENDING), ("updated_at", DESCENDING)])
    await db.leads.create_index([("name", TEXT), ("contact_name", TEXT), ("city", TEXT)])

    await db.activities.create_index("id", unique=True)
    await db.activities.create_index([("done", ASCENDING), ("due_at", ASCENDING)])
    await db.activities.create_index([("related_type", ASCENDING), ("related_id", ASCENDING)])

    await db.forms.create_index("id", unique=True)
    await db.forms.create_index("slug", unique=True)
    await db.form_submissions.create_index("id", unique=True)
    await db.form_submissions.create_index([("form_id", ASCENDING), ("created_at", DESCENDING)])
    # Contagem de envios por IP na última hora, usada no limite anti-robô.
    await db.form_submissions.create_index([("ip", ASCENDING), ("created_at_dt", DESCENDING)])

    await db.audit_logs.create_index([("created_at", DESCENDING)])
    await db.audit_logs.create_index([("entity", ASCENDING), ("entity_id", ASCENDING)])

    await db.api_keys.create_index("id", unique=True)
    await db.api_keys.create_index("key_hash")
    await db.webhooks.create_index("id", unique=True)
    await db.webhook_logs.create_index([("created_at", DESCENDING)])
    await db.login_attempts.create_index("created_at", expireAfterSeconds=3600)
    # Pedido de redefinição some sozinho na virada da validade.
    await db.password_resets.create_index("token_hash", unique=True)
    await db.password_resets.create_index("user_id")
    await db.password_resets.create_index("expira_em", expireAfterSeconds=0)
    # Referência externa do marketplace: identifica o mesmo pedido nas chamadas
    # seguintes. Esparso porque pedido criado na tela não tem referência.
    await db.orders.create_index("external_ref", unique=True, sparse=True)
    await db.counters.create_index("name", unique=True)


async def next_sequence(name: str) -> int:
    """Contador atômico. Substitui count_documents()+1, que gerava códigos
    duplicados quando dois pedidos eram criados ao mesmo tempo."""
    doc = await db.counters.find_one_and_update(
        {"name": name}, {"$inc": {"value": 1}}, upsert=True, return_document=True
    )
    return int(doc["value"])
