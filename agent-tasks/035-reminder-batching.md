# 035 — Gom Web Push tracker theo khung giờ

> Trạng thái: **DRAFT 2026-08-27 — product behavior do Owner nêu trực tiếp; technical spec chờ ad-review.**
>
> Executor đề xuất: **Terra/xhigh** · review thiết kế: **Sol/high nếu route callable** · T3: **Luna/xhigh hoặc Gemini 3.7/high read-only** · không substitute route âm thầm.

## 0. Kết quả người dùng phải nhận được

Trong failure-free path, ở một ngày theo múi giờ `Asia/Ho_Chi_Minh`, các tracker thật sự đến hạn ở
cùng `reminder_time` chính xác tới giây tạo **một provider call trên mỗi active
`push_subscription` endpoint**. Một thiết bị vật lý có thể để lại nhiều row/endpoint hoặc thay endpoint;
vì schema không có durable physical-device identity, “mỗi thiết bị” chỉ là kỳ vọng device acceptance
best-effort, không phải invariant máy kiểm được.

- Title: `Hi, it's microSched 🌸`.
- Một tracker public: body chỉ là tên tracker.
- Một tracker private, hoặc batch có từ hai tracker: body
  `Bạn có N thông báo từ app`.
- `N` là số tracker occurrence còn hợp lệ trong batch; không phải số thiết bị, số retry
  hay số row lịch sử.
- Batch nhiều tracker mở `/trackers`; batch đơn giữ deep-link hiện hành của tracker.
- `reminder_text` cũ không còn chọn lock-screen body. Field DB được giữ để rollback/compat,
  nhưng UI 036 không được tiếp tục hứa rằng text đó sẽ hiện trên màn hình khoá.

Scope chỉ là **tracker reminders** đang xuất hiện trong cell “Lịch nhắc nhở trong ngày”.
Không gom `subscription` expiry; không tạo task reminder mới.

`from microSched` trong ảnh iPhone là OS/browser attribution, không phải payload field.
Không claim xoá được dòng đó cho tới khi iPhone thật chứng minh.

Web Push chỉ là **at-least-once**: crash sau provider accept nhưng trước DB terminal có thể retry.
Opaque notification `tag` là best-effort visual collapse, không phải exactly-once. Acceptance không
được hứa tuyệt đối “không duplicate” ở failure window; device nào temporary-fail trong một batch mà
device khác sent có thể bỏ lỡ batch vì current product contract terminal khi có ít nhất một success.

## 1. Sự thật hiện tại

- `backend/app/domain/reminder.py` build và gửi từng tracker occurrence.
- `backend/app/core/cron_timer.py` pop/process từng `TimerItem`.
- unique durable hiện tại là `(subject_type, subject_id, dispatched_on)` trên
  `reminder_dispatch`; không có batch identity hoặc membership.
- `frontend/src/tracker-ui.ts` chỉ gom để hiển thị; không điều khiển delivery.
- retry hiện là `30s → 2m → 10m`; pending recovery khôi phục từng dispatch.
- Web Push chỉ có at-least-once boundary: provider có thể nhận trước khi DB ghi terminal.

Vì vậy không dùng giải pháp “send từng item rồi cho service worker tự collapse”. Nó không
giữ đúng `N`, privacy hay membership sau restart.

## 2. Thiết kế kỹ thuật khóa trong task

### 2.1 Expand schema `0012`

Thêm hai bảng; không backfill và không đổi unique hiện hữu:

```text
tracker_reminder_batch
  id UUID PK DEFAULT uuidv7()
  occurrence_on DATE NOT NULL
  reminder_time TIME WITHOUT TIME ZONE NOT NULL
  generation INTEGER NOT NULL DEFAULT 1 CHECK generation >= 1
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK pending|sent|no_device|cancelled|exhausted
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK 0 <= attempt_count <= 4
  last_attempt_at TIMESTAMPTZ NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  UNIQUE (occurrence_on, reminder_time, generation)
  INDEX (status)

tracker_reminder_batch_item
  id UUID PK DEFAULT uuidv7()
  batch_id UUID NOT NULL FK tracker_reminder_batch(id) ON DELETE CASCADE
  dispatch_id UUID NOT NULL UNIQUE FK reminder_dispatch(id) ON DELETE RESTRICT
  reminder_mode TEXT NOT NULL CHECK fixed|after_entry
  reminder_interval_days INTEGER NOT NULL CHECK >= 1
  reminder_action TEXT NOT NULL CHECK confirm_event|open_tracker
  input_mode TEXT NOT NULL CHECK event|money|quantity
  state TEXT NOT NULL DEFAULT 'pending'
    CHECK pending|sent|no_device|cancelled|exhausted
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  UNIQUE (batch_id, dispatch_id)
```

Snapshot chỉ lưu config không nhạy cảm; không lưu decrypted name, `reminder_text`, payload
body, endpoint hoặc secret.

Hai model mới phải khai `Gate.NONE`/soft-delete gate đúng registry hiện hành. Migration phải đặt tên
ổn định cho toàn bộ PK/FK/CHECK/UNIQUE/index (`pk_tracker_reminder_batch`,
`ck_tracker_reminder_batch_status`, `ck_tracker_reminder_batch_attempt_count`,
`uq_tracker_reminder_batch_occurrence_time_generation`, `ix_tracker_reminder_batch_status`,
`pk_tracker_reminder_batch_item`, `fk_tracker_reminder_batch_item_batch_id`,
`fk_tracker_reminder_batch_item_dispatch_id`, `ck_tracker_reminder_batch_item_state`,
`uq_tracker_reminder_batch_item_batch_dispatch`, `uq_tracker_reminder_batch_item_dispatch_id` và các
CHECK snapshot theo tên bảng). Exact whole-second guards:

```sql
ck_tracker_reminder_time_whole_second:
  reminder_time IS NULL
  OR (EXTRACT(MICROSECONDS FROM reminder_time)::bigint % 1000000) = 0
ck_tracker_reminder_batch_time_whole_second:
  (EXTRACT(MICROSECONDS FROM reminder_time)::bigint % 1000000) = 0
```

Cả hai bảng dùng trigger tên `set_updated_at` gọi `microsched.set_updated_at()` theo convention hiện
hành. Owner exact là `microsched_migrator`; default privileges phải cho `microsched_app` đúng CRUD cần
thiết (`SELECT, INSERT, UPDATE, DELETE`) và `PUBLIC` không có table privileges. Drift/canonical tests
đối chiếu column type/nullability/default, named constraints/index, trigger, owner và grants—không chỉ
dựa vào Alembic autogenerate vì nó không so trigger/owner/grant.

CI Migration QA phải dựng chính contract role này, không chạy migration `0012` với owner `postgres` rồi
vẫn tick acceptance. Bootstrap connection superuser của service chỉ được dùng trong
`scripts.prepare_ci_database` để tạo ephemeral roles/schema/extension; script tạo login
`microsched_migrator` và `microsched_app` bằng credential synthetic của CI, chuyển owner schema cho
`microsched_migrator`, revoke `PUBLIC`, và cấu hình default privileges do chính migrator sở hữu. Sau
bootstrap, `NEON_MIGRATOR_URL` của Alembic phải trỏ tới role `microsched_migrator`; application-role URL
riêng dùng để assert CRUD được phép và DDL bị cấm. Catalog test bắt buộc assert table/sequence owner,
explicit/default grants cho app và `PUBLIC` zero privileges. Password synthetic chỉ ở CI env, không ghi
vào spec/log artifact và không dùng `.env` thật.

