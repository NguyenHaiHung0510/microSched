# 027 — Calendar month UX: ngày không lặp, thao tác task phổ quát, palette nguồn giới hạn

> **Executor: T2 (chọn exact route từ Runtime Catalog khi giao) · Bậc: L2 · Effort đề xuất:
> high · Skill gợi ý: Playwright cho browser QA · MCP cần: Chrome chỉ cho production QA đã được
> owner cho phép.**
> **Trạng thái: ✅ OWNER-APPROVED DECISION 2026-08-24 — SPEC SẴN REVIEW.**
> Task có ba phase/PR: structure read-only đi trước; mọi source/task write phụ thuộc cứng Task 017;
> xem §2. Không tự merge.

Đọc trước khi thi công: `CLAUDE.md` · `AGENTS.md` · `docs/frontend-brief.md` ·
`docs/ui-brief.md` toàn bộ, đặc biệt §4/§6/§8–9 · `docs/qa-framework.md` ·
`agent-tasks/010a-calendar-import-crud.md` · `agent-tasks/010b-calendar-scroll-view.md` ·
`agent-tasks/017-offline-outbox.md` · `agent-tasks/022-task-day-timeline.md` ·
`agent-tasks/026-task-temporal-precision.md` · code/test nêu ở §1.

## 0. Kết quả người dùng phải nhận được

1. Trong từng khối tháng, ngày ngoài tháng là **ô trống, inert**. Tháng 8 không in lại ngày cuối
   tháng 7/đầu tháng 9; các placeholder vẫn giữ đủ bảy cột và đúng hình học tuần.
2. Từ month view, người dùng luôn có đường **chạm/keyboard** để thêm task vào ngày, tick xong và dời
   ngày. iPhone không cần hover, chuột hay native drag-and-drop.
3. Laptop lớn có thể có lối tắt nhanh hơn (inline quick-add, tick ngay ô, optional drag), nhưng chỉ
   bật theo viewport + capability con trỏ; không UA sniffing.
4. Nguồn lịch có đúng **5** màu đẹp, có tên/swatch, tokenized và API/DB validate. Không mở custom
   hex/library. Slice này **không** thêm nền/ảnh/theme cho task hoặc note.

Daily task UX redesign, AI scheduling/cost và theme/image system nằm ngoài scope.

## 1. Sự thật hiện tại và supersession

### 1.1 Evidence trên `origin/develop=e2a24682…` ngày 2026-08-24

- **[QUAN SÁT]** `monthWeeks()` điền đủ date string của tuần, kể cả tháng kề
  (`frontend/src/calendar-scroll.ts:126-139`). `CalendarScrollView` render tất cả thành `DayCell` và
  chỉ đánh `isOtherMonth` (`frontend/src/CalendarScrollView.tsx:419-424`). `DayCell` vẫn in số ngày
  mờ (`frontend/src/DayCell.tsx:40-80`). Vì vậy cùng date có thể xuất hiện ở hai month blocks.
- **[QUAN SÁT]** Cả `DayCell` là một `Button` (`frontend/src/DayCell.tsx:40-46`). Thêm Checkbox/
  menu bên trong nguyên cấu trúc đó sẽ tạo nested interactive HTML sai.
- **[QUAN SÁT]** Responsive logic chỉ hỏi `(min-width: 640px)`
  (`frontend/src/CalendarScrollView.tsx:99-116`), chưa xét `hover`/`pointer` capability.
- **[QUAN SÁT]** Frontend khai 6 key `rose/amber/emerald/sky/violet/slate`
  (`frontend/src/calendar-ui.ts:36-48`), nhưng `sky` render cùng rose và unknown rơi slate
  (`frontend/src/calendar-scroll.ts:205-220`). Backend nhận `color: str | None` tới 32 ký tự
  (`backend/app/domain/calendar.py:43`, `:59`) và DB là `TEXT NULL` không CHECK
  (`backend/app/domain/models.py:256`). Palette hiện không được validate end-to-end.
- **[QUAN SÁT]** `DayDetailDialog` chỉ mở TaskForm để **sửa** task; danh sách task là Button mở editor
  (`frontend/src/DayDetailDialog.tsx:439-469`, `:565-579`). Chưa có create/tick task từ Calendar.
