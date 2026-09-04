# tests/test_api.py
from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import Settings
from app.llm import FakeLLM, LLMMessage, ToolCall


def _app(tmp_path, script=None):
    # No script => no LLM configured (the /chat 503 path); scripted calls
    # inject a FakeLLM so the agent never touches the network.
    return create_app(
        Settings(db_path=str(tmp_path / "t.db")), llm=FakeLLM(script) if script else None
    )


def test_health_and_chat_needs_llm(tmp_path):
    c = TestClient(_app(tmp_path))
    assert c.get("/health").json() == {"ok": True, "llm": "none"}
    assert c.post("/chat", json={"message": "hi"}).status_code == 503


def test_referential_picks_survive_into_replay_history(tmp_path):
    """Turn 1's grounded picks must be stored with the assistant reply so a
    later 'compare these three' can map names to exact ids. Regression: a
    live model compared P01/P02/P03 after the user said 'these three' about
    P01/P09/P07, because replay history carried only prose (no ids) and it
    guessed ids in sequence."""
    import json

    from app.state.sqlite_store import SqliteStore

    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="search_products", arguments={
                "query": "wireless headphones under 10000", "top_k": 3})]),
        # no ids in the prose reply — exactly the failure mode
        LLMMessage(content="The best fits are SonicWave X5, EchoPods Lite, "
                            "and AudioNest Hush One.", tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    sid = c.post("/chat", json={"message": "headphones under 10k?"}).json()["session_id"]
    sess = SqliteStore(str(tmp_path / "t.db")).load(sid)
    stored = json.dumps(sess.messages)
    # the grounded picks ride in a separate USER-role context entry — never
    # inside assistant speech (models started echoing/forging the tag when it
    # lived in their own replayed words).
    assert "reuse these exact ids" in stored
    # every note id must be a real product with its real name, e.g. P01 = SonicWave...
    ctx = [m for m in sess.messages if "reuse these exact ids" in m.get("content", "")][0]
    assert ctx["role"] == "user"
    listed = ctx["content"].rsplit(": ", 1)[1].rstrip("]")
    assert listed, "note must not be empty"
    for chunk in listed.split("; "):
        pid, name = chunk.split(" = ", 1)
        assert pid.startswith("P") and name.strip(), chunk
    assert "P01 = SonicWave X5 Wireless Headphones" in listed
    # ...and assistant speech in history stays clean reply text
    assert "[Products shown above" not in json.dumps(
        [m for m in sess.messages if m["role"] == "assistant"])


def test_chat_with_fake_llm(tmp_path):
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="search_products", arguments={"query": "headphones", "top_k": 2})]),
        LLMMessage(content="Pick P01 at 8499.", tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    body = c.post("/chat", json={"message": "headphones?"}).json()
    assert body["session_id"].startswith("S-")
    assert "P01" in body["reply"]
    assert body["status"] == "ok"


def test_full_order_flow(tmp_path):
    c = TestClient(_app(tmp_path))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    prep = c.post("/checkout/prepare", json={"session_id": sid}).json()
    assert prep["status"] == "AWAITING_CONFIRMATION"
    assert len(prep["confirmation_token"]) == 16
    assert prep["cart_snapshot"]["items"][0]["name"] == "SonicWave X5 Wireless Headphones"  # catalog join on the slip
    assert c.post("/orders", json={"session_id": sid, "idempotency_key": "k1"}).status_code == 400
    token = prep["confirmation_token"]
    conf = c.post("/checkout/confirm", json={"session_id": sid, "confirmation_token": token}).json()
    assert conf["status"] == "CONFIRMED"
    o1 = c.post("/orders", json={"session_id": sid, "idempotency_key": "k1"}).json()
    assert o1["status"] == "COMPLETED"
    assert o1["order_id"].startswith("O-")
    assert o1["items"][0]["name"] == "SonicWave X5 Wireless Headphones"  # receipt lines carry names
    o2 = c.post("/orders", json={"session_id": sid, "idempotency_key": "k1"}).json()
    assert o2["order_id"] == o1["order_id"]
    assert c.get(f"/orders/{o1['order_id']}").json()["order_id"] == o1["order_id"]
    cart = c.get("/cart", params={"session_id": sid}).json()
    assert cart["items"] == []  # purchased lines leave the trolley
    o_get = c.get(f"/orders/{o1['order_id']}").json()
    assert o_get["items"][0]["name"] == "SonicWave X5 Wireless Headphones"


class _RecordingFake(FakeLLM):
    """FakeLLM that records every message list it is handed."""

    def __init__(self, script):
        super().__init__(script)
        self.seen_messages = []

    def complete(self, messages, tools):
        self.seen_messages.append(list(messages))
        return super().complete(messages, tools)


def test_chat_history_carries_across_turns(tmp_path):
    rec = _RecordingFake([
        LLMMessage(content="", tool_calls=[
            ToolCall(name="search_products", arguments={"query": "headphones", "top_k": 2})]),
        LLMMessage(content="P01 it is.", tool_calls=[]),
        LLMMessage(content="Second reply ok.", tool_calls=[]),
    ])
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db")), llm=rec))
    sid = c.post("/chat", json={"message": "find me headphones"}).json()["session_id"]
    c.post("/chat", json={"session_id": sid, "message": "and add it"})
    second_turn = rec.seen_messages[2]  # turn 1 used two completes (tool + answer)
    user_bits = [m.get("content") for m in second_turn if m.get("role") == "user"]
    assistant_bits = [m.get("content") for m in second_turn if m.get("role") == "assistant"]
    assert "find me headphones" in user_bits
    assert "and add it" in user_bits
    # turn-1 prose replays verbatim (with the grounded picks note appended)
    assert any(b.startswith("P01 it is.") for b in assistant_bits)


def test_forged_picks_tag_is_stripped_from_reply(tmp_path):
    """The [Products shown above: ...] tag is server-owned. A live model
    forged one (invented ids) after learning the format from replayed
    history — it must never render in the reply or replay as model speech."""
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="search_products", arguments={"query": "headphones", "top_k": 2})]),
        LLMMessage(content="P01 is the pick.\n[Products shown above: P99 = Forged Laptop]",
                   tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    body = c.post("/chat", json={"message": "best headphones?"}).json()
    assert "[Products shown above" not in body["reply"]
    assert "P01 is the pick." in body["reply"]
    # cards come only from real retrieved ids — the forged P99 never appears
    assert body["products"], "expected product cards"
    assert all(p["product_id"].startswith("P") for p in body["products"])
    assert not any(p["product_id"] == "P99" for p in body["products"])


def test_zero_tool_product_answer_is_retried_with_search(tmp_path):
    """Anti-fabrication guard: a catalog/cart product ask answered with ZERO
    tool calls is ungrounded by construction (live: 'show me laptops under
    30000' produced invented SKUs under ids that belong to other products).
    The turn is retried once with a search-first nudge; the grounded retry
    wins. The invented first answer never lands in history."""
    import json

    from app.state.sqlite_store import SqliteStore

    script = [
        # first attempt: confident fabrication, no tools
        LLMMessage(content="Here are laptops: ValueBook Pro (P02) at \u20b927,999, "
                            "ProBook Air (P15) at \u20b928,999", tool_calls=[]),
        # nudged retry: searches properly
        LLMMessage(content="", tool_calls=[
            ToolCall(name="search_products", arguments={
                "query": "laptop", "top_k": 5, "filters": {"max_price": 30000}})]),
        LLMMessage(content="CompuPro Budget 14 Laptop (P22) at \u20b929,990 is the "
                            "only laptop under \u20b930,000.", tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    body = c.post("/chat", json={"message": "show me laptops under 30000"}).json()
    sid = body["session_id"]
    assert "search_products" in body["tools"]
    assert "P22" in body["reply"]
    assert "ValueBook" not in body["reply"]  # the invented answer lost
    sess = SqliteStore(str(tmp_path / "t.db")).load(sid)
    stored = json.dumps(sess.messages)
    assert "ValueBook" not in stored  # fabricated turn never stored
    assert "P22" in stored


def test_zero_tool_twice_falls_back_deterministically(tmp_path):
    """If the model refuses to search even after the nudge, the reply is a
    deterministic fallback — never the model's ungrounded text."""
    script = [
        LLMMessage(content="Here are laptops: invented one (P02), invented two (P15)",
                   tool_calls=[]),
        LLMMessage(content="Same fabrication again.", tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    body = c.post("/chat", json={"message": "show me laptops under 30000"}).json()
    assert "grounded answer" in body["reply"]
    assert "invented" not in body["reply"]
    assert body["tools"] == [] and body["products"] == []


def test_error_paths(tmp_path):
    c = TestClient(_app(tmp_path))
    assert c.get("/products/PZZ").status_code == 404
    assert c.post("/cart/items", json={"product_id": "PZZ", "quantity": 1}).status_code == 400
    assert c.get("/cart", params={"session_id": "S-nope"}).status_code == 404
    assert c.get("/orders/O-nope").status_code == 404


def test_double_prepare_does_not_rotate_slip(tmp_path):
    c = TestClient(_app(tmp_path))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    p1 = c.post("/checkout/prepare", json={"session_id": sid}).json()
    p2 = c.post("/checkout/prepare", json={"session_id": sid}).json()
    assert p1["checkout_id"] == p2["checkout_id"]
    assert p1["confirmation_token"] == p2["confirmation_token"]
    assert p1["status"] == "AWAITING_CONFIRMATION"
    # a changed trolley still mints a fresh slip
    c.patch("/cart/items/P01", json={"session_id": sid, "quantity": 2}).json()
    p3 = c.post("/checkout/prepare", json={"session_id": sid}).json()
    assert p3["checkout_id"] != p1["checkout_id"]


def test_chat_confirm_intent_is_short_circuited(tmp_path):
    """'confirm the order' in chat must never reach the LLM (an empty FakeLLM
    script would 502 on any call). A live model once *narrated* an order
    confirmation with zero tool calls while the slip sat AWAITING — this gate
    makes that impossible. The slip survives intact; the real gate still
    works afterwards."""
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db")),
                              llm=FakeLLM([])))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    p1 = c.post("/checkout/prepare", json={"session_id": sid}).json()
    r = c.post("/chat", json={"session_id": sid, "message": "confirm the order"})
    assert r.status_code == 200
    body = r.json()
    assert "I confirm this order" in body["reply"]
    assert body["tools"] == [] and body["role"] == "cart"
    assert "🎉" not in body["reply"] and "Order ID" not in body["reply"]
    p2 = c.get("/checkout", params={"session_id": sid}).json()
    assert p2["checkout_id"] == p1["checkout_id"]  # slip not rotated
    assert p2["confirmation_token"] == p1["confirmation_token"]
    assert p2["status"] == "AWAITING_CONFIRMATION"  # nothing was confirmed
    conf = c.post("/checkout/confirm", json={"session_id": sid,
                                             "confirmation_token": p1["confirmation_token"]}).json()
    assert conf["status"] == "CONFIRMED"  # real gate still works


def test_chat_confirm_intent_variants_are_gated(tmp_path):
    """The awaiting-slip gate covers the phrasings shoppers actually use —
    not just the literal 'confirm the order'."""
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db")),
                              llm=FakeLLM([])))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    c.post("/checkout/prepare", json={"session_id": sid})
    for msg in ["place the order", "yes, proceed to checkout",
                "go ahead and order it", "buy it now", "i want to confirm",
                "complete the checkout", "checkout please"]:
        r = c.post("/chat", json={"session_id": sid, "message": msg})
        assert r.status_code == 200, msg
        body = r.json()
        assert body["tools"] == [], msg  # LLM never ran
        assert "I confirm this order" in body["reply"], msg
    # ...but ordinary chat is NOT gated: with an empty script the LLM call
    # surfaces as a 502, proving the product question reached the model.
    r2 = c.post("/chat", json={
        "session_id": sid, "message": "what is the battery life of P01?"})
    assert r2.status_code == 502


def test_place_order_without_slip_gets_deterministic_reply(tmp_path):
    """With nothing prepared, 'place my order' must not reach the LLM either —
    the reply says to prepare first. No model can invent an O- order id."""
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db")),
                              llm=FakeLLM([])))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    for msg in ["place my order", "confirm the order now", "complete the purchase"]:
        r = c.post("/chat", json={"session_id": sid, "message": msg})
        assert r.status_code == 200, msg
        body = r.json()
        assert body["tools"] == [], msg
        assert "Prepare checkout" in body["reply"], msg
        assert "O-" not in body["reply"], msg


