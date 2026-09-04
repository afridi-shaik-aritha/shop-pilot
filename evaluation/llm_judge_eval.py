"""LLM-as-judge response eval over the two scripted response scenarios.

Exit code is always 0 — report-only. Without LLM_PROVIDER/LLM_BASE_URL/
LLM_API_KEY/LLM_MODEL configured the runner prints SKIPPED rows (Plan 3
decision: LLM-judge eval deferred to Plan 4, needs live provider keys).
"""
import json
import re
import sys

sys.path.insert(0, ".")

from app.agent import ShoppingAgent
from app.cart.service import CartService
from app.catalog.service import ProductService
from app.checkout.service import CheckoutService, OrderService
from app.config import Settings, load_env_file
from app.llm import FakeLLM, LLMMessage, OpenAICompatibleClient, ToolCall
from app.retrieval.bm25 import ProductIndex
from app.retrieval.corpus import load_products
from app.state.models import Cart
from app.tools import build_tools

_JUDGE_SYSTEM = (
    "You audit an AI shopping assistant's final answer against the tool "
    "results it actually saw. Judge: (1) faithful — every price and product "
    "id in the answer appears in the trace; (2) score 1-5 for helpfulness. "
    'Reply with strict JSON: {"faithful": true|false, "score": 1-5, '
    '"rationale": "one sentence"}.'
)

_JSON_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _scenario_runs() -> list[dict]:
    """Replay the two response_eval scenarios and capture answer + trace."""
    rows = []
    for name, final_text in [
        ("grounded-answer", "SonicWave X5 (P01) costs 8499.0 with rating 4.4."),
        ("hallucinated-price", "P01 costs 100.0 and P99 is better."),
    ]:
        products = load_products("data/products.json")
        catalog = ProductService(products)
        carts = CartService(catalog)
        tools = build_tools(
            ProductIndex(products), catalog, carts, CheckoutService(carts), OrderService(catalog)
        )
        script = [
            LLMMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="search_products",
                        arguments={"query": "wireless headphones long battery life", "top_k": 2},
                    )
                ],
            ),
            LLMMessage(content=final_text, tool_calls=[]),
        ]
        result = ShoppingAgent(llm=FakeLLM(script), tools=tools).run(
            "headphones", {"cart": Cart(), "checkout": None}
        )
        rows.append(
            {"scenario": name, "response": result.text, "trace": str(result.trace)}
        )
    return rows


def judge_response(llm, response: str, trace: str) -> dict:
    messages = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {
            "role": "user",
            "content": f"Assistant answer:\n{response}\n\nTool trace:\n{trace}",
        },
    ]
    content = llm.complete(messages, {}).content
    verdict = _parse_verdict(content)
    verdict["parse_error"] = verdict["parse_error"] is not None
    if verdict["parse_error"]:
        verdict["raw"] = content
    return verdict


def _coerce_faithful(value) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in ("true", "yes", "1"):
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value == 1:
        return True
    return False


def _parse_verdict(content: str) -> dict:
    text = content or ""
    # Prefer a robust scan for the first decodable JSON object (handles
    # multi-JSON output better than a greedy regex).
    decoder = json.JSONDecoder()
    for start, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            data, _ = decoder.raw_decode(text[start:])
            if isinstance(data, dict):
                return {
                    "faithful": _coerce_faithful(data.get("faithful", False)),
                    "score": int(data.get("score", 0)),
                    "rationale": str(data.get("rationale", "")),
                    "parse_error": None,
                }
        except (ValueError, TypeError):
            continue
    match = _JSON_RE.search(text)
    if match:
        try:
            data = json.loads(match.group(0))
            return {
                "faithful": _coerce_faithful(data.get("faithful", False)),
                "score": int(data.get("score", 0)),
                "rationale": str(data.get("rationale", "")),
                "parse_error": None,
            }
        except (ValueError, TypeError):
            pass
    faithful = None
    score = 0
    rationale = ""
    for line in (content or "").splitlines():
        if line.lower().startswith("faithful"):
            faithful = "true" in line.lower()
        elif line.lower().startswith("score"):
            digits = re.findall(r"\d+", line)
            if digits:
                score = int(digits[0])
        elif line.lower().startswith("rationale"):
            rationale = line.split(":", 1)[1].strip()
    if faithful is None:
        return {
            "faithful": False,
            "score": score,
            "rationale": rationale,
            "parse_error": "unparseable judge output",
        }
    return {"faithful": faithful, "score": score, "rationale": rationale, "parse_error": None}


def run_judge(llm) -> list[dict]:
    rows = []
    for scenario in _scenario_runs():
        verdict = judge_response(llm, scenario["response"], scenario["trace"])
        rows.append({"scenario": scenario["scenario"], **verdict})
    return rows


def main(llm=None) -> int:
    if llm is None:
        load_env_file()
        settings = Settings.from_env()
        if settings.has_llm():
            llm = OpenAICompatibleClient.from_settings(settings)
    if llm is None:
        print(
            "SKIPPED: no LLM configured. Set LLM_PROVIDER/LLM_BASE_URL/"
            "LLM_API_KEY/LLM_MODEL and re-run for LLM-judge verdicts."
        )
        return 0
    print("| scenario | faithful | score | parse_error | rationale |")
    print("|---|---|---|---|---|")
    for row in run_judge(llm):
        print(
            f"| {row['scenario']} | {row['faithful']} | {row['score']} "
            f"| {row['parse_error']} | {row.get('rationale', '')[:200]} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
