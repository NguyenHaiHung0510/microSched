# 011b — QA product cho medication reminder, Web Push và scheduler

> **Trạng thái: DRAFT — owner đã cho phép thực thi ngày 2026-08-15; chưa có
> acceptance nào được coi là PASS.** Đây là product-QA contract bổ sung cho
> implementation `agent-tasks/011b-medication-reminder-webpush.md`. Nó không
> tự bật production timer/Web Push và không thay thế production cutover runbook.
>
> **Executor đề xuất:** T3 QA + owner handoff iPhone vật lý · **Model/effort:**
> Luna/high · **Viewport bắt buộc:** 390×844 và 1280×800 · **Target production:**
> `https://microsched.fly.dev`.

## 0. Mục tiêu, dữ liệu và boundary

Spec này nghiệm thu hành vi người dùng end-to-end của nhắc thuốc và nhắc
subscription hết hạn: đăng ký thiết bị, privacy-safe payload, dispatch durable,
retry/idempotency, notification click, confirmation, timer exact-time, UI và
iPhone. Đây là coverage ở product layer; test startup receipt thuần metadata
vẫn thuộc `agent-tasks/011e-cron-observability-receipts.md`.

Dữ liệu luôn synthetic:

- tracker/group/subscription chỉ dùng prefix `QA011B_` + UUID ngẫu nhiên;
- `reminder_text` là câu giả không chứa tên người, thuốc thật, liều, bệnh, địa
  chỉ, email, account, endpoint push, cookie, token hoặc secret;
- push provider là fake/local adapter hoặc endpoint test được owner cho phép;
  không gửi Web Push tới thiết bị/người thật trong local/CI;
- PIN, nếu cần cho private fixture, là **dev-only mock credential** sinh ephemeral
  trong test memory. Không ghi literal PIN (kể cả PIN được cung cấp trong prompt)
  vào file, log, screenshot, PR, report hay snapshot;
- report chỉ gọi tài khoản production là “allowlisted account”, không ghi email.

Không thuộc scope:

- CRUD tracker/entry/dashboard của 011a, subscription/F6 của 011c;
- outbox/cache/persistent service-worker replay của 017; spec này chỉ xác nhận
  online confirmation boundary và handoff exact endpoint cho 017;
- startup `cron_timer_started`/`queue_loaded` đơn lẻ của 011e;
- thêm external scheduler, GCS, cron endpoint production, API public reload,
  `Notification.actions`, hoặc dependency mới ngoài implementation contract;
- production activation chỉ vì test/local/CI PASS.

## 1. Product invariants

### W-01 — Đăng ký thiết bị và capability

1. Khi session hợp lệ bật reminder, iOS Safari tab thường bị chặn với hướng dẫn
   cài PWA Home Screen; Chrome desktop tab thường vẫn đi được luồng permission.
2. `Notification.requestPermission()` denied hiển thị hướng dẫn, không spin/retry
   vô hạn; granted phải đợi `navigator.serviceWorker.ready`, lấy VAPID qua
   `GET /api/push/vapid-public-key`, chuyển base64url thành `Uint8Array`, rồi
   `POST /api/push/subscribe` với endpoint/p256dh/auth.
3. Endpoint không phải `https`, loopback, private/link-local, `.internal` hoặc
   DNS rebind target bị `422`; endpoint hợp lệ upsert theo unique endpoint, không
   tạo row/device duplicate khi user bật lại.
4. `DELETE /api/push/subscribe` chỉ xoá đúng endpoint synthetic; lỗi tạm thời
   của provider không xoá subscription.
5. Chỉ sau subscription thành công mới lưu `reminder_time`/`reminder_text`.
   Tracker không phải `health + event` không có toggle one-tap và không tạo reminder
   bằng cách lách API.

### W-02 — Payload và privacy

Với cùng `dispatch_id` ổn định, kiểm cả tracker public/private và subscription:

- payload title/body/url là JSON metadata tối thiểu; medication URL đúng
  `/reminder-confirm?dispatch=<id>`;
- subscription URL đúng `/subscription?highlight=<subscription-id>`;
- private tracker không có `tracker.name`, ciphertext, private text, body detail
  hoặc subscription name; fallback là generic safe text;
- public tracker chỉ dùng `reminder_text` đã chủ chọn hoặc public name theo
  contract; subscription gắn parent private cũng generic;
- `event.data` null/JSON hỏng trong service worker vẫn hiện fallback notification,
  không throw silently;
- log, DB row, response, screenshot và notification không chứa endpoint, VAPID
  private key, cookie, auth token hay synthetic private marker ngoài fixture cần
  kiểm; report chỉ ghi digest/ID đã redact.

