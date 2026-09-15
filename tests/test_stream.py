import json
from fastapi.testclient import TestClient

from app.api.routes import create_app
from app.config import Settings
from app.llm import FakeLLM, LLMMessage, ToolCall
from app.state.sqlite_store import SqliteStore


def _app(tmp_path, script=None):
    return create_app(
        Settings(db_path=str(tmp_path / "t.db")),
        llm=FakeLLM(script) if script else None,
    )


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            events.append(json.loads(payload))
    return events


def test_chat_stream_503_without_llm(tmp_path):
    c = TestClient(_app(tmp_path))
    assert c.post("/chat/stream", json={"message": "hi"}).status_code == 503


def test_chat_stream_short_circuit(tmp_path):
    c = TestClient(_app(tmp_path, [LLMMessage(content="hi")]))
    resp = c.post("/chat/stream", json={"message": "cancel checkout"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert "delta" in types
    assert "done" in types
    done_event = [e for e in events if e["type"] == "done"][0]
    assert "trolley is untouched" in done_event["reply"]
    assert done_event["status"] == "ok"


def test_chat_stream_with_tools(tmp_path):
    script = [
        LLMMessage(
            content="",
            tool_calls=[
                ToolCall(
                    name="search_products",
                    arguments={"query": "speaker", "top_k": 2},
                )
            ],
        ),
        LLMMessage(
            content="I found the ThunderBox speaker (P04) for you.",
            tool_calls=[],
        ),
    ]
    c = TestClient(_app(tmp_path, script))
    resp = c.post("/chat/stream", json={"message": "find me a speaker"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert "status" in types
    assert "tool_start" in types
    assert "tool_end" in types
    assert "delta" in types
    assert "done" in types

    # Reassembled deltas match reply
    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    done_event = [e for e in events if e["type"] == "done"][0]
    assert deltas == done_event["reply"]
    assert "P04" in done_event["reply"]
    assert done_event["products"]
    assert done_event["products"][0]["product_id"] == "P04"

    # Check persistence in sqlite
    sid = done_event["session_id"]
    sess = SqliteStore(str(tmp_path / "t.db")).load(sid)
    assert len(sess.messages) >= 2
    assert sess.messages[-1]["role"] == "user"  # picks context
    assert any(m["role"] == "assistant" for m in sess.messages)
