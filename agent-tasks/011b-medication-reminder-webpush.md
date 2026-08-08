# 011b — Nhắc thuốc + nhắc hết hạn sub: hạ tầng Web Push + Dispatcher

> **Trạng thái: DRAFT — viết bởi T1 (Opus 5) 2026-08-01, phối hợp trực tiếp với chủ (không tự quyết
> một mình).** Đã qua phản biện **T3** (`gemini-3.1-pro-high`) + **T2 Codex**; T1 kiểm tay từng
> finding, sửa các finding thật và ghi rõ chỗ T2 kết luận đúng nhưng lý do/phạm vi sai. Chưa được chủ
> duyệt.
>
> **📝 2026-08-06 — chủ duyệt gộp 2 finding QA 011a vào lô này** (xem §4.4): hai vấn đề UI toàn app
> (touch target tab nav + dialog, và non-text contrast của `border-input`) phát hiện ở QA 011a
> (`agent-tasks/011a-qa-results.md`) được xử lý chung với 011b thay vì một PR riêng. Các acceptance
> tương ứng được bổ sung vào §7.
>
> **📝 Cập nhật cùng ngày, sau khi `011a` được viết: `011` tách làm BA lô, không phải hai.**
> `011a` = `tracker_group`/`tracker`/`entry` + lưới ghi + dashboard A1–A4/F1–F5
> (`agent-tasks/011a-tracker-capture-dashboard.md`). `011c` = entity `subscription` + luồng gia hạn
> + F6 + `app_setting` + seam định tuyến (**đã viết 2026-08-01**:
> `agent-tasks/011c-subscription-renewal-settings.md`). **Thứ tự thi công: `011a` → `011c` → `011b`**
> — file này nhắc cả thuốc lẫn sub, mà phần nhắc sub (§3.4 điểm 4) cần `subscription` đã tồn tại;
> làm cuối thì không phải ship một nửa rồi quay lại. Trong file này, mọi tham chiếu tới CRUD
> tracker/entry là `011a`; mọi tham chiếu tới `subscription`/F6/`app_setting` là `011c`.

## 0. Vì sao tách khỏi `011a`, và vì sao file này viết trước

`tracking-brief.md` §12 đã chốt mô hình dữ liệu (tracker thường + `reminder_time`/`reminder_text`,
đã nằm sẵn trong `models.py:339-340` + migration `0001` — **không cần migration cho hai cột này**).
Cái CHƯA từng được thiết kế là **cơ chế bắn nhắc nhở thật**: web push chưa tồn tại một dòng code nào
trong repo, và hạ tầng cron hiện tại (`devops-brief.md` §10) chỉ có **một** job cố định 20:00.

`011a` (CRUD tracker/entry + dashboard) và `011c` (subscription + F6 + `app_setting`) là phần
**cơ học**: mirror `tasks.py`/`notes.py`, phần lớn quyết định đã nằm sẵn trong schema và trong chính
`tracking-brief.md`. `011b` (file này) là phần **có phát sinh quyết định thiết kế mới** trong chính
phiên này (giới hạn iOS, notification, confirmation) — đúng loại việc đáng dùng nốt cửa sổ Opus còn
lại. Viết trước, chấp nhận file tham chiếu vài đường ống của `011a` chưa tồn tại.

**Phạm vi file này:** hạ tầng Web Push (VAPID, subscription, service worker) + nhắc
thuốc (tracker có `reminder_time`) + nhắc sắp hết hạn subscription (`tracking-brief.md` §9, §11 —
**cùng một đường ống**, không xây hai lần).

## 1. Quyết định đã chốt trong phiên này (2026-08-01, chủ + T1)

### 1.1 LOẠI BỎ hoàn toàn Google Cloud Scheduler 3-khe & lượng tử hoá (Quyết định lại)

Chủ đã chọn **011d (in-process async cron timer) là scheduler production duy nhất**. Google Cloud Scheduler đã bị loại bỏ hoàn toàn và không còn là fallback hay mode vận hành được hỗ trợ.
Do đó, việc xây dựng cron HTTP endpoint và thuật toán gán khe (`assign_slot`) trong 011b là **throwaway scope** (công cốc) và không được thi công.

**Chốt:**
- 011b **KHÔNG** làm external cron endpoint, **KHÔNG** làm lượng tử hoá `assign_slot`. Giờ nhắc (`reminder_time`) là exact time.
- 011b chỉ tập trung xây dựng domain logic: `ReminderDispatcher.dispatch_item(subject_type, subject_id, scheduled_time)`.
- Việc lập lịch và trigger hàm dispatch này sẽ do **011d** (in-process timer) đảm nhận.
- Để 011b có thể nghiệm thu (QA) độc lập khi 011d chưa merge, có thể phơi `POST /api/dev/trigger-dispatch` **chỉ ở local/dev-test** để T3 kích hoạt thủ công. Route này phải vắng mặt hoặc từ chối ở production, không dùng `CRON_TOKEN`, không là fallback scheduler và không thay thế integration test gọi dispatcher nội bộ.

### 1.3 Giới hạn thật của iOS — noti KHÔNG thể có nút ✓ trên lock-screen

