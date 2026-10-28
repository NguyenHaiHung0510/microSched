# microSched backend

FastAPI modular monolith, Python 3.14, SQLModel/Alembic và PostgreSQL/pgvector. Runtime và dev dependencies khóa trong [uv.lock](uv.lock).

Từ thư mục này: `uv sync --frozen`, chuẩn bị `.env` riêng từ [.env.example](.env.example), rồi `uv run --frozen uvicorn app.main:create_app --factory --reload`.

[Development](../docs/engineering/development.md) là hướng dẫn setup/test chuẩn; [data model](../docs/engineering/data-model.md) mô tả DB roles và constraints; [operations](../docs/operations/runbook.md) giữ migration/backup/deploy responsibilities. Runtime không dùng owner/migrator credentials và deploy không tự chạy migration. [Mimi](../docs/mimi/README.md) có README PARTIAL riêng.
