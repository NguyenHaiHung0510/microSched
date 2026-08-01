# 020 — Ba cột giữ dữ liệu app cũ (`task.completed_at`, `note.pinned`, `note.priority`)

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L2
> · Skill gợi ý: không cần · MCP cần: không cần.**
> **Trạng thái: DRAFT — viết bởi T1 (Opus 5) 2026-08-01, chủ đã chốt hướng, chưa duyệt bản chi tiết.**
> Phản biện: 1 lượt là đủ (tiền lệ `008g` — migration thuần cộng cột, theo đúng khuôn `0004`).

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

**Migration này là `0006`, KHÔNG phải `0005`.** `agent-tasks/010a-calendar-import-crud.md` §3 đã giữ
chỗ `0005` (`0005_calendar_description_and_visibility.py`) và nhắc số đó ở nhiều mục.

⇒ **Chỉ bắt đầu task này sau khi `010a` đã merge vào `develop`.** Nếu `backend/alembic/versions/`
chưa có file `0005_*`, **dừng lại và báo** — đặt `down_revision = "0005"` khi revision đó chưa tồn tại
sẽ làm `alembic upgrade head` gãy ngay trên CI.

## 2. Migration `0006`

File mới `backend/alembic/versions/0006_legacy_preserving_columns.py`, theo đúng khuôn `0004_task_pinned.py`.

| Cột | Bảng | Kiểu | Ghi chú |
|---|---|---|---|
| `completed_at` | `task` | `TIMESTAMPTZ NULL` | Không backfill. Hàng cũ để `NULL` — nghĩa là "không biết", không phải "chưa xong". |
| `pinned` | `note` | `BOOLEAN NOT NULL DEFAULT false` | Y hệt `task.pinned` (`0004`) để hai thực thể cùng hình dạng. |
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

## 4. Cố ý KHÔNG làm

- **Không** dựng UI ghim/ưu tiên cho note. Hai cột đó ở task này chỉ để **`012` có chỗ đổ dữ liệu vào**;
  cho tới khi có UI, chúng chỉ đọc được bằng SQL. Đây là đánh đổi có chủ ý: thêm cột bây giờ rẻ, thêm
  cột sau khi đã cutover thì phải backfill. Nếu chủ muốn UI, mở task riêng (`021`) sau khi nhìn thấy
  dữ liệu thật đã về.
- **Không** đụng `task.status` CHECK. Việc `archived` thuộc `012` §3, đang hoãn.
- **Không** tự áp migration lên Neon nếu chưa được chủ bật đèn — theo luật `CLAUDE.md`
  ("migrations are never auto-applied on deploy"). `010a` §581 có tiền lệ chủ cho Codex tự chạy;
  **task này chưa có tiền lệ đó**, phải hỏi.

## 5. Acceptance (chạy được, không phải "làm cho tốt")

1. `uv run alembic upgrade head` rồi `alembic downgrade -1` rồi `upgrade head` lại — cả ba xanh.
2. `uv run python -m scripts.check_migration_drift` ⇒ `migration_drift=empty`.
3. `uv run python -m scripts.check_migration_drops` ⇒ `migration_drop_guard=ok`.
4. `uv run pytest` xanh, có **test mới**: tick xong ⇒ `completed_at` không NULL · mở lại ⇒ về NULL ·
   đổi `title` mà không đụng `status` ⇒ `completed_at` giữ nguyên · ghi `note.priority='p4'` ⇒ DB từ chối.
5. `uv run ruff check` + `uv run ruff format --check` sạch — **chạy đúng danh sách lệnh trong
   `.github/workflows/ci.yml`**, không chạy danh sách nhớ trong đầu.
6. Sau khi áp lên Neon: query thật `information_schema.columns` thấy đủ 3 cột, và `pg_constraint`
   thấy CHECK mới của `note.priority`. **`alembic current` không tính là bằng chứng.**
