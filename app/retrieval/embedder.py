"""Embedders for semantic retrieval.

SentenceTransformerEmbedder loads the model lazily (first encode call) so
importing this module never pulls in torch. LexicalEmbedder is a
deterministic, dependency-free fallback for tests and offline runs.
"""
import hashlib
from typing import Protocol

_DIM = 256
_cache: dict[str, "Embedder"] = {}


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]:
        ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = sum(v * v for v in vec) ** 0.5
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class SentenceTransformerEmbedder:
    """Real semantic embedder (sentence-transformers), loaded on first use."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ModuleNotFoundError:
            raise RuntimeError(
                "sentence-transformers is not installed; "
                "run `pip install sentence-transformers` to use real embeddings"
            ) from None
        try:
            self._model = SentenceTransformer(self.model_name)
        except Exception as exc:  # model download/load failure -> clear error
            raise RuntimeError(
                f"could not load embedding model {self.model_name!r}: {exc}"
            ) from None

    def encode(self, texts: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]


class LexicalEmbedder:
    """Deterministic count-vector embedder over hashed token features.

    Fixed dimension, no model, no network. Cosine of these vectors behaves
    like a lightweight lexical similarity — good for tests/fallback.
    """

    def __init__(self, dimension: int = _DIM) -> None:
        self.dimension = dimension

    def _tokens(self, text: str) -> list[str]:
        out = []
        current = []
        for ch in text.lower():
            if ch.isalnum():
                current.append(ch)
            elif current:
                out.append("".join(current))
                current = []
        if current:
            out.append("".join(current))
        return out

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dimension
            for token in self._tokens(text):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
                index = int.from_bytes(digest[:4], "little") % self.dimension
                vec[index] += 1.0
            vectors.append(_l2_normalize(vec))
        return vectors


def get_embedder(name: str, dimension: int = _DIM) -> Embedder:
    """Cached embedder by name: 'lexical'/'stub' -> LexicalEmbedder, otherwise a
    SentenceTransformerEmbedder for that model name."""
    key = f"{name}:{dimension}" if name in ("lexical", "stub") else name
    if key not in _cache:
        if name in ("lexical", "stub"):
            _cache[key] = LexicalEmbedder(dimension=dimension)
        else:
            _cache[key] = SentenceTransformerEmbedder(name)
    return _cache[key]
