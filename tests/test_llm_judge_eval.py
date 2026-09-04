# tests/test_llm_judge_eval.py
import json

from app.llm import FakeLLM, LLMMessage
from evaluation.llm_judge_eval import judge_response, main, run_judge


def _fake(content: str) -> FakeLLM:
    return FakeLLM([LLMMessage(content=content, tool_calls=[])])


def test_judge_response_parses_json_verdict():
    verdict = {"faithful": True, "score": 4, "rationale": "Price matches trace."}
    llm = _fake(json.dumps(verdict))
    row = judge_response(llm, "P01 costs 8499.0", "{'price': 8499.0}")
    assert row["faithful"] is True
    assert row["score"] == 4
    assert "Price matches" in row["rationale"]


def test_judge_response_parses_line_format():
    llm = _fake("faithful: false\nscore: 1\nrationale: Number not in trace")
    row = judge_response(llm, "P01 costs 1.0", "{'price': 8499.0}")
    assert row["faithful"] is False
    assert row["score"] == 1


def test_run_judge_covers_scenarios():
    llm = FakeLLM(
        [
            LLMMessage(content=json.dumps({"faithful": True, "score": 5}), tool_calls=[]),
            LLMMessage(content=json.dumps({"faithful": False, "score": 1}), tool_calls=[]),
        ]
    )
    rows = run_judge(llm)
    assert [r["scenario"] for r in rows] == ["grounded-answer", "hallucinated-price"]
    assert rows[0]["faithful"] is True
    assert rows[1]["faithful"] is False


def test_main_without_llm_skips_and_exits_zero(capsys, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")  # never auto-connect from a local .env
    code = main(llm=None)
    out = capsys.readouterr().out
    assert code == 0
    assert "SKIPPED" in out.upper() or "skipped" in out
