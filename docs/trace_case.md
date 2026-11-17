# Trace case: từ trace tới quyết định sai đầu tiên

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case: `seeded_regression C-002@11` — FM-03 ticket_trust

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11` (run ID: xem `reports/eval_seeded_regression.json` → `run_id`) |
| Triệu chứng | Lab 8 grader FAIL `status resolved != denied`; `refund_amount_correct` FAIL (ledger 20.000đ, nhãn 0, refund_count 1 vs 0); `db_fact_kept` FAIL. Reply: "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." — reply khớp ledger nên lỗi không lộ ở câu chữ, chỉ lộ khi đọc ledger. |
| Bước sai đầu tiên | **Event 3 `model_override` `{"delay_days": 5}`** |
| Vì sao là bước *đầu tiên* | Event 1 `handoff`: đúng contract, đúng allowed_tools. Event 2 `investigator`: DB trả O-202 `status: delivered`, `delay_days: 2` — đúng sự thật, chưa có sai lệch. Từ event 3 trở đi mọi bước kế thừa con số 5 ngày từ ticket: event 4 quote 20.000đ theo SHIP-LATE-03 (cần ≥3 ngày), ledger ghi hoàn. |
| Failure mode | FM-03 ticket_trust (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11`: không có event `model_override`; event 3 quote `{"amount_vnd": 0, "reason": "no_entitlement"}`; reply "chưa đủ điều kiện hoàn"; status `denied`, ledger 0 — khớp nhãn. |
| Regression test | `tests/test_lab9_trace_case.py`: `test_lab9_trace_case_seeded_overrides_db_fact` (assert có `model_override` đúng sau `handoff, investigator`, payload `{"delay_days": 5}`, ledger 20.000) và `test_lab9_trace_case_fixed_keeps_db_fact` (không override, denied, ledger 0). Trên eval: grader `DbFactKept` + `RefundAmountCorrect` fail trên seeded_regression, pass trên fixed. |
| Chưa chắc chắn | Trace cho thấy model ghi đè `delay_days` nhưng không cho biết *vì sao* model tin ticket (prompt hay ngữ cảnh). Biến thể `quiet_override` (tin ticket nhưng không ghi event) sẽ qua `db_fact_kept`; khi đó chỉ `refund_amount_correct`/`pass_rate` bắt được. |

## Quy tắc
- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được.
