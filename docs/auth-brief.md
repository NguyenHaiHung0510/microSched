# Decision brief — Auth & private unlock (microSched)

> Decision record **tự-chứa** (đọc được ở phiên 0-context). **✅ CHỐT 2026-07-20** (phiên auth, cùng ngày phiên frontend — xem `frontend-brief.md`).
> Giải nốt 3 món treo: `architecture-brief.md` §7 (hết ⚠️ leaning) · mục DEFER "cơ chế mở private" của `tracking-brief.md` §5 · quyết định mới **AI × private** (bộ luật R1–R7, §4). Nghiên cứu live tra cùng ngày (nguồn §7).

## 0. Ràng buộc & threat model kế thừa (không bàn lại)

- Single-user, app public trên internet, dữ liệu quý. **Threat model = social engineering + người nhìn qua vai** (`devops-brief.md` §1) — KHÔNG phải bảo mật đa-user; không tự xây password login.
- **Private = cổng hiển thị** (`tracking-brief.md` §5); mã hóa at-rest đã chốt riêng (encryption review, §6) — master key ở app (Fly secrets) ⇒ **unlock KHÔNG phải cổng khóa mã hóa**, chỉ là cổng authz/hiển thị.
- Ràng buộc cứng của chủ (tracking-brief §6): *"AI đã được thiết kế vào hệ thống thì PHẢI đọc được"* — nền của bộ luật §4.
- Hai công tắc riêng: private ("ai được xem") ≠ toggle giá ("xem con số nào") — đã chốt, không trộn.

## 1. Danh tính — ✅ Google OAuth + allowlist, thư viện = Authlib

- **Flow:** OAuth/OIDC Google (**login-only**: scope `openid email profile`) → check email ∈ allowlist (env var) → tạo session (§2). Sai allowlist = từ chối thẳng, không có trang đăng ký.
- **Thư viện: Authlib** (1.7.2 tại 2026-07, production/stable, tích hợp Starlette/FastAPI chính chủ). **Loại `fastapi-sso`**: wrapper mỏng thêm một tầng che — Authlib gần protocol hơn, đúng tinh thần "OAuth là kỹ năng đáng học một lần" đã ghi ở architecture-brief §7.
- **Chi tiết đỡ việc:** login-only OIDC **không cần refresh token** → app trên Google Cloud Console để chế độ **Testing** với đúng 1 test user (email chủ) là chạy lâu dài, không cần verification (hạn 7-ngày của Testing chỉ áp lên refresh token). ⚠️ Kiểm chứng lại lúc build.
- **Note tương lai (KHÔNG quyết ở đây):** import Google Calendar là **grant riêng** với scope sensitive (`calendar.readonly` → cần app verification nếu production) — lúc làm feature đó cân nhắc **ICS secret URL** thay Calendar API (không OAuth gì cả).
- **Cửa thoát giữ nguyên:** Cloudflare Access (đã ghi architecture-brief §7) nếu OAuth tự-implement thành hố sâu.

## 2. Session — ✅ bảng `session` server-side trong Postgres, cookie chỉ giữ token mờ

| | Signed cookie (không bảng) | **Bảng `session` (✅ chọn)** |
|---|---|---|
| Thu hồi từ xa ("logout mọi nơi") | ❌ phải xoay secret | ✅ xóa row |
| Trạng thái private-unlock | phía client (ký chống sửa, nhưng không tắt sớm từ xa) | ✅ `private_until` nằm server |
| Chi phí | 0 | 1 bảng + ~50 dòng (KHÔNG cần Redis — Postgres đủ) |

- Cookie `HttpOnly + Secure + SameSite=Lax`, chứa token ngẫu nhiên; **DB chỉ lưu hash của token** (DB/dump lộ cũng không cướp được session sống). TTL **rolling 60–90 ngày** — một người dùng, ưu tiên không-friction (khớp hồ sơ chủ: ghét re-login vặt).
- **Không phạm "schema khép":** `schema-physical-brief.md` §8 đã để dành mục cookie/session store cho phiên auth. Bảng mới theo house-rules (UUIDv7 PK, `timestamptz` B2); **cột chính xác đúc lúc scaffold/Alembic** — dự kiến: `id`, `token_hash` (unique), `user_email`, `created_at`/`last_seen_at`/`expires_at`, `private_until` (NULL = đang khóa).
- SameSite=Lax tương thích OAuth redirect (callback là top-level GET). Cùng origin (FastAPI serve PWA) nên không đụng CORS/cookie cross-site.

## 3. Private unlock — ✅ passphrase riêng + Argon2id, mở theo session có TTL

So 2 phương án chủ đã ghi ở `tracking-brief.md` §5:

- ❌ **Loại (1) "OAuth-account cấu hình cứng":** allowlist có đúng 1 account → cờ cứng nghĩa là private *luôn mở* sau login = không còn là cổng; threat "nhìn qua vai" xảy ra đúng lúc máy đang đăng nhập sẵn. (Biến thể "2 account Google" = friction chuyển account, dễ bug.)
- ✅ **Chọn (2) passphrase riêng, độc lập Google:** server verify **Argon2id** (`argon2-cffi`) → set `private_until = now + TTL` trên session row. **TTL mặc định 15 phút** (`app_setting` — cùng pattern hằng số "trước 3 ngày" của subscription); nút **khóa lại ngay** + badge trạng thái đang-mở; **throttle**: 5 lần sai → khóa thử 15 phút.
- **Điểm khớp thiết bị chủ (iPhone — `frontend-brief.md` §5):** lưu passphrase vào iCloud Keychain/password manager → autofill bằng **FaceID** → *không gõ gì trước mặt người đang nhìn* — vá đúng chỗ threat model đau nhất, 0 dòng code thêm. **WebAuthn/passkey step-up = nâng cấp sau** (cửa 2 chiều), v1 không cần.
- Nhắc lại ranh giới: unlock là **cổng hiển thị**; khóa mã hóa AES-GCM vẫn ở app (Fly secrets) — không đổi gì encryption review đã chốt. TTL hết hạn giữa chừng → UI (và AI, §4) mất quyền thấy private từ lượt sau, y hệt nhau.

## 4. AI × private — ✅ bộ luật R1–R7 "AI đi theo cổng session" (chủ chọn 2026-07-20)

**Nguyên tắc gốc (lời chủ):** AI đã integrate vào hệ thống thì đi theo đúng chế độ public/private của session — *"khi bật private là toàn quyền"*; AI hỗ trợ riêng mình mà không sâu/đủ thì không đáng. Nhất quán với ràng buộc cứng "AI PHẢI đọc được" (§0). "Toàn quyền khi mở" chạm 7 bề mặt — mỗi bề mặt một luật:

| # | Luật | Nội dung |
|---|---|---|
| **R1** | Một cổng duy nhất (read) | Session locked → mọi tool của agent filter `is_private` tại **"tầng đọc sạch dùng chung"** (một chỗ, không rải điều kiện); unlocked → AI thấy private y như UI. TTL relock áp cho AI y hệt màn hình. |
| **R2** | KHÔNG lật luật index bền | Giữ nguyên luật encryption review: *đã mã hóa ⇒ không embed, không tsvector* — lý do là **rò nghĩa at-rest trên Neon**, không liên quan session mở/đóng. Thay thế: khi unlocked, agent có tool **runtime search** — giải mã tập private + scan trong process theo từng query, không index bền. Khả thi vì quy mô đo thật (~49 note/<1MB toàn bộ, private là tập con) → mili-giây; private phình hàng nghìn bài → nâng cấp in-memory index dựng-lúc-unlock (2 chiều). |
| **R3** | Route provider | Request có private trong context ⇒ ép **`zdr` + no-train cho TOÀN BỘ cascade** của request đó (escalate vẫn giữ ràng buộc); **loại model thuộc lớp buộc-retention** (vd lớp "Covered" 30-ngày của Claude — đã ghi encryption review). Private đã vào hội thoại → các lượt sau mang nó trong history → cả đoạn còn lại route zdr. **Nói thẳng trade-off:** zdr là *cam kết hợp đồng* của provider, không phải bảo đảm toán học — đây là mức rủi ro chủ chấp nhận để AI đọc sâu. |
| **R4** | Transcript theo cờ | Message sinh ra trong lúc unlocked mang `is_private` (tinh thần K11 mở rộng xuống message tầng-1) → **che khỏi lịch sử chat khi locked**. Thiếu luật này private mode tự thủng qua transcript. Mã hóa at-rest của message thì tầng-1 đã lo (encryption review). |
| **R5** | Background AI public-only | Job cron (embed, insight tương lai, nhắc nhở) không có session → **không bao giờ thấy private**, by construction. Giữ rạch ròi: **mã hóa ≠ private** — cột tiền mã hóa nhưng không private → job/dashboard/AI vẫn đọc qua tầng giải mã bình thường. |
| **R6** | Client cache | Response chứa private **không persist** vào IndexedDB offline-cache (loại khỏi persistQueryClient) — private chỉ sống trong RAM tab đang mở, không nằm lại trên đĩa điện thoại sau khi khóa. |
| **R7** | Write-tools (Bước 2) | Đối xứng R1: agent chỉ ghi vào private khi unlocked; confirm + audit như đã chốt; `audit_log.payload` chỉ marker cho field mã hóa (đã chốt encryption review). "Ở private ghi được cả public" áp cho AI y như cho chủ. |

