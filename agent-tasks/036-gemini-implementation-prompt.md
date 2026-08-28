# Prompt handoff — Gemini 3.7/high implement Task 036

Bạn là T2 UI executor cho repo public microSched. Làm trong **worktree/branch riêng do T1 cung cấp**;
không dùng cây `main` dirty. Model/effort phải là **Gemini 3.7/high**.

## Bắt buộc đọc trước

Đọc đầy đủ theo thứ tự:

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/ui-brief.md`
4. `docs/qa-framework.md`
5. `agent-tasks/036-dogfooding-ui-ux.md`

Nếu các file mâu thuẫn, dừng và nêu cả hai phía. Không đọc `.env`, không mở production/Chrome profile,
không chạy Neon, không commit screenshot Owner hoặc personal data.

## Objective

Thực hiện đúng toàn bộ Task 036, không hơn:

- đưa “Lịch nhắc nhở trong ngày” lên trước finance và sửa overflow mobile;
- tracker dialog cuộn/reflow + microcopy interval ngắn + bỏ lock-screen custom-text control;
- note card/reflection/metadata dùng đủ ngang mobile;
- sort Notes alphabet/created/updated, pinned partition, default alphabet;
- draft subtask khi create task, persisted subtask ngay trong edit dialog;
- quản lý subtask của task từ Calendar day/month flow.

Sáu screenshot của Owner chỉ là provenance private, **không phải input bắt buộc**: spec đã chưng cất
behavior reproducible. Không commit/chụp lại thông tin tab/bookmark/profile vào artifact.

## Hard boundaries

- Không raw controls; không hardcode màu; không dark mode; không card height cứng; chữ ≥12px.
- Không interaction chỉ-hover; mobile primary target ≥44px; no horizontal scroll 390px.
- Không đổi backend schema/API ngoài targeted whitespace validators/tests đã ghi trong spec;
  `TaskCreate.items` và child endpoints hiện hữu là seam được phép dùng.
- Không giải offline/outbox/Task 017; không sửa calendar anatomy ngoài subtask path.
- Không tự redesign brand hoặc copy ngoài copy exact trong spec.
- Bí hoặc cùng lỗi lặp hai vòng: dừng, dán raw output, không đoán.

## Workflow/receipt

1. Inspect exact current code + tests; ghi `git status --short` sạch trước patch.
2. Implement nhỏ theo surface, thêm unit/Playwright regression.
3. Với từng guardrail mới, cố ý phá → thấy test RED đúng lý do → restore → GREEN; ghi raw output.
4. Chạy trong `frontend`: `npm ci`, `npm run lint`, `npm run test`, `npm run build`,
   `npm run test:e2e` (hoặc exact scripts hiện có nếu package khác; dán output thật).
5. Root: `uvx pre-commit run --all-files`.
6. Chụp crop app-only ở 390×844 và 1280×800 cho reminder card, tracker dialog, note card/reflection,
   task edit + calendar subtask. Đo `innerWidth`, scrollWidth, bounding boxes/target sizes. Lưu artifact
   dưới `test-results/task-036/`, ghi relative path + SHA-256 của từng ảnh vào report; không nhúng ảnh
   Owner gốc hoặc screenshot có tab/bookmark/profile.
7. Kết thúc bằng:
   - files changed + vì sao;
   - `[ĐÃ CHẠY — PASS/FAIL]`, `[CHƯA VERIFY]`, `[BLOCKED]` tách riêng;
   - raw commands/output;
   - `git diff --check`, `git diff --stat`, `git status --short`;
   - không tự merge/deploy.
