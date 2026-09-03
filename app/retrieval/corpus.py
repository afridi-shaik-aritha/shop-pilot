"""Dataset loading and text normalization. Index is built once (see bm25.py), not per query."""
import json
import re

from app.models import Product, Review

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_text(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def load_products(path: str) -> list[Product]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [Product(**item) for item in raw]


def load_reviews(path: str) -> list[Review]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [Review(**item) for item in raw]


def product_to_document(product: Product) -> str:
    spec_text = " ".join(f"{k} {v}" for k, v in product.specs.items())
    return " ".join(
        [product.name, product.brand, product.category, product.description, spec_text]
    ).lower()
