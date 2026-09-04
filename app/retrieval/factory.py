"""Retrieval variant factory.

build_search_index returns any index honoring the frozen
search(query, top_k, filters) interface. Variants: bm25 | semantic | hybrid.
Callers (API, evals, demos) switch retrieval strategy here and nowhere else.
"""
from app.models import Product
from app.retrieval.bm25 import ProductIndex
from app.retrieval.embedder import Embedder, SentenceTransformerEmbedder
from app.retrieval.hybrid import HybridIndex
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.semantic import SemanticIndex

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
VARIANTS = ("bm25", "semantic", "hybrid")


def build_search_index(
    products: list[Product],
    variant: str = "bm25",
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    rerank_model: str = DEFAULT_RERANK_MODEL,
    rerank_enabled: bool = False,
    hybrid_rrf_k: int = 60,
    rerank_top_n: int = 20,
    embedder: Embedder | None = None,
):
    """Construct a retrieval index for the requested variant.

    embedder/reranker defaults are lazy: sentence-transformers models load on
    first use, so tests can inject stubs and offline runs degrade cleanly.
    """
    if variant not in VARIANTS:
        raise ValueError(
            f"unknown retrieval variant {variant!r}; choose from {list(VARIANTS)}"
        )
    if not isinstance(hybrid_rrf_k, int) or hybrid_rrf_k < 0:
        raise ValueError("hybrid_rrf_k must be a non-negative int")
    if not isinstance(rerank_top_n, int) or rerank_top_n < 0:
        raise ValueError("rerank_top_n must be a non-negative int")
    if variant == "bm25":
        return ProductIndex(products)
    resolved = embedder or SentenceTransformerEmbedder(embedding_model)
    if variant == "semantic":
        return SemanticIndex(products, resolved)
    reranker = (
        CrossEncoderReranker(rerank_model) if rerank_enabled else None
    )
    return HybridIndex(
        products,
        embedder=resolved,
        rrf_k=hybrid_rrf_k,
        reranker=reranker,
        rerank_top_n=rerank_top_n,
    )
