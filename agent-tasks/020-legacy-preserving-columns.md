# 020 — Ba cột giữ dữ liệu app cũ (`task.completed_at`, `note.pinned`, `note.priority`)

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L2
> · Skill gợi ý: không cần · MCP cần: không cần.**
> **Trạng thái: OWNER-APPROVED — chủ duyệt triển khai 2026-08-13; migration đã refresh theo head
> thật `0008` trước khi thi công. Chưa authorize áp migration lên Neon hoặc merge.**
> Phản biện: đã chạy chung một vòng với `012` 2026-08-02 (không tách riêng 1 lượt như dự tính ban đầu,
> vì `012` viết trước làm lộ ra `020` không chỉ "migration thuần cộng cột" — cột `completed_at` có
> logic nối dây thật). T1 đã vá mọi finding xác nhận đúng (xem §6 cuối file).

## 0. Vì sao có task này

Đang viết spec `012` (cutover), map cột-với-cột giữa Postgres cũ `microschedule_v2` và Neon thì lộ ra
**ba cột ở app cũ không có chỗ đứng ở app mới**. Chốt với chủ 2026-08-01: **không bỏ** — mất dữ liệu
vĩnh viễn không đáng đổi lấy schema gọn.

Bằng chứng, đo trên **Neon production** ngày 2026-08-01 (query read-only), không phải suy từ ORM:

```
migration_drift=empty      ← models.py khớp Neon tuyệt đối (compare_type + compare_server_default)

task:  id created_at updated_at title body_md status priority due_at is_private deleted_at pinned
note:  id created_at updated_at title body_md embedding is_private deleted_at
```

Đối chiếu DDL thật của nguồn cũ (`docs/_local/v2-schema.sql`, dump 2026-08-01):

| Cột app cũ | App mới | Hệ quả nếu không làm gì |
|---|---|---|
| `tasks.completed_at timestamptz NULL` | không có | mất mốc hoàn thành của mọi task đã xong |
| `notes.pinned bool NOT NULL` | `note` không có ghim (chỉ `task` có) | mất ghim của các note đang ghim |
| `notes.priority_id uuid NULL` | `note` không có priority | mất mức ưu tiên của note |

**Không thuộc phạm vi task này:** `calendar_event.description` — `010a` §3 đã thêm `description_md`
trong migration `0005`, không cần làm lại. Và `tasks.status = 'archived'` (giá trị thứ ba mà CHECK
mới từ chối) — đó là **thêm trạng thái**, không phải thêm cột; chủ chốt **tạm hoãn**, ghi lại ở
`012` §3.

## 1. Phụ thuộc cứng — đọc trước khi gõ số revision

**Migration này là `0009`, `down_revision = "0008"`.** Kiểm cây migration trên `develop` ngày
2026-08-13 thấy `0005_calendar_description_and_visibility.py`, `0006_day_annotation.py`,
`0007_reconcile_day_annotation_constraint.py` và `0008_push_subscription_and_reminder_dispatch.py`
đã chiếm các revision trước đó.

⇒ **Chỉ bắt đầu task này khi `0008_*` đã có trong `backend/alembic/versions/`.** Nếu head thật đổi
thêm trước lúc branch được dựng/rebase, dừng và refresh lại revision/down-revision; không tạo nhánh
migration song song từ một head cũ.

## 2. Migration `0009`

File mới `backend/alembic/versions/0009_legacy_preserving_columns.py`, theo đúng khuôn `0004_task_pinned.py`.

| Cột | Bảng | Kiểu | Ghi chú |
|---|---|---|---|
| `completed_at` | `task` | `TIMESTAMPTZ NULL` | Không backfill. Hàng cũ để `NULL` — nghĩa là "không biết", không phải "chưa xong". |
| `pinned` | `note` | `BOOLEAN NOT NULL DEFAULT false` | Y hệt `task.pinned` (`0004`) để hai thực thể cùng hình dạng — **kể cả** cách khai ở `models.py`: `sa_column=Column(Boolean, nullable=False, server_default=text("false"))` (`Task.pinned`, `models.py:135-137`), không chỉ Pydantic `default=False`. Thiếu `server_default` là drift thật: `check_migration_drift` so `compare_server_default`, migration có `server_default` mà model không khai cũng bị soi ra lệch. *(2026-08-02, làm rõ sau phản biện T3.)* |
| `priority` | `note` | `TEXT NULL` + `CHECK (priority IS NULL OR priority IN ('p1','p2','p3'))` | Cùng CHECK với `task.priority` — dùng lại nguyên văn ràng buộc ở `models.py:107-110`, đừng phát minh thang khác. |

`downgrade()` drop cả ba (drop trong `downgrade` không cần nhãn review — `scripts/check_migration_drops.py`
chỉ soi thân `upgrade`).