Upgrade order: preflight fractional tracker rows → thêm
`ck_tracker_reminder_time_whole_second` trên `tracker` bằng `NOT VALID` rồi
`VALIDATE CONSTRAINT` → widen dispatch CHECK → tạo bảng/constraints/index → trigger → catalog
owner/grant verification. Downgrade chạy **toàn bộ preflight trước DDL** và fail-closed nếu một
batch/item row tồn tại **hoặc** `reminder_dispatch.status IN ('cancelled','exhausted')`; chỉ khi sạch mới
drop trigger/table → drop `ck_tracker_reminder_time_whole_second` → thu hẹp dispatch CHECK. Local
round-trip phải query catalog ngay tại revision `0011` để chứng minh không còn table/trigger/index/CHECK
của `0012`, rồi mới upgrade lại và so canonical schema; chỉ drop schema/data rỗng.

`0012` đồng thời widen named CHECK của `reminder_dispatch.status` từ
`pending|sent|no_device` thành `pending|sent|no_device|cancelled|exhausted`; không đổi default
`pending`. Domain model và schema drift test phải cùng phản ánh tập giá trị này.

Không silently round fractional seconds. **Guard DTO/API/domain reject `reminder_time` có microseconds
phải vào 035A, có RED → GREEN và được deploy/verify trước khi apply `0012`**; đây là hard rollout gate,
không được để 035A còn nhận write fractional trong cửa sổ migration → 035B. Migration preflight
fail-closed nếu catalog đã có row fractional-second. DB thêm named CHECK dùng fractional microseconds để
direct SQL/old writer cũng fail; scheduler gặp row vi phạm phải fail-closed, không round.

### 2.2 Claim và membership

Batch key canonical = `(occurrence_on theo VN, reminder_time exact seconds)`.

1. CronTimer lấy toàn bộ tracker items cùng key đang due trong grace window.
2. Sort candidate theo tracker UUID. Trong một transaction, gọi
   `pg_advisory_xact_lock(namespace, key_hash)` trước mọi query/insert của key. `namespace` là constant
   signed-int32 riêng cho tracker batch; `key_hash` là 32 bit đầu SHA-256 của canonical UTF-8
   `YYYY-MM-DD\x1fHH:MM:SS`, chuyển sang signed-int32. Hash collision chỉ serialize thêm, không làm
   nhập membership vì query vẫn dùng key đầy đủ.
3. Sau advisory lock, re-read các tracker theo UUID order bằng `SELECT ... FOR UPDATE`, rồi revalidate
   delete/config/time/mode/action/input mode ngay trong transaction. Với `after_entry`, trong cùng
   transaction phải đọc lại latest `Entry.occurred_at` và recompute due eligibility; một Entry mới làm
   tracker không còn đến hạn thì candidate bị loại. `create_entry` và mọi writer đổi reminder/privacy/name
   phải lấy cùng tracker row lock, nên không mutation liên quan nào commit chen giữa lần revalidate và
   claim commit. Không dùng snapshot trước lock để quyết định membership.
4. Dưới lock, insert `reminder_dispatch` từng candidate hợp lệ bằng unique hiện hành; conflict nghĩa là
   occurrence đã được legacy/batch khác claim nên bỏ candidate đó. Nếu không claim được member nào,
   không tạo batch. Nếu có, đọc `max(generation)` của exact key, tạo `generation=max+1`, rồi insert
   item rows trong cùng transaction. Không được join thêm member vào batch đã commit, dù batch còn
   `pending`.
5. Membership bất biến sau commit. Retry/restart đọc batch `pending` + item đã commit; nó không chạy
   generation algorithm và không suy lại group từ heap hiện tại.
6. Tracker đổi time/mode/action/input mode hoặc bị delete trước retry làm member `cancelled`;
   tracker mới cùng giờ không được chèn vào batch cũ.

