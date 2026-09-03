from app.retrieval.corpus import (
    load_products,
    load_reviews,
    normalize_text,
    product_to_document,
)


def test_normalize_text():
    assert normalize_text("  Wireless HEADPHONES!! ") == ["wireless", "headphones"]


def test_load_products():
    products = load_products("data/products.json")
    assert len(products) == 6
    by_id = {p.product_id: p for p in products}
    assert by_id["P01"].price == 8499.0
    assert by_id["P01"].availability is True


def test_product_to_document_contains_searchable_terms():
    products = load_products("data/products.json")
    doc = product_to_document(products[0])
    for term in ["sonicwave", "wireless", "headphones", "battery"]:
        assert term in doc


def test_load_reviews():
    reviews = load_reviews("data/reviews.json")
    assert len(reviews) == 4
    assert {r.product_id for r in reviews} <= {"P01", "P02", "P04"}
