# 011d — In-Process Async CRON Timer (Scheduler production duy nhất)

> **Executor:** T2 Codex (`gpt-5.6-sol`) · **Bậc:** L2 — backend/infrastructure · **Effort:** high · **Skill gợi ý:** không cần · **MCP cần:** không cần.
>
> **Trạng thái: DRAFT — viết ngày 2026-08-05, cập nhật theo owner direction 2026-08-06.** 011d là scheduler production duy nhất được chọn thay cho Google Cloud Scheduler. Đây vẫn là DRAFT triển khai: không được bật production trước khi decision record nhận dated note và các cổng cutover ở §0.3 được thỏa.

## Phạm vi giao

Thiết kế và, sau khi được duyệt, thi công một **In-Process Async CRON Timer** chạy trong đúng process FastAPI hiện tại. Timer giữ lịch trong RAM bằng `heapq`/min-heap, ngủ bằng `asyncio`, chỉ đánh thức Neon khi cần nạp lại lịch hoặc xử lý một occurrence thật sự.

Timer này chịu trách nhiệm **định thời và gọi service dispatch**. Hạ tầng Web Push, VAPID, `push_subscription`, `reminder_dispatch`, payload kín đáo và confirmation idempotent vẫn thuộc hợp đồng của `agent-tasks/011b-medication-reminder-webpush.md`.

011d **không thêm bảng queue**, không thêm migration, không dựng scheduler service mới. Queue mất khi process chết; lúc startup/reload, queue được dựng lại từ `tracker`/`subscription` **và các row `reminder_dispatch` đang `pending` còn trong cửa sổ recovery**. Row pending là nguồn sự thật bền cho một dispatch đã bắt đầu trước crash, không được bỏ qua chỉ vì heap RAM đã mất.

## Phụ thuộc bắt buộc

- `011a`: `tracker.reminder_time`/`reminder_text`, tracker health + `input_mode='event'`, và đường tạo `Entry`/privacy gate.
- `011c`: `subscription`, `subscription_expiry_lead_days` trong `app_setting`, `SubscriptionStore`, và deep-link `/subscription`.
- `011b`: VAPID, `push_subscription`, `reminder_dispatch`, `PushResult`, payload builder, service worker và confirmation endpoint.
- `docs/architecture-brief.md`, `docs/devops-brief.md`, `docs/schema-physical-brief.md`, `docs/auth-brief.md`, `docs/tracking-brief.md`.

Nếu một phụ thuộc chưa tồn tại hoặc đang khác hợp đồng trên, executor **dừng và báo đúng mâu thuẫn**; không tự thêm bảng/field/semantics để lấp chỗ trống.

### Dependency gate — không được vượt qua bằng stub

**Trạng thái đã kiểm trên đĩa ngày 2026-08-05:** `agent-tasks/011b-medication-reminder-webpush.md` mới là spec; backend chưa có các bảng/model/runtime service `push_subscription` và `reminder_dispatch`. Các symbol `SubscriptionStore`, `ReminderDispatcher`, `PushResult` và `build_medication_payload` cũng chưa phải importable implementation trên đĩa. Vì vậy 011d có thể được thiết kế/review trước, nhưng **chưa được thi công hoặc activate**.

Executor chỉ được mở gate sau khi:

1. `011a`, `011c`, `011b` đã được merge vào baseline đang thi công;
2. code thật của `SubscriptionStore`, `ReminderDispatcher`, `PushResult`, payload builder và service worker đã tồn tại, import được, đúng contract tương ứng;
3. migration/schema của 011b đã được áp vào DB đích theo quy trình migration thủ công của repo;
4. không dùng fake class, test stub hoặc import path tưởng tượng để làm acceptance xanh.

Nếu thiếu bất kỳ điều nào, báo **CHƯA verify được — dependency gate chưa mở** và dừng trước phần activate/production.

## Quy ước bằng chứng khi thi công

PR phải tách rõ:

> **Đã chạy:** lệnh nguyên văn + output thật.
>
> **CHƯA chạy:** lane nào chưa chạy và vì sao.
>
> **Vì sao vẫn tin là đúng:** lập luận từ code/spec, không gọi đó là bằng chứng runtime.

Một guardrail mới chỉ được tính là có bằng chứng khi đã cố ý làm nó **đỏ**, thấy đỏ đúng lý do, khôi phục code, rồi chạy **xanh** lại.

## 0. Bối cảnh & Lý do chọn scheduler in-process

### 0.1 Bài toán vận hành

microSched chạy trên đúng một Fly.io Machine `shared-cpu-1x` với **256 MB RAM**, process FastAPI sống liên tục. Neon Postgres có auto-idle; một vòng `SELECT` mỗi 1–5 phút sẽ giữ compute thức, đốt CU-h và đi ngược health-check boundary đã chốt:

- `/api/healthz` là liveness-only, tuyệt đối không query DB.
- `/api/readyz` được phép query nhưng không được dùng làm probe tự động.
- Không có job nền nào được biến thành DB poller.

Nhu cầu mới là nhắc theo giờ thật của từng tracker và nhắc subscription theo ngày hết hạn. Một scheduler bên ngoài theo ba khe cố định không cần thiết khi process đã always-on, và không thể ngủ chính xác tới `tracker.reminder_time` tuỳ ý.

### 0.2 Vì sao chọn scheduler in-process

Scheduler in-process giữ toàn bộ lịch trong RAM:

1. Startup/redeploy đọc một lần các nguồn lịch từ DB và rehydrate các `reminder_dispatch` row đang `pending` còn hạn recovery.
2. Timer dựng min-heap, lấy `due_at` nhỏ nhất.
3. `asyncio` ngủ tới timestamp kế tiếp; không có tick 60 giây, 5 phút hay 1 phút.
4. Khi tới giờ, timer gọi trực tiếp Web Push dispatcher của 011b, không gọi HTTP loopback.
5. Sau lần dispatch, timer đưa occurrence kế tiếp vào heap; mutation của user phát một event để rebuild heap.

Đây là lựa chọn phù hợp với quy mô single-user và một process: độ trễ thấp, không thêm Redis/Celery/worker, không chạm Neon trong lúc chờ. Đổi lại, lịch không bền trong RAM và bị mất khi process chết; điều đó được giải bằng **rebuild từ DB lúc startup/reload**, trong đó pending dispatch được nạp lại để tiếp tục retry, và bằng `reminder_dispatch` để chống gửi trùng.

### 0.3 Cổng quyết định trước khi bật

Owner đã chọn scheduler in-process là production target duy nhất và loại bỏ hoàn toàn Google Cloud Scheduler. Các decision record hiện hành vẫn nói ngược (`docs/architecture-brief.md` §3/§5; `docs/devops-brief.md` §10; `CLAUDE.md`), nên executor không được activate trước khi owner thêm dated note vào các record đó. 011b đã bỏ ba khe `08:00`/`15:00`/`19:00`; đây là thay đổi kiến trúc được owner chỉ đạo, không được suy ra chỉ từ việc app always-on:

- Timer dùng `tracker.reminder_time` **chính xác**, không lượng tử hoá qua `assign_slot()`.
- Timer giữ giờ `19:00` cho subscription expiry reminder, vì đó là nhắc theo ngày chứ không phải giờ thuốc.
- VAPID, payload, `reminder_dispatch` và confirmation của 011b được tái sử dụng; 011b sở hữu dispatcher, 011d sở hữu lịch/trigger.
- Google Cloud Scheduler, external reminder endpoint và mọi scheduler thứ hai đều không được hỗ trợ. `reminder_dispatch` idempotency là hàng rào recovery/chống duplicate, không phải giấy phép dual-run.

