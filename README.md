# microSched

[![CI](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml?query=branch%3Adevelop)
[![CodeQL](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/codeql.yml/badge.svg?branch=develop)](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/codeql.yml?query=branch%3Adevelop)
[![Latest release](https://img.shields.io/github/v/release/NguyenHaiHung0510/microSched?display_name=tag)](https://github.com/NguyenHaiHung0510/microSched/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**microSched** là app cá nhân toàn năng và personal software laboratory của mình — chặng thứ ba, cũng là phiên bản trưởng thành nhất hiện tại, trong hành trình xây công cụ cá nhân.

Hành trình đi từ [Code_HoTro_HocTap](https://github.com/NguyenHaiHung0510/Code_HoTro_HocTap) (CLI C++ sơ khai từ năm nhất), qua [VC_QuanLyThoiGian](https://github.com/NguyenHaiHung0510/VC_QuanLyThoiGian) (desktop Python/Flet, vibe-coded, đóng gói `.exe`), đến microSched (harness engineering + AI engineering). Đây là sự trưởng thành trong tư duy sản phẩm, kỹ thuật và cách mình cộng tác với AI; microSched đã được dùng thật từ **21/07/2026** và tiếp tục cải tiến theo feedback thực tế.

> Đây là dự án cá nhân đang phát triển. Tài liệu này mô tả những gì code hiện có; không phải mọi ý tưởng trong roadmap đều đã shipped.

## Tính năng hiện có

- **Task:** deadline, checklist, ưu tiên, ghim, quá hạn, dời lịch và khôi phục sau soft-delete.
- **Ghi chú:** nội dung Markdown, checklist, thời gian, ghim/ưu tiên và private visibility.
- **Lịch:** nguồn lịch ICS, buổi thủ công, lịch cuộn theo ngày, annotation và dời task.
- **Theo dõi:** ghi nhanh các tracker sức khỏe hoặc tài chính, entry theo thời điểm, dashboard VND và đăng ký định kỳ/gia hạn.
- **Riêng tư:** Google OAuth với allowlist, server-side session và private unlock riêng cho lớp hiển thị. Dữ liệu mã hóa at-rest có ranh giới riêng; đây không phải tuyên bố security certification.
- **PWA:** cài và sử dụng trên laptop hoặc iPhone, có service worker và nền tảng Web Push. Full offline outbox cho mọi write chưa phải scope đã shipped.

## Định hướng học tập và hệ sinh thái

microSched là **dự án trục**, nơi mình luyện product thinking, backend/API, data model, privacy boundary, evaluation và vận hành production. Các hướng liên quan đang được phát triển hoặc nghiên cứu — **chưa claim shipped** — gồm:

- **Mimi:** AI agent hỗ trợ quản lý kế hoạch tích hợp website.
- **microLink:** cầu nối MCP local giữa AI agent và microSched.
- **miGarden:** hệ thống IoT giám sát và hỗ trợ tưới cây, dự kiến tích hợp vào microSched qua một seam tự nhiên.
- Có thể bổ sung các sản phẩm liên quan khác khi có nhu cầu và scope rõ.
- AI assistant read-only, hybrid retrieval, write tools có confirmation/audit và full offline outbox vẫn là roadmap/in-progress; MCP protocol chưa được bật trong microSched hiện tại.

## Kiến trúc

```text
React + TypeScript PWA (browser: laptop / iPhone)
                 │ JSON API, same origin
                 ▼
FastAPI modular monolith (một Python process)
                 │
                 ▼
Neon PostgreSQL + pgvector
```

Frontend là static SPA/PWA được cài và sử dụng trên laptop hoặc iPhone; service worker và Web Push foundation đã có trong app. Node chỉ dùng lúc build, còn production chạy một Python process phục vụ cả API và frontend build. Domain, web, retrieval, agent và jobs giữ trong cùng process; không có microservices hay Redis broker.

## Hạ tầng vận hành

- **Application:** FastAPI modular monolith + static React/TypeScript PWA.
- **Data:** Neon PostgreSQL với `pgvector`; private fields dùng encryption boundary của app.
- **Delivery thực tế:** GitHub Actions build và kiểm tra → Docker multi-stage build → một Fly.io Machine tại `sin`, shared CPU, 256 MB RAM và 512 MB swap; dữ liệu chạy trên Neon PostgreSQL + `pgvector`. Mình dùng app thật trên laptop và iPhone.
- **Auth:** Google OAuth allowlist và session server-side.

## Chạy local

### Backend

Yêu cầu Python 3.14 và `uv`. Từ thư mục repo:

```powershell
cd backend
uv sync
Copy-Item .env.example .env
uv run uvicorn app.main:create_app --factory --reload
```

Điền các biến local trong `backend/.env` theo `backend/README.md`. Không dùng owner/migrator URL làm runtime URL; không commit `.env` hoặc secret thật.

### Frontend

Yêu cầu Node 24 và npm:

```powershell
cd frontend
npm ci
npm run dev
```

Vite chạy frontend development; backend chạy riêng ở `http://localhost:8000`. Production không chạy Node process thứ hai.

## Kiểm tra chất lượng

```powershell
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest

cd ..\frontend
npm run lint
npm test
npm run build
```

CI còn có Frontend e2e, secret scan và Migration QA với Postgres/pgvector. Các lệnh trên là cách chạy kiểm tra; trạng thái pass hiện tại phải xem receipt CI tương ứng.

## Security và đóng góp

- Xem [SECURITY.md](SECURITY.md) để báo cáo lỗ hổng qua GitHub private vulnerability reporting.
- Xem [CONTRIBUTING.md](CONTRIBUTING.md) trước khi mở thay đổi.
- Không đưa credential, dữ liệu cá nhân thật, OAuth allowlist hoặc production payload vào issue, PR, log hay fixture.

## License

Source code và logo/icon do project sở hữu được phát hành theo [MIT License](LICENSE). Dependencies và third-party assets giữ license tương ứng; personal data, secrets, credentials và service accounts không thuộc phạm vi cấp phép của project.
