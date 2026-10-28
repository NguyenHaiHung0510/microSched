# Development và kiểm tra

Fresh clone cần Git (kèm Git LFS để tải hai ảnh tài liệu Mimi), Python 3.14 + uv, Node 24 + npm. Các lệnh dưới dùng PowerShell và bắt đầu từ repository root. Source commands chuẩn nằm trong [pyproject](../../backend/pyproject.toml), [package.json](../../frontend/package.json) và [CI](../../.github/workflows/ci.yml).

## Cài và chạy

```powershell
git lfs pull
cd backend
uv sync --frozen
Copy-Item .env.example .env
uv run --frozen uvicorn app.main:create_app --factory --reload
```

Chỉ copy `.env.example` khi chưa có `.env`; điền cấu hình local riêng, không in/commit secret. Backend đọc `backend/.env`, mặc định settings nghiêm theo production; đặt `APP_ENV=local` cho local development. Runtime dùng DB role CRUD; bootstrap/migration có credential và quyền riêng. Fresh clone không có DB/data/secret của Owner và không tự được phép tạo/sync/scrub Neon.

Mở terminal thứ hai:

```powershell
cd frontend
npm ci
npm run dev
```

Vite proxy `/api` và `/auth` về backend `http://localhost:8000`. Nếu cần tuple khác, cấu hình `VITE_BACKEND_ORIGIN` rõ ràng và freeze origin/ports cho QA. Local dev-session chỉ tồn tại khi guard local được bật đúng contract; không phải đường đăng nhập production. [QA framework §2.1](../qa-framework.md) giữ trình tự Owner sync → authorized scrub → synthetic/local auth.

## Kiểm tra tương ứng CI

Trong `backend`:

```powershell
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -m "not pg"
uv run --frozen python -m scripts.check_migration_drops
```

Trong `frontend`:

```powershell
npm run lint
npm test
npm run build
npm run e2e
```

`build` chạy TypeScript/Vite, Apple icon/PWA surface verification và precompression. `e2e` dùng Playwright theo [playwright.config.ts](../../frontend/playwright.config.ts), cần browser/dependencies đã cài. Không dùng browser profile thật hoặc copied storage làm synthetic fixture.

Tại root:

```powershell
python -m unittest discover -s .github/tests -v
python -m unittest discover -s qa/production-cell/tests -v
pre-commit run --all-files
```

Repository hooks dùng pre-commit với versions trong [.pre-commit-config.yaml](../../.pre-commit-config.yaml); CI cài công cụ này trước khi chạy. QA-cell dependencies riêng nằm trong [requirements.lock](../../qa/production-cell/requirements.lock). Khi cần đúng bộ đó, cài vào environment QA riêng; không đổi runtime dependency group.

DB tests dùng `uv run --frozen pytest -m pg` sau bootstrap/migrate một PostgreSQL 18 + pgvector **disposable** đã được cấp quyền. Migration QA trong CI là entry tái lập chuẩn cho role/grants/round-trip. Không tự tạo local DB tùy tiện, không dùng Neon/Owner DB làm đường tắt. Docker CLI có mặt chưa chứng minh daemon chạy; Owner khởi động Docker khi cần. Không giết process theo tên hoặc chiếm port của lane khác.

## Khi gặp lỗi

- Frozen install không khớp: kiểm package/lock diff; không chữa bằng một broad upgrade.
- 401/404 ở dev-session: kiểm `APP_ENV`, đúng backend/origin và guard QA; không nới auth.
- PG tests skipped/unavailable: ghi `NOT_RUN`, dùng receipt CI Migration QA đúng commit; non-PG PASS không thay thế SQL thật.
- Timeout khi cài/build/ghi dữ liệu: kiểm hiệu ứng đã xảy ra trước retry. Sau khoảng hai lần không tiến triển, giữ log và đổi kế hoạch.
- Secret scan/hook lỗi: sửa source hoặc fixture; không disable gate. Log/screenshot công khai không có account thật, secret hoặc payload cá nhân.

Các driver `.agents` cần freeze/capability và grant hiện tại, không tự launch theo tuple lịch sử. Xem [Verification](../verification/README.md).
