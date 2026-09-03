"""BM25 baseline retrieval. Index is built once and reused for every query."""
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.models import Product
from app.retrieval.corpus import normalize_text, product_to_document


@dataclass(frozen=True)
class RankedProduct:
    product: Product
    score: float


class ProductIndex:
    """Keyword retrieval over the product catalog.

    Filters (all optional): max_price (float), category (exact str),
    in_stock (bool, True keeps availability=True and stock>0).
    """

    def __init__(self, products: list[Product]) -> None:
        self._products = list(products)
        tokenized = [normalize_text(product_to_document(p)) for p in self._products]
        self._bm25 = BM25Okapi(tokenized)

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[RankedProduct]:
        tokens = normalize_text(query)
        if not tokens:
            return []
        candidates = self._apply_filters(filters)
        if not candidates:
            return []
        idx = [self._products.index(p) for p in candidates]
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            (RankedProduct(product=p, score=float(scores[i])) for p, i in zip(candidates, idx)),
            key=lambda r: r.score,
            reverse=True,
        )
        return ranked[: max(top_k, 0)]

    def _apply_filters(self, filters: dict | None) -> list[Product]:
        if not filters:
            return list(self._products)
        out = []
        for p in self._products:
            if "max_price" in filters and p.price > float(filters["max_price"]):
                continue
            if "category" in filters and p.category != filters["category"]:
                continue
            if filters.get("in_stock") and not (p.availability and p.stock > 0):
                continue
            out.append(p)
        return out