- **[QUAN SÁT]** 010b dời task bằng `23:59`; 026 sở hữu việc bỏ heuristic. 027 không được tái tạo nó.
- **[QUAN SÁT]** Task 017 khóa **mọi** domain write qua typed command + adapter registry
  (`agent-tasks/017-offline-outbox.md:155-168`, `:207-236`) và row giữ immutable payload hash/length
  (`:185-199`). Nhưng 017 chỉ gọi cửa đó theo khái niệm là `queuedMutation`; nó chưa khóa module path,
  exported symbol hay call signature, và `origin/develop` được quan sát chưa có file outbox/callable.
  Vì vậy 027 không được viết import tưởng tượng hoặc dựng seam thứ hai.
- **[QUAN SÁT]** `eventsByDay()` hiện chỉ lấy `startDay` + `endDay`
  (`frontend/src/calendar-scroll.ts:267-280`), nên event dài hơn hai ngày mất ngày giữa và event kết
  thúc đúng 00:00 còn bị tính vào ngày end. Backend range query đã đúng intersection nửa mở
  `starts_at < to AND ends_at > from` (`backend/app/domain/calendar.py:421-425`).
- **[SUY LUẬN]** Đổi outside-month date thành placeholder giảm DOM có nội dung/trùng action và làm
  navigation rõ hơn; vẫn phải đo scroll/mini-nav thật vì observer hiện neo vào week rows.
- **[KHÔNG BIẾT]** Spec lane chưa chạy browser/iPhone, chưa đo cảm giác scroll, bàn phím ảo hoặc
  palette trên màn hình thật. Các mục đó giữ là acceptance, không gọi PASS.

### 1.2 Phần cũ bị thay có chủ đích

| Nguồn | Phần bị supersede | Hợp đồng 027 |
|---|---|---|
| `010b` §1 (`:38-41`) | giữ tuần/date lặp giữa hai month blocks | §3: outside-month placeholder inert |
| `010b` §5.4 (`:406`) | in ngày tháng khác bằng chữ mờ | không in số/ngày/data attribute |
| `010b` §5.6 (`:471`) | dời về `23:59+07` | dùng full precision contract 026 |
| `010a` §5 (`:471-473`) | 6 màu + unknown/null fallback slate | §7: 5-key stored palette; null/slate chỉ là legacy wire alias |
| width-only `isDesktop` | desktop = `>=640` | §4: layout width và input capability là hai trục |

010b giữ nguyên các phần không xung đột: Monday-first, continuous month blocks, internal scroll,
IntersectionObserver, mini-nav 2 tháng, dialog là touch path, no calendar library, no polling.
Task 017 **không bị supersede**. Sau merge spec, integration owner cập nhật index/status board riêng;
PR 027 không sửa bảng trạng thái dùng chung.

## 2. Dependency/order — ba phase không được nhập nhằng

### 2.1 Phase 027A — structure/read-only

Branch/PR: `feat/027a-calendar-month-structure`.

Gate: 026B final API/schema shape đã merge (026C chỉ retire trigger, không đổi shape). **Không cần 017**
vì 027A không thêm/sửa bất kỳ mutation. Được làm:

- month placeholders/date uniqueness (§3);
- capability hook + component anatomy, nhưng chưa render task mutation controls (§4–5);
- half-open multi-day event projection (§3.3);
- read/render/a11y/performance tests tương ứng.

027A **không** đổi `SourceForm`, source DTO/DB color, không thêm direct transport và không gọi một
`queuedMutation` chưa tồn tại. Đây là fallback có thể merge độc lập khi 017 còn pending.

### 2.2 Phase 027B — source palette write contract

Branch/PR: `feat/027b-calendar-source-palette`.

Hard gate: Task 017 đã merge/rebase và §8.1 đã ghi được **actual** module path + exported callable +
registered `calendar.source.create/update` operation kinds từ code. Nếu chưa có, dừng 027B; không đổi
API/DB validation trước rồi để pending command cũ park. 027B làm toàn bộ §7 + compatibility acceptance
§12.2 trong một deploy sequence.

### 2.3 Phase 027C — task write UX

Branch/PR: `feat/027c-calendar-task-interactions`.

Hard gates, đủ cả hai:

1. 026B final contract + production migration receipt đã đóng; và
2. Task 017 đã merge, CI/deploy tương ứng xanh, §8.1 xác nhận actual callable + registered
   `task.create/update` trên exact base.

Nếu 017 chưa sẵn sàng: **dừng 027B/027C**. Không direct `apiRequest` tạm, không local queue mini, không
nút disabled “sắp có”, không copy code từ worktree 017. 027A có thể merge độc lập và month view tiếp
tục đọc/mở dialog như trước. Đây là phased fallback chính thức.

