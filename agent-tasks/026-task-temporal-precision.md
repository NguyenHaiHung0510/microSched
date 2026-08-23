# 026 — Task temporal precision: ngày, ngày + giờ, hoặc chưa xếp lịch

> **Executor: T2 (chọn exact route từ Runtime Catalog khi giao) · Bậc: L2 · Effort đề xuất:
> high · Skill gợi ý: Playwright cho browser QA · MCP cần: không bắt buộc.**
> **Trạng thái: ✅ OWNER-APPROVED DECISION 2026-08-24 — SPEC SẴN REVIEW.**
> Đây là task product/schema độc lập. PR spec chỉ viết hợp đồng; implementation phải đi qua branch
> `feat/026-task-temporal-precision` và các gate bên dưới. Không tự merge.

Đọc trước khi thi công: `CLAUDE.md` · `AGENTS.md` · `docs/schema-v1-brief.md` ·
`docs/schema-physical-brief.md` §2/§3/§5 · `docs/frontend-brief.md` · `docs/ui-brief.md` §4/§6/§8–9 ·
`docs/qa-framework.md` · `agent-tasks/010b-calendar-scroll-view.md` ·
`agent-tasks/017-offline-outbox.md` · `agent-tasks/022-task-day-timeline.md` · code/test nêu ở §1.

## 0. Kết quả người dùng phải nhận được

Một task có **đúng một** trong ba kiểu lịch:

| Kiểu | Ví dụ người dùng | Điều app được lưu/hiện |
|---|---|---|
| **Ngày** | “Làm trong hôm nay”, không nói giờ | ngày `2026-08-24`; **không** có giờ/phút ẩn |
| **Ngày + giờ** | “09:30 ngày 24/08” | instant có timezone, render lại `09:30` theo múi giờ app |
| **Chưa xếp lịch** | chưa muốn đặt ngày | không ngày, không giờ |

Mọi bề mặt tạo task mới mặc định chọn **Ngày · hôm nay**. Đây là default **UI**; API không tự lấy
ngày của server khi caller cũ bỏ field. Quick-add ở màn Task vẫn gõ một dòng + Enter, nhưng task mới
thuộc hôm nay thay vì rơi vào “Chưa xếp lịch”. Form đầy đủ cho đổi sang “Ngày + giờ” hoặc “Chưa xếp
lịch”.

🔒 **Không được biến “không nói giờ” thành `23:59`, `00:00`, phút hiện tại hay một instant nào khác.**
Ngày-only là một `DATE`, không phải timestamp giả được giấu khỏi UI.

## 1. Sự thật hiện tại và conflict được xử lý

### 1.1 Evidence trên `origin/develop=e2a24682…` ngày 2026-08-24

- **[QUAN SÁT]** Model `Task` chỉ có `due_at timestamptz nullable`
  (`backend/app/domain/models.py:128-131`) và index đơn `ix_task_due_at`
  (`backend/app/domain/models.py:693`). Chưa có cột ngày-only hoặc precision.
- **[QUAN SÁT]** `TaskCreate` / `TaskUpdate` / `TaskRead` chỉ có `due_at`
  (`backend/app/domain/tasks.py:64-126`); write naive datetime bị chặn
  (`backend/app/domain/tasks.py:83-115`).
- **[QUAN SÁT]** Form hiện chỉ có một `Input type="datetime-local"`
  (`frontend/src/TaskForm.tsx:60`, `:124-126`); serializer chỉ sinh `due_at`
  (`frontend/src/task-ui.ts:13-21`, `:40-42`).
- **[QUAN SÁT]** Quick-add đang gửi `due_at: null` (`frontend/src/TasksScreen.tsx:405-414`).
  Dời nhanh ở Task và Calendar gọi `endOfDayVietnam()` (`frontend/src/TasksScreen.tsx:754-761`,
  `frontend/src/DayDetailDialog.tsx:219-225`); helper trả `23:59+07`
  (`frontend/src/calendar-scroll.ts:186-188`). E2E đang khóa chính heuristic này tại
  `frontend/e2e/calendar-scroll.spec.ts:244`, `:289`, `:492`.