Loại Google Cloud Scheduler làm mất external retry policy, attempt deadline và result reporting độc lập với process FastAPI. 011d thay phần cần cho reminder bằng một contract cụ thể: tối đa 4 delivery attempts bền qua restart; backoff `30s → 2m → 10m`; timeout Web Push 20 giây; `pending` row recovery 24 giờ; structured receipt/log và supervision khiến process restart nếu loop chết. Đây vẫn **không tương đương hoàn toàn** với một monitor chạy ngoài app: Fly/process chết suốt outage dài không thể tự gửi alert độc lập. Contract đúng là lỗi không được chết im lặng trong process, pending vượt ngưỡng/hết quota để lại biên lai manual handling, và không hứa guaranteed delivery.

Trước khi bật `ENABLE_INPROCESS_CRON=true` trên Fly, chủ/T1 phải:

1. ghi **dated note** vào `docs/architecture-brief.md`, `docs/devops-brief.md` §10 và `CLAUDE.md`: Google Cloud Scheduler bị retirement hoàn toàn; 011d là owner duy nhất; nêu lý do, mất external retry/attempt deadline/result reporting và cơ chế thay thế;
2. xác nhận 011c rồi 011b đã merge, gồm settings, VAPID, `push_subscription`, `reminder_dispatch`, dispatcher, payload và confirmation thật; không dùng stub;
3. deploy với `ENABLE_INPROCESS_CRON=false` chỉ để xác nhận no-op/liveness. Đây **không** là mode external và không phát reminder;
4. deploy một SHA reviewed với `ENABLE_INPROCESS_CRON=true`, đúng một Fly Machine/process, rồi chứng minh startup queue, mutation reload, controlled dispatch, terminal/pending receipt và không có duplicate Entry;
5. sau receipt ở bước 4, xoá mọi Google Cloud Scheduler job còn tồn tại, gồm reminder và heartbeat, **và** xoá cron HTTP/token/workflow legacy theo §0.5; lưu biên lai vận hành rằng không còn external scheduler gọi app;
6. nếu cần abort sau khi GCS đã retire: đặt `ENABLE_INPROCESS_CRON=false`, fix/deploy lại và ghi rõ khoảng downtime không phát reminder. **Không** recreate GCS, GitHub schedule, cron HTTP hay fallback external.

Trong thời gian DRAFT, mặc định an toàn là `ENABLE_INPROCESS_CRON=false`; code không được tự bật timer chỉ vì module đã được import.

**Mẫu dated note bắt buộc khi chủ duyệt và chuẩn bị activate** (ghi vào đúng decision record, không chỉ ghi trong PR):

> **2026-08-06 — Thay thế hoàn toàn Google Cloud Scheduler bằng 011d.** microSched không còn mode external và không giữ Google Cloud Scheduler job, gồm reminder lẫn heartbeat. `ENABLE_INPROCESS_CRON=true` chạy một `CronTimer` trong process FastAPI: nạp lịch vào RAM, ngủ tới due time và recover `reminder_dispatch` pending từ Neon. Default vẫn `false` như safety gate trước activation, không phải fallback scheduler. Đánh đổi: không còn external retry policy, attempt deadline và result reporting độc lập; thay bằng tối đa 4 attempts bền qua restart, backoff `30s → 2m → 10m`, deadline network 20 giây, pending recovery 24 giờ và structured process observability/supervision. Chỉ retire GCS sau receipt của một deploy 011d running với một Fly process owner; rollback chỉ là flag false + fix/deploy, không dựng lại external scheduler.

Executor không tự sửa dated note này trong lượt thi công 011d; owner/T1 phải áp dụng đúng record trước production cutover.

### 0.4 Việc của CHỦ trước khi giao thi công

- [ ] Xác nhận 011a, 011c, 011b đã merge và các implementation/schema thật của chúng đã có trên đĩa/DB; không dùng stub để giả vờ đủ phụ thuộc.
- [ ] Thêm dated note vào `docs/architecture-brief.md`, `docs/devops-brief.md` và `CLAUDE.md` trước khi đổi config production.
- [ ] Xác nhận external retry/attempt deadline/result reporting được thay bằng bounded retry + pending recovery/observability, và chấp nhận phần không tương đương.
- [ ] Sau dispatch receipt của 011d, xoá mọi Google Cloud Scheduler job hiện có, gồm heartbeat, cùng cron HTTP/token/workflow legacy; không thay bằng scheduler external khác.
- [ ] Nếu chạy PG integration test: bật Docker Desktop trước. Nếu quên, lỗi kiểu `permission denied while trying to connect to the Docker API at npipe:////./pipe/dockerDesktopLinuxEngine` là blocker môi trường, không được chuyển sang Neon hoặc host Postgres.
- [ ] Chỉ dùng DB local throwaway cho test PG; không dùng Neon production, `microschedule_v2` hoặc DB chung của máy.
- [ ] VAPID private key, `DATABASE_URL` và các secret khác chỉ ở `.env`/Fly secret; không đưa vào prompt, diff, log hay artifact.
## 1. Quyết định kiến trúc & In-Memory Priority Queue

### 1.1 Một owner cho lịch reminder

Trong process có đúng **một** `CronTimer` và đúng **một** `asyncio.Task` sở hữu vòng lặp timer. Không tạo một task cho mỗi tracker/subscription.

`ENABLE_INPROCESS_CRON` là boolean, default `False` để một deploy chưa qua cutover không âm thầm bật reminder:

| `ENABLE_INPROCESS_CRON` | `CronTimer` | Reminder emission | Nguồn reminder |
|---|---|---|---|
| `False` | không được khởi tạo | không phát reminder; chỉ dùng trước cutover/test liveness | không có |
| `True` | chạy đúng một task ở lifespan | timer gọi dispatcher nội bộ 011b | `CronTimer` |

011d không giữ Google Cloud Scheduler heartbeat job và không định nghĩa scheduler external thay thế. Observability của timer là structured log + snapshot RAM; không dùng heartbeat để đánh thức timer và không biến bất kỳ heartbeat nào thành reminder scheduler.

Khi `ENABLE_INPROCESS_CRON=False`, đây là **no-op hoàn toàn**: không import/khởi tạo `CronTimer`, repository, dispatcher, `asyncio.Event`, background task, reload middleware/dependency override hay timer DB session; `get_session()` giữ nguyên contract hiện tại và **không có nguồn reminder khác**. Không log “timer started” ở mode này. Production không được coi trạng thái này là vận hành reminder.

### 1.1a One-way retirement của cron HTTP cũ

011d không kế thừa route `POST /api/cron/heartbeat`, `CRON_TOKEN`, Google Cloud Scheduler hay GitHub
workflow `cron.yml`. Đây là artifact legacy đã từng kiểm dây điện, không phải monitoring hoặc fallback
được phép giữ lại. Trong cùng release/cutover sau khi 011d đang chạy và có receipt §6.5, executor/owner
phải hoàn tất toàn bộ:

1. xoá router `/api/cron`, dependency `require_cron_token`, setting/env/example `CRON_TOKEN`, workflow
   `.github/workflows/cron.yml`, test endpoint/auth tương ứng và GitHub/Fly secret cùng tên;
