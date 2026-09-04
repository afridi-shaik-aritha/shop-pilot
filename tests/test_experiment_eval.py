# tests/test_experiment_eval.py
import json

from app.retrieval.corpus import load_products
from evaluation.experiment_eval import _summarize, run_variants


class StubEmbedder:
    def encode(self, texts):
        out = []
        for t in texts:
            low = t.lower()
            if "wireless headphones" in low:
                out.append([1.0, 0.0, 0.0])
            elif "speaker" in low:
                out.append([0.0, 1.0, 0.0])
            elif "smartwatch" in low:
                out.append([0.0, 0.0, 1.0])
            else:
                out.append([0.0, 0.0, 0.0])
        return out


class IdentityReranker:
    def score(self, query, products):
        return [float(len(products) - i) for i in range(len(products))]


def _products_and_cases():
    products = load_products("data/products.json")
    with open("evaluation/dataset.json", encoding="utf-8") as f:
        cases = json.load(f)
    return products, cases


def test_run_variants_covers_all_variants_and_metrics():
    products, cases = _products_and_cases()
    rows = run_variants(products, cases, k=5, embedder=StubEmbedder())
    assert {r["variant"] for r in rows} == {"bm25", "semantic", "hybrid"}
    assert len(rows) == 3 * len(cases)
    assert all(0.0 <= r["recall"] <= 1.0 for r in rows)
    assert all("constraint" in r and "latency_ms" in r for r in rows)


def test_stub_embedder_recall_is_perfect_on_dataset():
    products, cases = _products_and_cases()
    rows = run_variants(products, cases, k=5, embedder=StubEmbedder())
    summary = _summarize(rows)
    for variant in ("bm25", "semantic", "hybrid"):
        assert summary[variant]["recall"] == 1.0


def test_rerank_variant_added_when_reranker_present():
    products, cases = _products_and_cases()
    rows = run_variants(
        products, cases, k=5, embedder=StubEmbedder(), reranker=IdentityReranker()
    )
    assert "hybrid+rerank" in {r["variant"] for r in rows}


def test_json_round_trip(tmp_path):
    products, cases = _products_and_cases()
    rows = run_variants(products, cases, k=5, embedder=StubEmbedder())
    out = tmp_path / "exp.json"
    out.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert len(loaded["rows"]) == len(rows)
    assert loaded["rows"][0]["variant"] == rows[0]["variant"]
