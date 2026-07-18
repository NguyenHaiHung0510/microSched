# Decision brief — DB, hosting & backup (microSched)

> Decision record **tự-chứa** (đọc được ở phiên 0-context). Mọi mục dưới **đã chốt 18/07/2026** kèm lý do. Đây là cửa một-chiều (đổi DB/schema sau khi có data thì đắt).

## 1. Bối cảnh
microSched = app task/note/lịch cá nhân **một người dùng**, chạy web, hướng làm việc nhiều với AI, giữ dữ liệu quý (note). Bản mới **không dùng SQLite** — app cũ từng dùng đồng thời SQLite + Postgres dẫn đến split-brain (không rõ dữ liệu ở đâu), phải tránh lặp lại.

## 2. DB — ✅ PostgreSQL + `pgvector`
1. **Dữ liệu có cấu trúc + quan hệ** (task ↔ subtask, event ↔ nguồn lịch, note ↔ mục note) → DB quan hệ hợp hơn document DB. Câu hỏi kiểu "task tuần này" = query sạch, đáng tin (structured query trong bộ tool AI, Bước 1).
2. **`pgvector` = semantic search chung một DB** với dữ liệu cấu trúc → Bước 1 hybrid (query cấu trúc + tìm ngữ nghĩa trên chữ note) mà **không cần vector DB riêng** → không đồng bộ 2 kho.
3. **`JSONB`** cho phần linh hoạt + **bảng audit/log** sẵn cho tool ghi (Bước 2) & "log để fine-tune sau".

## 3. Phương án đã cân nhắc và loại
- **SQLite:** loại — web hosted + agent/UI đọc song song thì Postgres hợp hơn; và để tránh split-brain cũ.
- **Vector DB riêng (Pinecone/Qdrant):** loại — over-eng ở single-user, thêm một kho phải đồng bộ.
- **Mongo/document:** loại — dữ liệu quan hệ rõ, quan hệ hoá lợi hơn.

## 4. Nguyên tắc data model (AI-first + dễ xem)
"Khó xem" và "AI khó lấy dữ liệu" là **cùng một vấn đề** (xem `forward-spec.md` §C):
- **Mọi entity có `created_at`/`updated_at`** → note/task có "tính thời gian".
- **Lưu text đầy đủ**, chỉ cắt lúc hiển thị, luôn có "xem full".
- **Một tầng đọc sạch dùng chung cho UI + tool Agent** = "API endpoint sạch" mà strategy gọi là *lý do thật của rewrite* (Bước 2 tool ghi = chính các endpoint này).

## 5. Hosting — ✅ Neon (free tier)
Ngân sách mục tiêu <$1/tháng cho managed Postgres ≈ **free tier** (flat tier rẻ nhất cũng ~$5/mo: Neon/Heroku Essential; dưới đó chỉ có Neon usage-based scale-to-zero). Single-user → free tier dư dùng rất lâu → thực tế **$0**.

**Đã chọn Neon. Đã cân nhắc Supabase và loại.** So sánh (chính là lý do chọn) — cả hai đều có region Singapore (tốt cho VN) + pgvector:

| | **Neon** (đã chọn) | Supabase (loại) |
|---|---|---|
| Idle | Scale-to-zero, ngủ ~5' idle, dậy ~1s | Pause sau 7 ngày idle, request đầu ~30s |
| Free | ~0.5 GB/branch, 100 CU-h/mo, DB branching | 500 MB, 2 project, free KHÔNG có backup |
| Bonus | Branching tiện eval-in-CI sau | Gói auth/storage/realtime + pgvector docs tốt nhất |

**Lý do chọn Neon:** microSched single-user → không cần auth đa-user, nên BaaS gói-sẵn của Supabase phần lớn thừa. Neon scale-to-zero hợp app dùng ngắt quãng, không phải trông chừng "project paused". Đây là **cửa 2 chiều** (đổi provider = pg_dump/restore, luôn có sẵn dump) → chọn lại không đắt.

## 6. Backup & reliability — ✅ 3-2-1 đúng cỡ single-user
**Nguyên tắc cốt lõi:** provider durability **KHÔNG** phải backup — nó chỉ chống hỏng phần cứng của provider, KHÔNG cứu khỏi 4 rủi ro hay giết dữ liệu cá nhân nhất: (a) lỡ tay `DROP`/migration hỏng, (b) mất account/billing (free project bị pause/xoá, thẻ hết hạn), (c) provider biến mất, (d) corruption logic lan sang replica. Free tier thường không có backup → **bắt buộc có bản dump tự kiểm soát**.

**Thiết kế đã chốt (3 copy):** live trên Neon + dump-laptop + Google Drive auto-sync folder (3 copy / 2 domain kiểm soát). Điều kiện:
- Dump ghi **file có timestamp** (không ghi đè — vì Drive là *sync*, ghi đè/hỏng sẽ đồng bộ cái hỏng lên).
- **Mã hóa** file dump (chứa note riêng tư); không đẩy note thô lên bất kỳ repo nào.
- **Verify** định kỳ: restore dump vào Postgres tạm (Docker) → đếm dòng → drop. Backup chưa từng restore = "Schrödinger".
- **Bỏ** immutable/air-gap (lo doanh nghiệp). Tái dùng pattern `backup_service.py` của app cũ (`pg_dump -Fc` + atomic rename + retention + log).

**Không đầu tư availability tier** (five-nines vô nghĩa với 1 user; vài phút downtime hay 1s cold-start Neon không mất gì) — dồn hết vào backup + verify. Tự động hoá backup+verify = một mẩu CI/CD/observability đáng học (Track B). Xem `learnings-applied.md` (quy tắc 3-2-1).
