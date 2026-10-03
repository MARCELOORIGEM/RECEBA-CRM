"""Painel principal.

Correções em relação à versão anterior:
- `entregas_hoje` contava TODOS os pedidos da base, de qualquer data.
- `taxa_sucesso` dividia entregues pelo total, incluindo pedidos ainda em rota —
  o número caía sozinho a cada pedido novo, sem nada ter dado errado.
- `faturamento` somava o valor das compras (que é do restaurante) e chamava isso
  de faturamento da Miliano. A receita da operação é a comissão.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends

from .. import tempo
from ..config import settings
from ..db import db
from ..deps import get_current_user
from ..security import now_utc

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def _sum(collection: str, match: dict, field: str) -> float:
    pipeline = [{"$match": match}, {"$group": {"_id": None, "t": {"$sum": f"${field}"}}}]
    async for row in db[collection].aggregate(pipeline):
        return round(row["t"], 2)
    return 0.0


def _delta(atual: float, anterior: float) -> float:
    if not anterior:
        return 100.0 if atual else 0.0
    return round((atual - anterior) / anterior * 100, 1)


@router.get("/stats")
async def stats(user: dict = Depends(get_current_user)):
    # Fronteiras de dia no fuso do negócio, não em UTC.
    agora = now_utc()
    inicio_hoje = tempo.inicio_do_dia()
    inicio_ontem = tempo.inicio_do_dia(-1)
    inicio_mes = tempo.inicio_do_mes()

    hoje = {"created_at": {"$gte": inicio_hoje.isoformat()}}
    ontem = {"created_at": {"$gte": inicio_ontem.isoformat(), "$lt": inicio_hoje.isoformat()}}
    mes = {"created_at": {"$gte": inicio_mes.isoformat()}}

    pedidos_hoje = await db.orders.count_documents(hoje)
    pedidos_ontem = await db.orders.count_documents(ontem)
    entregas_hoje = await db.orders.count_documents({**hoje, "status": "entregue"})
    entregas_ontem = await db.orders.count_documents({**ontem, "status": "entregue"})
    em_rota = await db.orders.count_documents(
        {"status": {"$in": ["aguardando_coleta", "em_transito"]}}
    )

    # Taxa de sucesso só faz sentido sobre pedidos que já terminaram.
    entregues_total = await db.orders.count_documents({"status": "entregue"})
    cancelados_total = await db.orders.count_documents({"status": "cancelado"})
    finalizados = entregues_total + cancelados_total
    taxa_sucesso = round(entregues_total / finalizados * 100, 1) if finalizados else 0.0

    gmv_mes = await _sum("orders", {**mes, "status": "entregue"}, "amount")
    receita_mes = await _sum("orders", {**mes, "status": "entregue"}, "platform_commission")
    custo_entregadores = await _sum("orders", {**mes, "status": "entregue"}, "driver_earning")
    entregas_mes = await db.orders.count_documents({**mes, "status": "entregue"})
    ticket_medio = round(gmv_mes / entregas_mes, 2) if entregas_mes else 0.0

    repasse_pendente = await _sum(
        "payments", {"status": {"$in": ["pendente", "atrasado"]}}, "amount"
    )
    vencidos = await db.payments.count_documents(
        {"status": {"$in": ["pendente", "atrasado"]}, "due_date": {"$lt": tempo.dia_local()}}
    )

    # Volume por hora do dia corrente.
    hourly_pipeline = [
        {"$match": hoje},
        {"$group": {
            "_id": {"$hour": {"date": tempo.campo_data("created_at"), "timezone": settings.timezone}},
            "qtd": {"$sum": 1},
        }},
    ]
    por_hora = {r["_id"]: r["qtd"] async for r in db.orders.aggregate(hourly_pipeline)}
    hourly = [{"hora": f"{h:02d}h", "entregas": por_hora.get(h, 0)} for h in range(8, 23)]

    # Últimos 14 dias. Uma agregação agrupando pelo dia do `created_at`, em vez
    # do laço que fazia 28 count_documents — sozinho, ele respondia por quase
    # todo o tempo de resposta do painel.
    inicio_trend = tempo.inicio_do_dia(-13).isoformat()
    trend_pipeline = [
        {"$match": {"created_at": {"$gte": inicio_trend}}},
        {"$group": {
            "_id": {"$dateToString": {
                "format": "%Y-%m-%d",
                "date": tempo.campo_data("created_at"),
                "timezone": settings.timezone,
            }},
            "pedidos": {"$sum": 1},
            "entregues": {"$sum": {"$cond": [{"$eq": ["$status", "entregue"]}, 1, 0]}},
        }},
    ]
    por_dia = {r["_id"]: r async for r in db.orders.aggregate(trend_pipeline)}
    trend = []
    for i in range(13, -1, -1):
        dia = tempo.dia_local(-i)
        bucket = por_dia.get(dia, {})
        trend.append({
            "dia": f"{dia[8:10]}/{dia[5:7]}",
            "pedidos": bucket.get("pedidos", 0),
            "entregues": bucket.get("entregues", 0),
        })

    cat_pipeline = [
        {"$match": {"status": "entregue"}},
        {"$lookup": {"from": "restaurants", "localField": "restaurant_id",
                     "foreignField": "id", "as": "r"}},
        {"$unwind": {"path": "$r", "preserveNullAndEmptyArrays": True}},
        {"$group": {"_id": {"$ifNull": ["$r.category", "Outros"]},
                    "total": {"$sum": 1}, "valor": {"$sum": "$amount"}}},
        {"$sort": {"total": -1}},
        {"$limit": 8},
    ]
    by_category = [
        {"categoria": r["_id"], "total": r["total"], "valor": round(r["valor"], 2)}
        async for r in db.orders.aggregate(cat_pipeline)
    ]

    status_pipeline = [{"$group": {"_id": "$status", "qtd": {"$sum": 1}}}]
    status_counts = {r["_id"]: r["qtd"] async for r in db.orders.aggregate(status_pipeline)}

    top_pipeline = [
        {"$match": {**mes, "status": "entregue"}},
        {"$group": {"_id": "$restaurant_name", "entregas": {"$sum": 1},
                    "valor": {"$sum": "$amount"}}},
        {"$sort": {"valor": -1}},
        {"$limit": 5},
    ]
    top_restaurantes = [
        {"nome": r["_id"] or "—", "entregas": r["entregas"], "valor": round(r["valor"], 2)}
        async for r in db.orders.aggregate(top_pipeline)
    ]

    funil_pipeline = [{"$group": {"_id": "$stage", "qtd": {"$sum": 1},
                                  "valor": {"$sum": "$estimated_value"}}}]
    funil = {r["_id"]: r async for r in db.leads.aggregate(funil_pipeline)}
    abertos = [s for s in ("novo", "contatado", "negociacao", "proposta")]

    atividades_atrasadas = await db.activities.count_documents(
        {"done": False, "due_at": {"$ne": None, "$lt": agora.isoformat()}}
    )
    atividades_hoje = await db.activities.count_documents(
        {"done": False, "due_at": {"$gte": inicio_hoje.isoformat(),
                                   "$lte": tempo.fim_do_dia().isoformat()}}
    )

    return {
        "kpi": {
            "pedidos_hoje": pedidos_hoje,
            "pedidos_hoje_delta": _delta(pedidos_hoje, pedidos_ontem),
            "entregas_hoje": entregas_hoje,
            "entregas_hoje_delta": _delta(entregas_hoje, entregas_ontem),
            "em_rota": em_rota,
            "taxa_sucesso": taxa_sucesso,
            "restaurantes_ativos": await db.restaurants.count_documents({"status": "ativo"}),
            "entregadores_online": await db.drivers.count_documents(
                {"status": {"$in": ["disponivel", "em_entrega"]}}
            ),
        },
        "financeiro": {
            "gmv_mes": gmv_mes,
            "receita_mes": receita_mes,
            "custo_entregadores": custo_entregadores,
            "margem_mes": round(receita_mes - custo_entregadores, 2),
            "ticket_medio": ticket_medio,
            "repasse_pendente": repasse_pendente,
            "repasses_vencidos": vencidos,
            "restaurantes": await db.restaurants.count_documents({}),
            "entregadores": await db.drivers.count_documents({}),
        },
        "funil": {
            "em_aberto": sum(funil.get(s, {}).get("qtd", 0) for s in abertos),
            "valor_em_aberto": round(sum(funil.get(s, {}).get("valor", 0.0) for s in abertos), 2),
            "ganhos": funil.get("ganho", {}).get("qtd", 0),
            "perdidos": funil.get("perdido", {}).get("qtd", 0),
        },
        "agenda": {"atrasadas": atividades_atrasadas, "hoje": atividades_hoje},
        "hourly": hourly,
        "trend": trend,
        "by_category": by_category,
        "status_counts": status_counts,
        "top_restaurantes": top_restaurantes,
        "recent_orders": await db.orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(8),
        "pending_payments": await db.payments.find(
            {"status": {"$in": ["pendente", "atrasado"]}}, {"_id": 0}
        ).sort("due_date", 1).to_list(6),
    }