Ngay trước provider attempt, mở một transaction ngắn, lấy `SELECT ... FOR UPDATE` trên toàn bộ tracker
của active members theo UUID order **trước khi** dựng payload; đồng thời lock/re-read batch/item/dispatch
rows cần đổi trạng thái. Revalidate delete/config/time/mode/action/input mode và, với `after_entry`, đọc
lại latest `Entry.occurred_at` rồi recompute current due eligibility. Member không còn đến hạn hoặc không
còn hợp lệ bị mark `cancelled`. Chỉ từ row đã khóa này mới quyết định privacy/name/count/url và commit
payload inputs; không giữ row lock/DB connection qua network. Vì các writer tracker và `create_entry`
cùng lấy tracker row lock, mutation privacy/name/config/Entry commit trước lần pre-send lock sẽ được thấy;
mutation đang chờ chỉ commit sau boundary. **Linearization boundary** là lúc transaction pre-send commit:
mutation commit trước boundary phải phản ánh vào payload, mutation commit sau boundary không thể thu hồi
payload đã bắt đầu gửi. Lock-connection loss/process crash/provider accept sau boundary nằm trong failure
window at-least-once đã ghi ở §0, không được báo thành exactly-once.

Global row-lock order cho mọi code path chạm reminder/freshness là:

```text
tracker (UUID tăng dần) → entry (UUID tăng dần, nếu có)
→ tracker_reminder_batch → tracker_reminder_batch_item (dispatch UUID tăng dần)
→ reminder_dispatch (UUID tăng dần)
```

Query thăm dò để tìm ID được phép chạy trước nhưng không phải authority. Sau khi lấy tracker lock, code
phải re-read/lock row còn lại theo thứ tự trên và revalidate identity/state trước mutation. Confirmation
035A vì thế không được giữ dispatch lock rồi mới gọi `create_entry`: nó đọc dispatch ID/tracker ID không
lock, lấy tracker lock, sau đó re-read dispatch `FOR UPDATE`; row đổi/mất thì retry/fail-closed. Pre-send
tương tự có thể đọc membership ID trước, nhưng tracker lock luôn đứng trước batch/item/dispatch row lock.
Mọi freshness writer của `after_entry`—create Entry, update `occurred_at`, soft-delete, restore và
confirmation—phải lấy tracker lock trước Entry mutation trong cùng transaction. Không chỉ `create_entry`.

Toggle privacy **không cancel reminder**: payload retry dùng privacy hiện tại và chuyển sang generic nếu
tracker đã private. Đổi tên public dùng tên hiện tại; không dùng name snapshot.

Generation giải trường hợp batch cũ đã closed/terminal nhưng tracker khác mới đến hạn cùng ngày/giờ:
generation mới được tạo. Cùng tracker không được gửi occurrence thứ hai trong ngày vì unique
`reminder_dispatch(subject_type, subject_id, dispatched_on)` vẫn là authority; edit giờ sau dispatch
chỉ ảnh hưởng ngày kế tiếp. Concurrent generation insert retry theo named unique trong transaction,
không đọc `max+1` rồi ghi ngoài lock.

Legacy `reminder_dispatch pending` không có batch link tiếp tục đường delivery cũ trong cửa
sổ recovery 24 giờ; tuyệt đối không đoán membership/backfill nó.

### 2.3 Payload/privacy/click

Sau revalidation, `active_members` quyết định payload:

```text
len == 1 và public:
  title = "Hi, it's microSched 🌸"
  body = public tracker name nếu decrypt thành công
  nếu ciphertext hỏng hoặc key/decrypt unavailable:
    body = "Bạn có 1 thông báo từ app"
  url = existing action URL

len == 1 và private:
  title = "Hi, it's microSched 🌸"
  body = "Bạn có 1 thông báo từ app"
  url = existing action URL

len > 1:
  title = "Hi, it's microSched 🌸"
  body = "Bạn có N thông báo từ app"
  url = "/trackers"
```

Private/multi path không được gọi decrypt/name/custom-text helper. Multi click không tạo entry
hoặc chọn ngầm một tracker để confirm. Single `confirm_event` vẫn dùng member `dispatch_id` và
giữ idempotency nhiều thiết bị.