- **[QUAN SÁT]** Timeline/cursor 022 đã được merge vào code: query bucket và sort vẫn dựa hoàn toàn
  vào `Task.due_at`; SQL hiện order `pinned DESC, due_at ASC NULLS LAST, created_at DESC, id ASC` và
  keyset hand-code cùng fields (`backend/app/domain/tasks.py:361-430`, `:472-506`, `:582-593`). Header
  spec 022 còn ghi implementation pending, nhưng Git history hiện có merge PR #142; implementation
  phải tin cây code + test hiện tại, không tin header trạng thái cũ.
- **[QUAN SÁT]** Task 017 bắt row giữ `payload_sha256` + `payload_byte_length` immutable và retry cùng
  UUID/payload (`agent-tasks/017-offline-outbox.md:185-199`); do đó payload cũ `{due_at:null}` không
  được sửa trong flusher chỉ để khớp DTO mới.
- **[QUAN SÁT]** Alembic head trên base là `0009_legacy_preserving_columns.py`. Executor phải rebase
  rồi kiểm lại head trước khi đặt revision.
- **[SUY LUẬN]** Một giá trị lịch sử đúng `23:59` có thể do người dùng thật sự chọn, cũng có thể do
  heuristic 010b. Không có provenance đáng tin để phân biệt hai trường hợp.
- **[KHÔNG BIẾT]** Spec lane này không query dữ liệu task thật trên Neon, không biết distribution
  `due_at` hiện tại và không được suy từ snapshot cũ. Implementation phải chạy preflight chỉ trả
  aggregate/count, không in title/body hay dữ liệu cá nhân.

### 1.2 Supersession có chủ đích

Quyết định owner ngày 2026-08-24 thắng các đoạn sau khi không tương thích:

| Nguồn cũ | Phần bị thay | Hợp đồng mới |
|---|---|---|
| `schema-v1-brief.md` ERD `task.due_at` duy nhất | mô hình deadline chỉ-timestamp | §2: `due_precision` + `due_on` + `due_at` |
| `010b` §5.6 (`:471`) | dời task vào `23:59+07` | §2.6: giữ precision, không bịa giờ |
| `022` §2.1/§3 (`:72-76`, `:173`) | mọi task có lịch đều là instant | §4–5: range/cursor hiểu cả `DATE` và instant |
| Test `endOfDayVietnam` và ba assertion `23:59` | guard cho heuristic cũ | thay bằng guard “không có phút bịa” |

Các quyết định **không** bị mở lại: timezone app là `Asia/Ho_Chi_Minh`; timeline 7 ngày/cursor bounded;
privacy gate; soft-delete/undo; UUIDv7/idempotency; Task 017 typed outbox. Sau merge spec, integration
owner cập nhật index/status board riêng; PR 026 không sửa bảng trạng thái dùng chung.

## 2. Hợp đồng domain đã khóa

### 2.1 Ba field vật lý, một invariant

```text
due_precision = "none" | "date" | "datetime"
due_on        = DATE nullable
due_at        = TIMESTAMPTZ nullable
```

| `due_precision` | `due_on` | `due_at` | Hợp lệ |
|---|---|---|---|
| `none` | `NULL` | `NULL` | ✅ chưa xếp lịch |
| `date` | non-NULL | `NULL` | ✅ ngày-only |
| `datetime` | `NULL` | non-NULL, aware | ✅ ngày + giờ |
| mọi tổ hợp khác | | | ❌ API `422`, DB CHECK chặn |

Tên CHECK canonical: `ck_task_due_shape`. `due_precision` là `TEXT + CHECK`, theo convention của
`schema-physical-brief.md` §4; không dùng PostgreSQL native ENUM.

### 2.2 Create/read examples

Response luôn trả đủ ba field để caller không phải đoán:

```json
{"due_precision":"date","due_on":"2026-08-24","due_at":null}
{"due_precision":"datetime","due_on":null,"due_at":"2026-08-24T09:30:00+07:00"}
{"due_precision":"none","due_on":null,"due_at":null}
```

New first-party writes gửi `due_precision` tường minh. Field không thuộc shape có thể bỏ hoặc gửi
`null`; server canonicalize response như trên. Không có giá trị thứ tư kiểu `all_day`: đó là ngôn
ngữ event, không phải task.

### 2.3 Default

