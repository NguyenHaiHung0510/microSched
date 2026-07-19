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

## 2026-07-19 — Nhóm 2: schema vật lý

- **3 tầng schema (khái niệm → logic → vật lý):** "chọn Postgres" mới là engine; *schema vật lý* mới là kiểu cột/khoá/index/DDL thật — và là **cửa một-chiều** sau khi có data. Áp: `schema-physical-brief.md`.
- **UUIDv7 (RFC 9562, native PG18):** khoá chính time-ordered → index nhỏ ~26%, đọc-theo-thứ-tự nhanh ~3× vs UUIDv4; sinh được ở client → khớp **offline-first**. Bài học: chọn khoá chính là chọn *cả cách sinh ID* (server vs client), không chỉ kiểu dữ liệu.
- **Enum = TEXT + CHECK, không native ENUM:** schema còn tiến hoá → tránh `ALTER TYPE` phiền; AI-tool đọc/ghi text dễ hơn.
- **Index có đánh đổi:** tăng đọc nhưng tốn storage + chậm ghi (mọi INSERT cập nhật mọi index) → single-user vài trăm dòng thì **không over-index**; chỉ FK + cột thời gian. (Học "index là gì" từ 0.)
- **Migration autogenerate hay sót** (đổi type, CHECK, rename→drop-mất-data) → dựng **hàng rào QA CI** (round-trip, drift-check, chặn drop ngầm, thử trên bản restore) = một mẩu CI/CD đáng học.
- **Log AI 3 tầng (obs/eval):** hội thoại (message) ≠ log đủ; cần *phong bì* trace (tool/token/cost/model/accept-reject) tách khỏi *raw blob* prompt-đã-ráp (đẩy off-DB). Tách để vừa eval được vừa không phình DB.
- **Đo thật > ước tính:** đưa số từ `n_live_tup` ( estimate) ra "2 note" — SAI; `COUNT(*)` thật = 49 note / 887 dòng. DB v2 ~1 năm = 10MB → Neon 0.5GB là non-issue cho nội dung; chỉ log AI là biến số. Bài học: dùng exact count, cẩn thận multi-schema + thống kê cũ.

## 2026-07-19 — Phiên thiết kế tracking (đang chạy)

- **Event vs state (sự kiện vs trạng thái):** "tracking" hoá ra là 3 thứ — nhật ký hành vi + sổ chi tiêu (đều là *sự kiện*, gộp được) vs subscription (*trạng thái có vòng đời*, hỏi về tương lai) → entity riêng. Nhét trạng thái vào bảng nhật ký là chỗ app chi tiêu hay gãy. Áp: `tracking-brief.md` §1.
- **Thiết kế tâm lý "đo khoảng cách, không đếm":** chủ ý không ghi số điếu — ghi số biến app thành hạn mức; ghi "có một lần" biến metric chính thành *đã bao lâu rồi* (chỉ tăng khi không làm gì). Yêu cầu sản phẩm ngược lên schema: value optional **theo tracker**, không theo entry.
- **Threat model quyết định mô hình bảo mật:** "đọc thấp ghi cao" (Bell-LaPadula) sinh cho multi-user có địch bên trong; single-user threat thật = người nhìn qua vai → write-up chỉ tạo "ghi mù" (bug), không tạo bảo mật. Chọn mô hình theo threat model, không theo độ "chuẩn sách".
- **Embedding leakage:** mã hoá cột gốc nhưng lưu vector embedding của nó = vẫn rò *nghĩa* (vector là biểu diễn có mất mát của nội dung). Câu hỏi mã hoá đúng phải là "cột nào vào pgvector, chấp nhận rò nghĩa không". Áp: scope phiên encryption-review, `tracking-brief.md` §6.
- **Đa tiền tệ — chuẩn hoá về 1 đơn vị tính:** mọi phép tính chỉ chạm cột VND; ngoại tệ lưu dạng số (`orig_amount`+`orig_currency`) nhưng chỉ để hiển thị; KHÔNG auto-FX (kéo theo nguồn tỷ giá + tỷ giá-tại-thời-điểm — over-eng cho 1 user).
- **Adjacency list + recursive CTE:** cây phân loại bằng `parent_id` tự trỏ; lá = nút bấm khi ghi (phân loại không thêm bước nhập); cộng dồn nhánh bằng recursive CTE — micro-giây ở quy mô nhỏ, giá thật là code phức tạp hơn. *(Cuối phiên: RÚT — nhu cầu thật chỉ 1 tầng nhóm → bảng `tracker_group` 2 tầng thắng cây ở mọi mặt. Bài học: soi ví dụ thật trước khi chọn cấu trúc tổng quát.)*