### W-03 — Durable dispatch và response-lost

Cho mỗi `(subject_type, subject_id, dispatched_on)`:

1. Hai workers/tabs gọi cùng occurrence tạo đúng một `reminder_dispatch` row nhờ
   unique key/row lock; `dispatch_id` không đổi.
2. `pending` với `attempt_count < 4` tăng attempt durable trước network; crash
   trước commit được recovery bằng cùng occurrence/id.
3. `SENT` ≥1 subscription thành công → `sent`; không device hoặc chỉ dead 404/410
   → `no_device`; mixed dead + temporary giữ `pending` và cùng id.
4. Temporary 5xx, timeout 20s, network exception không xoá subscription và retry
   cùng dispatch; dead 404/410 mới xoá endpoint.
5. Attempt thứ 4 trả exhausted/manual-required, không gửi thêm. Không coi liveness
   HTTP hay log queue là proof delivered.

### W-04 — Confirmation idempotency

1. Notification body click mở `/reminder-confirm?dispatch=<id>`; không có action
   button `✓` làm đường chính trên iOS.
2. Route chỉ đọc dispatch; client tạo `entry_id` và `occurred_at` một lần, giữ
   nguyên body khi network retry/private unlock; không gọi generic create-entry.
3. Hai thiết bị/tap cùng dispatch với entry IDs khác nhau tạo tối đa một Entry,
   cùng `confirmed_entry_id`, lần sau trả `created=false`.
4. Dispatch không tồn tại → `404`; subject subscription → `409`; tracker deleted,
   wrong kind/input mode → `409`; private tracker locked → `403` code
   `PRIVATE_UNLOCK_REQUIRED` và zero Entry/confirmation.
5. Unlock rồi retry đúng body; network offline giữ màn hình + retry. Offline
   durable queue/reconnect receipt là handoff bắt buộc cho 017, không claim ở spec
   này.
6. Session hết hạn giữ `return_to=/reminder-confirm?dispatch=<id>` trong signed
   OAuth state; absolute `https://evil.example`, `//evil.example` và scheme-like
   input về `/`, không open redirect.

### W-05 — Subscription expiry và rollback

- Expiry reminder chỉ dùng `subscription_expiry_lead_days` allowlist, default
  hiện hành 3, biên theo 011c; không đọc generic `app_setting` có thể làm lộ
  private PIN hash/throttle.
- Chỉ subscription active, parent tracker còn tồn tại, chưa canceled/deleted và
  `expires_on >= occurrence_on` được schedule; subscription notification không tự
  tạo Entry.
- Body private generic; body public đúng label/days-left theo ngày Việt Nam.
- Tắt feature/rollback không tạo external scheduler hoặc duplicate dispatcher;
  production rollback là deploy flag false theo cutover runbook, không xoá row
  pending và không giả “đã gửi”.

## 2. Scheduler acceptance (011d product boundary)

Đây là phép đo product behavior của timer, không lặp startup logging của 011e.
Dùng injected clock/fake DB/fake push transport ở local/CI; không sleep theo thời
gian thật trừ lane production được owner cho phép.

### S-01 — Một máy, một timer, nhịp đúng

1. Chứng minh production topology chỉ một Fly machine/process và một
   `CronTimer`; không có external scheduler/HTTP polling owner thứ hai.
2. Khi `ENABLE_INPROCESS_CRON=false`, app không tạo timer/task/repository/event,
   không phát reminder. Khi true mà thiếu DB/VAPID/implementation dependency,
   production fail-fast, không queue rỗng “xanh giả”; local thiếu DB chỉ no-op theo
   contract.
3. Tracker dùng exact `reminder_time` theo `+07:00`; subscription dùng đúng
   07:00 `+07:00`; không lượng tử hoá slot và không dùng UTC date.
4. Heap rỗng chờ event, không poll DB; mutation reminder schedule chỉ đánh thức
   sau commit, rollback không reload. Không thêm DB polling/health timer dưới 3
   phút. Các backoff 30s → 2m → 10m ở S-02 là retry của một occurrence đã claim,
   không phải poller.
5. Polling/harness cadence của toàn task tuân 3/6/10/15/20 rồi mỗi 10 phút; terminal
   event/error có thể wake ngay. Đây là cadence của QA/harness, không phải giấy
   phép thêm DB poll ngắn vào sản phẩm.

### S-02 — Missed run, recovery, retry

1. Occurrence chưa claim quá grace 15 phút bị bỏ đúng occurrence và schedule kế
   tiếp; trong grace được xử lý một lần.
