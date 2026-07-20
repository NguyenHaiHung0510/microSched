# Cost brief — chi phí vận hành microSched

> Decision record **tự-chứa**. **Mốc thời gian: giá & chính sách tra ngày 2026-07-19.**
> ⚠️ Hạ tầng + dịch vụ AI đổi nhanh (Fly bỏ free tier 2024; Oracle giảm nửa ARM Always-Free 6/2026; giá LLM/Neon đổi liên tục) → **soi lại mỗi ~3 tháng và bắt buộc trước khi cutover.** Con số dưới là *ước tính theo kế hoạch tham chiếu*, không phải hoá đơn.

---

## TL;DR

**~$3.3–4/tháng (~$40–48/năm)** cho phương án khuyến nghị. Mọi thứ khác **$0** trong giai đoạn học nhờ free tier + credit sẵn có.

- Toàn bộ chi phí "cứng" hiện tại = **1 dòng duy nhất: hosting Fly.io**. Neon, backup, auth, CI/cron đều $0.
- Có **đường $0 tuyệt đối** (Oracle Always-Free / Render-free) nhưng đánh đổi reliability / cold-start — xem §3.
- Hai biến số cần canh: **LLM usage** (giờ ≈ $0 nhờ credit) và **domain** (tuỳ chọn, ~$12/năm).
- **2026-07-20:** thêm **§6 — stack công cụ AI cá nhân (~$80/mo)**, hạch toán RIÊNG — đó là chi phí *học/xây*, không phải chi phí *vận hành app*.

| Hạng mục | Dịch vụ (đã chọn) | Chi phí | Trạng thái |
|---|---|---|---|
| **Hosting** | Fly.io — 1× shared-cpu-1x always-on, region `sin`; **khởi đầu 256MB (~$2), lên 512MB (~$3.3) nếu OOM** | **~$2–3.3/mo** | ✅ đã chọn |
| Database | Neon Postgres + pgvector, free tier (dev/prod branching) | $0 | ✅ chốt |
| Auth | Google OAuth + allowlist cứng | $0 | ⚠️ leaning (xem architecture) |
| LLM | OpenRouter / API (credit sẵn: Google AI Studio, OpenAI, OpenRouter free) | ~$0 giờ → usage | ⚠️ biến số |
| Backup | Google Drive (sync) + dump laptop | $0 | ✅ chốt |
| CI / Cron | GitHub Actions free tier (deploy + backup/verify) | $0 | ⚠️ leaning |
| Domain | `*.fly.dev` (mặc định) · hoặc custom ~$12/năm | $0 / ~$12/năm | ⚠️ OPEN, tuỳ chọn |
| CDN / Access | Cloudflare free (nếu dùng) | $0 | DEFER, tuỳ chọn |
| **TỔNG** | | **~$40–48/năm** | |

---

## 1. Truy cập & tên miền

- Fly cấp **`tên-app.fly.dev` + HTTPS tự động** miễn phí → truy cập ngay, **không mua gì**, không đụng IP thô (IPv4 shared, free, nằm sau hostname).
- **Domain riêng = tuỳ chọn.** Lý do kỹ thuật để mua *sớm*: PWA-install + đăng ký web-push gắn với **origin**; đổi host mà không có domain riêng → phải cài lại PWA + đăng ký lại push. Domain riêng tách danh tính app khỏi host.
- Mua ở **Cloudflare Registrar** (giá gốc, không markup, không bẫy "năm đầu rẻ – gia hạn đắt"). `.com` ~$10–12, `.dev`/`.app` ~$12–15. Tránh `.vn` (đắt + giấy tờ).

## 2. Chi tiết dòng hosting (Fly.io)