Cập nhật `backend/app/domain/models.py` tương ứng: `Task.completed_at`, `Note.pinned`, `Note.priority`
+ `CheckConstraint` mới trong `Note.__table_args__` (đặt tên `priority_values`, khớp naming convention
đang có). **Bắt buộc**: `uv run python -m scripts.check_migration_drift` phải in `migration_drift=empty`
sau khi áp — nếu model và migration lệch nhau, CI đỏ.

## 3. Nối dây `task.completed_at` (phần duy nhất có logic)

Một cột không ai ghi là một cột chết. Trong task store (`backend/app/domain/tasks.py`):

- khi `status` chuyển `open → completed` ⇒ `completed_at = now()`;
- khi chuyển `completed → open` ⇒ `completed_at = None`;
- khi update không đụng `status` ⇒ **không chạm** `completed_at` (cẩn thận với `exclude_unset=True`);
- `TaskRead` thêm `completed_at` để client đọc được. **Không** thêm vào `TaskCreate`/`TaskUpdate` —
  đây là trường do server suy ra, không phải do client khai.

> 📝 **2026-08-02 — LÀM RÕ hai điểm sau phản biện T2 + T3, "chuyển" đọc mơ hồ dễ cài sai ngay lần đầu.**
>
> **1. `PATCH /task/{id}` — bắt buộc so `old_status` với `new_status`, không so một chiều.**
> `TaskStore.update()` hiện đã có sẵn khuôn đúng: `changes = payload.model_dump(exclude_unset=True)`
> rồi set field trong loop (`tasks.py:294`, `339-341`). Cắm `completed_at` vào **đúng** loop đó, nhưng
> phải lấy `old_status = task.status` **trước** khi gán field mới, rồi chỉ set mốc khi
> `"status" in changes and changes["status"] != old_status`:
> - `old_status != "completed"` và `new_status == "completed"` ⇒ `completed_at = now()`.
> - `old_status == "completed"` và `new_status == "open"` ⇒ `completed_at = None`.
> - mọi trường hợp khác (kể cả `"status" in changes` nhưng `new_status == old_status` — ví dụ client
>   PATCH gửi lại nguyên `status` hiện tại kèm đổi `title`) ⇒ **không chạm** `completed_at`.
>
> Nếu chỉ viết "khi status chuyển sang completed thì set `completed_at=now()`" mà không neo vào
> `old_status`, cài tự nhiên nhất (`if changes.get("status") == "completed": completed_at = now()`) sẽ
> **ghi đè mốc hoàn thành cũ** mỗi lần PATCH một task đã completed từ trước kèm `status: "completed"`
> trong payload (kể cả khi giá trị không đổi) — mất đúng mốc mà `012` vừa cutover từ dữ liệu cũ sang.
> Test bắt buộc thêm: PATCH `{"status":"completed"}` **hai lần liên tiếp** trên cùng một task ⇒
> `completed_at` của lần gọi thứ hai phải **bằng hệt** lần đầu, không nhảy tới `now()` mới.
>
> **2. `POST /task` với `status="completed"` ngay từ đầu — hiện KHÔNG được cutover-020 nối dây.**
> `TaskCreate` cho phép `status: TaskStatus = "open"` bao gồm giá trị `"completed"` (`tasks.py:58,64`),
> và `TaskStore.create()` ghi thẳng `payload.status` (`tasks.py:235`) mà không đụng `completed_at`. Kết
> quả: tạo task mới với `status="completed"` ngay từ `POST` sẽ để lại `completed_at = NULL` — một task
> "đã xong" nhưng không có mốc xong, chính cái lỗ mà cột này sinh ra để vá. Không cấm giá trị đó ở
> `TaskCreate` (đường thi công `008`/`009` đã cho phép, không phải phạm vi task này để đổi), chỉ cần
> đối xứng với luật `update()`: trong `TaskStore.create()`, nếu `payload.status == "completed"` thì set
> `values["completed_at"] = now()` cùng lúc set `status`. Test bắt buộc thêm: `POST /task` với
> `status:"completed"` ⇒ response có `completed_at` khác `null`.

## 4. Cố ý KHÔNG làm

- **Không** dựng UI ghim/ưu tiên cho note. Hai cột đó ở task này chỉ để **`012` có chỗ đổ dữ liệu vào**;
  cho tới khi có UI, chúng chỉ đọc được bằng SQL. Đây là đánh đổi có chủ ý: thêm cột bây giờ rẻ, thêm
  cột sau khi đã cutover thì phải backfill. Nếu chủ muốn UI, mở task riêng (`021`) sau khi nhìn thấy
  dữ liệu thật đã về.
