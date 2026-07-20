# 007 — Auth: Google OIDC + allowlist + session server-side

> **Trạng thái:** 📋 TODO (chạy sau 006 — cần bảng `session` + app đã deploy để có redirect URI thật)
> **Executor dự kiến:** **T1 (Claude Code / Sonnet 5) hoặc T2-Sol** — auth là security-critical, thuộc vùng T1 theo `docs/devops-brief.md` §7; chủ chọn lúc giao. · **Effort:** high · **Skill gợi ý:** `security-review` (T1, chạy trên diff trước khi merge) · **MCP cần:** (không)
> *Lý do: code sai ở đây không hiện ra ở demo — nó hiện ra khi bị khai thác. Ưu tiên đúng > nhanh.*

## Bối cảnh (đọc trước, đừng bỏ qua)

Đọc `CLAUDE.md` + **toàn bộ `docs/auth-brief.md`** (quyết định đã khép 2026-07-20: Authlib, login-only OIDC, allowlist env, bảng `session`, cookie đặc tả §2) + `docs/frontend-brief.md` §5 (bẫy OAuth redirect trong PWA iOS — *test máy thật để sau, không thuộc task này*).

Phạm vi task = **đăng nhập/đăng xuất + guard**, tức phần 2a–2c. **Private unlock (Argon2id, TTL 15′) và bộ luật AI R1–R7 KHÔNG thuộc task này** — chúng cần UI riêng + tầng AI chưa tồn tại; sẽ là task sau.

**Việc của CHỦ trước khi chạy task:**
- [ ] Google Cloud Console: tạo OAuth client (app để **Testing mode** — đủ cho login-only, auth-brief §1), redirect URIs cho cả `http://localhost:8000/...` và `https://<app>.fly.dev/...` (path callback do agent đặt, chủ điền theo PR).
- [ ] Đặt `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `ALLOWED_EMAILS` / secret ký state vào `.env` local + `fly secrets set` — giá trị thật không bao giờ qua chat/PR.

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
- Giả định nào trong auth-brief §1 (⚠️ Testing mode) sai khi build → **DỪNG, ghi nhận, escalate** — đừng tự đổi kiến trúc auth để "cho chạy được".
- **Không** commit secret. **Không** rewrite history.

## Acceptance (kiểm chứng được)

- [ ] Localhost: login email chủ → vào app, thấy email hiển thị; row session trong DB có `token_hash` (không phải token thô).
- [ ] Login bằng email ngoài allowlist (chủ dùng account phụ) → từ chối, **không** có row session mới.
- [ ] Cookie đúng flags (kiểm DevTools: HttpOnly, Secure, SameSite=Lax).
- [ ] `/api/*` không cookie → 401; sau logout → 401 (row đã xóa).
- [ ] `pytest` bộ test mục 8 pass; CI xanh; gitleaks sạch.
- [ ] Flow chạy được trên `https://<app>.fly.dev` (redirect URI prod đúng).

## Bàn giao

Branch **`feat/007-auth-oidc-session`** → PR vào `develop`. PR ghi: con số TTL đã chọn, path callback (để chủ điền Console), các test đã chạy + output. Người merge = chủ sau khi T1 review kỹ diff security. Commit message tiếng Việt *tại sao*, kèm `Co-Authored-By:` của agent thực thi. **Sau khi merge: walking skeleton hoàn thành** — trang thật trên Fly có login Google.
