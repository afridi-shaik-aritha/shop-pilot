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
    assert "P01 it is." in assistant_bits


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


def test_chat_confirm_request_cannot_rotate_slip(tmp_path):
    """Regression: a model answering 'confirm the order' by re-calling
    prepare_checkout must not mint a fresh slip or orphan the code the
    shopper sees on screen. The slip survives, still awaiting."""
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="prepare_checkout", arguments={})]),
        LLMMessage(content="Order C-x is ready, paste your code to confirm!", tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    sid = c.post("/cart/items", json={"product_id": "P01", "quantity": 1}).json()["session_id"]
    p1 = c.post("/checkout/prepare", json={"session_id": sid}).json()
    r = c.post("/chat", json={"session_id": sid, "message": "confirm the order"}).json()
    assert "prepare_checkout" in r["tools"]  # the model did misbehave
    p2 = c.get("/checkout", params={"session_id": sid}).json()
    assert p2["checkout_id"] == p1["checkout_id"]  # slip not rotated
    assert p2["confirmation_token"] == p1["confirmation_token"]
    assert p2["status"] == "AWAITING_CONFIRMATION"  # nothing was confirmed


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
