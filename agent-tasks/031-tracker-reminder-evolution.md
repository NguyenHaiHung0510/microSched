# 031 — Tracker + Reminder Evolution (`general`, `fixed`, `after_entry`)

> **Vai soạn spec:** T1 Architect / Spec Writer · **Bậc:** L3 — schema + domain +
> scheduler + Web Push + UI · **Blast radius:** cao (Neon production, CronTimer và PWA).
>
> **Trạng thái:** các quyết định product/architecture trong §1.2 đã được Owner chốt ngày
> **2026-08-26**. Spec này là artifact giao việc; **implementation CHƯA ĐƯỢC CHẠY** trong lượt
> soạn spec. Trước thi công vẫn phải có independent adversarial review exact file này và Owner/T1 mở
> gate theo §6; không tự nâng việc “spec đã viết” thành “implementation đã duyệt”.
>
> **Phân lane đề xuất:** `Terra/xhigh` cho 031A backend/migration/CronTimer; `Gemini 3.7/high`
> cho 031B UI/UX sau khi API contract 031A đã cố định. Mỗi lane một branch/worktree, không hai writer
> chung một cây.

## 0. Kết quả cần có (Deliverables)

Sau Task 031, Owner phải nhận được các hành vi nhìn thấy sau:

1. Có thể tạo nhóm và tracker loại **Chung** (`kind='general'`) bên cạnh Sức khoẻ và Tài chính;
   tracker vẫn chỉ có một tầng nhóm và vẫn không thể nằm trong group khác `kind`.
2. Mọi tracker — không phụ thuộc `kind` — có thể bật reminder theo một trong hai cách:
   - **Theo lịch cố định (`fixed`)**: mỗi `N` ngày tại một giờ trong ngày;
   - **Sau lần ghi gần nhất (`after_entry`)**: nhắc khi dữ liệu đã cũ `N` ngày.
3. Reminder của tracker `event` có thể:
   - mở `/reminder-confirm?dispatch=<id>` để ghi đúng một entry idempotent; hoặc
   - chỉ mở màn Theo dõi.
4. Reminder của tracker `money`/`quantity` **chỉ** mở màn Theo dõi để Owner nhập số; tap notification
   không bao giờ sinh entry rỗng.
5. Các tracker thuốc đang có tiếp tục chạy như trước về cadence/action: `fixed`, mỗi 1 ngày,
   `confirm_event`; không yêu cầu Owner sửa tay dữ liệu cũ.
6. Subscription vẫn chỉ gắn được vào tracker `finance + money`; `general + money` không phải lối vòng.
7. CronTimer vẫn là một in-process timer event-driven: không tick/poll Neon, không scheduler thứ hai,
   không làm mất retry/pending recovery/idempotency hiện hành.
8. Migration được rehearsal trên local/CI và Neon ephemeral branch đã scrub; production chỉ nhận
   migration thủ công sau gate, không destructive test và không downgrade Neon.

Artifact phải giao:

- migration Alembic expand/backfill + downgrade fail-closed;
- SQLModel/Pydantic/API contract và validation canonical;
- CronTimer generic tracker scheduling + entry mutation reload;
- generic Web Push payload/routing + confirmation action guard;
- UI tạo/sửa group/tracker, schedule summary và deep-link `/trackers`;
- tests unit/API/PG/frontend/Playwright, kèm RED → GREEN receipts;
- dated supersession trong các decision record được liệt kê ở §3;
- PR/CI/migration/production receipts tách đúng lớp, không gọi local pass là production pass.

## 1. Evidence đầu vào & quyết định đã chốt

### 1.1 Evidence đã quan sát trên codebase

**ĐÃ ĐỌC trên local HEAD `5b1bf7ba16e75d76c0f935ba08c27ec628bdfab4`, branch
`codex/local-qa-auth-fix`, ngày 2026-08-26; đây không phải receipt production:**

| Bề mặt | Sự thật hiện hành cần tiến hoá |
|---|---|
| `backend/app/domain/models.py` | `tracker_group.kind` và `tracker.kind` chỉ CHECK `health/finance`; composite FK `(group_id, kind)` đã tồn tại; tracker đã có `reminder_time`/`reminder_text`. |
| `backend/app/domain/tracker.py` | `Kind` chỉ có hai giá trị; DTO/store cấm `reminder_time` ngoài `health + event`; PATCH đã bảo vệ tracker có live subscription khỏi rời `finance + money`. |
| `backend/app/domain/subscription.py` | `_assert_tracker_kind()` đã yêu cầu chính xác `finance + money`. |
| `backend/app/core/cron_timer.py` | snapshot chỉ nạp `health + event + reminder_time`; lịch tracker luôn `+1 day`; retry, pending recovery, grace window và no-poll loop đã có. |
| `backend/app/domain/reminder.py` | payload còn mang tên medication; URL tracker luôn là `/reminder-confirm`; confirmation còn kiểm `health + event`. |
| `frontend/src/TrackerForm.tsx` | reminder chỉ hiện cho `health + event`, fieldset ghi “Nhắc uống thuốc”; chưa có mode/interval/action. |
| `frontend/src/GroupForm.tsx`, `tracker-ui.ts` | TypeScript và select chỉ có Sức khoẻ/Tài chính. |
| `frontend/src/TrackerScreen.tsx` | “Lịch nhắc nhở trong ngày” group theo giờ và luôn đưa nút ghi; route tab Theo dõi chưa sở hữu `/trackers`; file còn bốn `<button>` thô tại các disclosure hiện hữu. |
| `reminder_dispatch` | uniqueness `(subject_type, subject_id, dispatched_on)` đã cung cấp idempotency một occurrence/tracker/ngày; không cần bảng occurrence mới. |
| migration head local | Có `0010_task_due_precision_expand.py`; executor phải đọc lại head lúc bắt đầu, không hard-code revision kế tiếp từ spec này. |

**CHƯA VERIFY trong lượt viết spec:** trạng thái schema/data Neon hiện tại, số tracker thuốc production,
timer production đang enabled hay không, push subscription thiết bị thật, CI của implementation, Chrome/
iPhone/Safari và production SHA. Executor phải đo lại; không dùng bảng trạng thái hoặc evidence local trên
làm biên lai live.