def test_chat_cancel_checkout_voids_slip_but_keeps_trolley(tmp_path):
    """'cancel the checkout' must never reach the LLM (empty FakeLLM would
    502) and must void the slip WITHOUT emptying the cart. Regression: a live
    model answered 'cancel the checkout' with clear_cart, destroying the
    trolley the shopper only wanted to stop checking out."""
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db")),
                              llm=FakeLLM([])))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    p1 = c.post("/checkout/prepare", json={"session_id": sid}).json()
    assert p1["status"] == "AWAITING_CONFIRMATION"
    for msg in ["cancel the checkout", "cancel", "void the slip", "abort this checkout",
                # regression: the confirm gate's "alright … checkout" pattern
                # once swallowed this and answered with the confirm text
                "alright, cancel the checkout and clear everything from the cart"]:
        r = c.post("/chat", json={"session_id": sid, "message": msg})
        assert r.status_code == 200, msg
        body = r.json()
        assert body["tools"] == [], msg  # LLM never ran, no clear_cart
        assert "trolley is untouched" in body["reply"], msg
        assert "can't confirm an order from chat" not in body["reply"], msg
        # slip voided each time, cart preserved through every repeat
        cart = c.get("/cart", params={"session_id": sid}).json()
        assert [(i["product_id"], i["quantity"]) for i in cart["items"]] == [("P01", 1)], msg
    slip = c.get("/checkout", params={"session_id": sid}).json()
    assert slip["status"] == "REJECTED"
    assert slip["confirmation_token"] == ""
    # the trolley is reusable: a fresh prepare mints a new slip for the SAME cart
    p2 = c.post("/checkout/prepare", json={"session_id": sid}).json()
    assert p2["status"] == "AWAITING_CONFIRMATION"
    assert p2["checkout_id"] != p1["checkout_id"]


