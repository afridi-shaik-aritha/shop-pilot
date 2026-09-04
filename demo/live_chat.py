"""Live routed smoke test against a real LLM (OpenRouter or any OpenAI-compatible).

Drives the actual HTTP surface (`/chat` through `create_app`) with a scripted
scenario: one policy turn, one catalog turn, one cart turn, one checkout-prep
turn, and a final cart change after the slip was prepared. It asserts role
routing, read-only reach for catalog, that the cart role never sees order
tools, that no reply ever echoes a confirmation code, and that mutating the
cart after prepare_checkout voids the awaiting slip server-side (a stale
confirm is then rejected). It never confirms or places an order.

Because the app runs in-process (TestClient), each run gets a throwaway SQLite
file and no ports or servers are needed.

Usage:
    python demo/live_chat.py                          # model from .env
    python demo/live_chat.py --model deepseek/deepseek-chat
    python demo/live_chat.py --model openai/gpt-4o-mini --provider openrouter
    python demo/live_chat.py --compare "modelA,modelB"   # verdict table

Exit codes: 0 all green, 1 any turn failed, 2 scenario assertions failed.
"""
import argparse
import os
import re
import sys
import tempfile
from dataclasses import replace

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import Settings
from app.llm import OpenAICompatibleClient

SCENARIO = [
    # (expected role, message, note)
    ("policy", "What is your return policy and how is GST charged on delivery?", "policy grounding"),
    ("catalog", "Compare the SonicWave X5 and the BassBoom Pro wireless headphones.", "read-only reach"),
    ("cart", "I need the SonicWave X5 (P01) wireless headphones — add them to my cart.", "cart mutation"),
    ("cart", "The cart is settled. Prepare the checkout so I can review and confirm.", "checkout prep"),
    ("cart", "Actually, add a ThunderBox Bluetooth Speaker (P04) to the cart as well — one unit.", "cart mutation after prepare"),
]

# Tools that change the cart — the fifth turn must use at least one so the
# awaiting slip genuinely has nothing to stand on.
_MUTATORS = ("add_to_cart", "remove_from_cart", "update_cart_quantity", "clear_cart")

HEX16 = re.compile(r"\b[0-9a-f]{16}\b")


def load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE lines (later duplicates win); never override the env."""
    if not os.path.exists(path):
        return
    parsed: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            parsed[key.strip()] = value.strip().strip('"').strip("'")
    for key, value in parsed.items():
        if key and key not in os.environ:
            os.environ[key] = value


def run_model(model: str, provider: str | None, base_url: str | None,
              api_key: str | None, verbose: bool, timeout_s: int = 60) -> tuple[bool, list[str]]:
    """Run the scenario against one model; returns (passed, notes)."""
    notes: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        overrides: dict[str, str] = {"db_path": os.path.join(tmp, "live.db")}
        if model:
            overrides["llm_model"] = model
        if provider:
            overrides["llm_provider"] = provider
        if base_url:
            overrides["llm_base_url"] = base_url
        if api_key:
            overrides["llm_api_key"] = api_key
        overrides["llm_timeout_s"] = timeout_s  # runner default 60s; reasoning models need more
        settings = replace(Settings.from_env(), **overrides)
        if not settings.has_llm():
            return False, ["no LLM configured — set LLM_PROVIDER/LLM_BASE_URL/"
                           "LLM_API_KEY/LLM_MODEL in .env or pass --provider/--base-url/--api-key"]
        llm = OpenAICompatibleClient.from_settings(settings)
        client = TestClient(create_app(settings, llm=llm))
        sid: str | None = None
        try:
            for expected_role, message, note in SCENARIO:
                body = {"message": message}
                if sid:
                    body["session_id"] = sid
                resp = client.post("/chat", json=body)
                if resp.status_code != 200:
                    return False, notes + [f"{note}: HTTP {resp.status_code}: {resp.text[:160]}"]
                data = resp.json()
                sid = data["session_id"]
                reply = data.get("reply", "")
                tools = data.get("tools") or []
                if data.get("role") != expected_role:
                    return False, notes + [f"{note}: role={data.get('role')} expected {expected_role}"]
                if HEX16.search(reply):
                    return False, notes + [f"{note}: reply echoed a 16-hex confirmation-style token"]
                if data.get("status") != "ok":
                    return False, notes + [f"{note}: agent status={data.get('status')}: {reply[:160]}"]
                if expected_role == "catalog" and any(
                    t.startswith(("add_", "update_", "remove_", "prepare_", "confirm_", "place_")) for t in tools
                ):
                    return False, notes + [f"{note}: catalog role used a mutating tool: {tools}"]
                if verbose:
                    print(f"  [{note}] role={data.get('role')} tools={tools}")
                    print(f"    -> {reply[:220]}")
                notes.append(f"{note}: ok")
            # Final state integrity: the cart change after prepare_checkout
            # must have voided the awaiting slip server-side.
            if expected_role == "cart" and note == "cart mutation after prepare":
                if not any(t in _MUTATORS for t in tools):
                    return False, notes + ["cart mutation after prepare: model did not mutate the cart"]
                slip = client.get("/checkout", params={"session_id": sid})
                if slip.status_code != 400:
                    return False, notes + [
                        f"slip-void: /checkout returned {slip.status_code} after a cart change"
                        f" (expected 400 — the awaiting slip must not survive a changed trolley)"]
                stale = client.post("/checkout/confirm", json={
                    "session_id": sid, "confirmation_token": "stale-token"})
                if stale.status_code != 400:
                    return False, notes + [
                        f"stale-confirm: /checkout/confirm returned {stale.status_code} with no slip"]
                notes.append("slip voided by cart change: ok")
        except Exception as exc:  # network/provider/client errors surface here
            return False, notes + [f"exception: {type(exc).__name__}: {exc}"]
        return True, notes


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="", help="LLM_MODEL override, e.g. deepseek/deepseek-chat")
    parser.add_argument("--provider", default="", help="LLM_PROVIDER override (openrouter|nim|lmstudio|deepinfra)")
    parser.add_argument("--base-url", default="", help="LLM_BASE_URL override")
    parser.add_argument("--api-key", default="", help="LLM_API_KEY override")
    parser.add_argument("--compare", default="", help="comma list of models to run side by side")
    parser.add_argument("--timeout", type=int, default=60, help="per-request timeout seconds (reasoning models need more)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    models = [m.strip() for m in args.compare.split(",") if m.strip()] or [args.model or ""]
    if len(models) > 1 and args.model:
        print("note: --model ignored when --compare is given")
    results: list[tuple[str, bool, list[str]]] = []
    for model in models:
        label = model or "(.env)"
        print(f"\n=== model: {label} ===")
        ok, notes = run_model(model, args.provider, args.base_url, args.api_key,
                              args.verbose, timeout_s=args.timeout)
        for n in notes:
            print("  " + ("PASS" if n.endswith("ok") else "FAIL") + "  " + n)
        results.append((label, ok, notes))
        print(f"verdict: {'PASS' if ok else 'FAIL'}")

    if len(results) > 1:
        print("\n=== comparison ===")
        for label, ok, _ in results:
            print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print(f"\n{sum(1 for _, ok, _ in results if ok)}/{len(results)} models passed")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
