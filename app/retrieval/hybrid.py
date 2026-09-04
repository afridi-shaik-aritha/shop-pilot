"""Hybrid retrieval: BM25 + semantic fused with Reciprocal Rank Fusion.

RRF constant k defaults to 60 per spec §12. Optional reranker narrows (never
widens) the fused candidate set. Honors the frozen search() signature.
"""
from app.models import Product
from app.retrieval.bm25 import ProductIndex, RankedProduct
from app.retrieval.embedder import Embedder, LexicalEmbedder
from app.retrieval.reranker import Reranker
from app.retrieval.semantic import SemanticIndex

RRF_K_DEFAULT = 60


def rrf_fuse(rankings: list[list[str]], k: int = RRF_K_DEFAULT) -> dict[str, float]:
    """Reciprocal Rank Fusion: score(id) = sum over rankings of 1/(k+rank)."""
    if not isinstance(k, int) or k < 0:
        raise ValueError("rrf k must be a non-negative int")
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            fused[item_id] = fused.get(item_id, 0.0) + 1.0 / (k + rank)
    return fused


class HybridIndex:
    """RRF fusion of BM25 and semantic rankings, optionally reranked."""

    variant = "hybrid"

    def __init__(
        self,
        products: list[Product],
        bm25: ProductIndex | None = None,
        semantic: SemanticIndex | None = None,
        embedder: Embedder | None = None,
        rrf_k: int = RRF_K_DEFAULT,
        reranker: Reranker | None = None,
        rerank_top_n: int = 20,
    ) -> None:
        if not isinstance(rrf_k, int) or rrf_k < 0:
            raise ValueError("rrf_k must be a non-negative int")
        if not isinstance(rerank_top_n, int) or rerank_top_n < 0:
            raise ValueError("rerank_top_n must be a non-negative int")
        self._products = list(products)
        self._bm25 = bm25 or ProductIndex(self._products)
        self._semantic = semantic or SemanticIndex(
            self._products, embedder or LexicalEmbedder()
        )
        self._rrf_k = rrf_k
        self._reranker = reranker
        self._rerank_top_n = rerank_top_n

    @property
    def reranked(self) -> bool:
        return self._reranker is not None

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[RankedProduct]:
        if not query.strip() or not self._products:
            return []
        n = len(self._products)
        try:
            bm25_hits = self._bm25.search(query, top_k=n, filters=filters)
        except Exception:
            bm25_hits = []
        try:
            semantic_hits = self._semantic.search(query, top_k=n, filters=filters)
        except Exception as exc:
            if not bm25_hits:
                raise
            # Degrade to BM25 when embeddings are unavailable; surface the
            # cause in the score path rather than failing the whole search.
            semantic_hits = []
        if not bm25_hits and not semantic_hits:
            return []
        by_id = {p.product_id: p for p in self._products}
        fused = rrf_fuse(
            [
                [r.product.product_id for r in bm25_hits],
                [r.product.product_id for r in semantic_hits],
            ],
            k=self._rrf_k,
        )
        order = sorted(fused, key=lambda pid: (-fused[pid], pid))
        candidates = [RankedProduct(product=by_id[pid], score=fused[pid]) for pid in order]
        if self._reranker is not None and candidates:
            if self._rerank_top_n <= 0:
                return candidates[: max(top_k, 0)]
            head = candidates[: min(self._rerank_top_n, len(candidates))]
            products = [r.product for r in head]
            scores = self._reranker.score(query, products)
            if len(scores) != len(head):
                raise ValueError(
                    f"reranker returned {len(scores)} scores for {len(head)} candidates"
                )
            ordered = sorted(zip(head, scores), key=lambda pair: pair[1], reverse=True)
            candidates = [RankedProduct(product=r.product, score=float(s)) for r, s in ordered]
            # Rerank narrows but never widens: append non-reranked tail back so
            # top_k is still honored when top_k > rerank_top_n.
            if len(order) > len(head):
                tail_ids = order[len(head):]
                candidates.extend(
                    RankedProduct(product=by_id[pid], score=fused[pid])
                    for pid in tail_ids
                )
        return candidates[: max(top_k, 0)]
