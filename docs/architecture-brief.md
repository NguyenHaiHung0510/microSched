# Decision brief — kiến trúc, hosting & AI-tooling (microSched)

> Decision record **tự-chứa** (đọc được ở phiên 0-context). **Mốc: chốt 2026-07-19.** ⚠️ Hạ tầng đổi nhanh (giá Fly, chính sách Oracle, data-policy OpenRouter…) — số liệu chi tiết + nguồn xem `cost-brief.md` (mốc riêng, soi lại ~3 tháng/lần). File này giữ *quyết định + lý do*, không giữ giá — giá đổi không làm brief này sai.

## 0. Bối cảnh & phạm vi
Nối tiếp `db-and-data-model-brief.md` (DB/hosting DB đã chốt: Neon). Brief này trả lời phần còn lại của Phase B: **app gồm mấy mảnh, chạy ở đâu, truy cập kiểu gì, AI-tooling chuẩn hoá ra sao, ngôn ngữ/framework nào.** Đây vẫn là cửa tương đối dễ đổi (Docker → portable), khác DB/schema (cửa một-chiều).

## 1. Ngôn ngữ — ✅ Python cho lõi backend/AI
**Đã cân nhắc "AI viết code nên ngôn ngữ hết là rào cản" — kết luận: chỉ đúng một phần.** AI hạ được tường *viết code* (syntax/boilerplate), **không hạ được tường *ecosystem*** (chọn Rust/Go thì không AI nào tạo ra hộ một hệ `pgvector`+embedding+agent-eval chín như Python đã có) và chỉ hạ **một phần** tường *vận hành/debug* (behavior runtime lúc 11h đêm vẫn cần hiểu, không chỉ gõ).

- **Lý do chọn (đã hiệu chỉnh — merit khách quan, KHÔNG dựa "đã quen"):** (1) ecosystem AI/ML/pgvector/agent-eval chín nhất ở Python — 6–12 tháng trước TS về RAG/eval depth, mà Bước 1–3 microSched cày đúng chỗ đó; (2) khớp nghề AI-eng ("làm sản phẩm ứng dụng AI") — stack transferable; (3) **hosting là *hòa*, không phân biệt** (xem §5) nên không phải yếu tố. *Breakthrough đến từ tầng AI, không từ ngôn ngữ web* → giữ ngôn ngữ thực dụng.
- **Đã tái-thẩm 2026 vs TS full-stack, không chọn nhưng ghi rõ (khoảng cách đã hẹp):** LangGraph.js *đã ngang tính năng* LangGraph Python; 60–70% batch YC X25 xây agent bằng TS; Vercel AI SDK có DX streaming đẹp nhất. **Nhưng:** Vercel AI SDK *không* phải RAG framework đầy đủ (thiếu loader/chunking/vector-store); tài liệu học Python vẫn ~10× (câu trả lời cộng đồng 90% Python). → 2026 đây là câu hỏi *mục tiêu*, không phải "làm được hay không"; với dự án học-AI-depth thì Python hơn. (Note 2026-07-19: mục "vốn kinh nghiệm Python/FANG" **cố ý KHÔNG tính là trọng số** — mục tiêu hè là đổi mới, không dựa cái cũ.)
- **Không phải "một ngôn ngữ duy nhất":** frontend là PWA-JS **mỏng** (client câm, mọi logic AI+domain ở Python) — seam JSON sạch, bề mặt cross-language nhỏ (xem §4/§9). Go/Rust/Elixir/Phoenix/Rails: đáng mở mang riêng, không hợp làm trục — bỏ.

## 2. Backend framework — ✅ FastAPI (chốt 2026-07-19)
Fork thật sự sau khi loại Django (batteries/admin thừa cho single-user + cạnh tranh với UI viewability tự xây) = **FastAPI vs Litestar**:

| Tiêu chí | FastAPI (✅ chọn) | Litestar (ứng viên chính, không chọn) |
|---|---|---|
| Streaming token LLM | ✅ async-native | ✅ async-native |
| Tool schema có kiểu (Bước 2) | ✅ **Pydantic v2 = chuẩn de-facto** tool-schema/structured-output LLM | ✅ msgspec/attrs/Pydantic |
| Thiết kế "tầng đọc/ghi sạch" | ghép SQLModel/SQLAlchemy (tự lắp) | **SQLAlchemy-native, DI sạch hơn** — đẹp hơn |
| Ecosystem / đỡ-bị-kẹt / AI-assist | ✅ **khổng lồ** (4.5M dl/ngày; OpenAI/Anthropic dùng); AI-coding hỗ trợ dày | 🔴 nhỏ hơn nhiều → ít lời giải khi kẹt, **ít data cho AI-assist** |

