# 009 — Note slice (task/checklist/riêng tư/undo, chép khuôn từ 008 + 008f + 008n + 008m)

> **DRAFT — khung để chủ duyệt, CHƯA phải bản giao Codex.** Đã qua 1 lượt `adversarial_review`
> (T3, `gemini-3.1-pro-high`, 2026-07-28, đọc code thật) — 6 finding đã fold vào bản này. Còn thiếu
> bước "chi tiết hoá §2 thành dòng file/hàm chính xác" như `008m` đã làm trước khi đủ điều kiện
> giao Codex.

## 0. Bối cảnh — vì sao 009 chỉ còn là "chép khuôn"

`note`/`note_item` đã tồn tại đầy đủ ở tầng schema (`backend/app/domain/models.py`, migration
`006` + `0002`) — gần giống hình `task`/`task_item` nhưng **KHÔNG giống tuyệt đối, hai chỗ lệch
phải nhớ:**
1. `Note.title` **nullable** (`models.py:183`, CHECK viết `title IS NULL OR title LIKE
   'enc:v1:%'`) — khác `Task.title` là `NOT NULL`. Note không tiêu đề là hợp lệ; `NoteCreate` /
   `_sealed()` **không được** đòi title bắt buộc như `TaskCreate` đang làm.
2. `Note` có cột `embedding: list[float] | None` (`models.py:185`, "unbounded, unindexed vector
   placeholder" cho AI Bước 1) — **`Task` không có cột này**. `NoteRead` phải loại `embedding`
   khỏi response (mirror cách `TaskRead` loại `created`: `Field(default=None, exclude=True)`, hoặc
   đơn giản không khai field đó trong `NoteRead` — cột không tồn tại ở tầng DTO). Slice này
   **không ghi/đọc** giá trị embedding, chỉ tránh để nó rò ra JSON.

Ngoài hai lệch đó, `note_item` cùng `__privacy_gate__ = Gate.VIA_PARENT` như `task_item` — nhưng
**VIA_PARENT nghĩa là gác HOÀN TOÀN ở tầng app, KHÔNG có CHECK hay cột `is_private` nào trên chính
`note_item`** (chỉ `note` có CHECK `private_ciphertext`). Gọi `with_privacy_gate()`/`not_deleted()`
thẳng lên `NoteItem` sẽ ném `ReadingGateError` (`reading.py:61-69`) — luôn đi qua `note_id` để lấy
gate của cha, đúng như `tasks.py` đang làm cho `task_item`. Nhưng **chưa có một dòng domain/
router/UI nào cho Note** — 009 là dựng lại đúng công đã làm cho Task ở `008`/`008f`/`008i`/`008k`,
không phải thiết kế lại.

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
- `008m` — **✅ đã merge** (`3c09fa4`, PR #44, 2026-07-28). Seam id-client + ghi idempotent áp
  KHÔNG ĐIỀU KIỆN cho Note create, không còn nhánh "chưa merge thì tạm..." nào để cân nhắc — mọi
  chỗ dưới đây viết như thể seam đã sẵn có, không có fallback.

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
4. **Không đổi CHECK `private_ciphertext` hiện có trên `note`** — nó đã đúng (và đã tính tới
   `title` nullable, xem §0), chỉ cần code Python tôn trọng nó (mã hoá trước khi ghi khi
   `is_private=true`, dùng `app/core/crypto.py` từ 008a). `note_item` **không có CHECK nào của
   riêng nó** — bất biến của nó là app-layer thuần tuý qua `note.is_private`, xem §0 và khoá dòng
   cha ở mục 5 dưới.
5. **Khoá dòng cha (`SELECT … FOR UPDATE`) đúng chỗ, không phải mọi chỗ** — chép nguyên quy tắc
   `tasks.py` đang dùng (`_parent(db, auth, id, for_update=...)`, `tasks.py:283`):
   - Sửa `title`/`body_md`/soft-delete **không** khoá dòng cha (`for_update=False`).
   - Sửa **có đổi `is_private`** ⇒ khoá dòng cha (`for_update=True`) — đây là chỗ chống đua giữa
     "đang mã hoá con" và "một request khác đang ghi thêm con" (xem `tasks.py:283,289-298`).
   - Mọi thao tác lên `note_item` (thêm/sửa/xoá/đổi thứ tự) ⇒ **luôn** khoá dòng note cha
     (`for_update=True`, `tasks.py:376,401,428`) — item ghi plaintext hay ciphertext phụ thuộc
     trạng thái `is_private` hiện tại của cha, phải đọc trạng thái đó dưới khoá.
   - Không có DB nào tự chặn thiếu khoá này (CHECK chỉ thấy trạng thái cuối cùng, không thấy đua) —
     thiếu nó là type lỗi *im lặng*, chỉ lộ dưới tải đồng thời thật.

## 2. Phải làm (khung — chi tiết hoá khi hết DRAFT)

### 2.1 Backend — `notes.py` (mirror `tasks.py`)
- `NoteItemCreate` / `NoteItemUpdate` / `NoteItemRead` (mirror `TaskItemCreate/Update/Read`).
- `NoteCreate` / `NoteUpdate` / `NoteRead` — **`id: UUID | None = None`** ngay từ đầu (áp §2.2–§2.3
  của `008m` nguyên xi cho Note: idempotent write, chặn biến-tạo-thành-sửa, `409` thân rỗng cho
  trùng id với bản ghi không đọc được, validator version==7). `NoteRead` **không khai field
  `embedding`** (xem §0 mục 2).
- `NoteStore` — CRUD + mã hoá/giải mã `title`/`body_md` khi `is_private`, dùng
  `with_privacy_gate()`/`not_deleted()` (KHÔNG gọi `readable()` trực tiếp cho ghi, theo đúng lệ
  008f đã tách).

### 2.2 Router — `backend/app/web/routers/notes.py`
- Mirror `routers/tasks.py` đủ endpoint, đừng bỏ sót cái nào: `POST /api/notes`, `GET /api/notes`
  (danh sách), `GET /api/notes/{id}` (một note), `PATCH /api/notes/{id}`, `DELETE /api/notes/{id}`
  (soft-delete), `POST /api/notes/{id}/restore` (hoàn tác — bắt buộc, đây là endpoint toast 10s ở
  §2.3 gọi tới), `POST/PATCH/DELETE /api/notes/{id}/items/{item_id}` (hoặc gộp items vào payload
  note nếu `tasks.py` đang làm vậy — giữ đúng quy ước đã có, đừng bày quy ước mới).
- `require_session` ở tầng router (luật đã khoá từ auth-brief — không có slice nào ship thiếu gác).

### 2.3 Frontend
- `NotesScreen.tsx` + `NoteForm.tsx`: mirror `TasksScreen.tsx`/`TaskForm.tsx` — dùng component
  shadcn đã dựng ở `008e`, không thẻ `<button>` thô (luật UI trong `AGENTS.md`).
- `note-ui.ts`: type `NotePayload` (mirror `TaskPayload`/`TaskWritePayload` — tách write-payload
  không id khỏi create-payload có `id: string`, đúng lý do `008m` đã tách cho Task).
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
- Không để `NoteRead`/API trả `embedding` ra ngoài (§0 mục 2) — slice này không đọc/ghi giá trị đó.
- Không bỏ qua `for_update` ở đúng 3 chỗ nêu tại §1 mục 5 — thiếu nó không có test nào tự đỏ trừ
  khi cố tình viết test đua như `008m` đã làm cho `task`; nếu thời gian không đủ để viết test đua
  cho note, ít nhất phải áp đúng khoá, đừng bỏ qua vì "chưa có test bắt".

## 4. Acceptance (khung)

1. `uv run ruff check` sạch, `uv run pytest` xanh gồm lane `-m pg`.
2. `npm run lint` / `npm test` / `npm run build` xanh.
3. Test riêng tư: note riêng tư khoá ⇒ biến mất khỏi GET danh sách, `409` thân rỗng khi trùng id
   (nếu seam 008m đã áp), soft-delete giữ nguyên `deleted_at`.
4. Test checklist: thêm/sửa/xoá/đổi thứ tự `note_item`, xoá note cha thì item theo (CASCADE đã có
   ở DB, chỉ cần test không phá nó).
5. `gh pr checks <PR>` xanh đủ 5 required check.

## 5. Còn thiếu trước khi giao thi công (đừng bỏ qua)

- [x] Lượt `adversarial_review` (T3, `gemini-3.1-pro-high`, 2026-07-28) — 6 finding đã fold: title
      nullable, `embedding` không có ở Task, VIA_PARENT là app-layer thuần, thiếu khoá `for_update`,
      thiếu endpoint `GET /{id}` + `restore`, hedge 008m-chưa-merge đã lỗi thời.
- [x] `008m` đã merge — không còn nhánh điều kiện nào cần quyết ở thời điểm giao.
- [ ] Chi tiết hoá §2 thành các bước cụ thể như `008m` đã làm (dòng file, hàm chính xác) trước khi
      đưa cho Codex — bản này còn ở mức khung.
