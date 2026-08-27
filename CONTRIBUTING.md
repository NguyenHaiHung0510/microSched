# Contributing

microSched là dự án cá nhân, nhưng feedback và pull request có phạm vi rõ vẫn được hoan nghênh.

## Trước khi bắt đầu

- Với thay đổi lớn về product, architecture hoặc data model, hãy mở issue/discussion để thống nhất hướng trước.
- Đọc `CLAUDE.md`, `AGENTS.md` và decision brief liên quan trước khi sửa.
- Không đưa secret, credential, token, dữ liệu cá nhân thật hoặc production payload vào code, fixture, log, issue hay PR.

## Pull request

- Tạo branch riêng và mở PR vào `develop`; không push trực tiếp vào `main` hoặc `develop`.
- Mô tả mục tiêu, phạm vi, trade-off và các kiểm tra đã chạy; tách rõ phần chưa verify.
- Chạy các lệnh tương ứng trong backend/frontend README trước khi mở PR.
- Giữ PR nhỏ, không gộp refactor không liên quan. Merge và deploy thuộc owner/repository gate.
