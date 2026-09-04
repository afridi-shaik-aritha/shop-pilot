"""Rerankers for hybrid retrieval.

CrossEncoderReranker loads the model lazily so module import stays light.
The protocol keeps rerankers injectable in tests.
"""
from typing import Protocol

from app.models import Product


class Reranker(Protocol):
    def score(self, query: str, products: list[Product]) -> list[float]:
        ...


class CrossEncoderReranker:
    """Cross-encoder relevance scores via sentence-transformers, lazy-loaded."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
        except ModuleNotFoundError:
            raise RuntimeError(
                "sentence-transformers is not installed; "
                "run `pip install sentence-transformers` to use the reranker"
            ) from None
        try:
            self._model = CrossEncoder(self.model_name)
        except Exception as exc:
            raise RuntimeError(
                f"could not load reranker model {self.model_name!r}: {exc}"
            ) from None

    def score(self, query: str, products: list[Product]) -> list[float]:
        self._ensure_loaded()
        if not products:
            return []
        pairs = [
            [query, f"{p.name} {p.category} {p.brand} {p.description} price {p.price}"]
            for p in products
        ]
        return [float(s) for s in self._model.predict(pairs)]
