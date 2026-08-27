# 033 — Task checklist test hooks

**Trạng thái:** ✅ CHỐT — implementation scope được owner duyệt salvage từ PR #153.

## Provenance và baseline

PR #153 (`jules-14702205601529065039-25470f3a`) đề xuất thêm ba `data-testid` cho checklist
trong `TasksScreen.tsx`, nhưng PR đã đóng, chưa merge. PR head cũ là `9df7b0d`; remote branch
hiện đã drift sang `df1f71f` với thay đổi 112 file. Vì vậy không lấy code từ branch Jules và
không merge branch đó.

Implementation bắt đầu từ `origin/develop` exact `14787f5366d9e487df9dff4f7fd44d635fe09be9`,
trên branch `feat/033-task-checklist-test-hooks` trong worktree riêng.

## Phạm vi

1. Thêm đúng ba thuộc tính test-only vào `frontend/src/TasksScreen.tsx`:
   - `data-testid="task-item-delete"` trên nút xoá checklist.
   - `data-testid="task-item-add-input"` trên ô nhập checklist.
   - `data-testid="task-item-add-submit"` trên nút submit checklist.
2. Thêm `frontend/e2e/checklist.spec.ts` dùng fixture `./fixtures/tasks` hiện hữu để:
   - mở task fixture `task-012` bằng selector ổn định;
   - thêm một checklist item synthetic và assert request/API state/UI state;
   - xoá đúng item vừa thêm và assert request/API state/UI state.
3. Chứng minh RED khi thiếu selector, sau đó restore selector và chứng minh GREEN. Không commit
   trạng thái RED.

## Không làm

- Không lấy bất kỳ thay đổi nào khác từ branch Jules.
- Không đổi backend, fixture, API behavior, copy, layout, component, hoặc accessibility behavior.
- Không thêm selector dựa trên text tiếng Việt khi selector test-id đã có.
- Không chạy migration, Neon QA, production QA, push, hoặc mở PR trong lane này.

## Acceptance

- Diff chỉ gồm file spec này, `frontend/src/TasksScreen.tsx`, và focused Playwright spec.
- `git diff --check` pass.
- Targeted Playwright test có RED đúng lỗi thiếu `task-item-add-input` trước khi thêm selector,
  rồi GREEN sau khi restore đủ ba selector.
- Frontend test/lint/build được chạy nếu dependency/runtime cho phép; mọi blocker ghi raw output.
- Commit local dùng message tiếng Việt UTF-8 qua `git commit -F`, có `Co-Authored-By`; chưa push/open PR.

## Evidence boundary

Local unit/lint/build và Playwright Chromium chỉ chứng minh các gate đã chạy trong worktree này.
CI, production runtime, physical iPhone/Safari và Neon staging vẫn **CHƯA VERIFY** trong task này.
