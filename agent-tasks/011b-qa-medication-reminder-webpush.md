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
- synthetic endpoint được phép tồn tại trong DB fixture throwaway để kiểm natural
  key/upsert/delete; không được echo endpoint đó vào log, report, screenshot,
  response ngoài field contract, hoặc notification payload. VAPID private key,
  cookie và auth token luôn bị cấm ở mọi nơi. Synthetic private marker chỉ được
  xuất hiện trong fixture/response nội bộ cần kiểm, không xuất hiện trong log,
  report, screenshot hay notification; report chỉ ghi digest/ID đã redact.

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

### 3.1 Bản build thật — dedicated real-SW lane

Required-new test contract: `frontend/e2e/reminder-pwa-real-sw.spec.ts` và
`frontend/playwright.qa.config.ts`. Config này phải chạy production build/preview
riêng trên port `4174`, ví dụ web server command
`npm run build && npm run preview -- --host 127.0.0.1 --port 4174`, `baseURL`
`http://127.0.0.1:4174`, `serviceWorkers: 'allow'`, không reuse dev server, và
giữ hai project mobile/desktop. Đây là lane riêng với config hiện hành ở đó
`serviceWorkers: 'block'`; không sửa config CI chung để giả PWA xanh.

Test phải:

1. `GET /` trên bản preview, chờ `navigator.serviceWorker.ready`, assert
   `registration.active` và `navigator.serviceWorker.controller` khác null; nếu
   controller chưa sẵn sàng thì fail/`CHƯA VERIFY ĐƯỢC`, không bỏ qua.
2. Dùng Chromium CDP `ServiceWorker.enable`, capture `registrationId` from
   `ServiceWorker.workerVersionUpdated`, rồi gọi `ServiceWorker.deliverPushMessage`
   cho đúng origin/registration ID với JSON synthetic. Không dùng `page.route`,
   `route.fulfill`, abort giả, mock fetch hay fake `Notification` cho push/delivery.
3. Đọc `registration.getNotifications()` để assert title/body fallback và
   `notification.data.url` đúng dispatch/subscription deep link; ghi receipt
   `push delivered by CDP -> notification observed`.
4. Assert built `dist/sw.js` giữ NavigationRoute denylist: `/auth/login` và
   `/api/*` đi tới server, còn `/reminder-confirm?dispatch=...` và
   `/subscription?highlight=...` trả app shell rồi gọi API. Đây là browser
   request thật trên preview, không fulfill từ test.
5. `notificationclick` phải được kiểm bằng click notification thật trong physical
   iPhone handoff (hoặc browser OS notification nếu runner expose được); Playwright
   không được tự gọi `navigate()` để giả click. Nếu CDP chỉ chứng minh notification
   data mà không expose OS click, receipt phải ghi `CHƯA VERIFY ĐƯỢC` cho click,
   chờ L5; không claim deep-link click chỉ từ `getNotifications()`.

Sau mỗi run, đóng context/browser, unregister service worker trong context,
terminate preview process và assert port `4174` không còn listener. Lỗi cleanup
không được xoá receipt.

Kiểm bốn URL:

- `/auth/login` và `/api/*` đi tới server, không bị SPA fallback nuốt;
- `/reminder-confirm?dispatch=...` và `/subscription?highlight=...` trả app shell,
  rồi app gọi API đúng route.

InjectManifest phải giữ `NavigationRoute` denylist auth/api, listener `push`
fallback khi data null/hỏng và `notificationclick` focus/navigate/openWindow.
Browser `page.route`/`route.fulfill` chỉ dùng cho existing unit/UI harness, không
được coi là real service-worker hoặc delivery acceptance của lane trên.

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
5. đọc và ghi `window.innerWidth`/`window.innerHeight` thật trên iPhone tại mỗi
   phép đo; không gọi đây là `390×844 equivalent` (390×844 chỉ thuộc browser
   emulation lane). Chụp ảnh crop nội dung, không để lộ bookmark/tab/avatar/
   account/notification của app khác. Ghi OS/Safari/PWA mode, không ghi email/PIN.

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

## 5. Mapping acceptance → test/fixture/receipt

Tên bắt đầu bằng **required-new** là contract phải tạo khi thi công; không phải
file/test đã tồn tại và không được báo PASS trước khi có receipt. Tên không có
prefix đó là test/fixture hiện có đã kiểm được ở base.

