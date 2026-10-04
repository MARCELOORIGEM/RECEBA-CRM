"""Trilha de auditoria — quem mudou o quê e quando.

Um CRM guarda dinheiro e relacionamento comercial; sem registro de alterações
não há como apurar divergência de repasse nem reverter um erro operacional.
"""
import json
import uuid
from typing import Any

from . import pg

# Campos que nunca devem entrar no log.
_REDACTED = {"password", "password_hash", "key", "key_hash", "token", "token_hash"}

# Campos sem valor informativo num diff: mudam em toda escrita e só fariam
# ruído em cima do que mudou de verdade.
_RUIDO = {"_id", "updated_at"}


def _json_seguro(valor: Any) -> Any:
    """Deixa o valor gravável em JSONB.

    As datas agora voltam do banco como `datetime`, não mais como string ISO —
    e `json.dumps` não sabe serializá-las. Sem isto, auditar a alteração de um
    pedido (que tem `delivered_at`) estouraria no meio da gravação, depois de a
    alteração já ter sido aplicada: a mudança aconteceria e o registro dela
    não.
    """
    if isinstance(valor, dict):
        return {k: _json_seguro(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json_seguro(v) for v in valor]
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)


def _diff(before: dict | None, after: dict | None) -> list[dict]:
    """Lista do que mudou, pronta para o JSONB.

    Virou lista (era dicionário com o nome do campo como chave) porque o painel
    a exibe em ordem, e dicionário em JSONB não garante ordem nenhuma.
    """
    before, after = before or {}, after or {}
    chaves = (set(before) | set(after)) - _REDACTED - _RUIDO
    mudancas = []
    for chave in sorted(chaves):
        de, para = before.get(chave), after.get(chave)
        if de != para:
            mudancas.append(
                {"campo": chave, "de": _json_seguro(de), "para": _json_seguro(para)}
            )
    return mudancas


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
    await pg.executar(
        """
        INSERT INTO audit_logs
            (id, actor_id, actor_name, actor_email, action, entity, entity_id, label, changes)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        str(uuid.uuid4()),
        actor.get("id") or "",
        actor.get("name") or "",
        actor.get("email") or "",
        action,  # criou | atualizou | removeu | liquidou | ...
        entity,
        entity_id or "",
        label or "",
        _diff(before, after),
    )
