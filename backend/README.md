# Backend

## Chạy development

```powershell
cd backend
uv sync
Copy-Item .env.example .env
uv run uvicorn app.main:create_app --factory --reload
```

`backend/.env` là file local duy nhất được đọc. Ba URL có ba vai tách biệt:

- `NEON_OWNER_URL`: owner Neon, chỉ script bootstrap dùng; không lên Fly.
- `NEON_MIGRATOR_URL`: role `microsched_migrator` sở hữu schema và chạy Alembic;
  không lên Fly.
- `DATABASE_URL`: role runtime `microsched_app`, chỉ CRUD; đây là URL duy nhất lên Fly.

Không dùng URL owner hoặc migrator cho runtime dù kết nối vẫn chạy được.

## Bootstrap Neon và migration

Sau khi tự đặt `NEON_OWNER_URL` thật trong `backend/.env`, bootstrap sẽ tạo hai role
giới hạn, schema `microsched`, extension `pgvector`, và có thể sinh hai URL role còn
thiếu mà không in secret ra terminal:

```powershell
cd backend
uv run python -m scripts.bootstrap_neon --provision-local-env
uv run alembic upgrade head
```

Kiểm tra schema thật bằng hai role không-owner:

```powershell
uv run python -m scripts.verify_neon
```

Chủ tự đặt `DATABASE_URL` lên Fly sau khi merge. Không bao giờ đặt
`NEON_OWNER_URL` hoặc `NEON_MIGRATOR_URL` vào Fly secrets.

Migration `0001` giả định bootstrap đã tạo schema và extension. Cột
`note.embedding` là `vector` nullable không dimension, không HNSW; dimension và index
được giữ lại cho migration riêng của AI Bước 1.

Sau đó kiểm tra health endpoint:

```powershell
curl http://localhost:8000/api/healthz
```

## Kiểm tra

```powershell
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -m scripts.check_migration_drops
uv run python -m scripts.check_migration_drift
```

Job CI **Migration QA** chạy Postgres 18 + pgvector, `upgrade head`, drift-check,
`downgrade base`, `upgrade head` và drift-check lần cuối. Job không dùng secret Neon.
