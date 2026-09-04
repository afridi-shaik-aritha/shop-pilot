"""Deterministic catalog services. Every fact returned comes from loaded data."""
from app.models import Product, Review
from app.retrieval.corpus import normalize_text

_COMPARE_ATTRS = ("price", "rating", "review_count", "availability")


class ProductNotFound(LookupError):
    pass


class ProductService:
    def __init__(self, products: list[Product]) -> None:
        self._by_id = {p.product_id: p for p in products}

    def refresh(self, products: list[Product]) -> None:
        self._by_id = {p.product_id: p for p in products}

    def list_all(self) -> list[Product]:
        return list(self._by_id.values())

    def get_product(self, product_id: str) -> Product:
        try:
            return self._by_id[product_id]
        except KeyError:
            raise ProductNotFound(f"unknown product: {product_id}") from None

    def find_by_name(self, text: str) -> list[Product]:
        """Best-effort name match: exact, containment, then token overlap.

        Used by tools when the model passes a name or a model-invented slug
        instead of the canonical product id. Only the top-scoring products
        are returned: a unique best match resolves, a tie (e.g. 'SonicWave'
        matching the X5 and its refurbished unit) stays ambiguous so callers
        can surface the candidate ids instead of silently guessing.
        """
        q = " ".join(normalize_text(text))
        if not q:
            return []
        qt = set(q.split())
        scored = []
        for p in self._by_id.values():
            n = " ".join(normalize_text(p.name))
            if not n:
                continue
            overlap = len(qt & set(n.split()))
            if n == q:
                score = 100
            elif q in n or n in q:
                score = 60 + 10 * overlap
            else:
                score = 10 * overlap
            if score:
                scored.append((score, p))
        if not scored:
            return []
        best = max(s for s, _ in scored)
        scored = [(s, p) for s, p in scored if s == best]
        scored.sort(key=lambda t: (-t[0], len(t[1].name)))
        return [p for _, p in scored]

    def compare_products(self, product_ids: list[str]) -> dict:
        products = [self.get_product(pid) for pid in product_ids]
        rows: dict[str, dict] = {}
        for attr in _COMPARE_ATTRS:
            rows[attr] = {p.product_id: getattr(p, attr) for p in products}
        spec_keys: list[str] = []
        for p in products:
            for k in p.specs:
                if k not in spec_keys:
                    spec_keys.append(k)
        for k in spec_keys:
            rows[f"spec:{k}"] = {p.product_id: p.specs.get(k) for p in products}
        return {"products": [p.product_id for p in products], "rows": rows}


class ReviewService:
    def __init__(self, reviews: list[Review]) -> None:
        self._reviews = list(reviews)

    def search_reviews(
        self, product_id: str, query: str | None = None, top_k: int = 5
    ) -> list[dict]:
        pool = [r for r in self._reviews if r.product_id == product_id]
        if query:
            qtokens = set(normalize_text(query))
            scored = []
            for r in pool:
                dtokens = set(normalize_text(f"{r.title} {r.body}"))
                scored.append((len(qtokens & dtokens), r.helpful_votes, r))
            scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
            pool = [r for _, _, r in scored]
        else:
            pool = sorted(pool, key=lambda r: r.helpful_votes, reverse=True)
        return [
            {
                "review_id": r.review_id,
                "product_id": r.product_id,
                "rating": r.rating,
                "title": r.title,
                "body": r.body,
                "kind": "review-quote",
            }
            for r in pool[: max(top_k, 0)]
        ]
