import pytest

from app.cart.service import CartService
from app.catalog.service import ProductService
from app.checkout.service import (
    CheckoutService,
    ConfirmationError,
    OrderService,
    StaleCheckoutError,
)
from app.retrieval.corpus import load_products
from app.state.models import Cart, ConfirmationStatus


def _wired():
    products = ProductService(load_products("data/products.json"))
    carts = CartService(products)
    checkout = CheckoutService(carts)
    orders = OrderService(products)
    return products, carts, checkout, orders


def _confirmed_p01():
    _, carts, checkout, _ = _wired()
    cart = Cart()
    carts.add_to_cart(cart, "P01", 1)
    co = checkout.prepare(cart)
    co = checkout.request_confirmation(co)
    return checkout.confirm(co, co.confirmation_token)


def test_prepare_and_confirm_flow():
    _, _, checkout, _ = _wired()
    co = checkout.prepare(Cart())
    assert co.status == ConfirmationStatus.CHECKOUT_PREPARED
    assert co.confirmation_token == ""
    co = checkout.request_confirmation(co)
    assert co.status == ConfirmationStatus.AWAITING_CONFIRMATION
    assert len(co.confirmation_token) == 16
    co = checkout.confirm(co, co.confirmation_token)
    assert co.status == ConfirmationStatus.CONFIRMED
    with pytest.raises(ConfirmationError):
        checkout.confirm(co, co.confirmation_token)


def test_confirm_wrong_token_and_cancel():
    _, _, checkout, _ = _wired()
    co = checkout.request_confirmation(checkout.prepare(Cart()))
    with pytest.raises(ConfirmationError):
        checkout.confirm(co, "deadbeefdeadbeef")
    co = checkout.cancel(co)
    assert co.status == ConfirmationStatus.REJECTED


def test_token_bound_to_snapshot():
    _, carts, checkout, _ = _wired()
    cart = Cart()
    carts.add_to_cart(cart, "P01", 1)
    co = checkout.request_confirmation(checkout.prepare(cart))
    carts.add_to_cart(cart, "P03", 1)
    co2 = checkout.request_confirmation(checkout.prepare(cart))
    assert co2.confirmation_token != co.confirmation_token


def test_place_order_requires_confirmation():
    _, _, checkout, orders = _wired()
    co = checkout.request_confirmation(checkout.prepare(Cart()))
    with pytest.raises(ConfirmationError):
        orders.place_order(co, "key-1", load_products("data/products.json"))


def test_place_order_happy_path_and_idempotent():
    _, _, _, orders = _wired()
    co = _confirmed_p01()
    catalog = load_products("data/products.json")
    o1 = orders.place_order(co, "key-1", catalog)
    assert o1.order_id.startswith("O-")
    assert o1.status == "COMPLETED"
    o2 = orders.place_order(co, "key-1", catalog)
    assert o2.order_id == o1.order_id
    assert co.status == ConfirmationStatus.COMPLETED


def test_place_order_detects_stale_price():
    _, _, _, orders = _wired()
    co = _confirmed_p01()
    catalog = load_products("data/products.json")
    for p in catalog:
        if p.product_id == "P01":
            p.price = 99999.0
    with pytest.raises(StaleCheckoutError):
        orders.place_order(co, "key-stale", catalog)


def test_place_order_detects_unavailable():
    _, _, _, orders = _wired()
    co = _confirmed_p01()
    catalog = load_products("data/products.json")
    for p in catalog:
        if p.product_id == "P01":
            p.availability = False
            p.stock = 0
    with pytest.raises(StaleCheckoutError):
        orders.place_order(co, "key-oos", catalog)
