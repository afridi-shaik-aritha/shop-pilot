"""Dataset loading and text normalization. Index is built once (see bm25.py), not per query."""
import json
import re

from app.models import Product, Review

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_text(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _fold_plural(token: str) -> str:
    """Crude English singular: 'laptops' -> 'laptop', 'watches' -> 'watch',
    'batteries' -> 'battery'. Applied to documents and queries alike, so an
    imperfect fold (e.g. 'series' -> 'sery') still matches itself."""
    if len(token) <= 3 or token.isdigit():
        return token
    if token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith(("ches", "shes", "sses", "xes", "zes")):
        return token[:-2]
    if token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def search_tokens(text: str) -> list[str]:
    """Tokens for product retrieval: normalized, then plural-folded so a
    shopper's 'smartwatches' matches a catalog 'smartwatch'."""
    return [_fold_plural(t) for t in normalize_text(text)]


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
