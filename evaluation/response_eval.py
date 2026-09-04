"""Response grounding report over two scripted agent scenarios.

Scenario A (grounded) must pass; scenario B (hallucinated) must fail.
Exit code is always 0 — this is a report, safety_eval.py is the gate.
"""
import sys

sys.path.insert(0, ".")

from app.agent import ShoppingAgent
from app.cart.service import CartService
from app.catalog.service import ProductService
from app.checkout.service import CheckoutService, OrderService
from app.llm import FakeLLM, LLMMessage, ToolCall
from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products
from app.state.models import Cart
from app.tools import build_tools
from evaluation.grounding import grounding_ok


def _run(final_text: str):
    products = load_products("data/products.json")
    catalog = ProductService(products)
    carts = CartService(catalog)
    tools = build_tools(
        ProductIndex(products), catalog, carts, CheckoutService(carts), OrderService(catalog)
    )
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="search_products", arguments={"query": "wireless headphones long battery life", "top_k": 2})]),
        LLMMessage(content=final_text, tool_calls=[]),
    ]
    result = ShoppingAgent(llm=FakeLLM(script), tools=tools).run(
        "headphones", {"cart": Cart(), "checkout": None}
    )
    ok, detail = grounding_ok(result.text, str(result.trace))
    return ok, detail


def run_scenarios() -> list[dict]:
    rows = []
    ok_a, detail_a = _run("SonicWave X5 (P01) costs 8499.0 with rating 4.4.")
    rows.append({"scenario": "grounded-answer", "grounded": ok_a, **detail_a})
    ok_b, detail_b = _run("P01 costs 100.0 and P99 is better.")
    rows.append({"scenario": "hallucinated-price", "grounded": ok_b, **detail_b})
    ok_c, detail_c = _run("P01 is a steal at $84.99.")
    rows.append({"scenario": "currency-drift", "grounded": ok_c, **detail_c})
    return rows


def main() -> int:
    print("| scenario | grounded | missing |")
    print("|---|---|---|")
    for row in run_scenarios():
        missing = row["missing_numbers"] + row["missing_ids"]
        print(f"| {row['scenario']} | {row['grounded']} | {missing} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
