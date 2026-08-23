# Task 030 — Gom reminder thành một Web Push và hộp chờ trong app

> Trạng thái: 📋 READY — owner chốt hướng sản phẩm 2026-08-24; chưa implement
> Executor đề xuất: T2 Sol · Bậc: high · Effort: high · Skill gợi ý: Playwright · MCP cần: không có

## 1. Mục tiêu và câu hứa người dùng

Khi `N` reminder đến hạn trong cùng một cửa sổ gần nhau, microSched gửi **một notification
generic trên mỗi device đã đăng ký**, đúng mẫu:

```text
Title: microSched
Body:  Bạn có N thông báo từ microSched, bấm để xem ngay
```

Notification không chứa tên/type/nội dung từng mục và **không bao giờ tự tick, tạo Entry, gia hạn
subscription hay hoàn thành gì**. Bấm notification chỉ mở microSched và mở hộp reminder đang chờ;
mọi item bắt đầu unchecked, chỉ action rõ ràng của người dùng mới ghi nhận từng mục.

Phase đầu là một global window/template + một in-app panel. Không có per-device preference,
per-device delivery history, AI, dịch vụ/cost mới hay daily-task UX.

## 2. Bằng chứng hiện trạng và contract bị thay thế có chủ đích

- [QUAN SÁT] `backend/app/domain/models.py:603-662` có `reminder_dispatch` theo occurrence với
  unique `(subject_type, subject_id, dispatched_on)`, status `pending|sent|no_device`, attempt
  count và confirmation; chưa có due timestamp hay bundle metadata. `:578-600` là một row Web
  Push subscription cho mỗi endpoint/device.
- [QUAN SÁT] `backend/app/domain/reminder.py:49-97` đang tạo payload riêng từng tracker/
  subscription, đôi khi chứa public label. `:167-280` query toàn bộ push subscriptions rồi gửi
  payload một lần cho mỗi row; chỉ cần một send thành công thì occurrence có status `sent`.
- [QUAN SÁT] `backend/app/domain/reminder.py:118-123` ghi contract production đúng một app
  process và process-local mutex; durable dispatch state mới là lớp recovery qua restart.
- [QUAN SÁT] `backend/tests/test_reminder_domain.py:26-146` đang khóa payload cũ: private có thể dùng
  `reminder_text`, public có thể fallback tracker/subscription name. Implementation 030 phải thay
  các assertion đó bằng canary/count-only guard ở R10, không giữ hai expected contract cùng lúc.
- [QUAN SÁT] `backend/app/core/cron_timer.py:30-39,46-54` khóa timezone +07, subscription lúc
  07:00, grace 15 phút và retry `30s → 2m → 10m`; `:679-705` pop rồi dispatch từng item.
- [QUAN SÁT] `frontend/src/sw.ts:16-55` chỉ parse `{title, body, url}`, gọi
  `showNotification`, rồi click navigate/focus. Chưa có `tag`/`timestamp`, nhưng service worker
  tự nó không POST.
- [QUAN SÁT] `frontend/src/ReminderConfirmScreen.tsx:43-139` tạo UUID/time rồi
  `useEffect(...confirmMutation.mutate())`; chỉ cần mở `/reminder-confirm?dispatch=…` hiện nay
  đã POST confirm và tạo Entry. Historical contract ở `docs/tracking-brief.md:263-275` và
  `agent-tasks/011b-medication-reminder-webpush.md:217-228,526-529` còn ghi allowance đưa public
  `reminder_text`/tracker name lên lock screen; dated supersession hiện nằm ở
  `docs/tracking-brief.md:277-290` và các note 2026-08-24 của 011b. Task này **cố ý thay thế cả hai**:
  auto-confirm khi mở và payload theo từng subject, theo quyết định owner 2026-08-24.
- [QUAN SÁT] `backend/scripts/reminder_delivery_receipt.py:21-39,84-128` hiện giữ aggregate
  theo kind/date/status/attempt và top-level keys ổn định; chưa có bundle report.
- [QUAN SÁT] `backend/app/domain/subscription.py:333-352` đọc subscription bình thường bằng JOIN
  parent Tracker, áp `readable(..., Tracker, auth)` rồi `not_deleted(..., Subscription)`; do đó
  subscription soft-delete phải tiếp tục ẩn/404 ở CRUD API. Timer chỉ schedule subscription khi
  `subscription.deleted_at IS NULL`, `canceled_at IS NULL`, `expires_on >= today_vn` và parent
  tracker chưa delete (`backend/app/core/cron_timer.py:284-299`).
