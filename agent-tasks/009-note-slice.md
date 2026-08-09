# 009 — Note slice (task/checklist/riêng tư/undo, chép khuôn từ 008 + 008f + 008n + 008m)

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L2
> · Skill gợi ý: không cần · MCP cần: không cần.** Đã qua 1 lượt `adversarial_review` (T3,
> `gemini-3.1-pro-high`, 2026-07-28, đọc code thật) — 6 finding đã fold. §2 đã chi tiết hoá
> (2026-07-31, T1 đọc trực tiếp `tasks.py`/`routers/tasks.py`/`models.py` để đúc chữ ký chính xác)
> — **sẵn sàng giao Codex**, không còn ở mức khung.

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

## 2. Phải làm (chi tiết — mirror byte-for-byte trừ 3 delta ghi rõ dưới đây)

**Ba delta so với `Task`, không hơn không kém — mọi chỗ khác chép nguyên xi:**
1. `Note.title` **nullable** — `NoteCreate.title: str | None = None` (Task bắt buộc `min_length=1`).
2. `Note` **không có** `status`/`priority`/`due_at`/`pinned` — các DTO Note không khai 4 field này,
   `NoteStore.list()` không sort theo `pinned`/`due_at`.
3. `Note.embedding` tồn tại ở DB nhưng **không vào DTO nào** — slice này không đọc/ghi giá trị đó.

### 2.1 Backend — `backend/app/domain/notes.py` (file mới, mirror `backend/app/domain/tasks.py`)

DTOs — copy nguyên xi shape của `TaskItemCreate`/`TaskItemUpdate`/`TaskItemRead`
(`tasks.py:23-56`) thành `NoteItemCreate`/`NoteItemUpdate`/`NoteItemRead`, đổi `task_id` →
`note_id` trong `NoteItemUpdate.reject_null_required_fields`. Note chưa từng ship checklist nên
không có nhánh cũ phải giữ tương thích.

`NoteCreate` (mirror `TaskCreate`, `tasks.py:58-75`):
```python
class NoteCreate(BaseModel):
    id: UUID | None = None
    title: str | None = None          # delta 1 — Task bắt buộc, Note thì không
    body_md: str | None = None
    is_private: bool = False
    items: list[NonEmptyText] = Field(default_factory=list)
    # require_uuidv7 validator — copy nguyên xi từ TaskCreate (tasks.py:70-75)
```

`NoteUpdate` (mirror `TaskUpdate`, `tasks.py:78-95`) — **đây là chỗ dễ chép sai nhất trong cả
spec:**
```python
class NoteUpdate(BaseModel):
    title: str | None = Field(default=None)     # KHÔNG có min_length=1 (delta 1)
    body_md: str | None = None
    is_private: bool | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "NoteUpdate":
        # CHỈ "is_private" — "title" KHÔNG được liệt vào đây.
        # TaskUpdate cấm null cho "title" vì Task.title NOT NULL ở DB; Note.title
        # nullable, nên client gửi {"title": null} là yêu cầu HỢP LỆ để xoá tiêu đề,
        # không phải lỗi. Copy nguyên xi list ("title", "status", "is_private",
        # "pinned") từ TaskUpdate vào đây là BUG — nó chặn nhầm một thao tác hợp lệ,
        # không có test CI nào tự bắt vì đây là quyết định thiết kế, không phải type
        # error. Danh sách đúng cho Note: chỉ ("is_private",).
        for field in ("is_private",):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
```
Nhờ `model_dump(exclude_unset=True)` đã phân biệt "không gửi field" khỏi "gửi field=null", logic
mã hoá/patch ở `NoteStore.update()` (`if "title" in changes: note.title = changes["title"]`) chạy
đúng luôn cả khi `changes["title"] is None` — `_sealed()`/`_clear()` (copy nguyên xi từ
`tasks.py:119-130`) đã null-safe sẵn, không cần thêm nhánh nào.

`NoteRead` (mirror `TaskRead`, `tasks.py:98-112`) — bỏ `status`/`priority`/`due_at`/`pinned`,
**không khai `embedding`** (delta 3):
```python
class NoteRead(BaseModel):
    id: UUID
    title: str | None
    body_md: str | None
    is_private: bool
    items: list[NoteItemRead]
    created_at: datetime | None
    updated_at: datetime | None
    created: bool | None = Field(default=None, exclude=True)
```

