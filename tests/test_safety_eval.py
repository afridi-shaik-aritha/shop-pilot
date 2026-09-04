# tests/test_safety_eval.py
from evaluation.safety_eval import run_all


def test_safety_suite_all_pass():
    results = run_all()
    assert len(results) == 16
    failed = [name for name, passed, _ in results if not passed]
    assert failed == []