**Phương án dự phòng (ghi lại, không chọn):** "AI mù private tuyệt đối" — read-tools luôn filter bất kể session. Nếu sau này đổi khẩu vị rủi ro: chỉ cần tắt cổng ở R1, không phá gì (2 chiều).

## 5. Notes phụ ✅

- **Cron endpoints** (GitHub Actions gọi backup/embed/nhắc thuốc): auth bằng **bearer secret riêng** (Fly secret), không đi qua session user.
- **OAuth redirect trong PWA standalone iOS** = item test máy thật lúc build (bẫy kinh điển: flow văng sang Safari → cookie nằm storage Safari ≠ storage app đã cài → login loop) — đã ghi `frontend-brief.md` §5.

## 6. Delta schema từ phiên này (đúc DDL lúc scaffold)

Bảng **`session`** mới (§2) · cờ **`is_private` trên message tầng-1** (R4) · key `app_setting`: TTL private-unlock (§3). Tất cả theo house-rules `schema-physical-brief.md` (B1/B2); đã ghi chéo ở §8 file đó.

## 6.1 📝 2026-07-21 — thi công 007: 4 điểm thực tế lệch/bổ sung giả định

Ghi theo yêu cầu *"cập nhật khi code auth phát hiện khác giả định"*. **Không** điểm nào lật quyết định §1–§5; đều là chi tiết tầng vật lý brief chưa nói tới.

| # | Phát hiện | Xử lý |
|---|---|---|
| **A1** | **Fly cắt TLS ở proxy** → app chỉ thấy request `http`, nên `request.url_for()` dựng ra `http://microsched.fly.dev/auth/callback` — URI **Google chưa từng đăng ký** ⇒ `redirect_uri_mismatch`, login không bao giờ chạy. Brief §1 không lường bước này. | Ép `https` cho mọi host **trừ loopback** (`localhost`/`127.0.0.1` vốn thật sự chạy http). Chọn cách này thay vì thêm biến env `BASE_URL` để không bắt chủ nuôi thêm một secret. Có **test riêng cho cả hai chiều** vì lỗi này *không* hiện ra ở status code — chỉ hiện khi bấm nút thật. |
| **A2** | Authlib giữ `state`/`nonce` bằng **Starlette `SessionMiddleware`** — tức trong app tồn tại một cơ chế signed-cookie **trông y hệt** session đăng nhập. | Tách cứng: cookie riêng `ms_oauth_state`, TTL **300s**, và `request.session.clear()` ngay tại callback. Có test khẳng định cookie state **chết sau handshake**. Session đăng nhập vẫn đúng §2 (opaque token + bảng `session`). |
| **A3** | §2 chốt TTL "60–90 ngày" nhưng không chốt số. | Chọn **90**. Lý do: cửa sổ **rolling** nên nó chỉ kích hoạt sau 90 ngày *không dùng gì cả*; rút ngắn chỉ thêm phiền lúc đăng nhập lại trên PWA mà **không** giảm rủi ro máy bị mất — rủi ro đó xử bằng logout/thu hồi phiên, không phải bằng TTL. |
| **A4** | Brief không nói tới claim `email_verified`. | **Bắt buộc `email_verified=true`** mới qua cổng. Địa chỉ chưa xác minh không chứng minh quyền sở hữu — khớp tinh thần allowlist. |

**Ghi chú kiểm thử:** CI chạy `pytest` **không có Postgres** (workflow `backend` không dựng service DB) → tầng lưu phiên được test qua một double in-memory cùng contract, cộng test riêng cho `PostgresSessionStore` khẳng định **chỉ digest được ghi xuống**. Đường SQL thật vẫn phải nghiệm thu bằng tay (localhost + Fly) theo mục Acceptance của `agent-tasks/007`.

## 6.2 📝 2026-07-21 — kết quả security-review PR #9 (Opus 4.8 MAX, session riêng)

**Không có lỗ HIGH/MEDIUM.** Đã soi và loại: bypass allowlist (hoa-thường/khoảng trắng/thiếu `email_verified`/allowlist rỗng/token null/handshake lỗi — **mọi nhánh hỏng đều fail-closed**), session fixation, path traversal qua SPA mount, SQLi trong `scripts/*`, XSS, secret trong CI (workflow dùng `pull_request` chứ không phải `pull_request_target` → PR từ fork không nhận credential), least-privilege của `microsched_app`.

Điểm đáng giữ: reviewer xác nhận `token["userinfo"]` **chỉ** có sau khi Authlib xong `parse_id_token` (JWKS + `iss`/`aud`/`exp`/`nonce`); bỏ qua bước nào cũng ra `claims = {}` → 403.

