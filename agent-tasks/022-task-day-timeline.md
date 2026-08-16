# 022 — Task day timeline: xem được toàn bộ lịch sử, không phân trang bằng số

> **Executor: T2 (chọn route từ Runtime Catalog khi giao) · Bậc: L1 · Effort đề xuất: high ·
> Skill gợi ý: Playwright cho local browser QA · MCP cần: Chrome chỉ cho production QA đã được phép.**
> **Trạng thái: ✅ OWNER-APPROVED DECISION 2026-08-16 — implementation PENDING.**
> Đây là prerequisite UX/API cho cutover Task 012; **không** tự nâng Task 012 từ DRAFT thành approved
> và **không** chạy cutover dữ liệu thật trong task này.

Đọc trước khi thi công: `CLAUDE.md` · `AGENTS.md` · `docs/frontend-brief.md` ·
`docs/ui-brief.md` §4, §6, §8–9 · `docs/qa-framework.md` · `docs/forward-spec.md` §C ·
`agent-tasks/012-cutover-migration.md` · `agent-tasks/019-tasks-visual-polish.md` ·
`agent-tasks/021-balanced-query-polling.md` · code/task tests nêu ở §1.

## 0. Quyết định chủ đã chốt

Màn **Task** không còn là một list phẳng bị cắt ở 100 hàng hoặc một UI phân trang. Người dùng nhìn
thấy công việc theo **ngày rõ ràng như timeline**, nên biết việc thuộc ngày nào và luôn có đường tới
mọi task đã cutover — kể cả khi dữ liệu thực vượt 191 task.

Khi lần đầu mở màn Task, timeline có đúng các date group từ **hôm nay −3** đến **hôm nay +3** (bảy
ngày lịch liên tục, bao gồm hôm nay). Ngoài các date group đó:

- task `open` có hạn trước block ngày đang thấy nằm trong nhóm **“Quá hạn trước đó”**;
- task `open` có `due_at = null` nằm trong nhóm **“Chưa xếp ngày”**;
- task `pinned` chỉ đứng đầu **ngày/nhóm của chính nó**, không được nhảy qua toàn bộ timeline;
- task `completed` thuộc date group của `due_at`; mặc định được gấp trong từng ngày bằng control có
  thể chạm/keyboard, nhưng luôn xem lại được; và
- CTA **“Xem thêm ngày trước”** / **“Xem thêm ngày sau”** mở đúng một block liền kề 7 ngày. Không có
  page number, “trang 2”, “1–100”, hay control tương đương giả dạng pagination. Có đường
  **“Xem toàn bộ lịch sử”** để tiếp tục duyệt các block cũ bằng loading theo nhu cầu, không tải toàn
  bộ lịch sử vào một request.

Đây là direction product đã khóa. Executor được quyết L2 như tên component, chuỗi testid và shape
opaque cursor, nhưng không được đổi các hành vi trên thành list phẳng/limit lớn hơn.

## 1. Sự thật code hiện tại và conflict phải xử lý

### 1.1 OBSERVED trên base `d345c0e` (sau Task 021)

- `frontend/src/TasksScreen.tsx` có **một** query Task: `GET /api/tasks?status=all&limit=100&offset=0`.
  Filter hiện tại `open` / `completed` / `all` / `overdue` chỉ lọc client-side trên 100 hàng đó.
- `backend/app/web/routers/tasks.py` đặt `limit` tối đa 100. `TaskStore.list()` ở
  `backend/app/domain/tasks.py` cũng mặc định 100 và sort toàn cục `pinned DESC, due_at ASC,
  created_at DESC`.
- Schema chỉ có `open` / `completed`; `deleted_at` là soft-delete và API không expose trạng thái
  `archived`. Index Task hiện có là đơn `ix_task_due_at`.
- Calendar cũng gọi endpoint Task theo `limit=100&offset`, tối đa 5 page. Không được làm vỡ lịch
  khi thay task-list contract.
