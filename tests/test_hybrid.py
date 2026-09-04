# tests/test_hybrid.py
from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products
from app.retrieval.hybrid import HybridIndex, rrf_fuse
from app.retrieval.semantic import SemanticIndex


class StubEmbedder:
    def encode(self, texts):
        out = []
        for t in texts:
            low = t.lower()
            if "wireless headphones" in low or "battery" in low:
                out.append([1.0, 0.0, 0.0])
            elif "speaker" in low:
                out.append([0.0, 1.0, 0.0])
            elif "smartwatch" in low:
                out.append([0.0, 0.0, 1.0])
            else:
                out.append([0.0, 0.0, 0.0])
        return out


class ReverseReranker:
    """Scripted reranker: inverts whatever order it is given."""

    def score(self, query, products):
        return [float(i + 1) for i in range(len(products))]


def _products():
    return load_products("data/products.json")


def _hybrid(**kwargs):
    products = _products()
    bm25 = kwargs.pop("bm25", None) or ProductIndex(products)
    sem = kwargs.pop("semantic", None) or SemanticIndex(products, StubEmbedder())
    return HybridIndex(products, bm25=bm25, semantic=sem, **kwargs)


def _ids(results):
    return [r.product.product_id for r in results]


def test_rrf_fuse_arithmetic():
    fused = rrf_fuse([["a", "b"], ["c", "a", "b"]], k=10)
    assert fused["a"] == 1 / 11 + 1 / 12
    assert fused["b"] == 1 / 12 + 1 / 13
    assert abs(fused["a"] - 0.1742424242) < 1e-9
    order = sorted(fused, key=fused.get, reverse=True)
    assert order == ["a", "b", "c"]


def test_hybrid_fuses_and_returns_top_hit():
    index = _hybrid()
    results = index.search("wireless headphones battery", top_k=3)
    assert results[0].product.product_id == "P01"
    assert index.variant == "hybrid"
    assert len(_ids(results)) == len(set(_ids(results)))


def test_hybrid_honors_filters():
    ids = _ids(_hybrid().search("wireless headphones", top_k=10, filters={"max_price": 10000}))
    assert "P01" in ids
    assert "P02" not in ids


def test_hybrid_empty_query_and_top_k():
    assert _hybrid().search("   ") == []
    assert len(_ids(_hybrid().search("speaker", top_k=1))) == 1


def test_reranker_reorders_fused_results():
    plain = _hybrid()
    # window == top_k so the reversal expectation holds at any catalog size
    reranked = _hybrid(reranker=ReverseReranker(), rerank_top_n=6)
    results_plain = plain.search("wireless headphones battery", top_k=6)
    results_reranked = reranked.search("wireless headphones battery", top_k=6)
    assert _ids(results_reranked) == list(reversed(_ids(results_plain)))
    assert reranked.reranked is True
    assert plain.reranked is False