Public-single decrypt failure là failure-safe generic, không cancel member và không bao giờ đưa
ciphertext/error detail vào payload. Structured receipt chỉ ghi opaque batch ref, occurrence/time và
outcome `public_name_decrypt_fallback`; không tracker/dispatch UUID thô, name/text/ciphertext hay key
metadata. Unit test bắt buộc phủ ciphertext corrupt và key/decrypt unavailable, assert exact generic body,
URL/action giữ nguyên và artifact/log không chứa ciphertext.

Payload thêm `tag` opaque từ `batch_id` cho service worker dùng làm best-effort collapse khi
provider retry; tag không chứa ngày, tên hoặc count. Đây không phải exactly-once proof.

### 2.4 Delivery outcome

Một batch attempt chạy một vòng qua push subscriptions, không chạy một vòng/member.

Selection endpoint phải có **unit/contract test riêng**, không được chỉ dựa vào integration acceptance
hai endpoint ở §4. Schema hiện hành của `push_subscription` không có cột status/`deleted_at`: “active”
chính xác là row còn tồn tại tại thời điểm selector query; explicit unsubscribe và provider `404/410`
hard-delete row nên là inactive/revoked equivalent. `exhausted` là trạng thái batch/dispatch, không phải
trạng thái subscription và không được dùng để phát minh thêm cột/schema trong 035B. Fixture unit bắt buộc
có hai row hiện hành cộng các endpoint đã bị unsubscribe/dead-delete trước snapshot; oracle là selector
trả đúng hai endpoint hiện hành và provider mock nhận đúng hai endpoint đó, **zero call** cho mọi endpoint
đã bị xoá. Một batch đã terminal, gồm `exhausted`, vẫn phải qua terminal guard và tạo zero network call.

- Ít nhất một device `SENT` ⇒ batch `sent`.
- Không device sent nhưng có temporary failure ⇒ giữ `pending`, schedule đúng một retry chain.
- Không device / chỉ dead subscription ⇒ `no_device`.
- Không active member ⇒ `cancelled`, không network.
- Hết attempt thứ tư mà vẫn temporary failure ⇒ `exhausted`, structured manual-required receipt;
  không pending vô hạn. Occurrence ngày sau vẫn được schedule.
- `attempt_count` và telemetry authoritative ở batch. Per-member dispatch vẫn là occurrence +
  confirmation identity, không được báo “delivery pending” khi batch đã terminal.

Mapping bắt buộc:

| Batch | Active item + linked dispatch | Member invalid trước send |
|---|---|---|
| `pending` | `pending` | `cancelled` |
| `sent` | `sent` | giữ `cancelled` |
| `no_device` | `no_device` | giữ `cancelled` |
| `exhausted` | `exhausted` | giữ `cancelled` |
| `cancelled` | không còn active; tất cả `cancelled` | `cancelled` |

Batch `attempt_count` tăng và commit **trước** network; crash không reset attempt budget.
`reminder_dispatch.attempt_count=0` và `last_attempt_at=NULL` cho linked member suốt vòng đời; hai field
này chỉ authoritative cho legacy unlinked dispatch. `confirm_reminder_dispatch()` giữ fast-path trả
entry đã confirm trước mọi revalidation; với row chưa confirm, chỉ `pending|sent` được đi tiếp,
`no_device|cancelled|exhausted` trả `409` và tạo 0 Entry.

Legacy recovery phải exclude mọi dispatch đã có batch-item link. Khi batch terminal, active member
`reminder_dispatch.status` và item `state` đều mirror cùng terminal
`sent|no_device|cancelled|exhausted` trong chính transaction terminal. Vì vậy không có linked dispatch
`pending` sau khi batch terminal. Structured receipt cho `exhausted` gồm batch ref opaque,
occurrence/time, attempt count và outcome count; không name/text/endpoint/UUID thô. Legacy recovery
luôn anti-join batch-item trước khi xét status/age, nên mọi linked item terminal hoặc pending đều bị
exclude.

