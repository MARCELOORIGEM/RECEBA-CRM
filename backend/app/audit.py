"""Trilha de auditoria — quem mudou o quê e quando.

Um CRM guarda dinheiro e relacionamento comercial; sem registro de alterações
não há como apurar divergência de repasse nem reverter um erro operacional.
"""
import uuid
from typing import Any

from .db import db
from .security import now_iso

# Campos que nunca devem entrar no log.
_REDACTED = {"password", "password_hash", "key", "key_hash", "token"}


def _diff(before: dict | None, after: dict | None) -> dict:
    before, after = before or {}, after or {}
    keys = (set(before) | set(after)) - _REDACTED - {"_id", "updated_at"}
    changes: dict[str, Any] = {}
    for k in keys:
        if before.get(k) != after.get(k):
            changes[k] = {"de": before.get(k), "para": after.get(k)}
    return changes


async def record(
    actor: dict,
    action: str,
    entity: str,
    entity_id: str,
    *,
    label: str = "",
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    await db.audit_logs.insert_one(
        {
            "id": str(uuid.uuid4()),
            "actor_id": actor.get("id"),
            "actor_name": actor.get("name"),
            "actor_email": actor.get("email"),
            "action": action,  # criou | atualizou | removeu | liquidou | ...
            "entity": entity,
            "entity_id": entity_id,
            "label": label,
            "changes": _diff(before, after),
            "created_at": now_iso(),
        }
    )
