# Full end-to-end matrix: every product, every gate, every role.
#
# Each test boots the real FastAPI app on an isolated tmp DB (seeded from
# JSON), so stock mutations never leak between tests.
from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import Settings
from app.llm import FakeLLM, LLMMessage, ToolCall

PRODUCTS = ["P01", "P02", "P03", "P04", "P05", "P06"]
OUT_OF_STOCK = {"P06"}


def _client(tmp_path, script=None):
    return TestClient(
        create_app(Settings(db_path=str(tmp_path / "t.db")),
                   llm=FakeLLM(script) if script is not None else None)
    )


def _session(c):
    return c.post("/sessions").json()["session_id"]


def _order_flow(c, sid, pid, qty=1, key="k-e2e"):
    c.post("/cart/items", json={"session_id": sid, "product_id": pid, "quantity": qty})
    prep = c.post("/checkout/prepare", json={"session_id": sid}).json()
    c.post("/checkout/confirm",
           json={"session_id": sid, "confirmation_token": prep["confirmation_token"]})
    return c.post("/orders", json={"session_id": sid, "idempotency_key": key}).json()


# ---------- catalog: every product ----------

def test_e2e_product_detail_all(tmp_path):
    c = _client(tmp_path)
    for pid in PRODUCTS:
        r = c.get(f"/products/{pid}")
        assert r.status_code == 200, pid
        body = r.json()
        for field in ("product_id", "name", "brand", "category", "description",
                      "price", "rating", "review_count", "availability", "stock"):
            assert field in body, (pid, field)
    assert c.get("/products/PZZ").status_code == 404


def test_e2e_product_list_and_search_all(tmp_path):
    c = _client(tmp_path)
    ids = {p["product_id"] for p in c.get("/products").json()["products"]}
    assert set(PRODUCTS) <= ids
    for pid, category in [("P01", "wireless headphones"), ("P04", "bluetooth speaker"),
                          ("P05", "smartwatch"), ("P03", "wired earphones")]:
        hits = c.post("/search", json={"query": category, "top_k": 6}).json()["products"]
        assert pid in [h["product_id"] for h in hits], category
        for h in hits:  # every card carries display fields
            for field in ("category", "brand", "availability", "stock", "review_count"):
                assert field in h, field


def test_e2e_reviews_all(tmp_path):
    c = _client(tmp_path)
    for pid in PRODUCTS:
        r = c.get(f"/products/{pid}/reviews").json()
        assert isinstance(r["reviews"], list), pid
    p05 = c.get("/products/P05/reviews").json()["reviews"]
    assert len(p05) == 2 and all(r["kind"] == "review-quote" for r in p05)
    assert c.get("/products/PZZ/reviews").json() == {"reviews": []}


def test_e2e_cart_ops_all(tmp_path):
    c = _client(tmp_path)
    sid = _session(c)
    for pid in PRODUCTS:
        r = c.post("/cart/items", json={"session_id": sid, "product_id": pid, "quantity": 1})
        assert r.status_code == 200, pid
        assert r.json()["items"][-1]["name"] not in ("", None)
    cart = c.get("/cart", params={"session_id": sid}).json()
    assert len(cart["items"]) == len(PRODUCTS)
    up = c.patch("/cart/items/P01", json={"session_id": sid, "quantity": 3}).json()
    assert up["cart"]["items"][0]["quantity"] == 3 or any(
        i["product_id"] == "P01" and i["quantity"] == 3 for i in up["cart"]["items"])
    rm = c.delete("/cart/items/P01", params={"session_id": sid}).json()
    assert all(i["product_id"] != "P01" for i in rm["cart"]["items"])
    assert c.post("/cart/items", json={"session_id": sid, "product_id": "PZZ", "quantity": 1}).status_code == 400
    assert c.post("/cart/items", json={"session_id": sid, "product_id": "P01", "quantity": 0}).status_code in (400, 422)


# ---------- orders: every product ----------

