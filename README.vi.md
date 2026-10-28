# microSched

[English](README.md) | Tiếng Việt

[![CI](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/NguyenHaiHung0510/microSched)](https://github.com/NguyenHaiHung0510/microSched/releases/latest)

[Xem microSched](https://microsched.fly.dev/home) · [Tài liệu kỹ thuật](docs/project-guide.md) · [Changelog](CHANGELOG.md)

microSched là PWA quản lý công việc, ghi chú, lịch và theo dõi cá nhân cho một Owner. Đây cũng là software laboratory để thực hành harness engineering và AI engineering, tiếp nối [Code_HoTro_HocTap](https://github.com/NguyenHaiHung0510/Code_HoTro_HocTap) và [VC_QuanLyThoiGian](https://github.com/NguyenHaiHung0510/VC_QuanLyThoiGian).

- **Task và note:** deadline, ưu tiên, ghim, checklist, soft-delete/khôi phục và đọc/sửa Markdown.
- **Lịch và nhắc nhở:** nguồn ICS, sự kiện thủ công, dời ngày/giờ, annotation, nhắc một lần/định kỳ và lịch sử xử lý.
- **Theo dõi:** nhóm tracker, entry theo thời điểm, ghi khoản thu/nguồn tiền, báo cáo VND và gia hạn subscription.
- **Responsive PWA:** navigation chung, nội dung compact, public bootstrap offline và durable outbox cho **11 command Task/checklist/Entry**. Các domain khác vẫn cần mạng; lưu vào hàng đợi local khác với server đã xác nhận.
- **Riêng tư:** Google OAuth allowlist, opaque session server-side, private display unlock và ranh giới mã hóa của ứng dụng.
- **Mimi:** đã có năng lực đọc Task/checklist, đề xuất, review/revision và explicit Confirm. Toàn bộ module Mimi vẫn đang phát triển; xem [README kỹ thuật PARTIAL](docs/mimi/README.md).

React/TypeScript/Vite build frontend tĩnh. Một process FastAPI phục vụ SPA và API, dùng PostgreSQL/pgvector trên Neon. Node chỉ cần ở development/build. Cấu hình Fly trong repo dùng một machine always-on; sức khỏe runtime cần bằng chứng riêng.

Fresh clone bắt đầu tại [development setup](docs/engineering/development.md): Python 3.14, Node 24, `uv sync --frozen`, `npm ci`, vai trò environment và các lệnh test. [Operations](docs/operations/runbook.md) mô tả deploy, readiness, backup/recovery và migration có quyền riêng. Mô tả source hiện hành không chứng nhận mọi browser, thiết bị thật hay live-provider journey.

Xem [đóng góp](CONTRIBUTING.vi.md) và [báo cáo security](SECURITY.vi.md). Không đưa credential, account identifier hay dữ liệu cá nhân vào issue, fixture hoặc PR. Source và logo/icon do project sở hữu dùng [MIT License](LICENSE); third-party assets giữ license riêng. Personal data và service account không nằm trong phạm vi cấp phép.
