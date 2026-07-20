# 004 — Scaffold frontend: Vite + React + shadcn, serve cùng origin

> **Trạng thái:** 📋 TODO (chạy sau 003)
> **Executor dự kiến:** T2 — Codex (`docs/devops-brief.md` §7) · **Bậc model: Terra (workhorse)** · **Effort:** medium
> *Lý do bậc: init theo stack đã chốt sẵn từng lớp — việc là lắp đúng, không phải chọn.*

## Bối cảnh (đọc trước, đừng bỏ qua)

Đọc `CLAUDE.md` + **toàn bộ `docs/frontend-brief.md`** (đặc biệt §1 bảng stack, §4 mô hình runtime, §6 quy ước shadcn + supply-chain) + `docs/architecture-brief.md` §9. Task 003 đã dựng `backend/` với `GET /api/healthz`.

Stack **đã khép 2026-07-20, không relitigate**: React 19 + TypeScript + **Vite 8** + Tailwind CSS v4 + **shadcn/ui** + TanStack Query v5 + Dexie (outbox tự viết — **chưa làm ở task này**) + vite-plugin-pwa. Production không có Node — FastAPI serve `frontend/dist` cùng origin (frontend-brief §4).

## Mục tiêu

`frontend/` build được; dev-mode hot-reload gọi được API backend; production-mode FastAPI serve SPA tại `/`.

## Ghi chú T1 (bổ sung 2026-07-20, sau review diff 003 — PR #5)

**Nợ kỹ thuật phải trả trong task này** (bước 8 vốn đã đụng backend, gộp vào cho rẻ): `backend/app/web/routers/health.py` đang gọi `Settings()` **bên trong handler**, tức mỗi request khởi tạo lại object và đọc lại `.env` từ đĩa. Ở 003 thì vô hại, nhưng đây là **pattern sẽ bị copy**: đến 007 thì `Settings` chứa OAuth client secret + cấu hình session. Sửa thành một instance dùng chung (`@lru_cache` trên hàm `get_settings()`, hoặc FastAPI dependency) và cập nhật `health.py` + `main.py` dùng nó. Test hiện có phải vẫn xanh.

Ngoài ra, **không** xử lý `StarletteDeprecationWarning` (httpx → httpx2) trong task này — đã ghi sổ riêng, đụng vào lúc này là mở rộng phạm vi.

## Phải làm

1. **Init `frontend/`**: Vite 8 + React 19 + TypeScript (template react-ts). Pin version trong `package.json`, **commit `package-lock.json`** (frontend-brief §6.4 — npm supply-chain: mọi install sau này qua `npm ci`).
2. **Tailwind v4 + shadcn init**: chạy `shadcn init` (pin version CLI khi chạy, vd `npx shadcn@<ver>` — §6.2) và **commit `components.json` ngay từ init** (§6.3). Add đúng **một** component đầu tiên đang cần thật (vd `button`) — **add-on-demand**, không add sẵn hàng loạt (§6.1). Đọc diff file shadcn kéo về trước khi commit và xác nhận đã đọc trong PR (§6.2).
3. **TanStack Query v5**: cài + dựng `QueryClientProvider` ở root. **Chưa** cấu hình persist/IndexedDB (đi cùng outbox sau).
4. **Dexie**: chỉ cài dependency (khóa version) — **không viết outbox** (cần entity thật, task sau).
5. **vite-plugin-pwa**: manifest tối thiểu (`name`, icon placeholder, `display: "standalone"` — bắt buộc cho iOS push sau này, frontend-brief §5). Không đụng web-push (§7 để lúc build feature nhắc thuốc).
6. **Trang chào tối thiểu**: hiển thị "microSched" + kết quả fetch `GET /api/healthz` qua TanStack Query (chứng minh chuỗi FE→API chạy). Dùng component shadcn đã add. **Không cài router** — 1 màn chưa cần (frontend-brief §7; thêm khi có ≥2 màn thật là quyết định lúc đó).
7. **Dev proxy**: Vite dev server proxy `/api` → `http://localhost:8000` (mô hình dev 2-process, frontend-brief §4).
8. **Serve production cùng origin**: backend mount static — `/api/*` ưu tiên router API; mọi path khác serve `frontend/dist` (SPA fallback về `index.html`); nếu `dist/` chưa tồn tại (dev) thì backend vẫn chạy bình thường.
9. **CI**: nối thêm job `frontend` vào `.github/workflows/ci.yml` của 003: `npm ci` → `tsc --noEmit` (hoặc `vite build` đã bao gồm type-check qua plugin — chọn 1, ghi trong PR) → `npm run build`.
10. **Ghi nhận**: `agent-tasks/README.md` trạng thái 004; nếu chốt lựa chọn 2-chiều nào của frontend-brief §7 (vd công cụ sinh TS types — *chưa bắt buộc ở task này*), ghi note có ngày vào frontend-brief §7.

## KHÔNG được làm

- **Không** outbox/sync/IndexedDB logic, **không** web-push, **không** router, **không** chart lib.
- **Không** add nhiều component shadcn "cho sẵn" — chỉ cái dùng thật ở trang chào.
- **Không** đổi backend ngoài phần mount static (bước 8) **và việc gộp `Settings` ở "Ghi chú T1"** — ngoài hai chỗ đó thì backend không đụng.
- **Không** sửa `docs/*.md` ngoài mục được giao ở bước 10. Muốn làm khác brief → DỪNG, escalate T1.
- **Không** commit secret / `.env`. **Không** rewrite history.

## Acceptance (kiểm chứng được)

- [ ] Dev: `uvicorn` (:8000) + `npm run dev` (:5173) → trang chào hiển thị kết quả healthz qua proxy.
- [ ] Prod-mode local: `npm run build` xong → chỉ chạy uvicorn → mở `localhost:8000/` thấy đúng trang đó (cùng origin, không CORS config nào phải thêm).
- [ ] `npm ci && npm run build` sạch từ lockfile (xóa `node_modules` thử lại vẫn build được).
- [ ] `components.json` + `package-lock.json` đã commit; CI 3 job đều xanh; `pre-commit run --all-files` sạch.
- [ ] PR có dòng xác nhận "đã đọc diff shadcn lúc add".
- [ ] `Settings` đã thành instance dùng chung (không còn khởi tạo trong handler); `uv run pytest` vẫn xanh.
- [ ] Mô tả PR viết qua `--body-file` UTF-8 (AGENTS.md) — tiếng Việt hiển thị đúng dấu trên GitHub.

## Bàn giao

Branch **`feat/004-scaffold-frontend`** → PR nhỏ vào `develop`. PR mô tả việc + lệnh verify + output. Người merge = chủ sau khi T1 review. Commit message tiếng Việt *tại sao*, kèm `Co-Authored-By:` của agent thực thi.
