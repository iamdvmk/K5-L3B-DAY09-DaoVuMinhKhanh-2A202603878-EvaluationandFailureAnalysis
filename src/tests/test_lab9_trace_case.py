"""Regression test from docs/trace_case.md: seeded_regression C-002@11 (FM-03 ticket_trust).

First wrong step: event 3 `model_override {"delay_days": 5}` -- the ticket's claim overrides the
DB fact (O-202 delivered, delay_days=2). The fixed shape must never emit it and must deny.
Run: python -m pytest -q -m student -o addopts= -k trace_case
"""
import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def investigate():
    from lab9.trace_case import investigate

    return investigate


def _kinds(trial):
    return [e.get("kind") for e in trial["events"]]


def test_lab9_trace_case_seeded_overrides_db_fact(investigate):
    t = investigate("seeded_regression", "C-002", 11)["trial"]
    kinds = _kinds(t)
    assert "model_override" in kinds
    first_bad = kinds.index("model_override")
    assert kinds[:first_bad] == ["handoff", "investigator"]      # everything before it was fine
    assert t["events"][first_bad]["payload"] == {"delay_days": 5}
    assert t["snapshot"]["refund_vnd"] == 20000                  # money moved on a denied claim


def test_lab9_trace_case_fixed_keeps_db_fact(investigate):
    case = investigate("fixed", "C-002", 11)
    t, label = case["trial"], case["label"]
    assert "model_override" not in _kinds(t)
    assert t["result"]["status"] == label["status"] == "denied"
    assert t["snapshot"]["refund_vnd"] == label["refund_vnd"] == 0
