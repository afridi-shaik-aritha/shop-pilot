import pytest

from app.catalog.service import ProductNotFound, ProductService, ReviewService
from app.retrieval.corpus import load_products, load_reviews


def _products():
    return load_products("data/products.json")


def _reviews():
    return load_reviews("data/reviews.json")


def test_get_product():
    svc = ProductService(_products())
    assert svc.get_product("P01").name.startswith("SonicWave")
    with pytest.raises(ProductNotFound):
        svc.get_product("PZZ")


def test_compare_products_grounded():
    svc = ProductService(_products())
    table = svc.compare_products(["P01", "P02"])
    assert table["products"] == ["P01", "P02"]
    prices = table["rows"]["price"]
    assert prices == {"P01": 8499.0, "P02": 12999.0}
    assert table["rows"]["rating"] == {"P01": 4.4, "P02": 4.6}


def test_compare_unknown_raises():
    svc = ProductService(_products())
    with pytest.raises(ProductNotFound):
        svc.compare_products(["P01", "PZZ"])


def test_search_reviews_returns_evidence():
    svc = ReviewService(_reviews())
    res = svc.search_reviews("P01", query="battery", top_k=2)
    assert res[0]["review_id"] == "R01"
    assert res[0]["kind"] == "review-quote"
    assert "product_id" in res[0] and res[0]["product_id"] == "P01"


def test_search_reviews_unknown_product_empty():
    svc = ReviewService(_reviews())
    assert svc.search_reviews("PZZ") == []