- Task 021 đã khóa `taskRefetchInterval` 1 giây, dừng khi error/hidden; default query không poll.
  Mọi query mới trong 022 phải giữ đúng policy này, không khôi phục global 1 giây.
- Task 012 §2 đo **191** task tại 2026-08-01, nhưng đó là snapshot cũ; chính 012 yêu cầu không
  hardcode count. Vì vậy UI/cutover hiện tại mâu thuẫn: dữ liệu có thể vượt 100 trong khi màn Task
  chỉ fetch 100.

### 1.2 Boundary với Task 012 và archived

Task 012 vẫn ghi **DRAFT** dù migration 0009/Task 020 đã live. 022 chỉ bảo đảm app có thể xem dữ liệu
Task đầy đủ trước khi cutover; mọi gate dữ liệu, giá, backup và owner ceremony của 012 giữ nguyên.

`archived` không phải trạng thái Task hiện tại (`CHECK status IN ('open', 'completed')`) và 012 đang
chủ ý đếm/bỏ source `archived`. 022 **không** thêm status, tab, filter hay API archived. Hàng
`deleted_at IS NOT NULL` vẫn không đọc được như trước. Nếu một API consumer gửi/đòi archived, trả
validation error hiện có; đừng âm thầm biến nó thành “lịch sử”.

## 2. Hợp đồng timeline — hành vi người dùng

### 2.1 Mốc ngày và timezone

- Mọi quyết định “hôm nay”, group ngày và range API dùng `Asia/Ho_Chi_Minh` / UTC+07, không dùng
  timezone của thiết bị, UTC date string, hay locale browser. Reuse helper Vietnam hiện có ở frontend;
  backend phải cùng semantic bằng timezone có tên.
- Lấy `today` đúng một lần khi dựng/refetch wave. Range mặc định là `[today-3, today+4)` theo ngày
  lịch; `from` inclusive 00:00+07, `to` exclusive 00:00+07. Một `due_at` đúng `00:00+07` vào group
  ngày mới; một `due_at` sát trước boundary ở group ngày trước.
- Khi app vượt midnight +07 trong lúc đang mở, refetch/focus kế tiếp phải phát hiện date key mới,
  dựng lại seven-day default/mở rộng hiện có không duplicate. Không chờ người dùng reload để task
  đổi nhóm ngày.
- “Quá hạn” trong một date group là `status=open` và `due_at < now` như hành vi hiện tại. Nhóm
  **“Quá hạn trước đó”** hẹp hơn: chỉ open task có Vietnam date **trước earliest date block đang
  hiển thị**. Vì vậy task trễ hạn hôm qua vẫn ở group “Hôm qua” khi block mặc định chứa hôm qua;
  mở thêm 7 ngày trước sẽ chuyển nó từ nhóm quá hạn cũ sang đúng group ngày, không được nhân đôi.

### 2.2 Group, thứ tự và collapse

1. Date group render theo ngày tăng dần trong vùng đang xem; header đọc được bằng tiếng Việt và có
   semantic heading/date. Task có `due_at` chỉ xuất hiện một lần trong group Vietnam date của nó.
2. Trong **mỗi** date group: `pinned` trước không-pinned; tiếp theo `due_at ASC`, rồi
   `created_at DESC, id` làm tie-break deterministic. Pinned không được thoát khỏi status filter,
   private gate hay group ngày.
3. “Quá hạn trước đó” đứng trước date block sớm nhất; bên trong dùng cùng sort pinned → due → created.
   “Chưa xếp ngày” ở sau date blocks; open rows trong đó sort pinned → `created_at DESC, id`.
4. Date group hiển thị open rows. Nếu có completed rows phù hợp với status/all, header có control
   ví dụ “Đã xong (N)”; default **collapsed** để timeline không bị lịch sử completed nuốt màn. Control
   là `Button`/primitive phù hợp, có text + `aria-expanded` + vùng được liên kết; không dùng hover.
   Bấm/chạm/Enter/Space mở và đóng rows completed của **đúng ngày đó**. Không có completed task nào
   bị ẩn vĩnh viễn chỉ vì collapsed.
