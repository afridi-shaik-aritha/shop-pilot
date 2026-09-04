from app.agent import AgentResult, ShoppingAgent, _model_visible
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


def test_agent_step_budget_tail_allows_final_answer():
    """When the step budget runs out mid-reasoning, the agent gets ONE final
    no-tools completion so it can answer from the results it already has
    instead of dead-ending with a stop message."""
    agent, ctx = _agent(
        [
            LLMMessage(content="", tool_calls=[ToolCall(name="get_cart", arguments={})]),
            LLMMessage(content="The cart has 0 items.", tool_calls=[]),
        ]
    )
    agent.max_steps = 1  # exhausts on the very first tool-calling step
    agent.max_tool_calls = 5
    res = agent.run("What is in my cart?", ctx)
    assert res.status == "ok"
    assert res.text == "The cart has 0 items."
    assert res.tool_calls_made == 1


def test_agent_step_budget_tail_stops_if_model_keeps_calling():
    """If the final completion still demands tools, the agent stops honestly."""
    agent, ctx = _agent(
        [
            LLMMessage(content="", tool_calls=[ToolCall(name="get_cart", arguments={})]),
            LLMMessage(content="", tool_calls=[ToolCall(name="get_cart", arguments={})]),
        ]
    )
    agent.max_steps = 1
    agent.max_tool_calls = 5
    res = agent.run("Loop forever", ctx)
    assert res.status == "failed"
    assert "Stopped: step budget exceeded" in res.text
    assert res.tool_calls_made == 1


class _CaptureLLM:
    """Records every message list it is asked to complete (no network)."""

    def __init__(self, reply="ok"):
        self._reply = reply
        self.seen = []

    def complete(self, messages, tools):
        self.seen.append(list(messages))
        return LLMMessage(content=self._reply, tool_calls=[])


def test_agent_replays_plain_history_only_and_truncates():
    cap = _CaptureLLM()
    agent = ShoppingAgent(llm=cap, tools={}, system_prompt="sys")
    agent.run(
        "buy it",
        {"cart": Cart(), "checkout": None},
        history=[
            {"role": "user", "content": "earlier ask"},
            {"role": "assistant", "content": "earlier reply"},
            {"role": "system", "content": "drop me"},
            {"role": "tool", "name": "x", "content": "drop me too"},
            {"role": "user", "content": "z" * 5000},
        ],
    )
    msgs = cap.seen[0]
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "user", "user"]
    assert msgs[1]["content"] == "earlier ask"
    assert msgs[2]["content"] == "earlier reply"
    assert len(msgs[3]["content"]) == 4000  # truncated, not dropped
    assert msgs[4]["content"] == "buy it"  # current turn is never dropped
    assert msgs[0]["content"] == "sys"


def test_model_visible_redacts_confirmation_token():
    raw = {
        "status": "AWAITING_CONFIRMATION",
        "total": 10028.82,
        "confirmation_token": "tok-secret-123",
    }
    visible = _model_visible(raw)
    assert visible["status"] == "AWAITING_CONFIRMATION"
    assert visible["total"] == 10028.82
    assert visible["confirmation_token"] != "tok-secret-123"
    assert "tok-secret-123" not in str(visible)


def test_agent_never_sees_confirmation_token_in_prepare():
    """prepare_checkout succeeds, but the token never reaches the model text."""
    from app.cart.service import CartService as _CartService

    products = load_products("data/products.json")
    catalog = ProductService(products)
    carts = _CartService(catalog)
    tools = build_tools(
        ProductIndex(products), catalog, carts, CheckoutService(carts), OrderService(catalog)
    )
    agent = ShoppingAgent(
        llm=FakeLLM(
            [
                LLMMessage(
                    content="",
                    tool_calls=[ToolCall(name="prepare_checkout", arguments={})],
                ),
                LLMMessage(content="The slip is ready.", tool_calls=[]),
            ]
        ),
        tools={k: v for k, v in tools.items() if k in ("prepare_checkout", "get_cart")},
    )
    ctx = {"cart": Cart(), "checkout": None}
    carts.add_to_cart(ctx["cart"], "P01", 1)
    res = agent.run("Check me out", ctx)
    assert res.status == "ok"
    assert "[redacted" in str(res.trace)
    assert "tok-secret-123" not in "".join(str(t) for t in res.trace)
    # token stayed in the real checkout state, just not in the model trace
    assert ctx["checkout"].confirmation_token
