# 005 — Docker multi-stage + deploy Fly.io đầu tiên

> **Trạng thái:** 📋 TODO (chạy sau 004)
> **Executor dự kiến:** T2 — Codex · **Bậc model: Sol (bậc cao)** · **Effort:** high · **Skill gợi ý:** (không) · **MCP cần:** (không)
> *Lý do bậc: Docker/Fly là chỗ "sai âm thầm thành nợ" (bẫy chi phí, cấu hình sống lâu); debug deploy cần model mạnh.*

## Bối cảnh (đọc trước, đừng bỏ qua)

Đọc `CLAUDE.md` + `docs/architecture-brief.md` §5 (hosting — đặc biệt các bẫy) + `docs/frontend-brief.md` §4 (multi-stage) + `docs/cost-brief.md` §2. Task 003/004 đã có backend + frontend build cùng origin.

Quyết định đã khép: **Fly.io, 1× Machine `shared-cpu-1x` always-on, region `sin`, khởi đầu 256MB** (~$2/mo; lên 512MB *chỉ khi* OOM). Image cuối **không chứa Node** — Node chỉ tồn tại ở build stage.

**Việc của CHỦ trước khi chạy task** (agent không tự làm được và không được hỏi credential):
- [ ] Tạo tài khoản Fly + `fly auth login` sẵn trên máy (agent gọi `flyctl` qua session đã login — không bao giờ hỏi/token ra chat).
- [ ] ⚠️ **Chặn chi phí — tra lại 2026-07-20: Fly KHÔNG có spending limit và KHÔNG có billing alert.** Yêu cầu cũ ở dòng này là bất khả thi, đừng đi tìm nữa. Cách chặn thật duy nhất = **prepaid credits** (nạp ≥$25, hết credit thì account bị treo → trần cứng, đổi lại app sập khi hết). Không nạp thì phải **tự xem mục "current month to date" trong dashboard** định kỳ. → **Chủ đã chọn 2026-07-20: KHÔNG nạp prepaid, tự theo dõi dashboard + đặt nhắc nhở định kỳ** (lý do: nạp trước cho một app ~$2/mo là chôn vốn quá mức so với rủi ro). Hệ quả phải chấp nhận: **không có trần cứng nào** — nếu cấu hình sai âm thầm (2 máy, VM to hơn, volume) thì hoá đơn cứ chạy tới khi chủ tự nhìn thấy. Vì thế mục 4 ("ép `fly scale count 1`") là hàng rào chi phí **tự động duy nhất** của cả task, phải verify bằng output thật chứ không tin mặc định. *(Nhắc nhở này là ứng viên tự nhiên cho chính app sau khi có tracker — xem `docs/tracking-brief.md` §11 subscription.)*
- [ ] **Bật Docker Desktop trước khi giao task** — acceptance #1 là `docker build` chạy local. Máy chủ đã cài Docker CLI 29.4.3 nhưng daemon không tự chạy; nếu chưa bật, executor sẽ chết ngay ở bước đầu với lỗi `failed to connect to the docker API at npipe:...`.
- [ ] Chọn tên app — **ràng buộc của Fly: chỉ chữ thường, số và dấu `-`; không hoa, không `_`**. Nên `microsched`; nếu trùng thì `microsched-hung`. (`microSched` và `microsched_hung` đều **không hợp lệ**.) Báo tên đã chọn cho agent trong prompt lúc giao task.

## Mục tiêu

`https://<app>.fly.dev/` hiển thị trang chào (004) và `/api/healthz` trả 200 — từ đúng **1 machine** luôn-on ở `sin`.

## Phải làm

1. **`Dockerfile` multi-stage ở gốc repo** (frontend-brief §4): stage 1 image Node — `npm ci` + `npm run build` ra `dist/`; stage 2 image Python slim — cài deps backend từ lockfile (`uv sync --frozen` hoặc tương đương), copy `backend/` + `dist/`, chạy uvicorn bằng user non-root. Kèm `.dockerignore` (loại `node_modules`, `.git`, `.env`, `docs/`…).
2. **`fly.toml`**: `primary_region = "sin"`, internal port 8000, http_service với health-check trỏ `/api/healthz`, **`min_machines_running = 1` + tắt auto-stop** (always-on là điều kiện cứng — cold-start là dealbreaker của chủ), VM 256MB.
3. **Launch có kiểm soát**: dùng `fly launch --no-deploy` rồi **rà lại fly.toml nó sinh** theo đúng mục 2 (đừng để default tự quyết), sau đó `fly deploy`.
4. **Né bẫy chi phí #1** (architecture-brief §5): `fly launch` mặc định tạo **2 máy** HA → sau deploy phải verify và ép về **`fly scale count 1`**.
5. **Verify sau deploy**: `fly status` (1 machine, sin, 256MB) + curl trang `/` và `/api/healthz` qua HTTPS. Dán output các lệnh verify vào PR.
6. **Ghi nhận**: `agent-tasks/README.md` trạng thái 005; thêm note có ngày vào `docs/devops-brief.md` §6 (đã deploy lần đầu; CI-deploy vẫn chưa làm).

## KHÔNG được làm

- **Không** tạo volume, **không** Fly Managed Postgres, **không** Tigris (architecture-brief §5 — data ở Neon, backup đi đường khác).
- **Không** để 2 machine / autoscale / auto-stop bật.
- **Không** đặt secret nào ở bước này (006 mới cần `DATABASE_URL`; app hiện chạy không DB).
- **Không** dựng CI-deploy (GitHub Actions `fly deploy`) — pipeline riêng, cần bàn cách giữ token an toàn trước (devops-brief §6).
- **Không** mua domain / cấu hình cert riêng — dùng `*.fly.dev` (architecture-brief §6).
- **Không** sửa `docs/*.md` ngoài mục được giao. Kẹt/bí >2 vòng → DỪNG, escalate T1 kèm log lỗi.

## Acceptance (kiểm chứng được)

- [ ] `docker build` local thành công; `docker run -p 8000:8000` → `/` + `/api/healthz` OK; image cuối không có `node` trong PATH (`docker run <img> sh -c "command -v node || echo no-node"` → `no-node`).
- [ ] `https://<app>.fly.dev/` hiện trang chào; `/api/healthz` 200.
- [ ] `fly status`: đúng **1** machine, region `sin`, 256MB, luôn-on.
- [ ] `fly.toml` + `Dockerfile` + `.dockerignore` đã commit; CI xanh; `pre-commit run --all-files` sạch.

## Bàn giao

Branch **`feat/005-docker-fly-deploy`** → PR nhỏ vào `develop`, kèm output verify. Người merge = chủ sau khi T1 review. Commit message tiếng Việt *tại sao*, kèm `Co-Authored-By:` của agent thực thi.