- Form tạo mới và quick-add Task: `due_precision="date"`, `due_on=todayInVietnam()`.
- Quick-add từ một ô Calendar: `due_precision="date"`, `due_on=<ngày ô đó>` (§2.6; UI mới thuộc 027).
- Caller API cũ bỏ cả ba field: server dùng `none`. **Không** lấy ngày hiện tại ở DB/backend vì việc
  đó biến cùng payload thành kết quả khác theo thời điểm/múi giờ server.
- Edit dùng shape đang lưu; không tự đổi task cũ sang default hôm nay.

### 2.4 Render, overdue và sort

- `date`: hiện ngày, **không** hiện `00:00`/`23:59`; overdue khi `due_on < today` trong
  `Asia/Ho_Chi_Minh`. Task date-only của hôm nay chưa trễ cho tới khi sang ngày kế tiếp.
- `datetime`: hiện ngày + giờ theo `Asia/Ho_Chi_Minh`; overdue khi `due_at < now`.
- `none`: hiện “Chưa xếp lịch”, không bao giờ overdue.
- Mọi bucket và mọi continuation dùng **một** tuple canonical, theo đúng thứ tự/chiều:
  `pinned DESC` → `scheduled_rank ASC` (`date|datetime=0`, `none=1`) →
  `schedule_day ASC NULLS LAST` → `precision_rank ASC` (`datetime=0`, `date=1`, `none=2`) →
  `due_at ASC NULLS LAST` → `created_at DESC` → `id ASC`. `schedule_day` là `due_on` cho `date`, ngày
  Việt Nam của `due_at` cho `datetime` (SQL: `(due_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`), và
  `NULL` cho `none`. Vì vậy các ngày đi theo thứ tự civil; trong cùng ngày, giờ cụ thể đi trước
  date-only; unscheduled đi cuối. Đây là **sort semantic**, không phải lưu một giờ giả.
- Timeline, Calendar và dialog phải dùng cùng helper typed; cấm mỗi màn tự suy từ `due_at`.

### 2.5 Editing transitions

| Từ | Người dùng chọn | Hành vi form/save |
|---|---|---|
| `none` | `date` | điền ngày hôm nay, người dùng được sửa |
| `none` | `datetime` | điền ngày hôm nay, **ô giờ rỗng**, disable Save tới khi nhập giờ |
| `date` | `datetime` | giữ ngày, giờ rỗng; không lấy giờ hiện tại |
| `datetime` | `date` | giữ **ngày local Việt Nam**, bỏ giờ sau action rõ ràng |
| bất kỳ | `none` | xoá cả `due_on` và `due_at` |
| cùng precision | sửa giá trị | validate shape rồi lưu atomic |

Không parse giờ từ title/body trong task này. Nếu user chỉ gõ “mai họp” mà không chọn giờ, app vẫn
là date-only; natural-language/AI scheduling là feature riêng, DEFER.

### 2.6 Dời task sang ngày khác

Một helper domain/frontend duy nhất nhận **full old schedule + target date**:

- `date` → `date`, đổi `due_on` sang target.
- `datetime` → `datetime`, giữ nguyên clock time hiển thị trong `Asia/Ho_Chi_Minh`, ghép với target
  rồi chuyển thành instant mới.
- `none` → `date`, target là ngày người dùng vừa chọn.

Áp cho “Hôm nay/Mai/Ngày kia”, picker trong `DayDetailDialog`, Calendar drag nếu 027 chọn làm, và
undo. Undo giữ toàn bộ `{due_precision,due_on,due_at}` cũ; không chỉ giữ `due_at`.

### 2.7 Timezone và DST

- Date-only là civil `DATE`; không convert qua `Date`, UTC hay timezone thiết bị.
- Datetime API là offset-aware instant; UI chuyển `datetime-local` bằng named zone
  `Asia/Ho_Chi_Minh`, không bằng `new Date(input)` theo máy đang mở browser.
- Current app zone không có DST trong phạm vi vận hành hiện tại. Vẫn dùng IANA `ZoneInfo`/`Intl` thay
  vì rải `+07:00` để giữ contract có tên. Browser ở UTC/America vẫn phải hiện cùng ngày + giờ Việt Nam.
- Nếu sau này cho đổi app zone sang vùng có DST, đó là quyết định product riêng. Không âm thầm
  normalize nonexistent/ambiguous civil time trong task 026; contract tương lai phải chọn reject hay
  disambiguation tường minh trước khi mở setting đó.

## 3. DB và migration — expand, contract an toàn, rồi retire old writer

