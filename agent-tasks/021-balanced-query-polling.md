# 021 — cân bằng query polling theo mức cần đồng bộ

> **Executor: T2 (chọn route từ Runtime Catalog lúc giao) · Effort đề xuất: high ·
> Skill gợi ý: không cần · MCP cần: Playwright cho local browser QA; Chrome chỉ dùng ở production QA.**
> **Trạng thái: ✅ OWNER-APPROVED DECISION 2026-08-16 — spec sẵn sàng qua review; implementation
> phải đi branch/PR riêng sau PR docs này.**
> **Không migration. Không backend.** Task này chỉ đổi chính sách làm mới server-state ở frontend.

Đọc trước khi thi công: `CLAUDE.md` · `AGENTS.md` · `docs/frontend-brief.md` ·
`docs/ui-brief.md` §6 · `docs/devops-brief.md` §7 · `agent-tasks/018-qa-polish-playwright.md`
§2.6 · các screen/query/test được liệt kê ở §1.

## 0. Hành vi chủ đã chốt

Chỉ cần đồng bộ liên tục khi **đang thật sự dùng app**. Nhu cầu hai thiết bị cùng mở và cùng sửa gần
như không xảy ra, nên không đáng để mọi query gọi server mỗi giây.

Chính sách mới:

| Màn / query family | Interval khi query khoẻ và tab đang active | Khi quay lại foreground/focus | Sau mutation |
|---|---:|---|---|
| **Task** | **1 giây** | refetch | invalidate/refetch ngay |
| **Notes** | **15 giây** | refetch | invalidate/refetch ngay |
| **Tracker** — toàn bộ query đang active | **15 giây/query** | refetch | invalidate/refetch ngay |
| **Subscription route** — toàn bộ query đang active | **15 giây/query** | refetch | invalidate/refetch ngay |
| **Calendar** | **không interval** | refetch một wave khi quay lại | invalidate/refetch ngay |
| **Session** (`App` và observer ở reminder-confirm) | **không interval** | refetch | invalidate theo flow hiện có |
| **Query mới về sau** | **không interval mặc định** | theo default focus | theo mutation của slice |

Mọi interval ở bảng trên phải **dừng khi query chuyển sang `error`**. Không poll trong tab
hidden/background; không bật `refetchIntervalInBackground`.

## 1. Sự thật đã quan sát trên code — base `2cac6698930b98111e0e448ed3b4377a2e378cb4`

### 1.1 OBSERVED — query map hiện tại

Đã đọc trực tiếp `frontend/src/main.tsx`, `App.tsx`, các screen và query spec sau. Đây là count
`QueryObserver` ở màn đang mount, không phải số hàng dữ liệu:

| Khu vực | Query đang mount | Cơ chế hiện tại trước 021 |
|---|---:|---|
| `TasksScreen.tsx` | 1 — `tasks` | thừa hưởng global **1s**, dừng khi error |
| `NotesScreen.tsx` | 1 — `notes` | thừa hưởng global **1s**, dừng khi error |
| `TrackerScreen.tsx` | 6 — groups, trackers, dashboard, entries, subscriptions, settings | cả 6 thừa hưởng global **1s**, dừng khi error |
| `SubscriptionScreen.tsx` | 3 — subscriptions, settings, trackers | cả 3 thừa hưởng global **1s**, dừng khi error |
| `CalendarScreen.tsx` list | 2 — sources, events | mỗi query đã `refetchInterval: false` |
| `CalendarScrollView.tsx` grid | session + sources + N month-events + annotations + all-tasks + open-tasks | tất cả đi qua spec `refetchInterval: false`; ban đầu N=13, và N tăng khi cuộn mở rộng tháng |
| `App.tsx` | 1 — session | đã `refetchInterval: false` |
| `ReminderConfirmScreen.tsx` | 1 observer — session, dùng cùng key `['session']` | **chưa opt-out**, nên observer này đang thừa hưởng global 1s |
| query mới không khai interval | tuỳ slice | tự động thừa hưởng global 1s |

OBSERVED thêm:

- `main.tsx` đang đặt global `LIVE_REFETCH_MS = 1000` và default function cho mọi query.
- `refetchOnWindowFocus` không bị tắt; mutation hiện tại invalidate các query family liên quan.
- `CalendarScrollView` ban đầu tạo 13 query tháng vì `monthsWindow(center, 6)`, rồi thêm 6 tháng mỗi
  lần mở rộng. Hai query task của lịch có thể phân trang tới 5 request HTTP cho mỗi lần fetch.
- `frontend/tests/calendar-queries.test.ts` đang mirror global 1s để chứng minh Calendar opt-out.
- `frontend/e2e/tasks.spec.ts` đã có lane đo Task khoảng 60 request/60s và hidden 0/60s.
- Package được lock ở `@tanstack/react-query@5.101.2`, `@playwright/test@1.62.1`,
  `vitest@4.1.10`, React `19.2.8`, Vite `8.1.5` (`package-lock.json` lockfile v3).

### 1.2 INFERRED — vì sao chia ba mức như vậy

- **Task 1s:** đây là hành vi hai thiết bị đã được 018 nghiệm thu; checkbox/task đang thao tác là nơi
  phản hồi gần realtime có giá trị rõ nhất. Giữ nguyên để không hạ UX đã có.
- **Notes 15s:** ghi chú hiếm khi được sửa đồng thời ở hai thiết bị. Trễ tối đa khoảng 15 giây khi
  cả hai màn cùng mở là trade-off chấp nhận được; mutation trên chính thiết bị vẫn cập nhật ngay.
- **Tracker 15s:** một màn mount 6 query. Global 1s biến một màn thành tối đa khoảng 360 lượt
  interval/phút dù người dùng chủ yếu chỉ bấm một tracker. 15s vẫn đủ thấy thay đổi thiết bị kia
  trong lúc đang dùng mà giảm fanout 15 lần.
- **Subscription 15s:** ba query cùng mount; dữ liệu chu kỳ không cần realtime 1s. Mutation gia hạn,
  sửa setting và CRUD vẫn invalidate ngay nên thao tác tại chỗ không phải chờ interval.
- **Calendar không interval:** đây là màn fanout lớn nhất: ban đầu 13 tháng + các query phụ; query
  task còn có pagination. Lịch ít khi bị sửa song song. Mount, quay lại foreground/focus và mutation
  là ba điểm làm mới đủ dùng mà không tạo một cơn request lặp.
- **Session không interval:** TTL dài; cần kiểm khi mount/quay lại app và sau unlock/logout, không
  cần hỏi `/api/me` theo đồng hồ. `App` đã làm đúng; 021 chỉ đóng observer còn hở ở reminder-confirm.
- **Query mới mặc định không poll:** quên khai interval sẽ tạo dữ liệu hơi cũ nhưng hữu hạn và dễ
  phát hiện trong QA; tự động poll 1s một query fanout/đắt có thể gây tải âm thầm. Vì vậy 021 đảo
  default từ opt-out sang **opt-in có chủ đích**.

## 2. Hợp đồng implementation — đã khoá

### 2.1 Default toàn app: không interval, focus/foreground vẫn bật

Trong `main.tsx`, bỏ `LIVE_REFETCH_MS = 1000` và bỏ global function 1s. `QueryClient` phải có policy
tường minh, test được:

- `refetchInterval: false` (hoặc bỏ option vì TanStack mặc định là false), nhưng code/test phải làm
  rõ **query mới không poll**;
- `refetchIntervalInBackground: false` — không được đặt `true` ở global hay query riêng;
- `refetchOnMount: true` và `refetchOnWindowFocus: true` giữ bật;
- không tự viết `visibilitychange`, `focus` hoặc timer listener mới; dùng lifecycle của TanStack.

Tạo một policy/helper trung tâm có tên rõ nghĩa (ví dụ `query-polling.ts`) để giữ:

- `TASK_REFETCH_MS = 1_000`;
- `STANDARD_REFETCH_MS = 15_000`;
- function trả `false` khi `query.state.status === 'error'`, còn khoẻ thì trả interval được truyền
  vào.