2. giữ `app/core/process_stats.py` như helper nội bộ cho snapshot RSS/uptime của timer, chuyển test
   thuần của nó sang `test_process_stats.py`; `restart_advised` chỉ là metadata/log signal, **không**
   tự restart process;
3. xoá mọi GCS job sau khi list đúng project/region/job name; lưu output không secret chứng minh không
   còn job gọi app; không pause job để tạo fallback ẩn;
4. kiểm toàn repo hiện hành không còn `CRON_TOKEN`, `/api/cron`, `cron_router`, `require_cron_token`
   hoặc `cron.yml` ngoài record lịch sử được gắn nhãn legacy/superseded.

Remote secret/job là thao tác khó hoàn tác: phải list/read-only đúng target trước rồi mới xoá. Không có
trường hợp nào `ENABLE_INPROCESS_CRON=false` được phép bật lại cron cũ — trạng thái đó chỉ nói rõ
reminder đang downtime chờ fix/deploy.
### 1.2 Hình dạng queue item

Heap chỉ lưu dữ liệu tối thiểu để định thời; **không giữ SQLModel instance, tên đã giải mã, `reminder_text`, payload Web Push, VAPID key hay token**.

```python
class ScheduleKind(StrEnum):
    TRACKER = "tracker"
    SUBSCRIPTION = "subscription"


@dataclass(frozen=True, slots=True)
class TimerItem:
    due_at: datetime          # aware, Asia/Ho_Chi_Minh fixed +07:00
    occurrence_on: date       # ngày nghiệp vụ VN dùng cho reminder_dispatch
    kind: ScheduleKind
    subject_id: UUID          # tracker.id hoặc subscription.id
    reminder_time: time | None = None
    expires_on: date | None = None
    retry_count: int = 0
    dispatch_id: UUID | None = None  # chỉ có ở pending-recovery item
    is_pending_recovery: bool = False
```

Trong heap, dùng tuple có tie-breaker xác định:

```text
(due_at, kind_order, subject_id.int, occurrence_on, retry_count, item)
```

Không so sánh trực tiếp hai `TimerItem` có enum/UUID chưa định thứ tự. `kind_order` cố định (`tracker` trước `subscription`) chỉ để test và log deterministic, không mang ý nghĩa product.

### 1.3 Nguồn schedule và cách tính `due_at`

#### Tracker reminder

Nạp những tracker thỏa tất cả điều kiện:

- `deleted_at IS NULL`;
- `reminder_time IS NOT NULL`;
- `kind = 'health'` và `input_mode = 'event'`;
- không dùng `readable()` với fabricated session; timer không có user session.

`reminder_time` là `TIME` lặp hằng ngày. Với `now_vn = datetime.now(VN_TZ)`, occurrence kế tiếp là ngày hôm nay nếu `reminder_time` còn ở tương lai, nếu không thì ngày mai. Ghép ngày + giờ thành aware `due_at` ở fixed offset `+07:00`.

Timer **không gọi `assign_slot()`**. `assign_slot()`/`REMINDER_SLOTS` không thuộc 011b/011d và không được tái lập dưới tên khác; không được áp lượng tử hoá vào exact-time reminder.

#### Subscription expiry reminder

Nạp những subscription thỏa:

- `deleted_at IS NULL`;
- `canceled_at IS NULL`;
- `expires_on >= today_vn`;
- parent tracker còn sống theo invariant của 011c.

Đọc ngưỡng bằng `expiry_lead_days(db)` của 011c, không đọc `AppSetting` tự do và không hard-code `3`. Gọi `L = subscription_expiry_lead_days`.

Subscription chỉ có một reminder mỗi ngày lúc `SUBSCRIPTION_REMINDER_TIME = time(19, 0)`:

```text
first_date = max(today_vn, expires_on - L ngày)
candidate dates = first_date ... expires_on, mỗi ngày một occurrence
due_at = candidate date 19:00 +07:00
```

Nếu `19:00` hôm nay đã qua thì candidate đầu tiên là ngày mai, miễn vẫn `<= expires_on`. Subscription đã hết hạn, đã huỷ, bị xoá mềm hoặc parent tracker không hợp lệ không được đưa vào heap. Điều kiện eligibility vẫn phải được kiểm lại tại dispatch để bảo vệ trước thay đổi ngoài đường API.

### 1.4 Vòng đời heap và khôi phục pending sau crash

`CronTimer` có ba trạng thái logic: `STARTING`, `RUNNING`, `DEGRADED`. Không cần persist state này vào DB.

Luồng chính:

1. Load schedule từ DB vào một heap cục bộ.
2. Trong cùng một snapshot query/session, load thêm các row `reminder_dispatch` có `status='pending'` và `COALESCE(last_attempt_at, created_at) >= now - PENDING_RECOVERY_TIMEOUT`; chỉ row `attempt_count < 4` được chuyển thành `TimerItem` với **cùng** `subject_type`, `subject_id`, `dispatched_on` (map ngược thành `kind`, `subject_id`, `occurrence_on`), giữ nguyên `dispatch_id` và retry metadata. Không tạo dispatch ID mới. Pending-recovery item có `due_at = max(now_vn, last_attempt_at + bounded_backoff(attempt_count))`, không bị đặt vào quá khứ để bắn dồn.
3. Với pending row không còn hợp lệ (subject đã bị xoá/huỷ, payload contract không còn phù hợp, vượt 24 giờ hoặc `attempt_count >= 4`), không gửi mù và **không tự xoá/đổi status** trong 011d: log structured `cron_timer_pending_manual_required` (phân biệt `expired`/`exhausted`/`ineligible`), tăng counter, rồi schedule occurrence tương lai nếu subject còn lịch. Nếu 011b cần chuyển row sang trạng thái terminal hoặc manual-recovery state, đó phải là contract có sẵn của 011b; 011d không tự phát minh status mới trong bảng của 011b.
4. Deduplicate pending recovery với item lịch cùng occurrence bằng khóa `(kind, subject_id, occurrence_on)`; pending item thắng item mới để tiếp tục cùng `dispatch_id`/row.
5. Nếu load thành công, swap heap mới vào một lần; không để heap nửa cũ/nửa mới.
6. Nếu heap rỗng, `await reload_event.wait()`; không có timeout tick.
7. Nếu heap có item, tính `delay = max(0, (heap[0].due_at - now_vn).total_seconds())`.
8. Chờ bằng `asyncio.wait_for(reload_event.wait(), timeout=delay)` và phân biệt rõ:
   - `TimeoutError` ⇒ đây là due deadline bình thường; pop tất cả item `due_at <= now_vn`, xử lý batch tuần tự, rồi schedule occurrence kế tiếp;
   - event trả về trước deadline ⇒ clear event đúng cách, rebuild heap sau commit;
   - `asyncio.CancelledError` ⇒ ném lại ngay để lifespan shutdown, tuyệt đối không coi là timeout/retry và không log như lỗi dispatch.
9. Sau mỗi batch, nếu event đã được set trong lúc dispatch, bỏ heap cũ và rebuild; không tiếp tục tin lịch stale.

Shape bắt buộc của đoạn chờ, để không có `except Exception` nuốt cancellation:

```python
try:
    await asyncio.wait_for(reload_event.wait(), timeout=delay)
except asyncio.TimeoutError:
    await dispatch_due_batch()
except asyncio.CancelledError:
    raise
else:
    reload_event.clear()
    await reload_snapshot(reason="mutation")
```