Một migration duy nhất đặt `NOT NULL + CHECK` **trước** deploy sẽ làm app cũ hỏng: code cũ ghi
`due_at` nhưng không ghi precision. Chỉ “đợi deploy xong rồi backfill” cũng còn race với old Fly
machine/request đang chạy. Vì vậy 026 có ba PR tuần tự; contract giữ một trigger compatibility tới khi
có receipt chứng minh không còn binary cũ.

### 3.1 026A — expand + dual-read/write

Branch/PR: `feat/026-task-temporal-precision`.

Migration dự kiến từ head hiện tại: `0010_task_due_precision_expand.py` (nếu head đổi sau rebase,
chỉ đổi revision number/down_revision, không đổi contract):

1. thêm `task.due_precision TEXT NULL` và `task.due_on DATE NULL`, chưa thêm CHECK/NOT NULL;
2. backfill trong cùng transaction:
   - `due_at IS NULL` → `due_precision='none'`;
   - `due_at IS NOT NULL` → `due_precision='datetime'`;
   - `due_on` giữ `NULL` cho toàn bộ legacy rows;
3. không biến bất kỳ `23:59` legacy nào thành date-only;
4. thêm index `ix_task_due_on`; giữ `ix_task_due_at`;
5. server V2, trong **cùng transaction** trước mọi task INSERT/UPDATE, gọi
   `set_config('microsched.task_due_writer','v2',true)`; cờ transaction-local không được leak qua
   pooled connection;
6. thêm hai trigger function/trigger canonical, có tên cố định
   `fn_task_due_legacy_insert_v1` / `trg_task_due_legacy_insert_v1` và
   `fn_task_due_legacy_update_v1` / `trg_task_due_legacy_update_v1`:
   - đầu mỗi function: nếu `current_setting('microsched.task_due_writer', true)='v2'`, giữ nguyên NEW;
   - unmarked `BEFORE INSERT`: map `due_at NULL → none`, non-NULL → `datetime`, clear `due_on`;
   - unmarked `BEFORE UPDATE OF due_at`: map `NEW.due_at NULL → none`, non-NULL → `datetime`, clear
     `due_on`; old update chỉ title/status không kích hoạt trigger;
   - vì V2 write đã marked, invalid explicit V2 shape không được “sửa hộ” và CHECK sẽ chặn.

Code 026A đọc `due_precision IS NULL` theo cùng legacy mapping và **mọi write mới dual-write đủ
shape** + marker transaction-local. Khoảng giữa apply migration và deploy an toàn: unmarked old writer
được trigger canonicalize ngay, không để row NULL chờ “lần write kế tiếp”. Marker phải được set trong
transaction thực sự ghi row, không phải một connection/request setup rời transaction.

### 3.2 026B — contract

Chỉ bắt đầu sau khi 026A merge, CI/deploy xanh và `/api/readyz.commit` khớp merge SHA. Trigger §3.1
vẫn tồn tại trong suốt 026B, nên một old machine/request muộn không thể tạo shape vi phạm sau preflight.
Branch/PR: `feat/026b-task-temporal-contract`.

Migration dự kiến `0011_task_due_precision_contract.py`:

1. lấy migration/table lock trong transaction, backfill lại mọi row precision NULL theo mapping
   legacy rồi preflight count từng shape; fail nếu còn row không canonical;
2. set `due_precision NOT NULL`; **không đặt DB server default** trong compatibility window — default
   `'none'` sẽ che việc old INSERT bỏ precision và xung đột với `due_at` non-NULL trước trigger;
3. thêm `ck_task_due_precision_values` và `ck_task_due_shape`;
4. giữ cả hai trigger legacy §3.1; model metadata khớp constraints/indexes, còn catalog attestation
   kiểm exact trigger/function names + definitions.

Sau 026B, direct SQL shape của old binary vẫn deterministic:

| Old-writer statement | Shape lưu sau trigger |
|---|---|
| INSERT bỏ precision, `due_at=NULL` | `none/NULL/NULL` |
| INSERT bỏ precision, `due_at=<aware>` | `datetime/NULL/<aware>` |
| UPDATE date row `SET due_at=NULL` | `none/NULL/NULL` |
| UPDATE bất kỳ row `SET due_at=<aware>` | `datetime/NULL/<aware>` |
| UPDATE chỉ title/status, không SET `due_at` | schedule hiện tại giữ nguyên |