- [QUAN SÁT] confirm tracker hiện hành lock dispatch, trả 404 khi dispatch thiếu, 409 khi subject
  sai/Tracker đã delete hoặc config không còn eligible, 403 `PRIVATE_UNLOCK_REQUIRED` khi parent
  private khóa, và chỉ success mới set confirmation/tạo Entry
  (`backend/app/domain/reminder.py:283-374`). Acknowledge mới phải giữ cùng thứ tự safety gate và
  không biến subscription unavailable thành restore/renew.
- [QUAN SÁT bên ngoài, kiểm 2026-08-24] Apple hỗ trợ Web Push cho Home Screen web app từ
  iOS/iPadOS 16.4 và yêu cầu notification permission từ tương tác trực tiếp:
  <https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/>.
- [QUAN SÁT bên ngoài, kiểm 2026-08-24] Notifications Living Standard định nghĩa
  `tag`, `timestamp`, `renotify`; notification actions tùy platform:
  <https://notifications.spec.whatwg.org/>.
- [SUY LUẬN] Nâng sang Declarative Web Push không cần thiết để đạt mục tiêu và sẽ mở thêm
  compatibility scope. Phase này giữ payload/service-worker pipeline đang chạy, chỉ thêm metadata.
- [KHÔNG BIẾT] Push provider/OS có luôn collapse retry theo `tag` khi device offline hay không;
  không có per-device receipt để chứng minh. In-app inbox mới là canonical pending state.

## 3. Global grouping contract

### 3.1 Cấu hình cố định

Các constant ở code, có unit test và **không** là env/app setting/user/device preference:

```text
REMINDER_BUNDLE_WINDOW_MINUTES = 5
REMINDER_NOTIFICATION_TITLE = "microSched"
REMINDER_NOTIFICATION_BODY = "Bạn có {count} thông báo từ microSched, bấm để xem ngay"
REMINDER_NOTIFICATION_URL = "/?reminders=1"
```

- Window là bucket nửa mở 5 phút, align theo đồng hồ `Asia/Ho_Chi_Minh`: `[HH:00, HH:05)`,
  `[HH:05, HH:10)`, …; boundary đúng `HH:05:00` thuộc bucket sau.
- Không gửi sớm. Bundle flush ở cuối bucket, nên độ trễ chủ đích `0 < delay ≤ 5 phút`.
- `N` là số **occurrence rows duy nhất** trong bundle, không phải số device, attempts, subject
  types hay số item đang nhìn thấy khi private mode khóa.
- Tracker + subscription trong cùng bucket được gom chung. Không chia bundle theo kind/privacy.
- Current 15-minute grace vẫn giữ: occurrence lần đầu quá 15 phút là stale và không gửi; các
  occurrence hợp lệ bị timer/startup trễ nhưng còn trong grace được gom vào một catch-up bundle.
  Không “bắn bù” backlog nhiều ngày.

### 3.2 Timer không thành poller

- Heap vẫn là nguồn wake-up. Khi item đầu bucket đến hạn, timer buffer các item đến trước
  `window_end` và sleep đến `min(next_due, window_end)`; không thêm interval query.
- Đến `window_end`, validate subject eligibility hiện hành, claim occurrences và assign một
  `bundle_id` trong **một transaction**, rồi commit trước network I/O.
- Startup/reload thu mọi first-attempt occurrence overdue nhưng còn trong grace vào một catch-up
  bundle tại thời điểm reload. Pending recovery đã có `bundle_id` giữ nguyên membership.
- Pending row đã claim được rehydrate tối đa 24 giờ như contract 011d hiện hành; quá 24 giờ hoặc
  hết 4 attempts chỉ log `pending_manual_required`, giữ row và không gửi mù/đổi status.
- Schedule ngày kế tiếp vẫn được tạo kể cả bundle `no_device`, exhausted hay delivery lỗi, đúng
  invariant hiện hành; gom bundle không được nuốt chuỗi ngày sau.

## 4. Data/migration tối thiểu, không có bảng ops mới

Task 030 tạo **một Alembic revision nối trực tiếp revision task 028** và chỉ thêm vào
`reminder_dispatch`:

```text
scheduled_for TIMESTAMPTZ NULL  -- due instant gốc; NULL chỉ cho legacy
bundle_id     UUID NULL         -- UUIDv7 của logical bundle; NULL chỉ cho legacy/chưa claim
```

Thêm:

```text
CHECK (scheduled_for IS NULL OR bundle_id IS NOT NULL)
INDEX (scheduled_for, id)
  WHERE scheduled_for IS NOT NULL AND confirmed_at IS NULL
INDEX (bundle_id) WHERE bundle_id IS NOT NULL
```

- **Alembic upgrade không có DML backfill.** Ngay sau riêng bước upgrade, mọi historical row giữ
  NULL/NULL và toàn bộ status/attempt/confirmation/audit timestamp byte-for-byte. Không dùng
  `created_at` để giả một due time trong DB.
- Occurrence mới set `scheduled_for=item.due_at` (convert UTC) và `bundle_id` trước lần network
  đầu. Unique occurrence constraint/status enum/attempt max 4 giữ nguyên.
- Legacy `pending` row còn trong recovery window 24 giờ và attempt <4 được assign `bundle_id`
  để retry generic nhưng giữ `scheduled_for=NULL`, vì không biết chắc original due instant. Row đó
  vào inbox bằng fallback read-only `created_at`; row legacy ngoài recovery không gửi lại.
- `bundle_ref = sha256(bundle_id bytes)[:16]` chỉ để payload/log/report; không log raw bundle UUID.
- Downgrade drop hai index/check/cột. Migration QA chỉ trên Postgres throwaway/CI, không round-trip
  Neon.

### 4.1 Legacy recovery, audit timestamp và rollback

`backend/alembic/versions/0008_push_subscription_and_reminder_dispatch.py:129-137` cài
`BEFORE UPDATE` trigger cho `reminder_dispatch`; vì vậy không được đồng thời nói “gắn bundle” và
“audit byte-for-byte mãi mãi”. Contract duy nhất là:

1. Eligibility tại snapshot `now`: row legacy `status='pending'`, `bundle_id IS NULL`,
   `attempt_count < 4`, và `COALESCE(last_attempt_at,created_at) >= now - 24h`. Biên đúng 24h được
   nhận; cũ hơn dù một microsecond hoặc attempt =4 không được attach/mutate.
2. Trước network, một transaction ngắn set **chỉ** `bundle_id` cho các row eligible và commit.
   `scheduled_for` vẫn NULL; trigger đổi `updated_at` sang lúc attachment. Đây là audit trung thực
   của recovery metadata mutation, không phải timestamp reminder gốc và không được giấu/bypass
   trigger. `created_at`, status, attempt, last-attempt và confirmation fields giữ nguyên trong
   transaction attachment.
3. Crash sau commit phục hồi cùng durable `bundle_id`; đọc/reload lần sau không ghi lại attachment
   và không đổi `updated_at` chỉ vì quan sát. Network attempt sau đó mới đổi attempt/status fields
   và `updated_at` lần nữa theo contract dispatcher bình thường.
4. Legacy row **đã** `sent|no_device` tại recovery snapshot, pending quá 24h hoặc exhausted giữ
   NULL/NULL và audit timestamps byte-for-byte. Không có bulk historical rewrite.
5. Downgrade **trước** khi runtime attach row nào thì round-trip byte-for-byte. Sau khi đã attach,
   rollback contract được nói hẹp và rõ: dừng đường claim/dispatch 030 trước schema downgrade; chạy
   receipt read-only ghi `legacy_scheduled_count`; downgrade drop cột nhưng giữ `updated_at` ở mốc
   DML có thật gần nhất. Trường hợp này **không** còn byte-for-byte và tuyệt đối không backdate để
   giả lịch sử. Restore từ backup không phải acceptance hay thao tác tự động của task 030.

Không thêm bundle table, inbox table, device-delivery row, preference, cron service, queue/broker,
provider API hay retention job. `reminder_dispatch` tiếp tục là delivery receipt và pending state.

## 5. Claim, dedupe, retry và multi-device

### 5.1 Một logical bundle

1. Upsert mọi occurrence bằng unique hiện hành, lock rows deterministic theo
   `(COALESCE(scheduled_for,created_at),id)`.
2. Nếu chưa có bundle, assign cùng UUIDv7; nếu đã có, không re-bundle hoặc thêm member sau lần
   network đầu. Transaction hỏng thì không row nào mang bundle nửa vời.