027C thêm universal quick-add/tick/reschedule trước; laptop inline/drag chỉ sau khi universal paths
xanh (§5–6). Native DnD optional — cắt nó trước khi cắt đường chạm.

## 3. Month matrix — date chỉ xuất hiện trong tháng của chính nó

### 3.1 Data shape

Đổi pure helper thành:

```text
WeekRow.days: Array<string | null>   // luôn đúng 7 phần tử, Monday-first
```

- Ngày thuộc target month là ISO `YYYY-MM-DD`.
- Slot trước ngày 1/sau ngày cuối là `null`.
- Giữ **số tuần tự nhiên hiện có** của tháng (4–6 rows), không ép mọi tháng thành 6 rows và không đổi
  continuous-scroll geometry ngoài nội dung ô.
- Key week vẫn `(year,month,week_index)` để IntersectionObserver/mini-nav không đổi identity.
- Real day dùng ISO date làm React key. Placeholder dùng key ổn định
  `placeholder:${week.key}:${columnIndex}`; cấm dùng `null`, array index đơn lẻ hoặc random UUID làm key.
- `visibleDayKeys`, `scrollToDay`, grouping/chip count phải bỏ `null`, không stringify thành
  `"null"`/`undefined`.

Ví dụ February 2026, Monday-first:

```text
[null, null, null, null, null, null, "2026-02-01"]
...
["2026-02-23", ..., "2026-02-28", null]
```

### 3.2 DOM/behavior placeholder

Placeholder:

- có `data-testid="calendar-day-placeholder"` để test, **không** có `data-day`;
- `aria-hidden="true"`, không role/button/tabindex/tooltip/focus ring;
- không events/tasks/annotations/count, không click/long-press/drop target;
- dùng cùng grid slot/min-size/border spacing để cột/hàng không co.

Real day trong một set month blocks có `data-day` đúng **một lần**. Event qua midnight/month vẫn được
dedupe theo event ID và hiển thị trên từng **ngày thật** nó chạm, nhưng không vẽ trong placeholder.
Mini-nav cũng dùng placeholder cho outside-month slot.

Navigation “Hôm nay”, mini-nav và scroll-to-date chọn cell ở month block sở hữu date đó. Không còn
lý do chọn duplicate DOM row.

### 3.3 Event projection là interval nửa mở

Mỗi event là instant interval `[starts_at, ends_at)`. Project event vào đúng những civil day Việt Nam
`d` mà interval ngày `[d@00:00, (d+1)@00:00)` thỏa
`event.starts_at < day_end AND event.ends_at > day_start`:

- lặp từ Vietnam day của `starts_at` qua mọi ngày giao nhau, không chỉ set `{startDay,endDay}`;
- nếu `ends_at` đúng local midnight, **không** tính ngày bắt đầu tại instant đó;
- dedupe input theo event ID trước, rồi mỗi `(day,event.id)` chỉ được insert một lần; response overlap
  hoặc duplicate ID không nhân chip/count;
- chỉ project vào real day owner cell; placeholder không bao giờ nhận event.

Contract này áp dụng như nhau cho timed/all-day/manual/ICS event; không đổi parser hay event schema.

## 4. Responsive theo hai trục: kích thước × capability

Không dùng `navigator.userAgent`, platform string, iPhone regex hoặc “mobile/desktop” làm một boolean
bao trọn.

| Mode | Điều kiện | Affordance |
|---|---|---|
| **Universal compact** | mọi viewport/capability | mở day dialog, create/tick/reschedule đầy đủ |
| **Roomier layout** | `min-width: 640px` | 3 chip/mini-nav như 010b, chưa suy ra có hover |
| **Laptop enhanced** | `min-width: 1024px` **và** primary `(hover:hover) and (pointer:fine)` | inline quick-add/tick; optional drag handle |

Dùng một hook `useCalendarCapabilities()` dựa `matchMedia`, subscribe `change` và cleanup. Helper
subscription phải hỗ trợ cả API hiện đại `addEventListener('change', handler)` /
`removeEventListener(...)` và fallback Safari cũ `addListener(handler)` / `removeListener(handler)`;
cleanup dùng đúng nhánh đã đăng ký, đúng một lần. Width/capability đổi phải cập nhật không reload. CSS
media query tương ứng chỉ điều khiển presentation; JS capability quyết định behavior như `draggable`.

