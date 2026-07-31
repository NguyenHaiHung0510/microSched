# Cost brief — chi phí vận hành microSched

> Decision record **tự-chứa**. **Mốc thời gian: giá & chính sách tra ngày 2026-07-19.**
> ⚠️ Hạ tầng + dịch vụ AI đổi nhanh (Fly bỏ free tier 2024; Oracle giảm nửa ARM Always-Free 6/2026; giá LLM/Neon đổi liên tục) → **soi lại mỗi ~3 tháng và bắt buộc trước khi cutover.** Con số dưới là *ước tính theo kế hoạch tham chiếu*, không phải hoá đơn.

---

## TL;DR

**~\$3.3–4/tháng (~\$40–48/năm)** cho phương án khuyến nghị. Mọi thứ khác **\$0** trong giai đoạn học nhờ free tier + credit sẵn có.

- Toàn bộ chi phí "cứng" hiện tại = **1 dòng duy nhất: hosting Fly.io**. Neon, backup, auth, CI/cron đều \$0.
- Có **đường \$0 tuyệt đối** (Oracle Always-Free / Render-free) nhưng đánh đổi reliability / cold-start — xem §3.
- Hai biến số cần canh: **LLM usage** (giờ ≈ \$0 nhờ credit) và **domain** (tuỳ chọn, ~\$12/năm).
- **2026-07-20:** thêm **§6 — stack công cụ AI cá nhân (~\$80/mo)**, hạch toán RIÊNG — đó là chi phí *học/xây*, không phải chi phí *vận hành app*.

| Hạng mục | Dịch vụ (đã chọn) | Chi phí | Trạng thái |
|---|---|---|---|
| **Hosting** | Fly.io — 1× shared-cpu-1x always-on, region `sin`; **khởi đầu 256MB (~\$2), lên 512MB (~\$3.3) nếu OOM** | **~\$2–3.3/mo** | ✅ đã chọn |
| Database | Neon Postgres + pgvector, free tier (dev/prod branching) | \$0 | ✅ chốt |
| Auth | Google OAuth + allowlist cứng | \$0 | ⚠️ leaning (xem architecture) |
| LLM | OpenRouter / API (credit sẵn: Google AI Studio, OpenAI, OpenRouter free) | ~\$0 giờ → usage | ⚠️ biến số |
| Backup | Google Drive (sync) + dump laptop | \$0 | ✅ chốt |
| CI / Cron | GitHub Actions free tier (deploy + backup/verify) | \$0 | ⚠️ leaning |
| Domain | `*.fly.dev` (mặc định) · hoặc custom ~\$12/năm | \$0 / ~\$12/năm | ⚠️ OPEN, tuỳ chọn |
| CDN / Access | Cloudflare free (nếu dùng) | \$0 | DEFER, tuỳ chọn |
| **TỔNG** | | **~\$40–48/năm** | |

---

## 1. Truy cập & tên miền

- Fly cấp **`tên-app.fly.dev` + HTTPS tự động** miễn phí → truy cập ngay, **không mua gì**, không đụng IP thô (IPv4 shared, free, nằm sau hostname).
- **Domain riêng = tuỳ chọn.** Lý do kỹ thuật để mua *sớm*: PWA-install + đăng ký web-push gắn với **origin**; đổi host mà không có domain riêng → phải cài lại PWA + đăng ký lại push. Domain riêng tách danh tính app khỏi host.
- Mua ở **Cloudflare Registrar** (giá gốc, không markup, không bẫy "năm đầu rẻ – gia hạn đắt"). `.com` ~\$10–12, `.dev`/`.app` ~\$12–15. Tránh `.vn` (đắt + giấy tờ).

## 2. Chi tiết dòng hosting (Fly.io)