def test_chat_cancel_with_no_slip_is_deterministic(tmp_path):
    """'cancel the checkout' with nothing prepared must not reach the LLM and
    must not claim anything was cancelled or emptied."""
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db")),
                              llm=FakeLLM([])))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    r = c.post("/chat", json={"session_id": sid, "message": "cancel the checkout"})
    assert r.status_code == 200
    body = r.json()
    assert body["tools"] == []
    assert "There's no checkout to cancel" in body["reply"]
    cart = c.get("/cart", params={"session_id": sid}).json()
    assert [(i["product_id"], i["quantity"]) for i in cart["items"]] == [("P01", 1)]


def test_chat_cancel_question_answers_without_voiding(tmp_path):
    """'can I cancel?' is a question — answer deterministically but do NOT
    void the slip (the shopper asked whether, not to do it)."""
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db")),
                              llm=FakeLLM([])))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    c.post("/checkout/prepare", json={"session_id": sid})
    for msg in ["can I cancel the checkout?", "can I cancel?", "how do I cancel?"]:
        r = c.post("/chat", json={"session_id": sid, "message": msg})
        assert r.status_code == 200, msg
        body = r.json()
        assert body["tools"] == [], msg
        assert "Cancel checkout" in body["reply"], msg
        slip = c.get("/checkout", params={"session_id": sid}).json()
        assert slip["status"] == "AWAITING_CONFIRMATION", msg  # not voided by a question