**Vì sao FastAPI (lý do hiệu chỉnh, KHÔNG dựa FANG/đã-quen):**
1. **Tối đa thời-gian-cho-AI, tối thiểu plumbing:** ecosystem lớn nhất + AI-assistant hỗ trợ tốt nhất → ít sa lầy framework → đúng nguyên tắc "đừng đổ sức vào phi-AI". Đây là merit *khách quan của ecosystem*, không phải "quen tay".
2. **Ăn khớp tầng AI:** Pydantic v2 là *lingua franca* tool-calling/structured-output → Bước 2 khớp mượt.
3. **Breakthrough đặt đúng chỗ:** cái mới đến từ *tầng AI* (cascade/RAG/tool-audit), framework web giữ thực dụng.

**Litestar** thắng về *chất lượng thiết kế* (DI/DTO/SQLAlchemy-native) — nhưng "rủi ro support + AI-assist mỏng" lại hút đúng loại năng-lượng-phi-AI cần tránh → chọn Litestar chỉ hợp nếu muốn *chính framework* là bài học nâng cao. Không phải ưu tiên của dự án này.
**Coupling để Nhóm 2:** tầng đọc/ghi sạch ghép **SQLModel** (Pydantic+SQLAlchemy hợp nhất, cùng tác giả FastAPI) hoặc SQLAlchemy 2.0 async + Pydantic; migration Alembic; ASGI Uvicorn. → ✅ **Nhóm 2 chốt SQLModel + Alembic (có hàng rào QA), 2026-07-19** — xem `schema-physical-brief.md`.

## 3. Kiến trúc — ✅ Modular monolith, 1 tiến trình
**Không microservices.** Một user → không áp lực scale nào biện minh tách service qua network; tách ra chỉ mua thêm DevOps mà không được gì, và ngược hẳn triết lý "chống split-brain, ít mảnh rời" đã chốt ở DB.

```
┌──────── 1 process (FastAPI, Fly Machine) ──────────────┐
│ Web/API │ Domain (CRUD) │ Retrieval (pgvector) │ Agent  │
│                    ↑ "tầng đọc/ghi sạch" dùng chung     │
│                      UI + Agent — lý do thật của rewrite│
└──────────┬───────────────────────┬──────────────────────┘
           │                       │
        Neon PG                LLM API (ext, OpenRouter)
     (+pgvector)
```
- **Ranh giới module = trong process** (Web/Domain/Retrieval/Agent/Jobs), không phải ranh giới mạng.
- **Background/định kỳ (embed, import lịch, backup, nhắc thuốc):** **external cron (GitHub Actions)** gọi endpoint — không thêm hạ tầng, sống được kể cả khi app đang nghỉ. **Bỏ** Celery/RQ + Redis broker — thừa cho một user.
- **Hệ quả quan trọng:** "nhắc uống thuốc" = cron bắn đúng giờ → đánh thức app → gửi web-push. Cold-start vài giây chấp nhận được cho *lời nhắc*, nhưng **không chấp nhận được cho thao tác tương tác trực tiếp** → xem §4 (offline-first) và §5 (always-on).

## 4. Frontend/PWA — ✅ offline-first cho capture, còn lại OPEN
Yêu cầu cứng đã nêu: xem task hôm nay / ghi ý tưởng ngay **không được đợi**. Tách 2 đường theo đúng nơi nó cần giải:

| Thao tác | Cái chặn thật | Lời giải |
|---|---|---|
| Ghi note/ý tưởng ngay | write path | **PWA offline-first**: ghi IndexedDB tức thì (0ms, kể cả offline), sync nền sau — **không phụ thuộc host** |
| Xem task hôm nay | read path (cần server+DB) | **Host always-on** (§5) |

- ✅ **Chốt nguyên tắc:** capture phải hoạt động offline-first, độc lập tốc độ host.
- ✅ **Chốt kiểu triển khai = SPA/PWA *tĩnh*** (không SSR). *SPA* = một trang HTML, JS trong browser đổi nội dung + gọi JSON API. *Tĩnh* = sau build chỉ là file `html/js/css`, **không tiến trình Node lúc chạy** → FastAPI serve thẳng (`StaticFiles`), **1 runtime, 1 Fly Machine** (xem §5/§9). *PWA* = SPA + Manifest (cài được) + Service Worker (offline + web-push, chạy trong browser) + IndexedDB (lưu offline). → app riêng-tư/offline-first **không cần SEO/SSR** nên vấn đề 2-runtime không bao giờ xảy ra, dù frontend viết bằng TS hay JS.
- ⚠️ **OPEN — để phiên frontend:** framework/stack UI cụ thể (React/Svelte/Preact/vanilla), thư viện sync (local-first engine như PowerSync/ElectricSQL, hoặc tự viết sync qua queue), chi tiết web-push.

