"""BM25 baseline retrieval. Index is built once and reused for every query."""
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.models import Product
from app.retrieval.corpus import normalize_text, product_to_document
from app.retrieval.filters import apply_filters


@dataclass(frozen=True)
class RankedProduct:
    product: Product
    score: float


class ProductIndex:
    """Keyword retrieval over the product catalog.

    Filters (all optional): max_price (float), category (exact str),
    in_stock (bool, True keeps availability=True and stock>0).
    """

    variant = "bm25"

    def __init__(self, products: list[Product]) -> None:
        self._products = list(products)
        self._pos = {id(p): i for i, p in enumerate(self._products)}
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
        candidates = apply_filters(self._products, filters)
        if not candidates:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            (RankedProduct(product=p, score=float(scores[self._pos[id(p)]])) for p in candidates),
            key=lambda r: r.score,
            reverse=True,
        )
        return ranked[: max(top_k, 0)]
