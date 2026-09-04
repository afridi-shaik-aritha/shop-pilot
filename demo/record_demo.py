"""Recorded end-to-end demo.

Runs the full shopping flow (search -> compare -> cart -> checkout -> blocked
path -> explicit token confirm -> idempotent order) plus a short retrieval
variant comparison, and writes the transcript to demo/recording.md.

Usage:
    python demo/record_demo.py [--out demo/recording.md] [--embedder auto|lexical]
"""
import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from demo.cli import run_demo
from app.retrieval.corpus import load_products
from app.retrieval.embedder import Embedder, LexicalEmbedder, SentenceTransformerEmbedder
from app.retrieval.factory import build_search_index

DEMO_QUERY = "wireless headphones under 10000 with good battery life"


def record_demo(output_path: str = "demo/recording.md", embedder: Embedder | None = None):
    """Run the flow with automatic confirmation; write and return results."""
    products = load_products("data/products.json")
    shared = embedder or SentenceTransformerEmbedder(
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    lines: list[str] = []

    def emit(*parts) -> None:
        text = " ".join(str(p) for p in parts)
        lines.append(text)
        print(text)

    # --- retrieval variant comparison ---
    emit("# Shop-Pilot Recorded Demo")
    emit("")
    emit(f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} UTC_")
    emit("")
    emit(f"## Retrieval variants for: `{DEMO_QUERY}`")
    emit("")
    for variant in ("bm25", "semantic", "hybrid"):
        index = build_search_index(products, variant=variant, embedder=shared)
        hits = index.search(DEMO_QUERY, top_k=3)
        top = ", ".join(
            f"{r.product.product_id} ({r.product.name}) @ {r.product.price}"
            for r in hits
        )
        emit(f"- **{variant}** top 3: {top}")

    # --- purchase flow (auto-answers with the printed token) ---
    emit("")
    emit("## Purchase flow (explicit confirmation gate)")
    emit("")

    def capture(*parts) -> None:
        text = " ".join(str(p) for p in parts)
        lines.append(text)
        print(text)

    def auto_input(prompt: str = "") -> str:
        capture(prompt)
        for line in reversed(lines):
            if line.startswith("CONFIRMATION_TOKEN="):
                return line.split("=", 1)[1].strip()
        raise RuntimeError("confirmation token was never printed")

    result = run_demo(input_fn=auto_input, print_fn=capture)
    emit("")
    emit(f"## Result: order {result['order']['order_id']} COMPLETED, "
         f"idempotent repeat same id: {result['repeat_order_same_id']}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nwrote {output_path}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="demo/recording.md")
    ap.add_argument("--embedder", choices=("auto", "lexical"), default="auto")
    args = ap.parse_args()
    embedder = LexicalEmbedder() if args.embedder == "lexical" else None
    record_demo(output_path=args.out, embedder=embedder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
