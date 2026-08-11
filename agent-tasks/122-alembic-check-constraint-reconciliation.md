# 122 — Reconcile named CHECK metadata for Alembic 1.19

> **Executor: T2 Codex · Bậc: L2 · Effort: medium · Skill gợi ý: không cần · MCP cần: không cần.**
> **Trạng thái: DONE — 2026-08-11.**

## Mục tiêu

Chuẩn bị SQLModel metadata để Dependabot PR #122 có thể nâng Alembic từ 1.18.5 lên
1.19.0 mà `Migration QA` không báo drift cho named `CHECK` constraints. Alembic 1.19
lần đầu tự phát hiện named CHECK; plugin mặc định này phải tiếp tục hoạt động.

Root cause đã xác minh: naming convention
`ck_%(table_name)s_%(constraint_name)s` áp thêm một lần vào tên physical đã-final
trong metadata, trong khi migrations dùng `op.f()` để giữ nguyên physical name.
Đây chỉ là reconciliation metadata; không đổi biểu thức CHECK hay dữ liệu.

## Phạm vi được phép đổi

- `backend/app/domain/models.py`
- `backend/tests/test_schema_models.py`
- file task này

Canonical physical names phải giữ nguyên:

| Bảng | CHECK constraint names |
|---|---|
| `microsched.day_annotation` | `day_range` |
| `microsched.reminder_dispatch` | `ck_reminder_dispatch_subject_type`, `ck_reminder_dispatch_status`, `ck_reminder_dispatch_attempt_count` |

`DayAnnotation` dùng `sqlalchemy.schema.conv("day_range")` để đánh dấu tên đã-final.
Ba CHECK của `ReminderDispatch` dùng logical base names `subject_type`, `status`,
`attempt_count`, để naming convention render đúng ba canonical physical names.

## Không được làm

- Không thêm hay sửa Alembic migration (đặc biệt không có `0009`); migration history phải nguyên vẹn.
- Không đổi global naming convention.
- Không tắt/loại Alembic 1.19 named-CHECK plugin hoặc làm yếu `check_migration_drift`.
- Không nâng Alembic, sửa `uv.lock`, hoặc sửa Dependabot PR #122.
- Không chạy migration hay ghi lên Neon; không đọc hoặc echo secret.
- Không rename/drop/recreate bất kỳ DB constraint nào.

## Việc của chủ trước khi chạy PG lane (tùy chọn)

- Bật Docker Desktop nếu muốn chạy Postgres throwaway local. Nếu daemon không chạy,
  ghi rõ đó là environment block; không thay bằng Neon và không coi đó là test app đỏ.

## Acceptance và receipt

1. Metadata final names đúng bốn canonical names ở trên; `git diff --name-only` không
   chứa `backend/alembic/versions/`.
2. Chạy `git diff --check` và targeted test không-PG phù hợp. Chạy relevant
   `pre-commit`/`gitleaks` và dán raw output vào PR body.
3. Nếu Docker local sẵn sàng, có thể chạy relevant PG verification trên Postgres
   throwaway; nếu không, phân biệt environment block với test failure.
4. Commit tiếng Việt qua file UTF-8, có `Co-Authored-By:`. PR nhỏ vào `develop` có
   body tiếng Việt qua UTF-8 body-file, chứa raw command receipts và nói rõ Neon
   catalog/live Alembic 1.19 chưa verify nếu chưa chạy.
5. Đọc diff trước khi báo cáo; chờ CI với cadence external-run khoảng hai phút giữa
   mỗi lần kiểm tra. Không tự merge.