- **Không** đụng `task.status` CHECK. Việc `archived` thuộc `012` §3, đang hoãn.
- **Không** tự áp migration lên Neon nếu chưa được chủ bật đèn — theo luật `CLAUDE.md`
  ("migrations are never auto-applied on deploy"). `010a` §581 có tiền lệ chủ cho Codex tự chạy;
  **task này chưa có tiền lệ đó**, phải hỏi.
- **Không** chạy `alembic downgrade` nhắm vào Neon, kể cả để test. `backend/alembic/env.py:19,27,34-36`
  đọc thẳng `neon_migrator_url` từ `backend/.env` mà **không có guard chặn remote host** — không có gì
  ở tầng Alembic tự ngăn một `downgrade -1` gõ nhầm chạy lên Neon thật. Round-trip test ở §5 mục 1
  **chỉ được chạy trên Postgres throwaway local** (khuôn CI hiện có), không phải trên biến môi trường
  trỏ Neon. *(2026-08-02, thêm sau phản biện T2 — phát hiện §5 mục 1 và luật này ở ngay phía trên nó
  có thể tự mâu thuẫn nếu không nói rõ round-trip chạy ở đâu.)*

## 5. Acceptance (chạy được, không phải "làm cho tốt")

1. `uv run alembic upgrade head` rồi `alembic downgrade -1` rồi `upgrade head` lại — cả ba xanh, **chạy
   trên Postgres throwaway local/CI** (§4 — không phải Neon).
2. `uv run python -m scripts.check_migration_drift` ⇒ `migration_drift=empty`.
3. `uv run python -m scripts.check_migration_drops` ⇒ `migration_drop_guard=ok`.
4. `uv run pytest` xanh, có **test mới**: tick xong ⇒ `completed_at` không NULL · mở lại ⇒ về NULL ·
   đổi `title` mà không đụng `status` ⇒ `completed_at` giữ nguyên · PATCH `{"status":"completed"}` **hai
   lần liên tiếp** trên task đã completed ⇒ `completed_at` không đổi giữa hai lần · `POST /task` với
   `status:"completed"` ⇒ `completed_at` khác `null` ngay từ response đầu · ghi `note.priority='p4'` ⇒
   DB từ chối.
5. `uv run ruff check` + `uv run ruff format --check` sạch — **chạy đúng danh sách lệnh trong
   `.github/workflows/ci.yml`**, không chạy danh sách nhớ trong đầu.
6. Sau khi áp lên Neon: query thật `information_schema.columns` thấy đủ 3 cột, và `pg_constraint`
   thấy CHECK mới của `note.priority`. **`alembic current` không tính là bằng chứng.**

## 6. Vòng phản biện T2 + T3 (2026-08-02) — đã vá, ghi lại để không lặp lại

Chạy chung một vòng với `012` (xem `012` §10 để biết đầy đủ setup). Phần liên quan tới file này:

**Đã xác nhận đúng và vá trực tiếp** (dated note `2026-08-02` tại từng chỗ):
- **[MAJOR, T2]** §3 chỉ nói "khi status chuyển open→completed" mà không nêu cơ chế so `old_status` với
  `new_status` — cài tự nhiên nhất theo câu chữ gốc (`if new_status == "completed": completed_at =
  now()`) sẽ ghi đè mốc hoàn thành cũ mỗi lần PATCH một task **đã** completed kèm `status:"completed"`
  trong payload. Đã viết lại thành quy tắc so hai trạng thái tường minh + test PATCH-hai-lần-liên-tiếp.
- **[MAJOR, T2]** `POST /task` với `status="completed"` ngay từ đầu không được nối dây — `TaskCreate`
  cho phép giá trị đó (`tasks.py:58,64`), `TaskStore.create()` ghi thẳng `status` mà không đụng
  `completed_at` (`tasks.py:235`) ⇒ ra một task "đã xong" nhưng `completed_at=NULL`. Đã thêm luật đối
  xứng cho nhánh create + test.
- **[BLOCKER, T2]** §5 mục 1 (round-trip `upgrade → downgrade -1 → upgrade`) không nói rõ chạy ở đâu,
  trong khi `alembic env.py` đọc thẳng `NEON_MIGRATOR_URL` không có guard chặn remote host — nguy cơ
  `downgrade` chạy nhầm lên Neon. Đã ghi cứng: round-trip chỉ chạy trên Postgres throwaway local/CI.
- **[MINOR, T3]** "Y hệt `task.pinned`" không nói rõ có bao gồm `server_default=text("false")` ở
  `models.py` hay chỉ Pydantic `default=False` — thiếu `server_default` là drift thật dưới
  `compare_server_default`. Đã làm rõ: sao chép nguyên cách khai, không chỉ giá trị.

**Không có finding nào bị xác nhận sai** ở phần dành cho file này (khác với `012`, nơi một finding của
T3 bị bác sau khi kiểm DDL thật — xem `012` §10).
