# tests/test_sqlite.py
import os

import pytest

from app.cart.service import CartService
from app.catalog.service import ProductService
from app.checkout.service import CheckoutService, DictOrderStore, OrderService, SqliteOrderStore
from app.retrieval.corpus import load_products
from app.state.models import Cart, CartItem, Order, ShoppingSession
from app.state.sqlite_store import SqliteStore


def _db(tmp_path):
    return SqliteStore(str(tmp_path / "t.db"))


def _confirmed_p01(checkout, carts):
    cart = Cart()
    carts.add_to_cart(cart, "P01", 1)
    co = checkout.prepare(cart)
    co = checkout.request_confirmation(co)
    return checkout.confirm(co, co.confirmation_token)


def test_session_round_trip(tmp_path):
    db = _db(tmp_path)
    assert os.path.exists(str(tmp_path / "t.db"))
    session = ShoppingSession(session_id="S-9", user_id="u9")
    session.cart.items.append(CartItem(product_id="P04", quantity=2, unit_price=5999.0))
    db.save(session)
    loaded = db.load("S-9")
    assert loaded.cart.items[0].quantity == 2
    assert loaded.user_id == "u9"
    db.close()


def test_session_missing_raises(tmp_path):
    db = _db(tmp_path)
    with pytest.raises(FileNotFoundError):
        db.load("S-nope")
    db.close()


def test_key_claim_round_trip(tmp_path):
    db = _db(tmp_path)
    assert db.get_order_id("k-1") is None
    db.put_key("k-1", "O-aaa")
    assert db.get_order_id("k-1") == "O-aaa"
    db.close()


def test_order_save_and_lookup(tmp_path):
    db = _db(tmp_path)
    order = Order(order_id="O-1", checkout_id="C-1",
                  items=[CartItem(product_id="P01", quantity=1, unit_price=8499.0)],
                  total=10028.82, status="COMPLETED", idempotency_key="k-1")
    db.save_order(order)
    assert db.get_order("O-1").total == 10028.82
    assert db.get_order_by_key("k-1").order_id == "O-1"
    with pytest.raises(KeyError):
        db.get_order("O-nope")
    db.close()


def test_traces_filter(tmp_path):
    db = _db(tmp_path)
    db.save_trace("r1", "chat", {"a": 1})
    db.save_trace("r2", "order", {"b": 2})
    assert [t["run_id"] for t in db.list_traces()] == ["r2", "r1"]
    assert [t["run_id"] for t in db.list_traces(kind="order")] == ["r2"]
    assert db.list_traces(limit=1)[0]["run_id"] == ["r2"][0]
    db.close()


def test_durable_idempotency_across_instances(tmp_path):
    products = ProductService(load_products("data/products.json"))
    carts = CartService(products)
    checkout = CheckoutService(carts)
    db = _db(tmp_path)
    store = SqliteOrderStore(db)
    co = _confirmed_p01(checkout, carts)
    catalog = load_products("data/products.json")
    o1 = OrderService(products, store=store).place_order(co, "k-durable", catalog)
    o2 = OrderService(products, store=store).place_order(co, "k-durable", catalog)
    assert o1.order_id == o2.order_id
    db.close()
    db2 = _db(tmp_path)
    store2 = SqliteOrderStore(db2)
    o3 = OrderService(products, store=store2).place_order(co, "k-durable", catalog)
    assert o3.order_id == o1.order_id
    db2.close()