Không dùng `while True: sleep(60)` hoặc `SELECT ... WHERE due_at <= now()`.

### 1.5 Occurrence, late item và retry

`occurrence_on` là ngày của **lần nhắc dự định**, không phải ngày timer tình cờ retry. Nó được truyền vào dispatcher để mọi retry dùng đúng cùng key `(subject_type, subject_id, occurrence_on)` của `reminder_dispatch`.

DRAFT này chọn một grace window hữu hạn `MISSED_OCCURRENCE_GRACE = 15 phút`:

- startup/reload có thể enqueue occurrence vừa quá giờ nhưng chưa quá 15 phút;
- occurrence quá grace bị bỏ qua và chuyển sang occurrence kế tiếp;
- không catch-up vô hạn nhiều ngày, không bắn một loạt notification sau downtime dài.

Đây là một judgment call có thể veto trước khi thi công. Nếu chủ bỏ grace, chỉ đổi một hằng số và test “restart sát giờ”; không phát minh cơ chế replay khác.

Lỗi tạm thời của DB hoặc Web Push không được biến thành poller. Đây là contract exact, không phải
“retry bounded” chung chung:

- dispatcher giữ nguyên `reminder_dispatch.id`/row ở `pending` theo 011b;
- `attempt_count` là quota durable do 011b claim/increment: tối đa **4 delivery attempts tổng cộng**
  (lần đầu + 3 retry), không reset qua heap/reload/redeploy;
- retry sau attempt 1/2/3 dùng đúng row/id/occurrence với backoff **30 giây → 2 phút → 10 phút**;
  sau attempt 4 tuyệt đối không enqueue/query retry nữa;
- mỗi Web Push network attempt có deadline **20 giây**; timeout là `TEMPORARY_FAILURE`, giải phóng
  DB transaction/lock trước khi schedule retry;
- sau quota hết, log `cron_timer_dispatch_exhausted` kèm `dispatch_id`, kind, subject UUID,
  occurrence, attempt count; tăng counter/manual-required signal. Không đổi/xoá status `pending`
  chỉ để làm dashboard xanh; occurrence ngày sau vẫn là một key mới;
- retry vượt nửa đêm vẫn giữ `occurrence_on` cũ và không được tạo row cho ngày mới.

Backoff này chỉ tồn tại sau một dispatch/reload failure đã biết, không phải một nhịp poll khi hệ thống bình thường.

`PENDING_RECOVERY_TIMEOUT` là một hằng số typed, **khóa `timedelta(hours=24)`**, có test biên và log tuổi row:

```python
PENDING_RECOVERY_TIMEOUT: Final[timedelta] = timedelta(hours=24)
```

Không dùng quy tắc “quá 15 phút thì bỏ” cho pending row: **grace window của occurrence và timeout recovery của dispatch là hai khái niệm khác nhau**. Một pending row trong cửa sổ recovery và còn `attempt_count < 4` có thể được retry dù occurrence đã quá `MISSED_OCCURRENCE_GRACE`, vì notification đã được claim trước crash; ngược lại occurrence chưa từng claim vẫn tuân grace window. Pending row vượt 24 giờ hoặc đã hết quota phải được đo/log bằng `cron_timer_pending_manual_required`, giữ nguyên row và không âm thầm biến mất.

## 2. Chi tiết module backend

### 2.1 `backend/app/core/cron_timer.py`

Đây là module điều phối lifecycle và heap, không gửi Web Push trực tiếp.

Nên có các thành phần sau:

```python
class CronTimer:
    def request_reload(self, reason: str = "mutation") -> None: ...
    async def run(self) -> None: ...
    async def stop(self) -> None: ...


class ScheduleRepository(Protocol):
    async def load(self, now_vn: datetime) -> ScheduleSnapshot: ...


class ReminderDispatcher(Protocol):
    async def dispatch(self, item: TimerItem) -> DispatchOutcome: ...
```

`ScheduleSnapshot` chỉ chứa các `TimerItem` + số liệu observability (`tracker_count`, `subscription_count`, `pending_recovered_count`, `pending_expired_count`, `pending_exhausted_count`, `pending_manual_required_count`, `lead_days`, `loaded_at`). Repository tạo session ngắn bằng `get_sessionmaker()`, chạy query projection cho tracker/subscription **và pending dispatch recovery** chỉ lấy ID/thời gian/ngày cần thiết, rồi đóng session trước khi timer ngủ.

`CronTimer` nhận `clock`/`now_vn` injectable và `ScheduleRepository`/`ReminderDispatcher` injectable để unit test không cần Neon, không cần VAPID và không phải chờ đồng hồ thật.

Các invariant bắt buộc trong module:

- heap chỉ được thay thế sau load thành công;
- `request_reload()` chỉ `Event.set()`, không query và không tạo task mới;
- `CancelledError` phải được ném lại để lifespan shutdown sạch;
- exception của một item không làm chết main loop;
- mọi `asyncio.Task` do timer tạo phải được lifecycle sở hữu và await; tốt nhất loop không tạo child task nào.
- `wait_for()` phải bắt `TimeoutError` như due deadline, bắt lại và ném `asyncio.CancelledError`, không dùng `except Exception`/`except TimeoutError` rộng đến mức nuốt cancellation.

Log tối thiểu, không chứa payload/private plaintext:

```text
cron_timer_started mode=inprocess
cron_timer_queue_loaded reason=startup tracker_count=... subscription_count=... lead_days=...
cron_timer_pending_recovery recovered=... expired=... skipped=...
cron_timer_reload_requested reason=...
cron_timer_dispatch_started kind=... subject_id=... occurrence_on=...
cron_timer_dispatch_finished kind=... subject_id=... outcome=... retry_count=...
cron_timer_reload_failed reason=... error_type=...
cron_timer_dispatch_exhausted kind=... subject_id=... occurrence_on=...
cron_timer_pending_manual_required reason=expired|exhausted|ineligible dispatch_id=... kind=... subject_id=... occurrence_on=... attempt_count=...
cron_timer_stale reason=... queue_size=... next_due_at=... last_reload_at=... last_dispatch_at=...
cron_timer_loop_failed phase=reload|dispatch|unexpected consecutive_failures=... error_type=...
cron_timer_stopped
```

Không log tên tracker/subscription, `reminder_text`, ciphertext, endpoint push, VAPID key, cookie hoặc bearer token.

Vì Fly proxy không quan sát được công việc sinh ra sau response, các metric/log này là bắt buộc để biết background task còn sống: `cron_timer_running`/heartbeat process-local, `queue_size`, `next_due_at`, `last_reload_at`, `last_dispatch_at`, `last_dispatch_outcome`, `pending_recovered_count`, `pending_expired_count`, `pending_exhausted_count`, `pending_manual_required_count`, `consecutive_loop_failures`, `uptime_s` và RSS. `cron_timer_stale` chỉ hợp lệ khi (a) heap có due deadline đã qua mà chưa dispatch quá grace, hoặc (b) reload/retry loop đang failure; heap rỗng hay đang ngủ tới nhiều ngày **không** stale. Chỉ expose metadata không nhạy cảm; không tạo health probe query Neon. `/api/readyz` không được biến thành timer health check. Nếu timer loop chết hoặc stale, phải phát `cron_timer_stale`/`cron_timer_loop_failed` và manual signal rõ ràng; không trả “healthy” giả.