Touch/coarse ở màn 1280px vẫn phải dùng universal path và **không** bị ép native DnD. Fine pointer ở
768px vẫn có layout roomier nhưng không nhồi laptop controls vào ô hẹp. Hybrid có primary coarse nhưng
`any-pointer:fine` vì gắn mouse vẫn là universal-only; không dùng `any-*` để mở behavior drag.

## 5. Cấu trúc DayCell và đường thao tác phổ quát

### 5.1 Không nested interactive

Refactor root `DayCell` từ `Button` thành container không tương tác. Anatomy bắt buộc:

```text
DayCell root (div/article; layout only)
├─ Button mở ngày, phủ vùng nền/cell (sibling, không bọc controls)
├─ visual chips/annotation layer
└─ task controls layer (chỉ laptop enhanced; sibling của Button)
```

Background/open-day Button và task Checkbox/menu **không** là ancestor/descendant của nhau. Controls
ở layer trên có hit area riêng; click/touch không vô tình mở dialog ngày. Placeholder dùng component
riêng/branch không render Button.

Real-day open Button có accessible name gồm full date + tổng buổi/task; focus ring ≥3:1. Vùng mở ngày
≥44×44 ở 390px. Không thêm `role=button` lên root song song với Button thật.

### 5.2 Universal day dialog — bắt buộc trước mọi shortcut

Trên **mọi** device, `DayDetailDialog` có:

1. **“Thêm việc”** → `TaskForm` tạo mới với `due_precision=date`, `due_on=selectedDay`, client UUIDv7
   sinh **trước enqueue**. Đây là path chính cho iPhone.
2. Mỗi task có Checkbox **“Đánh dấu <title> hoàn thành/mở lại”**; PATCH absolute `status`, không toggle
   mù. Checkbox/action target ≥44×44 hoặc cả row label đạt cùng vùng.
3. Mỗi task có **“Dời việc”** → date picker/quick choices; dùng contract 026:
   datetime giữ giờ, date giữ date-only, none→date. Undo giữ full schedule cũ.
4. Chạm title/edit vẫn mở TaskForm; focus trả đúng trigger khi đóng.

Không có thông tin/hành động chỉ nằm trong tooltip/hover. Dialog list không bọc cả row bằng Button rồi
nhét Checkbox vào; dùng row container + sibling controls.

### 5.3 Quick-add trên laptop

Sau universal path xanh, laptop enhanced được thêm Button `+` ở real day. Nó có thể mở inline form
hoặc shadcn `Popover`, nhưng:

- **không dùng Tooltip làm form**; tooltip chỉ mô tả icon. Interactive content cần focus management,
  Escape/click-outside và portal ra `body` vì app có `overflow-hidden`;
- dùng `Input`/`Button` từ `@/components/ui/*`, Enter lưu, Escape huỷ, lưu xong clear + giữ focus;
- title-only create mặc định date-only của cell; muốn giờ/unscheduled mở full form;
- trigger vẫn keyboard reachable/focus-visible. Có thể visually reveal bằng hover/focus-within vì
  universal dialog đã chứa cùng action, nhưng hover không phải đường duy nhất.

### 5.4 Tick ngay ô tháng trên laptop

Laptop enhanced có thể hiện Checkbox cho task chip đang nằm trong giới hạn chip. Nó là sibling của
open-day Button (§5.1), có accessible name và non-text contrast. Với ô chật/overflow, không thu nhỏ
dưới 24px; cắt shortcut và giữ dialog path thay vì phá target.

## 6. Reschedule và optional desktop drag

### 6.1 Universal reschedule là Definition of Done

Dialog/date picker ở §5.2 phải pass trên 390×844 bằng `tap`, không hover/drag. Task screen quick choices
và Calendar đều gọi cùng typed helper 026; toast/undo đi qua Task 017 adapter.

### 6.2 Native drag là bonus có điều kiện

Chỉ cân nhắc sau universal create/tick/reschedule xanh. Nếu làm:

- chỉ render handle/`draggable=true` ở laptop enhanced §4; event/source chips không draggable;
- drop target chỉ real day, placeholder từ chối;
- date-only giữ date-only; datetime giữ clock; none không xuất hiện trên grid nhưng nếu được kéo từ
  picker tương lai thì thành date-only;
- drop enqueue đúng một absolute `task.update` qua Task 017, optimistic move một chip, success
  reconcile, failure badge/toast theo 017; không direct fetch;
- keyboard/touch vẫn dùng “Dời việc”; không cố giả native DnD trên iOS Pointer Events trong 027.

