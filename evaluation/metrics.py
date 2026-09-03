"""Lexical retrieval metrics. LLM-judged contextual relevancy/recall/precision land in Plan 3."""
from app.models import Product


def recall_at_k(expected_ids: list[str], retrieved_ids: list[str]) -> float:
    if not expected_ids:
        return 1.0
    hit = len(set(expected_ids) & set(retrieved_ids))
    return hit / len(expected_ids)


def precision_at_k(expected_ids: list[str], retrieved_ids: list[str]) -> float:
    if not retrieved_ids:
        return 0.0
    hit = len(set(expected_ids) & set(retrieved_ids))
    return hit / len(retrieved_ids)


def reciprocal_rank(expected_ids: list[str], retrieved_ids: list[str]) -> float:
    for rank, pid in enumerate(retrieved_ids, start=1):
        if pid in set(expected_ids):
            return 1.0 / rank
    return 0.0


def constraint_match(product: Product, constraints: dict) -> bool:
    if "max_price" in constraints and product.price > float(constraints["max_price"]):
        return False
    if "category" in constraints and product.category != constraints["category"]:
        return False
    return True
