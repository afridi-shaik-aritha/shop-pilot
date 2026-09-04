# tests/test_grounding.py
from evaluation.grounding import grounding_ok, ids_in, numbers_in
from evaluation.response_eval import run_scenarios


def test_numbers_and_ids_extraction():
    assert "8499.0" in numbers_in("P01 costs 8499.0 INR")
    assert ids_in("P01 and P99") == ["P01", "P99"]


def test_grounding_ok_and_miss():
    trace = "{'product_id': 'P01', 'price': 8499.0}"
    ok, _ = grounding_ok("P01 costs 8499.0", trace)
    assert ok is True
    ok2, detail = grounding_ok("P01 costs 100.0", trace)
    assert ok2 is False
    assert detail["missing_numbers"] == ["100.0"]


def test_scenarios_report():
    rows = run_scenarios()
    by_name = {r["scenario"]: r["grounded"] for r in rows}
    assert by_name["grounded-answer"] is True
    assert by_name["hallucinated-price"] is False
