# microSched

[English](README.md) | Tiếng Việt

[![CI](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/NguyenHaiHung0510/microSched/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/NguyenHaiHung0510/microSched)](https://github.com/NguyenHaiHung0510/microSched/releases/latest)

[Xem microSched](https://microsched.fly.dev/home) · [Tài liệu kỹ thuật](docs/project-guide.md) · [Changelog](CHANGELOG.md)

**microSched** là ứng dụng cá nhân all-in-one và phòng thử nghiệm phần mềm của mình — phiên bản thứ ba, cũng là phiên bản trưởng thành nhất trong hành trình tự xây công cụ cho bản thân đến hiện tại.

Hành trình đó bắt đầu từ năm nhất đại học với [Code_HoTro_HocTap](https://github.com/NguyenHaiHung0510/Code_HoTro_HocTap), một nhật ký học tập dạng CLI viết bằng C++, dùng để ghi lại việc học hằng ngày, lưu ghi chú theo môn hoặc công việc và tự chấm mức độ hài lòng với việc học trong ngày. Tiếp đó là [VC_QuanLyThoiGian](https://github.com/NguyenHaiHung0510/VC_QuanLyThoiGian), ứng dụng desktop Python/Flet được vibe-code để quản lý công việc và lịch trình cá nhân, đóng gói thành `.exe` trên Windows. Đến microSched, mình đưa công việc, ghi chú, lịch và tracker vào một ứng dụng web cá nhân, với Mimi hỗ trợ thao tác Task/checklist bằng AI.

Đó là ba thế hệ công cụ cá nhân và cũng là ba chặng trong quá trình học của mình: thực hành lập trình qua một CLI nhỏ, xây ứng dụng desktop cùng AI, rồi phát triển và vận hành một sản phẩm rộng hơn với một nhóm agent được tổ chức và điều phối. Qua từng chặng, tư duy sản phẩm, kỹ năng kỹ thuật và cách mình cộng tác với AI cũng dần trưởng thành hơn. Mình đã dùng microSched từ lần triển khai đầu tiên vào **21 tháng 8 năm 2026**, khi chuyển dữ liệu từ VC_QuanLyThoiGian sang, và tiếp tục cải thiện nó từ trải nghiệm sử dụng hằng ngày.

## Mình dùng microSched cho việc gì?

microSched gom công việc, ghi chú, lịch và các tracker của mình vào một PWA phục vụ nhu cầu cá nhân hằng ngày.

- **Task và note:** deadline, ưu tiên, ghim, checklist, soft-delete/khôi phục và đọc/sửa Markdown.
- **Lịch và nhắc nhở:** nguồn ICS, sự kiện thủ công, dời ngày/giờ, annotation, nhắc một lần/định kỳ và lịch sử xử lý.
- **Theo dõi:** nhóm tracker, entry theo thời điểm, ghi khoản thu/nguồn tiền, báo cáo VND và gia hạn subscription.
- **Responsive PWA:** navigation chung, nội dung compact, public bootstrap offline và durable outbox cho **11 command Task/checklist/Entry**. Các domain khác vẫn cần mạng; lưu vào hàng đợi local khác với server đã xác nhận.
- **Riêng tư:** Google OAuth allowlist, opaque session server-side, private display unlock và ranh giới mã hóa của ứng dụng.
- **Mimi:** đã có năng lực đọc Task/checklist, đề xuất, review/revision và explicit Confirm. Toàn bộ module Mimi vẫn đang phát triển; xem [README kỹ thuật PARTIAL](docs/mimi/README.md).

## Mình học gì qua việc xây dựng dự án?

Mình đang hướng tới trở thành một **AI engineer**. microSched là nơi mình vừa thử nghiệm, vừa học, vừa xây một sản phẩm mà bản thân thực sự sử dụng. Nhu cầu hằng ngày giúp mình chọn việc cần làm; quá trình dùng thật cho thấy thiết kế, implementation hay cách cộng tác với AI còn cần cải thiện ở đâu.

- **Harness engineering và điều phối agent:** tổ chức agent theo vai trò, trong đó có PM quản lý phạm vi, ưu tiên và phối hợp công việc; giao task và context rõ ràng; review kết quả (cả việc review cũng giao cho các agent khác nữa xD) trước khi tích hợp vào dự án. Mình học cách tổ chức việc phát triển cùng AI thành một nhóm làm việc có phối hợp.
- **Software engineering và vận hành:** làm việc xuyên suốt frontend, backend và database, rồi đưa thay đổi qua deployment, CI/CD, kiểm chứng, backup và bảo trì. Vì tự dùng ứng dụng, mình phải quan tâm đến độ tin cậy và khả năng bảo trì trong thực tế.
- **AI engineering với Mimi:** phát triển một module AI ngay trong ứng dụng, từ tích hợp model và tool đến context, đề xuất thao tác Task/checklist, xác nhận rõ ràng và recovery. Mimi giúp mình học cách làm một sản phẩm AI và đánh giá nó có giúp ích cho công việc thực tế hay không.

Việc xây dựng, học và sử dụng ứng dụng bổ trợ cho nhau: mình thử một cách làm, kiểm tra kết quả, dùng nó trong đời sống rồi đưa điều học được vào thay đổi tiếp theo.

## Tổng quan kỹ thuật và bắt đầu phát triển

React/TypeScript/Vite build frontend tĩnh. Một process FastAPI phục vụ SPA và API, dùng PostgreSQL/pgvector trên Neon. Node chỉ cần ở development/build. Cấu hình Fly trong repo dùng một machine always-on; sức khỏe runtime cần bằng chứng riêng.

Fresh clone bắt đầu tại [development setup](docs/engineering/development.md): Python 3.14, Node 24, `uv sync --frozen`, `npm ci`, vai trò environment và các lệnh test. [Operations](docs/operations/runbook.md) mô tả deploy, readiness, backup/recovery và migration có quyền riêng. Mô tả source hiện hành không chứng nhận mọi browser, thiết bị thật hay live-provider journey.

Xem [đóng góp](CONTRIBUTING.vi.md) và [báo cáo security](SECURITY.vi.md). Không đưa credential, account identifier hay dữ liệu cá nhân vào issue, fixture hoặc PR. Source và logo/icon do project sở hữu dùng [MIT License](LICENSE); third-party assets giữ license riêng. Personal data và service account không nằm trong phạm vi cấp phép.
