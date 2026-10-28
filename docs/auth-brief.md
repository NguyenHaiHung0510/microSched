# Auth, session và private contract

Ứng dụng có một Owner, public trên Internet. Threat model hiện hành nằm ở [security baseline](security-brief.md); không mô hình hóa khách hàng multi-tenant hoặc Owner cố phá app của mình. External content, stolen session, CSRF, crash và unintended actions vẫn có thể gây hại.

## Login và session

Google OAuth/OIDC login-only (`openid email profile`), Authlib, verified identity và allowlist server-side. Không có public signup/password-login thay thế. Lỗi identity/allowlist phải fail closed; không đưa identifier thật vào URL lỗi/log/fixture. Thêm Calendar OAuth scopes là grant riêng, không suy từ quyền login.

Cookie login chứa opaque random token, DB chỉ giữ token digest; HttpOnly/Secure/SameSite=Lax theo production settings. Server-side session có rolling90days; logout/thu hồi invalidates session. Cookie OAuth handshake riêng `ms_oauth_state`, TTL300s và clear sau callback; không dùng signed handshake cookie làm login session. APP_ENV production thiếu OAUTH_STATE_SECRET từ chối khởi động; local fallback không nới production guard.

Source: [oauth](../backend/app/web/oauth.py), [auth router](../backend/app/web/routers/auth.py), [session store](../backend/app/core/sessions.py), [settings](../backend/app/core/settings.py), [main](../backend/app/main.py).

## Private display gate

PIN đúng 6 ASCII digits, Argon2id m=19456KiB/t=2/p=1. PIN chỉ mở cổng hiển thị/authz, **không** dùng làm encryption key/KDF input. Master encryption key vẫn app-held, ngoài DB/repo.

Unlock có TTL cứng36phút, không gia hạn theo activity. Throttle toàn cục: sai lần10 →5phút,20 →8phút,36 →18phút rồi reset theo implementation. Session rolling TTL khác private TTL. Hết hạn/manual lock phải che và purge private surface/draft/cache theo contract; không biến private unlock thành đổi key.

Source: [PIN](../backend/app/core/private_pin.py), [private router](../backend/app/web/routers/private.py), [domain gate](../backend/app/domain/private_gate.py). Private flag và money-display toggle có ý nghĩa riêng.

## AI × private — R1–R7

Đây là policy ceiling đã được chấp nhận, giữ nguyên ý nghĩa khi sắp xếp tài liệu. Nó không claim mọi năng lực PRIVATE đã được Mimi triển khai hoặc cấp quyền. [Mimi STANDARD hiện hành](mimi/README.md) giới hạn Task tools nonprivate.

| Rule | Boundary | Contract |
|---|---|---|
| **R1** | Một cổng duy nhất (read) | Session locked → mọi tool của agent filter `is_private` tại **"tầng đọc sạch dùng chung"** (một chỗ, không rải điều kiện); unlocked → AI thấy private y như UI. TTL relock áp cho AI y hệt màn hình. |
| **R2** | KHÔNG lật luật index bền | Giữ nguyên luật encryption review: *đã mã hóa ⇒ không embed, không tsvector* — lý do là **rò nghĩa at-rest trên Neon**, không liên quan session mở/đóng. Thay thế: khi unlocked, agent có tool **runtime search** — giải mã tập private + scan trong process theo từng query, không index bền. Khả thi vì quy mô đo thật (~49 note/<1MB toàn bộ, private là tập con) → mili-giây; private phình hàng nghìn bài → nâng cấp in-memory index dựng-lúc-unlock (2 chiều). |
| **R3** | Route provider | Request có private trong context ⇒ ép **`zdr` + no-train cho TOÀN BỘ cascade** của request đó (escalate vẫn giữ ràng buộc); **loại model thuộc lớp buộc-retention** (vd lớp "Covered" 30-ngày của Claude — đã ghi encryption review). Private đã vào hội thoại → các lượt sau mang nó trong history → cả đoạn còn lại route zdr. **Nói thẳng trade-off:** zdr là *cam kết hợp đồng* của provider, không phải bảo đảm toán học — đây là mức rủi ro chủ chấp nhận để AI đọc sâu. |
| **R4** | Transcript theo cờ | Message sinh ra trong lúc unlocked mang `is_private` (tinh thần K11 mở rộng xuống message tầng-1) → **che khỏi lịch sử chat khi locked**. Thiếu luật này private mode tự thủng qua transcript. Mã hóa at-rest của message thì tầng-1 đã lo (encryption review). |
| **R5** | Background AI public-only | Job cron (embed, insight tương lai, nhắc nhở) không có session → **không bao giờ thấy private**, by construction. Giữ rạch ròi: **mã hóa ≠ private** — cột tiền mã hóa nhưng không private → job/dashboard/AI vẫn đọc qua tầng giải mã bình thường. |
| **R6** | Client cache | Response chứa private **không persist** vào IndexedDB offline-cache (loại khỏi persistQueryClient) — private chỉ sống trong RAM tab đang mở, không nằm lại trên đĩa điện thoại sau khi khóa. |
| **R7** | Write-tools (Bước 2) | Đối xứng R1: agent chỉ ghi vào private khi unlocked; confirm + audit như đã chốt; `audit_log.payload` chỉ marker cho field mã hóa (đã chốt encryption review). "Ở private ghi được cả public" áp cho AI y như cho chủ. |

Private trong conversation history kéo theo privacy/routing contract của các lượt sau; provider ZDR là cam kết dịch vụ, không phải bảo đảm toán học. Không tạo persistent private semantic indexes hoặc export transcript chỉ vì session đang mở. [Outbox](reference/offline-outbox.md) giữ riêng tradeoff của already-admitted private pending payload; đó không phải quyền persist private query responses.

Không thay auth/privacy/encryption/permission behavior trong một docs cleanup. [Reading gates](verification/reading-gates.md) và actual source/tests là reference cho implementer. Runtime/config/account/device acceptance cần bằng chứng riêng.
