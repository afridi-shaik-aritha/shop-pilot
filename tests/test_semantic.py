# tests/test_semantic.py
import builtins

import pytest

from app.retrieval.corpus import load_products, product_to_document
from app.retrieval.embedder import SentenceTransformerEmbedder
from app.retrieval.semantic import SemanticIndex


class StubEmbedder:
    """Deterministic text->unit-vector mapping; no model, no network."""

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


def _index():
    return SemanticIndex(load_products("data/products.json"), StubEmbedder())


def _ids(results):
    return [r.product.product_id for r in results]


def test_semantic_returns_relevant_first_and_variant():
    results = _index().search("wireless headphones battery", top_k=3)
    assert results[0].product.product_id == "P01"
    assert results[0].score > 0
    assert _index().variant == "semantic"


def test_max_price_filter_excludes_expensive():
    ids = _ids(
        _index().search("wireless headphones", top_k=10, filters={"max_price": 10000})
    )
    assert "P01" in ids
    assert "P02" not in ids


def test_category_and_in_stock_filters():
    ids = _ids(
        _index().search(
            "wireless headphones",
            top_k=10,
            filters={"category": "wireless headphones", "in_stock": True},
        )
    )
    assert "P01" in ids
    assert "P06" not in ids


def test_docs_embedded_once_per_product():
    index = _index()
    assert len(index._vectors) == len(load_products("data/products.json"))


def test_top_k_and_empty_query():
    assert len(_index().search("speaker", top_k=1)) == 1
    assert _index().search("   ", top_k=5) == []


def test_missing_dependency_raises_clear_error(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ModuleNotFoundError("No module named 'sentence_transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    embedder = SentenceTransformerEmbedder("any-model")
    with pytest.raises(RuntimeError, match="sentence-transformers"):
        embedder.encode(["hi"])
