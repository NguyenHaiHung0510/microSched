# Decision brief — Frontend UI stack (microSched)

> Decision record **tự-chứa** (đọc được ở phiên 0-context). **✅ CHỐT 2026-07-20** (phiên frontend).
> Nối tiếp `architecture-brief.md` §4 — ở đó đã chốt *kiểu triển khai* (SPA/PWA **tĩnh**, offline-first, serve cùng origin); file này chốt **stack cụ thể**. Nghiên cứu live tra cùng ngày (nguồn §8). Phần **cố ý còn mở** (router/chart/layout/web-push chi tiết — quyết lúc scaffold/build, không phải cửa một chiều): §7.

## 0. Ràng buộc kế thừa (không bàn lại ở đây)

- **SPA/PWA tĩnh, không SSR** — sau build chỉ còn file `html/js/css`, FastAPI serve qua `StaticFiles`, cùng origin, 1 Fly Machine (`architecture-brief.md` §4/§9).
- **Capture offline-first đã spec xong** (`tracking-brief.md` §8.1/K9): client sinh UUIDv7, ghi IndexedDB tức thì, toast 10s Hoàn tác = soft-delete, sync-retry idempotent theo UUID.
- **Client mỏng** — mọi logic AI + domain ở Python; seam = JSON API.
- Tiêu chí chọn = đúng phiên backend (FastAPI): **tối đa thời-gian-cho-AI** — ecosystem + AI-assist là trọng số chính; "đã quen" cố ý KHÔNG tính (mục tiêu hè là đổi mới).

## 1. Stack ✅ CHỐT (bảng tổng)

| Lớp | Chọn | Trạng thái tại 2026-07-20 | Ghi chú |
|---|---|---|---|
| Framework | **React** | 19.2.x stable | Fork A — lý do §2 |
| Ngôn ngữ | **TypeScript** | — | types phía client sinh từ OpenAPI của FastAPI → **Pydantic là nguồn hợp đồng duy nhất** (công cụ sinh cụ thể chọn lúc scaffold) |
| Build | **Vite 8** | stable 03/2026, bundler Rust **Rolldown** 1.0 (05/2026) | |
| PWA / service-worker | **vite-plugin-pwa** | bảo trì tích cực (update 05/2026; team đang chuẩn bị fork Workbox riêng) | SW vẫn cần cho offline/precache kể cả khi noti dùng Declarative Web Push (§5) |
| UI | **Tailwind CSS v4 + shadcn/ui** | shadcn full-support TW v4 + React 19 | toast nay là **sonner** — khớp đúng "toast 10s + Hoàn tác" đã chốt; quy ước dùng: §6 |
| Server-state | **TanStack Query v5** | 5.101.x (06/2026) | + persist vào IndexedDB → mở app thấy ngay data lần cuối, revalidate khi online |
| Local DB + sync | **Dexie.js + outbox queue tự viết** | — | Fork B — lý do §3; **KHÔNG** sync-engine |
| Router / chart | ⏸ chọn lúc scaffold / build | — | §7 — chi tiết nhỏ, không phải cửa một chiều |

## 2. Fork A — vì sao React (không Svelte 5)

Đây là **cặp FastAPI-vs-Litestar lặp lại** ở tầng client:

| | React (✅ chọn) | Svelte 5 (ứng viên thật duy nhất, không chọn) |
|---|---|---|
| Ecosystem / AI-assist | ~45% professional dev (khảo sát 2025); corpus AI-coding dày nhất | nhỏ hơn nhiều; runes (Svelte 5) còn mới → AI hay trộn cú pháp Svelte 4/5 |
| DX / chất lượng thiết kế | ổn, nhiều boilerplate hơn | **đẹp hơn** — satisfaction cao nhất State of JS 2025 |
| Hệ chat-UI cho AI (Bước 1) | chín nhất: Vercel AI SDK `useChat`, assistant-ui… đều React-first | mỏng — phần lớn phải tự đúc |
| UI kit | shadcn/ui bản gốc | port shadcn-svelte (theo sau bản gốc) |

**Lý do chọn:** (1) client cố ý mỏng → framework không phải chỗ đặt bài học (bài học nằm ở tầng AI) → chọn thứ ít sa lầy nhất, AI-assist dày nhất; (2) **Bước 1 cần chat UI streaming** (markdown, tool-call, token stream) — hệ component đó gần như chỉ chín ở React, chọn khác = tự đúc đúng loại plumbing cần tránh; (3) khớp portfolio AI-eng (UI sản phẩm AI trong ngành mặc định React). Svelte thắng *chất lượng thiết kế* nhưng chọn nó chỉ hợp khi muốn *chính framework* là bài học nâng cao — không phải ưu tiên dự án này. **Preact** loại (tiết kiệm ~30KB vô nghĩa single-user, đổi lấy edge-case tương thích); **vanilla** loại (mọi component tự đúc = năng lượng phi-AI).

