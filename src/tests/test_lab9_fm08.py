"""M3: FM-08 misreport grader (reply amount vs ledger) on hand-built Trials."""
import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def graders():
    from lab9 import graders

    return graders


def _eval(graders, text, ledger):
    from pydantic_evals.evaluators import EvaluatorContext

    trial = {"snapshot": {"refund_vnd": ledger, "refund_count": int(ledger > 0)}, "unexpected_rows": 0,
             "blob": "", "events": [{"kind": "reply", "payload": {"text": text}}], "result": {},
             "lab8_pass": True, "lab8_reason": None}
    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output={"refund_vnd": ledger},
                           output=trial, duration=0.0, _span_tree=None, attributes={}, metrics={})
    return graders.ReplyMatchesLedger().evaluate(ctx).value


def test_lab9_fm08_amount_formats(graders):
    assert graders.reply_amounts("Dạ, LogiX đã hoàn 120.000đ cho đơn O-515.") == [120000]
    assert graders.reply_amounts("refund 35,000 VND, 3–5 ngày, đơn O-808") == [35000]


def test_lab9_fm08_reply_matches_ledger(graders):
    assert _eval(graders, "Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.", 20000) is True
    assert _eval(graders, "Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành.", 0) is True


def test_lab9_fm08_misreport_is_caught(graders):
    assert _eval(graders, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.", 20000) is False   # C-008 seeded
    assert _eval(graders, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-909.", 0) is False       # C-007 seeded