## 5. Hosting — ✅ Fly.io, always-on, region `sin`
**Điều kiện ràng buộc thật (do chính chủ nêu):** có thẻ quốc tế, chịu được vài $/tháng, nhưng **cold-start là dealbreaker** cho read-path tương tác. → loại thẳng mọi phương án scale-to-zero (Render free, Fly-autostop) cho host chính; chuyển hẳn sang **always-on**.

**Đã loại và lý do (khách quan, xem chi tiết `cost-brief.md` §3):**
- **Shared/web-hosting VN** (BKNS/iNET "Hosting", promo "0đ") — **sai category**: không SSH/root/Docker/long-running, chỉ PHP/WordPress. Không phải ứng viên dù giá 0đ.
- **Oracle Always-Free ARM** (dù $0 + always-on + 12GB) — hào phóng vì là loss-leader hút khách vào OCI, đổi lại: báo cáo **terminate/purge data không cảnh báo dù trong hạn mức**, idle-reclaim (CPU<20% p95/7 ngày — app 1 user chính là đối tượng bị thu hồi), "out of host capacity", không SLA. → dùng làm **box thí nghiệm** (model local sau này), **không làm host chính**.
- **Hetzner** — rẻ/mạnh nhưng EU-only (~250ms từ VN) — sai region cho app tương tác.
- **Render free** — cold-start 30–60s — vi phạm điều kiện cứng.