`downgrade` của expand migration **phải fail closed nếu đã có row `due_precision='date'`**, vì bỏ
`due_on` sẽ mất ngày hoặc buộc bịa timestamp. Empty-DB CI round-trip vẫn phải pass; PG test có một
date-only row phải thấy downgrade dừng đúng lý do và data/schema còn nguyên. Production rollback là
roll-forward theo repo policy; không downgrade Neon.

### 3.3 026C — chứng minh hết old binary rồi retire trigger

Branch/PR: `feat/026c-retire-legacy-due-writer`. Không gộp vào 026B.

Chỉ drop hai trigger/function legacy bằng migration next-head khi có đủ receipt trong **cùng cửa sổ
vận hành**:

1. inventory Fly cho thấy mọi machine phục vụ/standby đều chạy exact merge SHA của 026B; machine cũ
   đã stop/remove, không chỉ “healthy machine mới có mặt”;
2. `/api/readyz.commit` của mọi machine khớp SHA đó, `db=up`, và không còn deploy đang rolling;
3. chờ quá max request timeout + retry/backoff của server, rồi aggregate preflight vẫn `NULL=0`,
   invalid=0; không in row/title/due value;
4. synthetic old-writer probe trên throwaway PG xanh trước drop; sau drop cùng direct legacy INSERT
   phải đỏ `NOT NULL/CHECK`, còn **legacy HTTP payload qua server mới** vẫn xanh nhờ shim §4.

Nếu không chứng minh đủ bốn gate, giữ trigger và dừng 026C; không đoán từ một health check. Việc giữ
trigger tạm thời không cho phép bỏ API dual-write hay validator.

### 3.4 Migration receipts

- Preflight Neon chỉ in: revision, tổng row, count `none/date/datetime/NULL/invalid`; không in title,
  due value hay ID.
- Dùng throwaway Postgres/Docker cho `upgrade → downgrade → upgrade`, trigger matrix, drift và guard
  RED/GREEN.
- Neon: apply từng revision bằng `NEON_MIGRATOR_URL`, rồi query read-only
  `information_schema.columns`, `pg_constraint`, `pg_indexes` và aggregate shape counts.
- `alembic current` một mình không phải proof. Không chạy downgrade/round-trip trên Neon.

## 4. API contract và backward compatibility

### 4.1 DTO

Thêm type dùng chung `TaskDuePrecision = Literal["none","date","datetime"]`. Ở input DTO,
`TaskCreate.due_precision` / `TaskUpdate.due_precision` dùng `TaskDuePrecision | None = None` làm
sentinel **omitted** và validator đọc `model_fields_set`; caller gửi tường minh `null` thì `422`.
`due_on`/`due_at` cũng phải phân biệt omitted với explicit null cho PATCH. `TaskRead.due_precision` là
non-null và response luôn canonical. Validator/service ghép toàn payload **trước** khi mutate ORM;
không để CHECK DB biến lỗi người dùng thành `500`.

### 4.2 Create/PATCH matrix

| Request | Kết quả |
|---|---|
| không field lịch nào | legacy create → `none` |
| POST legacy có exact `"due_at":null` | `none`; giữ nguyên request bytes/hash, response canonical |
| chỉ `due_at=<aware>` | legacy → `datetime`, clear `due_on` |
| chỉ `due_at=null` trong PATCH | legacy → `none`, clear cả hai |
| `precision=date` + `due_on` | date-only |
| `precision=datetime` + aware `due_at` | datetime |
| `precision=none` | clear cả hai |
| `due_precision=null` tường minh | `422`; null không phải mode thứ tư |
| chỉ `due_on` không precision | `422` ambiguous |
| date thiếu `due_on`; datetime thiếu/naive `due_at`; hai field cùng non-null | `422` |
| non-temporal PATCH | giữ nguyên full schedule |

Compatibility shim cho `due_at`-only giữ ít nhất qua khi Task 017 đã rebase và mọi first-party caller
đã gửi shape mới. Không có deadline xoá shim trong 026; muốn xoá phải có task/telemetry riêng.

