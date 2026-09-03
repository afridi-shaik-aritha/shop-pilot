from app.agent import ShoppingAgent
from app.cart.service import CartService
from app.catalog.service import ProductService
from app.checkout.service import CheckoutService, OrderService
from app.llm import FakeLLM, LLMMessage, ToolCall
from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products
from app.state.models import Cart
from app.tools import build_tools


def _agent(script):
    products = load_products("data/products.json")
    catalog = ProductService(products)
    carts = CartService(catalog)
    tools = build_tools(
        ProductIndex(products), catalog, carts, CheckoutService(carts), OrderService(catalog)
    )
    return ShoppingAgent(llm=FakeLLM(script), tools=tools), {"cart": Cart(), "checkout": None}


def test_agent_llm_failure_is_failed_result():
    agent, ctx = _agent(
        [LLMMessage(content="", tool_calls=[ToolCall(name="get_cart", arguments={})])]
    )
    res = agent.run("hi", ctx)
    assert res.status == "failed"
    assert "LLM error" in res.text
    assert res.tool_calls_made == 1


def test_agent_invalid_args_become_error_data():
    agent, ctx = _agent(
        [
            LLMMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="search_products",
                        arguments={"query": "x", "top_k": "many"},
                    )
                ],
            ),
            LLMMessage(content="let me restate", tool_calls=[]),
        ]
    )
    res = agent.run("hi", ctx)
    assert res.status == "ok"
    assert "ToolValidationError" in str(res.trace[0]["result"])