### 2.2 Repository nạp queue

Repository có thể nằm trong `cron_timer.py` lúc v1 hoặc tách thành `app/domain/reminder_schedule.py`; không được rải query vào `main.py` hay vòng `run()`.

Query phải:

- dùng runtime `DATABASE_URL`/role `microsched_app`, không dùng `NEON_OWNER_URL`/`NEON_MIGRATOR_URL`;
- projection ID + `reminder_time`/`expires_on` + cờ cần để tính lịch, không load toàn model nếu không cần;
- đọc `reminder_dispatch` pending bằng `status='pending'`, `created_at`/`last_attempt_at` và các field cần map về occurrence; **không** load push payload hoặc private plaintext để rehydrate;
- áp `deleted_at IS NULL` ở parent/subject theo §1.3;
- đọc `subscription_expiry_lead_days` qua allowlist helper của 011c;
- không giải mã tên/tiền chỉ để dựng heap;
- đóng session sau snapshot.

Nếu query reload thất bại, giữ heap gần nhất còn hợp lệ, chuyển `DEGRADED`, log lỗi và retry **30 giây → 2 phút → 10 phút**. Không được thay heap bằng rỗng rồi biến lỗi DB thành “không có reminder”. Hết ba retry liên tiếp phải log `cron_timer_loop_failed phase=reload` rồi làm `timer.run()` thất bại để lifespan supervision fail process/Fly restart; startup recovery mới được chạy lại. Không chờ mutation event trong trạng thái phục vụ HTTP nhưng timer đã chết, và không tự query mãi.

Reload phải recover pending rows **cả ở startup và ở mỗi reload event**, vì một mutation/redeploy có thể xảy ra sau crash. Nếu reload event liên tục dồn lại, coalesce thành một lần snapshot; không được bỏ qua pending recovery khi “chỉ có tracker/subscription thay đổi”.

### 2.3 Dispatcher boundary với 011b

011d gọi một service nội bộ của 011b, ví dụ `ReminderDispatcher.dispatch(item)`. Không import router và không gọi `httpx` tới chính app.

Dispatcher phải:

1. kiểm tra lại subject còn eligible và lấy payload bằng builder 011b;
2. map `TimerItem.kind` sang `reminder_dispatch.subject_type` (`tracker` hoặc `subscription`), map `occurrence_on` sang `dispatched_on`, rồi claim/load theo `(subject_type, subject_id, dispatched_on)` với state machine 011b;
3. gửi tới các `push_subscription` bằng VAPID private key chỉ nằm trong server process;
4. ghi `sent`, `no_device` hoặc giữ `pending` đúng `PushResult`;
5. đóng transaction DB trước khi gọi mạng nếu implementation giữ lock sẽ lâu; không giữ transaction mở quanh toàn bộ Web Push call;
6. trả về outcome có cấu trúc, không trả `bool` làm mất thông tin retry.

Timer không tự tạo `Entry`. Confirmation route của 011b mới tạo tối đa một Entry cho tracker reminder, chịu session/private gate và dùng `dispatch_id` idempotency.

### 2.4 Settings và app state

Thêm setting typed vào `app/core/settings.py`:

```python
enable_inprocess_cron: bool = False
```

Tên env tương ứng là `ENABLE_INPROCESS_CRON`. DRAFT/prod mặc định `False`. Production in-process phải fail-fast khi thiếu `DATABASE_URL`, 011b implementation/schema hoặc VAPID configuration bắt buộc; local không có DB có thể khởi động ở chế độ timer disabled để test các route liveness. Không giữ `CRON_SCHEDULER_MODE`, alias lâu dài hay config nào diễn tả mode external; nếu branch thử nghiệm đã thêm tên cũ thì executor phải xoá/deprecate nó mà không tạo fallback scheduler.

Đặt các object sau vào `app.state` để test/lifecycle nhìn thấy được:

```text
app.state.cron_timer
app.state.cron_timer_task
```

Không dùng global singleton có task tự chạy lúc import module.

Khi `enable_inprocess_cron` là `False`, `build_cron_timer_if_enabled()` phải trả `None` trước mọi import khởi tạo dependency, session factory, `asyncio.Event` hoặc metric task. Không sửa `get_session()` để phát event, không thêm middleware/contextvar và không thêm request overhead ở mode disabled.

`CronTimer.health_snapshot()` phải là hàm đọc RAM, không query DB, trả tối thiểu `enabled`, `running`, `degraded`, `queue_size`, `next_due_at`, `last_reload_at`, `last_dispatch_at`, `last_dispatch_outcome`, `pending_recovered_count`, `pending_expired_count`, `pending_exhausted_count`, `pending_manual_required_count`, `consecutive_loop_failures`, `uptime_s` và `rss_kb`. 011d không thêm endpoint để expose snapshot; nếu sau này cần expose ngoài process, đó là task riêng có auth/audit rõ ràng. Không tạo public health endpoint mới và không trỏ Fly probe vào endpoint có DB.

## 3. Tương thích Web Push (011b) & Neon Idle Protection

### 3.1 Tương thích Web Push

011d phải giữ nguyên các hợp đồng sau của 011b:

- payload medication dùng `dispatch_id` và `/reminder-confirm?dispatch=<id>`;
- payload subscription dùng `/subscription?highlight=<id>` và không tự ghi Entry;
- private parent không được rò tên ra lock-screen; `reminder_text` trần vẫn được phép vì đó là bề mặt kín đáo do user tự chọn;
- `PushResult.SENT`, `TEMPORARY_FAILURE`, `DEAD_SUBSCRIPTION` không bị gộp thành boolean;
- `410/404` dọn push subscription chết; lỗi mạng/5xx tạm thời không xoá;
- mixed dead + temporary giữ cùng dispatch row/id ở `pending`;
- `sent` hoặc `no_device` là terminal; retry không gửi lại terminal row;
- hai thiết bị tap cùng notification vẫn chỉ có một `Entry` qua `confirmed_entry_id`.

011b cần expose service dùng chung nhận `TimerItem`/`occurrence_on`. Tên/type thật của service phải được lấy từ implementation 011b sau khi merge; không tự tạo import path `ReminderDispatcher` nếu symbol đó chưa tồn tại. Không giữ endpoint, wrapper legacy hay code path external cho reminder.

### 3.2 Chính sách query Neon

| Tình huống | Query Neon | Kết nối trong lúc chờ |
|---|---:|---|
| App startup/redeploy | một lần load snapshot | đóng sau snapshot |
| User commit thay đổi schedule | một lần reload theo `asyncio.Event` | đóng sau snapshot |
| Heap rỗng | không query | không có connection |
| Heap đang ngủ tới `due_at` | không query | không có connection |
| Due occurrence | query/transaction ngắn của dispatcher 011b | đóng sau state update |
| Push network call | không giữ transaction/connection nếu có thể | không giữ lock DB quanh network |
| `/api/healthz` | không query | không áp timer vào healthz |

Không gọi `check_database()`, `/api/readyz`, `SELECT 1` hoặc `pool_pre_ping` chủ động trong mỗi vòng timer. `pool_pre_ping` của engine hiện có chỉ được để SQLAlchemy xử lý khi một session thật sự được mở; nó không phải lịch poll của timer.