`POST {id,…,"due_at":null}` đã nằm trong outbox trước 026 là wire contract hợp lệ, không phải payload
thiếu cần “nâng cấp”. Flusher gửi **đúng canonical bytes cũ**; cấm chèn `due_precision`, xoá key null,
đổi UUID, hoặc tính lại `payload_sha256`/`payload_byte_length`. Server mới canonicalize vào DB thành
`none/NULL/NULL` và trả response ba field; adapter reconcile theo response nhưng row/outbox hash bất
biến. Command mới enqueue sau 026 dùng triad V2 và hash mới của chính bytes đó. Cùng UUIDv7 + exact
legacy bytes replay sau mất response vẫn `200`, một row, schedule không bị update/rewrite.

### 4.3 UUID/idempotency/private

- POST cùng UUIDv7 replay vẫn `200` + row cũ, không biến replay thành update và không thay precision.
- Hai replay liên tiếp của exact `{due_at:null}` phải giữ cùng UUID, body bytes, SHA-256 và byte length;
  đây là test fixture byte-for-byte, không chỉ so JSON object sau parse.
- Private task vẫn mã hoá prose như cũ; ba field lịch để plaintext theo quyết định K23. Không mở lại
  privacy model.
- Error schedule là `422` có code/detail máy đọc được ổn định; không parse microcopy ở client.

## 5. Timeline, cursor và frontend hiện hữu

### 5.1 Range/bucket

Với range `[from,to)` mà first-party caller gửi theo midnight của `Asia/Ho_Chi_Minh`:

- `dated`: `date` dùng `due_on ∈ [local_date(from), local_date(to))`; `datetime` dùng
  `due_at ∈ [from_instant,to_instant)`; `none` không thuộc.
- `undated`: chỉ precision `none`, không còn suy bằng `due_at IS NULL`.
- `overdue`: open + trước earliest block **và** đã overdue theo §2.4.
- `open_picker`: mọi open task; dùng nguyên tuple §2.4, không có comparator riêng.

Cursor payload ký phải bind range/status/bucket/private scope như 022 và mang **đúng tuple §2.4 theo
đúng thứ tự**: `pinned`, `scheduled_rank`, `schedule_day`, `precision_rank`, `due_at`, `created_at`,
`id`. Decode validate rank/null/precision combination; cursor `date` không được có `due_at`, cursor
`datetime` phải có aware `due_at` và day Việt Nam khớp, `none` phải có day/time NULL. Backend có một
sort-key builder dùng chung cho SQL `ORDER BY`, keyset-after, inverse/has-previous và cursor
encode/decode; frontend có đúng một `compareTaskScheduleKey` mirror tuple đó. Contract fixture JSON
dùng chung phải chứng minh Python/TypeScript cho cùng order; không copy comparator theo từng màn/bucket.
Cursor cũ `due_at`-only trả `422`, client restart range bằng
request đầu theo 022. `due_at`/`created_at` trong cursor dùng canonical UTC RFC3339 (`Z`), còn
`schedule_day` là ISO civil date Việt Nam; frontend không lấy device timezone để dựng key. Với dataset
không mutation, concat mọi page phải byte-for-byte cùng thứ tự với one-shot query và mỗi ID đúng một
lần; mutation đổi tuple invalidate/restart cursor, không tiếp tục trên snapshot đã đổi.

Không dựng ba poller. `TasksScreen` vẫn đúng một primary timeline observer 1 giây khi visible theo
Task 021/022; Calendar không interval. Mutation invalidate cả `['tasks']` và `['calendar']`, không
`await invalidateQueries` trong `onSuccess`.

### 5.2 Task form và quick-add

- Dùng `Select`/segmented control từ `@/components/ui/*` với ba label: **Ngày · Ngày + giờ · Chưa
  xếp lịch**. Không `<select>`/`<input>` thô.
- `date` render `Input type="date"`; `datetime` render ngày + `Input type="time"` hoặc một
  `datetime-local` có helper named-zone, nhưng giờ phải rỗng khi chưa chọn. Input chữ ≥16px trên iOS.
- Save disable với giải thích tại chỗ khi shape thiếu; keyboard/focus không bị reset khi đổi mode.
- Quick-add Task gửi date-only hôm nay; full dialog mở bằng CTA hiện có cho hai mode khác.
- Card/dialog/timeline dùng copy tách được ba mode; không render phút cho date-only.

### 5.3 Existing Calendar/reschedule integration