Tên file/helper cụ thể là L2 của executor, nhưng **không** được rải số `1000`/`15000` khắp screen và
không được quay lại global interval. Nếu chọn cách khác helper trung tâm, PR phải ghi rõ judgment
call và vẫn phải đạt toàn bộ test map ở §4.

### 2.2 Mọi query active phải khai đúng policy

- `TasksScreen`: query duy nhất khai **function 1s + stop-on-error**.
- `NotesScreen`: query duy nhất khai **function 15s + stop-on-error**.
- `TrackerScreen`: **cả 6 query** khai **function 15s + stop-on-error**. Không bỏ sót
  subscriptions/settings chỉ vì endpoint không nằm dưới `/api/tracker/`.
- `SubscriptionScreen`: **cả 3 query** khai **function 15s + stop-on-error**.
- `CalendarScreen`, `CalendarScrollView` và `calendar-queries.ts`: giữ **explicit false** cho mọi
  query tĩnh lẫn `useQueries` động. Cập nhật comment/test cũ để không còn nói global 1s đang tồn tại.
- Session trong `App`: giữ **explicit false**.
- Session observer trong `ReminderConfirmScreen`: thêm **explicit false**. Unlock thành công/lỗi vẫn
  invalidate `['session']` như hiện tại; không đổi body/idempotency flow của confirm.

Không đổi query key, endpoint, retry policy hay `staleTime` trong task này.

### 2.3 “Đang dùng” được hiểu theo browser visibility, không theo cảm giác cửa sổ

Hợp đồng cần viết cả hai nửa để QA không báo nhầm:

- tab đóng/unmount ⇒ không còn observer/timer;
- tab `document.hidden`, tab nền hoặc cửa sổ minimize làm browser báo hidden ⇒ interval dừng;
- quay lại `document.visible`/foreground ⇒ query stale được refetch một wave theo
  `refetchOnWindowFocus`, rồi interval của Task/Notes/Tracker/Subscription tiếp tục;
- **chỉ blur/mất keyboard focus nhưng `document.visibilityState === 'visible'` không phải một cam
  kết dừng**. Ví dụ hai cửa sổ đặt cạnh nhau: cửa sổ microSched có thể vẫn poll dù người dùng đang
  gõ ở cửa sổ kia. Đây là trade-off đã được chủ chấp nhận; không thêm custom blur listener.

Test hidden phải thay đổi Page Visibility/focus manager thật sự; chỉ gọi `window.blur()` rồi đòi 0
request là test sai hợp đồng.

### 2.4 Mutation phải vẫn tức thì

Giữ nguyên mọi `invalidateQueries`/cache purge hiện có. Sau create/update/delete/restore/capture/
renew/setting change thành công, query liên quan phải refetch ngay; **không** chờ mốc 1s/15s.

Không `await invalidateQueries` trong `onSuccess` (luật `docs/ui-brief.md` §9c). Không thêm optimistic
update trong task này.

## 3. Trần request lý thuyết sau 021 — không phải production receipt

Các số dưới đây là **theoretical configuration ceilings** của interval trong 60 giây sau khi bỏ lượt
mount/focus/mutation/retry và giả định request settle kịp. Chúng không phải số đã đo trên production:

| Màn | Số query có interval | Trần interval lý thuyết / phút |
|---|---:|---:|
| Task | 1 × 1s | **~60** |
| Notes | 1 × 15s | **~4** |
| Tracker | 6 × 15s | **tối đa ~24** |
| Subscription route | 3 × 15s | **tối đa ~12** |
| Calendar | 0 | **0** |
| Session / reminder-confirm | 0 | **0** |

Lượt initial mount, một wave foreground/focus, mutation invalidation và retry hợp lệ có thể làm số
Network quan sát cao hơn bảng. TanStack/query-key sharing cũng có thể làm thấp hơn; báo cáo phải ghi
cách đo thay vì ép số cho đẹp.

## 4. Test bắt buộc — executable, không chỉ đọc code

### 4.1 Vitest + fake timers

Thêm/cập nhật unit test ở `frontend/tests/` để chứng minh:

1. **Biên 1s chính xác:** sau initial fetch, `999ms` chưa có interval call; tại `1000ms` có đúng một;
   mỗi biên tiếp theo tăng đúng một.
2. **Biên 15s chính xác:** sau initial fetch, `14_999ms` chưa có interval call; tại `15_000ms` có
   đúng một; tại `60_000ms` có đúng bốn interval calls.
3. Query đã vào `error` có **0 interval call tiếp theo** ở cả policy 1s và 15s; đặt `retry: false`
   trong test để không trộn retry với polling.
4. Query dùng app default mà không khai interval có **0 interval call** sau ít nhất 60s fake time.
5. Calendar list/grid, App session và reminder-confirm session đều có explicit policy **0 interval**.
   `CALENDAR_QUERY_SPECS` vẫn phủ query động, nhưng comment/test phải mô tả default mới đúng sự thật.
6. `focusManager` inactive/hidden ⇒ 0 interval; active/visible trở lại ⇒ đúng **một network fetch
   cho mỗi unique query key stale đang active** trong wave đó. `App` và `ReminderConfirmScreen` có
   thể đồng thời giữ hai observer của cùng key `['session']`; TanStack phải dedupe thành **một**
   fetch, test không được đòi hai chỉ vì có hai observer.
7. Unsubscribe/unmount observer ⇒ 0 call về sau.

Test phải restore fake timers và trạng thái `focusManager` sau mỗi case để không làm bẩn suite.

### 4.2 Playwright local trên production build

Dùng fixture API giả lập hiện có; không auth bypass, không backend thật. Có thể thêm một file
`polling.spec.ts` hoặc đặt test cạnh fixture phù hợp, nhưng phải đo được:

- Task visible giữ hành vi hiện tại khoảng 1s; test hai thiết bị/fixture hiện có không bị hạ cấp.
- Notes visible chạy theo 15s.
- Tracker visible không có query nào chạy 1s; trong một cửa sổ 15s chỉ có tối đa một interval call
  cho mỗi trong 6 query active.
- Subscription route tương tự, tối đa một interval call/query trong cửa sổ 15s.
- Calendar, App session và reminder-confirm session: sau initial fetch, 0 interval call trong cửa
  sổ đo. Browser chỉ đo query sản phẩm thật; **không** thêm component/query test-only vào app để tạo
  một product observer dùng default.
- Chuyển trang sang hidden bằng Page Visibility ⇒ 0 interval call; quay lại visible ⇒ một focus wave.
- Chuyển khỏi screen/unmount ⇒ endpoint của screen cũ không còn interval call.
- Một mutation trên màn 15s làm GET invalidation hạ cánh ngay, trước biên 15s; không đợi timer.
- Không có request fanout ngoài query map §1.1.

Không bắt mọi test browser phải chờ đủ 60 giây: cadence chính xác đã do fake timers chứng minh. Lane
timing thật có thể dùng cửa sổ ngắn vừa đủ vượt 15s để giữ CI hữu hạn. Giữ hai project mobile
390×844 + desktop 1280×800 và `serviceWorkers: 'block'` của harness hiện tại.
Default-no-poll của query mới được chứng minh tập trung bằng Vitest/helper ở §4.1 mục 4, không phải
bằng dead/test-only product code trong Playwright.

### 4.3 RED → GREEN guard proof

Ít nhất một guard mới phải chứng minh biết đỏ:

1. sau khi test đúng đã viết, **tạm** đổi `STANDARD_REFETCH_MS` từ 15s về 1s *hoặc* bỏ explicit
   `false` của reminder-confirm;
2. chạy đúng test hẹp, thấy đỏ vì **cadence/no-poll contract** (không phải lỗi syntax);
3. hoàn nguyên code;
4. chạy lại cùng lệnh, thấy xanh;
5. dán hai đoạn output vào PR description/comment. Không commit trạng thái RED.

## 5. Acceptance local, CI và production

### 5.1 Local — từ `frontend/`

- `npm ci` nếu worktree mới chưa có `node_modules`.
- `npm run lint`
- `npm test`
- `npm run build`
- `npm run e2e`

Từ repo root:

- `pre-commit run --all-files`
- `gitleaks git --pre-commit --staged` hoặc đúng lệnh hook sống trong repo;
- `git diff --check`;
- `git status --short` + `git ls-files`/`git check-ignore -v` cho file mới.

### 5.2 CI / merge

- PR nhỏ từ `feat/021-balanced-query-polling` vào `develop`; không commit thẳng `develop`, không đụng
  `main`, không `--auto` merge.
- Exact-head independent review đọc cả spec này, diff thật và test output.
- `gh pr checks <PR>` phải xanh, gồm lane `Frontend e2e`; không đổi tên required jobs/ruleset.
- Merge tuần tự theo gate T1. Không migration.
- Sau merge, `/api/readyz.commit` phải khớp exact merge SHA, `db=up`, và một Fly Machine đang passing
  trước khi gọi deploy xong. Đây **chưa** phải browser acceptance.

### 5.3 Production Chrome Network QA — sau deploy

Chỉ chạy khi T1/chủ đã cho phép dùng **vai allowlisted** trong lượt QA. Dùng dữ liệu synthetic/mock,
không dữ liệu cá nhân thật; không ghi email, endpoint nhạy cảm, cookie, literal dev PIN hay payload
riêng tư vào ảnh/log/PR. Nếu account chooser xuất hiện, xác nhận đúng vai trên màn confirmation rồi
mới tiếp tục. Xong phải logout app, đóng tab và dọn dữ liệu test được task tạo nếu an toàn.

Trong Chrome DevTools Network, reset count **sau initial mount**, đo từng cửa sổ 60 giây và ghi cả
method + pathname + điều kiện visibility:

- Task khoảng 60 interval GET/phút;
- Notes khoảng 4;
- Tracker tổng không quá khoảng 24 trên 6 endpoint;
- Subscription route tổng không quá khoảng 12 trên 3 endpoint;
- Calendar/session/reminder-confirm: 0 interval GET sau initial mount;
- hidden/background: 0 interval GET; trở lại visible tạo một focus wave;
- mutation synthetic trên màn 15s tạo refetch ngay, không chờ hết 15s.

Lane production của `reminder-confirm` chỉ chạy khi đã có một synthetic dispatch hợp lệ do flow QA
Web Push hiện hữu tạo ra. Không chèn tay DB, không tạo public debug route và không tái dùng dispatch
thật chỉ để lấy count. Nếu chưa có prerequisite này, ghi **CHƯA VERIFY production**; unit +
Playwright vẫn là receipt bắt buộc, không được nâng thành bằng chứng production.

Sai số do request đang in-flight hoặc mốc đo được phép giải thích bằng raw timestamps. Không biến
trần lý thuyết §3 thành lời khai production nếu chưa có Network receipt thật.

## 6. KHÔNG được làm

- Không backend, route, schema, migration, CRON, Web Push hoặc delivery-log changes.
- Không chạm implementation/WIP Task 017, Dexie, outbox hay persisted cache.
- Không WebSocket/SSE/service mới; 021 chỉ điều chỉnh TanStack Query policy hiện có.
- Không `refetchIntervalInBackground: true`; không custom blur/visibility timer.
- Không đổi query key, endpoint, retry, `staleTime`, auth/private flow hoặc mutation semantics.
- Không thêm dependency.
- Không đụng UI/microcopy/style; task này không có thay đổi thị giác.
- Không ghi tài khoản thật, literal PIN, secret hoặc dữ liệu cá nhân vào repo/PR/log.

## 7. Báo cáo bắt buộc

Tách ba nhãn:

- **ĐÃ CHẠY:** dán output lệnh, exact HEAD, diff stat, RED/GREEN receipt, CI và production/Chrome
  receipt nào thực sự đã thấy.
- **CHƯA CHẠY:** iPhone/Safari, production Network lane hoặc gate nào chưa có.
- **SUY LUẬN:** chỉ dùng cho trần §3/lập luận trade-off; không gọi là production proof.

PR description phải nêu rõ: query map trước/sau, trần lý thuyết, visibility nuance ở §2.3, RED/GREEN
receipt, không backend/migration, và mọi L2 judgment call của executor.
