# agent-tasks/ — hàng đợi việc giao cho agent

Mỗi file `NNN-<slug>.md` là **một spec tự-chứa** để giao cho một agent chạy độc lập.

## Cách dùng
1. Mở một session Claude Code mới trong repo này.
2. Ra lệnh: *"Đọc `agent-tasks/001-precommit-gitleaks.md` và thực hiện đúng spec đó."*
3. Agent làm xong → chính chủ (hoặc agent điều phối) review theo mục **Acceptance** trong spec.
4. Xong thì đổi `Trạng thái:` ở đầu file thành `✅ DONE (ngày)` — **không xóa file**, giữ làm lịch sử.

## Quy ước viết spec
- **Tự-chứa**: đọc được ở session 0-context. Không tham chiếu hội thoại cũ, chỉ tham chiếu file trong repo.
- **Nêu rõ ràng buộc + lý do**, không chỉ ra lệnh — agent cần biết *tại sao* để xử lý đúng lúc gặp tình huống ngoài spec.
- **Acceptance kiểm chứng được** (chạy lệnh nào, thấy output gì), không phải "làm cho tốt".
- **Nói rõ cái KHÔNG được làm** — phần này quan trọng ngang phần phải làm.
- Mỗi spec ghi sẵn **model tier + effort đề xuất** để chính chủ chọn đúng mức, không đốt token thừa.

## Hàng đợi
| # | Việc | Trạng thái |
|---|---|---|
| 001 | pre-commit + gitleaks (chặn secret trước khi commit) | ✅ DONE (2026-07-19) — đã kiểm chứng thật |
| 002 | gitleaks: rule riêng cho connection string DB (lỗ phát hiện khi kiểm chứng 001) | ✅ DONE (2026-07-19) — đã kiểm chứng thật |