`reminder_delivery_receipt.py` không được tiếp tục diễn giải linked `reminder_dispatch.attempt_count`
như provider attempt. Output mới tách: aggregate batch theo occurrence/time/generation/status/attempt,
active/cancelled member counts và aggregate **legacy unlinked** dispatch riêng. Không xuất batch/item/
dispatch UUID, tracker name/text, endpoint hoặc subscription key.

## 3. Phạm vi file dự kiến

- `backend/app/domain/models.py`
- `backend/alembic/versions/0012_tracker_reminder_batch.py`
- `backend/app/domain/reminder.py`
- `backend/app/core/cron_timer.py`
- `backend/app/domain/tracker.py` nếu cần reject microseconds
- `backend/scripts/prepare_qa_branch.py` + guard tests để truncate hai batch table cùng delivery data
- `backend/scripts/reminder_delivery_receipt.py` + tests để report batch authority và legacy unlinked
- `backend/scripts/scheduler_ownership_receipt.py` + tests cho one-shot advisory-lock holder count
- `frontend/src/sw.ts` + unit test cho opaque notification tag đi tới `showNotification`
- test reminder/cron/migration/schema tương ứng

Không sửa note/task/calendar UI trong task này. Không chạm `.env`, production, Neon hay push
subscription thật trong implementation PR.

## 4. Acceptance và RED → GREEN

1. Hai tracker cùng VN date/time + hai active `push_subscription` endpoints ⇒ 1 batch, 2 members, đúng
   2 provider calls, không phải 4. Unit contract riêng
   `test_batch_selects_only_current_push_subscription_rows` phải chứng minh selector chỉ lấy row hiện
   hành và endpoint đã unsubscribe/dead-delete nhận 0 provider call; batch terminal `exhausted` cũng
   nhận 0 provider call. Physical-device uniqueness chỉ best-effort acceptance.
2. Khác một giây hoặc khác VN date ⇒ hai batch.
3. Public single/private single/public+private/two public có đúng title/body/url; public-single
   decrypt corrupt/unavailable dùng exact generic fallback + structured receipt an toàn; không có
   plaintext/ciphertext/custom text trong generic payload.
4. Crash sau membership commit trước send ⇒ restart dùng cùng batch/member IDs; crash sau provider
   accept trước terminal commit chứng minh có thể duplicate và không được claim exactly-once.
5. Partial result: sent+temporary terminal sent; all temporary một retry; all dead no_device.
6. Edit schedule/action/delete trước retry cancel đúng member; privacy toggle không cancel mà đổi
   payload sang generic; không thêm member mới. Concurrency test phải điều khiển exact commit order:
   privacy/name/Entry commit trước pre-send row lock được phản ánh hoặc làm `after_entry` hết due; writer
   chờ lock chỉ commit sau boundary và không được mô tả như mutation “trước send” đã bị bỏ sót.
   Cases riêng bắt buộc cho create/update-occurred-at/soft-delete/restore/confirmation; không gom thành
   một test mock “Entry changed”.
7. Legacy unlinked pending không bị attach hoặc duplicate.
8. Batch temporary failure lần 4 ⇒ exhausted + receipt; occurrence sau không bị nuốt.
9. Single confirm từ hai thiết bị tạo đúng một Entry; multi click không gọi confirm endpoint.
10. Scrub guard chạy được **cả pre-0012** (batch tables chưa tồn tại) và post-0012; post-0012 chứng minh
    batch/item/reminder_dispatch/push data đều zero sau prepare QA.
11. Migration upgrade, downgrade-empty, round-trip và drift check xanh; downgrade non-empty fail-closed.
    Catalog tại revision `0011` sau downgrade không còn whole-second CHECK/table/trigger/index của `0012`.
