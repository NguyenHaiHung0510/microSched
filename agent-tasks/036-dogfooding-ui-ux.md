# 036 — Dogfooding UI/UX: Tracker, Note và subtask

> Trạng thái: **DRAFT 2026-08-27 — product behavior do Owner nêu trực tiếp; chờ ad-review spec.**
>
> UI executor bắt buộc: **Gemini 3.7/high**. Nếu exact route không callable, không substitute;
> dùng nguyên `agent-tasks/036-gemini-implementation-prompt.md` trong session Gemini khác.
> T3/reviewer có thể là Luna/xhigh hoặc Terra/xhigh read-only.

## 0. Kết quả người dùng phải nhận được

Sửa đúng sáu cụm lỗi dogfooding; không redesign hướng “B · hồng ấm”:

1. Cell “Lịch nhắc nhở trong ngày” đứng đầu màn Tracker, ngay trước
   “Tài chính tháng X năm Y”; các cell còn lại giữ thứ tự tương đối.
2. Nội dung/action của một reminder group không tràn khỏi card hoặc màn hình 390px.
3. Dialog tạo/sửa tracker dùng được khi laptop không fullscreen và trên 390×844: đầu/cuối không
   bị cắt; cuộn trong dialog; microcopy interval không ngắt “chưa / ghi” vô nghĩa.
4. Note card dùng gần hết chiều ngang khả dụng cho title/body/metadata/reflection; action rail không
   bó nội dung còn khoảng 60%.
5. Notes có ba sort mode: alphabet, thời gian tạo, thời gian sửa; mặc định alphabet; pinned luôn
   đứng trước normal và cùng comparator được dùng trong từng nhóm.
6. Tạo/sửa task và task trong calendar month quản lý subtask mà không phải “Lưu thay đổi” rồi mở
   dialog lại.

## 1. Luật UI bắt buộc

Đọc `docs/ui-brief.md` và `docs/qa-framework.md` trước dòng code đầu tiên.

- Không raw `<button>/<input>/<select>`; dùng `@/components/ui/*`.
- Không hardcode màu mới; không dark mode; font ≥12px.
- Không card height cứng; không interaction chỉ-hover.
- Mobile primary target ≥44px, absolute minimum ≥24px, gap ≥8px.
- Input text ≥16px trên mobile; `document.scrollWidth <= innerWidth` ở 390px.
- Dữ liệu dài/emoji/Vietnamese/70-char-no-space phải có behavior rõ: wrap/truncate, không overflow.
- Screenshot là taste evidence; geometry phải đo DOM.

## 2. Tracker screen

### 2.1 Thứ tự

Di chuyển nguyên block reminder hiện ở cuối phần quản lý lên trước finance overview. Không copy block,
không đổi thứ tự finance → capture → group management → recent entries → dashboard.

### 2.2 Reminder group responsive

- Header/time/preview có `min-w-0`; preview có wrap/truncate rõ.
- Tracker-name line wrap trong card.
- Action area ở mobile là full-width grid/stack; button dùng `h-auto min-h-11 min-w-0 w-full`
  + `whitespace-normal break-words`. Desktop có thể quay về inline.
- Không horizontal scroll; action cuối luôn nằm trong card.

### 2.3 Tracker dialog + microcopy

Create và edit `DialogContent` dùng `max-h` theo `100dvh` và `overflow-y-auto`; top/bottom cách
viewport tối thiểu 16px. Focus trap/return giữ nguyên.

Form không ép hai cột ở mobile. Label interval dùng copy ngắn, không chứa token kỹ thuật `N`:

- fixed: `Lặp lại mỗi (ngày)`;
- after-entry: `Số ngày chưa ghi`.

Task 035 supersede lock-screen copy, nên bỏ control “Nội dung hiện trên màn hình khoá” khỏi UI và
không gửi `reminder_text` mới. Giữ field backend/DB để compatibility; không migration drop.

## 3. Notes

### 3.1 Layout mobile

- Ở mobile, card chuyển thành flow dọc: title/badge, action row, body/reflection/metadata dùng full
  content width. `sm:` có thể dùng rail ngang nếu không bó body.
- Metadata time + `X/Y mục` không bị ép thành hai cột hẹp; CTA “Gửi lời nhắn tương lai” xuống hàng
  riêng khi cần.
- Reflection box rộng xấp xỉ content column, header wrap tự nhiên, không `text-[11px]`; edit/delete
  targets vẫn đạt ngưỡng. Thay hardcoded `amber-*` bằng semantic tokens hiện có, giữ cảm giác vàng ấm.
- Title/body/reflection long strings không đẩy action ra màn và không overflow.

### 3.2 Sort contract

UI dùng shadcn `Select` hoặc control tương đương với `data-testid="note-sort"`:

```text
alphabet (default): Intl.Collator('vi-VN', sensitivity base, numeric true), A→Z
created: created_at mới nhất trước
updated: (updated_at ?? created_at) mới nhất trước
```

Pinned là primary partition, comparator mode chỉ chạy bên trong pinned và normal. Tie-breaker lần lượt
label hiện hành (`title || "Không tiêu đề"`), `created_at`, rồi `id`. Không sort ciphertext ở DB;
sort sau API decrypt trên tập notes đang hiển thị. Selection được lưu localStorage; không có key thì
alphabet.

Query hiện chỉ tải 100 note. Task này phải fetch tuần tự các page `limit=100&offset=...` tới page ngắn
hơn 100, de-duplicate theo ID và fail visible nếu offset không tiến; sau đó mới sort toàn bộ tập visible.
Không thêm plaintext sort-key hoặc nới privacy boundary. Safety cap là **20 page / 2.000 note**. Nếu
page thứ 20 vẫn đủ 100 row, page fingerprint lặp, offset không tiến hoặc số ID unique không tăng, UI
không được render partial list như thể đã sort đủ: hiện error block
`data-testid="note-page-limit-error"` với copy `Không tải đủ ghi chú để sắp xếp. Thử lại.` và nút retry.
Test fixture 2.001 note phải chạm đúng guard. Report cap như operational guard, không claim unbounded
scale.

## 4. Task/subtask

### 4.1 Create task

Backend `TaskCreate.items` đã hỗ trợ tạo parent + checklist atomically; frontend hiện ép `items: []`.
Thêm shared draft checklist editor vào `TaskForm`/create dialog:

- thêm, sửa, xoá draft trước khi parent tồn tại;
- whitespace-only bị UI từ chối; backend `TaskCreate.items`, `TaskItemCreate.content` và
  `TaskItemUpdate.content` cũng trả 422 cho client bypass (Terra backend sub-lane nhỏ);
- submit một POST task với `items` theo order hiện trên form;
- create fail giữ nguyên draft; success đóng dialog và dữ liệu phản chiếu đúng.

Không tạo parent tạm, không POST child trước parent, không thêm bảng/outbox mới.

### 4.2 Edit task

Task đã có ID dùng child endpoints hiện hành. Trong cùng edit dialog, parent form và checklist editor
đều nhìn thấy; thêm/sửa/tick/xoá subtask không cần save parent trước hoặc đóng/mở lại.

Child mutation độc lập phải báo pending/error ngay trong dialog và invalidate task + calendar family.
Parent save không được xoá/ghi đè checklist vừa đổi.

Parent-save và child mutation không chạy đồng thời: khi một lane pending, disable submit/controls của
lane kia. Child đã success không rollback nếu parent save sau đó fail; UI giữ child mới và hiển thị
parent error. Child fail giữ parent draft, item text và dialog mở để retry.

### 4.3 Calendar month

`DayDetailDialog` khi mở task phải render cùng persisted checklist editor. User có thể add/edit/tick/
delete subtask rồi quay lại month view; chip/card phản ánh count/state sau invalidate. Không nested
interactive mới và không desktop-only hover path.

## 5. Phạm vi file dự kiến

- `frontend/src/TrackerScreen.tsx`, `TrackerForm.tsx`, `tracker-ui.ts`
- `frontend/src/NotesScreen.tsx`, `note-ui.ts`
- `frontend/src/TaskForm.tsx`, `TasksScreen.tsx`, `DayDetailDialog.tsx`
- `backend/app/domain/tasks.py` + targeted tests chỉ cho whitespace child guard
- shared checklist component mới nếu giúp tránh hai implementation lệch nhau
- frontend unit/Playwright fixtures/specs tương ứng

Không sửa migration, auth/private architecture, PWA outbox hoặc calendar grid anatomy ngoài chỗ cần
invalidate/render subtask.

## 6. Acceptance + RED → GREEN

### Tracker

- DOM order: reminder index < finance index; mỗi block xuất hiện đúng một lần.
- 390×844 và 1280×800: no horizontal overflow; button text dài nằm trong card.
- Tracker dialog top/bottom trong viewport, `scrollHeight > clientHeight` khi form dài và cuộn tới cả
  title lẫn submit được; close target/focus return pass.
- Microcopy không chứa `Nhắc sau N ngày chưa ghi`; lock-screen custom text control không còn.

### Notes

- Body/reflection box mobile rộng ≥90% content column; right edge không vượt card.
- Action row/metadata/CTA wrap có chủ đích; font ≥12; targets đạt ngưỡng.
- Sort fixtures có uppercase, dấu tiếng Việt, số, null title, equal timestamps và pinned mix.
- Default alphabet; created/updated newest-first; pinned partition luôn thắng; reload giữ choice.
- 101-note fixture chứng minh page thứ hai tham gia sort; repeated page/fingerprint fail visible thay vì
  loop vô hạn.

### Subtask

- Create task với 3 draft items gửi một POST, không child POST; response hiển thị đủ order.
- Create fail giữ draft và error visible.
- Edit task add child trước parent save; không đóng dialog; parent save không mất child.
- Backend direct create/add/update whitespace child trả 422.
- Parent/child mutations mutual-exclude; child error giữ input; parent error không rollback child success.
- Calendar edit task add/tick/delete child và month/day dialog refresh đúng.
- Long child content wraps; button/focus/mobile targets pass.

### RED proof

- Bỏ `min-w-0`/mobile stack ⇒ geometry test đỏ.
- Đổi comparator để pinned không partition ⇒ sort test đỏ.
- Ép create `items: []` ⇒ atomic checklist test đỏ.
- Ẩn checklist khi `editing=true` ⇒ edit-flow Playwright đỏ.
- Restore rồi lint/unit/build/e2e xanh.

## 7. Lệnh và report boundary

Fresh worktree: chạy `npm ci` trong `frontend` trước khi diễn giải thiếu dependency.

```text
frontend: npm run lint
frontend: npm run test
frontend: npm run build
frontend: npm run e2e
root:     uvx pre-commit run --all-files
```

Playwright 390×844/1280×800 không chứng minh Safari/iPhone thật. Ảnh Owner là input private, không
commit/copy vào repo public. Gemini report phải ghi raw output, screenshots crop app-only và
`git status --short` + `git diff --stat` để chứng minh scope.