## 3. Fork B — vì sao Dexie + outbox tự viết, KHÔNG sync-engine

- **Phần khó của sync đã được schema giải trước** (phiên tracking): UUIDv7 sinh ở client → server upsert idempotent → retry an toàn (K9); Hoàn tác = soft-delete cùng một nút dù đã sync hay chưa (§8.1). Outbox còn lại là đoạn code nhỏ, hiểu được 100%, không dependency lạ.
- **Sync-engine giải bài toán không tồn tại ở đây** — realtime multi-user conflict resolution. Một user, ghi chủ yếu append (entry), đọc cần server sống (host đã always-on). Đổi lại chi phí thật: PowerSync / ElectricSQL cần **một service đứng giữa Postgres và client** (self-host = thêm mảnh rời, cloud = thêm provider) — vi phạm trực tiếp nguyên tắc "ít mảnh rời, 2 hạ tầng". Zero (Rocicorp) cùng nhóm.
- **TanStack DB** (0.6 tại 07/2026 — persistence + offline, chỉ là lib client không cần service, cùng team TanStack Query) = **cửa nâng cấp HAI CHIỀU** được ghi rõ: nếu outbox tự viết bắt đầu phình thì chuyển; chưa dùng ngay vì còn 0.x.

## 4. Mô hình runtime — "2 ngôn ngữ nhưng vẫn 1 máy" (giải thắc mắc chủ, 2026-07-20)

Câu hỏi của chủ: *"vừa Python vừa TS (± Dexie) sao chạy hết trong 1 Fly machine?"* — Trả lời: **không chạy hết trong 1 machine, và không cần** — mỗi ngôn ngữ chạy ở đúng chỗ của nó:

```
LÚC BUILD (máy dev / CI — nơi DUY NHẤT có Node)     LÚC CHẠY (production)
┌────────────────────────────────┐        ┌───────────────────────────────┐
│ frontend/ (TypeScript + React) │        │ Fly Machine — ĐÚNG 1 process  │
│ Vite build → dist/             │  copy  │ Python (FastAPI + uvicorn)    │
│ (html/js/css TĨNH)             │ ─────▶ │  /api/* → JSON                │
└────────────────────────────────┘        │  /*     → serve file dist/    │
                                          └───────────────┬───────────────┘
                                                          │ html/js/css
                                          ┌───────────────▼───────────────┐
                                          │ Browser (iPhone của chủ)      │
                                          │ React + Dexie + service worker│
                                          │ CHẠY Ở ĐÂY, không phải ở Fly  │
                                          └───────────────────────────────┘
```

- **Node chỉ tồn tại lúc build** (trên laptop dev hoặc CI). Docker **multi-stage**: stage 1 (image Node) build ra `dist/` → stage 2 (image Python) copy `dist/` vào → image cuối **không chứa Node**. Trên Fly chỉ có đúng 1 process Python — đúng cam kết "1 runtime" của `architecture-brief.md` §4.
- **Dexie không phải ngôn ngữ thứ ba** — nó (và TanStack Query, outbox) là thư viện TypeScript chạy **trong browser**. Tổng ngôn ngữ: Python (server) + TypeScript (browser), cộng SQL trong Postgres nếu muốn đếm.
- **1 repo** (đã chốt §9): `backend/` + `frontend/` + `Dockerfile` gốc repo. **Dev hằng ngày = 2 process**: `uvicorn` (:8000) + `npm run dev` Vite (:5173, proxy `/api` → :8000, hot-reload). Production không có process thứ hai.
- **Tách biệt bằng hợp đồng, không bằng repo:** FE chỉ gọi JSON API; FastAPI tự sinh OpenAPI → sinh TS types từ đó → đổi schema Pydantic là client biết ngay lúc compile.

## 5. Thiết bị chủ = iPhone (iOS 18.7.9) — hệ quả PWA phải nhớ ✅ ghi 2026-07-20

