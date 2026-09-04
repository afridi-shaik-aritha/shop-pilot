# tests/test_record_demo.py
from app.retrieval.embedder import LexicalEmbedder
from demo.record_demo import record_demo


def test_record_demo_completes_and_writes_transcript(tmp_path):
    out = tmp_path / "recording.md"
    result = record_demo(output_path=str(out), embedder=LexicalEmbedder())
    assert result["order"]["status"] == "COMPLETED"
    assert result["order"]["order_id"].startswith("O-")
    assert result["blocked_without_confirmation"] is True
    text = out.read_text(encoding="utf-8")
    assert "BLOCKED: order without confirmation refused." in text
    assert "COMPLETED for" in text
    for marker in ("bm25", "semantic", "hybrid", "CONFIRMATION_TOKEN="):
        assert marker in text
