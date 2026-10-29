from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products


def _index() -> ProductIndex:
    return ProductIndex(load_products("data/products.json"))


def test_search_returns_relevant_headphone_first():
    results = _index().search("wireless headphones long battery life", top_k=3)
    assert results[0].product.product_id == "P01"
    assert results[0].score > 0


def test_plural_and_singular_queries_find_the_same_products():
    """Regression: 'laptops' matched no catalog word (the docs say 'laptop'),
    and the zero-score rows returned anyway were headphones and speakers,
    which a live model then presented as laptops."""
    plural = [r.product.product_id for r in _index().search("laptops", top_k=5)]
    singular = [r.product.product_id for r in _index().search("laptop", top_k=5)]
    assert plural == singular
    assert "P22" in plural  # CompuPro Budget 14 Laptop
    watches = _index().search("smartwatches", top_k=5)
    assert watches and all(r.product.category == "smartwatch" for r in watches)


def test_query_with_no_matching_word_returns_nothing():
    """No query word in any product means an empty list, filters or not,
    so the model can say nothing matched instead of mislabelling rows."""
    assert _index().search("drones", top_k=5) == []
    assert _index().search("drones", top_k=5, filters={"max_price": 30000}) == []


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
