"""Busca global, timeline por cadastro, auditoria e saúde da API."""
from fastapi import APIRouter, Depends, Query

from ..db import db
from ..deps import get_current_user, require_admin
from ..repo import PROJECTION, paginate, regex_filter

router = APIRouter(tags=["geral"])


@router.get("/health")
async def health():
    """Ping sem autenticação, para load balancer e monitoramento."""
    try:
        await db.command("ping")
        return {"status": "ok", "database": "up"}
    except Exception:
        return {"status": "degraded", "database": "down"}


@router.get("/search")
async def global_search(q: str = Query("", min_length=0), user: dict = Depends(get_current_user)):
    """Busca única sobre todo o CRM — alimenta o atalho Ctrl/⌘+K do painel."""
    term = q.strip()
    if len(term) < 2:
        return {"results": []}

    results: list[dict] = []

    async def collect(collection, fields, tipo, label_field, sub, rota):
        docs = await db[collection].find(regex_filter(term, fields), PROJECTION).limit(5).to_list(5)
        for d in docs:
            results.append({
                "tipo": tipo,
                "id": d["id"],
                "titulo": d.get(label_field, ""),
                "subtitulo": " • ".join(str(d.get(f, "")) for f in sub if d.get(f)),
                "rota": rota,
            })

    await collect("restaurants", ["name", "cnpj", "contact_person", "phone"],
                  "Restaurante", "name", ["category", "status"], "/restaurantes")
    await collect("drivers", ["name", "plate", "phone"],
                  "Entregador", "name", ["vehicle_type", "status"], "/entregadores")
    await collect("orders", ["code", "customer_name", "restaurant_name"],
                  "Pedido", "code", ["restaurant_name", "customer_name"], "/pedidos")
    await collect("leads", ["name", "contact_name", "city"],
                  "Lead", "name", ["city", "stage"], "/funil")
    await collect("payments", ["creditor"],
                  "Pagamento", "creditor", ["status", "due_date"], "/contratos-pagamentos")
    return {"results": results}


@router.get("/timeline/{entity_type}/{entity_id}")
async def timeline(entity_type: str, entity_id: str, user: dict = Depends(get_current_user)):
    """Linha do tempo de um cadastro: interações, tarefas e alterações."""
    atividades = await db.activities.find(
        {"related_type": entity_type, "related_id": entity_id}, PROJECTION
    ).sort("created_at", -1).to_list(100)

    logs = await db.audit_logs.find(
        {"entity_id": entity_id}, PROJECTION
    ).sort("created_at", -1).to_list(50)

    eventos = [
        {"at": a["created_at"], "origem": "atividade", "tipo": a.get("type"),
         "titulo": a.get("title"), "detalhe": a.get("description", ""),
         "autor": a.get("owner_name"), "done": a.get("done"), "id": a["id"]}
        for a in atividades
    ] + [
        {"at": l["created_at"], "origem": "sistema", "tipo": l.get("action"),
         "titulo": f"{l.get('action')} {l.get('entity')}", "detalhe": l.get("changes", {}),
         "autor": l.get("actor_name"), "done": True, "id": l["id"]}
        for l in logs
    ]
    eventos.sort(key=lambda e: e["at"], reverse=True)
    return {"eventos": eventos[:120]}


@router.get("/audit")
async def audit_log(
    entity: str = "todos",
    actor_id: str = "",
    page: int = 1,
    page_size: int = 50,
    admin: dict = Depends(require_admin),
):
    query: dict = {}
    if entity != "todos":
        query["entity"] = entity
    if actor_id:
        query["actor_id"] = actor_id
    return await paginate("audit_logs", query, page=page, page_size=page_size)
