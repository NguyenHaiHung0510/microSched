# 007 — Auth: Google OIDC + allowlist + session server-side

> **Trạng thái:** 🔍 **CHỜ NGHIỆM THU (2026-07-21)** — code + test xong (T1, branch `feat/007-auth-oidc-session`). Phần máy kiểm được đã xanh; 4 mục Acceptance cần account Google thật vẫn chờ chủ chạy tay. Lệch giả định ghi ở `docs/auth-brief.md` §6.1 (A1–A4).
> **Executor dự kiến:** **T1 (Claude Code / Sonnet 5) hoặc T2-Sol** — auth là security-critical, thuộc vùng T1 theo `docs/devops-brief.md` §7; chủ chọn lúc giao. · **Effort:** high · **Skill gợi ý:** `security-review` (T1, chạy trên diff trước khi merge) · **MCP cần:** (không)
> *Lý do: code sai ở đây không hiện ra ở demo — nó hiện ra khi bị khai thác. Ưu tiên đúng > nhanh.*

## Bối cảnh (đọc trước, đừng bỏ qua)

Đọc `CLAUDE.md` + **toàn bộ `docs/auth-brief.md`** (quyết định đã khép 2026-07-20: Authlib, login-only OIDC, allowlist env, bảng `session`, cookie đặc tả §2) + `docs/frontend-brief.md` §5 (bẫy OAuth redirect trong PWA iOS — *test máy thật để sau, không thuộc task này*).

Phạm vi task = **đăng nhập/đăng xuất + guard**, tức phần 2a–2c. **Private unlock (Argon2id, TTL 15′) và bộ luật AI R1–R7 KHÔNG thuộc task này** — chúng cần UI riêng + tầng AI chưa tồn tại; sẽ là task sau.

**Việc của CHỦ trước khi chạy task — ✅ XONG 2026-07-21:**
- [x] Google Cloud Console: project `microSched`, Auth Platform **External / Testing**, OAuth client Web `microSched web`, scope chỉ `openid email profile`, branding + authorized domain `microsched.fly.dev`.
- [x] Đặt `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `ALLOWED_EMAILS` / `OAUTH_STATE_SECRET` vào `.env` local + `fly secrets set` — giá trị thật không bao giờ qua chat/PR. Executor code bằng **tên biến + giá trị mock**, không cần biết giá trị thật.

> **⚠️ ĐẢO SO VỚI BẢN ĐẦU — đọc kỹ:** bản gốc ghi *"path callback do agent đặt"*. **Không còn đúng.** Chủ đã đăng ký sẵn **đúng hai** redirect URI trên Console:
> - `https://microsched.fly.dev/auth/callback`
> - `http://localhost:8000/auth/callback`
>
> → Path callback **cố định là `/auth/callback`**, executor **không được tự đặt tên khác**. Đặt khác = Google trả `redirect_uri_mismatch`, và sửa phải vào Console (việc của chủ, không phải của executor).

**Ma trận email để test (giá trị thật nằm ở `.env` của chủ — không ghi vào repo public, xem `devops-brief.md` §1 threat model):**

| Vai | Là Google test user? | Trong `ALLOWED_EMAILS`? | Dùng để chứng minh |
|---|---|---|---|
| Email chính | ✓ | ✓ | login thành công, tạo session |
| Email phụ #1 | ✓ | ✓ | allowlist nhận nhiều hơn một email |
| Email phụ #2, #3 | ✓ | ✗ | **qua được cổng Google, bị cổng app từ chối** |

Chủ đã thêm **4 email làm Google test user**, trong đó **2 nằm trong `ALLOWED_EMAILS`**. Cặp còn lại tồn tại để test đúng tầng: nếu dùng một email ngẫu nhiên chưa phải test user thì **Google** chặn trước, allowlist của app không hề chạy — test đó không chứng minh gì.

## Mục tiêu

Trên `https://<app>.fly.dev/`: bấm "Đăng nhập bằng Google" → về app với session sống trong bảng `session`; email ngoài allowlist bị từ chối sạch sẽ; mọi `/api/*` (trừ healthz + auth) đòi session.

## Phải làm

