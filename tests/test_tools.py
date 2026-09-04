import pytest

from app.cart.service import CartService
from app.catalog.service import ProductService
from app.checkout.service import CheckoutService, OrderService
from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products, load_reviews
from app.state.models import Cart
from app.tools import build_tools


def _tools():
    products = load_products("data/products.json")
    catalog = ProductService(products)
    carts = CartService(catalog)
    return build_tools(
        index=ProductIndex(products),
        catalog=catalog,
        carts=carts,
        checkout=CheckoutService(carts),
        orders=OrderService(catalog),
        products_path="data/products.json",
    )


def test_tool_names_and_schemas():
    tools = _tools()
    for name in [
        "search_products",
        "get_product",
        "search_reviews",
        "compare_products",
        "add_to_cart",
        "remove_from_cart",
        "update_cart_quantity",
        "get_cart",
        "clear_cart",
        "prepare_checkout",
        "confirm_checkout",
        "place_order",
    ]:
        assert name in tools
        assert tools[name].schema["name"] == name
        assert "properties" in tools[name].schema


def test_product_refs_resolve_by_name_or_slug():
    """The transcript failure: the model invented 'sonicwave_x5' instead of
    copying P01 from search results. Id-based tools must resolve names and
    model-invented slugs so a guessed id can never brick the cart."""
    tools = _tools()
    # exact canonical id still works
    assert tools["get_product"].run({"product_id": "P01"}, {})["product_id"] == "P01"
    # name-only, exactly as the shopper said it — the second transcript turn,
    # where the model failed despite the user quoting the full name
    ctx = {}
    detail = tools["get_product"].run(
        {"product_name": "SonicWave X5 Wireless Headphones"}, {}
    )
    assert detail["product_id"] == "P01"
    out = tools["add_to_cart"].run(
        {"product_name": "SonicWave X5 Wireless Headphones"}, ctx
    )
    assert out["cart"]["items"][0]["product_id"] == "P01"
    # review search, compare, update, remove by name
    assert (
        tools["search_reviews"].run(
            {"product_name": "SonicWave X5 Wireless Headphones"}, {}
        )["reviews"]
    )
    tools["compare_products"].run(
        {"product_ids": ["SonicWave X5 Wireless Headphones", "P02"]}, {}
    )
    tools["update_cart_quantity"].run(
        {"product_name": "SonicWave X5 Wireless Headphones", "quantity": 2}, ctx
    )
    assert ctx["cart"].items[0].quantity == 2
    tools["remove_from_cart"].run({"product_name": "SonicWave X5 Wireless Headphones"}, ctx)
    assert ctx["cart"].items == []


def test_ambiguous_product_ref_lists_candidates():
    """A short slug that matches several products must name them with ids so
    the model can retry with the canonical one — never silently pick. This is
    the exact slug the live model sent instead of P01."""
    tools = _tools()
    with pytest.raises(ValueError) as exc:
        tools["add_to_cart"].run({"product_id": "sonicwave_x5"}, {})
    msg = str(exc.value)
    assert "P01" in msg and "P06" in msg


def test_product_ref_schemas_advertise_product_name():
    """Small models read the schema — product_name must be visible on every
    id-based tool, and product_id must not be forced when only the name is
    known."""
    tools = _tools()
    for name in ["get_product", "search_reviews", "add_to_cart", "remove_from_cart"]:
        props = tools[name].schema["properties"]
        assert "product_name" in props, name
        assert "product_id" not in tools[name].schema.get("required", []), name


def test_search_get_compare_flow():
    tools = _tools()
    hits = tools["search_products"].run(
        {"query": "wireless headphones long battery life", "top_k": 2}, {}
    )
    assert hits["products"][0]["product_id"] == "P01"
    # BM25 relevance is a ranking detail, never a fact: exposing it let a
    # live model quote it as a rating ("4.0/5 (5.71 score)").
    assert "score" not in hits["products"][0]
    detail = tools["get_product"].run({"product_id": "P01"}, {})
    assert detail["price"] == 8499.0
    table = tools["compare_products"].run({"product_ids": ["P01", "P02"]}, {})
    assert table["rows"]["price"] == {"P01": 8499.0, "P02": 12999.0}


