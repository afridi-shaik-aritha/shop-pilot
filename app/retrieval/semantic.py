"""Semantic retrieval. Products are embedded once at construction; queries
are embedded per call and ranked by cosine similarity."""
from app.models import Product
from app.retrieval.bm25 import RankedProduct
from app.retrieval.corpus import product_to_document
from app.retrieval.embedder import Embedder, _l2_normalize
from app.retrieval.filters import apply_filters


def _dot(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"embedding dimension mismatch: {len(a)} vs {len(b)}")
    return sum(x * y for x, y in zip(a, b))


class SemanticIndex:
    """Embedding similarity over the product catalog. Honors the frozen
    search(query, top_k, filters) signature of ProductIndex."""

    variant = "semantic"

    def __init__(self, products: list[Product], embedder: Embedder) -> None:
        self._products = list(products)
        self._by_id = {p.product_id: i for i, p in enumerate(self._products)}
        self._embedder = embedder
        self._vectors: list[list[float]] = []
        if self._products:
            docs = [product_to_document(p) for p in self._products]
            self._vectors = [_l2_normalize(v) for v in embedder.encode(docs)]

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[RankedProduct]:
        if not query.strip() or not self._products:
            return []
        candidates = apply_filters(self._products, filters)
        if not candidates:
            return []
        qvec = _l2_normalize(self._embedder.encode([query])[0])
        ranked = sorted(
            (
                RankedProduct(
                    product=p, score=_dot(qvec, self._vectors[self._by_id[p.product_id]])
                )
                for p in candidates
            ),
            key=lambda r: r.score,
            reverse=True,
        )
        return ranked[: max(top_k, 0)]
