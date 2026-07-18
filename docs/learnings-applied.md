# Learnings applied — microSched

> Nhật ký **kiến thức đã học → áp dụng thật** vào microSched. Ghi ngắn: *học gì · áp vào đâu · ref*. Dùng làm nguyên liệu weekly-notes / blog / phỏng vấn.

## 2026-07-18

### Quy tắc sao lưu 3-2-1 (và mở rộng 3-2-1-1-0)
- **Học:** 3 bản sao · 2 loại phương tiện · 1 offsite. Mở rộng: **1** bản immutable/air-gapped, **0** lỗi (verify/test-restore định kỳ). Encrypt mọi bản.
- **Áp vào microSched (đúng cỡ single-user):** live trên Neon + dump-laptop + Google Drive auto-sync = **3 copy / 2 nơi**. **Bỏ** immutable (lo doanh nghiệp). **Giữ verify** = test-restore vào Postgres tạm định kỳ (backup chưa restore = "Schrödinger"). **Mã hóa** dump (chứa note riêng tư). Dump ghi **file timestamp**, không ghi đè.
- **Insight cốt lõi:** *provider durability ≠ backup* — nó chỉ chống hỏng phần cứng của họ, không cứu khỏi lỡ tay / mất account / provider biến mất. Với app 1 người: đầu tư vào **backup + verify**, KHÔNG vào availability tier (five-nines vô nghĩa).
- **Ref:** [3-2-1 Backup Rule Explained (IBM Technology)](https://www.youtube.com/watch?v=WJzsX32qMJY)

### Vài khái niệm khác đã áp (giai đoạn thiết kế microSched, 18/07/2026)
- **Hybrid retrieval (structured + semantic):** Postgres + `pgvector`, nguyên tắc *"cấu trúc ở chỗ cần query, markdown ở chỗ viết văn xuôi"* → phục vụ Bước 1 AI đọc. (nguồn: AI Engineering / strategy doc)
- **Một nguồn sự thật (chống split-brain):** VC cũ dùng cả SQLite + Postgres → không rõ data ở đâu. Mới: **một store Neon duy nhất**, role DB riêng giới hạn quyền.
- **Right-size characterization:** không copy y hệt hành vi app cũ (đang redesign) → port logic hữu ích + lo migrate data, dồn công test/eval sang **tính năng AI** nơi nó đáng.
- **Rewrite big-bang + đường lùi:** giữ VC cũ (`main`) chạy tới khi tự tin cutover.
