# 042 — bounded authority và chuẩn hóa entry point

Status: **Owner-approved 2026-09-06; implementation/review in progress**. Không phải product feature.

## Outcome và authority

Owner yêu cầu integrate proposal inherited/scoped/Owner-only ngay, áp dụng PR200 và merge các PR cần thiết
để hoàn tất phiên harness. Owner cũng cho phép release-label develop → main sau kiểm production, bao gồm
các thay đổi đã có trên develop trước phiên. Grant kết thúc khi closeout; không bao gồm new product work,
destructive/data/security changes hoặc cleanup worktrees. Thay policy authority trong task này đã được Owner duyệt.

T1 trực tiếp phân tích/viết, delegate read-only inventory và independent ad-review; T1 có quyền merge.
Không cần per-task coordination_record theo policy mới. Không dùng task này để tự cấp quyền Owner-only khác.

## Scope

- Canonical authority/review/merge policy, compact AGENTS, CLAUDE compatibility pointer, project reading map.
- Thay active callers xung đột; chuyển legacy harness prose sang history, không xóa evidence.
- QA docs reconcile về Owner-operated persistent staging; giữ QA037 schema/identity/single-use/Owner gates.
- Private harness-core/global adapter/memory retrieval được đồng bộ riêng; không publish private notes vào repo.
- PR200 song ngữ được merge; public profile/homepage/calendar để sau phiên.

Không sửa app, DB, dependencies, workflow/ruleset enforcement, credentials hoặc production data.

## Acceptance và review contract

T1 chọn independent ad-review cho thay đổi authority này: review immutable diff/hash, kiểm authority
laundering, scope inheritance/elevation, Owner-only, gate non-relaxation, semantic loss của instruction
migration, QA boundaries và active callers. Một consolidated ledger, không quota finding. Gate đã chọn này phải hoàn tất.

Local: changed-file scope, UTF-8, relevant links, retired-pattern audit và adapter drift/rollback checks.
Không claim policy prose là mechanical enforcement; interpretation scenarios là review cases.
CI: required checks terminal success trên exact PR head; fresh head/base/diff trước CAS merge.
Delivery: theo dõi deploy và exact readyz commit + db=up; release-label main chỉ sau gate đó và full-diff check.
Browser/device/product acceptance không nằm trong docs migration; không nâng các gate chưa chạy của task khác thành PASS.

## Stop/re-plan

Authority vượt grant, field/schema QA bị nới ngoài yêu cầu, unexpected file changes hoặc meaningful
head/base drift: reconcile trước action. Hai vòng cùng blocker không thêm evidence: báo log và đổi cách làm.
Không tạo thêm framework/authorization service/eval pipeline để thay một requirement paperwork cũ.

## Receipt

PR200: merge `58718ace321782d6f10515956cc851b48c861068`, reviewed head `e6ba79452e33a6fa0c116b760ce6b99fbc4e5dd9`,
base `6507a54d3149bab77e4e4381ee87f26a41969afd`, 10 checks PASS; CAS merge exit 0.
Migration PR, review/CI/live receipts cập nhật trong PR và closeout. Tài liệu này không tự chứng minh các gate đó đã chạy.
