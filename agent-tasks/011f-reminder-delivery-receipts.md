# 011f — Reminder delivery receipts + production diagnostic

> **Trạng thái: DRAFT — owner đã yêu cầu viết spec ngày 2026-08-16; chưa có acceptance nào
> được coi là PASS.** Đây là lô observability/QA nhỏ nối `011b` + `011d` + `011e`. PR spec không
> tự authorize implementation, merge, deploy, production mutation hoặc Web Push thật.

## 0. Vấn đề cần giải quyết và mức bằng chứng hiện có

### OBSERVED — đọc trực tiếp ở base của spec

- `CronTimer` dựng heap từ snapshot rồi ngủ tới đúng `TimerItem.due_at`; heap rỗng chờ event và
  không poll DB. `cron_timer_queue_loaded` hiện có `queue_size` nhưng chưa có `next_due_at`.
- `ReminderDispatcher.dispatch_item()` claim `reminder_dispatch`, tăng `attempt_count` trước network,
  rồi trả `sent | no_device | temporary_failure | exhausted`. Nhánh thành công và `no_device` hiện
  không phát receipt start/finish.
- `POST /api/push/subscribe` hiện trả `201` với `status=created|updated`. `GET /api/subscriptions` là
  domain subscription tài chính, không phải bằng chứng đăng ký Web Push.
- Test hiện có đã khóa heap/recovery/backoff/no-poll và upsert push subscription, nhưng chưa khóa chuỗi
  receipt mới hoặc output diagnostic production aggregate.

### INFERRED — chưa được dùng làm root cause

- Không thấy log ở giờ due có thể chỉ là nhánh `sent`/`no_device` đang im lặng; riêng sự vắng log không
  chứng minh timer chết, handler chưa mount hoặc event loop bị nghẽn.
- Traffic frontend dày là QA debt riêng; chưa có receipt cho thấy nó làm trễ `CronTimer`.
- DevTools force-push thành công chỉ chứng minh service worker/browser/OS ở thiết bị đó, không chứng
  minh backend VAPID/provider hoặc occurrence scheduled đã dispatch.

### CHƯA VERIFY ĐƯỢC

- Production có row thiết bị hợp lệ tại lúc test hay không; exact due item có đi qua dispatcher không;
  provider trả kết quả gì; notification scheduled có hiện và click/confirm được trên OS hay không.

## 1. Mục tiêu và hard boundaries

Sau lô này, một lần nhắc synthetic phải truy được chuỗi an toàn:

`queue next_due_at → dispatch_started → dispatch_finished → aggregate DB state → OS notification → click/confirm`.

Chỉ metadata vận hành được đi vào log/CLI. Lô này **không**:

- thêm minute tick, heartbeat query, DB/product poll, APScheduler/Celery/worker hay scheduler thứ hai;
- đổi heap/sleep exact-time, state machine, retry `30s → 2m → 10m`, network timeout 20s, recovery
  window 24h hoặc giới hạn bốn attempts;
- thêm public/admin/debug HTTP endpoint, cron endpoint hoặc browser route diagnostic;
- thêm migration/schema, đổi push payload/service worker/UI, sửa polling frontend hay Task 017;
- log payload, endpoint, p256dh/auth key, VAPID key, cookie, token, PIN, email/account, tên
  tracker/subscription, `reminder_text`, ciphertext hoặc raw provider response/exception text;
- coi `readyz`, queue load, subscription count hay provider `sent` riêng lẻ là bằng chứng người dùng
  đã nhìn thấy notification.

**Harness cadence:** mọi status poll bắt đầu không sớm hơn phút 3, rồi gần phút
`3/6/10/15/20`, sau đó khoảng 10 phút/lần. Completion/blocker/log-stream event có thể wake ngay vì
không phải poll. Retry `30s/2m/10m` là product backoff của occurrence đã claim, không phải giấy phép
cho harness query liên tục.

## 2. Phạm vi file implementation

Chỉ được sửa/tạo:

- `backend/app/core/cron_timer.py`
- `backend/app/domain/reminder.py`
- `backend/scripts/reminder_delivery_receipt.py` (mới)
- `backend/tests/test_cron_timer.py`
- `backend/tests/test_reminder_domain.py`
- `backend/tests/test_push_api.py`
- `backend/tests/test_reminder_delivery_receipt.py` (mới)

`backend/tests/test_push_api.py` sở hữu PG coverage thật của `ReminderDispatcher` và upsert thiết bị;
chỉ được sửa file này để thêm O-02/R-01 regression, không mở rộng product behavior. Mọi file khác,
đặc biệt router, model, migration, `fly.toml`, workflow, frontend, `agent-tasks/README.md` và Task 017,
nằm ngoài scope. Nếu file scope không đủ, dừng và xin T1/owner sửa spec; không tự mở rộng.

## 3. Contract implementation

### O-01 — `queue_loaded` có deadline kế tiếp

Giữ event và mọi field 011e hiện có, thêm đúng một field:

```text
cron_timer_queue_loaded ... queue_size=<n> next_due_at=<RFC3339-with-offset|none> ...
```

- Heap có item: `next_due_at` bằng `self._heap[0][0].isoformat()` sau khi snapshot thay heap thành
  công; offset phải hiện rõ (production schedule là `+07:00`).
- Heap rỗng: literal `next_due_at=none` để log vẫn parse theo token `key=value`.
- Không query thêm DB và không tạo log tick. Mỗi snapshot thành công vẫn chỉ một receipt.

### O-02 — start/finish cho từng due occurrence

Mỗi item thật sự đi vào dispatcher phát tối đa một cặp:

```text
cron_timer_dispatch_started kind=<tracker|subscription> due_at=<RFC3339> \
  occurrence_on=<YYYY-MM-DD> attempt_count=<0..4> occurrence_ref=<16-lower-hex>
cron_timer_dispatch_finished kind=<tracker|subscription> due_at=<RFC3339> \
  occurrence_on=<YYYY-MM-DD> outcome=<sent|no_device|temporary_failure|exhausted> \
  attempt_count=<0..4> occurrence_ref=<same-ref>
```

- `started` được emit sau durable claim/attempt-count decision và trước Web Push network I/O;
  `attempt_count` là giá trị thật của row cho lượt đó, không đoán từ số vòng loop.
- `finished` chỉ emit sau khi dispatcher có outcome thật; `attempt_count` lấy từ cùng row/result và
  hai event dùng cùng `occurrence_ref`. Các đường terminal đã tồn tại (`sent`, `no_device`,
  `exhausted`) vẫn phải có cặp receipt dù không gửi network lần nữa.
- Được phép thêm telemetry callback/context **keyword-only, optional và backward-compatible** trong
  `app/domain/reminder.py` để dispatcher báo durable `attempt_count` về logger đang giữ `due_at`.
  Existing direct caller không truyền context vẫn giữ return type `DispatchOutcome`; phải có ít nhất
  một assertion trực tiếp cho compatibility này trong `test_push_api.py`. Không đổi DB/state
  machine/public API và không duplicate cặp log ở cả timer lẫn dispatcher.
- Exception trước khi có outcome giữ event lỗi hiện hành với `error_type`; không giả thành `sent` hay
  `temporary_failure`, không log exception text. Một `started` thiếu `finished` là receipt điều tra,
  không được che bằng `finally` tạo outcome giả.
- Dùng logging level đang nhìn thấy trên Fly cho receipt vận hành, không đổi warning/error semantics
  của các event lỗi.

### O-03 — identifier redaction và privacy

Log không chứa raw `subject_id`, `dispatch_id` hoặc push-subscription ID. Correlation duy nhất là:

```text
occurrence_ref = sha256("<kind>:<canonical-subject-uuid>:<occurrence_on>").hexdigest()[:16]
```