3. Mỗi attempt tăng từng row đúng một lần và set `last_attempt_at`, commit rồi mới gọi Web Push.
   Bundle mới hoàn toàn có counts bằng nhau; row legacy được attach có thể làm min/max khác nhau.
   Payload `N`/body/tag/timestamp vẫn bất biến qua retry; dừng retry khi maximum count chạm 4.
4. Process-local lock dùng `bundle_id`; durable row/unique/lock vẫn bảo vệ crash/redeploy. Không
   giả định lock process là biên lai duy nhất.

### 5.2 Kết quả aggregate giữ đúng hệ thống hiện tại

- Query active `push_subscription` đúng **một lần mỗi bundle**, rồi gửi một generic payload cho
  từng row/device. “Một OS notification” nghĩa là một notification trên mỗi device; không thể có
  đúng một notification chung xuyên nhiều thiết bị.
- Có ít nhất một device `SENT`: tất cả rows bundle → `sent`; temporary failure ở device khác
  không retry vì không có per-device history, giống contract hiện hành.
- Không subscription hoặc toàn endpoint dead: rows → `no_device`.
- Tất cả send tạm lỗi: rows giữ `pending`, retry cùng bundle theo `30s, 2m, 10m`; không row nào
  được network-attempt quá 4 lần.
- Crash sau commit claim nhưng trước/giữa network: recovery retry cùng bundle. Có thể đã giao nhưng
  chưa nhận ACK; stable `tag` giúp OS collapse best-effort, không được báo cáo là exactly-once.
- `sent|no_device|exhausted delivery` không đồng nghĩa user đã xử lý. Chỉ `confirmed_at` quyết
  định item còn trong inbox.

## 6. Payload, service worker và lock-screen privacy

Payload JSON exact cho bundle 3 items:

```json
{
  "title": "microSched",
  "body": "Bạn có 3 thông báo từ microSched, bấm để xem ngay",
  "url": "/?reminders=1",
  "tag": "microsched-reminder-0123456789abcdef",
  "timestamp": 1787580300000
}
```

- `timestamp` là Unix milliseconds của `window_end`; retry không đổi.
- SW gọi:

```text
showNotification(title, {
  body, icon: '/microsched.svg', tag, timestamp,
  renotify: false, data: { url }
})
```

- Không `actions`, không notification action button, không background fetch/POST, không
  `requireInteraction`. Click chỉ close + navigate/focus `/?reminders=1`.
- Tag ổn định theo bundle để retry không tạo item OS mới ở platform hỗ trợ. Bundle khác có tag
  khác; nhiều cửa sổ thật sự khác nhau có thể để nhiều notifications.
- Malformed/old payload vẫn dùng safe fallback title/body/url và **không mutate**. Old push URL
  `/reminder-confirm?dispatch=…` là compatibility route mở inbox/highlight, không auto-confirm.
- Payload không chứa subject type/id/name, reminder text, privacy state, endpoint hay dispatch ID.
  Số `N` là metadata generic duy nhất có thể hiện trên lock screen theo template owner chốt.
- Builder active chỉ nhận `count`, `bundle_ref`, `window_end`; không nhận/decrypt `Tracker`,
  `Subscription`, name hay `reminder_text`. Public hay private đều đi **cùng một** count-only
  template. `reminder_text` chỉ còn là config/backward-compatible detail trong app; private detail
  chỉ đọc được sau reading gate tương ứng (`Subscription` kế thừa privacy từ Tracker cha), không bao
  giờ vào OS payload/log.
- App không điều khiển preview setting của iOS. Acceptance phải kiểm cả preview-on/off nhưng không
  tuyên bố app có thể buộc OS che count.

## 7. In-app pending reminder inbox

### 7.1 Vị trí và lifecycle

- Một compact cell global nằm trước active screen/dashboard; nếu có visible pending item, cell
  hiện `N lời nhắc đang chờ`. Bấm cell mở mobile bottom sheet/panel ngắn gọn.
- `/?reminders=1` tự mở panel **sau GET**, nhưng không gọi mutation. Old confirm route chuyển tới
  cùng panel với `highlight` client-side; không mount `ReminderConfirmScreen` auto-mutation cũ.
