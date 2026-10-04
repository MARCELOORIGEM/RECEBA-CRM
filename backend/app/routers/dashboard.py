"""Painel principal.

Correções em relação à versão anterior:
- `entregas_hoje` contava TODOS os pedidos da base, de qualquer data.
- `taxa_sucesso` dividia entregues pelo total, incluindo pedidos ainda em rota —
  o número caía sozinho a cada pedido novo, sem nada ter dado errado.
- `faturamento` somava o valor das compras (que é do restaurante) e chamava isso
  de faturamento da Miliano. A receita da operação é a comissão.

Sobre o desenho das consultas: no Mongo o painel fazia umas 25 idas ao banco,
uma atrás da outra. Com o banco remoto, cada ida custa a viagem inteira — 25
delas a 200 ms seriam 5 segundos para abrir a tela inicial. Aqui são três
consultas, em paralelo: uma com todos os números e listas agregadas
(`count(*) FILTER (WHERE ...)` calcula vários recortes numa passada, e
`json_agg` devolve cada lista pronta), e duas com as linhas dos pedidos
recentes e dos pagamentos pendentes.
"""
import asyncio

from fastapi import APIRouter, Depends

from .. import pg, tempo
from ..config import settings
from ..deps import get_current_user
from ..security import now_utc

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ABERTOS = ("novo", "contatado", "negociacao", "proposta")


def _delta(atual: float, anterior: float) -> float:
    if not anterior:
        return 100.0 if atual else 0.0
    return round((atual - anterior) / anterior * 100, 1)


def _r(valor) -> float:
    return round(float(valor or 0), 2)