1. **Authlib OIDC login-only** (scope `openid email profile` — không refresh token): route `GET /auth/login` (redirect Google, có `state`) + `GET /auth/callback` (verify → lấy email).
2. **Allowlist**: email ∈ `ALLOWED_EMAILS` (env, so sánh chuẩn hóa lowercase) — sai thì trả trang từ chối, **không tạo session**, không có "trang đăng ký".
3. **Session theo auth-brief §2**: token ngẫu nhiên ≥ 256-bit entropy (`secrets`), **DB chỉ lưu hash** (SHA-256), cookie `HttpOnly + Secure + SameSite=Lax` chứa token thô; TTL **rolling 60–90 ngày**: mỗi request hợp lệ cập nhật `last_seen_at` + gia hạn `expires_at` (chọn con số cụ thể trong khoảng đã chốt, ghi vào PR). `private_until` để NULL — cột đã có từ 006, task này không đụng.
4. **Guard**: dependency `require_session` áp cho mọi router `/api/*` trừ `/api/healthz` + `/auth/*`. Trả 401 JSON cho API.
5. **Logout**: `POST /auth/logout` xóa row session + clear cookie.
6. **Cron bearer (auth-brief §5)**: dependency `require_cron_token` đọc `Authorization: Bearer` so với secret env — tạo sẵn (kèm test), endpoint jobs thật sẽ dùng sau.
7. **FE tối thiểu**: gọi API bằng credentials cùng origin; nhận 401 → hiện màn login (nút "Đăng nhập bằng Google" = link `/auth/login`); đăng nhập rồi → hiện email + nút logout. Không router, không state phức tạp.
8. **Tests (pytest)**: allowlist đúng/sai · token lưu dạng hash (row trong DB không chứa token thô) · guard chặn khi thiếu/expired session · rolling TTL gia hạn · cron bearer đúng/sai. OAuth với Google mock ở ranh Authlib — không gọi Google thật trong CI.
9. **Ghi nhận**: `agent-tasks/README.md` trạng thái 007; note có ngày vào `auth-brief.md` (mục *"Cập nhật khi: code auth phát hiện khác giả định"*) nếu thực tế lệch giả định nào (vd Testing-mode).

## KHÔNG được làm

- **Không** làm private unlock / Argon2id / R1–R7 (task sau). **Không** thêm scope Google nào khác. **Không** refresh token.
- **Không** tự chế crypto/random (chỉ `secrets` + `hashlib`/thư viện chuẩn); **không** log token/cookie/secret ra console, log, hay message lỗi.
- **Không** nới allowlist hay thêm chế độ "dev bypass auth" nào — kể cả sau flag.
- **Không** đổi thiết kế session (vd chuyển JWT/signed-cookie) — đã chốt và có lý do trong auth-brief §2; muốn khác → DỪNG, escalate T1.
- **Không** dùng `SessionMiddleware` (hay bất kỳ signed-cookie nào) làm **session đăng nhập**. ⚠️ Bẫy cụ thể: Authlib thường cần Starlette `SessionMiddleware` để giữ `state`/`nonce` **trong lúc handshake OAuth** — đó là vai duy nhất của nó, và là vai của `OAUTH_STATE_SECRET`. Cookie đó **phải chết ngay sau callback**. Session đăng nhập là **opaque token + row trong bảng `session`** (auth-brief §2), không liên quan. Hai thứ này trông giống nhau trong code và **sai kiểu này vẫn demo chạy ngon** — nên phải tách rõ; gộp chúng lại = vi phạm §2, DỪNG và escalate.
- Giả định nào trong auth-brief §1 (⚠️ Testing mode) sai khi build → **DỪNG, ghi nhận, escalate** — đừng tự đổi kiến trúc auth để "cho chạy được".
- **Không** commit secret. **Không** rewrite history.

## Acceptance (kiểm chứng được)

- [ ] Localhost: login email chủ → vào app, thấy email hiển thị; row session trong DB có `token_hash` (không phải token thô).
- [ ] Login bằng **email phụ #2/#3** (là Google test user, KHÔNG trong allowlist — xem ma trận trên) → từ chối, **không** có row session mới. *Phải dùng đúng loại email này; email lạ bị Google chặn trước, không test được allowlist.*
- [ ] Cookie đúng flags (kiểm DevTools: HttpOnly, Secure, SameSite=Lax).
- [ ] Sau khi callback xong, **cookie state của Authlib không còn tồn tại** (DevTools) — chỉ còn đúng cookie session. Chứng minh hai cơ chế đã tách, không gộp.
- [ ] `/api/*` không cookie → 401; sau logout → 401 (row đã xóa).
- [ ] `pytest` bộ test mục 8 pass; CI xanh; gitleaks sạch.
- [ ] Flow chạy được trên `https://<app>.fly.dev` (redirect URI prod đúng).

## Bàn giao

Branch **`feat/007-auth-oidc-session`** → PR vào `develop`. PR ghi: con số TTL đã chọn, path callback (để chủ điền Console), các test đã chạy + output. Người merge = chủ sau khi T1 review kỹ diff security. Commit message tiếng Việt *tại sao*, kèm `Co-Authored-By:` của agent thực thi. **Sau khi merge: walking skeleton hoàn thành** — trang thật trên Fly có login Google.
