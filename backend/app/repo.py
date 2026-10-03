"""Helpers de acesso a dados compartilhados pelos routers."""
import re
from typing import Any

from fastapi import HTTPException
from pymongo import ASCENDING, DESCENDING

from .db import db

PROJECTION = {"_id": 0}


async def get_or_404(collection: str, doc_id: str, label: str) -> dict:
    doc = await db[collection].find_one({"id": doc_id}, PROJECTION)
    if not doc:
        raise HTTPException(status_code=404, detail=f"{label} não encontrado")
    return doc


def regex_filter(term: str, fields: list[str]) -> dict:
    """Busca parcial case-insensitive. Escapa o termo para que um usuário digitando
    '(11) 9' não quebre a query com um regex inválido."""
    pattern = re.compile(re.escape(term.strip()), re.IGNORECASE)
    return {"$or": [{f: pattern} for f in fields]}


async def paginate(
    collection: str,
    query: dict,
    *,
    page: int = 1,
    page_size: int = 25,
    sort_field: str = "created_at",
    sort_dir: str = "desc",
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    direction = DESCENDING if sort_dir == "desc" else ASCENDING
    cursor = (
        db[collection]
        .find(query, PROJECTION)
        .sort(sort_field, direction)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = await cursor.to_list(page_size)
    total = await db[collection].count_documents(query)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }
