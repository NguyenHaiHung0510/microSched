# 009 — Note slice (task/checklist/riêng tư/undo, chép khuôn từ 008 + 008f + 008n + 008m)

> **DRAFT — khung để chủ duyệt, CHƯA phải bản giao Codex.** Còn thiếu: lượt `adversarial_review`
> (T3, "spec sai ở đâu") trước khi đủ điều kiện thi công — thói quen đã áp cho `008-task-slice` và
> `008m`. Không giao executor cho tới khi lượt đó xong.

## 0. Bối cảnh — vì sao 009 chỉ còn là "chép khuôn"

`note`/`note_item` đã tồn tại đầy đủ ở tầng schema (`backend/app/domain/models.py`, migration
`006` + `0002`) — cùng hình với `task`/`task_item` gần như tuyệt đối: cùng `__privacy_gate__ =
Gate.APPLIES` (note) / `Gate.VIA_PARENT` (note_item), cùng CHECK `private_ciphertext` (tiêu đề +
thân đều phải là `enc:v1:%` khi riêng tư — khoá 23/07 sau security review 008d, để `note.title`
khớp `task.title`), cùng checklist con có `position`. Nhưng **chưa có một dòng domain/router/UI
nào cho Note** — 009 là dựng lại đúng công đã làm cho Task ở `008`/`008f`/`008i`/`008k`, không
phải thiết kế lại.

**Hai quyết định phạm vi đã chốt với chủ 2026-07-28 (không hỏi lại):**
1. **Checklist (`note_item`) làm ngay trong 009, không hoãn** — Task đã có checklist thật từ 008,
   009 "chép khuôn" thì chép đủ.
2. **Áp seam của `008m` (id UUIDv7 sinh ở client + ghi idempotent) cho Note create** ngay khi
   `008m` merge xong — nhưng **không** dựng hàng đợi offline thật (Dexie/outbox). Đúng như đã ghi
   lại vào `agent-tasks/README.md` (mục 015, thêm 2026-07-28): outbox thật dựng MỘT LẦN cho cả 4
   loại thực thể sau 011, không dựng riêng cho note ở đây. 009 chỉ *dùng* seam đã mở, không mở
   thêm cửa nào.

**Phụ thuộc bắt buộc, phải xong trước khi giao thi công:**
- `008f` (đã merge) — `with_privacy_gate()` / `not_deleted()` tách khỏi `readable()`, để
  `notes.py` gọi đúng hàm, không đụng `reading.py`.
- `008n` (đã merge) — cổng đọc khai báo tường minh `APPLIES|NONE|VIA_PARENT`; `note`/`note_item`
  đã khai đúng trong `models.py`, 009 chỉ tiêu thụ, không sửa.
- `008m` (**đang chạy nền lúc viết draft này** — xem trạng thái PR trước khi giao 009) — nếu chưa
  merge, 009 tạm thời tạo Note theo kiểu cũ (server sinh id) và **ghi rõ trong PR** rằng seam
  offline sẽ vá lại ở một PR nhỏ ngay sau khi 008m merge, KHÔNG chặn 009 chờ 008m.

## 1. Đã khoá — chép ra code, không mở lại

1. **File mới, không sửa file của `task`:** `backend/app/domain/notes.py`,
   `backend/app/web/routers/notes.py`, `frontend/src/NotesScreen.tsx`, `frontend/src/NoteForm.tsx`,
   `frontend/src/note-ui.ts`, `frontend/src/note-undo.ts`. Có thể **đọc** `tasks.py`/
   `TasksScreen.tsx`/`task-ui.ts`/`task-undo.ts` làm mẫu, nhưng đây là file riêng — không import
   chéo qua lại giữa hai domain trừ tiện ích dùng chung thật sự đã có (`reading.py`, `uuidv7.ts`
   nếu 008m đã tồn tại).
2. **Checklist con (`note_item`) đủ CRUD**, giống `task_item`: thêm/sửa/xoá/đổi thứ tự trong note.
3. **Riêng tư + undo giống hệt task**: `is_private` gác qua `with_privacy_gate()`, soft-delete +
   toast Hoàn tác 10 giây (khoá `tracking-brief.md:150`), route authorization ở tầng router.
4. **Không đổi CHECK `private_ciphertext` hiện có** — nó đã đúng, chỉ cần code Python tôn trọng nó
   (mã hoá trước khi ghi khi `is_private=true`, dùng `app/core/crypto.py` từ 008a).

## 2. Phải làm (khung — chi tiết hoá khi hết DRAFT)

### 2.1 Backend — `notes.py` (mirror `tasks.py`)
- `NoteItemCreate` / `NoteItemUpdate` / `NoteItemRead` (mirror `TaskItemCreate/Update/Read`).
- `NoteCreate` / `NoteUpdate` / `NoteRead` — **`id: UUID | None = None`** ngay từ đầu nếu 008m đã
  merge (áp §2.2–§2.3 của `008m` nguyên xi cho Note: idempotent write, chặn biến-tạo-thành-sửa,
  `409` thân rỗng cho trùng id với bản ghi không đọc được, validator version==7).
- `NoteStore` — CRUD + mã hoá/giải mã `title`/`body_md` khi `is_private`, dùng
  `with_privacy_gate()`/`not_deleted()` (KHÔNG gọi `readable()` trực tiếp cho ghi, theo đúng lệ
  008f đã tách).

### 2.2 Router — `backend/app/web/routers/notes.py`
- Mirror `routers/tasks.py`: `POST/GET/PATCH/DELETE /api/notes`, `POST/PATCH/DELETE
  /api/notes/{id}/items/{item_id}` (hoặc gộp items vào payload note nếu `tasks.py` đang làm vậy —
  giữ đúng quy ước đã có, đừng bày quy ước mới).
- `require_session` ở tầng router (luật đã khoá từ auth-brief — không có slice nào ship thiếu gác).

### 2.3 Frontend
- `NotesScreen.tsx` + `NoteForm.tsx`: mirror `TasksScreen.tsx`/`TaskForm.tsx` — dùng component
  shadcn đã dựng ở `008e`, không thẻ `<button>` thô (luật UI trong `AGENTS.md`).
- `note-ui.ts`: type `NotePayload` (mirror `TaskPayload`, có `id: string` nếu 008m đã merge).
- `note-undo.ts`: mirror `task-undo.ts` (toast 10s, hoàn tác = soft-delete).
- Áp luôn 2 bài học đã trả giá ở task, đừng lặp lại:
  - `AbortSignal.timeout(20s)` cho mọi `apiRequest` (008i) — đã có sẵn trong `api.ts`, chỉ cần
    dùng đúng, không tự chế lại.
  - Contrast/touch-target theo `ui-brief.md` (008e/008i/008k) — đặc biệt icon ghim (nếu Note cũng
    pin được) và viền input.

## 3. Không được làm

- Không dựng Dexie/outbox/IndexedDB thật — đó là 015 (sau 011), không phải 009.
- Không sửa `reading.py`, không sửa CHECK `private_ciphertext` hiện có.
- Không đụng file của `task` (`tasks.py`, `TasksScreen.tsx`, `task-ui.ts`, `task-undo.ts`) trừ đọc
  làm mẫu.
- Không tự quyết seam offline nếu `008m` **chưa merge** lúc thi công — báo lại, đừng tự chế một
  cơ chế idempotency khác cho Note.

## 4. Acceptance (khung)

1. `uv run ruff check` sạch, `uv run pytest` xanh gồm lane `-m pg`.
2. `npm run lint` / `npm test` / `npm run build` xanh.
3. Test riêng tư: note riêng tư khoá ⇒ biến mất khỏi GET danh sách, `409` thân rỗng khi trùng id
   (nếu seam 008m đã áp), soft-delete giữ nguyên `deleted_at`.
4. Test checklist: thêm/sửa/xoá/đổi thứ tự `note_item`, xoá note cha thì item theo (CASCADE đã có
   ở DB, chỉ cần test không phá nó).
5. `gh pr checks <PR>` xanh đủ 5 required check.

## 5. Còn thiếu trước khi giao thi công (đừng bỏ qua)

- [ ] Lượt `adversarial_review` (T3, "spec sai ở đâu") trên bản đầy đủ hoá của file này.
- [ ] Xác nhận trạng thái PR `008m` (merge hay chưa) tại thời điểm giao — quyết định seam theo §0.
- [ ] Chi tiết hoá §2 thành các bước cụ thể như `008m` đã làm (dòng file, hàm chính xác) trước khi
      đưa cho Codex — bản này còn ở mức khung.
