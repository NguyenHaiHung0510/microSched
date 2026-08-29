# 040 — Adaptive harness workflow cho issue cluster và review loop

> **Trạng thái:** ✅ CHỐT 2026-08-29 — owner yêu cầu áp dụng
> **Loại:** docs/policy · **Executor:** T1 · **Review:** adversarial docs review

## 1. Vấn đề

Task 036 cho thấy một issue cluster có thể bị dispatch như một UI task đơn dù thực tế chứa backend contract,
privacy/cache, concurrency/error handling, pagination và QA evidence. Target/report tiếp tục đổi trong lúc review,
finding được gửi nhỏ giọt và code/evidence/runtime gate bị trộn. Kết quả là verified progress trên time/token thấp,
dù nhiều finding riêng lẻ là bug thật.

Harness là moving target: model, nhu cầu, độ phức tạp và năng lực owner/T1 thay đổi. Vì vậy không khóa một số
review round chung hoặc một checklist khổng lồ cho mọi việc. Policy core phải ngắn và bền; task contract giữ
chi tiết phù hợp từng lane/model.

## 2. Quyết định

1. Raw issue cluster là intake, chưa phải dispatch. T1 triage, tư vấn/split và thương lượng task contract với
   owner trước first write.
2. Task contract chốt outcome, scope, dependency, delegation, quality axes, review posture, report depth/cadence,
   adaptive loop budget và stop/re-scope trigger.
3. T1 tổng hợp quality/reliability criteria trước repair đầu tiên; loại rõ axis không liên quan.
4. Review bind immutable target, hoàn tất declared axes và trả một consolidated finding ledger; không drip-feed
   một P1 mỗi vòng. Re-review đóng ledger + delta/regression.
5. Product correctness, evidence/report và runtime/device acceptance là gate riêng. Debt không tự thành
   regression; blocker phải được chốt trước hoặc làm lộ bug thật.
6. Không có universal round cap. T1 theo dõi marginal verified progress/time/token; khi loop giảm hiệu suất hoặc
   failure class lặp lại thì dừng để owner chọn ship/defer/split/rewrite/change executor.
7. Handoff thủ công hay tự động được đánh giá bằng hiệu quả, không bằng số lần. Nhiều handoff có thể hợp lý nếu
   mỗi lượt đóng được phần việc rõ; ít handoff vẫn tệ nếu chỉ vá cục bộ.

## 3. Không làm

- Không thêm service, schema JSON hay validator mới cho lifecycle này.
- Không hard-code model/provider hiện tại vào acceptance chung.
- Không ép mọi task dùng đủ mọi QA axis hoặc cùng số review round.
- Không thay authority, merge/deploy, Neon/production hay data-boundary gate hiện có.

## 4. Acceptance

- `docs/devops-brief.md` §7 chứa lifecycle intake → task contract → execution/review → adaptive stop.
- `CLAUDE.md` trỏ ngắn tới policy mới; không copy toàn bộ chi tiết.
- `AGENTS.md` buộc executor dừng khi thiếu contract làm đổi hướng và buộc reviewer trả consolidated ledger trên
  immutable target.
- Policy phân biệt product/evidence/runtime gates và không có universal loop cap.
- `git diff --check` và repository hooks pass; PR docs vào `develop`, không tự merge/deploy.