`NoteIdConflict(Exception)` — mirror `TaskIdConflict` (`tasks.py:115-116`), dùng cho cùng một tình
huống (id trùng một bản ghi không đọc được).

`NoteStore` — mirror `TaskStore` (`tasks.py:133-445`) method-for-method, `Task`→`Note`,
`TaskItem`→`NoteItem` khắp nơi, bỏ mọi dòng đụng `status`/`priority`/`due_at`/`pinned`:
- `_parent()` — copy nguyên xi (`tasks.py:136-148`), dùng `readable()` (đã gồm cả
  `with_privacy_gate()` + `not_deleted()` — đây là đường đi ĐÚNG cho mọi thao tác trừ `restore()`).
- `_items()`, `_item_read()` — copy nguyên xi, đổi field.
- `_note_read()` (mirror `_task_read()`, `tasks.py:168-181`) — bỏ 4 field theo delta 2.
- `list()` (mirror `tasks.py:183-215`) — bỏ filter `status`, bỏ `.order_by(Task.pinned.desc(),
  Task.due_at.asc()...)`. **Quyết định order cho Note (chưa có ở đâu khoá trước, T1 chọn ngay tại
  đây thay vì để trống):** `.order_by(Note.created_at.desc())` — mới nhất trước, đúng kỳ vọng UX
  thông thường của danh sách ghi chú (không có "hạn"/"ghim" để ưu tiên như task). Không có param
  `status` trong `list()`/router (Note không có trạng thái open/completed).
- `get()` — copy nguyên xi.
- `create()` (mirror `tasks.py:224-278`) — copy nguyên xi luồng idempotent
  (`insert(...).on_conflict_do_nothing(...)` → `NoteIdConflict` nếu id trùng bản ghi không đọc
  được), bỏ field `status`/`priority`/`due_at` khỏi dict `values`.
- `update()` (mirror `tasks.py:280-335`) — copy nguyên xi toàn bộ khối toggle `is_private`
  (encrypt-trước-flip-true / flip-false-trước-decrypt, `tasks.py:296-323`) KHÔNG đổi gì — logic đó
  không phụ thuộc field nào bị bỏ. Vòng `for field in (...)` cuối cùng (`tasks.py:331-333`) chỉ
  còn rỗng (Note không có field nào khác để patch qua đó) — **xoá cả vòng lặp đó**, đừng để lại
  `for field in ():` chết.
- `soft_delete()`, `restore()` (mirror `tasks.py:337-364`) — copy nguyên xi, **giữ đúng chỗ
  `restore()` dùng `with_privacy_gate()` + filter `deleted_at.is_not(None)` thay vì `readable()`**
  (008f đã tách hai hàm chính vì lý do này — `readable()` sẽ tự loại các row đã xoá nên không bao
  giờ tìm thấy gì để hoàn tác).
- `list_items()`, `add_item()`, `update_item()`, `delete_item()` (mirror `tasks.py:366-445`) — copy
  nguyên xi, mọi thao tác lên `note_item` giữ `for_update=True` khi khoá cha (§1 mục 5 đã nói lý
  do — không lặp lại ở đây).

### 2.2 Router — `backend/app/web/routers/notes.py` (file mới, mirror `backend/app/web/routers/tasks.py`)

Copy nguyên xi cấu trúc `routers/tasks.py` (153 dòng) — `Database`/`CurrentSession` type alias,
`_not_found()` (đổi message "Note not found"), và đủ 9 endpoint không thiếu cái nào:

| Method | Path | Mirror của |
|---|---|---|
| GET | `/api/notes` | `list_tasks` — bỏ query param `status` (Note không có) |
| POST | `/api/notes` | `create_task` — giữ nguyên logic `TaskIdConflict`→409/`response.status_code` 201-vs-200 theo `created`, đổi tên exception |
| GET | `/api/notes/{note_id}` | `read_task` |
| PATCH | `/api/notes/{note_id}` | `update_task` |
| DELETE | `/api/notes/{note_id}` | `delete_task` |
| POST | `/api/notes/{note_id}/restore` | `restore_task` |
| GET | `/api/notes/{note_id}/items` | `list_task_items` |
| POST | `/api/notes/{note_id}/items` | `create_task_item` |
| PATCH | `/api/notes/{note_id}/items/{item_id}` | `update_task_item` |
| DELETE | `/api/notes/{note_id}/items/{item_id}` | `delete_task_item` |