- **1 máy always-on:** 256MB = \$2.02, 512MB = \$3.32 (baseline Amsterdam; `sin` nhỉnh hơn chút). **Khởi đầu 256MB đúng ngân sách gốc \$2, theo dõi memory, `fly scale memory 512` chỉ khi OOM** — không cam kết \$4 trước. (Fly resize tức thì → không rủi ro.)
- **Bẫy chi phí #1:** `fly launch` mặc định tạo **2 máy** (HA) → gấp đôi tiền. `fly scale count 1` → còn 1 máy.
- **Không tốn thêm:** shared IPv4 = free (không cần dedicated \$2); TLS cert = free (Let's Encrypt qua `fly certs`); **không volume** (data ở Neon → \$0 lưu trữ; và volume snapshot tính phí từ 1/2026); bandwidth single-user ≈ \$0 (\$0.02/GB).
- **Bắt buộc:** đặt **spending limit / budget alert** (Cost Management) — Fly pay-as-you-go, tính theo giây, **không có free allowance** → chặn hoá đơn bất ngờ.

## 3. Các đường thay thế (đánh đổi — không chọn nhưng ghi lại)

| Phương án | Chi phí | Đổi lại | Vị trí |
|---|---|---|---|
| **Render Starter** | \$7/mo | 0-ops (git push), ổn định hơn, đắt hơn | nếu chịu \$7 để khỏi đụng Docker/OS |
| **Cloud VPS VN** (BKNS/AZDIGI/Vietnix — *dòng VPS*, KHÔNG shared) | ~\$3–6/mo, **soi giá gia hạn** | latency nội địa, nhưng tự quản OS toàn bộ | khi cần latency VN tối đa |
| **Oracle Always-Free** ARM | **\$0** | 🔴 rủi ro ban/reclaim, no SLA, tự quản VM | chỉ làm **box thí nghiệm** (nghịch model local), KHÔNG host chính |
| ~~Render free / Hetzner~~ | \$0 / €5.5 | cold-start 30–60s (loại) / EU-region ~250ms (loại) | — |

📝 **2026-07-23 — dòng cuối bảng này từng kéo theo một quyết định sai.** "cold-start 30–60s" là số **của Render**, nhưng `architecture-brief.md` §64 gộp Fly-autostop vào cùng câu loại trừ với Render free ⇒ Fly-autostop bị loại bằng **số của một dịch vụ khác, chưa ai đo**. Đo thật 23/07: Fly autostart **~8s kể cả sau 10h38 ngủ**. ⇒ đã đảo sang scale-to-zero, tiết kiệm ~50k VNĐ/tháng (**\~\$2,50 → \~\$0,30**). **Bài học cho chính bảng này: một ô "đổi lại" gộp nhiều phương án thì con số của phương án tệ nhất sẽ lây sang cả rổ.**

**Lưu ý category (bài học đã rút):** shared/web-hosting VN ("Hosting 0đ", `hosting-gia-re`, `web-hosting`) **KHÔNG chạy được** FastAPI persistent (không SSH/root/Docker/long-running) → không phải ứng viên dù rẻ/free. Chỉ xét dòng **VPS/Cloud-Server**.

## 4. Biến số & bẫy cần canh

- **LLM:** giờ ≈ \$0 nhờ credit + free models. Khi tiêu thật → usage-based; đặt **cap chi tiêu** ở OpenRouter. Cascade (model rẻ trước, escalate) giữ chi phí thấp. Bật *no-train providers* + `zdr` cho query nhạy cảm (privacy = cấu hình, không tốn tiền).
- **Embeddings (Bước 1):** rẻ qua API (vd text-embedding nhỏ) hoặc credit; chưa cần model local.
- **Neon:** free tier (**0.5 GB/project**, 100 CU-h/mo) dư rất lâu cho single-user → thực tế \$0 nhiều tháng/năm. **Đo thật 2026-07-19:** DB `microschedule_v2` ~1 năm dùng = **10 MB / ~887 dòng** → dư ~50×. Biến số duy nhất đụng trần = **log AI verbose** → chiến lược log 3 tầng đẩy blob nặng off-DB (`schema-physical-brief.md` §6). Trần free = **cứng (chặn ghi), không phải hoá đơn bất ngờ**; vượt = chủ động nâng Launch (~\$5).
- **Promo/renewal trap:** với bất kỳ dịch vụ nào (host, domain, VPS VN) → **đọc giá gia hạn, không phải giá "năm đầu".**

## 5. Chưa tính (sẽ phát sinh nếu chọn)

- Domain custom (~\$12/năm) — nếu muốn danh tính bền.
- LLM khi hết credit — usage thật, phụ thuộc tần suất + model.
- Model local sau này (Bước 3) — nếu chạy trên box riêng (vd Oracle) hoặc laptop → \$0 tiền mặt, tốn công vận hành.

## 6. 🆕 2026-07-20 — Stack công cụ AI cá nhân (dev-tooling, hạch toán riêng khỏi chi phí app)

> Tra live 2026-07-20, phiên harness (phân vai + lý do chọn/loại: `devops-brief.md` §7). **Soi lại ~10/2026** — thị trường coding-plan đổi giá theo quý (GLM promo \$3 thời 2025 chết trong <6 tháng, giá chuẩn ×3–6; Qwen đóng free tier 04/2026; MiniMax entry ×2).

| Tầng | Dịch vụ | Chi phí | Ghi chú |
|---|---|---|---|
| T1 óc | Claude Pro | \$20/mo | có từ 02/07; **hết Fable trên Pro sau 20/07** → Opus 4.8 (chat) + Sonnet 5 (Claude Code) |
| T2 tay | ChatGPT Plus (Codex, GPT-5.6) | \$20/mo | mua mới 07/2026; 07/2026 bỏ cap 5h → chỉ cap tuần |
| T3 chạy test | 2× Google AI Pro | ~\$40/mo (nếu giá chuẩn \$19.99×2) | sẵn có; **re-check 10/2026: còn cần cả 2 account không?** |
| (option, chưa mua) | DeepSeek V4 API | \$0 → ~\$1–3 khi dùng | van xả pay-per-token cho bulk (\$0.14–0.435/M input) |
| **TỔNG dev-stack** | | **~\$80/mo** | ≈ **40×** hosting app (~\$2/mo) — tỉ trọng thật của khoản "học AI-eng" |

**Giá đối chiếu đã tra cùng ngày** (để lần re-check sau đo drift): GLM Coding Lite \$12.6 (promo 30%) / \$18 chuẩn — kèm quota multiplier 3× giờ cao điểm trùng giờ VN; MiniMax Plus \$20; Kimi Code ~\$7/tuần (~\$28/mo); Qwen \$50; Cursor Pro \$20; Copilot Pro \$10 (chỉ ~\$15 credits/mo).

**Lane PAYG "tháng nhẹ" (bổ sung cùng ngày — chi tiết `devops-brief.md` §7):** tháng thuần-học có thể skip sub Codex → OpenRouter (ví duy nhất; **nạp \$10 một lần, không hết hạn → 1.000 req/ngày free-models vĩnh viễn**; phí topup 5.5%, nạp cục đừng nạp lắt nhắt) + model rẻ (DeepSeek V4) qua OpenCode hoặc Claude Code endpoint-compatible ≈ **\$2–5/tháng**. **Credit đang om (kiểm expiry NGAY):** OpenAI \$5 + daily-free data-sharing (~1M/ngày model lớn, 2.5M/ngày mini — reset hằng ngày, om là phí; chỉ việc public-context) · 2× Gemini free tier (Flash ~1.500 req/ngày/project) · 300K VND Google credit (**còn ~295K** tính 23/07). Earmark toàn bộ cho Bước-1 (eval, embedding, cascade-dev).

## 7. 🆕 MỞ 2026-07-22 — Mảng theo dõi hoá đơn thật (khác với ước lượng ở §TL;DR)

App đã deploy và **tiền đã bắt đầu chạy**. Chính chủ mở mảng mới: soi hoá đơn thật theo nhịp **3–7 ngày** (và khi thấy bất thường), tách khỏi việc soi giá 3 tháng/lần.

**Vì sao tách hai mảng — sự cố Neon 22/07 tự chứng minh:** §TL;DR ước \$0 cho Neon và **giá đó không sai**. Cái hỏng là **một config ở file khác phá giả định của ước lượng**. Soi giá lại 3 tháng nữa cũng không bao giờ tìm ra nó. Hai mảng đo hai thứ khác nhau:

| | `cost-brief` §1–§6 | Mảng mới §7 |
|---|---|---|
| Đo | **giá & lựa chọn** | **hoá đơn & hành vi** |
| Nhịp | ~3 tháng | 3–7 ngày |
| Câu hỏi | "còn đáng chọn không?" | "vì sao số này ra thế?" |

### 7.1 Số nền — đo thật 2026-07-22 (thay cho ước lượng)

**Fly — đơn vị hoá đơn: 1 unit = 1 giây máy chạy.** Suy ra và kiểm chứng: machine sinh `2026-07-20T14:00:19Z` ⇒ ngày 20 (UTC) còn lại 35.981 giây, hoá đơn ghi **36.007 units**. Khớp trong 26 giây.

| Ngày | Units | Đọc ra |
|---|---|---|
| 07-20 | 36.007 | 10,0h — ngày cụt, máy vừa sinh lúc 21:00 giờ VN |
| 07-21 | 82.103 | 22,8h — ngày đầy, hụt ~72 phút |

- **"Xu hướng tăng" của Fly là ảo giác của ngày đầu cụt**, không phải xu hướng. Trạng thái ổn định = 86.400 × \$0,00000095 = **\$0,082/ngày → ~\$2,50/tháng**.
- **Lệch so với ước lượng:** §2 ghi \$2,02 (baseline Amsterdam) kèm chú "`sin` nhỉnh hơn chút". Thực tế `sin` = **\$2,50, +24%**. Vẫn trong ngân sách; giờ là số thật.
- ~72 phút hụt của ngày 21 *(suy luận)*: các lần deploy restart + **crash-loop `httpx`** (lỗi B1 của 007) — Fly tính theo giây nên máy chết không tính tiền. Hoá đơn có dấu vết của bug.

**Neon — sự cố thật, đã vá** (PR [#11](https://github.com/NguyenHaiHung0510/microSched/pull/11)):

`fly.toml` gọi `/api/healthz` mỗi **30 giây**; endpoint đó chạy `SELECT 1`. Cửa sổ autosuspend của Neon là **5 phút**. 30 giây ≪ 5 phút ⇒ **DB không bao giờ được rảnh đủ lâu để ngủ**. Sàn 0,25 CU × 24h = **6 CU-hrs/ngày** trên hạn mức free **100 CU-hrs/tháng** ⇒ cạn trong **~17 ngày**, sau đó Neon **treo compute tới kỳ sau** — **mất DB giữa tháng, không phải mất tiền**. Số đo khớp: 4,54 CU-hrs sau ~20h chạy liên tục ≈ 0,227 CU ≈ đúng sàn.

**Bài học vượt ra ngoài chuyện tiền:** `schema-physical-brief.md` §185 đã cảnh báo đúng điều này từ 19/07 (*"cron đừng ping DB quá dày"*), rồi 005 vẫn đi thẳng vào. Không test nào đỏ, không log nào báo, security-review không thấy (không phải lỗ bảo mật). **Đây là lỗ hổng giữa hai quyết định đều đúng, nằm ở hai file không tham chiếu nhau** — cùng họ với B1/B2 của 007: thứ chỉ lộ ra khi **nhìn hệ thống đang chạy**, không phải khi đọc code. Đó chính là lý do mảng §7 phải tồn tại.

### 7.2 Ngưỡng báo động — soi số phải có nghĩa, không chỉ "nhìn cho biết"

| Trục | Kỳ vọng | Báo động ⇒ đi tìm cái gì |
|---|---|---|
| Fly units/ngày | ~86.400 | **>90.000 ⇒ đang chạy >1 máy** (bẫy `fly launch` tạo 2 máy, §2) |
| Fly bandwidth | ~\$0 | >0 đáng kể ⇒ có thứ gì đang gọi từ ngoài |
| Neon CU-hrs/ngày | **<1** (sau khi vá) | >2 ⇒ **có thứ đang giữ DB thức** |
| Neon storage | 0,03 GB | >0,25 GB ⇒ nửa quota free — **hạn mức liên tục, KHÔNG reset hàng tháng** |
| Neon dự phóng tới **20/08** | <60 CU-hrs | >80 |

**Hai loại ngưỡng, đừng gộp:** CU-hours và network transfer **reset ngày 20 hàng tháng** ⇒ soi theo *tốc độ tiêu* và *dự phóng tới ngày 20*. Storage/branches là **hạn mức liên tục** ⇒ soi theo *mức tuyệt đối*, và nó chỉ có một chiều: tăng. Nhầm hai loại này sẽ yên tâm sai về storage sau cutover 012.

**Dòng nguy nhất KHÔNG nằm trong bảng trên — và đó là chủ ý phải ghi rõ:** Fly bị chặn cứng bởi 1 máy cố định (trần ~\$2,50), Neon bị chặn bởi free tier (hết thì treo, không âm thầm tính tiền). **Cả hai tự có trần.** Dòng duy nhất **không có trần** là **LLM API ở Bước 1** — usage-based, và một vòng lặp agent lỗi đốt hết trong một đêm. Dòng đó **không canh bằng dashboard mà chặn bằng hard spending limit ở phía nhà cung cấp** (đây là lý do "nạp OpenRouter \$10 một lần" ở §6 là thiết kế tốt: **ví có đáy**). Nguyên tắc: **dòng có trần thì quan sát, dòng không trần thì chặn.**

**GitHub Actions = \$0** — public repo dùng standard runner miễn phí không giới hạn, nên CD ở 008b **không thêm dòng chi phí nào**. Ghi lại vì đây là **cổ tức không tính trước của quyết định public repo** (`devops-brief.md` §1, vốn quyết theo threat model): nếu lần re-check nào có ai cân nhắc chuyển private thì đây là một phần cái giá.

### 7.3 ⚠️ ĐANG THEO DÕI — Neon, 3 ngày, mỗi ngày một lần

**Chốt 2026-07-22:** sau khi PR #11 deploy, soi Neon **mỗi ngày một lần trong 3 ngày** (23/07, 24/07, 25/07).

Nghiệm thu **không nằm ở app mà ở biểu đồ Neon**: để yên >10 phút không đụng vào, biểu đồ Monitoring phải chuyển sang **ENDPOINT INACTIVE**. Còn chạy liên tục ⇒ **còn thứ khác đang ping DB mà ta chưa tìm ra** — và đó mới là phát hiện quan trọng, vì nó nghĩa là mô hình của ta về hệ thống còn thiếu một đường.

**✅ Ngày 0 (22/07) — NGHIỆM THU ĐẠT, cả hai chiều:**
- Compute `production` chuyển sang **Idle** ("Compute is suspended and automatically activates on client connections") — tức Fly ping `/api/healthz` mỗi 30 giây **không còn đánh thức DB**.
- Chủ mở web và dùng thật → **Active ngay lập tức**. Đây là nửa quan trọng thứ hai: nếu chỉ kiểm chiều "ngủ được" thì có thể vô tình đã làm hỏng đường đánh thức mà không biết.
- Gọi thật: `GET /api/healthz` → `{"status":"ok","version":"0.1.0"}` (**không còn key `db`**) · `GET /api/readyz` → `{...,"db":"up"}`.

**📅 Chu kỳ free — chốt điểm mù (chủ tra 2026-07-22, [Neon plans](https://neon.com/docs/introduction/plans#usage-metrics)):** hạn mức reset **ngày 20 hàng tháng**; chu kỳ hiện tại bắt đầu **20/07/2026**, đợt sau **20/08/2026**. CU-hours và network transfer reset theo chu kỳ; **storage/branches là hạn mức liên tục, KHÔNG reset** — nên đây là hai loại ngưỡng khác nhau, đừng gộp khi soi. Vượt hạn mức ⇒ compute suspended tới chu kỳ sau, **dữ liệu không bị ảnh hưởng**.

Có ngày reset thật thì mọi dự phóng mới tính được:
- **Đường đã tránh được:** 4,54 CU-hrs lúc 22/07, còn 95,46 cho 29 ngày. Với 6 CU-hrs/ngày (bản chưa vá) ⇒ cạn sau ~15,9 ngày ⇒ **compute treo khoảng 06–07/08**, tức **mất DB 13 ngày** trước khi reset 20/08. Ước lượng ~06/08 nêu lúc chưa biết ngày reset **khớp**.
- **Đường hiện tại:** 4,54 + 29 ngày × (<1) ⇒ **~20–34 CU-hrs cuối chu kỳ**, dư 3–5×. Gần như toàn bộ 4,54 đã tiêu là do chính con bug.

Mỗi ngày ghi: CU-hrs cộng dồn · CU-hrs riêng 24h qua · có thấy khoảng INACTIVE không. Sau 3 ngày, nếu <1 CU-hr/ngày thì hạ nhịp về 7 ngày như thường lệ.

**Giá đã trả cho việc cho Neon ngủ:** query đầu sau khi ngủ = **1,719 giây** (đo thật ở 006, ngưỡng báo động 3s). Cold-start là dealbreaker ở read-path (`architecture-brief.md` §64) nên đánh đổi này phải biết rõ: **1,7s một lần, đổi lấy DB không chết giữa tháng.** Nếu thực tế dùng thấy khó chịu thì đường nâng cấp là Neon Launch (~\$5/mo, tắt được scale-to-zero) — **cửa 2 chiều, không phải quyết định bây giờ**.

### 7.4 Còn phải thiết kế

Chính chủ yêu cầu tư vấn chi tiết hơn về mảng này **sau khi vá xong** — nội dung để bàn: tự động hoá (script kéo Fly GraphQL + Neon REST API, in bảng so ngưỡng, lệch thì mở issue) **gộp vào 008b** vì đó đúng lúc hạ tầng GH Actions cron ra đời; cách ghi log số liệu theo thời gian; và ngưỡng cho các dòng chi phí chưa tồn tại (LLM usage ở Bước 1 — dòng biến động nhất sắp tới).

📝 **2026-07-23:** vế *"gộp vào 008b vì đúng lúc hạ tầng GH Actions cron ra đời"* **hết căn cứ** — §9 devops đã đẩy script sang **008c**, và giờ hạ tầng cron **không còn là GH Actions** (§10 devops). Script soi hoá đơn chạy ở đâu là câu hỏi mở lại: GH Actions vẫn dùng được cho việc **không phải production runtime** (chạy trễ 30 phút không sao), nhưng nếu đã có Cloud Scheduler thì cân nhắc gộp một mối.

### 7.5 🆕 2026-07-23 — scale-to-zero: số mới, và một cảnh báo §6 đã hết hiệu lực

**Fly — dòng chi phí đổi hẳn.** Trạng thái ổn định cũ = 86.400 units/ngày ⇒ **\$2,50/tháng** (§7.1 đo thật). Với `auto_stop_machines = 'suspend'` + `min_machines_running = 0`, chỉ còn trả tiền lúc máy thức + rootfs lúc ngủ:

| Khoản | Số |
|---|---|
| CPU/RAM lúc ngủ | **\$0** — Fly tính stopped **và** suspended như nhau |
| Rootfs lúc ngủ | \$0,15/GB/tháng, **theo dung lượng THẬT ĐÃ DÙNG** (không phải 8GB cấp phát — Fly staff xác nhận) ⇒ ước **\$0,05–0,12** |
| Máy thức | \$0,00000095/giây ⇒ ~2h/ngày ≈ **\$0,20** |
| **Tổng ước** | **~\$0,30/tháng** (≈ tiết kiệm **50k VNĐ/tháng**) |

⚠️ **Ba dòng trên là ƯỚC, chỉ có hoá đơn mới là số thật** — và đó đúng là việc §7 sinh ra để làm. **Cần đo trên hoá đơn thật sau 3–5 ngày:** ① units/ngày thật (suy ra giờ thức thật, khác xa "2h/ngày" giả định nếu có gì đang gọi máy); ② **dòng rootfs** — dòng chưa từng xuất hiện trong hoá đơn trước đây, vì trước giờ máy không bao giờ ngủ.

**Ngưỡng §7.2 phải sửa theo, nếu không sẽ báo động sai:** dòng "Fly units/ngày ~86.400, **>90.000 ⇒ đang chạy >1 máy**" **hết đúng** kể từ 23/07 — giờ 86.400 units/ngày nghĩa là **máy không bao giờ ngủ**, tức autostop hỏng hoặc có thứ gì đang gọi liên tục. Ngưỡng mới: **kỳ vọng <15.000 units/ngày; >40.000 ⇒ đi tìm cái gì đang giữ máy thức.** *(Đây là ví dụ sạch của lớp lỗi §7.1 đã ghi: một ngưỡng đúng tuyệt đối trở thành mù khi giả định bên dưới nó đổi ở file khác.)*

**Neon: không đổi, nhưng có thêm một lớp bảo vệ miễn phí.** Máy đang ngủ thì health check cũng không chạy ⇒ **máy ngủ không ping được bất cứ thứ gì**. Sự cố 21/07 giờ có hai hàng rào chứ không phải một (`healthz` không chạm DB, + máy phần lớn thời gian không tồn tại).

**📌 Cảnh báo ở §6 đã HẾT HIỆU LỰC — sửa đè, không thêm note** (đúng luật D1: *current state* thì sửa tại chỗ, chỉ *quyết định* mới cộng dated note). Dòng cũ ghi *"⚠️ bật billing = mất free tier project đó → acc có 300K VND credit tách project riêng"*. Hiện trạng 23/07: project `microSched` **tạo 21/07 và đã là Tier 1 · Prepay ngay từ đầu** ⇒ chưa bao giờ có free tier Gemini trên project đó để mà mất; lời dặn "tách project riêng" nếu để nguyên sẽ khiến người đọc sau tưởng còn thứ cần giữ.

**Hai khoản lãi không mua có chủ ý, ghi lại vì cả hai đều có giá trị thật:**
- **Cloud Scheduler = \$0** (3 job free/billing account, dùng 1) ⇒ đổi cả hạ tầng cron mà **không thêm dòng chi phí nào**. Cùng loại "cổ tức" với ghi chú GitHub Actions = \$0 ở §7.2.
- **Gemini API ở paid tier thì Google KHÔNG train trên dữ liệu của mình** (free tier thì có). `auth-brief.md` R1–R7 bắt *private vào context ⇒ ép no-train cả cascade* — đường Gemini **đã sẵn thoả** nhờ Tier 1. Trước là ràng buộc phải đi tìm cách lách, giờ là chuyện đã rồi.

**Budget alert 88k VNĐ giờ gác chung hai thứ không liên quan** — LLM spend (Bước 1, dòng **không có trần**, xem §7.2) và hạ tầng cron (\$0, có trần cứng). Alert kêu thì không biết ngay là do cái nào. Chưa cần xử lý khi Cloud Scheduler còn free, nhưng **ghi ra để lần soi sau không phải suy lại**.

---
*Cập nhật khi: đổi host/DB/LLM provider, hết credit, đổi công cụ dev-stack (§6), hoặc tới mốc soi-lại 3 tháng (~10/2026). §7 cập nhật theo nhịp 3–7 ngày — đó là mục đích của nó. Thêm ghi chú có ngày — không xoá trắng con số cũ.*
