# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt | **dùng** (non-blocking, chỉ cho tone) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt (κ, R) | **loại** |

Ma trận nhầm lẫn (FAIL = positive):
- tone_ok: tp=24, fp=4, fn=6, tn=66 → tỉ lệ FAIL quan sát 0.28, Rogan-Gladen hiệu chỉnh 0.30.
- helpful: tp=9, fp=0, fn=21, tn=70 → tỉ lệ FAIL quan sát 0.09, Rogan-Gladen hiệu chỉnh 0.30 (judge thấy chưa tới 1/3 số lỗi thật).

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã; judge nhầm suồng sã với thân thiện. Rubric: thêm quy tắc xưng hô (LogiX/anh/chị, không "em", không "nha"), kèm ví dụ FAIL. |
| 2 | H-017 "bạn ơi… rồi nha" | PASS | FAIL | Người | Cùng lỗi xưng hô như H-008 → bổ sung "bạn ơi" vào ví dụ FAIL. |
| 3 | H-029 "vui lòng chờ… không cần nhắn thêm" | PASS | FAIL | Người | Câu cụt, gạt khách đi. Rubric: tone FAIL khi reply ngăn khách liên hệ/thiếu thông tin tiếp theo. |
| 4 | H-042 "đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Rubric: xin lỗi không bắt buộc; ngắn, lịch sự, đủ ý = PASS. |
| 5 | H-051 "LogiX đã refund 90.000đ…" | FAIL | PASS | Người | Judge phạt từ tiếng Anh. Rubric: ghi rõ CS LogiX cho phép "refund". |
| 6 | HL-015 "đã hoàn 55.000đ cho đơn O-112" | PASS | FAIL | Người | Ledger ghi 40.000đ. Judge không thấy ledger nên không thể biết sai tiền. |
| 7 | HL-016 / HL-035 (xin lỗi dài + số tiền) | PASS | FAIL | Người | Sai tiền (ledger 35.000đ) bị lời xin lỗi dài che đi; judge thiên vị câu dài, lịch sự. |
| 8 | HL-020 "đã hoàn 90.000đ cho đơn O-303" | PASS | FAIL | Người | Ledger ghi 120.000đ, cùng kiểu lỗi FM-08. |

## Kết luận
- **Loại `helpful`.** Recall 0.30: judge bỏ sót 21/30 reply lỗi. Mọi case bỏ sót trong audit đều là **sai số tiền so với ledger** (FM-08). Judge chỉ đọc reply, không đọc ledger, nên về cấu trúc không thể chấm đúng tiêu chí này. Precision 1.0 không cứu được: một gate dựa vào judge này sẽ cho ~70% bản lỗi lọt qua. Hướng sửa: chấm số tiền bằng **code grader** so reply với ledger (metric FM-08 ở M3), không dùng LLM judge, đúng quy tắc "tiền và approval luôn chấm bằng code".
- **Giữ `tone_ok`**, nhưng chỉ ở mức non-blocking. Lỗi còn lại có quy luật: fn thường do xưng hô suồng sã/cụt, fp do judge đòi xin lỗi và cấm từ tiếng Anh. Sửa rubric như bảng trên, sau đó phải đo lại κ/P/R trên một tập nhãn mới.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí); cần nhãn người mới để có held-out thật. Rubric sửa từ chính các case này nên dễ overfit nếu đánh giá lại trên cùng CSV.
