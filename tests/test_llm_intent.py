from app.llm import FakeLLM, LLMMessage, ToolCall
from app.structured_output import IntentConstraints, parse_intent


def test_fake_llm_replays_script():
    llm = FakeLLM(
        [
            LLMMessage(
                content="",
                tool_calls=[ToolCall(name="search_products", arguments={"query": "x"})],
            ),
            LLMMessage(content="done", tool_calls=[]),
        ]
    )
    first = llm.complete([], [])
    assert first.tool_calls[0].name == "search_products"
    second = llm.complete([], [])
    assert second.content == "done"


def test_parse_intent_budget_and_category():
    c = parse_intent("I need wireless headphones under 10000 with good battery life")
    assert c.category == "wireless headphones"
    assert c.max_price == 10000
    assert "battery" in " ".join(c.desired_attributes)


def test_parse_intent_empty():
    c = parse_intent("looking for a nice gift")
    assert c.category is None
    assert c.max_price is None
    assert isinstance(c, IntentConstraints)


def test_toolcall_model():
    t = ToolCall(name="get_cart", arguments={})
    assert t.name == "get_cart"
    assert t.arguments == {}