- Không polling. Fetch lúc authenticated app mount, window focus, private unlock/lock và sau mỗi
  mutation theo `NO_POLLING_QUERY_OPTIONS`/task 021.
- Offline: PWA shell có thể mở nhưng không persist labels/pending list mới; hiện “Cần kết nối để
  tải lời nhắc”. Không tick offline, không queue acknowledgment trong phase này.

### 7.2 Read API exact

```text
GET /api/reminders/pending?limit=50&cursor=<opaque>&highlight=<optional UUID>
```

```json
{
  "items": [
    {
      "dispatch_id": "<UUID>",
      "kind": "tracker",
      "due_at": "2026-08-24T14:00:00Z",
      "due_source": "scheduled_for",
      "label": "Uống thuốc",
      "action": "record_entry"
    },
    {
      "dispatch_id": "<UUID>",
      "kind": "subscription",
      "due_at": "2026-08-24T00:00:00Z",
      "due_source": "scheduled_for",
      "label": "Gói dịch vụ",
      "action": "acknowledge"
    }
  ],
  "next_cursor": null
}
```

- Default eligibility: `(scheduled_for IS NOT NULL OR bundle_id IS NOT NULL) AND confirmed_at IS
  NULL`, bất kể delivery status; order oldest due first bằng
  `(COALESCE(scheduled_for,created_at) ASC,id ASC)`. `limit` 1..100, default 50; cursor opaque chứa
  đủ sort tuple. Bundled legacy row trả `due_source=legacy_created_at`.
- `highlight` chỉ bổ sung đúng một legacy unresolved row nếu readable; dùng
  `due_at=created_at`, `due_source=legacy_created_at`, dedupe theo dispatch ID. Không liệt kê cả
  historical backlog.
- Không trả `subject_id`, `bundle_id/ref`, delivery attempts/status, hidden count hoặc endpoint.
- Join subject qua reading gates. Private tracker/subscription khi lock bị **lọc hoàn toàn**, không
  đổi response shape/flag/count. Panel luôn có lời nhắc tĩnh “Mở Chế độ Riêng tư để xem mục riêng
  tư” nên không cần tiết lộ có hidden row hay không; unlock refetch.
- Resolver của pending projection phân biệt chính xác:
  - tracker eligible = physical row live, `kind=health`, `input_mode=event`;
  - subscription eligible = physical row + parent live, subscription chưa soft-delete/chưa
    cancel và `expires_on >= today_vn` (`today_vn` ở `Asia/Ho_Chi_Minh`), đúng timer contract 011d;
  - physical subject còn tồn tại nhưng không đạt shape tương ứng là **unavailable**. Riêng
    subscription gồm ít nhất soft-deleted, canceled, expired hoặc parent tracker soft-deleted.
- Eligible subject qua reading gate mới được decrypt/trả label thật và action `record_entry`
  (tracker) hoặc `acknowledge` (subscription). Unavailable subject chỉ trả label generic
  `Mục không còn khả dụng` + action `acknowledge_unavailable`; không trả tên/status/reason.
- Đây là projection hẹp theo một dispatch đã có, không nới CRUD API: resolver được phép probe các
  physical columns tối thiểu và dùng `with_privacy_gate` trên Tracker cha trước khi phân loại,
  nhưng không dùng probe đó để trả model/name. `GET /api/subscriptions/{id}` của subscription
  soft-delete vẫn 404. Parent private khóa thì item bị lọc; physical subject/parent thật sự không
  còn tồn tại thì item cũng bị lọc vì không còn privacy basis an toàn.

### 7.3 Item actions — luôn explicit và idempotent

Mọi checkbox ban đầu unchecked. Click label chỉ mở detail (nếu còn), không tick. Khi người dùng
check:

- `action=record_entry`: capture `entry_id` UUIDv7 + `occurred_at` đúng lúc tap, rồi gọi endpoint
  tracker hiện hành:

  ```text
  POST /api/reminder-dispatch/{dispatch_id}/confirm
  {"entry_id":"<UUIDv7>","occurred_at":"<RFC3339>"}
  ```

  Endpoint giữ row lock/idempotency/private unlock/config checks. Chỉ success mới remove item;
  không optimistic checked. Retry dùng nguyên body đã capture.

