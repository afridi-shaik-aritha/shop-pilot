"""Baseline retrieval eval. Usage:
python evaluation/retrieval_eval.py --products data/products.json --dataset evaluation/dataset.json --k 5
"""
import argparse
import json
import sys

sys.path.insert(0, ".")

from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products
from evaluation.metrics import precision_at_k, recall_at_k, reciprocal_rank


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", default="data/products.json")
    ap.add_argument("--dataset", default="evaluation/dataset.json")
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    products = load_products(args.products)
    index = ProductIndex(products)
    with open(args.dataset, encoding="utf-8") as f:
        cases = json.load(f)

    print(f"| query | recall@{args.k} | precision@{args.k} | MRR | top_hit |")
    print("|---|---|---|---|---|")
    totals = [0.0, 0.0, 0.0]
    for case in cases:
        res = index.search(case["query"], top_k=args.k)
        got = [r.product.product_id for r in res]
        r = recall_at_k(case["expected_product_ids"], got)
        p = precision_at_k(case["expected_product_ids"], got)
        m = reciprocal_rank(case["expected_product_ids"], got)
        totals[0] += r
        totals[1] += p
        totals[2] += m
        top = got[0] if got else "-"
        print(f"| {case['query'][:48]} | {r:.2f} | {p:.2f} | {m:.2f} | {top} |")
    n = max(len(cases), 1)
    print(f"| **avg** | {totals[0]/n:.2f} | {totals[1]/n:.2f} | {totals[2]/n:.2f} |  |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
