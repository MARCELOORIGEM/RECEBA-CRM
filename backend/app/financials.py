"""Efeitos financeiros de um pedido entregue.

Antes, `total_deliveries` e `balance_due` eram números fixos do seed: nada no
sistema os movia. Entregar um pedido não mudava nada. Aqui a entrega passa a
alimentar os contadores e o saldo a repassar, usando a regra do contrato ativo
da parte.

`orders_month` não é guardado: um contador mensal gravado no documento nunca
virava o mês e só crescia. Ele é calculado na leitura, em `routers/restaurants`.

A aplicação é idempotente: o pedido guarda `financials_applied`, então reprocessar
o mesmo pedido (ou alternar o status ida e volta) não soma duas vezes.
"""
from .db import db
from .security import now_iso


async def _active_contract(party_type: str, party_id: str, party_name: str) -> dict | None:
    query = {"party_type": party_type, "status": "ativo"}
    if party_id:
        found = await db.contracts.find_one({**query, "party_id": party_id}, {"_id": 0})
        if found:
            return found
    return await db.contracts.find_one({**query, "party_name": party_name}, {"_id": 0})


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
    if order.get("financials_applied"):
        return {}

    driver = None
    if order.get("driver_id"):
        driver = await db.drivers.find_one({"id": order["driver_id"]}, {"_id": 0})
    elif order.get("driver_name"):
        driver = await db.drivers.find_one({"name": order["driver_name"]}, {"_id": 0})

    restaurant = None
    if order.get("restaurant_id"):
        restaurant = await db.restaurants.find_one({"id": order["restaurant_id"]}, {"_id": 0})
    elif order.get("restaurant_name"):
        restaurant = await db.restaurants.find_one({"name": order["restaurant_name"]}, {"_id": 0})

    earning = 0.0
    if driver:
        contract = await _active_contract("entregador", driver["id"], driver["name"])
        earning = driver_earning(contract, order)
        await db.drivers.update_one(
            {"id": driver["id"]},
            {"$inc": {"total_deliveries": 1, "balance_due": earning},
             "$set": {"updated_at": now_iso()}},
        )

    commission = 0.0
    if restaurant:
        contract = await _active_contract("restaurante", restaurant["id"], restaurant["name"])
        commission = restaurant_commission(restaurant, contract, order)
        await db.restaurants.update_one(
            {"id": restaurant["id"]},
            {"$inc": {
                "orders_total": 1,
                "revenue_total": float(order.get("amount") or 0),
                "commission_due": commission,
            },
             "$set": {"updated_at": now_iso()}},
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
        "delivered_at": now_iso(),
    }
    await db.orders.update_one({"id": order["id"]}, {"$set": lancamento})
    return lancamento


async def revert_delivery(order: dict) -> None:
    """Desfaz os lançamentos quando uma entrega é cancelada ou revertida."""
    if not order.get("financials_applied"):
        return

    earning = float(order.get("driver_earning") or 0)
    commission = float(order.get("platform_commission") or 0)
    valor = float(order.get("credited_amount", order.get("amount")) or 0)

    # Pedidos lançados antes deste campo existir caem no id do próprio pedido.
    driver_id = order.get("credited_driver_id") or order.get("driver_id")
    restaurant_id = order.get("credited_restaurant_id") or order.get("restaurant_id")

    if not driver_id and order.get("driver_name"):
        achado = await db.drivers.find_one({"name": order["driver_name"]}, {"_id": 0, "id": 1})
        driver_id = achado["id"] if achado else ""
    if not restaurant_id and order.get("restaurant_name"):
        achado = await db.restaurants.find_one(
            {"name": order["restaurant_name"]}, {"_id": 0, "id": 1}
        )
        restaurant_id = achado["id"] if achado else ""

    if driver_id:
        await db.drivers.update_one(
            {"id": driver_id},
            {"$inc": {"total_deliveries": -1, "balance_due": -earning},
             "$set": {"updated_at": now_iso()}},
        )
    if restaurant_id:
        await db.restaurants.update_one(
            {"id": restaurant_id},
            {"$inc": {
                "orders_total": -1,
                "revenue_total": -valor,
                "commission_due": -commission,
            },
             "$set": {"updated_at": now_iso()}},
        )
    await db.orders.update_one(
        {"id": order["id"]},
        {"$set": {"financials_applied": False, "driver_earning": 0.0,
                  "platform_commission": 0.0, "credited_driver_id": "",
                  "credited_restaurant_id": "", "delivered_at": None}},
    )