- **1 máy always-on:** 256MB = $2.02, 512MB = $3.32 (baseline Amsterdam; `sin` nhỉnh hơn chút). **Khởi đầu 256MB đúng ngân sách gốc $2, theo dõi memory, `fly scale memory 512` chỉ khi OOM** — không cam kết $4 trước. (Fly resize tức thì → không rủi ro.)
- **Bẫy chi phí #1:** `fly launch` mặc định tạo **2 máy** (HA) → gấp đôi tiền. `fly scale count 1` → còn 1 máy.
- **Không tốn thêm:** shared IPv4 = free (không cần dedicated $2); TLS cert = free (Let's Encrypt qua `fly certs`); **không volume** (data ở Neon → $0 lưu trữ; và volume snapshot tính phí từ 1/2026); bandwidth single-user ≈ $0 ($0.02/GB).
- **Bắt buộc:** đặt **spending limit / budget alert** (Cost Management) — Fly pay-as-you-go, tính theo giây, **không có free allowance** → chặn hoá đơn bất ngờ.

## 3. Các đường thay thế (đánh đổi — không chọn nhưng ghi lại)

| Phương án | Chi phí | Đổi lại | Vị trí |
|---|---|---|---|
| **Render Starter** | $7/mo | 0-ops (git push), ổn định hơn, đắt hơn | nếu chịu $7 để khỏi đụng Docker/OS |
| **Cloud VPS VN** (BKNS/AZDIGI/Vietnix — *dòng VPS*, KHÔNG shared) | ~$3–6/mo, **soi giá gia hạn** | latency nội địa, nhưng tự quản OS toàn bộ | khi cần latency VN tối đa |
| **Oracle Always-Free** ARM | **$0** | 🔴 rủi ro ban/reclaim, no SLA, tự quản VM | chỉ làm **box thí nghiệm** (nghịch model local), KHÔNG host chính |
| ~~Render free / Hetzner~~ | $0 / €5.5 | cold-start 30–60s (loại) / EU-region ~250ms (loại) | — |

**Lưu ý category (bài học đã rút):** shared/web-hosting VN ("Hosting 0đ", `hosting-gia-re`, `web-hosting`) **KHÔNG chạy được** FastAPI persistent (không SSH/root/Docker/long-running) → không phải ứng viên dù rẻ/free. Chỉ xét dòng **VPS/Cloud-Server**.

## 4. Biến số & bẫy cần canh

- **LLM:** giờ ≈ $0 nhờ credit + free models. Khi tiêu thật → usage-based; đặt **cap chi tiêu** ở OpenRouter. Cascade (model rẻ trước, escalate) giữ chi phí thấp. Bật *no-train providers* + `zdr` cho query nhạy cảm (privacy = cấu hình, không tốn tiền).
- **Embeddings (Bước 1):** rẻ qua API (vd text-embedding nhỏ) hoặc credit; chưa cần model local.
- **Neon:** free tier (**0.5 GB/project**, 100 CU-h/mo) dư rất lâu cho single-user → thực tế $0 nhiều tháng/năm. **Đo thật 2026-07-19:** DB `microschedule_v2` ~1 năm dùng = **10 MB / ~887 dòng** → dư ~50×. Biến số duy nhất đụng trần = **log AI verbose** → chiến lược log 3 tầng đẩy blob nặng off-DB (`schema-physical-brief.md` §6). Trần free = **cứng (chặn ghi), không phải hoá đơn bất ngờ**; vượt = chủ động nâng Launch (~$5).
- **Promo/renewal trap:** với bất kỳ dịch vụ nào (host, domain, VPS VN) → **đọc giá gia hạn, không phải giá "năm đầu".**

## 5. Chưa tính (sẽ phát sinh nếu chọn)

- Domain custom (~$12/năm) — nếu muốn danh tính bền.
- LLM khi hết credit — usage thật, phụ thuộc tần suất + model.
- Model local sau này (Bước 3) — nếu chạy trên box riêng (vd Oracle) hoặc laptop → $0 tiền mặt, tốn công vận hành.

## 6. 🆕 2026-07-20 — Stack công cụ AI cá nhân (dev-tooling, hạch toán riêng khỏi chi phí app)

> Tra live 2026-07-20, phiên harness (phân vai + lý do chọn/loại: `devops-brief.md` §7). **Soi lại ~10/2026** — thị trường coding-plan đổi giá theo quý (GLM promo $3 thời 2025 chết trong <6 tháng, giá chuẩn ×3–6; Qwen đóng free tier 04/2026; MiniMax entry ×2).

| Tầng | Dịch vụ | Chi phí | Ghi chú |
|---|---|---|---|
| T1 óc | Claude Pro | $20/mo | có từ 02/07; **hết Fable trên Pro sau 20/07** → Opus 4.8 (chat) + Sonnet 5 (Claude Code) |
| T2 tay | ChatGPT Plus (Codex, GPT-5.6) | $20/mo | mua mới 07/2026; 07/2026 bỏ cap 5h → chỉ cap tuần |
| T3 chạy test | 2× Google AI Pro | ~$40/mo (nếu giá chuẩn $19.99×2) | sẵn có; **re-check 10/2026: còn cần cả 2 account không?** |
| (option, chưa mua) | DeepSeek V4 API | $0 → ~$1–3 khi dùng | van xả pay-per-token cho bulk ($0.14–0.435/M input) |
| **TỔNG dev-stack** | | **~$80/mo** | ≈ **40×** hosting app (~$2/mo) — tỉ trọng thật của khoản "học AI-eng" |

**Giá đối chiếu đã tra cùng ngày** (để lần re-check sau đo drift): GLM Coding Lite $12.6 (promo 30%) / $18 chuẩn — kèm quota multiplier 3× giờ cao điểm trùng giờ VN; MiniMax Plus $20; Kimi Code ~$7/tuần (~$28/mo); Qwen $50; Cursor Pro $20; Copilot Pro $10 (chỉ ~$15 credits/mo).

**Lane PAYG "tháng nhẹ" (bổ sung cùng ngày — chi tiết `devops-brief.md` §7):** tháng thuần-học có thể skip sub Codex → OpenRouter (ví duy nhất; **nạp $10 một lần, không hết hạn → 1.000 req/ngày free-models vĩnh viễn**; phí topup 5.5%, nạp cục đừng nạp lắt nhắt) + model rẻ (DeepSeek V4) qua OpenCode hoặc Claude Code endpoint-compatible ≈ **$2–5/tháng**. **Credit đang om (kiểm expiry NGAY):** OpenAI $5 + daily-free data-sharing (~1M/ngày model lớn, 2.5M/ngày mini — reset hằng ngày, om là phí; chỉ việc public-context) · 2× Gemini free tier (Flash ~1.500 req/ngày/project; ⚠️ bật billing = mất free tier project đó → acc có 300K VND credit tách project riêng) · 300K VND Google credit. Earmark toàn bộ cho Bước-1 (eval, embedding, cascade-dev).

---
*Cập nhật khi: đổi host/DB/LLM provider, hết credit, đổi công cụ dev-stack (§6), hoặc tới mốc soi-lại 3 tháng (~10/2026). Thêm ghi chú có ngày — không xoá trắng con số cũ.*
