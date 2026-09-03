"""End-to-end demo: search -> compare -> cart -> checkout -> explicit
confirmation -> revalidation -> exactly one order, plus the blocked path.

The shopper confirms by typing the printed confirmation token. Anything else
(including the word CONFIRM alone) does NOT confirm.
"""
import sys

sys.path.insert(0, ".")  # allow `python demo/cli.py` from the repo root

from app.agent import ShoppingAgent
from app.cart.service import CartService
from app.catalog.service import ProductService
from app.checkout.service import CheckoutService, ConfirmationError, OrderService
from app.llm import FakeLLM, LLMMessage, ToolCall
from app.prompts import CONFIRM_REQUEST_TEMPLATE
from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products, load_reviews
from app.state.models import Cart
from app.structured_output import parse_intent
from app.tools import build_tools


def _wired():
    products = load_products("data/products.json")
    catalog = ProductService(products)
    carts = CartService(catalog)
    checkout = CheckoutService(carts)
    orders = OrderService(catalog)
    index = ProductIndex(products)
    tools = build_tools(index, catalog, carts, checkout, orders)
    return products, tools


def run_demo(input_fn=input, print_fn=print) -> dict:
    products, tools = _wired()
    intent = parse_intent("I need wireless headphones under 10000 with good reviews")
    print_fn(f"Intent: {intent.model_dump()}")

    script = [
        LLMMessage(
            content="",
            tool_calls=[
                ToolCall(
                    name="search_products",
                    arguments={"query": "wireless headphones battery", "top_k": 3},
                )
            ],
        ),
        LLMMessage(
            content="",
            tool_calls=[ToolCall(name="compare_products", arguments={"product_ids": ["P01", "P02"]})],
        ),
        LLMMessage(content="Top pick: SonicWave X5 at 8499, great battery.", tool_calls=[]),
    ]
    agent = ShoppingAgent(llm=FakeLLM(script), tools=tools)
    ctx: dict = {"cart": Cart(), "checkout": None}
    rec = agent.run("wireless headphones under 10000", ctx)
    print_fn(f"Assistant: {rec.text}")

    tools["add_to_cart"].run({"product_id": "P01", "quantity": 1}, ctx)
    prep = tools["prepare_checkout"].run({}, ctx)
    totals = prep["total"]
    lines = ", ".join(
        f"{i['quantity']}x {i['product_id']} @ {i['unit_price']}"
        for i in prep["cart_snapshot"]["items"]
    )
    print_fn(
        CONFIRM_REQUEST_TEMPLATE.format(
            total=totals, currency="INR", lines=lines, token=prep["confirmation_token"]
        )
    )
    print_fn(f"CONFIRMATION_TOKEN={prep['confirmation_token']}")

    blocked_without_confirmation = False
    try:
        tools["place_order"].run({"idempotency_key": "demo-key-1"}, ctx)
    except ConfirmationError:
        blocked_without_confirmation = True
        print_fn("BLOCKED: order without confirmation refused.")

    answer = input_fn("Type the confirmation token to confirm (anything else aborts): ")
    if answer.strip() != prep["confirmation_token"]:
        print_fn("Not confirmed. No order placed.")
        return {
            "order": None,
            "repeat_order_same_id": False,
            "blocked_without_confirmation": blocked_without_confirmation,
        }

    tools["confirm_checkout"].run({"confirmation_token": prep["confirmation_token"]}, ctx)
    order = tools["place_order"].run({"idempotency_key": "demo-key-1"}, ctx)
    repeat = tools["place_order"].run({"idempotency_key": "demo-key-1"}, ctx)
    print_fn(f"Order {order['order_id']} COMPLETED for {order['total']} INR.")
    return {
        "order": order,
        "repeat_order_same_id": repeat["order_id"] == order["order_id"],
        "blocked_without_confirmation": blocked_without_confirmation,
    }


def main() -> None:
    run_demo()


if __name__ == "__main__":
    main()