*(các mục dưới ghi lúc đóng phiên, cùng ngày)*
- **Composite FK làm cảnh sát nhất quán cho denorm cố ý:** `tracker.kind` phải khớp `group.kind` → `UNIQUE(id, kind)` trên cha + FK `(group_id, kind)` từ con: DB tự chặn lệch, 0 code app; group NULL → ràng buộc tự miễn (MATCH SIMPLE).
- **Chọn kiểu thời gian theo BẢN CHẤT khái niệm:** *thời điểm sự kiện* = `timestamptz` (B2) · *ngày lịch* (hết hạn sub) = `DATE` · *giờ lặp hằng ngày* (nhắc thuốc) = `TIME`. Ép tất cả thành timestamptz mới chính là nguồn bug lệch-một-ngày quanh múi giờ.
- **Trạng thái suy ra được thì đừng lưu:** `subscription` không có cột `status` — suy từ `expires_on` + `canceled_at` → miễn nhiễm update-anomaly (đúng tinh thần 3NF).
- **Partial unique index cho soft-delete:** UNIQUE `lower(name)` `WHERE deleted_at IS NULL` — chống trùng tên nhưng không chặn tái tạo tên đã xóa mềm; unique thường sẽ chặn nhầm.
- **Pattern nhắc-rồi-xác-nhận:** hệ thống chỉ push nhắc, dữ liệu chỉ sinh khi người xác nhận; mức "tiện" của bước xác nhận tùy bản chất việc (thuốc = ✓ 1 chạm ngay trên noti; gia hạn sub = phải xem xét/trả tiền ngoài rồi mới ghi). Auto-write không confirm để dành AI Bước 2 (có confirm + audit).
- **Bề mặt notification là bề mặt công khai:** text noti đọc được từ lock-screen → cho user tự kiểm soát độ kín đáo (`reminder_text` — "taken micardis?"). Privacy không chỉ nằm trong DB.

## 2026-07-19 — DevOps nền (git/PR/secret)

- **Threat model phải nêu tên cụ thể mới dùng được:** "lo bảo mật" là vô nghĩa; "ngại **social engineering**, không ngại người đọc repo" mới ra được quyết định (giữ public + vẫn cần private mode trong app). Bài học: hỏi *ngại AI nào* trước khi thiết kế biện pháp.
- **Phòng thủ nhiều lớp, chặn càng sớm càng rẻ:** push protection (server, lúc push) + pre-commit gitleaks (local, lúc commit). Lớp local bắt được cả secret tự chế mà pattern provider không biết.
- **Rule phải hợp quy mô đội:** branch protection đòi 1 approval sẽ **tự khóa** dự án một người (không tự duyệt PR của mình được) → đặt `required_approving_review_count: 0` nhưng vẫn bắt buộc PR. Copy best-practice của team lớn mà không chỉnh = tự bắn vào chân.
- **Dựng hàng rào TRƯỚC khi có thứ để rò rỉ:** làm secret-guard lúc repo còn chưa có code/`.env` — rẻ hơn nhiều so với lúc đã lỡ commit.
- **Đọc kỹ ranh giới gói dịch vụ:** "Copilot free có code review" là **sai** — free chỉ review vùng chọn trong IDE, review PR trên github.com cần bản trả phí. Cùng một cái tên tính năng, hai phạm vi khác hẳn (lặp lại đúng bài học "xác nhận đúng category" của phiên hạ tầng).
- **Giao việc cho agent = viết spec, không phải ra lệnh:** spec tự-chứa cần *bối cảnh + lý do*, **phần KHÔNG được làm**, acceptance kiểm chứng được, và đề xuất tier/effort — vì agent chạy ở session 0-context.
- **"Đã cài xong" ≠ "đang bảo vệ":** phải TEST hàng rào bảo mật bằng payload *giống thật*. Key mẫu trong tài liệu AWS không kích hoạt gitleaks (có allowlist cho giá trị ví dụ) → suýt kết luận sai theo cả hai chiều. Test bằng pattern thật mới lộ ra: gitleaks bắt GitHub PAT/Stripe nhưng **bỏ lọt `postgresql://user:pass@host`** — đúng loại secret nguy hiểm nhất của dự án này (Neon). Cùng họ với bài học "backup chưa restore = Schrödinger": công cụ chưa thử = chưa biết nó bảo vệ cái gì.
