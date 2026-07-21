# forward-spec.md — Backlog tính năng microSched

> **Tự-chứa.** Nguồn: note "Nâng cấp microSchedule" của chính chủ (18/07/2026) + đối chiếu `chien-luoc-he-2026.md` / `track_ai_eng_strategy.md`.
> **Forward spec** = tính năng MUỐN CÓ ở bản mới; tách khỏi backward spec (hành vi cũ). Cờ: ✅ đã quyết · ⚠️ OPEN (chưa xếp lịch) · DEFER (để sau) · 🆕 mới.

## A. Item đã được quyết ở strategy doc
| Note gốc | Trạng thái | Quyết định |
|---|---|---|
| "Chuyển kiến trúc multi app + deploy" | ✅ SUPERSEDED | Web (1 server), KHÔNG multi-app |
| "1 app desktop + 1 app mobile (đồng bộ)" | ✅ SUPERSEDED | Web/PWA thay cả hai; không nuôi 3 client |
| "Nhắc uống thuốc (rất cần)" | ✅ MUST-HAVE | Web push (PWA) lo phần lớn; bọc native chỉ nếu thực tế không đủ tin. **2026-07-19 thiết kế CHỐT:** tracker thường + `reminder_time`/`reminder_text` (noti kín đáo kiểu "taken micardis?"), ✓ trên noti = ghi 1 chạm, không streak — `tracking-brief.md` §12 |
| "A2A agent, routing ở lõi" | ✅ direction | Tên đúng = cascade/routing (không phải A2A). A2A → DEFER; cascade self-verify là hướng auto-mode |
| "Log all to fine-tune later" | ✅ aligned | Log mọi truy vấn từ đầu (eval + fine-tune cuối hè); fine-tune sau Bước 2 |

## B. UX mới đáng làm (Track A — agent làm, chính chủ review) — ⚠️ chưa xếp lịch
- Reschedule nhanh task trễ hạn → hôm nay / mai / ngày kia. *(cũng là ứng viên tool ghi đầu tiên cho AI Bước 2 — "move task")*
- Quick-add task bằng tooltip lịch tháng + kéo-thả vào ô ngày.
- Đánh dấu ngày đặc biệt (vd "ngày về quê") — annotation trên calendar.
- Ẩn / khoá task-note riêng tư — single-user nên là "kín đáo", không phải bảo mật đa-user.
  - **⚠️ 2026-07-19 SUPERSEDED (phiên tracking):** yêu cầu nâng cấp — không chỉ "kín đáo" mà là **private mode có auth gate thật** (mở bằng xác thực, phạm vi session), phủ cả **tracker + giá nhạy cảm**, kèm rà soát **mã hóa toàn DB** (phiên riêng). Xem `tracking-brief.md` §5–§6; cơ chế mở → phiên auth.
- DEFER "Lời nhắn từ tương lai" cho note khi review/hoàn thành — nice-to-have.

## C. 🆕 Nguyên tắc thiết kế: "viewability" (xem được)
Nhiều note gốc cùng một nỗi đau: **dữ liệu KHÓ XEM** — tooltip date-cell/note-cell bị cắt, ghi chú task 1 dòng, "xem full = phải bấm sửa", note không thể hiện mới/cũ. (Bằng chứng: một note dài phải tách làm 3 ảnh mới xem/ghi hết.)
→ Nguyên tắc bản mới (khớp mục tiêu AI-first):
1. Lưu full, chỉ cắt lúc hiển thị; luôn có "xem full" không cần vào chế độ sửa.
2. Mọi entity có mốc thời gian → note/task có "tính thời gian".
3. Một tầng đọc sạch dùng chung cho UI + Agent. "Khó xem" và "AI khó lấy dữ liệu" là **cùng một vấn đề, cùng một cách sửa** (xem `db-and-data-model-brief.md`).

## D. AI thật (Track B — phần đáng bảo vệ thời gian)
- Assistant read-only trên task/note (Bước 1) — hybrid retrieval.
- Tool ghi hẹp (Bước 2) — "move task", "tạo note"… có confirm + audit.
- Auto-mode = cascade (model rẻ → tự kiểm → escalate); KHÔNG learned router (over-eng single-user).
- DEFER memory cho Agent (dynamic feature trong AI Eng book) — sau Bước 2.