- `action=acknowledge` hoặc `acknowledge_unavailable`:

  ```text
  POST /api/reminder-dispatch/{dispatch_id}/acknowledge
  {}
  ```

  Endpoint không nhận action/subject state từ client; body chỉ `{}` và server lock dispatch rồi
  derive lại state. First success trả exact `200 {"acknowledged":true}`, set
  `confirmed_at=now`, giữ `confirmed_entry_id=NULL` (cùng `updated_at` do trigger hiện hành);
  không renew/cancel/restore/tạo Entry. Replay khi `confirmed_at IS NOT NULL` trả exact
  `200 {"acknowledged":false}` trước subject lookup và không đổi timestamp/row nào. Row lock phải
  khiến hai request đồng thời có đúng một `true`, một `false`.

Action/status matrix bắt buộc:

| State ở lúc server xử lý unconfirmed dispatch | Action GET | `POST .../acknowledge` | Mutation |
|---|---|---|---|
| Tracker live + eligible | `record_entry` | `409`, `detail.code=ENTRY_CONFIRM_REQUIRED` | không đổi dispatch, không Entry |
| Tracker physical nhưng soft-delete/config ineligible, privacy gate đọc được | `acknowledge_unavailable` | `200 {"acknowledged":true}`; replay `false` | chỉ confirm dispatch |
| Subscription live + eligible | `acknowledge` | `200 {"acknowledged":true}`; replay `false` | chỉ confirm dispatch; không Entry/renew/cancel |
| Subscription physical nhưng soft-delete/canceled/expired/parent soft-delete, privacy gate đọc được | `acknowledge_unavailable` + label generic | `200 {"acknowledged":true}`; replay `false` | chỉ confirm dispatch; không restore/uncancel/renew/Entry |
| Parent private khóa | item không có trong GET | `403`, `detail.code=PRIVATE_UNLOCK_REQUIRED` | zero mutation |
| Dispatch thiếu | item không có trong GET | `404`, `detail="Reminder dispatch not found"` | zero mutation |
| Subject/parent physical thật sự thiếu hoặc `subject_type` không hỗ trợ | item không có trong GET | `409`, `detail="Reminder subject is unavailable"` | zero mutation |

Đặc biệt, soft-deleted subscription **không** trả 404 từ acknowledge nếu physical row và parent
còn đủ để áp privacy gate; nó đi đúng nhánh unavailable như tracker unavailable. `404` chỉ dành
cho dispatch ID không tồn tại; physical subject/parent thật sự thiếu hoặc type không hỗ trợ trả
generic `409` như current confirm-family business conflict, không acknowledge. Một stale panel thấy
subscription eligible rồi subject đổi trạng thái trước POST vẫn được server derive lại và
acknowledge theo state mới; client không thể ép `acknowledge` để bypass gate.

- Network/403/409 khác giữ item unchecked và focus/error tại item. Private 403 mở unlock flow;
  success retry đúng body. Không có `check all`, bulk action, auto-dismiss, uncheck/revert hoặc
  swipe-to-complete trong phase này.

## 8. Log và receipt contract

### 8.1 Structured application logs

Hai event, một dòng key/value mỗi event:

```text
reminder_bundle_claimed
  bundle_ref window_start window_end scheduled_min scheduled_max item_count
  tracker_count subscription_count legacy_scheduled_count attempt_count is_retry

reminder_bundle_finished
  bundle_ref item_count device_count sent_count temporary_failure_count dead_count
  attempt_count outcome duration_ms
```

- Timestamp log UTC RFC3339; counts integer ≥0; outcome thuộc
  `sent|temporary_failure|no_device|exhausted`.
- Không log subject/dispatch/bundle UUID, names, labels, message body, endpoint/key, ciphertext,
  payload JSON hoặc exception text có URL. `error_type` cho failure là đủ.

### 8.2 `reminder_delivery_receipt.py`

Giữ nguyên top-level/field hiện có:

```text
commit, observed_at, window_started_at, window_minutes,
push_subscription_count, dispatch_groups
```

Chỉ cộng hai top-level additive fields:

```json
{
  "bundle_groups": [
    {
      "bundle_ref": "0123456789abcdef",
      "item_count": 3,
      "tracker_count": 2,
      "subscription_count": 1,
      "legacy_scheduled_count": 0,
      "resolved_count": 0,
      "earliest_scheduled_for": "<UTC RFC3339>",
      "latest_scheduled_for": "<UTC RFC3339>",
      "status_counts": {"pending": 0, "sent": 3, "no_device": 0},
      "minimum_attempt_count": 1,
      "maximum_attempt_count": 1,
      "earliest_last_attempt_at": "<UTC RFC3339|null>",
      "latest_last_attempt_at": "<UTC RFC3339|null>"
    }
  ],
  "legacy_dispatch_count": 0
}
```