Worktree hiện có thay đổi không thuộc Task 031. Lane implementation phải tạo worktree riêng và giữ
nguyên mọi file user-owned ngoài scope.

### 1.2 Quyết định Owner đã chốt — nguồn ưu tiên của task

Các mục dưới đây **supersede có chủ đích** thiết kế cũ “health/finance + reminder thuốc daily-only” trong
`docs/tracking-brief.md` §12 và draft Task 031 chưa approved ngày 2026-08-25:

1. Chọn **Phương án 2 — tiến hoá tại chỗ** trên `tracker`/`tracker_group`; không tạo entity schedule mới.
2. `kind` hợp lệ trên cả hai bảng: `health | finance | general`; giữ nguyên composite FK.
3. Tracker có thêm:
   - `reminder_mode`: `fixed | after_entry`, nullable;
   - `reminder_interval_days`: integer dương, nullable; default **có điều kiện** là `1` khi bật reminder;
   - `reminder_action`: `confirm_event | open_tracker`, nullable;
   - giữ `reminder_time TIME` và `reminder_text TEXT` nullable.
4. Legacy thuốc có `kind=health` và `reminder_time` được map thành
   `fixed + 1 day + confirm_event`.
5. `confirm_event` chỉ hợp lệ với `input_mode=event`; `money|quantity` có reminder thì action bắt buộc
   là `open_tracker`.
6. Subscription invariant giữ nguyên: chỉ `kind=finance AND input_mode=money`.
7. Cadence trong Task 031 chỉ dùng **ngày**. Draft cũ nói hour/day/week không còn là scope đã chốt;
   không lén thêm `unit`, giờ-lặp hoặc tuần-lặp.
8. Backup chỉ là một use case có thể cấu hình bằng tracker `general`; Task 031 không thêm page, setting,
   script hay pipeline backup riêng.

### 1.3 Các judgment kỹ thuật khóa trong spec

Các quyết định sau là cách triển khai cụ thể để đóng mâu thuẫn giữa nullable schema, rolling deploy và
domain invariant. Owner có thể veto trước khi giao executor; executor không tự đổi:

- `reminder_interval_days` **không có unconditional DB `DEFAULT 1`**. Cột nullable, server default
  `NULL`; Pydantic/store đặt `1` chỉ khi request bật reminder mà bỏ interval. Nếu default toàn cột là
  `1`, tracker không bật reminder cũng mang schedule giả và không còn bundle nullable đúng nghĩa.
- Task này không thêm cross-field CHECK “all-null hoặc all-set”. Khoảng migration → deploy còn old
  binary/PWA cũ chỉ biết `reminder_time`; một CHECK bundle nghiêm sẽ biến create cũ thành lỗi production.
  Thay vào đó, DB bảo vệ enum/số/action boundary; domain bảo vệ bundle; scheduler fail-closed với row
  malformed. §2.2 định nghĩa đúng ba hình dạng hợp lệ.
- `last_scheduled_date` của `fixed` lấy từ `max(reminder_dispatch.dispatched_on)` cho tracker, bất kể
  terminal status. Một occurrence đã claim/sent/no-device vẫn là một lần lịch đã chạy; retry tiếp tục
  dùng cùng ngày.
- Không thêm `anchor_date`: occurrence đầu tiên sau khi bật là `reminder_time` gần nhất; row dispatch
  đầu tiên trở thành anchor bền. Các lần sau cộng đúng `N` ngày.
- `after_entry` đã stale mà chưa có entry mới sẽ nhắc tối đa một lần mỗi ngày tại giờ gần nhất cho tới
  khi có entry; không chờ thêm `N` ngày sau chính notification vì notification không phải data entry.
- Canonical URL của `open_tracker` trong v1 là **`/trackers`**. Không mở page backup riêng và không
  dựng detail route/highlight nếu chưa có nhu cầu độc lập.

## 2. Thiết kế chi tiết

### 2.1 Schema vật lý và migration

#### 2.1.1 Target schema

| Bảng/cột | Kiểu / constraint target | Default vật lý |
|---|---|---|
| `tracker_group.kind` | `TEXT NOT NULL CHECK (kind IN ('health','finance','general'))` | không đổi |
| `tracker.kind` | cùng CHECK ba giá trị | không đổi |
| `tracker.reminder_mode` | `TEXT NULL CHECK (reminder_mode IN ('fixed','after_entry'))` | `NULL` |
| `tracker.reminder_interval_days` | `INTEGER NULL CHECK (reminder_interval_days > 0)` | `NULL` |
| `tracker.reminder_action` | `TEXT NULL CHECK (reminder_action IN ('confirm_event','open_tracker'))` | `NULL` |
| `tracker.reminder_time` | `TIME NULL`, wall-clock Asia/Ho_Chi_Minh | giữ nguyên |
| `tracker.reminder_text` | `TEXT NULL`, public lock-screen content | giữ nguyên |

Giữ nguyên:

- `UNIQUE tracker_group(id, kind)`;
- FK `tracker(group_id, kind) -> tracker_group(id, kind) ON DELETE SET NULL (group_id)`;
- mọi constraint/unit/encryption/index hiện có;
- `reminder_dispatch` schema và unique occurrence hiện có.

Thêm CHECK cùng bảng để DB chặn action nguy hiểm, nhưng vẫn cho legacy-null đi qua:

```sql
reminder_action IS NULL
OR reminder_action = 'open_tracker'
OR (reminder_action = 'confirm_event' AND input_mode = 'event')
```

Tên constraint phải deterministic và khớp SQLModel ↔ Alembic, tối thiểu:

- `ck_tracker_group_kind_values`;
- `ck_tracker_kind_values`;
- `ck_tracker_reminder_mode_values`;
- `ck_tracker_reminder_interval_days_positive`;
- `ck_tracker_reminder_action_values`;
- `ck_tracker_reminder_action_input_mode`.

#### 2.1.2 Upgrade order

Executor đọc `alembic heads`/thư mục versions tại thời điểm làm và lấy revision kế tiếp thật. Trong một
migration transaction:

1. Preflight bằng aggregate/count, không select/echo nội dung cá nhân:
   - count theo `tracker.kind` và `tracker_group.kind`;
   - count reminder theo `(kind,input_mode,reminder_time IS NOT NULL)`;
   - count row có `reminder_time IS NOT NULL` nhưng không phải `health + event`;
   - constraint/FK names hiện hành từ `pg_constraint`.
2. `ADD COLUMN` ba cột mới, đều nullable, không table-rewrite default.
3. Backfill đúng legacy rows:

   ```sql
   UPDATE microsched.tracker
   SET reminder_mode = 'fixed',
       reminder_interval_days = 1,
       reminder_action = 'confirm_event'
   WHERE kind = 'health'
     AND input_mode = 'event'
     AND reminder_time IS NOT NULL
     AND reminder_mode IS NULL
     AND reminder_interval_days IS NULL
     AND reminder_action IS NULL;
   ```

   Nếu preflight thấy reminder-time legacy ngoài `health + event`, migration **dừng có thông báo count**;
   không đoán action và không in name/text.
4. Thay hai kind CHECK bằng phiên bản có `general`. Dùng exact constraint name; `ADD ... NOT VALID`
   rồi `VALIDATE CONSTRAINT` trong transaction để giảm thời gian giữ lock scan. Không drop composite
   FK/unique.
5. Thêm ba value/positive CHECK và action-input CHECK theo cùng pattern `NOT VALID` → `VALIDATE`.
6. Postcondition query xác nhận columns, defaults đều null, constraint definitions và aggregate legacy
   mapping; không dừng ở `alembic current`.

`ADD COLUMN NULL` và widening CHECK là expand-compatible với binary cũ. Trong cửa sổ migration→deploy:
binary cũ vẫn đọc/ghi hai cột reminder cũ; binary mới có compatibility shape ở §2.2. Không tạo general
row trước khi backend 031A live.

#### 2.1.3 Downgrade fail-closed

Local/CI phải round-trip; Neon **không bao giờ downgrade**. `downgrade()` kiểm trước mọi destructive DDL
và raise nếu có bất kỳ:

- group/tracker `kind='general'`;
- tracker reminder không legacy-equivalent, gồm `after_entry`, interval khác `1`, action
  `open_tracker`, hoặc reminder trên kind/input khác `health + event`;
- row partial/malformed khiến drop cột làm đổi nghĩa.

Chỉ khi toàn bộ dữ liệu còn biểu diễn được bằng schema cũ mới drop action checks/columns, đưa kind CHECK
về hai giá trị. Không tự rewrite/drop general data để làm downgrade xanh.

### 2.2 Domain models, DTO và canonical validation

#### 2.2.1 Types

Backend và frontend dùng cùng tập literal:

```text
TrackerKind     = health | finance | general
ReminderMode    = fixed | after_entry
ReminderAction  = confirm_event | open_tracker
```

`TrackerCreate`, `TrackerUpdate`, `TrackerRead`, SQLModel `Tracker`, TypeScript `Tracker` và mutation
payload đều mang ba field mới. `reminder_text` trim; blank thành `NULL`; backend đặt `max_length=240`
để không dựa riêng vào UI.

#### 2.2.2 Ba hình dạng reminder hợp lệ

Domain chỉ chấp nhận:

1. **Disabled canonical:** `mode=NULL`, `interval=NULL`, `action=NULL`, `time=NULL`; khi UI tắt,
   `reminder_text` cũng được clear về `NULL`.
2. **Enabled canonical:** `mode`, interval dương, `action`, `time` đều non-null; text optional.
3. **Legacy compatibility:** đúng `health + event + reminder_time non-null`, cả ba field mới đều null.
   Effective config/read response là `fixed + 1 + confirm_event`.

Mọi hybrid khác (ví dụ mode có nhưng action null, action có nhưng time null, interval 0) là malformed:
API create/PATCH trả `422`; scheduler log structured count/ref không đảo ngược và skip row, không đoán.

Compatibility cho cached old PWA:

- Nếu request **bỏ hẳn** ba field mới, gửi `reminder_time non-null`, effective kind/input là
  `health + event`, backend canonicalize và lưu `fixed + 1 + confirm_event`.
- Explicit `null` khác với omitted; request cố gửi `mode=null` cùng `time` không được giả làm legacy.
- PATCH merge trên effective state: đổi riêng time/text của tracker đã backfill vẫn hợp lệ.

Khi enabled mà interval omitted, domain đặt `1`. Không tự default mode/action: client mới phải gửi lựa
chọn rõ; ngoại lệ duy nhất là legacy shape phía trên.

#### 2.2.3 Capture mode × action

| `input_mode` | `confirm_event` | `open_tracker` |
|---|---:|---:|
| `event` | hợp lệ | hợp lệ |
| `money` | **422** | hợp lệ |
| `quantity` | **422** | hợp lệ |

PATCH phải validate **effective row sau merge**, không chỉ field có trong payload:

- đổi `event → money/quantity` khi action còn `confirm_event` trả `422`, trừ khi cùng PATCH đổi action
  sang `open_tracker` hoặc tắt reminder;
- đổi kind không tự đổi action; reminder không còn phụ thuộc kind;
- chuyển group/kind vẫn validate composite pair hiện hành;
- thay bất kỳ `mode/interval/action/time`, create/restore/archive tracker đều set reload marker sau
  commit như contract 011d.

#### 2.2.4 Subscription invariant

Giữ hai lớp app guard hiện có và mở rộng test cho `general`:

- create/update/renew subscription chỉ nhận parent `finance + money`;
- tracker có live subscription không thể đổi kind khỏi `finance`, đổi input khỏi `money`, archive hoặc
  chuyển sang group không hợp lệ;
- `general + money` vẫn có thể ghi amount và góp vào finance aggregate theo `direction`, nhưng không
  được chứa subscription.

Không dựng trigger cross-table chỉ để lặp app invariant; đây vẫn là single-writer contract hiện hành.

### 2.3 CronTimer scheduling

#### 2.3.1 Eligibility và snapshot bounded

Tracker schedule hợp lệ khi:

- `deleted_at IS NULL`;
- effective reminder config là enabled canonical hoặc legacy compatibility;
- action/input_mode hợp lệ;
- không phụ thuộc `kind`.

Một snapshot lấy dữ liệu theo số query bounded, không N+1:

- active tracker config;
- `max(entry.occurred_at)` theo tracker, chỉ `entry.deleted_at IS NULL`;
- `max(reminder_dispatch.dispatched_on)` theo tracker và các candidate-date dispatch cần dedupe;
- pending recovery hiện hành;
- subscription/settings query hiện hành giữ nguyên.

Có thể dùng aggregate subquery/CTE hoặc một số query hằng; cấm query một lần/tracker. Heap chỉ giữ ID,
mode/interval/action/time và scheduling metadata tối thiểu; không giữ decrypted name, reminder text,
push endpoint hay key.

Mọi civil date/time tính theo fixed `Asia/Ho_Chi_Minh` (`+07:00`). `occurred_at` phải đổi sang VN trước
khi lấy `.date()`; không dùng server local date/UTC date trực tiếp.

#### 2.3.2 `fixed`

Gọi `N=reminder_interval_days`, `T=reminder_time`, grace window giữ 15 phút như 011d:

```text
if có last_scheduled_date:
    candidate_date = last_scheduled_date + N days
    trong khi candidate_date@T < now_vn - grace:
        candidate_date += N days
else:
    candidate_date = today_vn
    nếu today_vn@T < now_vn - grace: candidate_date = tomorrow
due_at = candidate_date@T +07:00
occurrence_on = candidate_date
```

Hệ quả bắt buộc:

- downtime không bắn dồn nhiều occurrence cũ; cadence được roll-forward theo bội số `N`;
- `sent`, `no_device`, exhausted hoặc claimed/pending đều giữ anchor ngày occurrence;
- temporary retry dùng cùng `occurrence_on`/dispatch row; chỉ sau terminal mới xếp occurrence
  `+N days`;
- restart/reload dựng lại cùng next date từ DB, không dựa vào heap cũ.

#### 2.3.3 `after_entry`

```text
last_entry_date = max(non-deleted occurred_at converted to VN).date() hoặc NULL
freshness_date = last_entry_date + N days nếu có entry

if freshness_date tồn tại và freshness_date@T >= now_vn - grace:
    candidate_date = freshness_date
else:
    candidate_date = today nếu today@T >= now_vn - grace, ngược lại tomorrow

while candidate_date đã có reminder_dispatch của tracker:
    candidate_date += 1 day
due_at = candidate_date@T +07:00
```

Quy tắc:

- chưa có entry và đã stale dùng giờ gần nhất: hôm nay nếu chưa qua grace, nếu không ngày mai;
- quá hạn không gửi ngay giữa ngày; reminder vẫn xuất hiện ở anchor wall-clock gần nhất;
- nếu không có entry sau notification, nhắc lại tối đa một lần/ngày; dispatch uniqueness chống duplicate;
- create/update `occurred_at`/soft-delete/restore entry set reload marker **sau commit**. Entry mới trước
  giờ due phải làm heap cũ mất hiệu lực và dời due thành `entry_date + N`;
- rollback/commit failure không phát reload;
- confirmation `confirm_event` tạo entry qua `TrackerStore`, vì vậy cũng phải đi qua cùng reload seam;
- entry soft-deleted không tính freshness; restore lại được tính.

#### 2.3.4 Dispatch-time revalidation, retry và stale item

Ngay trước dispatch, query tracker hiện tại và revalidate deleted/config/action/input. Item cũ sau PATCH
không được gửi theo config cũ. Pending recovery giữ đúng dispatch ID/date/retry metadata hiện hành;
không tạo row mới để né attempt count.

- `fixed`: terminal occurrence kế tiếp là `occurrence_on + N`.
- `after_entry`: terminal mà chưa có entry mới xếp ngày gần nhất chưa dispatch (thường ngày mai); entry
  mutation sẽ reload và thay lịch.
- stale unclaimed item không được gọi helper daily cũ một cách mù; recompute theo mode.
- subscription expiry scheduling, 07:00, retry/backoff, 24h recovery và observability của 011d không đổi.
- idle heap vẫn `asyncio` sleep/event wait; không thêm interval/tick/heartbeat/readyz DB probe.

Health snapshot thêm aggregate an toàn như `invalid_tracker_schedule_count` nếu có malformed rows; log
chỉ `occurrence_ref`/count/kind-mode metadata, không name, text, ciphertext hoặc UUID thô nếu không cần.

### 2.4 Web Push routing và confirmation boundary

Thay medication-specific builder bằng generic contract, ví dụ
`build_tracker_reminder_payload(tracker, dispatch_id, effective_config, today_vn)`; cập nhật toàn bộ call
site/test. Không giữ hai scheduler/payload paths song song.

| Action | URL payload | Tác dụng |
|---|---|---|
| `confirm_event` | `/reminder-confirm?dispatch=<id>` | Route hiện hữu gọi confirmation idempotent; chỉ tạo entry nếu tracker hiện vẫn `event + confirm_event`. |
| `open_tracker` | `/trackers` | Chỉ mở tab Theo dõi; không gọi confirm API, không tạo entry. |

Payload public-safe:

1. `title = "Nhắc nhở microSched"`.
2. Nếu `reminder_text` sau trim có nội dung, dùng chính text Owner đã chọn là public.
3. Nếu không có custom text:
  - private tracker: generic, không decrypt/reveal name, ví dụ “Đã tới hạn ghi nhận.”;
  - public `fixed`: “Đã tới hạn: <tracker name>”;
   - public `after_entry` có last entry: “Đã {days_overdue} ngày chưa ghi nhận: <tracker name>” (với days_overdue = max(N, (today_vn - last_entry_date).days));
  - chưa có entry: “Đã tới hạn ghi nhận: <tracker name>”.
4. Không đưa amount/unit/note/group/private state/ciphertext vào push.

`confirm_reminder_dispatch()` đổi eligibility từ `health + event` thành:

```text
effective reminder_action == confirm_event
AND tracker.input_mode == event
AND tracker còn active
```

