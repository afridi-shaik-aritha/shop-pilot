import pytest

from app.state.models import (
    Cart,
    CartItem,
    Checkout,
    ConfirmationStatus,
    Order,
    ShoppingSession,
)
from app.state.store import FileSessionStore


def test_cart_item_and_subtotal():
    cart = Cart(items=[CartItem(product_id="P01", quantity=2, unit_price=8499.0)])
    assert cart.subtotal() == 16998.0


def test_confirmation_status_values():
    assert ConfirmationStatus.AWAITING_CONFIRMATION.value == "AWAITING_CONFIRMATION"
    assert ConfirmationStatus.CONFIRMED.value == "CONFIRMED"


def test_checkout_and_order_models():
    cart = Cart(items=[CartItem(product_id="P01", quantity=1, unit_price=8499.0)])
    co = Checkout(
        checkout_id="C-abc",
        cart_snapshot=cart,
        status=ConfirmationStatus.AWAITING_CONFIRMATION,
        confirmation_token="tok123",
        total=8499.0,
    )
    assert co.status == ConfirmationStatus.AWAITING_CONFIRMATION
    order = Order(
        order_id="O-xyz",
        checkout_id="C-abc",
        items=[CartItem(product_id="P01", quantity=1, unit_price=8499.0)],
        total=8499.0,
        status="COMPLETED",
        idempotency_key="k1",
    )
    assert order.idempotency_key == "k1"


def test_store_round_trip(tmp_path):
    store = FileSessionStore(str(tmp_path))
    session = ShoppingSession(session_id="S-1", user_id="u1")
    session.cart.items.append(CartItem(product_id="P01", quantity=1, unit_price=8499.0))
    store.save(session)
    loaded = store.load("S-1")
    assert loaded.cart.items[0].product_id == "P01"
    assert loaded.user_id == "u1"


def test_store_load_missing_raises(tmp_path):
    store = FileSessionStore(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        store.load("S-nope")
