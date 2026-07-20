# Thiết kế tính năng TRACKING — microSched

> **Trạng thái: ⚠️ PHIÊN ĐANG CHẠY (2026-07-19)** — bản "chốt tới đâu ghi tới đó" giữa phiên, đề phòng mất context.
> Cờ từng mục: **✅ CHỐT** (chủ minh thị xác nhận) · **✅ CHỐT-ủy-quyền** (chủ nói "tùy bạn, tư vấn mình" → Claude quyết, có ghi rõ) · **⚠️ ĐỀ XUẤT** (Claude đề xuất, CHƯA gật) · **OPEN** (chưa bàn xong) · **DEFER** (đẩy phiên khác).
> Tự-chứa. Giải cụm parked ở `schema-physical-brief.md` §7 (C2, D1-tracker, feature design — note gốc #18) + các yêu cầu mới chủ nêu trong phiên (giá gốc/thực trả, private mode, mã hóa).

---

## 0. Tầm nhìn (lời chủ, đã chưng cất)

- Ghi lại để **nhìn rõ** những lần làm hành động không tốt (hút thuốc / uống bia / bi-a) — con số quan trọng nhất là **"lần cuối là bao giờ"**.
- Có **dashboard thống kê** (tổng lần theo tuần/tháng/năm, trung bình ngày/lần…) *bên cạnh* AI agent assistant.
- Hút thuốc: **chủ ý KHÔNG ghi số điếu, không ghi tiền**. Bia / bi-a: **cần ghi tiền**.
- Ngoài log hành động: log **chi tiêu muốn quản lý** (mua game, gói subscription AI…) — sub cần **thời hạn** kèm tiền (optional); có **2 giá**: giá niêm yết ($22.22 ~600k) vs **giá thực trả** (300k khi có promotion).
- Kéo theo: chế độ **public/private** (mục gắn "ẩn/nhạy cảm" chỉ hiện full ở private, cần auth) + toggle hiển thị giá.

---

## 1. Ba loại dữ liệu — không phải một ✅ CHỐT

| | Đơn vị của một dòng | Câu hỏi trả lời | Mô hình |
|---|---|---|---|
| **A. Nhật ký hành vi** (thuốc, bia, bi-a) | một lần xảy ra | "Lần cuối là bao giờ?" | `tracker`/`entry` |
| **B. Sổ chi tiêu** (mua game, chi lẻ) | một giao dịch có tiền | "Tháng này tiêu bao nhiêu, vào đâu?" | `tracker`/`entry` (A + cột tiền) |
| **C. Sổ đăng ký** (sub AI, các gói) | một **hợp đồng đang chạy**, có vòng đời | "Cái nào sắp hết hạn?" (câu hỏi về **tương lai**) | **entity riêng** |

- **A + B gộp được thật** — cùng là "sự kiện tại một thời điểm", B chỉ thêm tiền. Đúng mô hình `tracker`/`entry` đã chốt ở `schema-v1-brief.md`.
- **C = entity riêng, làm đúng ngay từ đầu** ✅ CHỐT (lời chủ: "nên làm đúng ngay từ đầu"). Subscription là **trạng thái** (bắt đầu → gia hạn → hết hạn → hủy), không phải sự kiện; ngày hết hạn là dữ liệu hạng nhất, không suy ra từ lần trả gần nhất.
- **Quan hệ C → B:** mỗi lần gia hạn **sinh ra** một entry chi tiêu — tái dùng pattern `calendar_source → calendar_event` (một nguồn sinh nhiều lần xuất hiện). Chi tiết entity → §8.3 (OPEN).

## 2. Triết lý nhóm A — đo KHOẢNG CÁCH, không đếm ✅ CHỐT

- Không ghi số điếu là **chủ ý thiết kế tâm lý**, không phải thiếu sót: ghi số → app hạn mức ("hôm nay còn mấy điếu"); ghi "có một lần" → con số nhìn hằng ngày là ***đã bao lâu rồi*** — thứ chỉ tăng khi mình không làm gì. Giữ nguyên chủ ý.
- **Hệ quả (mức nguyên tắc) ✅:** tiền/số lượng optional **theo TRACKER, không theo từng lần ghi** — tracker khai báo sẵn "tao ghi gì" (chỉ sự kiện / sự kiện + tiền / sự kiện + số lượng) → form nhập mỗi tracker chỉ hỏi đúng thứ cần, ghi vẫn một chạm. Cột cấu hình cụ thể → chốt cùng luồng ghi (§8.1).

## 3. Tiền — cách lưu ✅ CHỐT

| Cột trên `entry` | Vai trò | Trạng thái |
|---|---|---|
| `amount` | **thực trả, VND** — mọi phép tính/dashboard CHỈ chạm cột này | ✅ CHỐT |
| `list_amount` | giá niêm yết **quy VND** (600k) → tiết kiệm = `list_amount − amount` | ✅ CHỐT |
| `orig_amount` + `orig_currency` | `22.22` + `USD` — **dạng SỐ, không text** (lời chủ: "giá trị đó có giá trị sử dụng") — giữ sự thật để hiển thị "$22.22" | ✅ CHỐT |

- **Không quy đổi tỷ giá tự động** ✅ — `list_amount` nhập tay lúc ghi; ngoại tệ chỉ để hiển thị. (Auto-FX kéo theo nguồn tỷ giá + tỷ giá-tại-thời-điểm + lưu lịch sử — chi phí lớn, giá trị ~0 cho một người dùng.)
- **📝 2026-07-19 (muộn hơn trong phiên) — VND-ONLY cho v1 ✅ CHỐT (lời chủ):** "không cần lưu/xử lý gì liên quan tới $ trong hệ thống hiện tại, cứ dùng VND trước mắt" → **cắt `orig_amount` + `orig_currency` khỏi v1** (2 dòng cuối bảng trên coi như DEFER). Khi nào thật sự cần $ → thêm lại 2 cột nullable (không cửa một chiều), lúc đó mới bàn validate currency (ISO 4217). V1 chỉ còn: `amount` + `list_amount`, đều VND.
- **Toggle hiển thị giá: `giá gốc / giá thực trả / hybrid`** — ✅ CHỐT là *cần có*; là `app_setting`, thiết kế cụ thể ở **phiên frontend** (📌 đã note).
- ✅ **CHỐT — KHÔNG trộn "xem giá gốc" với private mode** (chủ gật 2026-07-19): private trả lời "*ai được xem*", toggle giá trả lời "*xem con số nào*"; trộn nhau dễ quên chế độ đang bật và đọc sai mức chi thật. **Hai công tắc riêng.**

## 4. Phân loại + thu nhập — nhu cầu ✅ CHỐT, cơ chế ⚠️ ĐỀ XUẤT

- **Nhu cầu ✅:** khi ghi cần "loại", ví dụ `chi tiêu → giải trí → Mua game` (nhóm A có thể không cần loại — mô hình phải cho phép nông). **2026-07-19 bổ sung ✅:** log cả **THU NHẬP** (lương, chu cấp bố mẹ, thưởng, khoản đầu tư có mục đích) — không chỉ chi.
- **📝 2026-07-19 — rút đề xuất cây `parent_id`:** khi soi kỹ, ví dụ `chi tiêu → giải trí → Mua game` có tầng đầu = `kind` (đã có) và tầng cuối = `tracker` (đã có) → chỉ thiếu **đúng một tầng nhóm ở giữa**. Cây tự trỏ thua bảng nhóm 2-tầng ở mọi mặt cho nhu cầu này (recursive CTE vs JOIN thường; rủi ro vòng lặp; mơ hồ "nhánh có giữ entry không"). Cần sâu hơn sau này → thêm cột vào bảng nhóm, không phải cửa một chiều.
- **Cơ chế ✅ CHỐT (chủ gật 2026-07-19 — "có gì sau cần mở rộng thì sửa sau chưa muộn"):**
  - Bảng **`tracker_group`** (`id`, `name`, `kind`, `color`, `position`) + **`tracker.group_id` nullable** — nullable để tracker hành vi (`Hút thuốc`) ngồi thẳng dưới kind, không ép nhóm. Là bảng chứ không phải cột text (gõ tay "Giải trí"/"giải trí"/"Giai tri" = 3 nhóm ma).
  - **`tracker.direction`** = `'in'`/`'out'` (TEXT+CHECK, khớp C1) — nằm trên **tracker, không phải entry**: tracker `Lương` khai `in` một lần, lúc ghi không bao giờ chọn chiều → giữ luật một chạm. **Tiền luôn lưu số dương**; dấu là việc của `direction` khi cộng dồn (lưu số âm = ổ bug kinh điển). Nhóm `Thu nhập` = một `tracker_group` thường.
  - Hệ quả đẹp của mô hình hợp nhất: **"tổng chi" = mọi entry có tiền + `direction='out'` bất kể `kind`** — tiền bia (kind=health) tự động vào tổng chi tài chính.
- **Quỹ có mục đích (earmarked fund)** — ví dụ chủ: "3 triệu mẹ đầu tư mua sub AI học hè", muốn biết "còn lại bao nhiêu" → đòi **nối** khoản thu với các khoản chi từ nó (envelope budgeting) = tính năng riêng, không phải một cột. **MUỐN — DEFER**: v1 ghi `in` vào tracker `Chu cấp học hè` + chi ghi `out` như thường; thiết kế fund entity sau nếu nhu cầu thật lặp lại.

## 5. Private mode — nhận diện & cắt phạm vi

- **Phát hiện quyết định cũ bị vượt:** `forward-spec.md` §B từng ghi *"Ẩn/khoá task-note — kín đáo, KHÔNG phải bảo mật đa-user"*. Yêu cầu mới của chủ (phiên này) = **private mode có auth gate thật** (mật khẩu/OAuth, phạm vi session), phủ **task + note + tracker + giá**. → **SUPERSEDED 2026-07-19**, đã ghi note có ngày bên `forward-spec.md`.
- **📝 2026-07-19 (đóng phiên) — threat model nói rõ hơn:** chính chủ xác nhận thứ thật sự ngại là **social engineering** (thông tin cá nhân bị dùng dựng pretext), KHÔNG phải người đọc được repo/code. Đây là lý do nền của cả private mode (§5) lẫn noti kín đáo (§12). Chi tiết + quyết định giữ repo public: `devops-brief.md` §1.
- **✅ CHỐT-ủy-quyền — BỎ "đọc thấp ghi cao"** (chủ: "tùy bạn thôi, tư vấn mình"): mô hình write-up (Bell-LaPadula) sinh cho môi trường nhiều người có địch bên trong; threat model thật ở đây là **người nhìn qua vai**. Cho ghi-lên-private từ public = ghi mù không đọc lại/sửa được → tạo bug, không tạo bảo mật. **Private = lớp che hiển thị**; muốn ghi vào private thì bật private (vài giây nhập auth). Ở private ghi được cả public (không cần chuyển).
- **DEFER → phiên auth:** cơ chế mở private — 2 phương án của chủ ghi nguyên trạng chờ phiên đó: (1) OAuth, account được cấu hình cứng bật private hay không; (2) mật khẩu cứng (có mã hóa/hash), mở cho phạm vi hẹp (một session hoặc hẹp hơn). Phiên auth vốn đã OPEN (`architecture-brief.md` §7) — giờ gánh thêm mục này.
- 📝 **2026-07-20 — ✅ GIẢI (phiên auth, `auth-brief.md`):** chọn phương án **(2)** — passphrase riêng (Argon2id), mở theo session TTL 15′; **loại (1)** vì allowlist chỉ có 1 account → cờ cứng = private luôn mở = không còn là cổng. Kèm quyết định mới **AI × private (R1–R7)**: AI đi theo đúng cổng private của session ("khi bật private là toàn quyền" — lời chủ, nhất quán ràng buộc §6 "AI PHẢI đọc được"); message sinh lúc unlocked mang `is_private` (K11 mở rộng xuống message); **giữ nguyên** luật §6 không-embed/FTS trên cột mã hóa — thay bằng runtime-search khi unlocked.
- **Không cửa một chiều:** cờ `is_private` = cột nullable, thêm lúc nào cũng được. Cửa một chiều thật là **mã hóa** (§6). Tiền lệ sẵn: `calendar_event.is_hidden`.

## 6. Mã hóa — mở phiên riêng "ENCRYPTION REVIEW" ✅ CHỐT

- **Phạm vi = TOÀN DB** (lời chủ: "không chỉ dữ liệu nhạy cảm, toàn bộ DB cần được xem xét chỗ nào cần chỗ nào không, cân đối trade-off theo quy mô").
- **Ràng buộc cứng ✅:** app giữ khóa — **đã có hàm mã hóa thì phải có giải mã; AI đã được thiết kế vào hệ thống thì PHẢI đọc được** (lời chủ). *(Sửa nhận định sai trong phiên: "mã hóa thì AI Bước 1 không đọc được" — sai, AI chạy trong app nên đọc qua tầng giải mã bình thường.)*
- **Trade-off thật cần rà (điểm xuất phát cho phiên đó):**
  1. Cột mã hóa với Postgres = byte vô nghĩa → mất `SUM`/`ORDER BY` trong SQL (**không đau** — vài nghìn dòng kéo về app tính bằng Python); mất index + full-text search (**chạm D4** đang DEFER Bước 1).
  2. **Embedding rò nghĩa** — chỗ đau nhất: mã hóa `note.body_md` nhưng lưu vector của nó = vector là biểu diễn có mất mát *của chính nội dung* → đọc DB không ra chữ nhưng dò được ý. Câu hỏi thật của phiên đó: **cột nào cần vào pgvector, và có chấp nhận rò nghĩa qua embedding không** — đây là chỗ mã hóa đánh nhau với AI-first.
  3. Mất khóa = mất data vĩnh viễn → đường backup khóa **tách khỏi** backup DB (nối vào 3-2-1 của `db-and-data-model-brief.md`).
- **Điểm mù ghi sớm:** ***tên tracker*** — `"Hút thuốc"` rò gần hết thông tin dù mọi entry mã hóa. Mã hóa entry mà để tên tracker trần = bảo mật hình thức.
- **Sơ bộ (chưa phải kết luận):** cần cân nhắc = tiền thực trả, entry tracker sức khỏe, note gắn private; gần chắc không = `calendar_event`, `app_setting`, mốc thời gian.
- **Yêu cầu nghiên cứu cho phiên đó:** tra live chính sách (Neon encryption-at-rest, data-retention của LLM provider khi AI đọc dữ liệu nhạy cảm — nối bookmark "privacy bar Bước 1") — theo checklist infra-research (tra tại chỗ, date-stamp).

### 📝 2026-07-20 — ĐÓNG "ENCRYPTION REVIEW" ✅ CHỐT

**Nghiên cứu live (tra tại chỗ, date-stamp 2026-07-20):**
- **Neon encryption-at-rest:** AES-256 (XTS-AES-256 trên NVMe) + TLS 1.2/1.3 in transit, SOC 2 Type II. **Khóa do Neon/AWS KMS giữ, không có BYOK** ([Neon Security overview](https://neon.com/docs/security/security-overview), [neon.com/security](https://neon.com/security)). → chỉ chống mất cắp phần cứng ở data center; **không** chống connection-string lộ, account bị chiếm, hay khớp threat-model "social engineering" của chủ — không được tính là "đã mã hóa rồi".
- **LLM provider data-retention:** Claude API mặc định **không lưu prompt/output**, không train trên data API ([API and data retention — Claude Platform Docs](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention)). Ngoại lệ cần nhớ khi chọn model Bước 1: model lớp "Covered" (vd Fable 5/Mythos 5) **bắt buộc lưu 30 ngày** — loại các model này khỏi ứng viên nếu muốn giữ mặc định no-retention; nội dung bị hệ thống an toàn gắn cờ có thể lưu tới 2 năm (áp dụng mọi model). Embedding provider (bên thứ ba, chưa chọn) → điều kiện chọn thầu Bước 1: phải đạt bar "no retention/no training", không tra trước danh sách cụ thể bây giờ.

**Quyết định phạm vi mã hóa (posture B-hẹp — mã hóa đúng nhóm "lộ = nguyên liệu pretext", KHÔNG mã hóa rộng vì đánh chết AI-first):**

| Cột / nhóm | Phán quyết | Lý do |
|---|---|---|
| `tracker.name` (toàn bộ, không chỉ tracker nhạy cảm) | 🔐 mã hóa | Điểm mù đã ghi ở trên — `"Hút thuốc"` rò gần hết dù entry mã hóa. Mã hóa *tất cả* (không rẽ nhánh theo độ nhạy) = một kiểu cột duy nhất, sort/hiển thị ở app-side. |
| `subscription.name` | 🔐 mã hóa | Danh sách dịch vụ đang trả tiền = nguyên liệu pretext kinh điển ("gọi từ X về thanh toán…"). |
| `entry.note` (text tự do trên entry) | 🔐 mã hóa | Ngữ cảnh sức khỏe/hành vi tự do gõ. Không cần FTS/embed ở v1. |
| `note.body_md`, `task.*` khi `is_private=true` | 🔐 mã hóa **theo cờ** | Private = che hiển thị (§5) **+ che at-rest** — nhất quán một nghĩa "private". Nội dung private vốn đã không vào FTS/embedding nên không mất gì thêm. |
| `note`/`task` không private | 📖 trần | Lõi retrieval của AI Bước 1 — phải FTS/embed được. Escape hatch = bật private. |
| **Cột tiền** `amount`/`list_amount`/`orig_amount` | 🔐 **mã hóa** *(chủ chọn lật từ đề xuất "trần" ban đầu — an toàn hơn dashboard-aggregate)* | Chấp nhận đánh đổi: mất `SUM`/`ORDER BY`/CHECK trực tiếp trong SQL, mọi tổng dashboard (§8.2) phải kéo entry về app rồi cộng bằng Python (khối lượng vài nghìn dòng — không đau, đã nói ở §6 gốc). |
| `tracker_group.name` | 📖 trần | Nhãn nhóm chung chung ("Giải trí/Ăn uống") — giá trị pretext ~0; giữ trần cho seed-migration + sort đơn giản. |
| `tracker.reminder_text` | 📖 trần **có chủ đích** | Được thiết kế là bề mặt công khai (§12 — hiện trên lock-screen qua web-push); mức kín do chủ tự gõ, mã hóa in-DB không đổi bản chất đó. |
| `calendar_event.*`, `app_setting`, timestamps/enums/ids | 📖 trần | Không đổi so với sơ bộ §6 gốc; calendar vốn nằm ở Google. Luật kèm: `app_setting` **cấm** chứa secret thật (secret → Fly secrets/`.env`, không qua DB). |

**Cơ chế:** mã hóa **app-level** (thư viện `cryptography`, AES-GCM), **không dùng `pgcrypto`** — pgcrypto bắt khóa đi trong câu SQL tới server Neon, tự phá mục đích giữ khóa ở app. Ciphertext có version-prefix (`enc:v1:…`) để xoay khóa sau không phải touch mọi hàng cùng lúc. Master key: Fly secrets (runtime) + `.env` (local dev).

**Luật pgvector/FTS (chốt cứng — đây là chỗ mã hóa "đánh nhau" với AI-first §6 gốc đã nêu):** ***đã mã hóa ⇒ không embed, không tsvector, hết.*** Không cân đo "rò nghĩa bao nhiêu % chấp nhận được" — né hẳn. AI vẫn đọc đủ theo ràng buộc cứng của chủ (app giải mã trước khi nhồi context) — chỉ mất khả năng *tìm bằng ngữ nghĩa/từ khóa trực tiếp trong Postgres* trên các cột mã hóa; tìm theo entity liên kết (vd "entry của tracker X") vẫn qua structured query bình thường, không qua vector.

**Phát hiện phụ (rà toàn-DB phát lộ, chưa ai ghi trước đây):**
1. **Log AI 3 tầng (schema-physical-brief.md §5 D3) tự phá mã hóa nếu không có luật riêng** — tầng 3 (raw replay blob = prompt đã ráp, **nội dung đã giải mã**) đẩy ra Google Drive = dựng lại đúng đường rò vừa bịt, ở chỗ khác. Luật: tầng 1 (message text) mã hóa cùng cơ chế cột; tầng 2 (metadata) trần; **tầng 3 bắt buộc mã hóa file-level trước khi rời máy**, dùng chung công cụ với backup dump (xem `db-and-data-model-brief.md` §6, cập nhật cùng ngày).
2. **`audit_log.payload`** (JSONB, Bước 2 write-tool) — khi diff đụng field đã mã hóa: ghi marker + entity id, **không bao giờ ghi plaintext của field mã hóa vào payload**.

**Cửa một chiều thật sự chỉ có MỘT:** bật mã hóa cột (đổ dữ liệu vào rồi đổi ý = migration + backfill giải mã). Chọn *cơ chế* (age vs khác cho file-level), *vị trí lưu khóa*, hay thêm/bớt cột **không** phải cửa một chiều — sửa được bất cứ lúc nào.

Cập nhật ngược cùng ngày: `schema-physical-brief.md` (bảng §1 + mục mã hóa mới), `db-and-data-model-brief.md` §6 (mã hóa dump + vị trí khóa), `CLAUDE.md`.

## 7. Giải các mục parked của Nhóm 2

### C2 — kiểu số `entry.value` ✅ CHỐT (2026-07-19)
- **Phát hiện:** một cột `value` gánh 2 nghĩa (tiền + số lượng) là sai từ gốc — precision khác, ý nghĩa khác. **Tách:** `quantity` (số lượng, hiếm dùng — nhớ là "không đếm điếu"; có thể lẻ) + bộ cột tiền §3.
- **Precision:** cột VND (`amount`, `list_amount`) = `NUMERIC(14,0)` (VND không phần lẻ; trần ~100 nghìn tỷ — dư); `orig_amount` = `NUMERIC(12,3)` (phủ tiền tệ 3 số lẻ như KWD); `quantity` = `NUMERIC(10,2)`. **Không `float`** (sai số tiền — khớp hướng nghiêng cũ của C2).

### D1-tracker — cascade `tracker → entry` = **RESTRICT + soft-delete** ✅ CHỐT (2026-07-19)
- Xóa nhầm 1 tracker mất sạch lịch sử log sức khỏe/tiền = đau → **RESTRICT** (chặn xóa khi còn entry) + **soft-delete** (`deleted_at`, khớp D3 đã chốt). "Dọn" tracker khỏi UI = ẩn/archive, không phải xóa thật.

## 8. Luồng ghi + dashboard (thiết kế 2026-07-19)

**Ba tầng quyết (meta — chốt cách làm việc ✅):** (1) *cột schema* → quyết phiên này; (2) *câu hỏi dashboard phải trả lời* → chốt phiên này ở mức hành vi, làm spec cho frontend; (3) *trình bày* (layout/chart/màu) → phiên frontend; (4) *insight/pattern* → AI Bước 1, **cố ý không làm UI**. Kiểm chứng: toàn bộ dashboard dưới đây chỉ cần **một cột schema mới** (`tracker.direction` §4) — phần trình bày hoãn an toàn.

### 8.1 Luồng ghi (capture flow)
- **Nguyên tắc: ghi < 3 giây, một chạm** — điều kiện sống còn (lười ghi → không data → AI Bước 1 đói); "ghi trước, làm giàu sau" — mọi hoàn hảo hóa (sửa giờ/tiền/note) đẩy về lúc rảnh.
- ✅ **CHỐT: bấm = GHI NGAY + Hoàn tác** (chủ theo khuyến nghị 2026-07-19), không hộp xác nhận (xác nhận đánh thuế mọi lần ghi đúng để phòng lần nhầm hiếm).
- ✅ **CHỐT-ủy-quyền — chính sách Hoàn tác an toàn-tin cậy** (chủ yêu cầu định nghĩa rõ): **"Hoàn tác" là vĩnh viễn, toast chỉ là lối tắt.** Bấm → entry ghi thật ngay (IndexedDB, cả offline) → toast **10 giây** có nút Hoàn tác; Hoàn tác = **soft-delete** entry đó (D3) → không đường nào mất dữ liệu thật, hoàn tác nhầm khôi phục được (`deleted_at=null`). Hết toast vẫn luôn sửa/xóa được từ danh sách. Offline: chưa sync → gỡ khỏi hàng đợi; đã sync → gửi soft-delete — cùng một nút, nhờ UUIDv7 sinh ở client (B1).
- ✅ **CHỐT (chủ gật 2026-07-19):** màn ghi = **lưới nút** (mỗi tracker một nút, sắp **động** theo tần suất + gần đây — nên tracker KHÔNG cần cột `position`); 3 mức nhập theo `tracker.input_mode`: `event` (1 chạm xong — Hút thuốc) / `money` (1 chạm + 1 ô số, bàn phím số bật sẵn — Bia, Mua game) / `quantity` (dự phòng); **nhấn giữ** = ghi lùi giờ (hôm qua / 2 giờ trước / chọn) — ngoài luồng chính. *(Amendment K4 2026-07-19: giá trị mode `'amount'` đổi tên → `'money'` để khỏi trùng tên cột `amount`.)*

### 8.2 Dashboard — spec mức "câu hỏi phải trả lời" ✅ CHỐT (chủ gật 2026-07-19)
*(chỉ chốt hành vi; layout/chart = phiên frontend)*

**Tracker hành vi (A)** — mọi con số phục vụ triết lý khoảng cách:
| # | Câu hỏi | Trả lời bằng |
|---|---|---|
| A1 | Lần cuối là bao giờ? | **trên chính nút ghi** (`Hút thuốc · 12 ngày trước`) — màn ghi kiêm dashboard chính |
| A2 | Khoảng cách này tốt/xấu so với chính mình? | khoảng cách hiện tại **vs trung bình khoảng cách** ("đang 12 ngày — bình thường 6") |
| A3 | Tuần/tháng/năm bao nhiêu lần? | đếm 3 khung (yêu cầu gốc của chủ ✅) |
| A4 | Đang tăng hay giảm? | tháng này vs trung bình 3 tháng gần nhất |

**Finance (B+C)**:
| # | Câu hỏi | Trả lời bằng |
|---|---|---|
| F1 | Tháng này tiêu bao nhiêu? | tổng `out` month-to-date |
| F2 | Nhiều/ít so với nhịp của mình? | so **CÙNG KỲ** tháng trước (19 ngày vs 19 ngày — so cả tháng là sai lệch kinh điển, luôn ra "đang ít hơn") |
| F3 | Tiêu vào đâu? | theo `tracker_group`, drill xuống tracker |
| F4 | Khoản nào to bất thường? | top 5 entry lớn nhất tháng (một khoản to giải thích spike tốt hơn average) |
| F5 | Thu − chi âm hay dương? | net theo `direction` |
| F6 | Bao nhiêu là CỐ ĐỊNH? | burn/tháng từ subscription entity (chu kỳ quy về tháng) + món sắp gia hạn — tách chi cố định/linh hoạt, entity C trả lãi ngay |

**MUỐN (sau, không phá schema):** streak/kỷ lục khoảng cách, heatmap lịch, run-rate dự báo cuối tháng, tổng tiết kiệm promotion (`list_amount − amount`), so theo năm. **AI Bước 1 (cố ý không làm UI):** "vì sao tháng này cao", pattern giờ/ngày-trong-tuần, tương quan bia↔thuốc.

### 8.3 Việc còn lại của phiên *(cập nhật 2026-07-19 muộn)*
1. ~~Entity subscription~~ → thiết kế xong ở **§11**, chờ gật S1 (ranh giới + cột) + S2 (luồng gia hạn nhắc-rồi-xác-nhận).
2. ~~Q1/Q2~~ → ✅ chốt cả hai (§10).
3. **Đóng phiên** (sau khi S1/S2 được gật): cập nhật ngược `schema-physical-brief.md` (bảng §1: C2/D1 hết DEFER; §5-D2 index mới K7/K16; §7 đóng; ERD thêm `tracker_group`/`subscription`) + note supersede K6 (`tracker.unit`) sang `schema-v1-brief.md` + cập nhật CLAUDE.md/memory.

## 10. RÀ SOÁT chuẩn hóa + toàn vẹn toàn cục (2026-07-19 — lượt kỹ, thay lượt nhanh 7-lỗ-hổng)

**Verdict chuẩn hóa:** các bảng đạt **3NF**; đúng **một denormalization cố ý có ràng buộc bảo vệ** = `tracker.kind` lặp `group.kind` (tránh join đệ quy khi cộng tổng; K1 chặn lệch). Không lưu giá trị dẫn xuất (tiết kiệm = `list_amount − amount` tính lúc đọc); không cột đa trị (C2 đã tách); bảng con phụ thuộc đầy đủ khóa. Subscription sẽ rà lại theo đúng chuẩn này khi thiết kế xong.

**Quản lý danh mục ✅ CHỐT (khung 3 loại):** (1) **enum cứng** (code rẽ nhánh theo giá trị: `kind`/`direction`/`input_mode`/`status`) = TEXT+CHECK, đổi bằng migration; (2) **danh mục người dùng** (`tracker_group`, `tracker`) = CRUD trong app, tạo nhóm inline ngay tại form tạo tracker; (3) **bộ khởi đầu** = seed bằng **Alembic data-migration lúc cutover** (versioned, chạy 1 lần, review được — khớp A2; KHÔNG startup-seed magic). Tiêu chí phân loại: *code có cần hiểu giá trị đó để rẽ nhánh không?*

### ✅ 2 câu PRODUCT — chủ gật khuyến nghị 2026-07-19
- **Q1 — xóa nhóm ✅ CHỐT:** group **không soft-delete, xóa thật + FK `tracker.group_id ON DELETE SET NULL`** (tracker thành "chưa nhóm"; group = cấu trúc rẻ, khác tracker/entry = lịch sử quý).
- **Q2 — seed khởi đầu ✅ CHỐT:** **có**, qua Alembic data-migration lúc cutover; bộ lấy từ đời thật của chủ (nhóm: Thu nhập/Giải trí/Ăn uống/Học tập…; tracker: Hút thuốc/Bia rượu/Bi-a/Mua game/Sub AI/Lương/Chu cấp…).

### ✅ CHỐT-kỹ-thuật (K — executor-level theo mandate rà soát 2026-07-19; chủ veto được từng mục)
| # | Chốt |
|---|---|
| K1 | Khớp kind 2 bảng bằng **composite FK**: `tracker_group UNIQUE(id, kind)`; `tracker FK (group_id, kind)` → DB tự chặn lệch, 0 code; `group_id NULL` → ràng buộc tự miễn (MATCH SIMPLE) |
| K2 | Chống trùng tên: unique index `lower(name)`; tracker dùng **partial** `WHERE deleted_at IS NULL` (tên đã xóa mềm không chặn tạo mới); group unique thường |
| K3 | Enum mới theo C1: `direction` CHECK `('in','out')` NOT NULL DEFAULT `'out'`; `input_mode` CHECK `('event','money','quantity')` NOT NULL DEFAULT `'event'` |
| K4 | Giá trị mode `'amount'` → **`'money'`** (tránh trùng tên cột `amount`) |
| K5 | CHECK số: `amount, list_amount >= 0` (0 hợp lệ — trial); `quantity > 0`; tiền luôn lưu dương |
| K6 | **`tracker.unit` thu hẹp nghĩa** (supersede mô tả schema-v1 "VND/count/minutes" — VND đã thành cột tiền riêng): chỉ là nhãn cho mode `quantity` ("phút", "km"), nullable + CHECK đi cặp mode → cần note có ngày sang `schema-v1-brief.md` lúc đóng phiên |
| K7 | Index theo query thật: `entry(tracker_id, occurred_at DESC)` composite (A1/A2 "lần cuối mỗi tracker") + `entry(occurred_at)` (F1 MTD) — thay cặp index rời D2 cho entry |
| K8 | Validate "entry đúng cột theo `input_mode`" ở **app layer** (PG CHECK không nhìn bảng khác; không dựng trigger — over-eng single-writer) |
| K9 | Double-tap: UUID client chống trùng khi **sync-retry**; 2 tap thật = **debounce UI** (khóa nút khi toast hiện) — không phải việc của DB |
| K10 | Bảng mới ăn luật chung: `tracker_group` + `subscription` có timestamps + trigger (B2); soft-delete có ở `tracker`/`entry`/`subscription`, **không** ở group (Q1); `position`: group **có**, tracker **không** (lưới nút sắp động) |
| K11 | `is_private` (tương lai, phiên auth): đặt ở cấp **cha** (task/note/tracker — entry thừa kế theo tracker), không rải từng entry |
| K12 | Ngoài cụm tracking: bảng cũ khớp luật chung; điểm nhỏ duy nhất `calendar_source.name` nên unique — chốt lúc đúc DDL |
| K13 | **Chuẩn đặt trước cho subscription:** phải mang `tracker_id` (entry gia hạn sinh ra có chỗ rơi vào sổ chi — không entry mồ côi); nối `entry.subscription_id` nullable, cascade bàn ở bước thiết kế subscription |

## 9. Ràng buộc mang sang (không đổi)

- **Xây phần ghi-log TRƯỚC, AI phân tích thói quen/chi tiêu SAU** — đừng để UI tracker nuốt thời gian 2 tính năng AI (`forward-spec.md` §E).
- Privacy bar khi AI đọc health/finance qua LLM bên thứ ba — bookmark Bước 1 (giờ nối vào phiên encryption-review §6).
- Nhắc uống thuốc (note #5, MUST-HAVE) đã có cơ chế cron → web-push (`architecture-brief.md`); **"nhắc sub sắp hết hạn" tái dùng cùng đường ống** — 📌 note cho phiên frontend/jobs.

## 11. Entity `subscription` (thiết kế 2026-07-19)

### Ranh giới ✅ CHỐT (S1 — chủ gật 2026-07-19)
Tiêu chí duy nhất: **có ngày-hết-hạn hay không.** Có thời hạn/chu kỳ → `subscription`, kể cả game pass / gói trả-trước-một-cục (= `auto_renew=false`); **mua đứt vĩnh viễn → `entry` thường** (không gì ở tương lai để theo dõi). → Giải luôn câu hỏi mở ở §8.3.

### Cột ✅ CHỐT (S1 — chủ gật 2026-07-19, kèm 1 amendment)
| Cột | Kiểu | Nghĩa |
|---|---|---|
| `id` | UUIDv7 PK | B1 |
| `name` | TEXT NOT NULL, unique `lower(name)` WHERE `deleted_at IS NULL` | K2 pattern |
| `tracker_id` | FK → `tracker` NOT NULL, `ON DELETE RESTRICT` | K13 — entry gia hạn có chỗ rơi |
| `amount` | NUMERIC(14,0) NOT NULL, CHECK ≥0 | giá **dự kiến mỗi kỳ**, VND thực trả |
| `list_amount` | NUMERIC(14,0) NULL, CHECK ≥0 | giá niêm yết VND; *lịch sử giá thật = các entry* → không cần bảng price-history |
| `period_count` / `period_unit` | INT NOT NULL CHECK >0 DEFAULT 1 / TEXT CHECK (`day/week/month/year`) DEFAULT `month` | chu kỳ 1-tháng, 3-tháng, 1-năm… |
| `started_on` / `expires_on` | **DATE** NOT NULL, CHECK `expires_on >= started_on` | `expires_on` = "sắp hết hạn?"; auto-renew → nghĩa là ngày trừ tiền kế |
| `auto_renew` | BOOL NOT NULL **DEFAULT `false`** *(amendment chủ 2026-07-19: "app là ghi lại thôi, quyết định thực tế ở ngoài" — chỉ bật khi chủ động chọn)* | "sắp mất tiền" vs "sắp mất access"; F6 chỉ đếm auto-renew vào burn cố định |
| `canceled_at` | timestamptz NULL | sự kiện hủy → trạng thái "đã hủy còn hạn" |
| `note_md` | TEXT NULL | markdown theo nguyên tắc chung |
| `created_at`/`updated_at`/`deleted_at` | timestamptz | B2 + soft-delete (K10) |

**Không cột `status`** — suy ra từ (`expires_on`, `canceled_at`): `active` / `đã hủy còn hạn` / `hết hạn`. Lưu riêng = update-anomaly (khớp verdict 3NF §10).

### Luồng gia hạn ✅ CHỐT (S2 — chủ SỬA đề xuất, 2026-07-19)
*(Đề xuất gốc có nút "Đã gia hạn" 1-chạm ngay từ noti — chủ rút gọn đúng hướng tối giản: "không cần tiện đến mức bấm phát tự động; cần xem xét + đánh giá + trả tiền rồi mới được coi là gia hạn".)*
- **Noti chỉ để BÁO:** cron quét `expires_on` sắp tới (mặc định trước **3 ngày** — hằng số `app_setting`, chưa cần per-sub) → web-push → chủ **xem xét + quyết định + trả tiền Ở NGOÀI** → rồi mới vào app ghi gia hạn: form với default sẵn từ sub (tạo `entry` gắn `subscription_id`, `amount` sửa được nếu giá đổi) + đẩy `expires_on` thêm 1 chu kỳ.
- **KHÔNG nút tự động từ noti** — "gia hạn" trong app chỉ ghi nhận việc thật đã xảy ra. Auto-write không confirm để dành AI Bước 2 (có confirm+audit). Lần mua đầu = cùng flow tạo sub.

### Kỹ thuật đi kèm ✅ CHỐT-kỹ-thuật (K14–K16, cùng mandate §10)
| # | Chốt |
|---|---|
| K14 | **DATE cho `started_on`/`expires_on`** — ngoại lệ có chủ đích với B2: B2 diệt bug naive-time của *thời điểm sự kiện*; ngày-thanh-toán là *ngày lịch* không giờ — ép timestamptz mới tạo bug lệch-một-ngày quanh múi giờ. `canceled_at`/timestamps vẫn timestamptz đúng B2 |
| K15 | `entry.subscription_id` UUID NULL, FK `ON DELETE SET NULL` — entry sống tiếp như khoản chi thường nếu sub bị xóa cứng |
| K16 | Index: FK (`tracker_id`; `entry.subscription_id`) + `subscription(expires_on)` (đúng luật D2 "cột thời gian") |

## 12. Nhắc thuốc (note gốc #5 — MUST-HAVE) — thiết kế ✅ CHỐT (2026-07-19, chủ bổ sung lúc đóng phiên)

Chủ: tính năng **quan trọng nhất app** (sức khỏe trực tiếp) nhưng phải **tối giản** — mỗi ngày ~20–21h được hỏi "đã uống thuốc chưa", miễn đừng quên; streak "có cũng được, không có lại tối giản → khá tốt" ⇒ **không làm streak** (A1/A3 dashboard đã đủ: "lần cuối" + đếm).

- **Mô hình: KHÔNG entity mới** — là một tracker thường (`Uống thuốc`, kind=health, input_mode=event) + 2 cột nullable trên `tracker`: **`reminder_time TIME`** (có giờ = bật nhắc) + **`reminder_text TEXT`** (fallback = name).
- **Nguyên tắc KÍN ĐÁO trên noti ✅ (lời chủ):** text notification là **bề mặt công khai** (đọc được từ lock-screen) → chủ tự đặt mức kín đáo qua `reminder_text` — vd `"taken micardis?"` thay vì tên thuốc/bệnh tiếng Việt tường minh. Cùng họ tư duy với private mode §5: kiểm soát *bề mặt hiển thị*, và đây là lớp không cần tới auth.
- **Luồng:** cron (GitHub Actions — architecture đã chốt) → app → web-push đúng `reminder_time` → **bấm ✓ ngay trên noti = ghi entry 1 chạm**. Pattern *nhắc-rồi-xác-nhận* lần 2 — nhưng khác S2 đúng chỗ cần khác: thuốc không có gì phải "xem xét/trả tiền ngoài" nên ✓-1-chạm là đúng; sub thì không.
- **K17 (kỹ thuật, cùng mandate §10):** `TIME` = wall-clock lặp-hằng-ngày, cùng họ ngoại lệ K14 (không phải *thời điểm sự kiện*; app quy sang UTC khi đặt lịch cron — single-user VN). Cơ chế generic cho **mọi** tracker, không riêng thuốc; cadence v1 = daily-only, mở rộng (theo thứ trong tuần…) = DEFER.

## 13. ✅ ĐÓNG PHIÊN 2026-07-19

Mọi mục của phiên đã về trạng thái cuối — **0 mục ⚠️ còn treo**. Schema toàn dự án **khép tại đây**: C2/D1 hết DEFER; +`tracker_group`, +`subscription`; cột mới trên `tracker` (`direction`, `input_mode`, `group_id`, `reminder_time`, `reminder_text`, `unit` thu hẹp) và `entry` (`quantity`, `amount`, `list_amount`, `subscription_id`).
Cập nhật ngược cùng ngày: `schema-physical-brief.md` (§1 + §7), `schema-v1-brief.md` (delta khái niệm), `forward-spec.md` (§A nhắc thuốc + §E), `CLAUDE.md`, memory (kèm **checklist đóng-phiên** mới).
**Phiên kế tiếp (chủ chọn):** frontend UI stack · auth (kèm private-mode unlock §5) · encryption-review (scope §6) · AI Bước 1.

---
*Cập nhật khi: phiên auth / encryption-review / frontend chốt các phần DEFER của file này. Thêm note có ngày — không xóa kết luận cũ.*
