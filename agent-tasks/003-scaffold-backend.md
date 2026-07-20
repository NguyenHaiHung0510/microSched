# 003 — Scaffold backend: FastAPI skeleton + tooling + CI nền

> **Trạng thái:** 📋 TODO
> **Executor dự kiến:** T2 — Codex (`docs/devops-brief.md` §7) · **Bậc model: Terra (workhorse)** · **Effort:** medium
> *Lý do bậc: mọi fork lớn đã được brief quyết sẵn — giá trị nằm ở làm ĐÚNG convention, không ở sáng tạo. Agent khác chạy spec này cũng được (spec tự-chứa), dùng tầng tương đương.*

## Bối cảnh (đọc trước, đừng bỏ qua)

Đọc `CLAUDE.md` (toàn bộ) + `docs/architecture-brief.md` §3/§9 + `docs/schema-physical-brief.md` §2-A1 trước khi viết dòng code nào.

**microSched** — web app cá nhân một-người-dùng (task/note/lịch/tracker), AI-first, rewrite sạch từ app desktop cũ. Repo hiện **PRE-CODE**: chỉ có decision records (`docs/`), specs (`agent-tasks/`), pre-commit + gitleaks đang hoạt động (001/002 DONE). Spec này **mở màn phase B (scaffold)** — chuỗi 003→007 có mục tiêu chung: **walking skeleton** = một trang thật trên `*.fly.dev` có login Google.

Kiến trúc đã khép, **không relitigate**: Python + FastAPI, modular monolith **1 process**, ranh giới module trong-process = `web / domain / retrieval / agent / jobs` (architecture-brief §3). Layout: 1 repo, `backend/` + `frontend/`, Dockerfile ở gốc (§9).

**Ranh giới dữ liệu (devops-brief §7):** agent không bao giờ cần — và không được hỏi — giá trị secret thật. Code bằng `.env.example`; giá trị thật chỉ chủ đặt tay vào `.env` local / Fly secrets.

## Mục tiêu

`backend/` chạy được local: `GET /api/healthz` trả JSON; lint + test + CI xanh.

## Phải làm

1. **Layout `backend/`**: package `app/` với app-factory (`create_app()`) + các module rỗng đúng ranh giới §3: `web/` (routers), `domain/`, `retrieval/`, `agent/`, `jobs/`, `core/` (settings, db-placeholder). Mỗi module có `__init__.py` + docstring 1 dòng nói vai — đây là ranh giới kiến trúc, không phải folder tùy hứng.
2. **Tooling**: `backend/pyproject.toml`, package manager khuyến nghị **uv** (commit lockfile; đây là cửa 2 chiều — nếu executor có lý do mạnh dùng thứ khác, ghi 3 dòng lý do trong PR). Pin bản Python stable mới nhất **tra tại thời điểm chạy** (đừng chép từ trí nhớ). Deps khởi điểm: `fastapi`, `uvicorn`, `pydantic-settings`, `sqlmodel` (chưa đụng DB — cài để khóa version sớm); dev: `ruff`, `pytest`, `httpx`.
3. **Settings** qua `pydantic-settings` đọc `.env`. Commit `.env.example` chỉ chứa placeholder an toàn (connection string dùng đúng dạng `postgresql://user:password@host/db` — dạng placeholder mà rule gitleaks của 002 cố tình cho qua; tuyệt đối không giá trị trông-thật).
4. **`GET /api/healthz`** trả `{"status": "ok", "version": ...}` + test pytest cho nó (dùng `httpx`/`TestClient`).
5. **ruff** đảm nhiệm cả lint + format (không cài black); cấu hình trong `pyproject.toml`.
6. **CI**: `.github/workflows/ci.yml` — job `backend`: cài deps từ lockfile → `ruff check` + `ruff format --check` + `pytest`; job `hooks`: `pre-commit run --all-files`. Cấu trúc workflow chừa chỗ để 004 (frontend) và 006 (migration QA) nối thêm job.
7. **Ghi nhận**: cập nhật `docs/devops-brief.md` §6 (CI nền đã dựng, kèm ngày) + `agent-tasks/README.md` (trạng thái 003, và trạng thái các task sau nếu đổi).
8. Thêm `backend/README.md` ngắn: lệnh chạy dev, lệnh test — để mọi agent/human sau không phải đoán.

## KHÔNG được làm

- **Không** viết logic domain/DB thật, không tạo model/bảng nào (006 lo DB).
- **Không** đụng `frontend/` (004), Dockerfile/Fly (005), auth (007).
- **Không** thêm dependency ngoài danh sách trên trừ khi thiếu-thì-không-chạy-được; mỗi dep thêm phải ghi lý do trong PR.
- **Không** sửa nội dung `docs/*.md` ngoài đúng mục được giao ở bước 7 — decision records đã chốt; muốn làm khác điều đã chốt → DỪNG, escalate T1 (devops-brief §7).
- **Không** commit `.env` thật / secret. **Không** rewrite git history.

## Acceptance (kiểm chứng được)

- [ ] Lệnh dev trong `backend/README.md` chạy được → `curl localhost:8000/api/healthz` trả 200 JSON.
- [ ] `ruff check` + `ruff format --check` + `pytest` pass local.
- [ ] CI xanh trên PR (cả 2 job).
- [ ] `pre-commit run --all-files` sạch.
- [ ] `.env.example` tồn tại và không làm gitleaks kêu.

## Bàn giao

Branch **`feat/003-scaffold-backend`** → **PR nhỏ vào `develop`** (quy ước code mới, devops-brief §7 — docs mới được commit thẳng develop, code thì không). PR mô tả: đã làm gì, lệnh verify đã chạy + output, quyết định 2-chiều nào đã chọn và vì sao. Người merge = chủ, sau khi T1 review diff. Commit message tiếng Việt, giải thích *tại sao*, kèm `Co-Authored-By:` của agent thực thi.