| ID | Existing hoặc required-new test/fixture | Command/lane | Expected receipt |
|---|---|---|---|
| W-01 | Existing `backend/tests/test_push_api.py::test_validate_push_endpoint_resolves_every_answer`, `::test_validate_push_endpoint_rejects_internal_and_literal_private_targets`, `::test_push_subscription_create_update_and_unsubscribe`; **required-new** `frontend/e2e/reminder-push-product.spec.ts::test_permission_denied_does_not_retry_or_patch_tracker`, `::test_granted_waits_for_controller_and_upserts_endpoint`; **required-new fixture** `frontend/e2e/fixtures/qa011b-push.ts` | `cd backend; uv run pytest -m "not pg" tests/test_push_api.py`; PG test ở L1; `cd frontend; npx playwright test -c playwright.qa.config.ts e2e/reminder-push-product.spec.ts` ở L2 | denied có hướng dẫn và 0 PATCH; granted có controller→VAPID GET→subscribe POST; invalid endpoint `422`; cùng endpoint upsert 1 row; response không echo endpoint |
| W-02 | Existing `backend/tests/test_reminder_domain.py::test_medication_payload_private_tracker_without_text`, `::test_medication_payload_private_tracker_with_text`, `::test_subscription_expiry_payload_private`, `::test_medication_payload_public_tracker`; **required-new** `backend/tests/test_qa_011b_product.py::test_payload_artifact_boundary_allows_fixture_endpoint_only`, `::test_private_payload_has_no_name_or_ciphertext`; **required-new fixture** `backend/tests/fixtures/qa011b_payloads.py` | `cd backend; uv run pytest tests/test_reminder_domain.py tests/test_qa_011b_product.py` ở L0; inspect `caplog`, responses, fake provider payload và fixture DB ở L1 | private/generic body đúng; endpoint chỉ tồn tại trong fixture DB, không log/report/response/notification; VAPID private/cookie/token 0 occurrence; null/malformed push data fallback |
| W-03 | Existing `backend/tests/test_push_api.py::test_dispatch_item_never_sends_concurrently`, `backend/tests/test_cron_timer.py::test_pending_recovery_keeps_dispatch_id_and_backoff`, `::test_dead_pending_rows_are_receipted_not_dropped`, `::test_exhausted_outcome_is_receipted_and_next_day_scheduled`; **required-new** `backend/tests/test_qa_011b_product.py::test_mixed_dead_and_temporary_keeps_pending_same_id`, `::test_response_lost_reuses_dispatch_id`, `::test_attempt_four_emits_manual_required_without_send` | `cd backend; uv run pytest -m pg tests/test_push_api.py tests/test_qa_011b_product.py` ở L1; timer unit ở L0 | one unique row/id; mixed dead+temp pending; response-lost same id; 404/410 delete only dead; attempt 4 no network call + manual receipt |
| W-04 | Existing `frontend/e2e/reminder-confirm.spec.ts` tests F9 same-body retry/network loss and dispatch change; existing PG `backend/tests/test_push_api.py::test_two_devices_confirm_same_dispatch_create_one_entry`, `::test_private_dispatch_requires_unlock_then_accepts_same_body`; existing non-PG `backend/tests/test_auth.py` return-to tests; **required-new** `frontend/e2e/reminder-confirm-product.spec.ts::test_service_worker_click_keeps_dispatch_and_deep_links` | `cd backend; uv run pytest -m pg tests/test_push_api.py`; `uv run pytest -m "not pg" tests/test_auth.py`; existing mocked e2e in L2; real-SW click only L5 if OS notification is observable | 404/409/403 codes exact; two devices one Entry; same body after unlock/retry; relative signed return_to; no generic create; click deep-link receipt separate from route mock |
| W-05 | Existing `backend/tests/test_reminder_domain.py::test_subscription_expiry_payload_private`, `::test_subscription_expiry_payload_days_left_uses_vn_today`, `backend/tests/test_cron_timer.py::test_subscription_candidates_and_lead_change`, `::test_subscription_chain_schedules_next_day_and_retry_backoff`; existing 011c QA owns renewal UI; **required-new** `backend/tests/test_qa_011b_product.py::test_rollback_stops_timer_without_external_scheduler`, `::test_subscription_expiry_never_creates_entry` | `cd backend; uv run pytest tests/test_reminder_domain.py tests/test_cron_timer.py tests/test_qa_011b_product.py`; rollback/manual receipt in L0/L4 rehearsal | allowlisted setting only; active eligible subscriptions only; private generic/public VN label; no auto Entry; rollback leaves pending/manual state and creates no external scheduler |
| S-01 | Existing `backend/tests/test_cron_disabled_mode.py::test_disabled_create_app_does_not_load_or_construct_cron_runtime`, `::test_local_enabled_without_database_starts_as_disabled_noop`, `::test_production_enabled_without_database_still_fails_fast`, `::test_enabled_lifespan_builds_one_timer_task`; existing `backend/tests/test_cron_timer.py::test_empty_heap_waits_without_queries`, `::test_get_session_reload_marker_only_after_commit`; **required-new** `backend/tests/test_qa_011b_product.py::test_one_app_instance_has_one_timer_and_no_external_trigger`; **required-new production receipt command** `fly machines list --app microsched --json` | L0/L1 unit + `fly machines list --app microsched --json` in L4; harness polls at 3/6/10/15/20→10m | one live machine/process; false flag no timer; true missing dependency fail-fast; exact +07:00 times; empty heap no DB polling; reload only post-commit; no second scheduler |
| S-02 | Existing `backend/tests/test_cron_timer.py::test_tracker_due_at_0800_and_2359_boundaries`, `::test_load_snapshot_keeps_occurrences_inside_15_minute_grace`, `::test_pending_recovery_keeps_dispatch_id_and_backoff`, `::test_dead_pending_rows_are_receipted_not_dropped`, `::test_exhausted_outcome_is_receipted_and_next_day_scheduled`, `::test_subscription_chain_schedules_next_day_and_retry_backoff`; **required-new** `backend/tests/test_qa_011b_product.py::test_retry_backoff_is_30s_2m_10m_and_attempt4_terminal` | `cd backend; uv run pytest tests/test_cron_timer.py tests/test_qa_011b_product.py` ở L0/L1 với injected clock, không sleep thật | 15m grace, 24h recovery, same row/id, four total attempts, 20s network timeout; pending/exhausted manual receipt; next day survives failure |
| S-03 | Existing `backend/tests/test_cron_timer.py::test_reload_sink_request_reload`; **required-new** `backend/tests/test_qa_011b_product.py::test_manual_trigger_is_local_only_and_rejected_in_production`; **required-new fixture** `backend/tests/fixtures/qa011b_runtime.py` | `cd backend; uv run pytest tests/test_qa_011b_product.py`; local test-only dispatcher call; production `GET/POST` probe must be read-only and owner-authorized | local trigger calls internal dispatcher only; production route absent/403; no `CRON_TOKEN`, no browser delivery, no external scheduler; no activation without dated owner receipt |