**Hai mục cần quyết ở tương lai — không phải việc của 007:**

| Mục | Vì sao ghi lại |
|---|---|
| **CSRF khi Bước 2 có write-tool** | Hiện `SameSite=Lax` là phòng thủ CSRF **duy nhất**, và nó đủ *chỉ vì* endpoint đổi-trạng-thái duy nhất là `POST /auth/logout` (`fly.dev` nằm trong Public Suffix List nên app anh em vẫn là cross-site). **Lax KHÔNG bảo vệ `GET` đổi trạng thái** — khi Bước 2 mở tool ghi thì phải quyết tường minh (token CSRF hoặc bắt buộc mọi write là POST/PUT). |
| **Nâng version Authlib = thay đổi có tính bảo mật** | Test mock nguyên client Authlib nên state/nonce/chữ ký **không** được chạy trong CI; tính đúng đắn dựa vào bản đã pin. ⇒ mỗi lần bump `authlib` trong `uv.lock` phải review có ý thức, không merge kiểu dependency-bump thường. |

Hai mục nhỏ hơn (cảnh báo lúc khởi động khi thiếu `OAUTH_STATE_SECRET`; `except Exception` trần ở callback xoá mất phân biệt "Google chết" với "có người dò") — **để dành thành task polish sau merge**, không sửa ngay để diff đã review không đổi.

## 6.3 📝 2026-07-21 — bốn lỗi chỉ lộ ra khi mở trình duyệt thật

007 xanh CI 100%, security-review không tìm ra HIGH/MEDIUM — rồi bốn lỗi này vẫn tới tay chủ. **Không cái nào nằm trong code**, nên không công cụ đọc-code nào bắt được:

| # | Triệu chứng | Gốc | Vá |
|---|---|---|---|
| **B1** | Fly crash-loop, app không khởi động | `httpx` nằm ở nhóm `dev`; Authlib import nó lúc load package; image production cài `--no-dev`. **pytest chạy *với* nhóm dev nên nhóm dev che mất dependency prod bị thiếu** | chuyển `httpx` sang dependency chính + job CI `runtime-deps` cài `--no-dev` rồi thử `create_app()` |
| **B2** | Bấm "Đăng nhập bằng Google" không đi đâu cả | `vite-plugin-pwa` mặc định cho service worker trả `index.html` cho **mọi** điều hướng → nuốt luôn `/auth/login`, request không bao giờ tới FastAPI | `workbox.navigateFallbackDenylist: [/^\/auth\//, /^\/api\//]` |
| **B3** | `?code=…` nằm lại trên thanh địa chỉ **chỉ ở nhánh bị từ chối** | nhánh hợp lệ 303 về `/` nên URL bị thay; nhánh từ chối trả HTML **ngay tại** `/auth/callback` nên code ở lại URL + history | nhánh từ chối cũng 303, sang `/auth/denied` |
| **B4** | Đăng xuất xong dash vẫn hiện; đăng nhập lại không qua Google | (a) query cache giữ `data` cũ khi refetch lỗi → dash và màn login cùng hiện; (b) Google vẫn giữ phiên riêng của nó nên nhận diện im lặng | (a) đăng xuất bằng **điều hướng thật** thay vì can thiệp cache; (b) `prompt=select_account` |

**B3 do chính chủ tìm ra**, bằng thao tác không agent nào làm: **đối chiếu URL giữa nhánh hợp lệ và nhánh bị từ chối rồi hỏi vì sao khác nhau** — kiểm thử khác biệt, không phải kiểm thử theo checklist. Bài học chung từ B3: **nhánh lỗi và nhánh thành công có bề mặt rò rỉ khác nhau**; chỉ test happy path là mù đúng nửa còn lại.

Quy ước rút ra (đã ghi thành luật ở `agent-tasks/README.md` §"Quy ước BÁO CÁO" và `devops-brief.md` §7.1): **xanh CI ≠ chạy được**; deploy + nhìn bằng mắt là một bước nghiệm thu riêng.

## 7. Nguồn (tra live 2026-07-20)

[Authlib PyPI](https://pypi.org/project/Authlib/) · [Authlib FastAPI client](https://docs.authlib.org/en/v1.3.2/client/fastapi.html) · [iOS web push yêu cầu Home Screen (Pushpad)](https://pushpad.xyz/blog/ios-special-requirements-for-web-push-notifications) · Claude API retention (đã tra ở encryption review, `tracking-brief.md` §6)

---
*Cập nhật khi: code auth lúc scaffold phát hiện khác giả định (Google Testing mode, iOS redirect), hoặc Bước 1/2 kích hoạt lại phương án nâng cấp của R2/R3/R7. Thêm note có ngày — không xóa kết luận cũ.*