5. Khi status filter là `open`, không render completed rows/count. Khi là `completed`, chỉ render
   completed rows của các date group và date groups rỗng bị ẩn; “Quá hạn trước đó” là open-only,
   còn completed `due_at=null` phải ở subsection collapsed **“Đã xong (N)”** của “Chưa xếp ngày”,
   never fabricate a date. Khi là `all`, áp dụng rule collapse ở trên cho cả date group và subsection
   undated. Điều này giữ mọi task xem được dù không có hạn.
   Đây thay thế filter `overdue` như một màn list riêng; banner có thể scroll/focus tới group liên
   quan, không tạo một filter làm biến mất timeline.

### 2.3 Điều hướng ngày và lịch sử

- `Xem thêm ngày trước` lấy block `[earliest-7, earliest)`; `Xem thêm ngày sau` lấy
  `[latest+1, latest+8)`. Không overlap/gap ở boundary, không reset collapse choice của date group
  đã nằm trên màn và không duplicate ID nếu response/network replay.
- CTA vẫn visible/focusable ở mobile. Nếu không còn dữ liệu trong hướng đó, hiển thị state trung thực
  hoặc disable có giải thích ngắn; không tạo CTA dead. Không dùng number page.
- `Xem toàn bộ lịch sử` chuyển sang history browsing có chủ đích: bắt đầu từ ranh giới quá khứ đang
  biết và tiếp tục nạp **block 7 ngày** theo cursor/range khi người dùng yêu cầu hoặc scroll tới
  sentinel. Nó là lối tới mọi due-date trong quá khứ, không phải lệnh “fetch tất cả”. Vẫn không có
  số trang. Future navigation giữ CTA block riêng.
- Mỗi CTA đang fetch có trạng thái pending hữu hạn, `aria-live` nhỏ cho result/error, và có retry
  nhìn thấy được. Một error ở block lịch sử không xóa các group đã tải thành công.

### 2.4 Filter, search, empty/loading/error và mutation

- Giữ intent của filter status hiện có; đổi layout timeline chứ không đổi nghĩa `open`, `completed`,
  `all`. Không thêm sort control mới trong 022.
- **OBSERVED:** `TasksScreen` hiện không có Task text search. **Không thêm search field** để mở scope.
  Nếu một search control đã tồn tại lúc implementation/rebase, nó phải được đánh giá server-side cùng
  status/date range trước pagination/cursor; kết quả search không được giới hạn 100 hay chỉ tìm các
  block đã cache. Chốt product search UX là task riêng nếu chưa có.
- Empty first load: giữ quick-add usable, nói rõ không có task phù hợp trong seven-day window và chỉ
  khi cần nêu nhóm null/overdue rỗng. Loading skeleton/status không được nhảy layout quá mức. Initial
  error có retry và copy “Không tải được việc. Thử lại.”, không xóa cache timeline cũ. Error một
  continuation block nằm cạnh CTA block đó.
- Giữ tất cả mutation hiện có: quick add, create dialog, edit, pin/unpin, complete/reopen, reschedule,
  checklist, soft-delete + undo, private gate và legacy pin migration. Sau mutation invalidation phải
  cập nhật ngay group cũ/mới (dời hạn, due→null, null→due, complete/reopen, pin) và calendar family
  hiện có; không chờ 1s/CTA kế tiếp. Không `await invalidateQueries` trong `onSuccess`.
- Không để mutation leak private task vào cache/group khi private gate locked. Khi gate thay đổi, dùng
  invalidation/purge contract hiện có để rows private không còn render được.

## 3. Backend/API contract — bounded request, không tăng limit

### 3.1 Contract cần thi công

Thay list contract Task bằng một contract cursor/date-range đủ cho **cả Timeline và Calendar**, hoặc
thêm route timeline riêng nhưng phải giữ Calendar functional. L2 route name được phép, nhưng contract
phải có đầy đủ các khả năng dưới đây và OpenAPI/TypeScript caller phải cùng một source of truth:

```
status = open | completed | all
due range = [from, to) theo local Vietnam date, optional
due bucket = dated | undated (optional; undated means due_at IS NULL)
cursor = opaque, tamper/shape-invalid -> 422, never SQL fragment
limit = bounded server-side page size (không 100 fixed cap workaround)
response = { items, next_cursor: string | null, ...optional group counts }
```

- Range query trả task có `due_at >= from_instant AND due_at < to_instant`. Có endpoint/query rõ ràng
  cho open `due_at < earliest` và open `due_at IS NULL`; không fetch `status=all` lịch sử rồi lọc
  client-side.
- Cursor là keyset theo ordering thật, gồm tie-break `id`; không dùng `offset` càng lớn càng chậm.
  Cursor của dated query không dùng lại cho undated query hay status/range khác. Invalid/tampered/stale
  cursor phải fail rõ, không skip/duplicate hàng im lặng.
- `limit` bảo vệ request và được server clamp/reject; không đơn giản đổi `le=100` thành 500/1000 rồi
  gọi đó là solution. UI load next cursor trong cùng group/block không hiển thị page number; nếu cần
  nhiều page trong một date group, control phải nói hành động (“Xem thêm việc trong ngày”), không nói
  trang/số offset.
- Response/timeline metadata phải đủ để collapsed completed group (kể cả undated) biết count mà không
  cần poll/nạp full historical content. Fetch rows completed khi expand có thể lazy, nhưng phải
  reachable và sau mutation đúng.
- `readable()`/privacy gate và `deleted_at` filtering phải nằm **trước** pagination. Child `TaskItem`
  chỉ query cho parent page IDs như store hiện tại; không N+1 task/item. Không trả `completed_at` hay
  private payload khác ngoài TaskRead policy hiện hữu.

### 3.2 Query/loading và polling budget

- Default visible Task screen chỉ request các bucket cần cho seven-day window, overdue-before-window
  và undated-open, theo cursor bounded. Không tải all history lúc mount, focus, poll 1s hay khi click
  một filter.
- Theo Task 021, chỉ **primary query family của TaskScreen đang visible/mounted** dùng
  `taskRefetchInterval` 1s (`pollWhileHealthy`); hidden/unmount/error dừng. Expanded history blocks,
  lazy completed pages và continuation cursors không nhân thêm timer 1s. Chúng refresh qua explicit
  mutation invalidation/focus cần thiết, không biến một Task screen thành N poller.
- Không dùng `refetchIntervalInBackground: true`, custom visibility timer hay global default. Focus
  quay lại được phép một wave như 021; exact request count phải report tách khỏi interval count.
- Calendar phải đổi từ offset fixed/5×100 sang date-window/cursor loading tương đương và vẫn explicit
  `NO_POLLING_QUERY_OPTIONS`. Calendar không được lấy cả lịch sử task ở mỗi focus/scroll expand; chỉ
  lấy tasks cần cho month window/selected detail hoặc cached cursor range theo contract được chọn.

### 3.3 DB/index/performance

Trước khi thêm index, executor đọc query plan trên throwaway Postgres/CI fixture có >191 rows và privacy
conditions; không sửa Neon trực tiếp. Migration/index choice phải chứng minh được supporting queries:

- dated status/range/keyset; và
- open-overdue / undated keyset.

`ix_task_due_at` đơn hiện hữu có thể không đủ cho `status` + `deleted_at` + cursor. Một partial/composite
index (ví dụ live rows, `status, due_at, id`, cộng index cho null bucket nếu plan cần) là L2 **chỉ khi
EXPLAIN/acceptance chứng minh cần**. Nếu migration thay index, migration QA và catalog assertion phải
kiểm tên/cột/predicate thật. Không create unbounded duplicate index chỉ vì “có thể nhanh”.

## 4. UI/accessibility/mobile contract

- Dùng components `@/components/ui/*`; không `<button>`/`<input>` thô, không hardcode màu, dark mode,
  height cứng cho card, text <12px hoặc hover-only path. Giữ warm light tokens/các contrast rule của
  `ui-brief.md`.