026 chỉ sửa **đường dời đang tồn tại** để bỏ heuristic; không thêm quick-add/drag/tick trong month
view (đó là 027). `endOfDayVietnam` bị xoá khỏi production code. Picker/quick-reschedule dùng helper
§2.6 và undo giữ full schedule.

## 6. Boundary với Task 017 — không giải outbox trong 026

Task 017 là source of truth cho queue, optimistic reconcile, private hold, Web Locks và UUIDv7.

- 026 **không** tạo Dexie table, `queuedMutation`, flusher hay adapter riêng; không sửa WIP/worktree
  017 của agent khác.
- 026 thay đổi các write surface đã có để gửi shape typed online. API shim §4.2 bảo đảm row outbox/cached
  client cũ chỉ có `due_at` vẫn replay được **mà không mutate/re-hash payload**.
- Khi 017 rebase sau 026, adapter `task.create`/`task.update` phải serialize full canonical schedule;
  optimistic apply/reconcile/undo không được suy `date` từ `23:59`.
- 026 acceptance **không** được gọi là offline/PWA pass. 027 không mở write surface mới cho tới khi
  017 merge (§027).

## 7. File scope dự kiến

Được chạm trong 026 implementation:

- `backend/alembic/versions/0010_*`, `0011_*`, migration retire-trigger next-head của 026C (revision
  number theo head sau rebase);
- `backend/app/domain/models.py`, `backend/app/domain/tasks.py`,
  `backend/app/web/routers/tasks.py`;
- task/calendar helpers và callers hiện hữu: `frontend/src/task-ui.ts`, `TaskForm.tsx`,
  `TasksScreen.tsx`, `calendar-scroll.ts`, `CalendarScrollView.tsx`, `DayDetailDialog.tsx` và type
  sát cạnh cần thiết;
- tests task/timeline/calendar tương ứng.

Không được làm:

- không redesign Daily Task UX, search/filter, AI parsing, cost feature;
- không thêm `23:59`, `00:00`, “end of day” instant cho date-only;
- không đoán legacy `23:59` là date-only;
- không thêm timezone setting hay dependency lịch mới;
- không viết outbox/Dexie/service-worker;
- không thay status/priority/private/soft-delete/idempotency contract;
- không đổi calendar source color hoặc month layout (027 sở hữu);
- không sửa shared `agent-tasks/README.md` trong lane này.

## 8. Acceptance — mọi guard phải biết đỏ

### 8.1 Backend/API/PG

1. DTO/API test đủ create + PATCH matrix §4.2; response luôn canonical; naive datetime `422`.
2. Migration PG thật seed ít nhất:
   - legacy NULL;
   - legacy timestamp thường;
   - legacy exact `23:59+07`;
   - private/completed/deleted rows.
   Sau expand: NULL → none, mọi non-NULL (kể cả 23:59) → datetime, zero date. Sau contract: zero
   invalid/null precision; exact constraints/indexes/triggers có mặt.
3. Old-writer PG matrix §3.2 chạy cả giữa 026A→app deploy và sau 026B. Thêm negative regression:
   unmarked update date row bằng `SET due_at=NULL` thành none; unmarked update chỉ title giữ date;
   marked canonical datetime→date giữ date; marked invalid shape đỏ CHECK. Kết thúc transaction V2,
   reuse cùng pooled connection cho unmarked legacy write và chứng minh marker không leak.
4. Deliberately insert từng invalid V2 shape sau contract ⇒ DB đỏ đúng `ck_task_due_shape`; hoàn
   nguyên rồi insert ba shape hợp lệ xanh. Trigger không được sửa hộ invalid explicit V2.
5. Downgrade guard với date-only row đỏ **trước khi drop**; empty throwaway DB round-trip xanh. 026C
   có RED/GREEN riêng: old direct writer xanh trước drop, đỏ sau drop, legacy HTTP shim vẫn xanh.
6. Range/cursor test >205 synthetic rows trộn pinned/unpinned, ba precision, nhiều row cùng
   day/time/created_at, boundary 00:00, private/deleted: concat pages bằng exact one-shot tuple §2.4,
   mọi visible ID đúng một lần. Chạy cùng assertion cho dated/overdue/undated/open_picker;
   rank/null mismatch, cursor mutation/scope mismatch đều `422`.
7. Overdue fake clock: date-only hôm nay chưa trễ lúc 23:59:59 local, trễ sau local midnight;
   datetime trễ đúng instant; none không trễ.
