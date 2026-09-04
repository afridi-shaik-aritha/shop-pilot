# tests/test_retrieval_factory.py
import pytest

from app.config import Settings
from app.retrieval.corpus import load_products
from app.retrieval.factory import build_search_index
from app.retrieval.reranker import CrossEncoderReranker


class StubEmbedder:
    def encode(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


def _products():
    return load_products("data/products.json")


def test_every_variant_resolves_with_stub_embedder():
    for variant in ("bm25", "semantic", "hybrid"):
        index = build_search_index(_products(), variant=variant, embedder=StubEmbedder())
        assert index.variant == variant
        hits = index.search("wireless headphones with good battery life", top_k=2)
        assert hits[0].product.product_id == "P01"


def test_unknown_variant_raises():
    with pytest.raises(ValueError):
        build_search_index(_products(), variant="teleport")


def test_rerank_enabled_attaches_lazy_reranker():
    index = build_search_index(
        _products(), variant="hybrid", rerank_enabled=True, embedder=StubEmbedder()
    )
    assert index.variant == "hybrid"
    assert index.reranked is True
    assert isinstance(index._reranker, CrossEncoderReranker)


def test_settings_retrieval_defaults():
    s = Settings()
    assert s.retrieval_variant == "bm25"
    assert s.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert s.rerank_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert s.rerank_enabled is False
    assert s.rerank_top_n == 20
    assert s.hybrid_rrf_k == 60


def test_settings_env_retrieval(monkeypatch):
    monkeypatch.setenv("ASA_RETRIEVAL", "hybrid")
    monkeypatch.setenv("ASA_RERANK", "true")
    monkeypatch.setenv("ASA_RRF_K", "30")
    monkeypatch.setenv("ASA_RERANK_TOP_N", "8")
    s = Settings.from_env()
    assert s.retrieval_variant == "hybrid"
    assert s.rerank_enabled is True
    assert s.hybrid_rrf_k == 30
    assert s.rerank_top_n == 8