Kind không còn là confirmation gate. Nếu action/input thay đổi sau lúc push được gửi, tap link cũ trả
`409`, không tạo entry — fail-safe quan trọng vì `reminder_dispatch` không snapshot action. Idempotency
`confirmed_entry_id` và private unlock gate giữ nguyên. `open_tracker` không có đường nào gọi hàm này.

### 2.5 UI/UX

031B chỉ bắt đầu sau khi contract 031A đã được review/merge và frontend lane rebase đúng `develop`.

#### 2.5.1 Group/tracker forms

- Kind select có ba label thống nhất: `health = Sức khoẻ`, `finance = Tài chính`,
  `general = Chung`; dùng một helper mapping, không ternary hai nhánh khiến `general` rơi thành Tài chính.
- Group đang edit vẫn không đổi kind; muốn đổi tạo group mới và move tracker explicit như contract
  composite FK hiện hành.
- Reminder fieldset đổi tên **“Nhắc nhở”** và hiện cho mọi kind/input mode.
- Khi bật:
  - Mode: “Theo lịch cố định” / “Sau lần ghi gần nhất”;
  - Interval numeric integer, min 1, copy: “Mỗi N ngày” hoặc “Nhắc sau N ngày chưa ghi” theo mode;
  - Giờ nhắc (`type=time`);
  - Action:
    - `event`: cho chọn “Xác nhận và ghi một chạm” hoặc “Mở tracker để ghi”;
    - `money|quantity`: chỉ hiển thị/submit “Mở tracker để nhập số liệu”; không render option
      `confirm_event`;
  - Text public: “Nội dung hiện trên màn hình khoá (không bắt buộc)” + microcopy nói rõ đây là bề mặt
    công khai.
- Chuyển input mode từ event sang money/quantity trong form tự đổi action sang `open_tracker`; không
  giữ hidden stale `confirm_event`.
- Tắt reminder gửi toàn bộ `mode/interval/action/time/text = null`.
- API legacy read đã canonicalize nên form cũ mở ra phải hiện `fixed / 1 / confirm_event`.

Khi bật reminder, create **và** update đều gọi `ensurePushSubscription()` trước save; synthetic
`ensure_push` phải bị strip khỏi JSON API ở cả hai path. Nếu browser từ chối permission, không lưu trạng
thái “đã bật” giả; hiện lỗi hành động được. Tắt reminder không đòi permission.

#### 2.5.2 Schedule summary và deep link

Thay helper/section chỉ hiểu “group theo giờ + ghi ngay” bằng summary generic:

- `fixed`: `Mỗi 3 ngày · 09:00 · Mở tracker`;
- `after_entry`: `Sau 3 ngày chưa ghi · 09:00 · Xác nhận một chạm/Mở tracker`.

Không đưa nút ghi amount/quantity không có input. Nếu giữ shortcut “Ghi” thì chỉ render cho
`event + confirm_event`; open-tracker action dùng đường mở/focus capture UI, không tạo entry.

`/trackers` phải là deep-link hợp lệ trong `App.tsx`: authenticated user mở trực tiếp hoặc từ service
worker thấy tab Theo dõi, refresh không rơi về Task. V1 không cần detail route/highlight.

#### 2.5.3 UI hard rules

Tuân `docs/ui-brief.md` §6 và `docs/qa-framework.md`:

- chỉ component `@/components/ui/*`, không hardcode màu, không dark mode, chữ ≥12px, touch target;
- không hover-only; keyboard/focus/label/error đầy đủ;
- vì 031B bắt buộc sửa `TrackerScreen.tsx`, thay bốn `<button>` disclosure thô hiện hữu bằng primitive
  hợp lệ trong cùng file; đây là compliance debt trên đúng touched surface, không phải redesign;
- test mobile 390×844 + desktop 1280×800 với text dài/no-space/emoji/tiếng Việt dấu dày.

## 3. Phạm vi sửa file

Tên migration/test mới là pattern, executor lấy tên thật theo head. Không được dùng bảng này làm giấy
phép sửa mọi file trong thư mục.

### 3.1 031A — Terra/xhigh backend, migration, CronTimer

| File/bề mặt | Sửa được | Mục đích |
|---|---:|---|
| `backend/alembic/versions/<next>_tracker_reminder_evolution.py` | tạo mới | nullable expand, legacy backfill, CHECK widening, downgrade guard |
| `backend/app/domain/models.py` | có | SQLModel fields/constraints/kind |
| `backend/app/domain/tracker.py` | có | DTO, canonical validation, legacy compatibility, reload markers |
| `backend/app/core/cron_timer.py` | có | generic fixed/after-entry schedule, bounded aggregates, revalidation |
| `backend/app/domain/reminder.py` | có | generic payload + confirm action boundary |
| `backend/app/domain/subscription.py` | chỉ khi cần | giữ/diễn đạt finance+money invariant; không đổi semantics |
| `backend/app/web/routers/tracker.py`, `push.py` | chỉ khi contract cần | map lỗi 422/409; không thêm scheduler endpoint |
| `backend/scripts/cutover_v2.py` | có, hẹp | thêm ba persisted tracker columns để inventory/drift không bỏ sót |
| `backend/scripts/prepare_qa_branch.py` | review bắt buộc; sửa chỉ nếu test chỉ ra | `reminder_text` đã scrub; không log config/text mới |
| `backend/tests/test_tracker_api.py` | có | kind/reminder/API matrix + reload |
| `backend/tests/test_cron_timer.py` | có | fixed/after_entry/restart/no-poll/retry |
| `backend/tests/test_reminder_domain.py`, `test_push_api.py` | có | payload URL/privacy/confirmation |
| `backend/tests/test_subscription_api.py` | có | `general + money` bị từ chối |
| `backend/tests/test_schema_models.py` | có | metadata/constraint names |
| `backend/tests/test_migration_<revision>.py` | tạo mới | backfill/constraint/downgrade fail-closed |
| `backend/tests/test_cutover_v2_pg.py` | nếu persisted-column test cần | schema inventory tương thích |
| `docs/tracking-brief.md` | dated note hẹp | supersede daily medication-only bằng quyết định 031 |
| `docs/schema-v1-brief.md`, `docs/schema-physical-brief.md` | dated/current-state delta hẹp | `general` + ba cột/cadence mới |
| `docs/forward-spec.md`, `CLAUDE.md` | chỉ dòng current-state liên quan | bỏ mô tả health+finance-only/daily-only đã lỗi thời; không viết session log dài |