2. Pending row đã claim nhưng process crash được rehydrate trong recovery window
   24 giờ, giữ `dispatch_id`, `attempt_count`, `occurrence_on`; row quá hạn hoặc
   exhausted giữ lại và phát manual-required receipt, không âm thầm xoá.
3. Temporary dispatch retry cùng row/id theo `30s → 2m → 10m`, tối đa 4 attempts
   tổng cộng; attempt 4 không có retry. Mỗi push network call timeout 20s và không
   giữ DB transaction/row lock qua network.
4. Sau `SENT`, `NO_DEVICE` hoặc exhausted, occurrence ngày kế tiếp vẫn được xếp;
   một subject lỗi không chặn subject kế tiếp. Tất cả datetimes aware +07:00.

### S-03 — Manual trigger và no production activation

Local/dev-test có thể dùng test-only internal trigger hoặc gọi dispatcher fixture
để kiểm W-02–W-04. Route này:

- không xuất hiện hoặc bị từ chối ở production;
- không nhận `CRON_TOKEN`, không gọi qua browser production, không thành fallback
  scheduler và không thay integration test gọi service nội bộ;
- không cần thêm dependency/scheduler nào.

Trước mọi production push/timer action, phải có owner authorization dated riêng
cho activation, exact deploy SHA, `db=up`, one-machine receipt, VAPID/fixture
approval và rollback plan. Nếu thiếu bất kỳ mục nào, chỉ chạy production
read-only/locked surface và ghi `CHƯA VERIFY ĐƯỢC`; không tự đặt
`ENABLE_INPROCESS_CRON=true`, không subscribe thiết bị thật, không gửi push thật.

## 3. Service worker, UI và iPhone

### 3.1 Bản build thật

Chạy `npm run build`, inspect `dist/sw.js` và serve preview/production build với
service workers **allow**. Không dùng `serviceWorkers: 'block'` để tick PWA behavior.
Kiểm bốn URL:

- `/auth/login` và `/api/*` đi tới server, không bị SPA fallback nuốt;
- `/reminder-confirm?dispatch=...` và `/subscription?highlight=...` trả app shell,
  rồi app gọi API đúng route.

InjectManifest phải giữ `NavigationRoute` denylist auth/api, listener `push`
fallback khi data null/hỏng và `notificationclick` focus/navigate/openWindow.
Browser `page.route`/`route.fulfill` chỉ là unit/UI harness; không được coi là
real service-worker or delivery acceptance.

### 3.2 Viewport and accessibility matrix

Chạy normal/loading/permission-denied/sending/network-lost/retry/success/private
unlock/error/empty/long copy ở 390×844 và 1280×800. Đo:

- primary/retry/confirm/tab/close hit area ≥44×44 CSS px, không horizontal overflow;
- text 4.5:1, large text 3:1, non-text border/focus/status ≥3:1;
- focus visible, dialog keyboard order/close, no hover-only action;
- toast/error không chứa private content; title/body/microcopy không hứa guaranteed
  delivery.

### 3.3 Physical iPhone handoff

Owner/T3 phải chạy trên iPhone vật lý được cho phép:

1. Cài PWA vào Home Screen, xác minh standalone và service-worker controller;
2. cấp permission cho synthetic app, bật một tracker health/event với
   `QA011B_` reminder; không dùng dữ liệu thuốc thật;
3. nhận đúng một push synthetic, mở thân notification (không tìm action button),
   xác minh route dispatch, private-safe text và confirm outcome;
4. reload/focus/network loss theo khả năng thiết bị, retry không nuốt dispatch;
5. chụp ảnh crop nội dung, không để lộ bookmark/tab/avatar/account/notification
   của app khác. Ghi OS/Safari/PWA mode, không ghi email/PIN.

Không nhận được push trên iPhone là `CHƯA VERIFY ĐƯỢC` hoặc `FAIL` theo triệu
chứng đã quan sát, không thay bằng Chromium emulation và không suy ra từ CI.

## 4. Ma trận lane executable