Nếu native DnD không ổn định hoặc làm core generic outbox phình, **bỏ bonus**. 027 vẫn DONE khi mọi
universal path và laptop inline non-drag đạt; PR body ghi rõ DnD **SKIPPED**, không gọi nó pass.

## 7. Calendar source colors — đúng 5 lựa chọn, typed end-to-end

### 7.1 Palette chốt

Chỉ `calendar_source.color` dùng palette này. Key lưu DB không đổi theo ngôn ngữ UI:

| Key | Label UI | Background token/value | Foreground token/value | Contrast chữ |
|---|---|---|---|---:|
| `rose` | Hồng ấm | `--calendar-source-rose-bg: #fde4ea` | `--calendar-source-rose-fg: #8f3050` | 6.45:1 |
| `amber` | Hổ phách | `--calendar-source-amber-bg: #fdf1de` | `--calendar-source-amber-fg: #7a4b0a` | 6.63:1 |
| `emerald` | Xanh lá | `--calendar-source-emerald-bg: #e6f4ee` | `--calendar-source-emerald-fg: #21674a` | 5.97:1 |
| `sky` | Xanh trời | `--calendar-source-sky-bg: #e7f2f7` | `--calendar-source-sky-fg: #285e75` | 6.26:1 |
| `violet` | Tím dịu | `--calendar-source-violet-bg: #f1eaf7` | `--calendar-source-violet-fg: #62487d` | 6.51:1 |

**[QUAN SÁT]** Các tỷ lệ trên được tính sRGB cho chính cặp đề xuất trong spec lane ngày 2026-08-24;
implementation phải re-run bằng test/tool độc lập trên CSS computed values. Foreground so với trắng
cũng đều >6.7:1, đủ làm swatch/border non-text. Hex chỉ nằm trong `index.css` token registry, không
trong component.

`SourceForm` hiện swatch + label tiếng Việt + check/selected text; không bắt người dùng đọc key Anh,
không phân biệt chỉ bằng màu. Chip dùng background/foreground pair; detail dialog vẫn hiện source name,
nên màu chỉ là tín hiệu bổ sung.

### 7.2 API/DB/migration + immutable queued payload

`CalendarSourceColor = Literal["rose","amber","emerald","sky","violet"]` là type **storage/read**;
`SourceRead.color` luôn một trong năm key. Write DTO có compatibility type riêng chỉ để không phá
command đã enqueue trước palette:

| Wire input | Canonical DB/response |
|---|---|
| create bỏ `color` | `rose` |
| update bỏ `color` | giữ màu hiện tại |
| một trong 5 key | giữ nguyên |
| explicit `null` hoặc legacy `slate` | `rose` |
| blank, hex, key khác, sai type | `422` |

First-party UI/command mới chỉ được gửi năm key, không expose null/slate. Compatibility alias không có
deadline xoá cho tới khi Task 017 có versioned-command migration riêng. Với outbox row cũ, flusher gửi
nguyên body bytes `null/slate` và giữ `payload_sha256`/`payload_byte_length`; cấm rewrite/re-hash row.
Adapter có thể **render optimistic** alias đó bằng tone rose và reconcile response rose, nhưng không
mutate persisted command. Unknown key vẫn park theo validation contract 017, không map âm thầm.

027B deploy theo thứ tự: (1) code API compatibility + actual 017 source adapters; code tạm dual-read
DB null/slate thành response rose và mọi write mới lưu năm key; (2) receipt mọi Fly machine chạy exact
SHA mới, không còn rolling/old binary; (3) migration next-head (tên dự kiến
`0012_calendar_source_color_palette.py`, revision phải re-query). Không đặt CHECK trong lúc old server
còn có thể ghi null/slate trực tiếp.

Migration:

1. preflight `SELECT color,count(*) GROUP BY color` chỉ in key/count;
2. nếu có key ngoài `{NULL,slate,rose,amber,emerald,sky,violet}` ⇒ **fail closed**, không âm thầm đổi;
3. map `NULL` và legacy `slate` → `rose`; năm key còn lại giữ nguyên;
4. set `color NOT NULL DEFAULT 'rose'`;
5. add canonical CHECK `ck_calendar_source_color_values` đúng năm key;
6. model/migration drift rỗng. Downgrade bỏ CHECK/default/NOT NULL nhưng không cố đổi `rose` về
   `slate` (không có provenance).