`occurrence_ref` ổn định trong đúng một occurrence, không dùng làm auth/key và không xuất hiện trong
API. Cùng helper phải thay raw subject/dispatch identifier ở các receipt timer bị chạm bởi lô này
(`dispatch_*`, due-item `stale`, `dispatch_failed`, `pending_manual_required`). Không hash endpoint,
email, tên hay payload để log — các giá trị đó bị **loại bỏ hoàn toàn**, không “redact bằng hash”.

Test dùng sentinel cho name, reminder text, ciphertext-like text, endpoint, key, cookie, token,
dev-only credential và provider response; assert zero occurrence trong toàn bộ captured output. Không
ghi literal credential/account thật vào fixture, output, PR hoặc report.

### D-01 — internal read-only aggregate diagnostic

Tạo CLI one-shot `python -m scripts.reminder_delivery_receipt --window-minutes <N>` chạy **bên trong
Fly Machine** với runtime `DATABASE_URL`. Không thêm route hay secret flag.

Contract output: đúng một JSON object, stable keys, chỉ gồm:

- `commit`, `observed_at`, `window_minutes`;
- `push_subscription_count`;
- `dispatch_groups`: group theo `kind`, `occurrence_on`, `status`, `attempt_count`, kèm
  `dispatch_count`, `earliest_created_at`, `latest_created_at`, `earliest_last_attempt_at`,
  `latest_last_attempt_at`, `confirmed_count`.

CLI chỉ `SELECT`, đóng connection trong `finally`, exit non-zero khi config/query lỗi và chỉ in
`error_type` an toàn ra stderr. `1 <= N <= 1440`; filter theo `created_at` hoặc `last_attempt_at` nằm
trong window. Không nhận ID/endpoint/name làm argument; không SELECT/print raw ID, endpoint, key,
user-agent, name, text, ciphertext, email, session, provider response hay DSN. Timestamps RFC3339 UTC;
group/order deterministic. `push_subscription_count > 0` chỉ chứng minh có row, không chứng minh
endpoint còn sống hoặc đúng thiết bị đang quan sát.

Production invocation mẫu (shell trong Machine, không ghi env):

```text
cd /app/backend
python -m scripts.reminder_delivery_receipt --window-minutes 15
```

## 4. Đăng ký thiết bị và production T+2 QA

Owner đã cho phép production browser QA bằng allowlisted test role và mock data trong phiên hiện tại;
không chép account hay dev-only credential vào artifact. Nếu permission này bị thu hồi hoặc session
không còn đúng vai, dừng lane mutation.

### R-01 — bằng chứng thiết bị

Chấp nhận một trong hai receipt, ưu tiên (a):

1. Network thật của app: `POST /api/push/subscribe` trả `201` và JSON `status=created|updated`; report
   chỉ ghi method/path/status/status-token, không ghi request body, response `id`, endpoint/key.
2. CLI D-01 trả `push_subscription_count > 0` ngay trước test.

Tuyệt đối không dùng `GET /api/subscriptions` làm proof Web Push. Nếu count bằng 0, kết luận
`registration persistence chưa đạt`; không đổ lỗi scheduler.

### P-01 — một occurrence synthetic ở T+2

Precondition bắt buộc:

1. CI của exact merge SHA xanh; `GET /api/readyz` có `commit` đúng SHA và `db=up`; Fly chỉ một
   Machine/process passing; `ENABLE_INPROCESS_CRON=true`; không có external scheduler owner thứ hai.
2. R-01 đạt. Mở một bounded log stream trước mutation hoặc dùng event notification; không query log
   lặp. Lấy baseline D-01 một lần và lưu count của mọi group
   `(kind=tracker, occurrence_on=<ngày VN>, status, attempt_count)`; group chưa có được tính là
   `dispatch_count=0`, `confirmed_count=0`. Sau `dispatch_finished`, target group là group
   `status=sent` có `attempt_count` đúng giá trị vừa quan sát (không giả định luôn thành công lần 1).