- **Web-push trên iOS CHỈ hoạt động khi app đã cài Home Screen** (Safari → Share → *Add to Home Screen*), manifest bắt buộc `display: standalone` — chưa cài thì `pushManager` không tồn tại. → onboarding trên máy chủ: **cài PWA trước, rồi mới bật nhắc thuốc**. iOS 18.7.9 > 18.4 nên có thêm lựa chọn **Declarative Web Push** (cơ chế noti mới của Apple từ iOS/Safari 18.4, không cần service worker cho phần push) — chọn lúc build.
- ⚠️ **Nút "✓ đã uống" NGAY TRÊN noti** (`tracking-brief.md` §12): action button trên web-push iOS nhiều khả năng không có/không đủ → thiết kế fallback ngay từ đầu: **tap noti → mở thẳng màn ✓ một chạm** (tổng 2 chạm). Kiểm chứng trên máy thật lúc build; nếu iOS cho action button thì giữ 1 chạm như spec gốc.
- **Storage:** chính sách WebKit miễn cho app đã cài Home Screen khỏi hạn "7 ngày không dùng → xoá storage" của Safari — dù vậy outbox nên flush sớm khi có mạng, không giữ lâu. Kiểm chứng thực tế lúc build, không tin chay.
- **OAuth redirect bên trong PWA standalone** = item test máy thật (bẫy kinh điển iOS: flow văng sang Safari → cookie nằm ở storage Safari, không phải storage app đã cài → login loop).

## 6. Quy ước shadcn/ui + supply-chain (chủ đề xuất, Claude thẩm định + bổ sung, ✅ 2026-07-20)

1. **Add-on-demand:** `npx shadcn add <x>` đúng lúc build feature cần nó — không "add trước 20 cái cho chắc" (component không dùng = dead code phải nuôi; bản chép vào repo không tự update nên chỉ phình + drift với upstream).
2. **Supply-chain đúng bản chất copy-in:** file shadcn kéo về không có hash-pin kiểu lockfile — an toàn đến từ **đọc diff một lần lúc add** (đó là khoảnh khắc rủi ro duy nhất; sau đó là code của mình, git track, không có kênh silent-update). Kỷ luật review-trước-commit + gitleaks sẵn có (`devops-brief.md` §3) áp thẳng, không cần hàng rào riêng. *Tùy chọn rẻ:* pin version CLI khi chạy (`npx shadcn@<ver>`).
3. **Commit `components.json` ngay từ `shadcn init`**, không tay sửa tùy hứng — CLI đọc file này mỗi lần add; đổi nó là quyết định có chủ đích để mọi lần add sau nhất quán style/alias.
4. **(Bổ sung của Claude) Nửa còn lại của bức tranh là npm dependencies thật** (radix/tanstack/dexie… cài qua npm — nơi từng có làn sóng tấn công chuỗi cung ứng npm cuối 2025): commit lockfile + **`npm ci` trong CI/Docker build** (build chỉ theo lockfile, không tự nâng version). Đây mới là cửa chính; quy ước 1–3 lo cửa phụ.

## 7. Cố ý còn mở — quyết lúc scaffold/build (không phải cửa một chiều)

- Router (React Router vs TanStack Router — chi tiết nhỏ) · chart lib cho dashboard (§8.2 tracking-brief đã spec *hành vi*) · công cụ sinh TS types từ OpenAPI.
- Web-push implementation: VAPID keys, `pywebpush` phía FastAPI, SW-push vs Declarative Web Push (§5).
- Layout/màu/lưới nút capture · UI toggle giá (`app_setting`, `tracking-brief.md` §3) · PWA manifest chi tiết.

## 8. Nguồn (tra live 2026-07-20)

[React versions](https://react.dev/versions) · [Vite 8](https://vite.dev/blog/announcing-vite8) · [vite-plugin-pwa](https://github.com/vite-pwa/vite-plugin-pwa) · [shadcn/ui Tailwind v4](https://ui.shadcn.com/docs/tailwind-v4) · [State of JS 2025 — front-end frameworks](https://2025.stateofjs.com/en-US/libraries/front-end-frameworks/) · [tổng hợp khảo sát framework](https://gist.github.com/tkrotoff/b1caa4c3a185629299ec234d2314e190) · [TanStack DB 0.6](https://tanstack.com/blog/tanstack-db-0.6-app-ready-with-persistence-and-includes) · [PowerSync vs Electric](https://powersync.com/blog/electricsql-electric-next-vs-powersync) · [TanStack Query releases](https://github.com/tanstack/query/releases) · [Declarative Web Push (Progressier)](https://progressier.com/pwa-capabilities/declarative-web-push) · [iOS web push yêu cầu Home Screen (Pushpad)](https://pushpad.xyz/blog/ios-special-requirements-for-web-push-notifications)

---
*Cập nhật khi: scaffold chốt các mục §7, hoặc kiểm chứng máy thật §5 cho kết quả khác giả định. Thêm note có ngày — không xóa kết luận cũ.*