**Đã tra sống 2026-08-01** (do chủ dùng iPhone XS Max, iOS 18.7.9): Safari/iOS **không hỗ trợ mảng
`actions` của Notification API** — nút hành động tuỳ biến trên banner chỉ có ở Chrome/Firefox
([Safari notification actions bị bỏ qua — WebKit forum thảo luận](https://developer.apple.com/forums/tags/wwdc2022-10098),
tổng hợp tại
[MagicBell — PWA iOS limitations](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide)).
Push nói chung hoạt động từ iOS 16.4+ **chỉ khi app đã cài vào Home Screen** (standalone), không chạy
từ tab Safari thường — thứ này app đã đủ điều kiện (`manifest.display: 'standalone'`,
`vite.config.ts:35`). Safari 18.4 thêm "Declarative Web Push" (noti không cần service worker để dựng
nội dung) nhưng đây là tối ưu độ tin cậy, **không** cấp thêm khả năng nút hành động — không cần dùng
ở v1, giữ một luồng imperative Push API (`push` event + `showNotification`) chạy đúng trên mọi trình
duyệt mục tiêu, đỡ phải bảo trì hai nhánh.

**Hệ quả — sửa lại giả định "1 chạm trên lock-screen" từ đầu phiên:** không có nút ✓ trực tiếp trên
banner. Cơ chế thay thế, **tái dùng nguyên xi triết lý "ghi ngay + hoàn tác" đã chốt ở
`tracking-brief.md` §8.1** (không phát minh luồng UX mới):

1. Chạm vào noti (thân noti, không phải nút) → `notificationclick` trong service worker → mở/focus
   PWA tại route `/reminder-confirm?dispatch=<reminder_dispatch.id>`.
2. App tải route đó → gọi endpoint confirmation **idempotent theo dispatch** (§3.6) → chuyển sang màn
   ghi chính, hiện toast 10 giây. Cảm giác vẫn là "ghi ngay"; khác biệt kỹ thuật là hai thiết bị không
   thể tạo hai Entry.
3. Nếu session hết hạn ⇒ login bình thường nhưng phải giữ `return_to=/reminder-confirm?dispatch=...`;
   login xong route chạy tiếp. Nếu private gate khoá ⇒ unlock riêng tư rồi retry (§3.6), không bypass.
   > 🔴 **`return_to` hiện KHÔNG tồn tại ở bất kỳ đâu — T2 bắt 2026-08-01, và việc này thuộc `011b`.**
   > Kiểm tay: UI luôn trỏ `/auth/login` cứng (`App.tsx:59`) và callback OAuth luôn
   > `RedirectResponse(url="/")` (`auth.py:148`). `011c` chỉ dựng seam định tuyến phía client, không
   > đụng auth. Nghĩa là kịch bản thật — noti lúc 8h sáng, session đã hết hạn — sẽ **nuốt mất lượt
   > nhắc**: đăng nhập xong rơi về trang chủ, `dispatch` mất, không ai ghi Entry.
   > ⇒ `011b` phải làm, **đủ ba lớp**: (a) client đính `return_to` (đường dẫn **tương đối**, bắt đầu
   > bằng đúng một `/`, **không** `//` và không có scheme/host) khi chuyển sang login; (b) server
   > giữ nó trong **OAuth `state` đã ký**, không phải query trần — `state` là chỗ duy nhất không bị
   > sửa giữa đường; (c) callback validate lại **same-origin, đường dẫn tương đối** trước khi
   > redirect, không khớp ⇒ về `/`. Test bắt buộc: `return_to=https://evil.example` và
   > `return_to=//evil.example` đều **phải** rơi về `/` (open-redirect là lỗ kinh điển của đúng
   > tính năng này).
4. Nếu offline ⇒ Dexie queue **request confirmation** (dispatch id + stable entry id + thời điểm tap),
   không queue generic create-entry. Hành động vẫn chạy trong tab app, không fetch trần từ service
   worker; auth/private gate vẫn do server thi hành khi outbox flush.

Đây là phát hiện làm **đơn giản hoá** bài toán so với lo ngại ban đầu: không cần thiết kế đường xác
thực riêng cho hành động chạy trong service worker, vì hành động thật chạy trong tab app đã mở.

### 1.4 Idempotency — bảng `reminder_dispatch`

Timer 011d có bounded retry và recovery row `pending` sau restart; dev trigger chỉ phục vụ QA có thể gọi lại cùng occurrence. Không được bắn push hai lần. Bảng mới, dùng chung cho cả nhắc thuốc lẫn nhắc sub:

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | UUIDv7 PK | B1 |
| `subject_type` | `TEXT CHECK IN ('tracker', 'subscription')` | phân biệt hai nguồn nhắc |
| `subject_id` | `UUID NOT NULL` | id của `tracker` hoặc `subscription`; không FK cứng (subject có thể bị xoá mềm, vẫn muốn giữ log) |
| `dispatched_on` | `DATE NOT NULL` | ngày Việt Nam (`+07:00`), không phải UTC — cùng quy ước K14 (`subscription.started_on`/`expires_on`) |
| `status` | `TEXT CHECK IN ('pending','sent','no_device')` | default `pending`; retry dùng lại chính row/id này |
| `attempt_count` | `INTEGER NOT NULL DEFAULT 0 CHECK >= 0` | quota delivery bền: tăng một lần cho mỗi lượt dispatch có gửi Web Push, không reset qua restart |
| `last_attempt_at` | `timestamptz NULL` | quan sát retry/stuck pending |
| `confirmed_entry_id` | `UUID NULL UNIQUE FK entry(id)` | chỉ tracker-reminder dùng; stable link chống hai thiết bị/tap tạo hai Entry |
| `confirmed_at` | `timestamptz NULL` | thời điểm server chốt confirmation; bất biến sau lần đầu |
| `created_at` | `timestamptz` | B2; không cần `updated_at`/`deleted_at` — chỉ hai cột confirmation đổi đúng một lần |

`UNIQUE (subject_type, subject_id, dispatched_on)`. Bảng này vừa là claim chống hai cron chồng nhau,
vừa là log "đã nhắc ngày nào", vừa cấp **dispatch id ổn định** cho confirmation.

> 🔴 **State machine cuối cùng — sửa qua hai vòng T3 rồi T2/T1.** Bản đầu giữ row dù lỗi tạm ⇒ mất
> nhắc cả ngày (T3 bắt). Bản vá đầu xoá row để retry ⇒ retry sinh **dispatch id mới**; nếu push cũ thật
> ra đã tới thiết bị nhưng response mạng bị mất, notification cũ trỏ tới row đã xoá và không confirm
> được. Sau khi T2 bắt confirmation phải dùng dispatch id, T1 kiểm chéo mới lộ ra khe này. **Không xoá
> row khi retry nữa.**
>
> 1. `INSERT ... ON CONFLICT DO NOTHING` row `status='pending'`, rồi `SELECT ... FOR UPDATE` đúng unique
>    key. Hai cron chồng nhau tuần tự trên cùng row; không có hai lượt gửi đồng thời.
> 2. `status IN ('sent','no_device')` ⇒ đã terminal, bỏ qua. `pending` với `attempt_count < 4` ⇒
>    claim **một delivery attempt**: trong transaction ngắn, tăng `attempt_count` đúng một lần và set
>    `last_attempt_at`, rồi mới gửi tới mọi subscription. Crash sau claim nhưng trước network có thể
>    tiêu hao một attempt thay vì reset quota sau restart — đây là đánh đổi cố ý để retry luôn bị chặn.
>    `pending` có `attempt_count >= 4` ⇒ tuyệt đối không gửi nữa, trả `EXHAUSTED` cho 011d ghi biên lai
>    manual handling.
> 3. **≥1 `SENT`** ⇒ `status='sent'`, commit, trả outcome `SENT`.
> 4. **0 `SENT` + ≥1 `TEMPORARY_FAILURE`** ⇒ **giữ `status='pending'` và cùng `id`**, commit rồi
>    trả outcome có cấu trúc `TEMPORARY_FAILURE` (kèm `dispatch_id`, `attempt_count`) cho timer 011d
>    re-enqueue theo bounded backoff. Một response-lost có thể bắn push trùng, nhưng mọi bản trùng mang
>    **cùng dispatch id**, nên §3.6 vẫn chỉ tạo một Entry.
> 5. **0 `SENT` + chỉ `DEAD_SUBSCRIPTION`, hoặc không có subscription ngay từ đầu** ⇒
>    `status='no_device'`, commit, trả outcome `NO_DEVICE`; retry không cứu được.
>
> Crash trước commit để row `pending`; retry dùng lại cùng id. Crash sau push nhưng trước commit có thể
> gửi trùng — chiều đánh đổi đã chọn: thà noti trùng còn hơn mất, và confirmation-idempotency làm phần
> dữ liệu không trùng. **Không giữ transaction DB mở trong khi gọi mạng nếu implementation không thể
> chịu lock dài:** được phép claim/commit `pending` trước rồi acquire advisory lock theo dispatch id
> quanh lượt gửi; nhưng không được đổi id hay cho hai worker gửi song song.

> **Hợp đồng reliability chung 011b → 011d — không để executor tự chọn số.** Một occurrence có tối đa
> **4 delivery attempts tổng cộng**: lần đầu + 3 retry. `attempt_count` là nguồn sự thật durable và
> không được reset theo process/heap/redeploy; 011d chỉ dùng nó để tính lần retry kế tiếp, 011b tự chặn
> thêm như lớp phòng thủ thứ hai. Sau attempt thứ 1/2/3, 011d đặt lại cùng row theo **30 giây → 2 phút
> → 10 phút**; attempt thứ 4 không có retry. Mỗi Web Push network attempt bị bọc trong
> `asyncio.timeout(20)` (hoặc timeout có hiệu lực tương đương nếu SDK là synchronous); timeout map thành
> `TEMPORARY_FAILURE`, không log response/payload và không giữ transaction/row lock trong lúc chờ mạng.
> Đây thay retry/deadline của GCS cho reminder, nhưng **không hứa guaranteed delivery**: pending quá
> recovery window hoặc hết 4 attempts phải để lại row/receipt cho manual handling, không âm thầm xoá.

> 🔴 **Dispatch-id cũng là khoá idempotency của hành động XÁC NHẬN — thêm sau T2.** Chống cron gửi
> lặp **không** tự chống Entry lặp: cùng notification có thể bị tap hai lần, hoặc cùng dispatch được
> gửi tới iPhone + desktop rồi tap ở cả hai; nếu URL chỉ mang `tracker` + `slot`, mỗi tab sinh UUIDv7
> mới và `011a` hợp lệ hoá cả hai. Vì vậy payload thuốc phải mang `dispatch_id`, URL là
> `/reminder-confirm?dispatch=<id>` (không còn `tracker`/`slot`), và API confirmation khoá chính dòng
> dispatch đó (§3.6). `confirmed_entry_id` là nguồn sự thật: một dispatch thuốc tạo **tối đa một
> Entry**, kể cả offline, retry, nhiều thiết bị. Notification subscription-expiry không tạo Entry qua
> đường này — nó mở màn subscription để chủ xử lý ở ngoài, đúng S2.

## 2. Migration mới — kiểm `ls backend/alembic/versions/` để lấy đúng số, ĐỪNG tin con số ở đây

Tại thời điểm viết file này head là `0004` — nhưng `011a` (nếu thi công trước) hoặc phiên `010`
(song song) có thể đã thêm `0005`/`0006`. File mới: hai bảng `push_subscription` + `reminder_dispatch`.

```python
# push_subscription — một dòng / một thiết bị đã cấp quyền noti (đơn user, đa thiết bị)
id: UUIDv7 PK
endpoint: TEXT NOT NULL, UNIQUE          # URL endpoint của push service — khoá tự nhiên của 1 thiết bị
p256dh: TEXT NOT NULL                    # public key phía trình duyệt, base64url
auth: TEXT NOT NULL                      # auth secret, base64url
user_agent: TEXT NULL                    # chỉ để chủ tự nhận ra "cái nào là điện thoại" khi dọn tay
created_at, last_seen_at: timestamptz    # last_seen_at cập nhật mỗi lần gửi push THÀNH CÔNG

# reminder_dispatch — xem bảng §1.4; ngoài UNIQUE(subject_type, subject_id, dispatched_on):
status: TEXT NOT NULL DEFAULT 'pending' CHECK IN ('pending','sent','no_device')
attempt_count: INTEGER NOT NULL DEFAULT 0 CHECK >= 0
last_attempt_at: timestamptz NULL
confirmed_entry_id: UUID NULL UNIQUE FK entry(id)
confirmed_at: timestamptz NULL
```

**Không `user_id`** — app một-người-dùng, `session` đã là nguồn sự thật duy nhất về "ai"; phân biệt
theo **thiết bị** (endpoint), không theo người. `push_subscription` không mã hoá — `endpoint`/khoá
public không phải nội dung nhạy cảm theo posture B-hẹp (`tracking-brief.md` §6), và cần `WHERE` được
để dọn theo `endpoint` khi push service trả 410.

Áp bằng tay (`cd backend && uv run alembic upgrade head`, `NEON_MIGRATOR_URL`), xác minh bằng
`information_schema.columns` — luật cứng `CLAUDE.md`, không có ngoại lệ cho migration "nhỏ".

## 3. Backend

### 3.1 VAPID keys

Sinh một lần bằng `py-vapid` (thêm vào `backend/pyproject.toml`): `public_key` + `private_key` (cả
hai là **Fly secret / `.env` local**, không commit). Contact email bắt buộc
theo chuẩn VAPID (`mailto:`, để push service liên hệ nếu app bị lạm dụng gửi spam — không áp dụng
thực tế cho app 1-người-dùng nhưng chuẩn đòi có).

**Public key phục vụ qua API, KHÔNG embed lúc build.** *(Sửa 2026-08-01 sau phản biện T3 — bản trước
ghi "embed vào frontend lúc build".)* Thêm `GET /api/push/vapid-public-key` (sau `require_session`,
cùng router §3.5) trả `{"public_key": "..."}`. Ba lý do: build-time embed khoá cứng frontend vào
**một** cặp khoá, nên local dev và production buộc phải dùng chung khoá hoặc phải build hai bản;
xoay khoá thành một lần build lại + deploy lại thay vì đổi một secret; và `VITE_*` env đi vào bundle
tĩnh nên giá trị cũ còn nằm trong service worker đã precache của thiết bị cũ. Khoá công khai gọi qua
mạng mỗi lần bật nhắc là một request/đời-thiết-bị — rẻ hơn cả ba vấn đề trên.

### 3.2 `app/domain/reminder.py` — logic payload

(Thuật toán `assign_slot` đã bị loại bỏ vì dùng exact time theo `011d`).
Chỉ giữ lại các hàm thuần tạo lock-screen text dựa trên `subject_type` (tracker/subscription).

### 3.3 `app/domain/push.py` — gửi push, dọn subscription chết

Thư viện `pywebpush`. **Không trả `bool`** — T2 bắt đúng rằng `False` đã xoá mất thông tin mà thuật
toán §1.4 cần. Khai enum/result tường minh:

```python
class PushResult(StrEnum):
    SENT = "sent"
    TEMPORARY_FAILURE = "temporary_failure"
    DEAD_SUBSCRIPTION = "dead_subscription"

async def send_push(subscription: PushSubscription, payload: dict) -> PushResult: ...
```

- Gọi `webpush()` với `vapid_private_key`, bắt `WebPushException`.
- **`410 Gone` hoặc `404 Not Found`** từ push service ⇒ subscription đã chết (trình duyệt tự huỷ, ví
  dụ chủ gỡ-cài-lại PWA) ⇒ `DELETE FROM push_subscription WHERE id = ...` ngay trong cùng lượt, trả
  `DEAD_SUBSCRIPTION`.
- Lỗi khác (mạng, 5xx tạm thời) ⇒ log, trả `TEMPORARY_FAILURE`, **không xoá**.
- Thành công ⇒ cập nhật `last_seen_at = now()`, trả `SENT`.

Dispatcher đếm ba enum riêng. **0 `SENT` + ≥1 `TEMPORARY_FAILURE`** ⇒ giữ row/id ở `pending` và trả
`TEMPORARY_FAILURE` có cấu trúc cho timer 011d retry bounded; **0 `SENT` + chỉ `DEAD_SUBSCRIPTION` hoặc danh sách ban đầu rỗng** ⇒ chuyển
`no_device`. Không suy
nguyên nhân từ việc bảng subscription rỗng *sau* khi gửi — lúc đó không phân biệt được "rỗng từ đầu"
với "vừa dọn hết 410".

### 3.4 `app/domain/dispatcher.py` — Hàm Gửi Notification Nội Bộ

Không tạo HTTP route cron (`/api/cron/reminder`).
Tạo hàm nội bộ `async def dispatch_item(db: AsyncSession, subject_type: str, subject_id: UUID, scheduled_time: datetime)`:

1. `SELECT ... FOR UPDATE` check subject (còn sống không, reminder còn không).
2. Tạo/Claim `reminder_dispatch` (idempotent key).
3. `SELECT` mọi `push_subscription`.
4. Bắn `send_push_notification` (§3.3) qua tất cả các sub.
5. `UPDATE reminder_dispatch` với kết quả (sent, temporary_failure, no_device).
6. Trả outcome có cấu trúc (`SENT`, `TEMPORARY_FAILURE`, `NO_DEVICE`, `SKIPPED`); dispatcher không định nghĩa HTTP status. Dev trigger (nếu có) chỉ là adapter test mapping outcome sang response.

(Optional: `POST /api/dev/trigger-dispatch` chỉ có ở local/dev-test, vắng mặt hoặc từ chối ở production, để test riêng 011b; không dùng làm trigger scheduler.)

### 3.5 `app/web/routers/push.py` — CRUD subscription, sau `require_session`

```
POST   /api/push/subscribe          body {endpoint, keys: {p256dh, auth}, user_agent?}
DELETE /api/push/subscribe          body {endpoint}   — bấm tắt nhắc, hoặc trước khi đăng ký lại
GET    /api/push/vapid-public-key   → {"public_key": "..."}   — §3.1
```

> 🔒 **Validate `endpoint` trước khi lưu — thêm 2026-08-01 sau phản biện T3.** `endpoint` là chuỗi do
> **client gửi lên** và server sau đó tự `POST` tới nó mỗi lần nhắc ⇒ đúng khuôn SSRF: lưu
> `http://169.254.169.254/...` hay `http://localhost:8080/...` thì cron biến thành công cụ gọi vào
> mạng nội bộ của Fly. Luật: chỉ nhận `https://`, host phải phân giải ra **địa chỉ public** — chặn
> loopback, link-local (`169.254.0.0/16`), private ranges (RFC1918), `.internal` (Fly dùng
> `*.internal` cho mạng riêng). Sai ⇒ `422`.
>
> **Ghi trung thực mức nghiêm trọng:** T3 chấm CRITICAL; ở đây **thấp hơn thế** — endpoint này nằm
> sau `require_session` + allowlist Google một-người-dùng, và khoá VAPID **private** không bao giờ rời
> server (chỉ JWT đã ký đi ra). Kẻ tấn công phải đăng nhập được bằng tài khoản chủ trước đã, lúc đó
> đã có thứ đáng giá hơn. Nhận bản vá vì nó **rẻ** (một hàm ~15 dòng + test), không vì nó chặn một
> đường tấn công đang mở — phòng thủ theo lớp, đúng threat model social-engineering ở
> `devops-brief.md`.

`POST` idempotent theo `endpoint` (`ON CONFLICT (endpoint) DO UPDATE SET p256dh=…, auth=…,
last_seen_at=now()`) — trình duyệt có thể trả subscription cũ y hệt khi gọi lại `subscribe()`, không
được tạo dòng trùng. **Không cần endpoint riêng để "bật nhắc cho tracker X"** — `011b` mở rộng
`TrackerUpdate` của `011a` bằng `reminder_time`/`reminder_text`; chỉ cho set giờ khi
`kind='health' AND input_mode='event'`, ngược lại `422`. `push_subscription` là hạ tầng thiết bị,
tách khỏi cấu hình từng tracker.

### 3.6 `POST /api/reminder-dispatch/{dispatch_id}/confirm` — đúng một Entry / occurrence

Router mới nằm dưới `protected_api` (`require_session`), body:

```json
{"entry_id": "<client UUIDv7>", "occurred_at": "2026-08-01T19:02:11+07:00"}
```

`occurred_at` là **thời điểm tap do client chụp**, không phải lúc outbox cuối cùng gửi được — offline
qua đêm vẫn phải ghi đúng lúc chủ bấm. Bắt buộc tz-aware và reuse validator của `011a`.

Transaction:
1. `SELECT reminder_dispatch WHERE id=:id AND subject_type='tracker' FOR UPDATE`; không thấy ⇒ `404`.
2. Nếu `confirmed_entry_id IS NOT NULL` ⇒ đọc Entry đó kể cả soft-delete và trả `200
   {created:false, entry:...}`; **không restore, không tạo dòng mới**. Undo trước đó là quyết định của
   chủ, tap lặp không được tự đảo Undo.
3. Load Tracker vật lý từ `subject_id`, rồi áp **write gate của `011a`**. Tracker private mà gate đang
   khoá ⇒ `403` với machine code `PRIVATE_UNLOCK_REQUIRED`, message generic không có tên/id tracker;
   không set confirmation. Không được bypass gate chỉ vì request tới từ notification.
4. Xác nhận tracker còn sống, `kind=health`, `input_mode=event`; sai ⇒ `409` generic (cấu hình đã đổi
   sau khi push được gửi), không tạo Entry.
5. Gọi đúng helper create-entry của `011a` với UUID/timestamp từ body, rồi set
   `confirmed_entry_id=entry.id`, `confirmed_at=now()`, commit. Hai thiết bị đua sẽ tuần tự ở
   `FOR UPDATE`; thiết bị thua đi nhánh 2.

API create Entry trực tiếp của `011a` vẫn idempotent theo `entry_id`; endpoint này thêm idempotency
**theo occurrence**. Cả hai lớp đều cần: outbox có thể gửi lại cùng body, còn hai thiết bị có hai UUID
khác nhau.

Frontend gặp `PRIVATE_UNLOCK_REQUIRED` ⇒ mở flow `PrivateGate` hiện có, giữ nguyên body trong outbox,
sau unlock retry **cùng `dispatch_id` + `entry_id` + `occurred_at`**. Nếu offline thì cứ queue; không
có "unlock offline" và không tự ghi public. Notification body/name vẫn generic theo §3.2 nên trước
unlock không rò nội dung.

## 4. Frontend

### 4.1 Đổi chiến lược `vite-plugin-pwa`: `generateSW` → `injectManifest`

`vite.config.ts:15-44` hiện dùng `generateSW` (Workbox tự sinh toàn bộ service worker, không cho chèn
code). Xử lý `push`/`notificationclick` bắt buộc tự viết service worker. Đổi:

```ts
VitePWA({
  strategies: 'injectManifest',
  srcDir: 'src',
  filename: 'sw.ts',
  injectManifest: { /* giữ globPatterns/globIgnores hiện có, chuyển vào đây */ },
  registerType: 'autoUpdate',
  manifest: { /* không đổi */ },
})
```

File mới `frontend/src/sw.ts`: giữ nguyên phần precache (Workbox `precacheAndRoute(self.__WB_MANIFEST)`
— placeholder bắt buộc của `injectManifest`, mất placeholder này = build lỗi ngay, không lỗi ngầm) +
thêm:

```ts
self.addEventListener('push', (event) => {
  // ⚠️ event.data CÓ THỂ null — push service cho phép gửi push RỖNG, và bản nháp trước
  // (`event.data?.json()` rồi dùng thẳng `data.title`) sẽ ném TypeError trong luồng service
  // worker: không có màn hình nào hiện lỗi, chỉ là "hôm nay không thấy nhắc". Fallback bắt buộc.
  let data: { title?: string; body?: string; url?: string } = {}
  try { data = event.data?.json() ?? {} } catch { data = {} }
  event.waitUntil(self.registration.showNotification(data.title ?? 'microSched', {
    body: data.body ?? 'Bạn có một lời nhắc.',
    icon: '/microsched.svg',
    data: { url: data.url ?? '/' },   // '/reminder-confirm?dispatch=<reminder_dispatch.id>'
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(self.clients.matchAll({ type: 'window' }).then((clients) => {
    const existing = clients.find((c) => 'focus' in c)
    if (existing) { existing.navigate(event.notification.data.url); return existing.focus() }
    return self.clients.openWindow(event.notification.data.url)
  }))
})
```

> 🔴 **`navigateFallbackDenylist` KHÔNG tồn tại dưới `injectManifest` — kiểm tay 2026-08-01 sau
> phản biện T2, và đây là bẫy nặng nhất của §4.1.** Option đó thuộc `GeneratePartial`
> (`workbox-build/build/types.d.ts:286`, trong khối `178-348`), còn
> `InjectManifestOptions = BasePartial & GlobPartial & InjectPartial & …` (`types.d.ts:487`) **không
> gồm `GeneratePartial`**. Nghĩa là "giữ nguyên option cũ" ở `vite.config.ts:22` là **không làm được**
> — nó sẽ bị bỏ qua (im lặng, hoặc lỗi type), và cùng lúc `/auth/*` + `/api/*` mất hàng rào. Đúng
> cái sự cố mà comment ngay tại `vite.config.ts` mô tả: nút đăng nhập câm.
> ⇒ **Chuyển sang code trong `sw.ts`**, không phải config:
> ```ts
> import { createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
> import { NavigationRoute, registerRoute } from 'workbox-routing'
> precacheAndRoute(self.__WB_MANIFEST)
> registerRoute(new NavigationRoute(createHandlerBoundToURL('index.html'), {
>   denylist: [/^\/auth\//, /^\/api\//],
> }))
> ```
> Nghiệm thu phải kiểm **bốn** đường trên bản build thật: `/auth/login` (đi tới server, không bị SW
> nuốt) · `/api/*` · và hai deep link `/reminder-confirm`, `/subscription` (phải trả `index.html`).

**Rủi ro thi công thật cần đo tay trước khi tin spec này**: `injectManifest` đổi cách Workbox build
service worker — cần chạy `npm run build` xong kiểm `dist/sw.js` có đúng cả route-caching cũ (nay là
`NavigationRoute` + denylist viết tay theo hộp trên) lẫn hai listener mới. Đây thuộc "thử trước khi code" mà chủ đã nói
sẽ làm — ghi vào Definition of Done, không chặn viết spec này.

### 4.2 Route `/reminder-confirm` — ghi ngay, idempotent theo dispatch

> 🔴 **Vá 2026-08-01 (T1, lúc viết `011c`) — file này giả định một router chưa từng tồn tại.**
> Đo tay cùng ngày: `App.tsx:104-125` chuyển màn bằng `useState`, `package.json` **không có**
> `react-router`. Nghĩa là cả hai deep link của lô này (`/reminder-confirm?dispatch=…` ở đây và URL
> màn subscription ở §3.2) không có đường nào để tới, và `navigate('/')` dưới kia không có hàm nào
> để gọi. Lỗ nằm **giữa** `011a` (không cần route) và file này (cần, nhưng tưởng đã có) — không spec
> nào nhận.
> **Đã vá bằng cách giao cho `011c`** (`agent-tasks/011c-subscription-renewal-settings.md` §5.1):
> seam tự viết ~40 dòng ở `frontend/src/lib/route.ts` (`usePath()` + `navigate()` trên
> `history.pushState`/`popstate`), **không thêm `react-router`**; `App.tsx` rẽ nhánh theo path.
> `011c` chạy trước lô này nên tới đây seam đã có sẵn. **Việc của `011b` chỉ là thêm một nhánh
> `/reminder-confirm`** — không dựng router, không đổi cơ chế tab. Nếu vì lý do nào đó `011c` bị bỏ
> qua, **dừng lại và báo T1**, đừng tự dựng router thứ hai.
> Backend đã sẵn sàng cho tải nguội: `SPAStaticFiles` trả `index.html` cho path không khớp file
> (`main.py:28-37, 102`) — đã kiểm, không phải giả định. Nhưng §4.1 đổi sang `injectManifest` thì
> phải giữ `navigateFallbackDenylist` như cũ, nếu vỡ thì deep link chết chung với nút đăng nhập.

Component `ReminderConfirm.tsx` đọc **chỉ** `dispatch` từ query; lúc mount sinh một UUIDv7 + chụp
`occurred_at` +07 một lần, giữ ổn định qua mọi render/retry, rồi gọi
`POST /api/reminder-dispatch/{dispatch}/confirm` (§3.6). **Không** gọi thẳng generic create-entry và
không nhận `tracker`/`slot` từ URL — đó là bản nháp trước T2, tạo duplicate khi tap ở hai thiết bị.

- `201 created=true` hoặc `200 created=false` ⇒ `navigate('/')`, hiện cùng toast 10 giây. Với
  `created=false`, toast ghi *"Lần uống này đã được ghi"*; nút Hoàn tác trỏ đúng `confirmed_entry_id`
  server trả về, không trỏ UUID client thua cuộc.
- `PRIVATE_UNLOCK_REQUIRED` ⇒ mở `PrivateGate`; unlock xong retry nguyên request ổn định. Không hiện
  tên tracker trước unlock.
- Dispatch không tồn tại / subject đã đổi/xoá ⇒ toast lỗi generic rồi `/`; không trắng màn hình.
- Offline ⇒ queue **endpoint confirmation này** trong Dexie, không queue generic create-entry. Đây là
  seam bắt buộc để idempotency nhiều thiết bị còn đúng sau reconnect.

> 📝 **2026-08-06 — Ranh giới outbox:** phần offline confirm (queue endpoint confirmation trong
> Dexie + flush sau reconnect) thuộc **`agent-tasks/017-offline-outbox.md`** (hàng đợi ghi toàn
> app). Lô 011b hiện chỉ thi công **PrivateGate + retry** cho confirmation; không dựng Dexie queue
> trong lô này.

Push subscription-expiry dùng URL màn subscription (011c), không mount route này và không tự ghi
Entry — chủ còn phải trả tiền ở ngoài theo S2.

### 4.3 Đăng ký nhắc — nằm trong form sửa tracker của `011a`

Toggle "Bật nhắc nhở" + input giờ chỉ hiện khi tracker `kind='health'` + `input_mode='event'` — đây là
đường duy nhất mà tap notification có thể tạo Entry không cần hỏi thêm field (§3.6/K8). Tracker
finance/money/quantity không hiện toggle; muốn nhắc kiểu khác là scope tương lai, không tạo một push
mà bấm xong chắc chắn `422`. Bật lần đầu (chưa có
`push_subscription` nào trên thiết bị này):
1. **Chỉ trên iOS**, kiểm `window.matchMedia('(display-mode: standalone)').matches` — `false` ⇒ dừng,
   hiện hướng dẫn *"Cài microSched vào Màn hình chính trước khi bật nhắc — Safari không cho web
   thường gửi thông báo"* (đúng giới hạn iOS §1.3, không phải bug).
   > 📝 **Sửa 2026-08-01 sau phản biện T3.** Bản trước bắt điều kiện này cho **mọi** nền tảng. Sai:
   > Chrome/Edge desktop và Chrome Android gửi push được trong **tab thường**, không cần cài PWA — áp
   > chung sẽ từ chối oan đúng cái máy chủ dùng để ngồi làm việc. Điều kiện iOS-only:
   > `/iP(hone|ad|od)/.test(navigator.platform) || (navigator.platform === 'MacIntel' &&
   > navigator.maxTouchPoints > 1)` — nhánh sau bắt iPad iOS 13+ tự nhận là Mac. Nếu không phải iOS
   > ⇒ bỏ qua bước 1, đi thẳng bước 2; `Notification.requestPermission()` tự báo lỗi nếu trình duyệt
   > thật sự không hỗ trợ. Test bắt buộc: cùng luồng bật nhắc chạy được trên Chrome desktop tab
   > thường (chính là môi trường `frontend/e2e/` chạy Playwright — áp luật cũ thì e2e không test nổi
   > luồng này).
2. `Notification.requestPermission()` — `denied` ⇒ hiện hướng dẫn mở lại quyền trong Cài đặt iOS,
   không tự ý thử lại (iOS không cho JS re-prompt sau khi bị từ chối).
3. `granted` ⇒ `GET /api/push/vapid-public-key` (§3.1 — **không** đọc từ `import.meta.env`) →
   `registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey:
   urlBase64ToUint8Array(key) })` → `POST /api/push/subscribe`. `applicationServerKey` nhận
   `BufferSource`, chuỗi base64url phải chuyển sang `Uint8Array` — bỏ bước này thì `subscribe()` ném
   `InvalidCharacterError`, một bẫy kinh điển của Web Push.
4. Chỉ SAU khi có subscription mới `PATCH` `reminder_time`/`reminder_text` lên tracker — tránh trạng
   thái "đã đặt giờ nhắc nhưng không có thiết bị nào để nhắc" mà chủ không biết.

**Nếu `011a` build trước và đã tồn tại form sửa tracker** khi thi công `011b`: chèn đúng khối trên vào
form đó, không tạo màn riêng. **Nếu `011b` bị buộc build trước `011a`** (đảo thứ tự thi công): cần một
form tối giản độc lập chỉ có `reminder_time`/`reminder_text`/toggle, gọi thẳng `PATCH
/api/tracker/{id}` của domain tracker (giả định domain đã tồn tại dù chưa có UI CRUD đầy đủ) — không
nên xảy ra nếu theo đúng thứ tự đề xuất ở §0.

### 4.4 Findings QA 011a gộp vào lô này — UI toàn app (chủ duyệt 2026-08-06)

Hai finding từ QA 011a (lane Chrome MCP production, viewport 390×844) là vấn đề **toàn app, không
riêng tracker** — nên gộp vào 011b xử lý một thể:

1. **Touch target dưới HIG 44px** — thanh tab điều hướng (`Task`/`Ghi chú`/`Lịch`/`Theo dõi`) cao
   **36px** và nút `Đóng` dialog **28×28px**. Đạt WCAG 2.5.8 (≥24px) nhưng dưới target 44px của HIG
   (thiết bị chính của chủ là iPhone — `ui-brief.md`). Yêu cầu: nâng **tab nav lên ≥44px** và nút
   `Đóng` dialog lên **≥44×44px** (giữ hit area 44px, không nhất thiết phình visual). Tab nav nằm ở
   app shell dùng chung mọi màn — phải verify không vỡ layout ở 390px (flex/scroll nếu cần).
2. **Non-text contrast của `border-input`** — viền card + viền input (`#e5e7eb` trên nền `#ffffff`)
   ratio **1.3:1**, dưới WCAG 1.4.11 (≥3:1). **Nợ tương tự đã ghi ở README mục 016** (viền input
   1,32:1 và viền badge throttled 1,17:1, chưa fix) — xử lý **một lần cho cả hai**, đổi token border
   sang màu đạt ≥3:1 trên nền trắng, rồi soát các surface dùng cùng token để không bỏ sót. Luật
   `ui-brief.md` §6.2: **chỉ sửa token trong `index.css`, không hardcode màu ở component.**

Phạm vi gộp: chỉ 2 mục trên + regression tương ứng. Không kéo thêm finding QA khác vào lô này; mọi
thứ khác từ `011a-qa-results.md` không chặn merge.

## 5. Loại bỏ Google Cloud Scheduler

Không tạo, vận hành hoặc giữ bất kỳ Google Cloud Scheduler job nào cho microSched, gồm cả reminder lẫn heartbeat. Cơ chế GCS đã bị **xoá hoàn toàn** ở lô `011d`. Owner phải xác nhận không còn scheduler external nào gọi app trên GCP.

Reminder chỉ do `011d` schedule in-process. Không có fallback external; khi `ENABLE_INPROCESS_CRON=false`, production không phát reminder cho tới khi cutover được thực hiện có kiểm soát.
## 6. Không được làm

- Không quét DB theo chu kỳ ngắn hơn cửa sổ idle 5 phút của Neon (`cost-brief.md` §7 — bất biến toàn
  dự án, sự cố 22/07).
- Không tái sử dụng Google Cloud Scheduler, cron endpoint external hay scheduler external khác cho reminder/heartbeat; 011d là owner duy nhất của reminder schedule.
- Không dùng mảng `actions` của Notification API làm đường chính — không chạy trên iOS (§1.3); có thể
  thêm như progressive enhancement cho Chrome/Android **sau**, không phải v1.
- Không xây đường xác thực riêng cho `notificationclick` — nó chạy trong ngữ cảnh app đã đăng nhập
  (§1.3 điểm 3), thêm cơ chế riêng là giải một vấn đề không tồn tại.
- Không tạo bảng `push_subscription` gắn `user_id` — app một người dùng, phân biệt theo thiết bị.
- Không xoá `push_subscription` khi push lỗi tạm thời (mạng, 5xx) — chỉ xoá khi push service xác nhận
  410/404 (§3.3).
- Không nhắc sub hết hạn ở mọi thời điểm — chỉ 07:00 (+07:00) (do `011d` gọi), tránh nhắc sai giờ.

> 📝 **2026-08-06 — CHỦ CHỐT: giờ nhắc sub = 07:00 (+07:00) (JC3), thay 19:00; xem
> `agent-tasks/011d-inprocess-cron-timer.md`.**
>
> 📝 **2026-08-06 — JC docs:** JC2 (renew anchor) / JC3 (giờ nhắc sub 07:00) / JC4 (privacy
> toast) sẽ được ghi chi tiết khi luồng UI (Kuhn) báo cáo — **placeholder: [chờ báo cáo Kuhn]**.
- Không dùng `tracker.name` làm fallback payload khi tracker private; `reminder_text` vẫn được phép vì
  đã khoá là bề mặt public do chủ tự viết (§3.2).
- Không cho `/reminder-confirm` gọi generic create-entry trực tiếp; bắt buộc đi endpoint confirmation
  khoá `reminder_dispatch` (§3.6), nếu không hai thiết bị tạo hai Entry.
- Không thêm entity lịch con trong v1; thuốc nhiều lần/ngày dùng một tracker/mỗi lần uống (§1.2).
- Không dùng `zoneinfo` cho phép tính "hôm nay VN" — cùng lý do offset cố định đã ghi ở `010a` §2.6.

## 7. Nghiệm thu — test tự động + ba phép đo tay

**Test bắt buộc, mỗi bài phải biết đỏ khi gỡ luật:**


  ba URL thật đều match ít nhất một tracker fixture.
- `PushResult` + dispatch state: sent/temp/dead; hỗn hợp dead+temp giữ **cùng row/id** ở `pending` +
  endpoint 5xx; chỉ dead hoặc bảng rỗng chuyển `no_device`; ≥1 sent chuyển `sent`. Retry/crash phải
  reuse đúng dispatch id.
- Private payload: tracker có `reminder_text` dùng đúng text public; thiếu text thì **không chứa
  tracker.name** và dùng generic; public thiếu text mới fallback name. Subscription có parent private
  cũng không chứa `subscription.name`.
- Hai request confirm cùng dispatch nhưng hai `entry_id` khác nhau (mô phỏng hai thiết bị, chạy đồng
  thời) ⇒ đúng một Entry + cùng `confirmed_entry_id`; gửi lại qua outbox ⇒ vẫn một dòng.
- Private gate khoá ⇒ confirm `403 PRIVATE_UNLOCK_REQUIRED`, 0 Entry, 0 confirmation; unlock rồi retry
  cùng body ⇒ một Entry.
- Tracker reminder không phải health/event ⇒ PATCH `422`; safety-net cron skip + log, không gửi.
- Build `injectManifest` giữ `navigateFallbackDenylist`; push payload rỗng vẫn hiện fallback, không ném.
- **§4.4-1 (touch target):** Playwright đo thật trên viewport 390×844 — tab nav height ≥44px, nút
  `Đóng` dialog ≥44×44px hit area, `scrollWidth <= innerWidth` (0 overflow ngang); test biết đỏ khi
  ai đó hạ kích thước xuống dưới ngưỡng.
- **§4.4-2 (contrast):** test token — `border-input` (và token viền badge throttled của 016) đạt ≥3:1
  với nền trắng; verify bằng đo giá trị token trong `index.css` + tính ratio (không chỉ "nhìn đậm
  hơn"); các component dùng token cũ được soát hết.

**Ba phép đo tay đã nói trước với chủ, không chặn khoá spec nhưng chặn merge:**

1. **Test thật trên iPhone XS Max / iOS 18.7.9 của chủ**: cài PWA → xin quyền → nhận 1 push thật →
   bấm vào → xác nhận mở đúng route. Nên làm **trước** khi viết code phần push thật, ngay sau khi
   `injectManifest` build được (§4.1) — rẻ nhất là test cái khung rỗng trước khi lắp logic nhắc thuốc
   lên trên.
2. **`injectManifest` có giữ đúng hành vi `navigateFallbackDenylist` hiện tại không** — nếu vỡ, nút
   đăng nhập câm lại y hệt sự cố đã từng gặp và được ghi lại trong chính file `vite.config.ts`.
3. Ngưỡng "sắp hết hạn 3 ngày" thuộc `app_setting`; **`011c`** phải tạo CRUD + seed/default cho nó
   (`tracking-brief.md` §11 S2 nói "hằng số `app_setting`, chưa cần per-sub"). `011a` cấm chạm
   `app_setting`; bản nháp trước giao việc này cho `011a` là mâu thuẫn scope, T2 đã bắt và sửa ở đây.
   📝 **2026-08-01: `011c` đã viết xong** (`agent-tasks/011c-subscription-renewal-settings.md` §4.4)
   — key là `subscription_expiry_lead_days`, mặc định 3, biên 0–30, và **CRUD `app_setting` chạy qua
   allowlist hằng số**. Lý do allowlist quan trọng với chính lô này: `private_gate.py:19-21` dùng
   chung bảng đó cho `private_pin` (chứa hash Argon2id của PIN 6 chữ số), `private_unlock_throttle`
   và `private_unlock_ttl_minutes`; một CRUD tổng quát sẽ đẩy hash PIN ra client. Nếu `011b` cần đọc
   thêm bất kỳ setting nào, **thêm key vào allowlist của `011c`**, đừng mở đường đọc tự do.

## 8. Hai judgment call chủ veto được trước khi giao executor

1. **Một tracker = một lần uống hằng ngày** (§1.2), nên thuốc A sáng/chiều là hai tracker cùng group;
   không thêm `tracker_reminder` child ở v1. Đây là cách duy nhất vừa phục vụ toa thật vừa giữ quyết
   định khoá "không entity mới" trong `tracking-brief.md` §12.
2. **Reminder chỉ bật cho health/event** (§3.4/§4.3), vì confirm một chạm không thể tự bịa amount hay
   quantity. Schema vật lý rộng hơn nhưng API/UI v1 cố ý hẹp.

T3 chưa soi hai judgment call này vì chúng phát sinh từ review T2. Trước thi công, chủ chỉ cần veto
nếu muốn *một tracker chứa nhiều lịch*; nếu không, cả hai mặc định được chấp nhận như quyết định v1.
