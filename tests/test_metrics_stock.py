# tests/test_metrics_stock.py
from evaluation.metrics import constraint_match
from app.retrieval.corpus import load_products


def _by_id():
    return {p.product_id: p for p in load_products("data/products.json")}


def test_in_stock_constraint_matches_available():
    products = _by_id()
    assert constraint_match(products["P01"], {"in_stock": True}) is True


def test_in_stock_constraint_rejects_unavailable_and_zerostock():
    products = _by_id()
    assert constraint_match(products["P06"], {"in_stock": True}) is False


def test_in_stock_combines_with_other_constraints():
    products = _by_id()
    assert (
        constraint_match(
            products["P01"], {"category": "wireless headphones", "in_stock": True}
        )
        is True
    )
    assert (
        constraint_match(
            products["P01"], {"max_price": 5000, "in_stock": True}
        )
        is False
    )


def test_no_in_stock_key_behaves_as_before():
    products = _by_id()
    assert constraint_match(products["P06"], {"category": "wireless headphones"}) is True
