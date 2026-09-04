# tests/test_observe.py
from app.observe import TraceRecorder, redact
from app.state.sqlite_store import SqliteStore


def test_redact_nested_and_token_kept():
    payload = {
        "api_key": "sk-secret",
        "nested": {"Authorization": "Bearer x", "password": "pw"},
        "confirmation_token": "abc123",
        "total": 10.0,
    }
    out = redact(payload)
    assert out["api_key"] == "***"
    assert out["nested"] == {"Authorization": "***", "password": "***"}
    assert out["confirmation_token"] == "***"
    assert out["total"] == 10.0


def test_redact_lists():
    out = redact([{"secret_sauce": 1}, "plain"])
    assert out == [{"secret_sauce": "***"}, "plain"]


def test_record_round_trip(tmp_path):
    db = SqliteStore(str(tmp_path / "t.db"))
    rec = TraceRecorder(db)
    run_id = rec.record("chat", {"session_id": "S-1", "api_key": "sk-x"})
    rows = db.list_traces(kind="chat")
    assert len(run_id) == 12
    assert rows[0]["run_id"] == run_id
    assert rows[0]["payload"]["api_key"] == "***"
    assert rows[0]["payload"]["session_id"] == "S-1"
    db.close()