def test_first_time_proceed_to_checkout_still_reaches_llm(tmp_path):
    """Gate 2 must not over-reach: with NO slip standing, 'proceed to
    checkout' is a legitimate prepare request and must reach the model."""
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="prepare_checkout", arguments={})]),
        LLMMessage(content="Your checkout is ready — press I confirm this order on the slip.",
                   tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    r = c.post("/chat", json={"session_id": sid, "message": "yes, proceed to checkout"}).json()
    assert "prepare_checkout" in r["tools"]  # the model ran and prepared


def test_pasting_confirmation_code_in_chat_is_short_circuited(tmp_path):
    """Pasting the slip code into chat must never reach the LLM (an empty
    FakeLLM script would 502 on any call) and must not change server state.
    The shopper can still confirm through the real gate afterwards."""
    import json

    from app.state.sqlite_store import SqliteStore

    # empty script: any LLM call would raise and surface as a 502, so a 200
    # with the fixed reply proves the code never reached the model
    c = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db")),
                              llm=FakeLLM([])))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    token = c.post("/checkout/prepare", json={"session_id": sid}).json()["confirmation_token"]
    r = c.post("/chat", json={"session_id": sid,
                               "message": f"{token} here's my confirmation code"})
    assert r.status_code == 200
    body = r.json()
    assert "I confirm this order" in body["reply"]
    assert body["role"] == "cart" and body["tools"] == []
    assert token not in body["reply"]
    still = c.get("/checkout", params={"session_id": sid}).json()
    assert still["status"] == "AWAITING_CONFIRMATION"
    assert still["confirmation_token"] == token
    # the code never lands in stored session history
    sess = SqliteStore(str(tmp_path / "t.db")).load(sid)
    assert token not in json.dumps(sess.messages)
    # ...and the shopper can still confirm through the real gate afterwards
    conf = c.post("/checkout/confirm", json={"session_id": sid,
                                             "confirmation_token": token}).json()
    assert conf["status"] == "CONFIRMED"