def test_search_products_schema_documents_natural_language_filters():
    """The model must be able to tell that budget/battery/review asks are
    searchable — a bare opaque 'filters' object once led a live model to
    refuse instead of searching."""
    tools = _tools()
    t = tools["search_products"]
    props = t.schema["properties"]["filters"]["properties"]
    assert set(props) >= {"max_price", "category", "in_stock"}
    desc = t.description
    assert "max_price" in desc and "in_stock" in desc and "under 10000" in desc
    # price/budget queries are satisfied by the query string itself
    assert ("free-text" in desc or "free text" in desc
            or "shopper's own words" in desc)
    # feature/sensor asks are free-text too — a live model once refused
    # "smartwatch with heart-rate tracking" claiming it could not filter by
    # specs, and no id/model name is ever required to search.
    assert "heart rate tracking" in desc
    assert "no id or model name is needed" in desc


def test_cart_checkout_confirm_order_flow():
    from app.catalog.service import ReviewService  # noqa: F401 (import surface check)

    tools = _tools()
    ctx: dict = {}
    tools["add_to_cart"].run({"product_id": "P01", "quantity": 1}, ctx)
    cart = tools["get_cart"].run({}, ctx)
    assert cart["items"][0]["product_id"] == "P01"
    prep = tools["prepare_checkout"].run({}, ctx)
    assert prep["status"] == "AWAITING_CONFIRMATION"
    assert len(prep["confirmation_token"]) == 16
    with pytest.raises(Exception):
        tools["place_order"].run({"idempotency_key": "t-key"}, ctx)
    confirmed = tools["confirm_checkout"].run(
        {"confirmation_token": prep["confirmation_token"]}, ctx
    )
    assert confirmed["status"] == "CONFIRMED"
    order = tools["place_order"].run({"idempotency_key": "t-key"}, ctx)
    assert order["status"] == "COMPLETED"
    assert order["order_id"].startswith("O-")


def test_clear_cart_empties_every_line():
    tools = _tools()
    ctx: dict = {}
    tools["add_to_cart"].run({"product_id": "P01", "quantity": 2}, ctx)
    tools["add_to_cart"].run({"product_id": "P03", "quantity": 1}, ctx)
    assert len(tools["get_cart"].run({}, ctx)["items"]) == 2
    cleared = tools["clear_cart"].run({}, ctx)
    assert cleared["cart"]["items"] == []
    assert cleared["totals"]["total"] == 0.0


def test_cart_change_voids_awaiting_slip():
    """A slip belongs to the exact trolley it was cut for: mutating the cart
    drops it, so an old code can never confirm lines the shopper no longer sees."""
    tools = _tools()
    ctx: dict = {}
    tools["add_to_cart"].run({"product_id": "P01", "quantity": 1}, ctx)
    prep = tools["prepare_checkout"].run({}, ctx)
    assert ctx["checkout"] is not None
    # adding another product changes the trolley -> slip voided
    tools["add_to_cart"].run({"product_id": "P02", "quantity": 1}, ctx)
    assert ctx["checkout"] is None
    prep2 = tools["prepare_checkout"].run({}, ctx)
    # resizing a line also voids the standing slip
    tools["update_cart_quantity"].run({"product_id": "P02", "quantity": 3}, ctx)
    assert ctx["checkout"] is None
    prep3 = tools["prepare_checkout"].run({}, ctx)
    assert prep3["checkout_id"] not in (prep["checkout_id"], prep2["checkout_id"])
    # clearing the trolley drops the fresh slip too
    tools["clear_cart"].run({}, ctx)
    assert ctx["checkout"] is None


def test_repeated_prepare_keeps_standing_slip():
    tools = _tools()
    ctx: dict = {}
    tools["add_to_cart"].run({"product_id": "P01", "quantity": 1}, ctx)
    first = tools["prepare_checkout"].run({}, ctx)
    second = tools["prepare_checkout"].run({}, ctx)
    assert second["checkout_id"] == first["checkout_id"]
    assert second["confirmation_token"] == first["confirmation_token"]
    assert second["status"] == "AWAITING_CONFIRMATION"
    # a changed cart mints a fresh slip with a fresh code
    tools["add_to_cart"].run({"product_id": "P02", "quantity": 1}, ctx)
    third = tools["prepare_checkout"].run({}, ctx)
    assert third["checkout_id"] != first["checkout_id"]
    assert third["confirmation_token"] != first["confirmation_token"]