## E. 🆕 Tracker (sức khỏe + tài chính) — ✅ làm ngay, mô hình hợp nhất
- Theo dõi "hoạt động xấu" (thuốc/bia/bi-a) **và** chi tiêu cá nhân → gộp một mô hình `tracker`/`entry` (xem `schema-v1-brief.md`).
- **Xây phần ghi-log ngay** (dữ liệu tích lũy sớm → tới lúc Bước 1 AI chạy đã có data thật để hỏi). **AI phân tích thói quen/chi tiêu giữ đúng thứ tự sau** (không để dựng UI tracker nuốt thời gian 2 tính năng AI).
- Bảo mật: health + finance nhạy cảm → bar bảo mật nổi lên khi AI đọc qua LLM bên thứ ba (bookmark Bước 1: cân nhắc model local cho phần nhạy cảm).
- **⏸ Thiết kế chi tiết = phiên riêng (mục tiêu chiến lược):** kiểu số `entry.value`, cascade `tracker→entry`, mô hình feature — parked ở `schema-physical-brief.md` §7 (C2 + D1-tracker).
- **2026-07-19 — phiên tracking ĐANG CHẠY:** quyết định giữa phiên ghi tại `tracking-brief.md` (3 loại dữ liệu A/B/C, subscription = entity riêng, bộ cột tiền VND + giá gốc dạng số, private mode nâng cấp, mở phiên encryption-review riêng).
- **2026-07-19 (muộn) — phiên tracking ĐÃ ĐÓNG, toàn bộ ✅:** thêm luồng ghi + dashboard spec, `tracker_group`, thu nhập (direction), VND-only v1, rà soát chuẩn hóa toàn cục (§10), subscription (§11), nhắc thuốc (§12). **Schema toàn dự án khép.**

## F. Ghi chú tài nguyên (không phải feature)
- Chính chủ có free credit Google AI Studio (nhiều acc qua OpenRouter) + OpenAI → backend model rẻ Bước 1 + chạy eval/experiment. Khớp line "OpenRouter pay-as-you-go" trong strategy. *(Dùng đúng mức học tập, tránh lách ToS.)*

### 📝 2026-07-21 — ⏸ TODO nghiên cứu: pool model free (hoãn tới lúc thật sự gắn API)
Ngoài OpenAI platform + Google AI Studio + OpenRouter còn nhiều nơi cho dùng model free ở cỡ vài trăm tỉ tham số (chính chủ nhắc NVIDIA — có lẽ `build.nvidia.com`). **Chưa tra** — cố ý hoãn tới khi thật sự cắm API vào microSched, vì chính sách các chỗ này đổi theo quý, tra sớm là tra lại.
Khi tra, cột quyết định **không phải giá mà là "có train trên data không"** — vì nó ánh xạ thẳng vào lằn ranh đã khoá ở `auth-brief.md` R1–R7:

| Ngữ cảnh | Đường đi | Căn cứ |
|---|---|---|
| task/note **không** private, calendar | model free thoải mái | R3 — free tier thường free *vì* được train trên prompt (đã ghi ở `devops-brief.md` §7 cho OpenAI daily-free) |
| health, finance, note/task private | buộc zdr/no-train cả cascade | R5 — free tier gần như tự loại |

⇒ Model free phủ **phần lớn** tính năng microSched; phần còn lại đã có R1–R7 chặn sẵn. Không phải quyết định mới.

### 📝 2026-07-21 — retrieval: FTS trước, embedding khi corpus xứng đáng
Corpus thật hiện tại = **49 note + 163 task**. Semantic search kiếm cơm ở quy mô hàng nghìn+; ở ~200 tài liệu thì `tsvector` + `pg_trgm` chạy ngay trong Neon: $0, không provider, không bar retention, không phải chọn dimension, không gì rời khỏi DB. (`schema-physical-brief.md` §C4 đã ghi sẵn: *"ở quy mô 49 note hiện tại, index vector còn chưa cần thiết cho tốc độ"*.)
**Không phải hoãn AI** — hybrid retrieval vốn ba chân (structured + keyword + semantic); ở cỡ này hai chân đầu gánh gần hết, chân thứ ba thêm vào khi **đo được** nó cải thiện — mà phần "đo được" chính là eval, đúng thứ đáng học. ⇒ quyết định ⚠️ OPEN *embedding provider* tụt từ **chặn đường** xuống **rẻ và để sau**; cột `vector` vốn đã nullable nên thêm sau chỉ là một migration nhỏ.

### 📝 2026-07-21 — credit GCP ₫7,9M (~$300): ✅ chốt BỎ QUA
Tài khoản đã lên full (GPU được mở, nhưng quota mặc định 0 → phải xin). **Quyết định: không đuổi theo.** Fine-tune / distributed / GPU là **ML engineering (hạ tầng huấn luyện)**, không phải **AI engineering (xây trên model)** — track mà kế hoạch hè này nhắm. Đổi hướng học vì ₫8M sắp hết hạn chính là lỗi chi phí cơ hội. Cửa để ngỏ nếu tò mò: **Vertex managed tuning** không cần quota GPU và không kéo theo MLOps (một buổi chiều, không đổi track).
⚠️ **Vệ sinh bắt buộc:** account giờ là *full / pay-as-you-go, KHÔNG tự dừng*, và budget alert **chỉ gửi mail chứ không chặn chi**. Credit hết **28/08/2026** → sau đó mọi thứ còn chạy sẽ vào thẻ. Đặt nhắc **27/08 quét sạch tài nguyên**. Rủi ro nằm ở chỗ quên tắt, không nằm ở chỗ để credit hết hạn.

---
*Bản chụp backlog để đối chiếu, KHÔNG phải cam kết làm hết. Ưu tiên: bảo vệ item AI (§D, §E-analysis) khỏi bị đống UX nuốt thời gian — đúng cảnh báo §3 strategy.*