- Window filter giữ semantics hiện hành (`created_at` hoặc `last_attempt_at` trong window).
- `legacy_scheduled_count` đếm member của bundle có `scheduled_for IS NULL`; earliest/latest
  scheduled bỏ qua NULL và cùng là `null` nếu toàn bundle legacy.
- `resolved_count` đếm `confirmed_at IS NOT NULL`, gồm tracker confirm và subscription/unavailable
  acknowledge; `dispatch_groups.confirmed_count` cũ vẫn chỉ đếm `confirmed_entry_id` để không đổi nghĩa.
- `legacy_dispatch_count` là count rows trong cùng filter có `bundle_id IS NULL`; không chia kind
  hoặc in IDs. `bundle_groups` chỉ bundle non-null; không names/endpoints/payload.
- CLI vẫn one-shot read-only, cùng input validation/timeout/không scheduler. Không có metrics
  service, dashboard hay provider-cost integration.

## 9. Delayed/offline/fallback matrix

| Trạng thái | Hành vi đã khóa |
|---|---|
| Timer trễ ≤15 phút | claim item hợp lệ, gom catch-up thành một bundle, không gửi từng item |
| Timer trễ >15 phút, chưa claim | giữ stale/grace contract; log aggregate-safe, lên lịch occurrence sau |
| Pending đã claim <24 giờ | retry cùng/attach bundle generic; legacy không bịa `scheduled_for` |
| Pending >24 giờ hoặc attempt=4 | giữ row, không gửi; log `pending_manual_required` như 011d |
| DB lỗi trước claim commit | không gửi; reload dựng lại từ schedule, unique ngăn duplicate occurrence |
| Crash sau claim commit | recovery cùng `bundle_id`, N/tag/timestamp bất biến |
| Push temporary failure toàn bộ | retry 30s/2m/10m, max 4; inbox vẫn có item |
| Ít nhất một device sent | aggregate `sent`; không retry device tạm lỗi vì không có history per-device |
| Không device/dead endpoints | `no_device`; inbox vẫn cho người dùng xử lý khi mở app |
| Device offline sau provider ACK | provider/OS quyết định delay; `timestamp` giữ mốc bundle; app không hứa SLA |
| App offline khi click | mở shell/offline message; không POST/queue/persist private pending data |
| Old/malformed payload | generic fallback + open app; tuyệt đối không auto-confirm |

## 10. Acceptance matrix và test bắt buộc

| ID | Tình huống | Biên lai bắt buộc |
|---|---|---|
| R1 | 3 tracker cùng bucket | đúng 1 payload/device, body N=3; không có 3 per-item payload |
| R2 | tracker + subscription mixed | một bundle N=2; inbox có hai action đúng loại |
| R3 | 04:59.999 vs 05:00 boundary | thuộc hai bundle; không gửi occurrence trước due |
| R4 | retry/crash | same bundle/ref/body/tag/timestamp; mỗi member tăng đúng một attempt, unique rows |
| R5 | 2 devices, một sent/một temp fail | 2 network sends, aggregate rows sent; không tuyên bố device thứ hai delivered |
| R6 | no device | status no_device nhưng pending panel vẫn có item |
| R7 | click OS/old confirm URL | chỉ GET/mở panel; network trace không có POST trước explicit tap |
| R8 | tracker explicit check | một Entry idempotent; default unchecked; private unlock retry giữ body; gọi ack khi tracker vẫn eligible → 409/zero mutation |
| R9a | subscription eligible check | first ack 200/true, concurrent/replay 200/false; confirmed_at set, không Entry/renew/cancel |
| R9b | subscription soft-delete/cancel/expire/parent delete trước ack | GET generic + `acknowledge_unavailable`; 200 true→false; không name/reason/restore/uncancel/renew/Entry |
| R9c | subscription private/orphan boundary | locked parent: GET omit + direct ack 403/zero mutation; dispatch missing → 404; physical subject/parent missing → GET omit + 409; CRUD GET soft-deleted vẫn 404 |
| R10 | public/private canary labels + reminder_text | mọi bundle chỉ exact count-only body; không subject field/text trong payload/log; in-app private detail cần unlock |
| R11a | migration, chưa chạy recovery | mọi historical row/audit byte-for-byte; downgrade round-trip byte-for-byte |
| R11b | eligible legacy ở biên 24h | set bundle_id, giữ scheduled_for NULL; chỉ updated_at đổi lúc attach; crash/reload reuse, không ghi attachment lần hai |
| R11c | legacy quá 24h/attempt=4/terminal | không attach, không gửi, mọi field/audit byte-for-byte |
| R11d | downgrade sau attachment | dừng claim/dispatch; pre-downgrade receipt có legacy count; cột bị drop nhưng updated_at giữ mốc DML thật, không backdate; byte-for-byte không còn được hứa |
| R12 | offline/delayed | mọi nhánh §9 có deterministic unit/integration test; không poller mới |
| R13 | receipt/log privacy | schema exact/additive; không ID/name/endpoint/payload; read-only CLI |
| R14 | mobile/a11y | 320×568/390×844, 44 px, keyboard/SR/focus/error; sheet không overflow |