`day_annotation.color` không thuộc migration/palette product này. Bắt buộc tách constant/helper
source-specific (`CALENDAR_SOURCE_COLORS` / `calendarSourceTone`) khỏi `AnnotationForm` và
annotation renderer; **không** thay generic list đang nuôi annotation bằng list source rồi vô tình
xoá lựa chọn cũ. Annotation tiếp tục đọc/sửa được legacy `slate/null` theo contract hiện tại cho tới
một quyết định riêng. Không thêm color UI cho task/note và không migrate annotation trong 027.

## 8. Task 017 integration — dependency phải có receipt thật

### 8.1 Public-callable gate, không đặt tên export tưởng tượng

Spec 017 chỉ khóa adapter methods, chưa khóa JS export. Vì vậy 027 **không** tuyên bố có sẵn một hàm
`queuedMutation`. Trước dòng implementation đầu tiên của 027B/027C, executor phải rebase exact merged
017 và ghi vào PR body bốn receipt lấy từ code:

```text
OUTBOX_PUBLIC_MODULE=<actual tracked path>
OUTBOX_PUBLIC_EXPORT=<actual exported symbol>
OUTBOX_CALL_SIGNATURE=<actual TypeScript signature>
OUTBOX_REGISTRY=<actual tracked path + registered operation kinds>
```

Typecheck phải chứng minh source/task call sites gọi chính symbol đó. Callable thật phải đi qua static
adapter contract đã khóa ở 017 — `encodeCommand`, `optimisticApply`, `reconcileSuccess`,
`discardOrRollback`, `affectedQueryKeys` — và persist canonical bytes/hash **trước** optimistic apply.
027 không được thêm facade/public export vào generic outbox core. Nếu merged 017 không expose callable
hoặc chưa register kind cần thiết, đó là blocker/follow-up thuộc 017; dừng phase write.

### 8.2 Exact operation contracts 027 được phép dùng

| Phase/action | Required registered `operation_kind` | Typed input/bất biến |
|---|---|---|
| 027B source create | `calendar.source.create` | client UUIDv7 trước enqueue; body color theo §7.2 |
| 027B source update | `calendar.source.update` | entity ID + absolute patch; legacy body bất biến |
| 027C create từ ngày | `task.create` | UUIDv7 + canonical triad 026 trước enqueue; retry một row |
| 027C tick/reopen | `task.update` | entity ID + absolute status; không toggle mù |
| 027C reschedule/undo | `task.update` | entity ID + full schedule triad 026; undo cũng absolute |

UI truyền typed domain input, không truyền method/path/body generic và không parse URL để chọn adapter.
Optimistic overlay cập nhật cả `['tasks', ...]` và `['calendar', ...]`; source adapter cập nhật source
map tương ứng. Reconnect coordinator flush trước refetch như 017. Offline create hiện pending công khai;
private pending không leak khi gate locked. Failed row giữ badge/discard contract 017, không giả đã sync.

027 không sửa Dexie schema, classifier, Web Locks, private purge, query persistence hoặc generic core.
Static guard trên component 027B/027C phải chặn mutation `apiRequest`/`fetch`; read GET vẫn được phép.

## 9. Query/cache/performance

- Không query theo cell. Reuse một source map, month event queries, annotation range và Calendar task
  date-window/cursor đã có. Mở move picker mới được lazy load open tasks như 022.
- Placeholder không fetch date ngoài tháng chỉ để lấp ô. Month event fetch range giữ nửa mở hiện tại;
  projection dùng intersection §3.3, dedupe event ID trước group và `(day,event.id)` trước count.
- Mọi Calendar query giữ `refetchInterval:false`/`NO_POLLING_QUERY_OPTIONS`; Task primary polling 1s
  không nhân theo month/cell/dialog.
- Mutations invalidate family một lần; không `await invalidateQueries` trong `onSuccess`.
- Capability hook tạo đúng một listener/query mỗi media expression, cleanup đúng modern/legacy branch
  khi unmount; không `resize` loop/setInterval.
- ±6 tháng ban đầu vẫn bounded. Sau placeholder, số request không tăng so với base; 31/42 cells hoặc
  30+ task không sinh N+1.

## 10. Accessibility/mobile/laptop

- 390×844: no horizontal scroll; real-day open target và universal action ≥44×44; input ≥16px; gap
  giữa targets ≥8px; keyboard ảo không che quick-add cuối dialog.
- Placeholder: 0 focus/announcement/action. Real dates có heading/accessible full date.
- DOM có **0 nested interactive**: test ít nhất `button button`, `button input`, `button [role=button]`,
  `a button`, `label button` theo component anatomy thực tế.
- Checkbox label = động từ + task; source chooser không color-only; focus ring/non-text ≥3:1; text
  chip ≥4.5:1 và ≥12px.