| Lane | Cách chạy/fixture | Receipt bắt buộc | Giới hạn |
|---|---|---|---|
| L0 domain/unit | `cd backend; uv run pytest -m "not pg" tests/test_reminder_domain.py tests/test_cron_timer.py tests/test_cron_disabled_mode.py tests/test_push_api.py` | payload privacy, state machine, clock/backoff/no-op | không chứng minh DB/real SW/iPhone |
| L1 PG throwaway | `cd backend; uv run pytest tests/test_reminder_domain.py tests/test_cron_timer.py tests/test_cron_disabled_mode.py`; sau đó `uv run pytest -m pg tests/test_push_api.py` với DB local, synthetic roles/env, fake push | unique dispatch, confirm race, settings allowlist, recovery rows | không dùng Neon production; VAPID/endpoint thật cấm |
| L2 frontend build/browser | `cd frontend; npm test; npm run build; npx playwright test e2e/reminder-confirm.spec.ts` ở mobile + desktop; thêm production preview lane với SW allow | UI error/retry/deep-link, build SW route, 390×844/1280×800 | mocked `page.route` không chứng minh backend/push |
| L3 CI | `Backend checks`, `Frontend checks`, `Frontend e2e`, `Migration QA`, `Production dependency check`, `Repository hooks` theo workflow hiện hành | reproducible code/static/PG gates | CI/docs không là product acceptance |
| L4 production read-only | `GET /api/readyz`, assert JSON field `commit` exact SHA + `db=up`; verify one machine/process; inspect safe logs | deploy/cutover precondition, no-secret observability | no activation/delivery claim |
| L5 physical iPhone | owner-approved PWA + synthetic push/fixture | standalone permission/click/confirm visual | no real data or credential artifact |

L1 phải dùng một outer `try/finally`: tạo DB/env/fixture, chạy test, cleanup
fixture/container/process, rồi mới restore env/cache và kết luận. Nếu cleanup có
lỗi, vẫn phải log lỗi đó và chạy postcheck exact container/process/port; không được
để cleanup error skip privacy or idempotency verdict.

## 5. Observability, rollback và privacy evidence

### 5.1 Safe receipts

Kiểm structured metadata ở timer/dispatcher, không payload:

- startup/queue receipts và safe counts thuộc 011e;
- product lane cần thấy reload-after-commit, due/dispatch outcome (`sent`,
  `temporary_failure`, `no_device`, `exhausted`), retry/manual-required, stale or
  degraded và stable redacted subject kind/ID nếu contract cho phép;
- không log tracker/subscription name, reminder text, private ciphertext, endpoint,
  VAPID key, cookie, bearer/PIN hoặc full provider response;
- healthz chỉ liveness; readyz commit/db receipt không chứng minh timer delivery.

### 5.2 Rollback

Runbook rehearsal ở local/CI phải chứng minh: tắt flag/deploy rollback dừng timer
không tạo scheduler thứ hai; pending rows vẫn còn và manual state rõ; restore
config/env/service-worker fixture; notification/DB cleanup không bỏ qua postcheck.
Production rollback/activation chỉ do owner theo dated note; không viết secret hay
PIN vào rollback file.

### 5.3 Artifact rules

Report append-only có exact HEAD/status, browser/OS/build SHA, lane, command/URL,
raw output và nhãn `OBSERVED`/`INFERRED`. Mỗi W-01…W-05 và S-01…S-03 phải có
`PASS/FAIL/SKIP/CHƯA VERIFY ĐƯỢC`; failure có severity + file:line/selector,
expected/observed metric. Screenshot 390×844, 1280×800, iPhone (nếu có) crop
trước khi lưu, checksum trước khi đọc comment, không chứa account/PIN/cookie,
private marker, endpoint thật hay app khác.

Mỗi guard quan trọng có RED→GREEN proof: tạm gỡ idempotency unique path,
privacy fallback, same-dispatch retry, SW denylist hoặc timer disabled gate trong
throwaway; thấy test đỏ đúng lý do; restore và chạy xanh. Không commit phá guard.

## 6. Không trùng coverage đã có

- `agent-tasks/011b-medication-reminder-webpush.md` là implementation/domain
  contract; file này là user-visible product matrix, executable local/CI/
  production/iPhone và limits.
- `agent-tasks/011e-cron-observability-receipts.md` sở hữu startup/queue structured
  receipt; file này chỉ dùng receipt đó làm dependency và nghiệm thu dispatch,
  retry, confirm, UI và physical delivery separately.
- `agent-tasks/011a-qa-tracker-slice.md` sở hữu tracker CRUD/dashboard; file này
  chỉ kiểm reminder-specific trigger, payload and confirm boundary.
- `agent-tasks/011c-qa-subscription.md` sở hữu subscription/F6 UI; file này kiểm
  expiry notification URL/body/scheduling, không lặp renewal form.
- `agent-tasks/017-qa-offline-outbox.md` sở hữu persistent cache/outbox/real-SW
  offline replay; file này dừng ở online confirmation và ghi handoff, không tick
  offline acceptance thay 017.