def test_e2e_order_flow_in_stock(tmp_path):
    for pid in [p for p in PRODUCTS if p not in OUT_OF_STOCK]:
        c = _client(tmp_path / pid)
        sid = _session(c)
        before = c.get(f"/products/{pid}").json()["stock"]
        order = _order_flow(c, sid, pid, key=f"k-{pid}")
        assert order["status"] == "COMPLETED", pid
        assert order["items"][0]["name"] not in ("", None)
        assert c.get(f"/products/{pid}").json()["stock"] == before - 1, pid
        assert c.get("/cart", params={"session_id": sid}).json()["items"] == []
        # idempotent replay: same order, no second decrement
        again = c.post("/orders", json={"session_id": sid, "idempotency_key": f"k-{pid}"}).json()
        assert again["order_id"] == order["order_id"]
        assert c.get(f"/products/{pid}").json()["stock"] == before - 1


def test_e2e_out_of_stock_blocked(tmp_path):
    c = _client(tmp_path)
    sid = _session(c)
    c.post("/cart/items", json={"session_id": sid, "product_id": "P06", "quantity": 1})
    prep = c.post("/checkout/prepare", json={"session_id": sid}).json()
    c.post("/checkout/confirm",
           json={"session_id": sid, "confirmation_token": prep["confirmation_token"]})
    assert c.post("/orders", json={"session_id": sid, "idempotency_key": "k-oos"}).status_code == 400
    assert c.get("/products/P06").json()["stock"] == 0


def test_e2e_oversell_blocked(tmp_path):
    c = _client(tmp_path)
    sid = _session(c)
    stock = c.get("/products/P02").json()["stock"]  # 17 in seed
    c.post("/cart/items", json={"session_id": sid, "product_id": "P02", "quantity": stock + 1})
    prep = c.post("/checkout/prepare", json={"session_id": sid}).json()
    c.post("/checkout/confirm",
           json={"session_id": sid, "confirmation_token": prep["confirmation_token"]})
    assert c.post("/orders", json={"session_id": sid, "idempotency_key": "k-over"}).status_code == 400
    assert c.get("/products/P02").json()["stock"] == stock


# ---------- money math ----------

def test_e2e_money_math(tmp_path):
    c = _client(tmp_path)
    sid = _session(c)
    c.post("/cart/items", json={"session_id": sid, "product_id": "P03", "quantity": 1})
    totals = c.get("/cart", params={"session_id": sid}).json()["totals"]
    assert totals == {"subtotal": 999.0, "shipping": 49.0, "tax": 188.64, "total": 1236.64}
    sid2 = _session(c)
    c.post("/cart/items", json={"session_id": sid2, "product_id": "P01", "quantity": 1})
    totals2 = c.get("/cart", params={"session_id": sid2}).json()["totals"]
    assert totals2 == {"subtotal": 8499.0, "shipping": 0.0, "tax": 1529.82, "total": 10028.82}


# ---------- confirmation gates ----------

def test_e2e_gates(tmp_path):
    c = _client(tmp_path)
    sid = _session(c)
    assert c.post("/checkout/prepare", json={"session_id": sid}).status_code == 400  # empty cart
    c.post("/cart/items", json={"session_id": sid, "product_id": "P01", "quantity": 1})
    assert c.post("/orders", json={"session_id": sid, "idempotency_key": "k-g"}).status_code == 400  # unconfirmed
    prep = c.post("/checkout/prepare", json={"session_id": sid}).json()
    assert len(prep["confirmation_token"]) >= 16
    assert c.post("/checkout/confirm",
                  json={"session_id": sid, "confirmation_token": "wrong"}).status_code == 400
    token = prep["confirmation_token"]
    assert c.post("/checkout/confirm",
                  json={"session_id": sid, "confirmation_token": token}).json()["status"] == "CONFIRMED"
    assert c.post("/checkout/confirm",
                  json={"session_id": sid, "confirmation_token": token}).status_code == 400  # double confirm
    order = c.post("/orders", json={"session_id": sid, "idempotency_key": "k-g"}).json()
    assert order["status"] == "COMPLETED"
    assert c.post("/checkout/cancel", json={"session_id": sid}).status_code == 400  # cancel after complete
    assert c.get(f"/orders/{order['order_id']}").json()["order_id"] == order["order_id"]
    assert c.get("/orders/O-nope").status_code == 404