- Tooltip/popover portaled; trigger cuối màn không bị cắt. Escape đóng đúng lớp, focus trả trigger.
- Laptop 1280×800 primary fine+hover: shortcuts tồn tại; keyboard làm được cùng action. Primary coarse
  1280 (kể cả `any-pointer:fine` do gắn mouse) và mobile 390: enhanced shortcuts/drag ẩn nhưng universal
  paths đủ.
- Dữ liệu QA dùng synthetic/adversarial; không chụp/dán task, source name, email thật vào artifact.

## 11. File scope dự kiến

027A được chạm:

- calendar grid/read helpers: `CalendarScrollView.tsx`, `DayCell.tsx`, `MiniNav.tsx`,
  `calendar-scroll.ts`, capability helper sát cạnh và layout token cần thiết trong `index.css`;
- tests sát các file trên.

027B được chạm:

- source palette UI/helpers: `calendar-ui.ts`, `SourceForm.tsx`, `index.css`;
- `backend/app/domain/models.py`, `backend/app/domain/calendar.py`, migration next-head;
- **actual** calendar-source adapter extension point đã chứng minh ở §8.1, không generic core;
- unit/API/PG/outbox compatibility tests sát các file trên.

027C được chạm:

- `DayDetailDialog.tsx`, `DayCell.tsx`, TaskForm/helper imports cần thiết;
- **actual** task adapter extension point đã chứng minh ở §8.1, không sửa generic core;
- unit/component/e2e/PWA tests.

Không được làm:

- không sửa ICS parser/import semantics, calendar event schema, day_annotation schema/privacy;
- không calendar library, DnD dependency, virtualization, UA detection;
- không interactive Tooltip; không nested Button/Checkbox/menu;
- không task/note wallpaper, background image, custom theme/dark mode, unbounded color picker;
- không Daily Task redesign, AI/cost/search;
- không direct mutation/new outbox khi 017 chưa merge;
- không sửa shared `agent-tasks/README.md` trong lane này.

## 12. Acceptance/QA matrix

### 12.1 Structure/read-only — 027A

1. February 2026 Monday-first có 5 rows × 7; first row 6 null + `2026-02-01`, last row
   `2026-02-23..28` + null. Leap February 2028 và month bắt đầu Monday/Sunday đều exact.
2. Render 13 adjacent month blocks: mọi `data-day` unique; placeholder count đúng; placeholder không
   có date/chip/control. Mọi key `placeholder:${week.key}:${columnIndex}` unique/stable qua rerender;
   pure key-set guard đỏ nếu bỏ `week.key`; spy `console.error` không có React duplicate-key warning
   ở render thật.
3. `visibleDayKeys`/scroll/mini-nav lọc null; Hôm nay/target date scroll đúng owning month.
4. Event fixture `2026-08-30T22:00+07:00 → 2026-09-02T09:00+07:00` xuất hiện đúng một lần/count trên
   30/08, 31/08, 01/09, 02/09 và zero placeholder. Fixture kết thúc `02/09T00:00+07:00` chỉ có
   30/08, 31/08, 01/09. Duplicate cùng event ID trong input vẫn đúng một chip mỗi real day.
5. Component DOM test 0 nested interactive; placeholder inert; full-date accessible name.
6. Capability unit: width-only không đủ; 1280 primary coarse + `any-pointer:fine` ⇒ universal only;
   768 primary fine ⇒ no laptop enhanced; 1280 primary fine ⇒ enhanced. Media change cập nhật. Chạy
   hai stub: modern chỉ có `add/removeEventListener`, legacy Safari chỉ có `add/removeListener`; mỗi
   nhánh register/cleanup đúng một lần, không gọi method không tồn tại.

### 12.2 Source palette/outbox compatibility — 027B

1. Exactly five selectable keys/labels; null/slate không selectable; computed text contrast từng pair
   ≥4.5, swatch/focus ≥3; component source không chứa color hex.
2. API create/update: năm key pass; omitted create/null/slate trả canonical rose; blank/hex/unknown
   `422`. `SourceRead` không bao giờ trả null/slate.
3. Migration map chỉ null/slate, fail-closed unknown; DB direct invalid insert đỏ đúng CHECK; receipt
   mọi app machine exact new SHA trước apply constraint.
4. Seed outbox command legacy source create/update với exact body bytes có `null` và `slate`; capture
   SHA/length trước/sau dispatch, assert bất biến; optimistic tone rose, server response rose, một
   entity sau retry. Unknown body bất biến nhưng park validation, không rewrite.