- Header ngày, group “Quá hạn trước đó”, “Chưa xếp ngày”, collapse controls và CTAs cần testid semantic
  (đề xuất `task-day-group`, `task-day-completed-toggle`, `task-load-earlier`, `task-load-later`,
  `task-history`, `task-undated-group`, `task-overdue-earlier-group`). ID/ngày ở `data-*` riêng, không
  nhét ID vào testid.
- Mobile 390×844: không horizontal scroll; primary CTA/collapse control đạt 44×44 CSS px hoặc có vùng
  chạm rõ ≥44px; icon button vẫn aria-label động từ + đối tượng. Desktop 1280×800 giữ tooltip chỉ như
  lối tắt, không làm đường duy nhất.
- Khi CTA thêm dates, focus không bị ném lên đầu trang: giữ context hoặc chuyển focus tới heading của
  block mới theo hành động người dùng. Keyboard Tab đi hết controls không trap; collapse đúng
  `aria-expanded`/`aria-controls`.
- QA dùng adversarial text bắt buộc (70 ký tự không space, tiếng Việt dấu dày, chữ hoa có dấu, emoji,
  một ký tự, leading/trailing whitespace, whitespace-only rejection), không dùng title/body thật.

## 5. Test bắt buộc — RED → GREEN, không chỉ đọc code

### 5.1 Backend/domain/API

Trên Postgres throwaway/CI, seed synthetic >191 task (ví dụ 205+) trải qua nhiều date, cùng due date,
open/completed, 3 pinned rải group, overdue trước window, `due_at=null`, soft-deleted và private
locked/unlocked. Không hardcode count dữ liệu thật của owner.

1. Cursor/range: theo từng cursor page collect **mọi** visible ID đúng một lần; không skip/duplicate;
   tất cả >191 reachable; invalid cursor 422; status/date/bucket không bypass private/deleted gate.
2. Boundary +07: cases ngay trước/tại midnight, `today-3` inclusive, `today+4` exclusive và current
   now cho overdue. Assert đúng group/bucket, không dùng machine timezone.
3. Ordering: pinned chỉ first trong own day/overdue/undated group; status filter không leak completed
   pin vào open; stable tie-break across cursor page.
4. `due_at=null` open vào undated group; completed null-due chỉ ở subsection collapsed undated, không
   bị đặt giả vào dated/history và vẫn reachable qua filter completed/all.
5. Existing create/update/item/delete/restore/private API tests vẫn pass; add API tests cho dời task
   qua range/null, complete/reopen và `next_cursor` response. Calendar caller tests phải chứng minh
   không còn assumption five `offset=100` pages.
6. Nếu migration index cần, run required `Migration QA` lane and catalog/assertion of exact index.

### 5.2 Frontend unit + Playwright production-build mock lane

Fixture/API mock phải parse range/cursor thật (không trả toàn mảng bất kể query) và có >191 synthetic
rows. Tests bám `data-testid`, không bám Vietnamese copy dễ đổi.

- Default thấy exactly seven contiguous date headers today−3…today+3, nhóm overdue-old và undated đúng
  rule, pinned không vượt group, completed collapsed rồi mở được.
- Filters open/completed/all cập nhật đúng group semantics; banner overdue scrolls/focuses group thay
  vì biến màn thành list pagination.
- Click/tap previous/next add exact contiguous 7 days no duplicate/gap; history path reaches a task
  beyond row 191; DOM không có page number/pagination/offset control.
- Mutation mock làm task xuất hiện đúng group ngay qua invalidation (due→null/null→due, reschedule,
  complete/reopen, pin); undo/private gate giữ behavior cũ.
- Query tests: primary visible Task query ~1s; hidden 0 interval; one expanded history/completed block
  không tạo poll 1s thứ hai; after mutation GET occurs before next cadence. Đo exact method/path/query
  params and distinguish initial/focus/mutation from interval.
