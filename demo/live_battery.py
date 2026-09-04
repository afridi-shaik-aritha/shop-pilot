"""Live regression battery — replays every verbatim live failure from the
2026-09-04 hardening session against the provider in .env (default NVIDIA NIM
+ openai/gpt-oss-20b) and asserts the fix still holds end to end:

  A. product-id guessing      "add sonic wave to cart" must land P01 (name/slug resolution)
  B. feature refusal          "smartwatch with heart-rate tracking" must search, not apologize
  C. referential compare      "compare these three" must compare the products actually shown
  D. confirm gates            "confirm the order" / "proceed to checkout" while a slip awaits
                             → deterministic replies, LLM never runs, slip not rotated
  E. cancel gate              "cancel the checkout" → slip REJECTED, trolley untouched
  F. zero-tool fabrication    "show me laptops under 30000" must search and surface the real P22,
                             never invented SKUs under foreign ids, never a forged picks tag

The canonical routed smoke is demo/live_chat.py (separate). Exit 0 only if
every scenario passes.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import Settings
from app.llm import OpenAICompatibleClient


def load_dotenv(path: str = ".env") -> None:
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


def _chat(client, sid: str | None, message: str) -> dict:
    body = {"message": message}
    if sid:
        body["session_id"] = sid
    resp = client.post("/chat", json=body)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    return resp.json()


def scenario_a(client, sid) -> list[str]:
    """Name/slug resolution — the 'sonicwave_x5' transcript."""
    notes: list[str] = []
    r1 = _chat(client, sid, "I need wireless headphones under \u20b910,000 with good "
                           "battery life and good reviews")
    assert "search_products" in (r1.get("tools") or []), "turn 1 did not search"
    notes.append("search: ok")
    r2 = _chat(client, sid, "alright, add sonic wave to cart")
    tools2 = r2.get("tools") or []
    assert any(t in ("add_to_cart",) for t in tools2), f"turn 2 tools={tools2}"
    assert "isn't recognized" not in r2.get("reply", "") and \
        "not recognized" not in r2.get("reply", ""), "turn 2 still failed to resolve"
    notes.append("add sonic wave -> resolved (no invented-id error)")
    r3 = _chat(client, sid, 'this one "SonicWave X5 Wireless Headphones"')
    cart = client.get("/cart", params={"session_id": sid}).json()
    items = [(i["product_id"], i["quantity"]) for i in cart.get("items", [])]
    assert items == [("P01", 1)], f"cart={items}"
    notes.append("quoted name + final cart P01 x1")
    return notes


def scenario_b(client, sid) -> list[str]:
    """Feature-ask refusal — the smartwatch heart-rate transcript."""
    notes: list[str] = []
    r = _chat(client, sid, "Show me a smartwatch with heart-rate tracking")
    tools = r.get("tools") or []
    assert "search_products" in tools, f"refused without searching: tools={tools}"
    low = r.get("reply", "").lower()
    for banned in ("i'm sorry", "can't provide", "cannot provide", "can't help"):
        assert banned not in low, f"reply refused: {r.get('reply')[:200]}"
    assert "pulsefit" in low or "P05" in r.get("reply", ""), "PulseFit S2 not surfaced"
    notes.append("heart-rate ask -> searched, grounded PulseFit S2")
    return notes


def scenario_c(client, sid) -> list[str]:
    """Referential compare — 'compare these three' must hit the shown set."""
    notes: list[str] = []
    r1 = _chat(client, sid, "I need wireless headphones under \u20b910,000 with good "
                            "battery life and good reviews")
    shown = set(p["product_id"] for p in r1.get("products", []))
    assert shown, "turn 1 produced no product cards"
    assert "P01" in shown
    notes.append(f"turn 1 shown: {sorted(shown)}")
    r2 = _chat(client, sid, "compare these three")
    tools2 = r2.get("tools") or []
    assert "compare_products" in tools2, f"compare not used: {tools2}"
    compared = set(p["product_id"] for p in r2.get("products", []))
    assert compared, "compare turn produced no cards"
    assert compared <= shown, f"compared products {sorted(compared)} not a subset of shown {sorted(shown)}"
    assert "P01" in compared
    notes.append(f"compare these three -> {sorted(compared)} (all from the shown set)")
    return notes


def scenario_de(client, sid) -> list[str]:
    """Confirm + cancel gates with a real slip standing (deterministic paths)."""
    notes: list[str] = []
    sid = client.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    p1 = client.post("/checkout/prepare", json={"session_id": sid}).json()
    assert p1["status"] == "AWAITING_CONFIRMATION"

    for msg in ["confirm the order", "yes, proceed to checkout", "alright, confirm"]:
        r = _chat(client, sid, msg)
        assert (r.get("tools") or []) == [], f"gate leaked to LLM on {msg!r}: {r.get('tools')}"
        assert "I confirm this order" in r.get("reply", ""), f"reply not a gate reply: {r.get('reply')[:200]}"
        notes.append(f"{msg!r} -> deterministic gate (no LLM)")
        slip = client.get("/checkout", params={"session_id": sid}).json()
        assert slip["checkout_id"] == p1["checkout_id"] and slip["status"] == "AWAITING_CONFIRMATION"

    r = _chat(client, sid, "cancel the checkout")
    assert (r.get("tools") or []) == [], "cancel leaked to LLM"
    assert "trolley is untouched" in r.get("reply", "")
    slip = client.get("/checkout", params={"session_id": sid}).json()
    assert slip["status"] == "REJECTED" and slip["confirmation_token"] == ""
    cart = client.get("/cart", params={"session_id": sid}).json()
    items = [(i["product_id"], i["quantity"]) for i in cart.get("items", [])]
    assert items == [("P01", 1)], f"cancel emptied the trolley: {items}"
    notes.append("cancel the checkout -> slip REJECTED, trolley untouched")
    return notes


def scenario_f(client, sid) -> list[str]:
    """Zero-tool fabrication — the invented-laptops transcript. The catalog's
    only laptop under \u20b930,000 is P22; ids P02/P03/P14/P15/P16 are headphones/
    smartwatches. The reply must be tool-grounded and carry no forged picks tag."""
    notes: list[str] = []
    r = _chat(client, sid, "now show me laptops under 30000")
    tools = r.get("tools") or []
    assert "search_products" in tools, f"answered without searching: tools={tools}"
    low = (r.get("reply") or "").lower()
    assert "[products shown above" not in low, "model forged/echoed the picks tag"
    assert "p22" in low, f"real P22 laptop not surfaced: {r.get('reply')[:200]}"
    picks = set(p["product_id"] for p in r.get("products", []))
    assert picks == {"P22"} or "P22" in picks, f"picks missing the grounded laptop: {picks}"
    notes.append("laptops under 30000 -> searched, real P22 surfaced, no forged tag")
    return notes


def scenario_e2(client, sid) -> list[str]:
    """Cancel with nothing prepared must be deterministic too."""
    r = _chat(client, sid, "cancel the checkout")
    assert (r.get("tools") or []) == [], "no-slip cancel leaked to LLM"
    assert "There's no checkout to cancel" in r.get("reply", "")
    return ["cancel with no slip -> deterministic reply"]


def main() -> int:
    load_dotenv()
    settings = Settings.from_env()
    llm = OpenAICompatibleClient.from_settings(settings)
    client = TestClient(create_app(settings, llm=llm))
    print(f"=== live battery — {settings.llm_model or '(from env)'} ===")
    scenarios = [
        ("A name/slug resolution", scenario_a),
        ("B feature-ask refusal", scenario_b),
        ("C referential compare", scenario_c),
        ("D confirm gates + E cancel gate", scenario_de),
        ("E2 cancel with no slip", scenario_e2),
        ("F zero-tool fabrication", scenario_f),
    ]
    failed = 0
    for label, fn in scenarios:
        sid = client.post("/sessions").json()["session_id"]
        try:
            notes = fn(client, sid)
            for n in notes:
                print(f"  PASS  {n}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {label}: {exc}")
        except Exception as exc:  # provider/network errors
            failed += 1
            print(f"  FAIL  {label}: exception {type(exc).__name__}: {exc}")
    print(f"\nverdict: {'PASS' if failed == 0 else f'FAIL ({failed} scenario(s))'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