Nếu không có item nào, process chỉ chờ `Event`; Fly vẫn sống nhưng Neon được ngủ. Nếu có lỗi thật cần retry, backoff hữu hạn ở §1.5 là ngoại lệ có nguyên nhân và có điểm dừng, không được mở rộng thành health loop.

### 3.3 Bộ nhớ 256 MB

- Không cache full rows hoặc toàn bộ push subscription.
- Không cache decrypted payload/name.
- Chỉ giữ ID, mốc thời gian, kind và counter nhỏ trong heap.
- Mỗi reload xây snapshot cục bộ rồi bỏ snapshot cũ sau swap để không giữ hai bản lớn hơn cần thiết.
- Không dùng unbounded retry list; retry item thay thế cùng occurrence, không nhân bản vô hạn.
- Log queue count/RSS ở mức metadata; không dump heap đầy đủ trong production log.

## 4. Event reload mechanism & Lifespan hook

### 4.1 Phát event sau commit, không phát sau `flush`

Reload phải xảy ra **sau khi transaction HTTP commit thành công**. Phát event trong domain method trước commit sẽ tạo race: timer có thể đọc snapshot chưa commit, hoặc rebuild một dữ liệu sẽ bị rollback.

Đặt một marker dùng chung trong `db.info`, ví dụ:

```python
CRON_TIMER_RELOAD_INFO_KEY = "microsched.cron_timer.reload"


def mark_cron_timer_reload(db: AsyncSession, reason: str) -> None:
    db.info[CRON_TIMER_RELOAD_INFO_KEY] = reason
```

Các đường phải mark:

| Mutation | Khi nào mark |
|---|---|
| `tracker` create | tạo tracker có/không có `reminder_time` đều được mark; rẻ và tránh bỏ sót |
| `tracker` update | Chụp `old_reminder_time` trước `flush`, tính giá trị mới sau validate, và chỉ mark nếu `old_reminder_time != new_reminder_time` (bật/tắt/đổi giờ). Đổi `reminder_text`, name, color hoặc field không ảnh hưởng schedule **không** mark; payload đọc lúc dispatch nên không cần reload heap. |
| tracker soft-delete/restore | luôn mark vì subject có thể vào/ra eligibility |
| `subscription` create/update | `expires_on`, `canceled_at`, `deleted_at`, `tracker_id` hoặc trạng thái eligibility đổi |
| subscription cancel/uncancel/soft-delete/restore/renew | luôn mark |
| `app_setting` update | chỉ khi key `subscription_expiry_lead_days` đổi |

#### Giữ nguyên contract của `get_session()` bằng ContextVar có điều kiện

Code thật hiện tại là `async def get_session() -> AsyncIterator[AsyncSession]`, **không nhận `Request`**; các router dùng `Depends(get_session)`/`Annotated[..., Depends(get_session)]`. 011d **không** đổi signature này và không buộc 100% protected route phải nhận thêm dependency parameter.

Chọn mechanism `ContextVar` + middleware chỉ được đăng ký khi `ENABLE_INPROCESS_CRON=True`:

```python
cron_reload_sink: ContextVar[ReloadSink | None] = ContextVar(
    "microsched_cron_reload_sink", default=None
)


@app.middleware("http")
async def cron_reload_context(request: Request, call_next):
    token = cron_reload_sink.set(getattr(request.app.state, "cron_timer", None))
    try:
        return await call_next(request)
    finally:
        cron_reload_sink.reset(token)
```

`get_session()` vẫn giữ nguyên signature và transaction contract, chỉ thêm post-commit hook nội bộ:

```python
async def get_session() -> AsyncIterator[AsyncSession]:
    ...
    async with factory() as db:
        try:
            yield db
            await db.commit()
        except asyncio.CancelledError:
            await db.rollback()
            db.info.pop(CRON_TIMER_RELOAD_INFO_KEY, None)
            raise
        except Exception:
            await db.rollback()
            db.info.pop(CRON_TIMER_RELOAD_INFO_KEY, None)
            raise
        else:
            reason = db.info.pop(CRON_TIMER_RELOAD_INFO_KEY, None)
            sink = cron_reload_sink.get()
            if sink is not None and reason is not None:
                sink.request_reload(reason)
```

Đây là thay đổi nội bộ của dependency, không đổi object được yield, commit/rollback semantics hay API route. `ContextVar` được reset trong `finally`; không để sink của app này rò sang request/task khác. Unit test gọi `get_session()` không cần tạo `Request`; test post-commit reload có thể set ContextVar bằng helper fixture hoặc chạy qua ASGI request. Các đường ghi nội bộ ngoài HTTP phải dùng helper scope tương đương và gọi notifier sau commit; không tự gán global timer.

**Zero-overhead khi timer disabled:** khi `ENABLE_INPROCESS_CRON=False`, middleware trên không được đăng ký, `app.state.cron_timer` không được tạo, không có `asyncio.Event`/background task/repository/dispatcher, và `cron_reload_sink` giữ default `None`. `get_session()` không query thêm, không tạo task và không phát event; marker `db.info` nếu mutation helper đặt vào chỉ là metadata trong session và được pop sau commit/rollback, không thêm round-trip hay latency DB đáng kể. Nếu muốn loại cả marker branch khỏi code path, helper mutation phải được bind sau khi feature enabled, nhưng không được làm thay đổi transaction contract hiện tại.

`request_reload()` không await DB và không tạo `asyncio.create_task`; nó chỉ set một `asyncio.Event`, để đúng một loop timer xử lý việc reload.

Nếu có đường ghi nội bộ không đi qua `get_session()`, đường đó phải tự gọi notifier sau commit hoặc dùng helper transaction chung. Không coi “router hiện tại đã mark” là bằng chứng cho mọi caller tương lai.

### 4.2 Lifespan trong `app/main.py`

Dùng một `asynccontextmanager` duy nhất cho FastAPI:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    timer = build_cron_timer_if_enabled()
    app.state.cron_timer = timer
    app.state.cron_timer_task = None
    if timer is not None:
        app.state.cron_timer_task = asyncio.create_task(
            timer.run(), name="microsched-cron-timer"
        )
    try:
        yield
    finally:
        if timer is not None:
            await timer.stop()
        task = app.state.cron_timer_task
        if task is not None:
            await task
