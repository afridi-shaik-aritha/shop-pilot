from app.agent import AgentResult, ShoppingAgent
from app.cart.service import CartService
from app.catalog.service import ProductService
from app.checkout.service import CheckoutService, OrderService
from app.llm import FakeLLM, LLMMessage, ToolCall
from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products
from app.state.models import Cart
from app.tools import build_tools


def _agent(script, allowed=None):
    products = load_products("data/products.json")
    catalog = ProductService(products)
    carts = CartService(catalog)
    tools = build_tools(
        ProductIndex(products), catalog, carts, CheckoutService(carts), OrderService(catalog)
    )
    if allowed is not None:
        tools = {k: v for k, v in tools.items() if k in allowed}
    return ShoppingAgent(llm=FakeLLM(script), tools=tools), {"cart": Cart(), "checkout": None}


def test_agent_search_then_answer():
    agent, ctx = _agent(
        [
            LLMMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="search_products",
                        arguments={"query": "wireless headphones", "top_k": 2},
                    )
                ],
            ),
            LLMMessage(content="Top pick: SonicWave X5 at 8499.", tool_calls=[]),
        ]
    )
    res = agent.run("Find me wireless headphones", ctx)
    assert isinstance(res, AgentResult)
    assert res.status == "ok"
    assert "SonicWave" in res.text
    assert res.tool_calls_made == 1


def test_agent_unknown_tool_is_reported():
    agent, ctx = _agent(
        [
            LLMMessage(
                content="", tool_calls=[ToolCall(name="teleport", arguments={})]
            ),
            LLMMessage(content="Sorry, I cannot teleport you.", tool_calls=[]),
        ]
    )
    res = agent.run("Teleport me", ctx)
    assert res.status == "ok"
    assert "teleport" in res.text.lower()


def test_agent_step_budget_stops_loops():
    script = [
        LLMMessage(
            content="",
            tool_calls=[ToolCall(name="get_cart", arguments={})],
        )
        for _ in range(30)
    ]
    agent, ctx = _agent(script)
    agent.max_steps = 5
    agent.max_tool_calls = 3
    res = agent.run("Loop forever", ctx)
    assert res.status == "failed"
    assert res.tool_calls_made == 3
