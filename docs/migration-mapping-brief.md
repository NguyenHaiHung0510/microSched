# Migration mapping brief — dữ liệu cũ → microSched mới

> Decision record tự-chứa. Nguồn migration là Postgres local `microschedule_v2`; SQLite `todo.db` là tập
> chết, read-only reference, không đụng. Count đo 18/07/2026 chỉ là ảnh chụp lịch sử, không phải hợp đồng.

## 1. Nguồn thật

| Store | Trạng thái | Quy tắc |
|---|---|---|
| PostgreSQL `microschedule_v2` local | nguồn sống cho tới cut-over | chỉ read-only; freeze tại exact cut-off |
| SQLite `todo.db` | chết/tập con cũ | bỏ qua, không migrate |

microSched sau cutover dùng duy nhất Neon Postgres, role riêng giới hạn. Source local giữ archive read-only,
không thành store song song để tiếp tục ghi.

## 2. Mapping khái niệm

| v2 source | target | Ghi chú |
|---|---|---|
| `tasks` / `task_items` | `task` / `task_item` | giữ historical UUID và timestamp; priority 6 mức → `p1..p3` |
| `notes` / `note_items` | `note` / `note_item` | prose đầy đủ; `is_done` → `is_completed` |
| manual `calendar_events` | one new `calendar_source` / events | chỉ `external_uid=manual_*`; lịch gốc import lại từ `.ics` |
| `priorities` | cột priority task/note | không có bảng target |
| app settings/version/history/log cũ | — | không map |

Timestamps nguồn đã `timestamptz`: giữ instant, canonical verify UTC; không suy đoán/ép timezone. `calendar`
manual target source có UUIDv7 mới được ghi vào manifest, còn event giữ ID hợp lệ theo contract cutover.

## 3. Cutover contract

Chi tiết executable/DRAFT nằm ở [`agent-tasks/012-cutover-migration.md`](../agent-tasks/012-cutover-migration.md).
Task 012 không được chạy trước khi Task 022 đã production-accepted để mọi task sau import còn xem được.

**📝 2026-08-16 — owner-approved refresh:** toàn bộ domain content hiện hữu ở Neon là mock/trash và được
phép purge atomically khi import. Chỉ preserve `app_setting`, `session`, `push_subscription`,
`alembic_version`; target cần pre/post canonical count, ID set và full-row digest (optional small encrypted
preserve export), không full target dump. Source bắt buộc full encrypted verified dump. Mọi mapped component
phải exact-match transformed source count/IDs/full field digest at the source-freeze cut-off; source archived
rows are fail-closed pending owner decision.

## 4. Vệ sinh vận hành

- Không chạy hai app ghi song song sau freeze; đó là split-brain cũ cần tránh.
- Credentials và dump/dữ liệu cá nhân không vào repo/PR/log. Dump dùng encryption, timestamp, restore verify.
- Chỉ owner workstation chạy real cutover; Fly sole Machine dừng trong maintenance, sau đó start exactly one
  và verify visual + exact `/api/readyz.commit` SHA + `db=up`.