Real-SW mapping: **required-new** `frontend/e2e/reminder-pwa-real-sw.spec.ts::test_push_via_cdp_and_notification_data`, `::test_navigation_denylist_and_deep_link_shell` with **required-new** `frontend/playwright.qa.config.ts` and existing `frontend/src/sw.ts` as built input. Command: `cd frontend; npx playwright test -c playwright.qa.config.ts e2e/reminder-pwa-real-sw.spec.ts`. Lane L2 proves controller, CDP push, `getNotifications()` data, denylist and deep-link shell; OS notification click is L5 unless the runner exposes a real click event. It must never use `page.route`/`route.fulfill`; cleanup must assert preview port `4174` is closed.

## 6. Observability, rollback và privacy evidence

### 6.1 Safe receipts

Kiểm structured metadata ở timer/dispatcher, không payload:

- startup/queue receipts và safe counts thuộc 011e;
- product lane cần thấy reload-after-commit, due/dispatch outcome (`sent`,
  `temporary_failure`, `no_device`, `exhausted`), retry/manual-required, stale or
  degraded và stable redacted subject kind/ID nếu contract cho phép;
- không log tracker/subscription name, reminder text, private ciphertext, endpoint,
  VAPID key, cookie, bearer/PIN hoặc full provider response;
- healthz chỉ liveness; readyz commit/db receipt không chứng minh timer delivery.

### 6.2 Rollback

Runbook rehearsal ở local/CI phải chứng minh: tắt flag/deploy rollback dừng timer
không tạo scheduler thứ hai; pending rows vẫn còn và manual state rõ; restore
config/env/service-worker fixture; notification/DB cleanup không bỏ qua postcheck.
Production rollback/activation chỉ do owner theo dated note; không viết secret hay
PIN vào rollback file.

### 6.3 Artifact rules

Report append-only có exact HEAD/status, browser/OS/build SHA, lane, command/URL,
raw output và nhãn `OBSERVED`/`INFERRED`. Mỗi W-01…W-05 và S-01…S-03 phải có
`PASS/FAIL/SKIP/CHƯA VERIFY ĐƯỢC`; failure có severity + file:line/selector,
expected/observed metric. Screenshot 390×844, 1280×800, iPhone (nếu có) crop
trước khi lưu, checksum trước khi đọc comment, không chứa account/PIN/cookie,
private marker, endpoint thật hay app khác.

Mỗi guard quan trọng có RED→GREEN proof: tạm gỡ idempotency unique path,
privacy fallback, same-dispatch retry, SW denylist hoặc timer disabled gate trong
throwaway; thấy test đỏ đúng lý do; restore và chạy xanh. Không commit phá guard.

## 7. Không trùng coverage đã có

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