3. Trong app, xác nhận đúng allowlisted role trên màn confirmation nếu account chooser xuất hiện.
   Tạo tracker health/event mock prefix `QA011F_`; chọn minute boundary đầu tiên **không sớm hơn
   now+2:00** và ghi exact `due_at` +07:00. Không dùng dữ liệu thuốc/người thật.

Chuỗi PASS phải quan sát đủ, theo thứ tự:

1. `queue_loaded` sau commit có `next_due_at` đúng occurrence synthetic;
2. `dispatch_started` cùng `kind/due_at/occurrence_on/occurrence_ref`;
3. `dispatch_finished` cùng ref, `outcome=sent`, attempt count khớp aggregate;
4. OS hiện notification trên thiết bị đang test;
5. click thân notification mở/focus đúng `/reminder-confirm?dispatch=...`, confirmation trả success;
6. sau terminal event hoặc mốc poll đầu ≥3 phút, chạy D-01 cùng window và so với baseline: đúng target
   group có `dispatch_count_final - dispatch_count_baseline = 1` và
   `confirmed_count_final - confirmed_count_baseline = 1`. `earliest/latest_created_at` và
   `earliest/latest_last_attempt_at` phải nằm trong cùng observation window; `latest_created_at` và
   `latest_last_attempt_at` phải advance so với baseline tương ứng. Cặp start/finish dùng cùng
   `occurrence_ref`, có `due_at` trong window và khớp `kind/occurrence_on/attempt_count` của target
   group. Không bao giờ giả định absolute count ban đầu bằng 0 hoặc final `confirmed_count` tuyệt đối
   bằng 1.

`sent` chỉ có nghĩa ít nhất một push provider call thành công; với nhiều device, nó không tự chứng
minh notification đã hiện trên đúng máy. Mỗi bước ghi `OBSERVED`; thiếu bước nào ghi `CHƯA VERIFY
ĐƯỢC`/`FAIL` đúng triệu chứng, không suy từ bước trước.

Cleanup: tắt reminder và soft-delete fixture qua app; xóa notification synthetic khỏi OS; giữ/xóa
device subscription theo lựa chọn owner (không DELETE DB tay); logout app, đóng tab/log stream. Row
`reminder_dispatch` là receipt lịch sử, không xóa bằng diagnostic. Postcheck không còn active
`QA011F_` reminder; artifact không chứa raw account, credential, endpoint, key, dispatch URL/ID hoặc
notification của app khác.

## 5. Decision matrix — chỉ kết luận sau receipt

| Receipt quan sát | Kết luận hẹp được phép | Bước kế tiếp |
|---|---|---|
| `push_subscription_count=0` hoặc POST không `201` | registration/persistence chưa đạt | sửa luồng subscribe trước, chưa chẩn đoán timer |
| device row có, nhưng reload không có due item đúng | schedule eligibility/reload/commit marker | kiểm tracker kind/input/reminder time và reload receipt |
| đúng `next_due_at`, sau due không `started`, không row aggregate mới | chưa đủ kết luận timer-loop: `_process_due_item` có thể bỏ item khi subject đã deleted/disabled/ineligible, hoặc một committed reload đã thay heap | kiểm lại eligibility tại due time và reload receipt nào supersede heap; chỉ khi subject vẫn eligible, không có reload thay thế và timer vẫn running mới phân loại due-loop gap; không thêm scheduler |
| `finished outcome=no_device` | dispatcher không còn usable device trong lượt đó | đăng ký lại/pruning evidence; không gọi đây là provider outage |
| `temporary_failure`, row `pending`, attempt tăng | VAPID/provider/network/DNS path lỗi tạm | để product backoff chạy; harness không poll dày |
| `exhausted`, `attempt_count=4` | bốn attempts đã hết, cần manual handling | giữ row/receipt; không tạo attempt thứ năm |
| `sent`, không thấy OS notification | backend nhận ít nhất một provider success; display target chưa đạt | kiểm đúng device/browser/OS permission; nhiều-device ambiguity |
| OS notification có nhưng click/confirm lỗi | service-worker click/deep-link/auth/confirm path | phân loại theo route/HTTP receipt |
| chỉ DevTools force-push thành công | SW/browser/OS lane đạt riêng | backend scheduled delivery vẫn CHƯA VERIFY |

