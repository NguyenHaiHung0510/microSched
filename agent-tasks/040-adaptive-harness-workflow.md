# 040 — Adaptive harness workflow cho issue cluster và review loop

> **Trạng thái:** ✅ CHỐT 2026-08-29 — owner yêu cầu áp dụng
> **Loại:** docs/policy + bounded infra guard
> **Executor:** T1 cho policy/docs; owner-approved exception cho đúng config/test patch ở §4
> **Model + effort đề xuất:** Sol/max cho policy judgment; bounded config patch deterministic, không cần route riêng
> **Skill/MCP:** không bắt buộc
> **Review posture:** một independent adversarial PR review, consolidated ledger

**Task contract:**

- **Outcome:** đổi raw issue cluster thành owner-negotiated adaptive lifecycle và khôi phục canonical Fly swap guard.
- **Scope:** bảy file policy/task/config/test trong PR #189; không product feature hoặc runtime mutation.
- **Dependency/hard start:** exact `develop` base; owner decision ở task này; review + CI là merge gate.
- **Report:** một strategic terminal packet cho owner; raw receipt nằm trong PR; không heartbeat/monitor.
- **Loop budget:** một independent review + tối đa một consolidated fix batch; sau đó dừng cho owner decision,
  không tự mở review thứ hai.
- **Stop/re-scope:** dừng nếu cần deploy/secret/live Machine, đổi authority, mở rộng khỏi bounded config guard,
  hoặc ledger sau fix vẫn cần product/architecture decision.

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

## 4. Bounded Fly swap correction

Owner đã bật 512MB swap nhưng canonical `fly.toml` bị ghi đè về trạng thái không có swap. PR này giữ
`swap_size_mb = 512` ở top-level theo Fly config contract, ghi rationale trong `architecture-brief.md` và
thêm một static test để CI đỏ nếu key bị mất/di chuyển/sai giá trị. Không deploy hoặc gọi production.

Owner trực tiếp yêu cầu T1 gắn correction này vào cùng PR sau policy commit. Đây là exception hẹp cho
config + guard deterministic, không thay đổi policy phân vai, không cấp merge/deploy/production authority
và không trở thành precedent cho T1 tự thi công app code.

## 5. Acceptance

- `docs/devops-brief.md` §7 chứa lifecycle intake → task contract → execution/review → adaptive stop.
- `CLAUDE.md` trỏ ngắn tới policy mới; không copy toàn bộ chi tiết.
- `AGENTS.md` buộc executor dừng khi thiếu contract làm đổi hướng và buộc reviewer trả consolidated ledger trên
  immutable target.
- Policy phân biệt product/evidence/runtime gates và không có universal loop cap.
- `fly.toml` parse/validate với top-level `swap_size_mb = 512`; focused config test pass.
- `git diff --check` và repository hooks pass; PR docs vào `develop`, không tự merge/deploy.
