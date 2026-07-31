# 014 — ghi RSS trong cron heartbeat (cái canh mà quyết định scale-to-zero đã hứa)

> **Executor: T3 / `agy` chạy trong worktree riêng** (`../microsched-t3lane`, nhánh `feat/014-cron-rss-watch`) → PR nhỏ vào `develop`.
> Spec tự-chứa. Đọc `CLAUDE.md` + `AGENTS.md` trước.
> **KHÔNG có migration. KHÔNG chạm frontend. KHÔNG thêm dependency.**

## 0. Bối cảnh — vì sao có task này

2026-07-23 dự án đảo hosting sang **scale-to-zero** (`auto_stop_machines = 'suspend'`, `min_machines_running = 0`). Quyết định đó ghi rõ **đánh đổi thật duy nhất**: `suspend` nghĩa là **tiến trình không bao giờ restart**, nên **rò rỉ bộ nhớ tích luỹ mãi** — và cái canh được chọn là *"canh bằng RSS ghi trong job cron"*.

**Đo 2026-07-26: cái canh đó không tồn tại.** `grep -rni "rss|memory_info|getrusage" backend/app` ra **0 dòng**. `backend/app/web/routers/cron.py` chỉ log một chuỗi cố định `"Cron heartbeat received"`.

Nghĩa là: đánh đổi đã được **chấp nhận** nhưng chưa được **quan sát**. Không có gì đỏ, không có gì cảnh báo — máy cứ chạy tới lúc OOM. Task này đóng đúng khoảng đó, không làm gì hơn.

## 1. Đã KHOÁ — chép ra code, không mở lại

1. **Không thêm dependency.** Không `psutil`, không gì cả. CI có job `Production dependency check` và luật supply-chain của dự án; một dòng đọc file không đáng một dependency production.
2. **Đọc từ `/proc/self/status` (`VmRSS`).** Không `resource.getrusage` — nó trả *peak* (`ru_maxrss`), mà thứ cần canh là **mức hiện tại** đang tăng dần theo thời gian sống của tiến trình.
3. 🔒 **Phải chạy được trên máy KHÔNG có `/proc`.** Production là Linux, nhưng máy dev của chủ là **Windows** và CI là Ubuntu. Không có `/proc/self/status` ⇒ trả `None`, **endpoint vẫn `200`**. Tuyệt đối không để một dòng quan sát làm chết một endpoint.
4. **Không chạm DB.** `cron.py` cố ý không bao giờ đụng database — đó là bản vá của sự cố Neon 22/07 (health check `SELECT 1` giữ Neon thức 24/7, đốt 6 CU-h/ngày). Task này không được phá điều đó.
5. **Xong việc bên trong request.** Luật 23/07: proxy Fly mù với mọi thứ sinh ra sau khi response đã trả ⇒ không `BackgroundTasks`, không thread, không `asyncio.create_task`.
6. **Không đổi đường dẫn, không đổi cơ chế auth** của `/api/cron/heartbeat`.

## 2. Phải làm

### 2.1 Hàm đọc RSS

Thêm một hàm nhỏ vào `backend/app/core/` (ví dụ `process_stats.py`):

```
def read_rss_kb() -> int | None
```

- Đọc `/proc/self/status`, tìm dòng bắt đầu bằng `VmRSS:`, lấy số, trả về **kB** (đơn vị `/proc` đã là kB — **không tự nhân chia**).
- File không tồn tại, không đọc được, không có dòng `VmRSS`, hoặc parse thất bại ⇒ trả `None`. **Không raise.**
- Đường dẫn phải **tham số hoá được** (ví dụ tham số `path` có default) để test đút file giả vào — đừng monkeypatch `open`.

### 2.2 Heartbeat ghi số đó

Trong `backend/app/web/routers/cron.py`:

- Gọi `read_rss_kb()`.
- Có số ⇒ `logger.info` **một dòng có cấu trúc, grep được**, kèm giá trị (ví dụ `Cron heartbeat received rss_kb=51234`). Giữ nguyên phần chữ `Cron heartbeat received` — đừng đổi, log cũ còn phải tra được.
- `None` ⇒ log như hiện nay, thêm dấu hiệu là không đo được.
- **Trả `rss_kb` trong body JSON**: `{"status": "ok", "rss_kb": <int|null>}`. Lý do: nó cho T1 một đường nghiệm thu bằng một lời gọi `curl` trên production, chứ không phải đi đào log.

### 2.3 Test (`backend/tests/`, lane `not pg`)

| Test | Phải khẳng định |
|---|---|
| Parse | Đút file giả có `VmRSS:   51234 kB` ⇒ trả đúng `51234` |
| Không có file | Đường dẫn không tồn tại ⇒ trả `None`, **không raise** |
| Rác | File có nội dung không có `VmRSS` / số hỏng ⇒ `None`, không raise |
| Endpoint có số | `POST /api/cron/heartbeat` với token đúng ⇒ `200`, body có `rss_kb` là int |
| Endpoint không đo được | `read_rss_kb` trả `None` ⇒ vẫn `200`, `rss_kb` là `null` |
| Auth không đổi | Không token / token sai ⇒ vẫn `401` như trước |

🔒 **Chứng minh BIẾT ĐỎ:** trước khi báo xong, phá tạm phần parse (ví dụ trả sai đơn vị) và ghi vào PR rằng test nào đã đỏ. Một test luôn xanh là một test không bảo vệ gì.

## 3. KHÔNG được làm

- **Không** thêm dependency (kể cả dev).
- **Không** đụng: `backend/app/domain/tasks.py`, `backend/app/domain/models.py`, `backend/app/domain/reading.py`, `backend/app/web/routers/tasks.py`, bất kỳ file nào trong `frontend/`, bất kỳ file `alembic/versions/*`. Ba lane khác đang chạy trên đúng những file đó.
- **Không** thêm endpoint mới, không thêm metric/Prometheus/exporter. Một dòng log + một field JSON là toàn bộ phạm vi.
- **Không** đặt ngưỡng cảnh báo, không tự restart máy khi RSS cao. Đó là quyết định của chủ, không phải của task này.
- **Không** chạm `fly.toml`, `.github/**`, `.pre-commit-config.yaml` — **một luồng khác đang sửa `.github/**` ngay lúc này.**
- **Không** tự `git push` lên `develop`; chỉ commit trên nhánh `feat/014-cron-rss-watch`.

## 4. Acceptance — kiểm chứng được

Chạy **đúng danh sách của `ci.yml`**, không phải danh sách mình nhớ:

1. `cd backend && uv run ruff check .` sạch **và** `uv run ruff format --check .` sạch *(bỏ lệnh thứ hai đã từng làm CI đỏ sau 10 giây — 26/07)*.
2. `cd backend && uv run pytest -m "not pg"` xanh toàn bộ.
3. `git diff --stat` chỉ hiện file thuộc phạm vi §2 (không có file nào ở §3).
4. Ghi trong PR: test nào đã chứng minh đỏ, và cách xử lý ca không có `/proc`.

## 5. Báo cáo

PR nhỏ vào `develop`, tiêu đề `014: ghi RSS trong cron heartbeat`. Trong PR description ghi rõ **cái gì mình KHÔNG tự verify được** (ví dụ không chạy được Docker, không chạy được lane `pg`) — báo thiếu thì T1 chạy lại, báo đạt sai thì mất cả niềm tin vào lane này.