- Desktop 1280×800 + mobile 390×844 run cả timeline flows. Mobile measure no horizontal overflow and
  touch targets; keyboard/ARIA collapse/focus on desktop; loading/error/empty states on both. Include
  `30+` visual density and all QA-framework states, then visual screenshots for timeline at ≥30 items.

Harness may keep `serviceWorkers: 'block'`; that is local browser receipt, **not** PWA/iPhone proof.

### 5.3 Mandatory guard proof

Sau khi test đúng đã xanh, làm một perturbation **không commit**:

1. tạm trả/cắt route Timeline ở 100 rows (hoặc làm client dừng khi first cursor page) trong exact
   >191 Playwright/API test;
2. chạy test hẹp, thấy đỏ vì synthetic task sau row 191 không reachable — không phải lint/syntax;
3. hoàn nguyên đúng source; chạy cùng lệnh thấy xanh;
4. dán nguyên hai output RED/GREEN vào PR. Không commit RED state.

## 6. Local, CI, production acceptance

### Local

- Fresh worktree: `cd frontend && npm ci` trước khi diễn giải thiếu eslint/node_modules.
- Chạy exact backend/frontend commands từ `pyproject.toml`, `package.json`, CI workflow; tối thiểu
  backend task/API tests, `ruff check`, `ruff format --check`, frontend lint/test/build/e2e, `git diff --check`,
  pre-commit và gitleaks hook living in repo.
- Nếu DB/Docker lane cần daemon, chủ bật Docker Desktop/Postgres trước. Không suy luận timeout install
  là chưa cài: inspect lockfile/node_modules/status.

### CI / PR

- Branch `feat/022-task-day-timeline` → PR nhỏ vào `develop`; không commit thẳng develop/main, không
  auto-merge. Docs/spec PR này không chứa code; chủ đã authorize implementation lane riêng sau khi
  exact-head spec được review/merge, nhưng mọi review/CI/merge gate của lane đó vẫn giữ nguyên.
- Review exact head, `gh pr checks <PR>` xanh (giữ tên required checks), then T1 decides merge.
- PR phải tách **ĐÃ CHẠY** (raw outputs, HEAD/diff, RED/GREEN, CI), **CHƯA CHẠY** (iPhone/production
  QA), **SUY LUẬN** (request ceilings/index judgment). Không ghi title/body/cursor token, account,
  email, PIN, cookie hay personal data.

### Production after merge

Sau merge only: `/api/readyz.commit` equals exact merge SHA, `db=up`, healthy Fly Machine. Đây không
tự là browser acceptance. Chrome QA with an allowlisted role and only synthetic tasks measures default,
7-day CTAs, >191 reachability and request cadence; logout/close tab/cleanup synthetic rows. iPhone
physical/Safari must separately verify day boundaries, touch targets, keyboard safe area and collapse;
if unavailable report **CHƯA VERIFY**, never call local mock lane production proof.

## 7. Không được làm

- Không chỉ tăng `limit`, không offset pagination/page numbers, không bulk load toàn history cho poll.
- Không cutover/migrate data thật, không touch old app/SQLite/Neon production manually.
- Không add Task `archived` status, schema concept, AI/search UX, WebSocket/SSE, outbox/Dexie/service,
  global polling, custom visibility loop or new dependency without owner decision.
- Không thay product decision của Task 012, private policy, Calendar feature semantics or existing
  mutation/idempotency/undo contract. Calendar changes chỉ để preserve full correct Task consumption.
- Không log/commit fixture based on personal task/note content or credentials.

## 8. Việc của CHỦ trước khi giao implementation

- [ ] Nếu executor chạy DB-backed backend/index/migration QA: bật Docker Desktop hoặc Postgres service
      throwaway. Nếu quên, expected prerequisite error là connection refused/daemon unavailable; đừng
      debug nó như lỗi code.
- [ ] Nếu production Chrome/iPhone lane: nêu rõ allowlisted QA role trong prompt; chuẩn bị synthetic
      data only. Không dùng account khác và không sử dụng dữ liệu task thật.