def test_delete_cart_clears_all_and_voids_awaiting_slip(tmp_path):
    c = TestClient(_app(tmp_path))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 2}).json()["session_id"]
    c.post("/cart/items", json={"session_id": sid, "product_id": "P03", "quantity": 1})
    prep = c.post("/checkout/prepare", json={"session_id": sid}).json()
    assert prep["status"] == "AWAITING_CONFIRMATION"
    cleared = c.delete("/cart", params={"session_id": sid}).json()
    assert cleared["items"] == [] and cleared["totals"]["total"] == 0.0
    # the awaiting slip was dropped with the cart that no longer matches
    assert c.get("/checkout", params={"session_id": sid}).status_code == 400
    assert c.post("/checkout/confirm", json={"session_id": sid,
                                              "confirmation_token": prep["confirmation_token"]}).status_code == 400
    # and the trolley stays usable afterwards
    c.post("/cart/items", json={"session_id": sid, "product_id": "P05", "quantity": 1})
    prep2 = c.post("/checkout/prepare", json={"session_id": sid}).json()
    assert prep2["status"] == "AWAITING_CONFIRMATION"
    assert prep2["checkout_id"] != prep["checkout_id"]


def test_update_and_remove(tmp_path):
    c = TestClient(_app(tmp_path))
    sid = c.post("/cart/items", json={"product_id": "P03", "quantity": 1}).json()["session_id"]
    up = c.patch("/cart/items/P03", json={"session_id": sid, "quantity": 2}).json()
    assert up["cart"]["items"][0]["quantity"] == 2
    rm = c.delete("/cart/items/P03", params={"session_id": sid}).json()
    assert rm["cart"]["items"] == []