```

Đoạn trên là shape, không phải code copy mù. Executor phải bảo đảm:

- `FastAPI(..., lifespan=lifespan)` được dùng; không đồng thời thêm `@app.on_event("startup")` cho cùng timer;
- `timer.run()` tự load snapshot đầu tiên với `reason="startup"` trước khi ngủ;
- shutdown cancel/await task, không để `Task was destroyed but it is pending`;
- `CancelledError` không bị catch thành lỗi dispatch;
- `ENABLE_INPROCESS_CRON=False` không tạo task, middleware, `ContextVar` sink binding, repository, dispatcher hoặc timer DB session;
- `ENABLE_INPROCESS_CRON=True` tạo **đúng một** task kể cả khi `create_app()` được gọi nhiều lần trong test — mỗi app instance có state riêng, không có module-global task;
- mode in-process local thiếu DB chỉ log disabled/no-op theo policy local, còn production thiếu cấu hình/dependency bắt buộc phải fail-fast thay vì chạy “xanh giả” với heap rỗng;
- nếu timer loop không còn reload/dispatch trong ngưỡng stale đã cấu hình, health snapshot phải chuyển `stale`/`degraded` và structured log phải phát signal; không báo healthy chỉ vì process vẫn nhận HTTP.

### 4.3 Race giữa reload và due dispatch

Nếu user sửa reminder đúng lúc timer đang dispatch:

- event không huỷ giữa chừng một network call đang chạy;
- dispatcher đọc lại subject hiện tại và kiểm eligibility ngay trước claim/send;
- event vẫn giữ trạng thái set nếu commit xảy ra trong lúc dispatch;
- sau dispatch, timer reload snapshot mới trước khi ngủ tiếp;
- `reminder_dispatch` unique key + row lock/advisory lock của 011b là lớp chống duplicate cuối cùng.

Không dùng `heap` cũ để suy ra payload. Heap chỉ trả lời “có thể tới giờ”; DB/dispatcher trả lời “hiện còn được phép gửi không”.

## 5. Security, Privacy (R1–R7), Error Handling

### 5.1 Security boundary

- Timer không có user session và không nhận input HTTP trực tiếp.
- Timer gọi service nội bộ, không gọi route reminder external và không tự chế bearer token.
- `DATABASE_URL` là runtime least-privilege role; tuyệt đối không dùng migrator/owner.
- VAPID private key chỉ đọc ở backend settings/secret store; không vào heap, queue log hoặc response.
- Push endpoint được validate SSRF ở 011b lúc registration; timer không chấp nhận endpoint mới từ item.
- Không thêm endpoint “reload queue” công khai. Reload đến từ commit marker trong process; nếu sau này cần nút vận hành, đó là task riêng với auth/audit rõ ràng.
- Không xem `reminder_dispatch.subject_id` là bí mật để đưa vào notification URL ngoài hợp đồng 011b; URL medication dùng dispatch ID, không dùng tracker ID/name.

### 5.2 Privacy theo R1–R7

| Rule | Hợp đồng của timer |
|---|---|
| **R1 — một cổng read** | Timer không giả lập session unlocked và không gọi `readable()` để lách gate. Queue chỉ giữ ID/time. Dispatcher 011b tự đọc subject/payload theo hợp đồng reminder; private tracker/subscription phải generic hoặc dùng đúng `reminder_text` trần đã được user chọn. |
| **R2 — không lật luật index** | Không embedding, FTS, semantic search hay index mới. Không đưa ciphertext/name vào heap. |
| **R3 — provider route** | Timer không gọi LLM/provider. Không có private content nào được đưa ra ngoài. Nếu tương lai thêm AI vào background job, đó không thuộc 011d và phải tuân `zdr`/no-train của R3. |
| **R4 — transcript** | Timer không đọc/ghi message transcript và không tạo audit payload chứa nội dung notification. |
| **R5 — background AI public-only** | Timer không phải AI job và không được suy ra private gate từ session. Reminder là user-enabled Web Push exception của 011b: private tracker vẫn có thể được nhắc, nhưng lock-screen payload không được fallback tên private; subscription private dùng thông báo generic. |
| **R6 — client cache** | Queue chỉ ở RAM server; không persist xuống disk/IndexedDB. Service worker nhận payload đã sanitize; private plaintext không được thêm vào cache. |
| **R7 — write tools** | Timer không ghi private domain data và không tự tạo Entry. Confirmation của 011b mới là write path, phải có session, private unlock, idempotency và audit contract. |

`reminder_text` là ngoại lệ có chủ đích: nó là text trần do user tự nhập để kiểm soát độ kín đáo trên lock-screen. Không thay nó bằng ciphertext và không dùng nó làm lý do để fallback tên private.

### 5.3 Error handling

- Lỗi một tracker/subscription chỉ làm occurrence đó fail/skip; không làm chết timer loop.
- `CancelledError` luôn được re-raise.
- Lỗi parse/config startup có message rõ (`ENABLE_INPROCESS_CRON`, DB, 011b dependency, VAPID), không nuốt thành queue rỗng.
- Lỗi reload giữ heap cũ, log structured error, retry hữu hạn; không xóa lịch tốt cuối cùng.
- Lỗi Web Push tuân `PushResult`; không xoá subscription khi lỗi tạm thời.
- Lỗi DB sau due occurrence dùng cùng dispatch key và retry bounded; không insert dispatch row mới cho một retry.
- Lỗi không được log `str(payload)`, exception có thể chứa URL/token, ciphertext hoặc response body từ push service. Log `error_type`, kind, subject UUID, occurrence date và counter tối thiểu.
- Nếu timer loop gặp exception ngoài dự kiến ở mức top-level, log `cron_timer_loop_failed`, chuyển `DEGRADED`, chờ backoff hữu hạn hoặc shutdown; không để task chết im lặng mà app vẫn tưởng reminder đang hoạt động.

## 6. Acceptance Criteria (tiêu chí nghiệm thu)

### 6.1 Static/design boundary

1. File implementation có `CronTimer` ở `backend/app/core/cron_timer.py` hoặc module được spec ghi rõ; heap dùng `heapq`/min-heap, không dùng thư viện scheduler mới.
2. `app/main.py` có lifespan duy nhất cho timer; `app.state.cron_timer_task` là task được tạo và await trong cùng lifespan.
3. Có `ENABLE_INPROCESS_CRON: bool = False`; khi false, no-op hoàn toàn, không có request overhead/extra DB query và không phát reminder. Khi true, chỉ `CronTimer` gọi dispatcher nội bộ 011b. Không có endpoint/scheduler external hay owner thứ hai.
4. `get_session()` vẫn là async generator dependency không nhận `Request`; nếu dùng ContextVar/middleware thì contract, commit/rollback và unit tests hiện hữu không bị đổi. Test `update_tracker` chỉ reload khi `reminder_time` thực sự đổi.
5. 011d không tạo migration/bảng queue/index mới. Nếu 011b chưa merge hoặc các implementation/schema thật chưa có trên đĩa, dừng theo dependency gate; không dùng stub.
6. `git diff --check` sạch; không có secret thật, URL push thật, email thật hoặc dữ liệu cá nhân trong diff/log/test fixture.

### 6.2 Unit tests bắt buộc — test phải biết đỏ

Mỗi bài sau phải có một red-proof: cố ý gỡ đúng guard/nhánh đang bảo vệ, chạy thấy fail đúng lý do, khôi phục, chạy xanh.

- `reminder_time` 08:00/23:59 và ngày chuyển tiếp tạo đúng `due_at` aware +07:00; không có naive datetime.
- Tracker dùng exact-time trực tiếp (không còn assign_slot trong repo).
- Subscription với lead `3`, expiry hôm nay/+1/+3/+10 ngày tạo đúng candidate 19:00; canceled/deleted/expired bị loại; đổi `subscription_expiry_lead_days` rồi reload đổi lịch.
- Tie cùng `due_at` có thứ tự deterministic; batch pop đủ các item đã due.
- Heap rỗng chờ event vô thời hạn; fake repository query count không tăng trong thời gian chờ.
- Timer ngủ tới deadline và `request_reload()` đánh thức sớm; item cũ bị thay bằng snapshot mới, không dispatch subject đã xoá/tắt reminder.
- Mutation marker chỉ reload sau commit; rollback không set event. Test phải bắt lỗi nếu notifier được gọi trước `commit`.
- Startup/redeploy load lại từ source DB **và pending `reminder_dispatch` rows còn trong `PENDING_RECOVERY_TIMEOUT`**, giữ nguyên dispatch ID/row; test crash giữa push và commit phải retry cùng occurrence, không tạo duplicate row.
- Grace 15 phút: occurrence quá giờ nhưng trong grace được enqueue; quá grace không replay vô hạn. Nếu chủ veto grace, thay test theo quyết định mới trước khi merge.
- Sau `SENT`/`NO_DEVICE`, occurrence kế tiếp được schedule đúng; retry temporary dùng cùng `occurrence_on`/dispatch ID và backoff bounded.
- `TEMPORARY_FAILURE` không làm task chết; một exception của item không chặn item kế tiếp.
- Shutdown cancel/await sạch, không pending task và không log exception giả như lỗi Web Push.
- `ENABLE_INPROCESS_CRON=False` không tạo task/middleware/repository/dispatcher/event, `get_session()` không thêm query/latency path; `ENABLE_INPROCESS_CRON=True` tạo đúng một task trên một app instance; thiếu DB/VAPID/011b implementation production không chạy silent-empty.
- `asyncio.wait_for` timeout được xử lý như due deadline, còn `asyncio.CancelledError` được re-raise và không bị tính là retry/failure.
- `cron_timer_running`, queue size, next due, last reload/dispatch, pending recovered/expired, loop failures và RSS/uptime có structured observability; timer loop chết/stale phát signal degraded.

### 6.3 Integration tests với dispatcher 011b

- Timer gọi service dispatcher trực tiếp, không gọi router/HTTP loopback.
- `SENT`, `DEAD_SUBSCRIPTION`, `TEMPORARY_FAILURE`, mixed dead+temporary khớp state machine 011b.
- Retry sau crash/response-lost reuse cùng `reminder_dispatch` row/id; startup/reload nạp pending chưa timeout; hai invocation concurrent không gửi hai lần sau terminal state.
- Private tracker không lộ tên/ciphertext trong payload; `reminder_text` được dùng đúng khi có; subscription dưới private parent dùng generic.
- Timer không tạo Entry; confirmation endpoint mới tạo tối đa một Entry và vẫn trả `PRIVATE_UNLOCK_REQUIRED` khi gate khoá.

### 6.4 Neon idle/resource proof

Test fake repository/SQLAlchemy instrumentation phải chứng minh:

1. startup có load query;
2. mỗi commit schedule có một reload event/query sau commit;
3. giữa hai due time không query;
4. queue rỗng không query;
5. không có loop `sleep(1..300)` kèm query.

> **Đã chạy phải dán output thật trong PR:**

```powershell
cd backend
uv run ruff check app/core/cron_timer.py app/main.py app/core/settings.py app/web/deps.py
uv run pytest tests/test_cron_timer.py tests/test_cron_timer_lifespan.py -q
uv run pytest -q
cd ..
git diff --check
git status --short
```

Nếu có PG test, ghi riêng lệnh/output của DB local throwaway. Không tick “Neon idle protection proven” bằng unit test; lane production chỉ được ghi sau khi nhìn số đo thật trên hệ thống đang chạy.

### 6.5 Production/manual lane — không được suy ra từ local pass

Sau merge/deploy, chỉ khi owner đã ghi dated note, retire mọi Google Cloud Scheduler job và bật `ENABLE_INPROCESS_CRON=true`:

- thấy log startup `cron_timer_started mode=inprocess` và `cron_timer_queue_loaded ...`;
- tạo/sửa/xoá một reminder test, thấy reload xảy ra sau commit và item cũ không bắn;
- tại một giờ gần nhau, thấy một dispatch thật qua Web Push/011b và một `reminder_dispatch` terminal, không có duplicate Entry;
- nhìn Neon activity/metric quanh lúc due: có một nhịp ngắn phục vụ dispatch, không có query đều đặn khi timer đang ngủ;
- kiểm `/api/healthz` vẫn liveness-only;
- kiểm Fly chỉ có đúng một Machine/process theo quyết định hiện hành.

Nếu chưa làm được lane này, báo **CHƯA verify được**; local green không chứng minh production scheduler, push delivery hay Neon autosuspend.

### 6.6 Hình dạng báo cáo cuối

PR/hand-off phải có các mục:

```text
Đã chạy:
- <lệnh nguyên văn>
- <output nguyên văn>

