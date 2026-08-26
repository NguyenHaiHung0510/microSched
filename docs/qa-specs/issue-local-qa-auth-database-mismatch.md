# BÁO CÁO BÀN GIAO & PHÂN TÍCH LỖI: LOCAL QA AUTH & DATABASE CONNECTION MISMATCH

> **Thời điểm ghi nhận:** 25/08/2026
> **Dự án:** microSched
> **Mục tiêu:** Bàn giao chi tiết hiện trạng, nguyên nhân gốc rễ và tracebacks cho Agent chuyên trách Backend/DevSecOps tiếp quản xử lý.

---

## 1. Tóm tắt Hiện tượng (Observed Symptoms)

1. **Người dùng mở `http://localhost:5173` (tab ẩn danh):**
   - Bấm nút **"Đăng nhập bằng Google" (OAuth)** thì vào được app, nhưng **hiển thị toàn bộ dữ liệu thật trên Production** thay vì dữ liệu đã làm sạch trên nhánh staging `develop`.
   - Bấm nút **"Đăng nhập QA (Bypass OAuth)"** thì nhận về phản hồi lỗi `{"detail": "Not authenticated"}` hoặc gặp lỗi `Internal Server Error (500)`.

---

## 2. Nguyên nhân Gốc rễ (Root Cause Analysis)

### Vấn đề 1: Môi trường Local bị nạp nhầm URL Production từ `.env`
 - Trong `backend/.env`, `DATABASE_URL` trỏ tới **Production Host** (hostname đã redact, hậu tố Neon chung) và `NEON_DEVELOP_BRANCH_KEY` trỏ tới nhánh staging `-pooler` riêng.
 - Khi tiến trình backend (Uvicorn) khởi chạy ở local, `Settings()` đọc `backend/.env` và nạp `DATABASE_URL` (Production) vào SQLAlchemy Engine.
- Do đó, khi người dùng bấm OAuth Google ở local, backend đã kết nối trực tiếp vào database **Production** thật và truy vấn dữ liệu cá nhân thật của người dùng.

### Vấn đề 2: Lỗi Driver `psycopg2` vs `asyncpg` khi ghi đè `DATABASE_URL`
- Chuỗi kết nối từ Neon cấp thường có tiền tố `postgresql://...`.
- SQLAlchemy Async Engine (`create_async_engine`) đòi hỏi driver bất đồng bộ `postgresql+asyncpg://...`.
- Khi thiết lập `self.database_url = self.neon_develop_branch_key`, nếu không qua hàm chuẩn hóa `async_postgres_url()`, SQLAlchemy sẽ mặc định tìm `psycopg2` (chưa được cài đặt vì dự án dùng `asyncpg`) dẫn đến lỗi:
  ```text
  ModuleNotFoundError: No module named 'psycopg2'
  ```

### Vấn đề 3: Lỗi SSL / Event Loop Conflict giữa SQLAlchemy Connection Pool và Asyncpg
 - Khi chạy `create_async_engine` kết nối tới Neon Endpoint develop (nhánh `-pooler`, hostname đã redact), asyncpg ném lỗi:
  ```text
  sslproto._fatal_error(ex, 'Fatal error on SSL protocol')
  RuntimeError: Event loop is closed
  ```
- Cần cấu hình đúng tham số SSL (`ssl='require'`) và cơ chế Connection Pooling của SQLAlchemy Async Engine để tương thích với Neon Connection Pooler.

### Vấn đề 4: Thuộc tính `session_cookie_secure` khi chạy HTTP Plain ở Local
- Trong `backend/app/core/settings.py`, mặc định `session_cookie_secure: bool = True` (bắt buộc HTTPS).
- Khi trình duyệt truy cập qua `http://localhost:5173` (HTTP thường, không có chứng chỉ SSL), trình duyệt Chromium/Safari sẽ tự động **drop (loại bỏ)** cookie có cờ `Secure`.
 - Dẫn đến việc sau khi gọi `/auth/dev-session`, cookie không được lưu vào trình duyệt và các API sau đó đều trả về `401 Unauthorized`.

---

## 3. Log & Traceback Chi tiết (Exact Receipts)

### Traceback 1: ModuleNotFoundError 'psycopg2'
```text
File "backend/app/core/db.py", line 23, in get_engine
  return create_async_engine(database_url, pool_pre_ping=True)
File "sqlalchemy/ext/asyncio/engine.py", line 120, in create_async_engine
  sync_engine = _create_engine(url, **kw)
File "sqlalchemy/dialects/postgresql/psycopg2.py", line 697, in import_dbapi
  import psycopg2
ModuleNotFoundError: No module named 'psycopg2'
```

### Traceback 2: SSL Protocol / Event Loop Closed trên Neon Connection Pooler
```text
File "backend/app/web/deps.py", line 106, in require_session
  session = await store.load_valid(token)
File "sqlalchemy/dialects/postgresql/asyncpg.py", line 816, in ping
  _ = self.await_(self._async_ping())
File "asyncpg/connection.py", line 354, in execute
  result = await self._protocol.query(query, timeout)
File "asyncio/sslproto.py", line 700, in _write_appdata
  self._fatal_error(ex, 'Fatal error on SSL protocol')
RuntimeError: Event loop is closed
```

---

## 4. Các file và vị trí code liên quan

1. **`backend/app/core/settings.py`**:
   - Khai báo `app_env`, `database_url`, `neon_develop_branch_key`, `session_cookie_secure`.
   - Cần cấu hình an toàn: khi `app_env == "local"`, tự động trỏ `database_url` sang `neon_develop_branch_key` qua `async_postgres_url()` và đặt `session_cookie_secure = False`.
2. **`backend/app/core/db.py`**:
   - Hàm `get_engine()` và `get_sessionmaker()`: cấu hình kết nối `create_async_engine` với SSL và pool settings phù hợp cho Neon.
3. **`backend/app/web/routers/auth.py`**:
   - Endpoint `/dev-session` phục vụ QA local bypass OAuth, cấp token phiên làm việc cho `owner@test.local`.
4. **`backend/app/main.py`**:
   - Router mounting: đảm bảo `auth_router` unauthenticated không bị chặn bởi dependency `require_session` của `protected_api`.
5. **`backend/scripts/prepare_qa_branch.py`**:
   - Script scrub dữ liệu format-preserving trên nhánh `develop`.

---

## 5. Đề xuất Hướng xử lý cho Agent chuyên trách

1. **Chuẩn hóa cấu hình Engine DB Local (`backend/app/core/db.py` & `settings.py`):**
   - Đảm bảo `database_url` ở local luôn đi qua `async_postgres_url()` để gắn driver `postgresql+asyncpg://`.
   - Cấu hình tham số `connect_args={"ssl": "require"}` hoặc tương đương cho `asyncpg` khi kết nối tới Neon pooler.
2. **Khóa cứng chốt chặn an toàn (Fail-closed Guard):**
   - Ở môi trường local (`APP_ENV=local`), nếu phát hiện `database_url` trùng với host Production, ứng dụng phải từ chối khởi động ngay lập tức để tránh rò rỉ dữ liệu thật.
3. **Hoàn thiện luồng QA Session:**
   - Đảm bảo `/auth/dev-session` tạo session hợp lệ trong bảng `microsched.session` của nhánh `develop` và gắn cookie `ms_session` không có cờ `Secure` khi ở local.