### 3.2 031B — Gemini 3.7/high UI/UX

| File/bề mặt | Sửa được | Mục đích |
|---|---:|---|
| `frontend/src/tracker-ui.ts` | có | types, mutation payload, summary helper |
| `frontend/src/tracker-ui.test.ts` | có | pure types/summary/action tests |
| `frontend/src/GroupForm.tsx` | có | kind Chung |
| `frontend/src/TrackerForm.tsx` | có | generic reminder form + action boundary |
| `frontend/src/TrackerScreen.tsx` | có | save permission flow, summary, touched raw-button compliance |
| `frontend/src/App.tsx`, `frontend/src/lib/route.ts` | có, hẹp | deep-link `/trackers` |
| `frontend/src/push-subscription.ts` | chỉ khi needed | reuse permission seam; không đổi VAPID contract |
| `frontend/src/ReminderConfirmScreen.tsx` | có | chuẩn hoá toast/status copy thành thông điệp chung (thay vì hardcode "uống thuốc") |
| `frontend/e2e/fixtures/tracker.ts` | có | type/fixture ba kind + config mới |
| `frontend/e2e/tracker.spec.ts`, `tracker-error.spec.ts` | có | form/route/action/browser cases |
| `frontend/e2e/reminder-confirm.spec.ts` | có | generic confirm/open regression |
| `frontend/e2e/ui-standards.spec.ts`, `polling.spec.ts` | nếu expectation thay | no raw control/no poll/deep-link regression |

File phát sinh ngoài bảng: dừng, nêu exact lý do và xin T1/Owner mở scope trước khi sửa. `agent-tasks/README.md`
do T1/Owner cập nhật status sau review/approval; hai executor không tự nâng trạng thái.

## 4. Những điều KHÔNG được làm (Hard boundaries)

1. Không tạo bảng `schedule`, `recurrence`, `backup_job` hoặc queue mới; không thêm `anchor_date`.
2. Không thêm recurrence theo giờ/tuần/tháng, weekday, RRULE hoặc timezone per user trong Task 031.
3. Không thêm backup-specific page/cell/app_setting/script/retention/cloud automation. `general` là primitive
   chung, không phải ngụy trang cho một feature backup mới.
4. Không đổi/xoá composite FK; không cho edit `tracker_group.kind` tại chỗ.
5. Không cho `general + money` chứa subscription; không nới invariant thành “mọi money tracker”.
6. Không cho money/quantity dùng `confirm_event`; không tạo amount/quantity/entry rỗng từ notification.
7. Không dùng notification hoặc dispatch date như entry cho `after_entry`; freshness chỉ từ non-deleted
   `entry.occurred_at`.
8. Không sửa cadence/retry/subscription 07:00/pending recovery của 011d ngoài phần generic tracker cần
   thiết; không tạo external cron, HTTP heartbeat, tick loop hoặc DB polling.
9. Không đổi unique key `reminder_dispatch(subject_type,subject_id,dispatched_on)` và không tạo dispatch
   mới cho retry cùng occurrence.
10. Không leak tracker name/text/ciphertext/private data vào heap, log, test artifact hoặc push private.
    `reminder_text` là public chỉ vì Owner chủ động nhập; không suy mọi tracker text là public.
11. Không đặt DB default `1` vô điều kiện; không silently repair malformed production rows bằng đoán.
12. Không auto-apply migration trong deploy; không downgrade Neon; không destructive QA/push automation
    trên production.
13. Không dùng production data thật trong test lane. Ephemeral branch phải scrub và truncate push/
    dispatch trước test.
14. Không đổi dashboard semantics ngoài việc general đi qua type/label đúng; không redesign toàn màn
    Tracker, không dark mode, không raw HTML control mới.
15. Không sửa user-owned dirty files ngoài scope, không commit thẳng `develop`, không merge/auto-merge
    khi chưa có exact-head review + CI + authority.

## 5. Acceptance criteria và test bắt buộc

### 5.1 Schema/migration (PG thật)

- [ ] Upgrade từ schema trước 031 với fixture legacy tạo đúng `fixed/1/confirm_event`; text/time/name không
      đổi.
- [ ] Tracker không reminder giữ ba cột mới null; không có phantom interval `1`.
- [ ] Insert group/tracker `general` pass; general tracker vào health/finance group fail đúng composite FK.
- [ ] Direct SQL invalid kind/mode/action/interval `0/-1` fail đúng named CHECK.
- [ ] Direct SQL `money + confirm_event` fail action-input CHECK; null legacy fields vẫn được phép trong
      expand window.
- [ ] SQLModel metadata constraint names/expressions khớp migration; drift checker xanh.
- [ ] Old-writer fixture `health + event + reminder_time`, ba field mới omitted, được scheduler/API mới
      nhìn thành legacy effective config.
- [ ] Downgrade local sạch legacy-equivalent pass rồi upgrade head pass; có general hoặc advanced reminder
      thì downgrade đỏ trước khi drop dữ liệu.
- [ ] `cutover_v2` persisted tracker columns chứa đủ ba field mới; canonical schema inventory không bỏ
      sót drift.

### 5.2 Domain/API validation

- [ ] CRUD group/tracker nhận/return `general`; error label không gọi general là Tài chính.
- [ ] Create enabled reminder thiếu interval đặt `1`; thiếu mode/action/time trả `422` trừ legacy shape.
- [ ] Matrix event/money/quantity × action đúng §2.2.3 ở create và PATCH effective-state.
- [ ] Disable canonical clear toàn bộ bundle/text; re-enable không phục hồi hidden action cũ.
- [ ] Cached old PWA payload time/text-only trên health-event được canonicalize; explicit-null hybrid bị
      từ chối.