CHƯA chạy:
- <lane bị chặn hoặc chưa có quyền>

Vì sao vẫn tin là đúng:
- <lập luận ngắn, gắn rõ đây không phải runtime proof>

Judgment calls:
- exact-time thay slot
- grace window 15 phút (nếu còn)
- backoff retry
- `PENDING_RECOVERY_TIMEOUT` và pending-row rehydration sau crash
- `ENABLE_INPROCESS_CRON` + mất external retry/attempt deadline/result reporting
- cutover một chiều + retirement toàn bộ Google Cloud Scheduler job
```

## 7. Mục KHÔNG ĐƯỢC LÀM

- **Không** query Neon mỗi 1–5 phút, mỗi 60 giây hoặc mỗi vòng `while`; không `SELECT 1` để “giữ kết nối”; không dùng `readyz`/health probe làm tick.
- **Không** giữ DB connection/transaction trong lúc `asyncio.sleep()` hoặc quanh toàn bộ network call Web Push.
- **Không** dùng Google Cloud Scheduler, cron endpoint external hay scheduler external khác cho reminder/heartbeat; không xem `reminder_dispatch` idempotency là lý do hợp lệ để dual-run.
- **Không** tự bật `ENABLE_INPROCESS_CRON=true` khi decision record chưa được dated-note, 011b chưa merge, hoặc mọi Google Cloud Scheduler job chưa được retirement có biên lai.
- **Không** gọi HTTP loopback tới route reminder, không tự chế bearer token cho call nội bộ, không dùng `BackgroundTasks`/fire-and-forget route để dispatch.
- **Không** thêm Celery, RQ, Redis, APScheduler, Supercronic, broker, `LISTEN/NOTIFY` hoặc scheduler dependency khác cho v1.
- **Không** tạo bảng persistent queue, cột `due_at` mới, migration hoặc index mới cho 011d.
- **Không** cache full `Tracker`/`Subscription`, decrypted name, `reminder_text`, push payload, VAPID key, cookie hay bearer token trong heap/log.
- **Không** dùng `assign_slot()`/ba khe cố định hoặc lượng tử hoá tương đương để làm sai exact `reminder_time`.
- **Không** dùng `zoneinfo` nếu image/runtime không bảo đảm tzdata; dùng quy ước fixed `+07:00` đã chốt cho lịch VN và luôn giữ timestamp aware.
- **Không** replay vô hạn các occurrence quá khứ, không retry DB/Push vô hạn, không biến một failure đơn lẻ thành poll loop.
- **Không** dùng fabricated unlocked session, bỏ qua privacy gate, fallback tên private ra lock-screen, hoặc coi timer background là quyền đọc private không giới hạn.
- **Không** để timer tự tạo `Entry`, tự bypass confirmation, tự restore item đã undo, hoặc nhân bản state machine của 011b.
- **Không** sửa `reminder_dispatch` semantics, VAPID payload, service worker, iOS action limitation hay confirmation route theo trực giác; nếu cần đổi hợp đồng, sửa 011b/decision record trước.
- **Không** sửa unrelated task/note/calendar/UI files để “tiện tay”; mọi thay đổi ngoài module/lifespan/dependency marker/011b adapter phải được nêu rõ và xin quyết định.
- **Không** echo hoặc commit secret thật; test chỉ dùng synthetic/redacted values và `.env.example`.
