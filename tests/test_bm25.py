from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products


def _index() -> ProductIndex:
    return ProductIndex(load_products("data/products.json"))


def test_search_returns_relevant_headphone_first():
    results = _index().search("wireless headphones long battery life", top_k=3)
    assert results[0].product.product_id == "P01"
    assert results[0].score > 0


def test_max_price_filter_excludes_expensive():
    results = _index().search(
        "wireless headphones", top_k=10, filters={"max_price": 10000}
    )
    ids = [r.product.product_id for r in results]
    assert "P01" in ids
    assert "P02" not in ids


def test_category_and_availability_filters():
    results = _index().search(
        "headphones",
        top_k=10,
        filters={"category": "wireless headphones", "in_stock": True},
    )
    ids = [r.product.product_id for r in results]
    assert "P01" in ids
    assert "P06" not in ids


def test_top_k_is_honored_and_empty_query_returns_nothing():
    assert len(_index().search("speaker", top_k=1)) == 1
    assert _index().search("   ", top_k=5) == []