`require_session` ở tầng router qua `CurrentSession = Annotated[AuthSession,
Depends(require_session)]` — copy nguyên xi, không có slice nào ship thiếu gác (luật khoá từ
`auth-brief.md`). Đăng ký `router` mới trong `backend/app/main.py` (tìm chỗ `tasks.router` đang
được include, thêm `notes.router` cạnh đó — đọc file thật để biết tên biến/hàm chính xác, đừng
đoán).

### 2.3 Frontend

**Phạm vi UI: chỉ CRUD + checklist + riêng tư + undo.** `TasksScreen.tsx` (925 dòng) đã tích luỹ
nhiều tính năng riêng của Task từ `018`/`008g`/`008k` (ghim, banner trễ hạn, ô hạn/priority,
drag-select) — **Note không có `pinned`/`due_at`/`priority` nên KHÔNG mirror các UI đó**, chỉ
mirror khung list+form+checklist+privacy-toggle+undo-toast. Đọc `TasksScreen.tsx` để lấy đúng
pattern (cách gọi `apiRequest`, cách dùng component shadcn, cách xử lý `AbortSignal.timeout`), rồi
lược bỏ phần không áp dụng cho Note thay vì mirror nguyên khối rồi để dở dang.

- `frontend/src/note-ui.ts` (mirror `task-ui.ts`, 49 dòng): `NoteFormState` (`title`, `body`,
  `isPrivate` — bỏ `priority`/`dueAt`), `NoteWritePayload` (`title: string | null`, `body_md:
  string | null`, `is_private: boolean` — `title` **nullable ở type**, khác `TaskWritePayload`),
  `NotePayload = NoteWritePayload & { id: string }`, `noteInvalidationKey`, `noteQueryKey` (Note
  không có filter trạng thái nên có thể chỉ là hằng số `['notes']`, không cần tham số `filter` như
  `taskQueryKey`), `notePayload(state)`, `canSubmitNote` — **cân nhắc**: vì title nullable ở
  backend, `canSubmitNote` không nhất thiết đòi `title.length > 0` như `canSubmitTask` — quyết định
  UX (cho phép note trống tiêu đề) là hợp lệ theo schema; nếu muốn vẫn yêu cầu tiêu đề ở tầng UI thì
  đó là lựa chọn UX được phép, không phải ràng buộc backend — ghi rõ lựa chọn nào được chọn trong
  PR description.
- `frontend/src/note-undo.ts` (mirror `task-undo.ts`, 23 dòng) — copy nguyên xi, đổi endpoint
  `/api/tasks/${id}/restore` → `/api/notes/${id}/restore`, đổi tên hàm `restoreTask`→`restoreNote`.
- `frontend/src/NoteForm.tsx` + `frontend/src/NotesScreen.tsx` (file mới) — dùng component shadcn
  đã dựng ở `008e` (không thẻ `<button>` thô, luật UI `AGENTS.md`), gọi `apiRequest` với
  `AbortSignal.timeout(20s)` đã có sẵn trong `api.ts` (008i — dùng đúng, không tự chế lại), tôn
  trọng contrast/touch-target theo `ui-brief.md` (đặc biệt viền input — không có icon ghim vì Note
  không pin được).
- Đăng ký route/tab Note trong `frontend/src/App.tsx` (đọc file thật để biết cách Task đã đăng ký,
  mirror đúng cách đó — điều hướng giữa Task/Note là quyết định UI nhỏ, chọn cách rẻ nhất khớp
  pattern hiện có, ví dụ tab/route cạnh nhau).

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
- [x] Chi tiết hoá §2 (2026-07-31) — T1 đọc trực tiếp `tasks.py`/`routers/tasks.py`/`models.py`,
      đúc 3 delta thật (title nullable + validator, thiếu 4 field, embedding loại khỏi DTO), chọn
      order mặc định cho `list()` (chưa từng quyết trước đó), và cắm cờ rủi ro chép-sai lớn nhất
      (`NoteUpdate.reject_null_required_fields` không được copy nguyên `TaskUpdate`).
- [ ] **Việc của CHỦ trước khi giao Codex:** không có công tắc môi trường nào cần bật riêng (không
      Docker/VPN mới ngoài những gì `008`/`008m` đã cần) — sẵn sàng giao ngay.
