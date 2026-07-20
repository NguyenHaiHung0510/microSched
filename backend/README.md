# Backend

## Chạy development

```powershell
cd backend
uv sync
uv run uvicorn app.main:create_app --factory --reload
```

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
```
