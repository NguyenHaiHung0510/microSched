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
| manual `calendar_events` | one new `calendar_source` / events | chỉ rows từ source `v1_sqlite_schedule` có `external_uid LIKE 'manual\_%' ESCAPE '\'`; UID/source khác fail-closed |
| `priorities` | cột priority task/note | không có bảng target |
| app settings/version/history/log cũ | — | không map |

Timestamps nguồn đã `timestamptz`: giữ instant, canonical verify UTC; không suy đoán/ép timezone.
`priority_id=NULL` giữ `priority=NULL`; chỉ priority name được tham chiếu mà lạ/trùng mới fail-closed.
Manual target source có UUIDv7 mới được ký trong manifest; formula cột đầy đủ (kể cả target defaults/null,
event visibility và timestamp) nằm ở Task 012, không được suy diễn từ server default.

## 3. Cutover contract

Chi tiết executable/DRAFT nằm ở [`agent-tasks/012-cutover-migration.md`](../agent-tasks/012-cutover-migration.md).
Task 012 không được chạy trước khi Task 022 đã production-accepted để mọi task sau import còn xem được.

**📝 2026-08-20 — exact-head T3 corrections folded, still DRAFT:** toàn bộ domain content hiện hữu ở Neon
là mock/trash và được purge atomically khi import. Chỉ preserve `app_setting`, `session`,
`push_subscription`, `alembic_version`; target dùng pre/post canonical proof (optional small encrypted
preserve export), không full target dump. Source bắt buộc full encrypted, restore-tested dump.

Manifest có hai phase: source expected sau freeze, rồi exact Phase-B target snapshot sau khi Fly dừng; chỉ
owner approval ký trên `run_id` + manifest digest + snapshot digest mới chạy dry-run/commit/verify/recover.
Ngay trong `microsched_app` transaction, trước DELETE đầu tiên, toàn bộ mapped + purge-only pre-state phải
exact-match signed snapshot; drift abort. Mapped components exact-match transformed count/IDs/full-field
digest; mọi purge-only table (`day_annotation`, tracker/subscription/reminder, `message`, `audit_log`) must
end count 0 + canonical empty digests.

`app_setting`/`session`/`push_subscription` là **toàn bộ** app-readable preserve set: mọi app transaction
assert đủ đúng ba component này. `alembic_version`/catalog chỉ được attest qua bounded migrator/owner
read-only connection trước/sau operation rồi đóng; không kế thừa app assertion hay mở rộng grant. DML luôn
là `microsched_app`. `--recover` còn require failure receipt có hạn, bind run/manifest/failure và inventory
failed-run với Fly never restarted; source archived rows remain fail-closed pending owner decision.

Mọi digest pre-state/recovery cho 8 purge-only tables dùng field-order explicit ở Task 012 (không `SELECT *`
hay column-order ngầm), gồm mọi field/timestamp/JSON/ciphertext cần thiết để một thay đổi một cột cũng abort.

## 4. Vệ sinh vận hành

- Không chạy hai app ghi song song sau freeze; đó là split-brain cũ cần tránh.
- Credentials và dump/dữ liệu cá nhân không vào repo/PR/log. Dump dùng encryption, timestamp, restore verify.
- Chỉ owner workstation chạy real cutover; Fly sole Machine dừng trong maintenance, sau đó start exactly one
  và verify visual + exact `/api/readyz.commit` SHA + `db=up`.
- Sau atomic manual-event proof/Fly start, owner re-import `.ics` canonical qua 010a. Count và visual receipt
  cho các file là bước riêng; final calendar = manual migrated + canonical file imports, không phải chỉ tập
  calendar của transaction.
