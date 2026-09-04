"""Shared filter application across retrieval variants.

Filter semantics (frozen since Plan 1, now shared so every variant agrees):
max_price: float (inclusive: price <= max_price keeps the product),
category: exact str, in_stock: bool (truthy).
"""
from app.models import Product


def apply_filters(products: list[Product], filters: dict | None) -> list[Product]:
    if not filters:
        return list(products)
    if not isinstance(filters, dict):
        raise ValueError("filters must be an object")
    out = []
    for p in products:
        if "max_price" in filters:
            try:
                limit = float(filters["max_price"])
            except (TypeError, ValueError):
                raise ValueError("max_price must be a number") from None
            if p.price > limit:
                continue
        if "category" in filters and p.category != filters["category"]:
            continue
        if filters.get("in_stock") and not (p.availability and p.stock > 0):
            continue
        out.append(p)
    return out