Test lanes:

- Backend unit/integration: bucket boundaries/timezone, mixed grouping, stale/catch-up, atomic claim,
  unique race, retry/exhausted/crash recovery, aggregate multi-device result, no-device, active
  legacy recovery ở `24h`, `24h+1µs`, attempt 3/4; exact before/after columns + trigger timestamp;
  downgrade trước/sau attachment, gồm receipt + expected non-byte-preserving `updated_at`; pending
  cursor/privacy/highlight; confirm/ack action matrix, gồm subscription live/soft-delete/canceled/
  expired/parent-delete, locked parent, physical-missing, stale-state và concurrent true→false.
- Timer regression: heap sleeps tới due/boundary/reload event, không interval DB poll; next-day
  scheduling giữ nguyên cho tracker/subscription.
- Frontend Vitest: exact Vietnamese payload string/parser/tag/timestamp; canary public/private
  names và `reminder_text` không xuất hiện; click no mutation, panel query lifecycle,
  unchecked/error/unlock actions, old route, offline state/cache exclusion.
- Playwright: intercept GET/POST để chứng minh open/deep-link không POST; mobile sheet/a11y/focus;
  service-worker notification path ở browser hỗ trợ.
- Physical iPhone Home Screen post-deploy: cùng bucket N=2 trên một device chỉ thấy một generic OS
  notification; tap mở panel; preview không có label; explicit check mới POST. Đây là acceptance
  **CHƯA VERIFY** cho tới khi owner/device lane chạy — CI/browser desktop không thay thế.
- Guardrail RED → GREEN: tạm khôi phục auto-confirm `useEffect` hoặc vòng dispatch per-item, thấy
  test “no POST on open”/“one payload per device per bundle” đỏ đúng lý do; hoàn nguyên rồi xanh.

## 11. Sequencing, deploy gate và không làm

1. **Gate cứng 1:** task 017 merge trước vì cùng service worker, app/query cache/offline contract.
2. **Gate cứng 2:** task 028 migration merge trước; revision 030 đặt `down_revision` đúng revision
   028. Không để hai Alembic heads hoặc triển khai hai migration song song.
3. Backend migration → bundle dispatcher/tests → pending API → SW/UI → receipt/docs. Production
   migration áp dụng thủ công theo runbook; không thêm auto-migrate/cron/worker.
4. Dated records 2026-08-24 trong `docs/tracking-brief.md` và task 011b của spec PR này đã
   supersede **cả** auto-confirm lẫn public `reminder_text`/name payload. Implementation/QA phải
   giữ count-only contract; payload-specific assertion cũ trong `test_reminder_domain.py`, QA 011b
   và acceptance 011d là historical ở đúng điểm này, còn scheduler/retry contract khác vẫn giữ.
   Không xóa historical decision và không sửa status/index rộng.
5. Deploy/physical device là gate tuần tự sau CI/review; task này không tự merge/deploy.

Không làm: task reminder/daily-task UX, per-device history/preferences, notification categories/
actions, bulk check, cached private inbox, new provider/cost API, AI, declarative Web Push migration,
queue/broker, new ops service, production data backfill hoặc analytics dashboard. Nếu production
không còn đúng invariant một app process, dừng và tách architecture decision; không lén dùng
process lock như distributed guarantee.