**Đã chọn Fly.io.** Cân nhắc trung thực cả điểm yếu: uptime thực đo ~92%/30 ngày (dưới SLA 99.9% họ công bố), phần lớn sự cố tới từ Fly Managed Postgres/Consul — **ta không dùng Fly-PG (dùng Neon)** nên né được lớp sự cố hay gặp nhất. Vài giờ downtime/năm chấp nhận được: docs đã chốt "five-nines vô nghĩa với 1 user", và 3-2-1 backup đã lo phần mất dữ liệu.
- **Cấu hình:** 1× Machine `shared-cpu-1x`, always-on (`min_machines_running=1`, tắt autostop), region `sin`. **Khởi đầu 256MB ($2.02, đúng ngân sách gốc), theo dõi memory, chỉ `fly scale memory 512` ($3.3) nếu OOM** — không cam kết $4 trước. **`fly scale count 1`** — `fly launch` mặc định tạo 2 máy (HA), single-user không cần → bẫy chi phí #1.
- **Dùng:** Shared IPv4 (free) + TLS free (Let's Encrypt qua `fly certs`); Secrets (mã hoá at-rest cho API key/DB url); `fly deploy` qua GitHub Actions.
- **Không dùng:** Volumes (data ở Neon), Fly Managed Postgres, Tigris (backup đã có Google Drive).
- **Cửa 2 chiều:** Docker image chuẩn → đổi sang Render/VPS trong vài giờ nếu cần.
- **Bắt buộc vận hành:** đặt spending/budget alert (pay-as-you-go theo giây, không free allowance).

## 6. Truy cập & domain — ✅ `*.fly.dev` trước, domain riêng khi cần bền
- Fly cấp sẵn `tên-app.fly.dev` + HTTPS tự động, **miễn phí, dùng ngay** — không cần mua gì, không đụng IP thô.
- **Domain riêng = tuỳ chọn**, đáng mua *sớm* nếu định đổi host về sau: PWA-install + đăng ký web-push gắn với **origin** → đổi host mà giữ nguyên domain thì không phải cài lại PWA/re-subscribe push. Mua ở Cloudflare Registrar (giá gốc, không bẫy renewal). Chi tiết giá: `cost-brief.md`.

## 7. Auth — ⚠️ leaning: Google OAuth + allowlist cứng
App sẽ public trên internet, một-người-dùng, dữ liệu quý → cần auth nhưng **không tự xây password** (phiền + rủi ro tự implement sai).
- **Leaning:** OAuth Google (Authlib/fastapi-sso) → sau login check email ∈ allowlist hardcode/env → cookie session. Lý do: "đứng trên vai khổng lồ" (Google lo credential), giữ đúng 2 hạ tầng (không thêm provider), và OAuth là kỹ năng đáng học một lần (đúng track AI-eng).
- **Đã cân nhắc, không chọn ngay nhưng ghi lại như "cửa thoát":** Cloudflare Access — cấu hình 100% UI, <10 phút, 0 dòng code, free (50 user/50 app). Nếu OAuth tự-implement thành hố sâu, đây là phương án rút lui không tốn thêm gì.
- Chưa chốt hẳn (⚠️) vì implementation cụ thể (thư viện, cookie/session store) chưa quyết — **để phiên auth/scaffold riêng** (KHÔNG thuộc Nhóm 2; Nhóm 2 chỉ lo schema vật lý).

## 8. AI-tooling & MCP — ✅ tool layer chuẩn hoá ngay, MCP protocol hoãn
**Tách rõ "chuẩn hoá" khỏi "nói MCP":** chuẩn hoá thật nằm ở **hợp đồng typed sạch** (mỗi tool = 1 Pydantic schema + confirm + audit — đây chính là "tầng ghi sạch" Bước 2 đã có trong `forward-spec.md`). MCP chỉ là *một cách chiếu* hợp đồng đó ra ngoài cho consumer khác.
- ✅ **Làm ngay:** tool layer typed sạch (Pydantic schema, confirm, audit_log) — MCP-ready by construction.
- ❌ **Không làm giờ:** bọc MCP server khi Agent nội bộ là consumer duy nhất — round-trip MCP với chính mình là indirection vô ích.
- **Khi nào bật MCP thật:** có consumer thứ 2 (vd Claude Desktop muốn đọc note/task). Lúc đó `FastMCP` mount **cùng process/host hiện có** — **không cần host thứ 2, không thêm provider.**
- **Model "não" Agent:** OpenRouter cascade (model rẻ → escalate frontier khi cần), tận dụng credit sẵn có (Google AI Studio, OpenAI, OpenRouter free models). **Chưa chạy model local** — Fly 512MB không đủ tài nguyên; Oracle 12GB chỉ đủ cho model rất nhỏ/CPU-only, không đáng tin làm "não" tool-calling. Chỉ **chừa seam model-router** (đã có khái niệm cascade trong docs) để trỏ phần nào đó sang local sau nếu muốn — không xây trước khi cần.
- **Privacy LLM bên thứ ba (bookmark cũ ở `forward-spec.md` §E):** đã đối chiếu lại — dữ liệu health/finance của một sinh viên **không cực nhạy cảm**, nên **không over-engineer redact**. Giải bằng **cấu hình provider** (rẻ hơn viết code): OpenRouter mặc định không lưu prompt trừ opt-in; bật *disallow-training-providers*; dùng tham số `zdr` (zero-data-retention) cho riêng query đụng finance/health. `audit_log` giữ trong DB của mình, không để log thô chảy ra ngoài.

## 9. Repo layout — ✅ 1 repo, backend serve PWA cùng origin
Một repo (backend + frontend), backend serve static PWA build cùng origin → không CORS, cookie/session đơn giản, một lần deploy (khớp §3 modular-monolith, §5 Fly 1-Machine).

## 10. Tổng hợp trạng thái
| # | Quyết định | Trạng thái |
|---|---|---|
| Ngôn ngữ lõi | Python | ✅ |
| Framework | **FastAPI** (+ Pydantic v2; **ORM=SQLModel chốt Nhóm 2** → `schema-physical-brief.md`) | ✅ |
| Kiến trúc | Modular monolith, cron ngoài cho jobs | ✅ |
| Frontend | SPA/PWA **tĩnh** (offline-first), serve chung 1 origin | ✅ kiểu triển khai / ⚠️ stack UI cụ thể OPEN |
| Hosting | Fly.io, 1×512MB always-on, `sin` | ✅ |
| Domain | `*.fly.dev` trước, custom khi cần bền | ✅ |
| Auth | Google OAuth + allowlist | ⚠️ leaning |
| AI tool layer | Typed, MCP-ready, MCP bật khi có consumer 2 | ✅ |
| Model AI | OpenRouter cascade, chưa local | ✅ |
| Privacy LLM | Cấu hình provider (no-train, zdr), không redact nặng | ✅ |
| Repo | 1 repo, 1 origin | ✅ |
| Chi phí | xem `cost-brief.md` | — |

## 11. Chưa quyết (đẩy sang Nhóm 2/3 — không phải phạm vi brief này)
> ✅ **Nhóm 2 đã CHỐT 2026-07-19** (`schema-physical-brief.md`): DDL (enum=TEXT+CHECK, index tối thiểu, cascade), ORM=**SQLModel**, Alembic+QA, DB role+schema riêng, khoá chính **UUIDv7**, chiến lược **log AI 3 tầng** + soft-delete. Còn lại:
- **Phiên thiết kế TRACKING** (mục tiêu chiến lược): kiểu số `entry.value`, cascade `tracker→entry`, design feature — parked ở `schema-physical-brief.md` §7.
- Kích thước + dimension cột `vector` (coupling embedding model — Bước 1).
- Frontend stack cụ thể + thư viện sync offline-first.
- Auth: thư viện cụ thể, cookie/session store.
- Embedding model, backend LLM mặc định cho Bước 1.