5. PR body có đủ bốn `OUTBOX_*` receipt §8.1; TypeScript compile chứng minh call sites dùng actual
   export + registered `calendar.source.create/update`. Static guard không có component mutation
   `apiRequest`/`fetch`.

### 12.3 Universal task paths — 027C

| Case | Mobile touch 390×844 | Desktop keyboard 1280×800 | Offline/PWA sau 017 |
|---|---|---|---|
| create date task | dialog → Thêm việc → chip | cùng path + inline shortcut | optimistic pending → one server row |
| tick/open lại | dialog Checkbox | dialog + inline checkbox | absolute command/coalesce |
| date-only reschedule | giữ precision date | giữ precision date | replay/undo full shape |
| timed reschedule | giữ exact Vietnam clock | giữ exact clock | replay/undo full shape |
| failed validation | visible error, data giữ | visible error + focus | parked/badge theo 017 |

Test quick-add Enter clear + giữ focus; UUID replay một row; private lock không leak; mutation đổi chip
old/new day ngay. Universal flows dùng `tap`/keyboard, **0 hover/drag**.

Nếu DnD được làm, thêm desktop test drag real day→real day cho date/datetime, drop placeholder không
dispatch, coarse/mobile không có draggable. Thiếu DnD phải report **SKIPPED (optional)**, không giả pass.

### 12.4 Browser visual/state/performance

Playwright production-build mock lane, ít nhất:

- projects: `mobile 390×844 hasTouch`, `desktop 1280×800 fine`, và một coarse/hybrid capability mock;
- empty/loading/error/sending/send-error/offline/30+ items/private/completed;
- leading/trailing placeholders nhìn trống nhưng grid không sập; screenshots adjacent months ở mobile
  + desktop; taste report riêng, không tự đổi palette;
- long no-space/Vietnamese dấu dày/emoji/whitespace-only; chip không đẩy controls ra ngoài;
- exact network count: render thêm cells/placeholder không tăng source/task requests; no interval sau
  fake timers; 027B/027C offline lane chờ SW ready+controller và ngắt network thật theo 017.

Physical iPhone/Safari production: chạm real day, thêm/tick/dời, keyboard/safe-area, scroll inertia,
popover không cắt, source chooser phân biệt được. Chưa chạy thì **CHƯA VERIFY**, Playwright không thay
biên lai thiết bị.

### 12.5 RED → GREEN bắt buộc

027A:

1. tạm trả outside-month date thay `null` → unique-date test đỏ; restore → xanh;
2. tạm project event chỉ vào start/end → fixture 4-day đỏ; restore → xanh;
3. tạm bỏ `week.key` khỏi placeholder key → pure duplicate-key guard đỏ; restore → xanh.

027B:

1. tạm đổi một source foreground thành token yếu dưới 4.5 → contrast test đỏ; restore → xanh;
2. tạm rewrite body legacy null→rose trước flush → immutable hash/body test đỏ; restore → xanh;
3. tạm bypass actual registered source mutation bằng direct transport → static guard đỏ; restore → xanh.

027C:

1. tạm reschedule date-only thành datetime/end-of-day → precision test đỏ; restore → xanh;
2. tạm bypass actual registered task mutation bằng direct transport trong test guard → guard đỏ;
   restore → xanh.

Dán nguyên output; RED phải đỏ đúng invariant, không do syntax/lint.

## 13. Lệnh/gate và báo cáo

Fresh worktree: `npm ci` trong `frontend`. Docker/Postgres local phải được bật cho palette migration PG
lane; không chạy downgrade Neon.

Tối thiểu, raw output tách từng lệnh:

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

Mỗi phase là PR nhỏ riêng vào `develop`, review exact head và `gh pr checks <PR> --watch` terminal;
không auto-merge. Palette migration apply/verify theo rule thủ công, query exact columns/constraint/
aggregate keys. Production proof = readyz exact merge SHA + DB up; browser/iPhone acceptance là receipt
riêng.

Báo cáo cuối tách: **ĐÃ CHẠY** · **CHƯA CHẠY** · **SKIPPED OPTIONAL (DnD nếu có)** · **SUY LUẬN** ·
**MIGRATION/CI/PRODUCTION**. Không dán dữ liệu cá nhân/secret. Integration owner thêm rows 026/027 vào
`agent-tasks/README.md` sau khi các spec PR không còn tranh chấp; executor 027 không sửa bảng đó.