@router.get("/stats")
async def stats(user: dict = Depends(get_current_user)):
    # Fronteiras de dia no fuso do negócio, não em UTC.
    agora = now_utc()
    inicio_hoje = tempo.inicio_do_dia()
    fim_hoje = tempo.fim_do_dia()
    inicio_ontem = tempo.inicio_do_dia(-1)
    inicio_mes = tempo.inicio_do_mes()

    # Tudo o que é agregado sai de UM comando: os números de uma linha (uma
    # CTE por tabela) e as listas do gráfico, cada uma como um array JSON
    # montado pelo próprio banco (`json_agg`). Em consultas separadas eram
    # nove conexões ao mesmo tempo — e o pooler do Supabase em modo sessão
    # aceita 15 para a API inteira, somando todos os workers.
    numeros = pg.um(
        """
        WITH p AS (
        SELECT
            count(*) FILTER (WHERE created_at >= $1)                          AS pedidos_hoje,
            count(*) FILTER (WHERE created_at >= $2 AND created_at < $1)      AS pedidos_ontem,
            count(*) FILTER (WHERE created_at >= $1 AND status = 'entregue')  AS entregas_hoje,
            count(*) FILTER (WHERE created_at >= $2 AND created_at < $1
                               AND status = 'entregue')                       AS entregas_ontem,
            count(*) FILTER (WHERE status IN ('aguardando_coleta', 'em_transito')) AS em_rota,
            count(*) FILTER (WHERE status = 'entregue')                       AS entregues_total,
            count(*) FILTER (WHERE status = 'cancelado')                      AS cancelados_total,
            count(*) FILTER (WHERE created_at >= $3 AND status = 'entregue')  AS entregas_mes,
            COALESCE(SUM(amount) FILTER (WHERE created_at >= $3
                                           AND status = 'entregue'), 0)       AS gmv_mes,
            COALESCE(SUM(platform_commission) FILTER (WHERE created_at >= $3
                                           AND status = 'entregue'), 0)       AS receita_mes,
            COALESCE(SUM(driver_earning) FILTER (WHERE created_at >= $3
                                           AND status = 'entregue'), 0)       AS custo_entregadores
        FROM orders
        ), pag AS (
        SELECT
            COALESCE(SUM(amount) FILTER (WHERE status IN ('pendente', 'atrasado')), 0)
                AS repasse_pendente,
            count(*) FILTER (WHERE status IN ('pendente', 'atrasado') AND due_date < $4)
                AS vencidos
        FROM payments
        ), ag AS (
        SELECT
            count(*) FILTER (WHERE due_at < $5)                    AS atrasadas,
            count(*) FILTER (WHERE due_at >= $1 AND due_at <= $6)  AS hoje
        FROM activities WHERE NOT done
        )
        SELECT p.*, pag.*, ag.*,
            (SELECT count(*) FROM restaurants WHERE status = 'ativo') AS restaurantes_ativos,
            (SELECT count(*) FROM restaurants)                         AS restaurantes,
            (SELECT count(*) FROM drivers
              WHERE status IN ('disponivel', 'em_entrega'))           AS entregadores_online,
            (SELECT count(*) FROM drivers)                             AS entregadores,

            -- Volume por hora do dia corrente, no relógio local.
            (SELECT COALESCE(json_agg(t), '[]') FROM (
                SELECT extract(hour FROM created_at AT TIME ZONE $7)::int AS hora,
                       count(*) AS qtd
                  FROM orders WHERE created_at >= $1 GROUP BY 1
            ) t) AS por_hora,

            -- Últimos 14 dias, agrupados pelo dia local do `created_at`.
            (SELECT COALESCE(json_agg(t), '[]') FROM (
                SELECT to_char(created_at AT TIME ZONE $7, 'YYYY-MM-DD') AS dia,
                       count(*) AS pedidos,
                       count(*) FILTER (WHERE status = 'entregue') AS entregues
                  FROM orders WHERE created_at >= $8 GROUP BY 1
            ) t) AS por_dia,

            -- Junção com o cadastro só para pegar a categoria. LEFT porque o
            -- pedido pode ter restaurante apagado ou só o nome: vira "Outros".
            (SELECT COALESCE(json_agg(t), '[]') FROM (
                SELECT COALESCE(NULLIF(r.category, ''), 'Outros') AS categoria,
                       count(*) AS total, COALESCE(SUM(o.amount), 0) AS valor
                  FROM orders o LEFT JOIN restaurants r ON r.id = o.restaurant_id
                 WHERE o.status = 'entregue'
                 GROUP BY 1 ORDER BY total DESC LIMIT 8
            ) t) AS por_categoria,

            (SELECT COALESCE(json_agg(t), '[]') FROM (
                SELECT status, count(*) AS qtd FROM orders GROUP BY status
            ) t) AS por_status,

            (SELECT COALESCE(json_agg(t), '[]') FROM (
                SELECT restaurant_name AS nome, count(*) AS entregas,
                       COALESCE(SUM(amount), 0) AS valor
                  FROM orders WHERE created_at >= $3 AND status = 'entregue'
                 GROUP BY restaurant_name ORDER BY valor DESC LIMIT 5
            ) t) AS top,

            (SELECT COALESCE(json_agg(t), '[]') FROM (
                SELECT stage, count(*) AS qtd, COALESCE(SUM(estimated_value), 0) AS valor
                  FROM leads GROUP BY stage
            ) t) AS funil
        FROM p, pag, ag
        """,
        inicio_hoje, inicio_ontem, inicio_mes, tempo.hoje_local(), agora, fim_hoje,
        settings.timezone, tempo.inicio_do_dia(-13),
    )

    # As duas listas de linhas inteiras vão à parte, para voltarem com os
    # tipos do driver (datas como datetime), iguais às das outras rotas.
    recentes = pg.varios("SELECT * FROM orders ORDER BY created_at DESC LIMIT 8")
    pendentes = pg.varios(
        "SELECT * FROM payments WHERE status IN ('pendente', 'atrasado') "
        "ORDER BY due_date ASC LIMIT 6"
    )

    p, recentes, pendentes = await asyncio.gather(numeros, recentes, pendentes)
    por_hora, por_dia, por_categoria = p["por_hora"], p["por_dia"], p["por_categoria"]
    por_status, top, funil = p["por_status"], p["top"], p["funil"]

    # Taxa de sucesso só faz sentido sobre pedidos que já terminaram.
    finalizados = p["entregues_total"] + p["cancelados_total"]
    taxa_sucesso = round(p["entregues_total"] / finalizados * 100, 1) if finalizados else 0.0
    gmv_mes, receita_mes = _r(p["gmv_mes"]), _r(p["receita_mes"])
    custo_entregadores = _r(p["custo_entregadores"])
    entregas_mes = p["entregas_mes"]

    hora = {r["hora"]: r["qtd"] for r in por_hora}
    hourly = [{"hora": f"{h:02d}h", "entregas": hora.get(h, 0)} for h in range(8, 23)]

    dias = {r["dia"]: r for r in por_dia}
    trend = []
    for i in range(13, -1, -1):
        dia = tempo.dia_local(-i)
        bucket = dias.get(dia, {})
        trend.append({
            "dia": f"{dia[8:10]}/{dia[5:7]}",
            "pedidos": bucket.get("pedidos", 0),
            "entregues": bucket.get("entregues", 0),
        })

    etapas = {r["stage"]: r for r in funil}

    return {
        "kpi": {
            "pedidos_hoje": p["pedidos_hoje"],
            "pedidos_hoje_delta": _delta(p["pedidos_hoje"], p["pedidos_ontem"]),
            "entregas_hoje": p["entregas_hoje"],
            "entregas_hoje_delta": _delta(p["entregas_hoje"], p["entregas_ontem"]),
            "em_rota": p["em_rota"],
            "taxa_sucesso": taxa_sucesso,
            "restaurantes_ativos": p["restaurantes_ativos"],
            "entregadores_online": p["entregadores_online"],
        },
        "financeiro": {
            "gmv_mes": gmv_mes,
            "receita_mes": receita_mes,
            "custo_entregadores": custo_entregadores,
            "margem_mes": round(receita_mes - custo_entregadores, 2),
            "ticket_medio": round(gmv_mes / entregas_mes, 2) if entregas_mes else 0.0,
            "repasse_pendente": _r(p["repasse_pendente"]),
            "repasses_vencidos": p["vencidos"],
            "restaurantes": p["restaurantes"],
            "entregadores": p["entregadores"],
        },
        "funil": {
            "em_aberto": sum(etapas.get(s, {}).get("qtd", 0) for s in ABERTOS),
            "valor_em_aberto": _r(sum(float(etapas.get(s, {}).get("valor", 0)) for s in ABERTOS)),
            "ganhos": etapas.get("ganho", {}).get("qtd", 0),
            "perdidos": etapas.get("perdido", {}).get("qtd", 0),
        },
        "agenda": {"atrasadas": p["atrasadas"], "hoje": p["hoje"]},
        "hourly": hourly,
        "trend": trend,
        "by_category": [
            {"categoria": r["categoria"], "total": r["total"], "valor": _r(r["valor"])}
            for r in por_categoria
        ],
        "status_counts": {r["status"]: r["qtd"] for r in por_status},
        "top_restaurantes": [
            {"nome": r["nome"] or "—", "entregas": r["entregas"], "valor": _r(r["valor"])}
            for r in top
        ],
        "recent_orders": recentes,
        "pending_payments": pendentes,
    }
