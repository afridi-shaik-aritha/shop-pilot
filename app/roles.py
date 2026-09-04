"""Agent roles: reach-bounded specialists over one ReAct engine.

Every message is routed to exactly one role. The role's *tool allowlist* is
a cost-control / blast-radius guardrail for LLM-driven calls only — it is
NOT an authentication boundary: direct HTTP calls to /cart, /checkout/* and
/orders bypass routing entirely and are enforced by the service layer
(confirmation gate, revalidation, session-scoped idempotency).
No role can confirm or place an order (those stay behind the human slip/API).
Prompts only tell the model which behaviours the role expects.
"""
from dataclasses import dataclass

from app.prompts import CART_SYSTEM, CATALOG_SYSTEM, POLICY_SYSTEM

CATALOG_TOOLS = frozenset(
    {"search_products", "get_product", "search_reviews", "compare_products"}
)
CART_TOOLS = CATALOG_TOOLS | frozenset(
    {"add_to_cart", "remove_from_cart", "update_cart_quantity", "get_cart",
     "clear_cart", "prepare_checkout"}
)
POLICY_TOOLS = frozenset({"search_policy"})


@dataclass(frozen=True)
class AgentRole:
    name: str
    description: str
    tools: frozenset
    prompt: str
    max_steps: int
    max_tool_calls: int


ROLES: dict[str, AgentRole] = {
    "policy": AgentRole(
        name="policy",
        description="Read-only policy advisor; answers from the policy corpus only.",
        tools=POLICY_TOOLS,
        prompt=POLICY_SYSTEM,
        max_steps=6,
        max_tool_calls=8,
    ),
    "catalog": AgentRole(
        name="catalog",
        description="Read-only catalog specialist: search, compare, reviews.",
        tools=CATALOG_TOOLS,
        prompt=CATALOG_SYSTEM,
        max_steps=8,
        max_tool_calls=12,
    ),
    "cart": AgentRole(
        name="cart",
        description="Shopping specialist: catalog reads plus cart management and checkout preparation.",
        tools=CART_TOOLS,
        prompt=CART_SYSTEM,
        max_steps=12,
        max_tool_calls=20,
    ),
}

# Order matters: policy markers beat cart markers, explicit read-only phrasing
# beats the buying default, and everything else lands on catalog.
_POLICY_MARKERS = (
    "shipping", "delivery", "deliver", "return", "refund", "policy",
    "policies", "warranty", "gst", "tax", "taxes", "charges", "fee", "fees",
    "cancell", "payment", "payments", "pay for", "money",
)
_CATALOG_MARKERS = (
    "compare", "comparison", "versus", " vs ", "spec", "specification",
    "describe", "tell me about", "difference", "details", "list all",
    "show me", "what about", "is it good", "how is", "review of", "rating",
    "smartwatch", "headphone", "earphone", "speaker", "available", "in stock",
    "price of", "product",
)
_CART_MARKERS = (
    "cart", "trolley", "add", "remove", "quantity", "prepare checkout",
    "checkout", "buy", "purchase", "order", "need", "want", "looking for",
    "find", "put it", "take it", "that one",
)


def classify(message: str) -> AgentRole:
    """Pick the role for a user message. Deterministic, no LLM call."""
    lower = f" {str(message or '').lower()} "
    if any(m in lower for m in _POLICY_MARKERS):
        return ROLES["policy"]
    buying = any(m in lower for m in _CART_MARKERS)
    if not buying and any(m in lower for m in _CATALOG_MARKERS):
        return ROLES["catalog"]
    if buying:
        return ROLES["cart"]
    return ROLES["catalog"]


def subset_tools(all_tools: dict, role: AgentRole) -> dict:
    """Narrow the full registry to what the role may call."""
    return {name: all_tools[name] for name in role.tools if name in all_tools}
