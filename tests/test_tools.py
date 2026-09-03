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
        "prepare_checkout",
        "confirm_checkout",
        "place_order",
    ]:
        assert name in tools
        assert tools[name].schema["name"] == name
        assert "properties" in tools[name].schema


def test_search_get_compare_flow():
    tools = _tools()
    hits = tools["search_products"].run(
        {"query": "wireless headphones", "top_k": 2}, {}
    )
    assert hits["products"][0]["product_id"] == "P01"
    detail = tools["get_product"].run({"product_id": "P01"}, {})
    assert detail["price"] == 8499.0
    table = tools["compare_products"].run({"product_ids": ["P01", "P02"]}, {})
    assert table["rows"]["price"] == {"P01": 8499.0, "P02": 12999.0}


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
