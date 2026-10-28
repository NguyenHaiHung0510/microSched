# Data model và schema ownership

Nguồn vật lý hiện hành là [domain models](../../backend/app/domain/models.py), [Mimi models](../../backend/app/agent/models.py) và [Alembic revisions](../../backend/alembic/versions). Dùng `uv run --frozen alembic heads` để biết head của checkout; số revision trong receipt cũ không chứng minh schema đang chạy.

## Entity và quan hệ

| Nhóm | Quan hệ và dữ liệu chính |
|---|---|
| Task / TaskItem | Task giữ title/body, status/priority/pin, due precision và collection version. Child checklist có position, identity và tombstone; writes liên quan khóa parent trước child |
| Note / NoteItem | Markdown và checklist; title/body có thể chưa đặt. Child visibility đi theo Note |
| CalendarSource / CalendarEvent / DayAnnotation | Nguồn ICS hoặc manual, event có thời gian; annotation theo ngày. Calendar event không có cơ chế soft-delete “Don't care” |
| TrackerGroup / Tracker / Entry | Nhóm tracker; tracker có direction/input mode/unit và cấu hình nhắc. Entry ghi occurrence, quantity/amount/list amount; phân biệt tiền với lượng và timestamp |
| Subscription | Liên kết tracker và các entry gia hạn; started/expires là DATE, trạng thái suy ra từ ngày/hủy thay vì một status độc lập |
| Reminder | Recurring dispatch/batches, one-shot reminder và occurrence-handled history; nguồn typed FK, version/state/attempt metadata ngăn replay sai và giữ lịch sử |
| AuthSession / AppSetting / PushSubscription | Session token digest, thời hạn/private gate; setting do app quản lý; đăng ký push theo thiết bị |
| Mimi | Conversation → messages/runs/events/provider calls; change sets → execution receipts/refresh markers; feedback/evidence; device preferences và notification intent/delivery |

Funding/income Entry dùng cùng model và domain rules hiện có, không tạo một store tiền riêng. Tracker money dùng VND và metadata queryable; text dài giữ đầy đủ, UI chỉ thu gọn phần hiển thị. Giá trị amount và quantity có ý nghĩa riêng theo input mode; đọc constraint/serializer hiện hành trước khi đổi loại tracker hoặc ghi dữ liệu.

## Invariants

- UUIDv7 cho identity; timestamp timezone-aware, thời gian hệ thống theo UTC, hiển thị theo timezone của app. DATE dùng cho ý nghĩa ngày thuần túy, không chuyển lén thành một instant.
- Enum vật lý dùng TEXT + CHECK. FK, unique/partial indexes và trigger là một phần contract, không chỉ ORM validation.
- `updated_at` và collection version hỗ trợ concurrency. Soft-delete khác hard-delete; không thay tombstone bằng xóa thật để đơn giản hóa consumer.
- Privacy và deletion gate khai báo tường minh; child phải đọc qua parent đúng trục. Xem [reading-gate registry](../verification/reading-gates.md).
- Prose và các giá trị nhạy cảm dùng encryption boundary của app; master key nằm ngoài DB/repo. Encrypted columns không được đưa vào pgvector/FTS. Mã hóa không đồng nghĩa với cờ private: dữ liệu public được mã hóa vẫn có thể được app giải mã theo contract.
- Domain effects, Mimi execution receipt và durable refresh marker phải cùng transaction khi contract yêu cầu. Provider calls/cost và outcome unknown giữ provenance, không suy ra zero từ dữ liệu thiếu.

## Roles và migration

`DATABASE_URL` dùng role runtime CRUD; `NEON_MIGRATOR_URL` dùng role sở hữu schema/DDL; `NEON_OWNER_URL` chỉ dùng bootstrap do Owner vận hành. Hai URL đặc quyền không lên Fly. Cấu hình mẫu: [backend/.env.example](../../backend/.env.example).

Alembic changes phải review DDL, có một head, kiểm DROP có chủ ý, drift-check và round-trip trên PostgreSQL/pgvector dùng một lần. [Migration QA](../../.github/workflows/ci.yml) thực hiện bootstrap roles, upgrade, drift, downgrade/re-upgrade, grants và tests `pg`. Không round-trip/downgrade live Neon. Production migration cần backup/restore rehearsal và quyền riêng; deploy code không chạy nó.

Giữ [0017 impact/rollback safeguards](../migrations/0017-mimi-task-collection-plan.md), [forward SQL](../migrations/0017-mimi-task-collection-forward.sql) và [execution record](../migrations/0017-mimi-task-collection-execution.md) khi xử lý collection schema. Đây là phạm vi revision cụ thể; không phải lời cho phép thực thi lại lên production. Runbook là điểm bắt đầu cho backup/recovery và thay đổi schema mới.
