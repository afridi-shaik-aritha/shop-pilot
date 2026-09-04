# Shopper-journey E2E: query -> pick -> cart -> prepare -> confirm -> place.
# One continuous run per product, plus full-lifecycle CRUD journeys.
from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import Settings

JOURNEYS = [
    ("wireless headphones battery", "P01"),
    ("bass headphones", "P02"),
    ("wired earphones", "P03"),
    ("bluetooth speaker picnics", "P04"),
    ("smartwatch heart rate", "P05"),
    ("refurbished", "P06"),
]


def _client(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "t.db"))))


def _journey_order(c, pid, qty=1, key="k-journey"):
    """Drive query -> order for pid; return (order, prep, stock_before)."""
    sid = c.post("/sessions").json()["session_id"]
    stock_before = c.get(f"/products/{pid}").json()["stock"]
    cart = c.post("/cart/items",
                  json={"session_id": sid, "product_id": pid, "quantity": qty}).json()
    assert cart["items"] and cart["totals"]["total"] > 0
    prep = c.post("/checkout/prepare", json={"session_id": sid}).json()
    assert prep["status"] == "AWAITING_CONFIRMATION"
    assert prep["cart_snapshot"]["items"][0]["name"] not in ("", None)
    conf = c.post("/checkout/confirm",
                  json={"session_id": sid, "confirmation_token": prep["confirmation_token"]}).json()
    assert conf["status"] == "CONFIRMED"
    order = c.post("/orders", json={"session_id": sid, "idempotency_key": key}).json()
    assert order["status"] == "COMPLETED"
    assert order["total"] == prep["total"] == cart["totals"]["total"]
    return order, prep, stock_before, sid


def test_journey_query_to_order(tmp_path):
    for query, pid in JOURNEYS:
        if pid == "P06":
            continue  # out-of-stock path has its own journey below
        c = _client(tmp_path / pid)
        hits = c.post("/search", json={"query": query, "top_k": 5}).json()["products"]
        assert pid in [h["product_id"] for h in hits], (query, pid)
        detail = c.get(f"/products/{pid}").json()
        assert detail["price"] > 0 and detail["stock"] > 0
        order, prep, before, sid = _journey_order(c, pid, key=f"k-{pid}")
        assert c.get(f"/products/{pid}").json()["stock"] == before - 1
        assert c.get("/cart", params={"session_id": sid}).json()["items"] == []
        fetched = c.get(f"/orders/{order['order_id']}").json()
        assert fetched["items"][0]["name"] == detail["name"]
        replay = c.post("/orders", json={"session_id": sid, "idempotency_key": f"k-{pid}"}).json()
        assert replay["order_id"] == order["order_id"]
        assert c.get(f"/products/{pid}").json()["stock"] == before - 1


def test_journey_out_of_stock_query_to_blocked_order(tmp_path):
    c = _client(tmp_path)
    hits = c.post("/search", json={"query": "refurbished", "top_k": 5}).json()["products"]
    assert "P06" in [h["product_id"] for h in hits]
    sid = c.post("/sessions").json()["session_id"]
    c.post("/cart/items", json={"session_id": sid, "product_id": "P06", "quantity": 1})
    prep = c.post("/checkout/prepare", json={"session_id": sid}).json()
    c.post("/checkout/confirm",
           json={"session_id": sid, "confirmation_token": prep["confirmation_token"]})
    assert c.post("/orders", json={"session_id": sid, "idempotency_key": "k-p06"}).status_code == 400
    assert c.get("/products/P06").json()["stock"] == 0


def test_journey_cancel_then_reorder(tmp_path):
    c = _client(tmp_path)
    sid = c.post("/sessions").json()["session_id"]
    c.post("/cart/items", json={"session_id": sid, "product_id": "P03", "quantity": 1})
    c.post("/checkout/prepare", json={"session_id": sid})
    cancelled = c.post("/checkout/cancel", json={"session_id": sid}).json()
    assert cancelled["status"] == "REJECTED"
    # cart survives cancel; reorder cleanly on a fresh session
    assert len(c.get("/cart", params={"session_id": sid}).json()["items"]) == 1
    order, _, before, _ = _journey_order(c, "P03", key="k-reorder")
    assert order["status"] == "COMPLETED"
    assert c.get("/products/P03").json()["stock"] == before - 1


def test_journey_crud_product_lifecycle(tmp_path):
    c = _client(tmp_path)
    new = {"product_id": "P91", "name": "Journey Widget", "brand": "J", "category": "widgets",
           "description": "a widget for journey testing", "price": 500.0, "rating": 4.0,
           "review_count": 0, "stock": 3}
    assert c.post("/products", json=new).status_code == 201
    hits = c.post("/search", json={"query": "journey widget", "top_k": 5}).json()["products"]
    assert "P91" in [h["product_id"] for h in hits]
    # order the new product end to end (500 + 49 ship + 18% = 647.82)
    sid = c.post("/sessions").json()["session_id"]
    c.post("/cart/items", json={"session_id": sid, "product_id": "P91", "quantity": 1})
    prep = c.post("/checkout/prepare", json={"session_id": sid}).json()
    assert prep["total"] == 647.82
    c.post("/checkout/confirm",
           json={"session_id": sid, "confirmation_token": prep["confirmation_token"]})
    order = c.post("/orders", json={"session_id": sid, "idempotency_key": "k-p91"}).json()
    assert order["status"] == "COMPLETED" and order["total"] == 647.82
    assert c.get("/products/P91").json()["stock"] == 2
    # patch price -> new orders use it
    assert c.patch("/products/P91", json={"price": 1000.0}).json()["price"] == 1000.0
    assert c.get("/products/P91").json()["price"] == 1000.0
    # delete -> gone from detail and search
    assert c.delete("/products/P91").status_code == 200
    assert c.get("/products/P91").status_code == 404
    hits = c.post("/search", json={"query": "journey widget", "top_k": 5}).json()["products"]
    assert "P91" not in [h["product_id"] for h in hits]


def test_journey_crud_review_lifecycle(tmp_path):
    c = _client(tmp_path)
    body = {"review_id": "RX91", "rating": 5, "title": "journey review", "body": "holds up well"}
    assert c.post("/products/P01/reviews", json=body).status_code == 201
    reviews = c.get("/products/P01/reviews").json()["reviews"]
    assert any(r["review_id"] == "RX91" and r["kind"] == "review-quote" for r in reviews)
    assert c.delete("/reviews/RX91").status_code == 200
    reviews = c.get("/products/P01/reviews").json()["reviews"]
    assert all(r["review_id"] != "RX91" for r in reviews)