8. UUIDv7 create/replay exact legacy `{due_at:null}` vẫn một row/`200`; capture body bytes/hash/length
   trước hai dispatch và assert bất biến, response luôn canonical none. Fixture `{due_at:<aware>}` có
   cùng guarantee và canonical datetime.

### 8.2 Frontend unit/component

1. Mọi create surface mặc định date-only hôm nay; quick-add Enter gửi `due_precision=date` +
   `due_on=today`, không gửi timestamp.
2. Chuyển mode theo bảng §2.5; date→datetime giữ ngày nhưng giờ rỗng/Save disabled; datetime→date
   giữ Vietnam date và bỏ instant.
3. Render exact three modes; date-only DOM không có `00:00`/`23:59`; whitespace-only title vẫn bị
   từ chối theo QA framework.
4. Reschedule helper test cả ba mode + undo full shape. Timed `09:30` sang ngày khác vẫn `09:30`;
   date-only vẫn date; none thành date.
5. Browser test chạy context timezone UTC và `America/Los_Angeles`: cùng API fixture phải hiện cùng
   Vietnam date/time; date-only không dịch ngày.
6. Static guard production source:
   `rg -n "endOfDayVietnam|T23:59:00" frontend/src` ⇒ **0 match**. Test fixture legacy được phép có
   23:59 nếu assertion chứng minh nó vẫn là `datetime`.

### 8.3 Timeline/Calendar regression + performance

- Existing 022 paths (>191 reachability, seven-day groups, cursor, one primary poller) xanh sau typed
  grouping. Calendar date-window query vẫn bounded/no polling và không thêm request theo số ô.
- Mutation chuyển task qua old/new group ngay sau invalidate; private lock purge cả Task/Calendar
  cache như 022.
- Playwright mobile 390×844 + desktop 1280×800: create/edit/quick-add/reschedule/undo bằng keyboard
  và touch; no horizontal scroll; controls chính ≥44×44, input text ≥16px.
- Dữ liệu adversarial bắt buộc: 70 ký tự không space, tiếng Việt dấu dày, emoji, whitespace-only,
  ≥30 task trộn cả ba precision.

### 8.4 RED → GREEN bắt buộc

Sau khi suite xanh, perturbation không commit:

1. tạm map date-only reschedule về `23:59` **hoặc** đổi overdue date-only thành `due_on <= today`;
2. chạy test hẹp, thấy đỏ đúng semantic (không phải lint/type error);
3. restore source, chạy cùng lệnh xanh;
4. dán nguyên output RED/GREEN vào PR 026A. PR 026B làm RED/GREEN riêng cho trigger + DB CHECK/
   downgrade guard; PR 026C chứng minh trigger-retire RED/GREEN §8.1.

## 9. Lệnh/gate và báo cáo

Fresh worktree: `npm ci` trong `frontend` trước khi kết luận thiếu tool. Docker/Postgres local là
prerequisite cho PG/migration lane; nếu daemon tắt, báo connection/daemon unavailable, không đoán lỗi
code.

Tối thiểu chạy và dán raw output riêng từng lệnh:

```text
backend: uv run ruff check .
backend: uv run ruff format --check .
backend: uv run pytest -m "not pg"
backend: uv run pytest -m pg                  # 0 skip với throwaway Postgres
frontend: npm run lint
frontend: npm test
frontend: npm run build
frontend: npm run e2e
root: git diff --check
root: pre-commit run --all-files
```

Mỗi 026A/B/C là PR vào `develop`, giữ tên required checks, chờ `gh pr checks <PR> --watch` terminal.
Chỉ claim phase production khi inventory machine + `/api/readyz.commit` khớp exact merge SHA và
`db=up`; 026C còn cần gate retire §3.3. Đó chưa phải browser/iPhone acceptance. iPhone/Safari thật phải
verify default today, keyboard, date-only không hiện giờ và reschedule; chưa chạy thì ghi
**CHƯA VERIFY**, không suy từ Playwright.

Báo cáo cuối tách đúng bốn mục: **ĐÃ CHẠY** (raw output) · **CHƯA CHẠY** · **SUY LUẬN** ·
**MIGRATION/PRODUCTION RECEIPT**. Không dán task title, due value thật, account, token hay secret.
