# tests/test_roles.py
"""Role-based agents: routing, per-role reach, and grounded policy answers."""
from fastapi.testclient import TestClient

from app.agent import ShoppingAgent
from app.api.routes import create_app
from app.cart.service import CartService
from app.catalog.service import ProductService
from app.checkout.service import CheckoutService, OrderService
from app.config import Settings
from app.llm import FakeLLM, LLMMessage, ToolCall
from app.policy import PolicyService, load_policies
from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products
from app.roles import ROLES, classify, subset_tools
from app.state.models import Cart
from app.tools import build_tools

POLICY = load_policies("data/policies.json")
BLOCKED_EVERYWHERE = {"confirm_checkout", "place_order"}


def _all_tools():
    products = load_products("data/products.json")
    catalog = ProductService(products)
    carts = CartService(catalog)
    return build_tools(
        ProductIndex(products), catalog, carts, CheckoutService(carts), OrderService(catalog)
    )


def _agent(script, role):
    tools = subset_tools(_all_tools(), role)
    return ShoppingAgent(llm=FakeLLM(script), tools=tools, system_prompt=role.prompt), tools


# ---------- policy corpus ----------

def test_policy_service_is_grounded():
    svc = PolicyService(POLICY)
    hits = svc.search("shipping fee threshold free")
    assert hits and hits[0]["policy_id"] == "POL-SHIPPING"
    assert "5,000" in hits[0]["body"]
    assert svc.search("completely unrelated zzz") == []


# ---------- router ----------

def test_router_sends_messages_to_the_right_role():
    assert classify("what is your shipping and return policy?").name == "policy"
    assert classify("how is the gst calculated").name == "policy"
    assert classify("compare P01 vs P02").name == "catalog"
    assert classify("show me a smartwatch with heart-rate tracking").name == "catalog"
    assert classify("what are the specs of P01").name == "catalog"
    assert classify("I need wireless headphones under 10000").name == "cart"
    assert classify("add P01 to my cart").name == "cart"
    assert classify("remove the speaker and prepare checkout").name == "cart"
    assert classify("hello").name == "catalog"


# ---------- reach: the allowlist is the guardrail ----------

def test_role_allowlists_bound_reach():
    all_tools = _all_tools()
    for role in ROLES.values():
        assert role.tools <= set(all_tools), f"{role.name} names tools that don't exist"
        assert set(subset_tools(all_tools, role)) == role.tools
        assert not (BLOCKED_EVERYWHERE & role.tools), \
            f"{role.name} must not reach {BLOCKED_EVERYWHERE & role.tools}"
    assert ROLES["policy"].tools == {"search_policy"}
    assert ROLES["catalog"].tools.isdisjoint({"add_to_cart", "get_cart", "prepare_checkout"})
    assert ROLES["cart"].tools >= ROLES["catalog"].tools
    # budgets tighten with reach: policy < catalog < cart
    assert ROLES["policy"].max_steps < ROLES["catalog"].max_steps < ROLES["cart"].max_steps


def test_catalog_role_cannot_touch_cart():
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="add_to_cart", arguments={"product_id": "P01", "quantity": 1})]),
        LLMMessage(content="done", tool_calls=[]),
    ]
    agent, tools = _agent(script, ROLES["catalog"])
    res = agent.run("add it", {"cart": Cart(), "checkout": None})
    assert "unknown tool: add_to_cart" in str(res.trace)
    assert "add_to_cart" not in tools


def test_cart_role_still_cannot_confirm_or_place():
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="place_order", arguments={"idempotency_key": "k1"})]),
        LLMMessage(content="done", tool_calls=[]),
    ]
    agent, tools = _agent(script, ROLES["cart"])
    res = agent.run("place it", {"cart": Cart(), "checkout": None})
    assert "unknown tool: place_order" in str(res.trace)
    assert BLOCKED_EVERYWHERE.isdisjoint(tools)


def test_policy_role_answers_only_from_rules():
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="search_policy", arguments={"query": "shipping"})]),
        LLMMessage(content="POL-SHIPPING applies.", tool_calls=[]),
    ]
    agent, tools = _agent(script, ROLES["policy"])
    res = agent.run("how much is shipping?", {"cart": Cart(), "checkout": None})
    assert res.status == "ok"
    assert "POL-SHIPPING" in res.text
    assert set(tools) == {"search_policy"}


# ---------- the API routes through the router ----------

def test_chat_api_reports_and_honors_role(tmp_path):
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="search_policy", arguments={"query": "return policy"})]),
        LLMMessage(content="POL-RETURN covers that.", tool_calls=[]),
    ]
    app = create_app(Settings(db_path=str(tmp_path / "t.db")), llm=FakeLLM(script))
    c = TestClient(app)
    body = c.post("/chat", json={"message": "what is your return policy?"}).json()
    assert body["role"] == "policy"
    assert "POL-RETURN" in body["reply"]
