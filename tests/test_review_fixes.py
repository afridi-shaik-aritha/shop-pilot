# Regression tests for the review fixes (security + correctness).
from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.cart.service import CartService
from app.catalog.service import ProductService
from app.checkout.service import CheckoutService, ConfirmationError, OrderService
from app.config import Settings
from app.retrieval.corpus import load_products
from app.state.models import Cart
from evaluation.grounding import numbers_in
from evaluation.llm_judge_eval import _parse_verdict


def _wired():
    products = ProductService(load_products("data/products.json"))
    carts = CartService(products)
    checkout = CheckoutService(carts)
    orders = OrderService(products)
    return products, carts, checkout, orders


def test_confirmation_tokens_are_random_not_forgeable():
    _, carts, checkout, _ = _wired()
    c1, c2 = Cart(), Cart()
    carts.add_to_cart(c1, "P01", 1)
    carts.add_to_cart(c2, "P01", 1)
    t1 = checkout.request_confirmation(checkout.prepare(c1)).confirmation_token
    t2 = checkout.request_confirmation(checkout.prepare(c2)).confirmation_token
    assert len(t1) >= 16 and len(t2) >= 16
    assert t1 != t2


def test_prepare_empty_cart_rejected():
    _, _, checkout, _ = _wired()
    try:
        checkout.prepare(Cart())
        assert False, "empty prepare must raise"
    except ConfirmationError:
        pass


def test_cancel_after_complete_rejected():
    _, carts, checkout, orders = _wired()
    cart = Cart()
    carts.add_to_cart(cart, "P01", 1)
    co = checkout.request_confirmation(checkout.prepare(cart))
    co = checkout.confirm(co, co.confirmation_token)
    orders.place_order(co, "k-cancel-guard", load_products("data/products.json"))
    try:
        checkout.cancel(co)
        assert False, "cancel after COMPLETED must raise"
    except ConfirmationError:
        pass


def test_idempotency_scoped_per_session_api(tmp_path):
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db"))))
    s1 = c.post("/sessions").json()["session_id"]
    s2 = c.post("/sessions").json()["session_id"]
    c.post("/cart/items", json={"session_id": s1, "product_id": "P01", "quantity": 1})
    p1 = c.post("/checkout/prepare", json={"session_id": s1}).json()
    c.post("/checkout/confirm", json={"session_id": s1, "confirmation_token": p1["confirmation_token"]})
    o1 = c.post("/orders", json={"session_id": s1, "idempotency_key": "same-key"}).json()
    c.post("/cart/items", json={"session_id": s2, "product_id": "P01", "quantity": 1})
    p2 = c.post("/checkout/prepare", json={"session_id": s2}).json()
    c.post("/checkout/confirm", json={"session_id": s2, "confirmation_token": p2["confirmation_token"]})
    o2 = c.post("/orders", json={"session_id": s2, "idempotency_key": "same-key"}).json()
    assert o1["order_id"] != o2["order_id"]


def test_cart_add_returns_top_level_items_with_names(tmp_path):
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db"))))
    sid = c.post("/sessions").json()["session_id"]
    body = c.post("/cart/items", json={"session_id": sid, "product_id": "P01", "quantity": 1}).json()
    assert body["items"] and body["items"][0]["name"] == "SonicWave X5 Wireless Headphones"


def test_search_returns_card_fields(tmp_path):
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db"))))
    prods = c.post("/search", json={"query": "headphones", "top_k": 2}).json()["products"]
    for p in prods:
        for field in ("category", "brand", "availability", "stock", "review_count"):
            assert field in p, f"missing {field}"


def test_judge_coerces_string_false():
    assert _parse_verdict('{"faithful": "false", "score": 1}')['faithful'] is False
    assert _parse_verdict('{"faithful": true, "score": 5}')['faithful'] is True


def test_grounding_ignores_stray_digits():
    assert numbers_in("SonicWave X5 (P01) costs 8499.0 rating 4.4") == ["8499.0", "4.4"]