## 6. Tests, RED→GREEN và commands

### Mapping acceptance

| ID | Test/receipt bắt buộc | Expected |
|---|---|---|
| O-01 | `test_queue_loaded_receipt_includes_next_due_at`, `..._uses_none_for_empty_heap` trong `test_cron_timer.py` | exact token set, một log/snapshot, no extra query |
| O-02 | PG `test_push_api.py::test_dispatch_receipts_cover_durable_outcomes` param đủ `sent|no_device|temporary_failure|exhausted`; PG `::test_dispatch_item_without_telemetry_keeps_dispatch_outcome_return`; non-PG `test_cron_timer.py::test_cron_timer_dispatch_receipt_ordering` | exact kind/due/occurrence/ref/attempt; count khớp row; same ref; direct caller vẫn nhận `DispatchOutcome` |
| O-03 | caplog sentinel + raw UUID denylist cho mọi event bị chạm | chỉ allowlisted metadata; zero forbidden value |
| D-01 | non-PG formatter/CLI validation + PG throwaway aggregate test trong `test_reminder_delivery_receipt.py` | SELECT-only, exact JSON schema/group/count/time, deterministic order, cleanup |
| R-01 | existing `test_push_subscription_create_update_and_unsubscribe` + production receipt | `201 created`, `201 updated`, một row; không artifact endpoint/key |
| P-01 | production runbook §4 | exact deploy + complete six-step observed chain |

Test phải dùng fake clock/fake transport; không sleep 30s/2m/10m và không gửi push thật ở local/CI.
PG lane dùng DB throwaway + synthetic row trong outer `try/finally`; cleanup lỗi vẫn phải báo và chạy
postcheck. Không dùng Neon production cho test automation.

Ít nhất hai guard phải có raw RED→GREEN receipt trong implementation PR:

1. tạm bỏ `next_due_at` hoặc một terminal `dispatch_finished`, chạy targeted test và thấy fail đúng
   assertion; restore rồi thấy green;
2. tạm cho raw subject UUID hoặc sentinel endpoint/text lọt vào output, thấy privacy test fail; restore
   rồi thấy green.

Không commit sabotage. Commands tối thiểu:

```text
cd backend
uv run ruff check app/core/cron_timer.py app/domain/reminder.py scripts/reminder_delivery_receipt.py tests/test_cron_timer.py tests/test_reminder_domain.py tests/test_push_api.py tests/test_reminder_delivery_receipt.py
uv run pytest -m "not pg" tests/test_cron_timer.py tests/test_reminder_domain.py tests/test_reminder_delivery_receipt.py tests/test_push_api.py -q
uv run pytest -m pg tests/test_push_api.py tests/test_reminder_delivery_receipt.py -q
cd ..
pre-commit run --all-files
gitleaks detect --source . --no-banner --redact
git diff --check
git status --short
```

Nếu PG/Docker/env không khả dụng, ghi raw output + `CHƯA VERIFY ĐƯỢC`; không đổi thành PASS. CI xanh
chứng minh exact commit qua automated lanes, không chứng minh production/OS.

## 7. Definition of Done

- Diff chỉ nằm trong §2; không có route/migration/scheduler/poller/architecture change.
- O-01…O-03 và D-01 có local + CI receipt, gồm RED→GREEN và privacy denylist.
- PR body tách `OBSERVED` / `INFERRED` / `CHƯA VERIFY`, ghi exact HEAD, command + raw output, cleanup
  và giới hạn; không chứa identifier/secret/personal data bị cấm.
- Sau merge/deploy, P-01 chỉ PASS khi exact SHA/db/one-machine và cả sáu event/UX/aggregate bước đều
  được quan sát. Nếu production lane chưa chạy, trạng thái cuối là **CHƯA VERIFY ĐƯỢC**, không phải
  “scheduler fixed”.
