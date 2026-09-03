from evaluation.metrics import constraint_match, precision_at_k, recall_at_k, reciprocal_rank


def test_recall_and_precision_at_k():
    assert recall_at_k(["P01", "P04"], ["P01", "P02"]) == 0.5
    assert precision_at_k(["P01", "P04"], ["P01", "P02"]) == 0.5
    assert recall_at_k(["P09"], ["P01"]) == 0.0
    assert recall_at_k([], []) == 1.0


def test_reciprocal_rank():
    assert reciprocal_rank(["P04"], ["P01", "P04", "P02"]) == 0.5
    assert reciprocal_rank(["P09"], ["P01", "P02"]) == 0.0


def test_constraint_match():
    from app.retrieval.corpus import load_products

    by_id = {p.product_id: p for p in load_products("data/products.json")}
    assert constraint_match(by_id["P01"], {"max_price": 10000}) is True
    assert constraint_match(by_id["P02"], {"max_price": 10000}) is False
    assert constraint_match(by_id["P01"], {"category": "wireless headphones"}) is True
