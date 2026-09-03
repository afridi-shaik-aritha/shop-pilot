import pytest

from app.cart.service import CartError, CartService
from app.catalog.service import ProductService
from app.retrieval.corpus import load_products
from app.state.models import Cart


def _svc() -> CartService:
    return CartService(ProductService(load_products("data/products.json")))


def test_add_and_totals_free_shipping():
    svc = _svc()
    cart = Cart()
    svc.add_to_cart(cart, "P01", 1)
    totals = svc.totals(cart)
    assert totals["subtotal"] == 8499.0
    assert totals["shipping"] == 0.0
    assert totals["tax"] == round(8499.0 * 0.18, 2)
    assert totals["total"] == round(8499.0 * 1.18, 2)


def test_add_merges_quantity_and_validates():
    svc = _svc()
    cart = Cart()
    svc.add_to_cart(cart, "P03", 1)
    svc.add_to_cart(cart, "P03", 2)
    assert cart.items[0].quantity == 3
    with pytest.raises(CartError):
        svc.add_to_cart(cart, "P03", 0)
    with pytest.raises(CartError):
        svc.add_to_cart(cart, "PZZ", 1)


def test_small_cart_pays_shipping():
    svc = _svc()
    cart = Cart()
    svc.add_to_cart(cart, "P03", 1)
    totals = svc.totals(cart)
    assert totals["shipping"] == 49.0
    assert totals["total"] == round((999.0 + 49.0) * 1.18, 2)


def test_remove_update_clear():
    svc = _svc()
    cart = Cart()
    svc.add_to_cart(cart, "P01", 1)
    svc.update_quantity(cart, "P01", 2)
    assert cart.items[0].quantity == 2
    svc.update_quantity(cart, "P01", 0)
    assert cart.items == []
    svc.add_to_cart(cart, "P04", 1)
    svc.remove_from_cart(cart, "P04")
    assert cart.items == []
    with pytest.raises(CartError):
        svc.remove_from_cart(cart, "P04")
    svc.add_to_cart(cart, "P04", 1)
    svc.clear_cart(cart)
    assert cart.items == []