12. RED proof tối thiểu:
    - cố ý send per-member ⇒ provider-call assertion đỏ;
    - cố ý đưa endpoint đã unsubscribe/dead-delete vào selector hoặc bỏ terminal guard của batch
      `exhausted` ⇒ unit endpoint-selection assertion đỏ; restore ⇒ đúng hai active calls và zero inactive;
    - bỏ privacy generic gate ⇒ leak test đỏ;
    - dùng UTC date hoặc round seconds ⇒ boundary test đỏ;
    - hai CronTimer trên PG thật: đúng một owner, standby zero snapshot/recovery/send, handoff sau close;
    - làm mất dedicated lock connection: owner cũ không bắt đầu provider call mới và task supervision
      fail/restart; graceful shutdown await dispatch loop trước unlock;
    - 035A-owner + 035B-standby overlap và rollback 035B→035A với linked pending đều zero per-item send;
    - concurrent same-key claim tạo một generation/membership; linked pending bị legacy anti-join;
    - bỏ tracker `FOR UPDATE` ở pre-send hoặc bỏ latest-Entry recompute ⇒ controlled race leak/stale-due
      test đỏ; restore cả hai ⇒ xanh;
    - giữ lock order cũ `dispatch → tracker` trong confirmation rồi chạy đồng thời với linked pre-send
      `tracker → dispatch` ⇒ deadlock/timeout guard đỏ; đổi cả hai về global order ⇒ xanh và không user
      action nào bị PostgreSQL chọn làm deadlock victim;
    - 035A confirmation guard: `pending|sent` được confirm, `no_device|cancelled|exhausted` tạo 0 Entry,
      kể cả sau rollback từ schema `0012`;
    - mixed active/cancelled terminal mirror đúng bảng §2.4;
    - crash sau provider accept hoặc giữa device loop ghi rõ duplicate-possible at-least-once receipt;
    - direct SQL fractional second đỏ trên tracker + batch; downgrade có cancelled/exhausted đỏ;
    - service worker truyền opaque `tag` vào `showNotification`;
    - restore rồi toàn bộ xanh.

## 5. Lệnh và evidence boundary

```text
backend: uv run ruff check .
backend: uv run ruff format --check .
backend: uv run pytest tests/test_reminder_batching.py::test_batch_selects_only_current_push_subscription_rows
backend: uv run pytest -m "not pg"
backend: uv run pytest -m pg   # Docker prerequisite
frontend: npm run lint
frontend: npm run test         # unit test phải assert tag tới showNotification
frontend: npm run build
frontend: npm run e2e          # canonical full Playwright command
root:    uvx pre-commit run --all-files
```

Docker Desktop phải được Owner bật trước PG lane. Local/CI không chứng minh migration Neon,
production delivery, title/icon iPhone, OS attribution hoặc exactly-once. Report phải tách
PASS/FAIL/NOT_RUN.

## 6. Scheduler ownership fence và release gate

Đây là schema + outbound behavior, nên không merge/deploy/apply migration nếu chưa có exact-head
ad-review, CI xanh và authority/gate hợp lệ. `fly.toml` hiện dùng `strategy='immediate'`; protocol dưới
đây áp cho **mọi process overlap** bất kể Fly gọi nó là immediate/rolling/restart. Release bắt buộc thành
hai PR/deploy tuần tự:

1. **035A — scheduler ownership fence + future-schema guard, không đổi payload/schema:**
   - State machine exact: `starting → owner|standby → ownership_lost|stopping → stopped`. CronTimer chỉ
     mở session factory/rebuild heap/recover/send sau khi giữ session-level PostgreSQL advisory lock
     constant trên **dedicated connection**. Standby không query snapshot/recovery/delivery; acquire
     retry dùng bounded backoff + stop/reload wake event, không tick DB khi đã owner và heap idle.
   - Dedicated connection có termination listener. Connection loss set `ownership_lost`, chặn mọi
     provider call mới, cancel/await timer TaskGroup và propagate fatal ownership error qua lifespan để
     Fly restart; process **không reacquire** sau loss. Trước mỗi snapshot/recovery/provider attempt,
     kiểm event + liveness của chính lock connection; failed check fail-closed. Provider call đã được
     accept ngay trước loss vẫn là at-least-once failure window, không claim tuyệt đối zero duplicate.
   - Graceful shutdown: set `stopping` + chặn due mới → await/cancel in-flight dispatch loop → chỉ sau
     đó advisory unlock/close dedicated connection. Không unlock trước rồi mới chờ sender.
   - Forward-compatible recovery: 035A dùng `to_regclass('microsched.tracker_reminder_batch_item')`.
      Table chưa tồn tại ⇒ legacy query hiện hành. Table tồn tại ⇒ pending recovery **anti-join** item
      trước status/age; 035A không bao giờ gửi linked dispatch per-item. Vì vậy rollback 035B→035A là
      degraded legacy mode nhưng không tách batch đã claim thành nhiều push.
   - Forward-compatible confirmation guard cũng phải vào 035A: sau fast-path idempotent cho dispatch đã
      confirm, row chưa confirm chỉ được tạo Entry khi status thuộc `pending|sent`; `no_device` và mọi
      future/unknown terminal status—including `cancelled|exhausted` sau `0012`—trả `409` và tạo 0 Entry.
      RED/GREEN bắt buộc chạy trên schema pre-0012 cho `pending|sent|no_device`, rồi trên schema post-0012
      với chính binary 035A/rollback cho `cancelled|exhausted`; không để rollback mở lại stale link.
      Implementation phải chuyển confirmation sang global lock order `tracker → dispatch → create Entry`
      và re-read dispatch dưới lock, không giữ pattern hiện hành `dispatch → tracker`.
   - Whole-second writer guard cũng phải vào 035A: create/PATCH legacy lẫn canonical reject
     `reminder_time.microsecond != 0` trước flush. RED dùng fractional API payload thấy `422` đúng
     invariant; restore thấy whole-second payload xanh. Exact 035A head có guard này phải được
     independent-review, CI xanh, deploy và verify trước khi `0012` thêm/validate DB CHECK; thiếu receipt
     thì dừng trước migration.
   - Observable receipt: structured transition log chứa commit, scheduler state và opaque lock constant
     (không DB URL/PID/UUID người dùng), cộng one-shot read-only
     `scripts/scheduler_ownership_receipt.py` đếm exact advisory-lock holders từ `pg_locks`. Không expose
     snapshot/lock qua `/healthz` hoặc `/readyz`; hai route giữ contract hiện hành.
   - Deploy 035A rồi xác nhận exact production commit, `fly machine list` chỉ topology được phép và
     receipt `holder_count=1`; mọi live process phải là 035A+ trước bước kế. Một `/readyz.commit` đơn
     lẻ không đủ chứng minh không còn process pre-fence.
2. **035B — migration + batching:** apply `0012` thủ công khi 035A đang live (expand-compatible), query
   catalog thật, rồi deploy batching nhưng giữ nguyên chính advisory-lock constant/protocol của 035A.
   Trong healthy overlap, chỉ process đang giữ lock được send; binary mới chờ old release rồi mới
   rebuild từ DB và chạy. Lock-loss/crash vẫn theo at-least-once failure boundary ở §0/§6. Sau cutover
   xác nhận exact `/api/readyz.commit`, `db=up`, một scheduler owner và không
   còn legacy unlinked pending quá recovery window trước khi xoá code legacy ở task sau.

Không gộp 035A và 035B thành một rolling deploy. T1 không tự merge/release.

Trước production 035B còn cần: Owner xác nhận fresh encrypted backup/recovery path; Tầng 2 chỉ chạy
sau khi mâu thuẫn policy Neon trong Task 037 được Owner chốt và đúng Stop & Request Owner; scrub +
migration rehearsal + catalog/grant/trigger query xanh. Production/device/Web Push thật cần authority
riêng; iPhone/Safari chưa chạy phải ghi `NOT_RUN`.