- [ ] PATCH đổi event→money cùng action→open pass; đổi riêng input mode khi confirm còn sống trả `422`.
- [ ] Mọi thay đổi schedule và entry freshness mutation phát đúng một reload sau commit; rollback 0.
- [ ] `general + money` subscription create/update/renew fail; `finance + money` regression pass; tracker
      có live sub không đổi sang general.
- [ ] Privacy/UUIDv7/idempotent create/read gates hiện hành không regress.

### 5.3 CronTimer unit/integration

- [ ] Fixed N=3: không history chọn giờ gần nhất; có last dispatch `D` chọn `D+3`; terminal chọn tiếp +3,
      không +1.
- [ ] Fixed downtime nhiều chu kỳ roll-forward theo bội N, không burst catch-up; grace 15 phút đúng.
- [ ] Restart/reload cùng DB snapshot cho cùng candidate; sent/no-device/pending đều không duplicate date.
- [ ] After-entry dùng max non-deleted `occurred_at` theo ngày VN; case quanh `17:00 UTC` chứng minh không
      lệch ngày.
- [ ] Entry mới + N ngày chưa tới xếp đúng freshness date; no-entry/overdue chọn hôm nay trước giờ hoặc
      ngày mai sau giờ.
- [ ] Overdue không có entry nhắc tối đa mỗi ngày một lần; tạo entry sau reminder dời lịch +N; soft-delete
      entry làm freshness quay lại row trước, restore đảo lại.
- [ ] General health finance đều eligible theo config; kind không còn là scheduler branch.
- [ ] Malformed hybrid bị skip + health count/log an toàn, không crash toàn timer.
- [ ] Dispatch-time config/action change làm item cũ bị bỏ; pending recovery giữ dispatch ID/attempt/date.
- [ ] Query count snapshot là hằng số với 1 và 100 tracker; idle ảo nhiều giờ không thêm DB query.
- [ ] Subscription schedule 07:00, retry `30s→2m→10m`, recovery 24h, timer supervision/no-op disabled
      regression xanh nguyên vẹn.

### 5.4 Web Push/confirmation

- [ ] `confirm_event` URL exact `/reminder-confirm?dispatch=<uuid>`; `open_tracker` URL exact `/trackers`.
- [ ] Custom text trim và được dùng; private fallback không chứa decrypted name/ciphertext; public
      fixed/after-entry copy đúng mode/N.
- [ ] Confirm event trên `general + event` tạo đúng một entry; hai tap/device vẫn một confirmed entry.
- [ ] Confirm link cũ sau khi tracker đổi sang open/money/quantity trả `409`, tạo 0 entry.
- [ ] `open_tracker` flow không gọi confirm endpoint và không tạo entry dù tap/reload nhiều lần.
- [ ] No-device/temporary/exhausted outcomes không làm mất occurrence kế tiếp.

### 5.5 Frontend unit/component/Playwright

- [ ] Group/tracker select render “Chung”; list badge/summary không rơi vào label Tài chính.
- [ ] Reminder fieldset hiện cho mọi kind; mode/interval/time/action/text serialize canonical.
- [ ] Money/quantity DOM không có option confirm; đổi mode tự chuyển open; event cho đủ hai action.
- [ ] Create và update enabled reminder đều ensure push trước save và không gửi `ensure_push` lên API;
      permission denied giữ dialog/data và không lưu enabled giả.
- [ ] Legacy tracker mở form thành fixed/1/confirm; disable gửi null bundle.
- [ ] Summary phân biệt fixed/after-entry/N/action; money/quantity không có shortcut tạo entry.
- [ ] Direct `/trackers`, refresh và notification-click đều mở tab Theo dõi; `/reminder-confirm` regression
      không bị route `/trackers` nuốt.
- [ ] Static/UI guard: 0 raw `<button>/<input>/<select>` trong ba touched tracker form/screen files; không
      hardcode màu, text ≥12px, keyboard/focus/aria/44px touch path dùng được.
- [ ] Playwright mobile 390×844 + desktop 1280×800: create/edit general fixed, general after-entry,
      money open-tracker, validation error; long/no-space/Vietnamese/emoji không tràn hoặc đẩy action.
- [ ] Physical iPhone/Safari Web Push là lane riêng. Chưa chạy thì ghi **CHƯA VERIFY**, không lấy Chromium
      thay thế.

### 5.6 RED → GREEN proof bắt buộc

Mỗi guard dưới đây phải được cố ý làm sai trong local throwaway diff, thấy test đỏ **đúng invariant**,
restore code rồi thấy xanh. Không commit sabotage; dán raw command/output RED và GREEN vào PR receipt:

1. Bỏ `general` khỏi một kind CHECK/model → general schema/model test đỏ → restore xanh.
2. Bypass action-input validation cho `money + confirm_event` → PG/API test đỏ → restore xanh.
3. Đổi fixed next occurrence từ `+N` thành `+1` → N=3 test đỏ → restore xanh.
4. Tính after-entry từ UTC date hoặc tính cả soft-deleted entry → timezone/delete test đỏ → restore xanh.
5. Route `open_tracker` nhầm sang `/reminder-confirm` → payload/e2e test đỏ → restore xanh.
6. Bỏ confirmation action revalidation → stale-link zero-entry test đỏ → restore xanh.
7. Render confirm option cho money trong UI → component/Playwright guard đỏ → restore xanh.
8. Nới subscription parent thành mọi money tracker → general-subscription regression đỏ → restore xanh.
9. Seed advanced reminder rồi downgrade → migration phải đỏ fail-closed; xóa fixture/legacy-only →
   round-trip xanh.

### 5.7 Lệnh tối thiểu và report boundary

Fresh worktree: `npm ci` trong `frontend`. Docker Desktop là prerequisite cho PG local; nếu daemon tắt,
báo blocker môi trường, không chuyển test sang Neon production.

```text
# backend/
uv run ruff check .
uv run ruff format --check .
uv run pytest -m "not pg"
uv run pytest -m pg

# frontend/
npm run lint
npm test
npm run build
npm run e2e

# root/
git diff --check
pre-commit run --all-files
git status --short
```

CI required checks phải giữ nguyên tên và terminal xanh:

- `Backend checks`
- `Frontend checks`
- `Frontend e2e`
- `Repository hooks`
- `Secret scan`
- `Migration QA`
- `Production dependency check`

Báo cáo mỗi PR tách: **ĐÃ CHẠY (raw output)** · **CHƯA CHẠY** · **SKIPPED** · **SUY LUẬN** ·
**MIGRATION** · **CI** · **PRODUCTION** · **BROWSER/DEVICE**. Local pass không chứng minh CI, deploy,
timer live hoặc iPhone.

## 6. Quy trình 3 tầng, release gates và phân vai thi công

### 6.1 Gate trước thi công

1. Independent T3/Luna `xhigh` hoặc route mạnh callable tương đương review exact spec theo tối thiểu:
   schema compatibility, domain invariants, scheduler/idempotency/restart, privacy/push, UI/mobile,
   migration/rollback/ops. Reviewer không phải writer 031A/031B.
2. Owner/T1 giải mọi P0/P1 và chốt exact spec revision; chưa có gate thì không viết implementation.
3. Query Runtime Catalog/probe exact route/model/effort lúc giao lane; không silently substitute.
4. Tạo hai worktree/branch riêng, prefix theo policy hiện hành; tuyệt đối không dùng dirty main worktree.

### 6.2 Tầng 1 — local/CI fast + PG throwaway

**031A — Terra/xhigh:** migration/models/domain/CronTimer/push/tests/docs. Chạy unit + PG round-trip trên
Docker `pgvector:pg18`, migration drift và RED/GREEN. Không chạm production/push thật.

**031B — Gemini 3.7/high:** bắt đầu sau 031A API exact; frontend/tests/Playwright. Không tự đổi API/domain
contract. Nếu UI phát hiện contract thiếu, dừng và trả finding cho T1/Terra, không vá backend trong cùng
worktree.

Mỗi PR phải có independent exact-head review và CI terminal trước gate tiếp theo.

### 6.3 Tầng 2 — Neon ephemeral branch đã scrub

Sau local/CI xanh, 031A rehearsal theo `AGENTS.md` §9 / `docs/devops-brief.md` §8.3:

```powershell
neonctl branches create --name qa-031-tracker-reminder --parent main
cd backend
uv run python -m scripts.prepare_qa_branch --branch-url "<BRANCH_NEON_MIGRATOR_URL>" --prod-key "<PROD_KEY>" --pin 123456
$env:NEON_QA_BRANCH = "1"
uv run alembic upgrade head
```

Placeholder secret không được thay bằng giá trị thật trong prompt/PR/log. Receipt phải chứng minh:

- scrub hoàn tất; `push_subscription` và `reminder_dispatch` đã truncate trước QA;
- migration upgrade + exact catalog constraints/backfill aggregate;
- API cases general/fixed/after-entry/subscription invariant trên data scrubbed;
- Cron scheduling pure/integration không gửi Web Push thật;
- 031B Playwright có thể dùng `ms_session=qa_token`, PIN `123456`, nhưng không mở Chrome profile thật.

Neon ephemeral **không downgrade**. Sau khi xuất receipt, xóa đúng branch đã resolve:

```powershell
neonctl branches delete qa-031-tracker-reminder
```

List/resolve exact branch ID trước delete; không để branch QA sống sau task.

### 6.4 Tầng 3 — production migration/deploy tuần tự

Do merge `develop` tự deploy và binary 031A query cột mới, thứ tự bắt buộc:

1. PR 031A exact head đã independent-review + toàn CI xanh; re-query head/base/mergeability/checks.
2. Owner xác nhận có fresh encrypted backup/restore path theo workflow local-manual hiện hành; Task 031
   không tự động hoá backup.
3. Từ exact reviewed PR head, apply migration 031 thủ công lên Neon production **trước merge**. Binary cũ
   vẫn chạy được vì expand nullable và legacy-compatible.
4. Query `information_schema.columns`, `pg_constraint` và aggregate legacy mapping; không in text/name.
5. Merge 031A bằng compare-and-swap authority hiện hành; chờ deploy exact merge SHA; verify
   `/api/readyz.commit=<merge SHA>` và `db=up`. `/api/healthz` không phải DB proof.
6. Verify CronTimer startup/reload/next due/invalid count trên structured receipt không dữ liệu cá nhân.
   Không tạo general production data trước khi 031-capable backend live.
7. Sau 031A ổn định, rebase/run/review/merge 031B; verify exact new production SHA và route
   `/trackers`. Device/Web Push thật chỉ chạy khi Owner cấp lane/account rõ ràng.

Sau khi user đã tạo `general` hoặc advanced reminder, rollback schema/binary cũ có thể không đọc được dữ
liệu mới. Policy là **roll-forward fix**; downgrade guard phải chặn mất dữ liệu. Không dùng việc “Fly máy
cũ vẫn healthy” làm bằng chứng rollback an toàn.

### 6.5 Ownership và điểm dừng

| Vai | Sở hữu | Không được tự làm |
|---|---|---|
| T1 | scope, exact API contract, reconcile findings, migration/deploy gate recommendation, status board sau approval | không tự gọi spec complete = runtime accepted; không merge/release nếu không có authority |
| T2 Terra/xhigh (031A) | backend, migration, scheduler, push, PG tests, decision-record delta | không sửa UI ngoài generated/shared contract; không apply prod/merge nếu gate chưa cấp |
| T2 Gemini 3.7/high (031B) | UI/UX, frontend types/tests/Playwright, mobile/desktop states | không đổi schema/domain, không review chính diff mình như independent T3 |
| T3 independent | adversarial review exact heads + receipt audit | không viết chồng cùng worktree; finding phải có file/line/invariant |
| Owner | product/architecture veto, prod migration/device/account approval | không bị buộc đọc code; T1 phải báo user-visible impact + số đo thật |

Executor dừng sau khoảng hai vòng bí, khi evidence production khác preflight, khi constraint/doc conflict
không được quyết định này supersede rõ, hoặc khi cần file/action ngoài scope. Báo raw log và hai phía
mâu thuẫn; không tự phát minh kiến trúc.
