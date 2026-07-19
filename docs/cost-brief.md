# Cost brief — chi phí vận hành microSched

> Decision record **tự-chứa**. **Mốc thời gian: giá & chính sách tra ngày 2026-07-19.**
> ⚠️ Hạ tầng + dịch vụ AI đổi nhanh (Fly bỏ free tier 2024; Oracle giảm nửa ARM Always-Free 6/2026; giá LLM/Neon đổi liên tục) → **soi lại mỗi ~3 tháng và bắt buộc trước khi cutover.** Con số dưới là *ước tính theo kế hoạch tham chiếu*, không phải hoá đơn.

---

## TL;DR

**~$3.3–4/tháng (~$40–48/năm)** cho phương án khuyến nghị. Mọi thứ khác **$0** trong giai đoạn học nhờ free tier + credit sẵn có.

- Toàn bộ chi phí "cứng" hiện tại = **1 dòng duy nhất: hosting Fly.io**. Neon, backup, auth, CI/cron đều $0.
- Có **đường $0 tuyệt đối** (Oracle Always-Free / Render-free) nhưng đánh đổi reliability / cold-start — xem §3.
- Hai biến số cần canh: **LLM usage** (giờ ≈ $0 nhờ credit) và **domain** (tuỳ chọn, ~$12/năm).

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

---
*Cập nhật khi: đổi host/DB/LLM provider, hết credit, hoặc tới mốc soi-lại 3 tháng. Thêm ghi chú có ngày — không xoá trắng con số cũ.*
