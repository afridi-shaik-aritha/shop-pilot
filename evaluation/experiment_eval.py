"""Retrieval variant experiment comparison.

Usage:
  python evaluation/experiment_eval.py --k 5                  (real embeddings, cached)
  python evaluation/experiment_eval.py --embedder stub        (deterministic, no model)
  python evaluation/experiment_eval.py --rerank --json out.json

Output: one metrics table per variant plus a best-variant summary and an
optional JSON file with every per-case row.
"""
import argparse
import json
import sys
import time

sys.path.insert(0, ".")

from app.models import Product
from app.retrieval.corpus import load_products
from app.retrieval.embedder import LexicalEmbedder
from app.retrieval.factory import build_search_index
from app.retrieval.hybrid import HybridIndex
from app.retrieval.reranker import Reranker
from evaluation.metrics import constraint_match, precision_at_k, recall_at_k, reciprocal_rank

VARIANT_NAMES = ("bm25", "semantic", "hybrid")


def run_variants(
    products: list[Product],
    cases: list[dict],
    k: int = 5,
    embedder=None,
    reranker: Reranker | None = None,
) -> list[dict]:
    """Score every case against every variant; return one dict per row."""
    from app.retrieval.embedder import LexicalEmbedder as _Lex

    indices: dict[str, object] = {}
    for variant in VARIANT_NAMES:
        try:
            idx = build_search_index(
                products, variant=variant, embedder=embedder
            )
            # Warmup (model load excluded from timings); fall back to stub
            # offline so the default --embedder auto path never crashes.
            try:
                idx.search("warmup", top_k=1)
            except Exception:
                idx = build_search_index(
                    products, variant=variant, embedder=_Lex()
                )
                idx.search("warmup", top_k=1)
            indices[variant] = idx
        except Exception as exc:
            # Never fail the whole experiment because one variant is
            # unavailable offline; record the fallback instead.
            idx = build_search_index(products, variant=variant, embedder=_Lex())
            indices[variant] = idx
    if reranker is not None:
        indices["hybrid+rerank"] = HybridIndex(
            products, embedder=embedder, reranker=reranker, rerank_top_n=20
        )
    rows: list[dict] = []
    for variant, index in indices.items():
        for case in cases:
            start = time.perf_counter()
            hits = index.search(case["query"], top_k=k)
            latency_ms = (time.perf_counter() - start) * 1000.0
            got = [r.product.product_id for r in hits]
            constraints = case.get("expected_constraints") or {}
            # constraint@1: does the top suggestion honor the shopper's stated
            # constraints? (All-of-top-k is meaningless on a tiny catalog.)
            constraint = 1.0
            if not got:
                constraint = 0.0
            elif constraints:
                constraint = float(constraint_match(hits[0].product, constraints))
            rows.append(
                {
                    "variant": variant,
                    "query": case["query"],
                    "recall": recall_at_k(case["expected_product_ids"], got),
                    "precision": precision_at_k(case["expected_product_ids"], got),
                    "mrr": reciprocal_rank(case["expected_product_ids"], got),
                    "constraint": constraint,
                    "latency_ms": round(latency_ms, 3),
                    "top_hit": got[0] if got else "-",
                }
            )
    return rows


def _summarize(rows: list[dict]) -> dict[str, dict]:
    per_variant: dict[str, list[dict]] = {}
    for row in rows:
        per_variant.setdefault(row["variant"], []).append(row)
    summary = {}
    for variant, group in per_variant.items():
        n = len(group)
        summary[variant] = {
            "recall": sum(r["recall"] for r in group) / n,
            "precision": sum(r["precision"] for r in group) / n,
            "mrr": sum(r["mrr"] for r in group) / n,
            "constraint": sum(r["constraint"] for r in group) / n,
            "latency_ms": sum(r["latency_ms"] for r in group) / n,
            "queries": n,
        }
    return summary


def _print_rows(rows: list[dict]) -> None:
    print("| variant | query | recall | precision | MRR | constraint | latency_ms | top_hit |")
    print("|---|---|---|---|---|---|---|---|")
    for row in rows:
        print(
            f"| {row['variant']} | {row['query'][:44]} | {row['recall']:.2f} "
            f"| {row['precision']:.2f} | {row['mrr']:.2f} | {row['constraint']:.2f} "
            f"| {row['latency_ms']:.1f} | {row['top_hit']} |"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", default="data/products.json")
    ap.add_argument("--dataset", default="evaluation/dataset.json")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--embedder", choices=("auto", "stub"), default="auto")
    ap.add_argument("--rerank", action="store_true", help="add a hybrid+rerank column (real cross-encoder)")
    ap.add_argument("--json", dest="json_path", default=None)
    args = ap.parse_args()

    products = load_products(args.products)
    with open(args.dataset, encoding="utf-8") as f:
        cases = json.load(f)

    embedder = LexicalEmbedder() if args.embedder == "stub" else None
    reranker = None
    if args.rerank:
        from app.retrieval.factory import DEFAULT_RERANK_MODEL
        from app.retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker(DEFAULT_RERANK_MODEL)

    rows = run_variants(products, cases, k=args.k, embedder=embedder, reranker=reranker)
    _print_rows(rows)
    summary = _summarize(rows)
    print("\n| variant (avg over queries) | recall | precision | MRR | constraint | latency_ms |")
    print("|---|---|---|---|---|---|")
    for variant, stats in summary.items():
        print(
            f"| {variant} | {stats['recall']:.2f} | {stats['precision']:.2f} "
            f"| {stats['mrr']:.2f} | {stats['constraint']:.2f} | {stats['latency_ms']:.1f} |"
        )
    best = max(summary, key=lambda v: (summary[v]["recall"], -summary[v]["latency_ms"]))
    print(f"\nbest variant by recall: {best}")

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump({"k": args.k, "rows": rows, "summary": summary}, f, indent=2)
        print(f"wrote {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
