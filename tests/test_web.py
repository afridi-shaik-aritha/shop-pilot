# tests/test_web.py
from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import Settings
from app.llm import FakeLLM, LLMMessage, ToolCall


def _app(tmp_path, script=None):
    return create_app(
        Settings(db_path=str(tmp_path / "t.db")), llm=FakeLLM(script) if script else None
    )


def test_root_serves_index_html(tmp_path):
    c = TestClient(_app(tmp_path))
    r = c.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'id="app"' in r.text


def test_static_assets_served(tmp_path):
    c = TestClient(_app(tmp_path))
    assert c.get("/static/app.js").status_code == 200
    assert c.get("/static/styles.css").status_code == 200


def test_product_reviews_endpoint(tmp_path):
    c = TestClient(_app(tmp_path))
    r = c.get("/products/P01/reviews").json()
    assert len(r["reviews"]) >= 1
    assert r["reviews"][0]["kind"] == "review-quote"
    assert c.get("/products/PZZ/reviews").json() == {"reviews": []}


def test_chat_response_includes_tool_trace(tmp_path):
    script = [
        LLMMessage(
            content="",
            tool_calls=[
                ToolCall(name="search_products", arguments={"query": "x", "top_k": 2})
            ],
        ),
        LLMMessage(content="done", tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    body = c.post("/chat", json={"message": "hi"}).json()
    assert body["tools"] == ["search_products"]
    assert body["status"] == "ok"


def test_chat_returns_products_seen_in_trace(tmp_path):
    script = [
        LLMMessage(
            content="",
            tool_calls=[
                ToolCall(name="search_products", arguments={"query": "smartwatch", "top_k": 2})
            ],
        ),
        LLMMessage(content="P05 it is.", tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    body = c.post("/chat", json={"message": "show me a smartwatch"}).json()
    cards = body.get("products", [])
    assert "P05" in [p["product_id"] for p in cards]
    for p in cards:
        for field in ("name", "price", "category", "brand", "availability",
                      "stock", "review_count"):
            assert field in p, f"card missing {field}"


def test_chat_cards_use_most_recent_product_result(tmp_path):
    script = [
        LLMMessage(
            content="",
            tool_calls=[
                ToolCall(name="search_products", arguments={"query": "speaker", "top_k": 5})
            ],
        ),
        LLMMessage(
            content="",
            tool_calls=[
                ToolCall(name="get_product", arguments={"product_id": "P04"})
            ],
        ),
        LLMMessage(content="ThunderBox it is.", tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    body = c.post("/chat", json={"message": "bluetooth speaker for picnics"}).json()
    assert [p["product_id"] for p in body["products"]] == ["P04"]


def test_chat_cards_narrow_to_products_named_in_reply(tmp_path):
    script = [
        LLMMessage(
            content="",
            tool_calls=[
                ToolCall(name="search_products", arguments={"query": "smartwatch", "top_k": 5})
            ],
        ),
        LLMMessage(content="Take the PulseFit S2 (P05).", tool_calls=[]),
    ]
    c = TestClient(_app(tmp_path, script))
    body = c.post("/chat", json={"message": "show me a smartwatch"}).json()
    assert [p["product_id"] for p in body["products"]] == ["P05"]
