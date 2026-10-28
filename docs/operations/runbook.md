# Operations runbook

Tài liệu này mô tả cơ chế repo hiện có và trách nhiệm vận hành. Lệnh có tác động production, schema, credentials hoặc dữ liệu cần đúng quyền của batch; fresh clone không có quyền hay secret của Owner.

## Deploy và release

1. Thay đổi đi qua branch riêng → PR vào `develop`. Kiểm exact head/base/diff, scope và mọi gate đang required; không đổi tên check để né gate.
2. [CI](../../.github/workflows/ci.yml) giữ **Backend checks**, **Frontend checks**, **Repository hooks**, **Migration QA**, **Production dependency check**, cùng Secret scan/Frontend e2e và các gate configured khác. Required status/ruleset là cấu hình sống, cần query mới trước merge.
3. Executor có quyền merge dùng exact-head compare-and-swap (`gh pr merge --match-head-commit <head>`); drift phải reconcile. [Deploy workflow](../../.github/workflows/deploy.yml) chạy khi push `develop`, không chờ một lượt push CI thứ hai. Merge có thể kích hoạt deploy; một quyền viết docs không tự cấp quyền merge.
4. Docker multi-stage build frontend bằng Node 24 và runtime Python 3.14 với `uv sync --frozen --no-dev`. Một process không-root phục vụ app. Không có Alembic trong bước deploy.
5. Sau khi production được xác minh và release được duyệt, PR qualified revision vào `main`, rồi tag/release theo quyền của release executor. `main` là release label; không force-reset để đuổi kịp `develop`. Changelog v2.0 là nội dung mốc sản phẩm, không tự chứng minh tag đã tồn tại.

GitHub scheduled/community/security-update consumers thường đọc default branch; kiểm branch thực của mỗi consumer trước khi tuyên bố đã kích hoạt. Dependabot version-update `target-branch` và security-update default-branch behavior khác nhau. Workflow/default-branch changes cần đến `main` qua release flow phù hợp.

## Readiness và cấu hình

[fly.toml](../../fly.toml) khai báo region `sin`, một machine always-on, RAM 512 MB và swap 512 MB; [Dockerfile](../../Dockerfile) là build/runtime contract. Đây là cấu hình source, không phải inventory hạ tầng live.

- `/api/healthz`: liveness không query DB, dùng cho routine Fly health check.
- `/api/readyz`: readiness có kiểm DB. Production proof cần `status=ok`, `db=up` và `commit` khớp **exact deployed SHA**. `healthz=ok` chưa đủ.
- Workflow smoke có retry hữu hạn sau deploy. Không biến readyz thành poll thường xuyên hoặc thêm cron làm mất cửa sổ idle/quota của Neon.
- In-process cron đã là cơ chế nhắc nền; thay cadence/retry/service cần tính lại tài nguyên, fallback và rollback. Model/provider prices hay flags trong receipt cũ không chứng minh cấu hình live.

Secrets giữ ngoài Git; runtime chỉ nhận `DATABASE_URL` của role app. Không đưa owner/migrator URL lên Fly. Xem [auth](../auth-brief.md), [security](../security-brief.md) và [.env.example](../../backend/.env.example). Không in secret khi đối chiếu config.

## Backup và recovery

Backup là trách nhiệm Owner vận hành, tách khỏi deploy. Giữ database dump, encryption key và code/config revision tương ứng trong các nơi có kiểm soát truy cập; key cần được bảo quản riêng với dữ liệu mã hóa. Bản dump mà thiếu key có thể không phục hồi được nội dung. Dùng chính sách 3-2-1 và **restore rehearsal** để chứng minh khả năng đọc/giải mã, schema, row counts và quyền app/migrator.

Owner có utility backup riêng và kho backup local do máy Owner quản lý. Chúng **không được phân phối trong repository/fresh clone**. Tài liệu không cung cấp một command giả định script local đó đã có sẵn. Người vận hành clone mới phải chọn/kiểm công cụ PostgreSQL phù hợp và cấu hình riêng; không sao chép credential hoặc backup cá nhân vào repo.

Khi phục hồi: xác định revision và backup đích, dừng writer theo maintenance plan được duyệt, restore thử vào target cô lập, kiểm role/schema/decryption/dữ liệu và chạy acceptance phù hợp trước cutover. Neon branch create/delete/Restore/Sync do Owner trực tiếp thao tác. Không downgrade/round-trip live Neon, không ghi thử vào predecessor stores. Backup/key/stash không thuộc cleanup mặc định.

## Migration và rollback

Schema changes có lane riêng: review migration/DDL, một Alembic head, intentional-DROP guard, PG drift/round-trip/grants, backup identifier/time và restore rehearsal trước production. [Data model](../engineering/data-model.md) và [0017 safety card](../migrations/0017-mimi-task-collection-plan.md) mô tả các bất biến hiện có. Các script bootstrap/verify trong [backend/scripts](../../backend/scripts) là công cụ privileged có phạm vi cụ thể, không phải startup routine.

Rollback application về revision/config đã biết tương thích. Nếu schema mới có tombstone/receipt/notification data, app cũ có thể chỉ được dùng **read-only**; không giả định rollback code cho phép writer cũ. Ưu tiên roll-forward hoặc feature-off đã được kiểm chứng trong plan của revision. Không bỏ dữ liệu để làm downgrade xanh. Mỗi schema operation giữ actor/grant/target/command/exit và catalog evidence riêng; successful deploy không chứng minh migration đã chạy.

Sự cố timeout/unknown phải kiểm trạng thái durable, deployment revision và receipt trước retry. Không replay mù domain write/provider call. Production không phải môi trường seed/fault/load test; dùng môi trường disposable đúng quyền.