def test_e2e_idempotency_isolated_per_session(tmp_path):
    c = _client(tmp_path)
    s1, s2 = _session(c), _session(c)
    o1 = _order_flow(c, s1, "P03", key="shared")
    o2 = _order_flow(c, s2, "P03", key="shared")
    assert o1["order_id"] != o2["order_id"]


def test_e2e_sessions(tmp_path):
    c = _client(tmp_path)
    assert c.get("/cart").status_code == 400  # sid required, no junk minting
    assert c.get("/cart", params={"session_id": "S-deadbeef1234"}).status_code == 404
    sid = _session(c)
    assert sid.startswith("S-")
    # session survives app "restart" (same db file)
    c2 = TestClient(create_app(Settings(db_path=str(tmp_path / "t.db"))))
    assert c2.get("/cart", params={"session_id": sid}).status_code == 200


# ---------- chat roles ----------

def _chat_client(tmp_path, script):
    return _client(tmp_path, script)


def test_e2e_chat_policy(tmp_path):
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="search_policy", arguments={"query": "return policy"})]),
        LLMMessage(content="POL-RETURN covers that.", tool_calls=[]),
    ]
    body = _chat_client(tmp_path, script).post(
        "/chat", json={"message": "what is your return policy?"}).json()
    assert body["role"] == "policy" and body["status"] == "ok"
    assert "POL-RETURN" in body["reply"]


def test_e2e_chat_catalog_with_cards(tmp_path):
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="search_products", arguments={"query": "smartwatch", "top_k": 2})]),
        LLMMessage(content="Take the PulseFit S2 (P05).", tool_calls=[]),
    ]
    body = _chat_client(tmp_path, script).post(
        "/chat", json={"message": "show me a smartwatch"}).json()
    assert body["role"] == "catalog"
    assert [p["product_id"] for p in body["products"]] == ["P05"]


def test_e2e_chat_cart_adds(tmp_path):
    script = [
        LLMMessage(content="", tool_calls=[
            ToolCall(name="add_to_cart", arguments={"product_id": "P04", "quantity": 1})]),
        LLMMessage(content="Added the speaker.", tool_calls=[]),
    ]
    c = _chat_client(tmp_path, script)
    body = c.post("/chat", json={"message": "add the bluetooth speaker to my cart"}).json()
    assert body["role"] == "cart" and body["status"] == "ok"
    cart = c.get("/cart", params={"session_id": body["session_id"]}).json()
    assert any(i["product_id"] == "P04" for i in cart["items"])


def test_e2e_chat_needs_llm_and_maps_failures(tmp_path):
    c = _client(tmp_path)
    assert c.post("/chat", json={"message": "hi"}).status_code == 503
    c2 = _client(tmp_path / "x", script=[])  # exhausted script -> failed turn
    assert c2.post("/chat", json={"message": "hi"}).status_code == 502


# ---------- catalog CRUD ----------

def test_e2e_crud(tmp_path):
    c = _client(tmp_path)
    new = {"product_id": "P90", "name": "Test", "brand": "T", "category": "test",
           "description": "d", "price": 10.0, "rating": 4.0, "review_count": 0, "stock": 5}
    assert c.post("/products", json=new).status_code == 201
    assert c.patch("/products/P90", json={"price": 20.0, "stock": 7}).json()["price"] == 20.0
    hits = c.post("/search", json={"query": "Test", "top_k": 5}).json()["products"]
    assert "P90" in [h["product_id"] for h in hits]
    assert c.post("/products/P90/reviews",
                  json={"review_id": "RX90", "rating": 5, "title": "t", "body": "b"}).status_code == 201
    assert c.delete("/reviews/RX90").status_code == 200
    assert c.delete("/products/P90").status_code == 200
    assert c.get("/products/P90").status_code == 404
