"""Efeitos financeiros de um pedido entregue.

Antes, `total_deliveries` e `balance_due` eram números fixos do seed: nada no
sistema os movia. Entregar um pedido não mudava nada. Aqui a entrega passa a
alimentar os contadores e o saldo a repassar, usando a regra do contrato ativo
da parte.

`orders_month` não é guardado: um contador mensal gravado no documento nunca
virava o mês e só crescia. Ele é calculado na leitura, em `routers/restaurants`.

A aplicação é idempotente: o pedido guarda `financials_applied`, então reprocessar
o mesmo pedido (ou alternar o status ida e volta) não soma duas vezes.

No Mongo essa trava era ler-depois-gravar: a tela e o webhook do marketplace
marcando o mesmo pedido como entregue no mesmo instante passavam os dois pela
leitura e lançavam em dobro. Aqui o pedido é *reivindicado* no próprio UPDATE
(`WHERE NOT financials_applied`): só uma das chamadas recebe a linha de volta,
e só ela lança.
"""
from . import pg, repo
from .security import now_utc


async def _active_contract(party_type: str, party_id: str, party_name: str) -> dict | None:
    if party_id:
        found = await pg.um(
            "SELECT * FROM contracts WHERE party_type = $1 AND status = 'ativo' "
            "AND party_id = $2 ORDER BY created_at DESC LIMIT 1",
            party_type, party_id,
        )
        if found:
            return found
    return await pg.um(
        "SELECT * FROM contracts WHERE party_type = $1 AND status = 'ativo' "
        "AND party_name = $2 ORDER BY created_at DESC LIMIT 1",
        party_type, party_name,
    )


def driver_earning(contract: dict | None, order: dict) -> float:
    """Quanto o entregador ganha por esta entrega, conforme a regra do contrato."""
    if not contract:
        # Sem contrato cadastrado, o entregador recebe a taxa de entrega cheia.
        return round(float(order.get("delivery_fee") or 0), 2)

    rule, value = contract.get("rule_type"), max(0.0, float(contract.get("value") or 0))
    if rule == "valor_km":
        return round(value * max(0.0, float(order.get("distance_km") or 0)), 2)
    if rule == "comissao_entrega":
        base = float(order.get("delivery_fee") or 0) or float(order.get("amount") or 0)
        return round(max(0.0, base) * value / 100, 2)
    # taxa_fixa é mensal: não gera valor por entrega.
    return 0.0


def restaurant_commission(restaurant: dict | None, contract: dict | None, order: dict) -> float:
    """Comissão que a Miliano tem a receber do restaurante por esta entrega."""
    rate = None
    if contract and contract.get("rule_type") == "comissao_entrega":
        rate = float(contract.get("value") or 0)
    elif restaurant:
        rate = float(restaurant.get("commission_rate") or 0)
    # Cadastros antigos chegaram a gravar comissão negativa ou acima de 100%,
    # porque a API não validava. O cálculo não pode propagar esse erro.
    rate = min(100.0, max(0.0, rate or 0.0))
    if not rate:
        return 0.0
    return round(max(0.0, float(order.get("amount") or 0)) * rate / 100, 2)


async def apply_delivery(order: dict) -> dict:
    """Lança os efeitos de uma entrega. Devolve o resumo lançado."""
    # Reivindica o pedido: se outra chamada já lançou (ou está lançando), não
    # volta linha nenhuma e nada é somado.
    order = await pg.um(
        "UPDATE orders SET financials_applied = TRUE "
        "WHERE id = $1 AND NOT financials_applied RETURNING *",
        order["id"],
    )
    if not order:
        return {}

    driver = None
    if order.get("driver_id"):
        driver = await repo.pegar("drivers", order["driver_id"])
    elif order.get("driver_name"):
        driver = await repo.um_por("drivers", "name", order["driver_name"])

    restaurant = None
    if order.get("restaurant_id"):
        restaurant = await repo.pegar("restaurants", order["restaurant_id"])
    elif order.get("restaurant_name"):
        restaurant = await repo.um_por("restaurants", "name", order["restaurant_name"])

    agora = now_utc()
    earning = 0.0
    if driver:
        contract = await _active_contract("entregador", driver["id"], driver["name"])
        earning = driver_earning(contract, order)
        await repo.incrementar(
            "drivers", driver["id"],
            {"total_deliveries": 1, "balance_due": earning},
            definir={"updated_at": agora},
        )

    commission = 0.0
    if restaurant:
        contract = await _active_contract("restaurante", restaurant["id"], restaurant["name"])
        commission = restaurant_commission(restaurant, contract, order)
        await repo.incrementar(
            "restaurants", restaurant["id"],
            {
                "orders_total": 1,
                "revenue_total": float(order.get("amount") or 0),
                "commission_due": commission,
            },
            definir={"updated_at": agora},
        )

    lancamento = {
        "financials_applied": True,
        "driver_earning": earning,
        "platform_commission": commission,
        # Guarda quem foi efetivamente creditado e sobre qual valor. O estorno
        # devolve exatamente isto, em vez de refazer a busca: um pedido sem
        # `driver_id` era creditado pelo nome e depois não era debitado, porque
        # o estorno só olhava o id — o saldo ficava inflado para sempre.
        "credited_driver_id": driver["id"] if driver else "",
        "credited_restaurant_id": restaurant["id"] if restaurant else "",
        "credited_amount": float(order.get("amount") or 0),
        "delivered_at": agora,
    }
    await repo.atualizar("orders", order["id"], lancamento)
    return lancamento


async def revert_delivery(order: dict) -> None:
    """Desfaz os lançamentos quando uma entrega é cancelada ou revertida.

    Os valores a devolver são lidos da linha no momento em que o lançamento é
    desmarcado — no mesmo comando —, e não do dicionário recebido: ele pode
    ser uma leitura velha, de antes de outra chamada já ter estornado.
    """
    antes = await pg.um(
        """
        UPDATE orders AS o
           SET financials_applied = FALSE, driver_earning = 0, platform_commission = 0,
               credited_driver_id = '', credited_restaurant_id = '', credited_amount = 0,
               delivered_at = NULL
          FROM (SELECT * FROM orders WHERE id = $1 AND financials_applied FOR UPDATE) AS antes
         WHERE o.id = antes.id
        RETURNING antes.*
        """,
        order["id"],
    )
    if not antes:
        return

    earning = float(antes.get("driver_earning") or 0)
    commission = float(antes.get("platform_commission") or 0)
    valor = float(antes.get("credited_amount") or antes.get("amount") or 0)

    # Pedidos lançados antes deste campo existir caem no id do próprio pedido.
    driver_id = antes.get("credited_driver_id") or antes.get("driver_id")
    restaurant_id = antes.get("credited_restaurant_id") or antes.get("restaurant_id")

    if not driver_id and antes.get("driver_name"):
        achado = await repo.um_por("drivers", "name", antes["driver_name"])
        driver_id = achado["id"] if achado else ""
    if not restaurant_id and antes.get("restaurant_name"):
        achado = await repo.um_por("restaurants", "name", antes["restaurant_name"])
        restaurant_id = achado["id"] if achado else ""

    agora = now_utc()
    if driver_id:
        await repo.incrementar(
            "drivers", driver_id,
            {"total_deliveries": -1, "balance_due": -earning},
            definir={"updated_at": agora},
        )
    if restaurant_id:
        await repo.incrementar(
            "restaurants", restaurant_id,
            {"orders_total": -1, "revenue_total": -valor, "commission_due": -commission},
            definir={"updated_at": agora},
        )
