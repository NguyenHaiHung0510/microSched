# 018 — batch polish màn Task + đồng bộ đa thiết bị + Playwright suite đầu tiên

> **Executor: Codex (T2)** · Bậc: **Sol** · Effort: **high** · **Skill gợi ý:** `frontend-design`, `design-qa` · **MCP cần:** không (Playwright chạy bằng CLI).
> Nhánh **`feat/018-qa-polish-playwright`** → PR nhỏ vào `develop`.
> Spec tự-chứa. Đọc **`CLAUDE.md`** + **`AGENTS.md`** + **`docs/ui-brief.md` §6, §8, §9** + **`docs/qa-framework.md`** trước khi viết dòng đầu tiên.
> ⚠️ **Task này KHÔNG có migration.** Merge xong **đừng** chạy `alembic upgrade` theo quán tính.
> ⚠️ **Cần chạy được server cục bộ + tải browser cho Playwright** ⇒ giao bằng `-s danger-full-access`.

## 0. Bối cảnh — vì sao có task này

Chủ tự dùng app thật một buổi (29/07, iPhone + máy tính) và bắt được 5 mục mà **lượt QA kịch bản của
`008e` bốn ngày trước đó đã trượt sạch**. Cả hai lượt đều làm đúng việc của mình: lượt 25/07 soi **dữ
liệu ác ý**, buổi 29/07 soi **việc dùng thật lặp lại**. Khoảng trống nằm giữa hai phạm vi.

Task này làm ba việc, và **chỉ có việc thứ ba là lý do nó phải chạy trước `009`**:

1. Sửa 5 mục đã bắt được (rẻ, đã biết chính xác chỗ nào).
2. Mở seam đồng bộ đa thiết bị (`refetchInterval`) — chủ dùng app trên **hai thiết bị**, hiện phải
   tải lại trang bằng tay.
3. **Dựng harness Playwright + quy ước `data-testid` để `009`–`012` kế thừa.** Đây mới là phần đắt:
   `008` là task đặt khuôn, và mọi slice sau chép hình của nó. Dựng harness sau `009` nghĩa là `009`
   ra đời không có test hồi quy, rồi `010`–`012` chép đúng cái thiếu đó.

Khung QA (`docs/qa-framework.md`) đã được T1 viết xong trong cùng phiên — **task này là lượt áp dụng
đầu tiên của nó**, và §4 dưới đây bắt buộc một lượt QA theo khung đó sau khi deploy.

## 1. Đã KHOÁ — chép ra code, không mở lại

1. **Lớp nổi (tooltip/popover) phải portal ra `body`.** Khung app có `overflow-hidden` (`App.tsx:75`)
   — mọi thứ dựng bằng `absolute` bên trong thẻ sẽ bị cắt. Không có ngoại lệ, và luật này áp cho cả
   `009`–`012`.
2. **Không viết tay component nổi.** `shadcn add tooltip` (`ui-brief.md` §8: *"009–012 cứ `shadcn
   add`, đừng viết tay"*). Tooltip hiện tại là một `<div>` tự vẽ — đúng cái mà luật UI #1 gọi là
   *"vá tại chỗ"*.
3. **"Trễ hạn" là một *view dẫn xuất*, không phải một *status*.** Không được nới `TaskFilter` trong
   `task-ui.ts` — kiểu đó mô tả `status` của server và đang được `taskQueryKey` dùng. Xem §2.3.
4. **`data-testid` theo đúng quy ước ở `docs/qa-framework.md` §6.** Tên đặt ở task này là tên mà 4
   slice sau sẽ chép.
5. **Playwright chạy trên API giả lập ở tầng mạng, không chạy trên backend thật.** Xem §2.7 — lý do
   và giới hạn được ghi rõ ở đó, đừng tự nâng cấp.
6. 🔒 **Tuyệt đối không thêm đường vòng xác thực (auth bypass) cho test.** Dù chỉ bật ở `APP_ENV=local`.
   Lõi bảo mật của dự án được review tay từng dòng; đổi nó để lấy vài test giao diện là đánh đổi tồi.

## 2. Phải làm

### 2.1 Tooltip bị khung ngoài cắt

**Hiện trạng:** `TasksScreen.tsx:370-388` — tooltip tự vẽ bằng `absolute` + `group-hover/task`,
`md:block`, `aria-hidden`. Thẻ nằm gần đáy danh sách thì tooltip bị `overflow-hidden` của
`App.tsx:75` cắt mất.

**Phải làm:**
- Thay bằng `@/components/ui/tooltip` (`shadcn add tooltip`). Nội dung tooltip giữ nguyên (checklist
  + ghi chú).
- Giữ nguyên **tính chất lối tắt desktop**: hover/focus mở, không thay thế đường chạm. Đường chạm là
  `Dialog` chi tiết — nó phải tiếp tục hiển thị đủ mọi thứ tooltip hiển thị (`ui-brief.md` §9a).
- ⚠️ `shadcn add` có **4 cái bẫy đều báo thành công khi hỏng** (`ui-brief.md` §8): ghi ra thư mục tên
  `@` · prompt ghi đè làm rụng file · mặc định theo dark mode hệ điều hành · `var(--radius)` trần.
  **Đếm file thật sau khi chạy**, đừng đọc dòng tổng kết của CLI.
- Radix `Tooltip` cần `TooltipProvider`. Đặt **một lần** ở nơi hợp lý, không bọc từng thẻ.
- ℹ️ **Radix Tooltip không mở khi chạm** (nó lọc theo `pointerType` và đóng ở `pointerdown`) ⇒ trên
  iPhone không có tooltip kẹt lại. **Nhưng đây là hành vi thư viện, không phải thứ ta đo được ở CI**:
  §4.6 bắt buộc kiểm bằng tay trên iPhone thật — chạm tiêu đề **không** được để lại lớp nổi nào.

**Đạt khi:** thẻ **cuối cùng, sát đáy màn**, hover vào tiêu đề ⇒ tooltip hiện **trọn vẹn**, không bị
cắt cạnh nào. *(Thẻ đầu tiên luôn trông ổn — đo ở thẻ đầu là không đo gì.)*

### 2.2 Vùng bấm mở chi tiết = cả thẻ

**Hiện trạng:** `onClick` chỉ nằm trên `<Button>` tiêu đề (`TasksScreen.tsx:239-257`). Trên di động
phải chạm trúng đúng chữ.

**Phải làm:** chạm/bấm vào **bất cứ khoảng trống nào trong thẻ** cũng mở `Dialog` chi tiết.

🔒 **Ba cái bẫy, cả ba đều phải né:**

- **Không lồng phần tử tương tác vào nhau.** Thẻ chứa sẵn `Checkbox`, 3 nút icon, checklist, nút
  thu/mở. Không bọc `Card` bằng `<button>`, không dùng lớp phủ "stretched link". Cách đúng: handler ở
  `Card`, **bỏ qua** sự kiện phát ra từ một phần tử tương tác (kiểm tổ tiên gần nhất của
  `event.target`).
- **Không thêm điểm dừng Tab mới.** **Không** gắn `tabIndex` và **không** gắn `role="button"` lên
  `Card`. Đường bàn phím giữ nguyên: nút tiêu đề vẫn là điểm vào, `aria-label` giữ nguyên. *(Gắn
  `role` mà không có `tabIndex` là nói dối trình đọc màn hình; gắn cả hai là nhân đôi điểm dừng Tab
  cho mỗi task.)*
- **Không nuốt thao tác bôi đen chữ.** Kéo chọn chữ trong thẻ rồi thả **không được** mở Dialog.
  🔒 Kiểm tổ tiên (`closest`) **một mình không đủ**: bôi đen một `<span>` (hạn ở dòng 268, số mục nhỏ
  ở dòng 277) vẫn phát ra `click` với `target` là chính `<span>` đó, mà `closest('button, …')` trả về
  `null` ⇒ Dialog mở. Phải kiểm thêm **có đang có vùng chọn không** (`window.getSelection()`).

🔒 **Và một thứ nữa phải sửa cùng lúc: đường trả focus.** `detailsReturnRef`
(`TasksScreen.tsx:199-205`) hiện nhận `event.currentTarget` của **nút tiêu đề**; `onCloseAutoFocus`
(`TasksScreen.tsx:399-408`) lấy nó để trả focus khi đóng Dialog. Mở Dialog từ **thân thẻ** thì ref
không được đặt ⇒ đóng Dialog là focus rơi xuống `body`, người dùng bàn phím phải Tab lại từ đầu
trang. Sửa: mở từ thân thẻ thì đặt đường trả focus về **nút tiêu đề của chính thẻ đó** (giữ ref tới
nó). Kiểu `HTMLButtonElement` của ref phải giữ nguyên — nó chính là thứ chặn việc gán nhầm một `div`.

**Đạt khi:** ① chạm khoảng trống ⇒ mở chi tiết; ② chạm nút ghim/sửa/xoá/checkbox ⇒ **chỉ** làm việc
của nút đó, Dialog **không** mở; ③ số điểm dừng Tab trên một thẻ **không đổi** so với trước; ④ mở
Dialog từ thân thẻ rồi đóng ⇒ focus quay về nút tiêu đề của thẻ đó, **không** rơi xuống `body`;
⑤ bôi đen chữ trong thẻ rồi thả ⇒ Dialog **không** mở.

### 2.3 Banner "N việc trễ hạn" phải dẫn đi đâu đó

**Hiện trạng:** `TasksScreen.tsx:714-723` — chỉ là một `<span>` đếm số. Task trễ vẫn nằm trong danh
sách nhưng không có đường tới nếu danh sách dài.

**Phải làm:**
- Banner thành **nút thật** (`Button`, `asChild` nếu cần giữ hình dạng) → bấm vào thì danh sách
  chuyển sang **chỉ hiển thị task trễ hạn**.
- **Kiểu dữ liệu:** không nới `TaskFilter` (§1.3). Dựng một kiểu riêng cho *view* của màn, ví dụ
  `type ListView = TaskFilter | 'overdue'`, dùng cho state `filter` và hàng chip lọc.
  `taskQueryKey`/`status=` của API **không đổi** — client vẫn luôn gọi `status=all` và lọc ở client
  như hiện nay.
- 🔒 **Chế độ phải có lối ra nhìn thấy được** (Nielsen #3, `qa-framework.md` §3.A). Khi `overdue`
  đang bật, hàng chip lọc phải hiện chip **"Trễ hạn"** ở trạng thái active để người dùng thấy mình
  đang ở đâu và bấm sang chip khác để ra.
- Chip "Trễ hạn" **chỉ hiện khi** `overdueCount > 0` **hoặc** khi nó đang là view hiện tại. Hiện một
  chip chết khi không có gì trễ hạn là rác (Nielsen #8).
- 🔒 **Ngõ cụt phải được xử lý:** đang ở view `overdue` mà người dùng hoàn thành nốt task trễ cuối
  cùng ⇒ `overdueCount` về 0 ⇒ chip biến mất **trong khi vẫn đang ở view đó** = danh sách rỗng, không
  còn lối ra hiển thị. Khi điều đó xảy ra, **tự chuyển về `open`**.
- Banner đang có `role="status"` — giữ vai trò thông báo, nhưng nay nó là nút nên phải có `aria-label`
  mô tả **hành động** ("Xem N việc trễ hạn"), và đích chạm ≥ 44px chiều cao.

🔒 **Phải gỡ `task.pinned ||` khỏi vị ngữ lọc — nếu không thì view "Trễ hạn" không bao giờ đúng.**
`TasksScreen.tsx:687-691` hiện là:

```ts
items.filter((task) => task.pinned || filter === 'all' || task.status === filter)
```

Task **đã ghim đi xuyên qua mọi bộ lọc**. Thêm nhánh `overdue` mà giữ nguyên vế đầu ⇒ view "Trễ hạn"
vẫn hiện task ghim **không hề trễ**, tức thẳng thừng sai với chính nhãn của nó.

Đây **không phải quyết định mới** — `ui-brief.md` §9(b) đã chốt hướng sửa từ 25/07: *"ghim nổi lên
đầu **trong phạm vi** bộ lọc, không xuyên qua bộ lọc"*, và ghi *"chờ slice đưa `pinned` xuống DB làm
luôn"*. Slice đó là `008g`; nó chuyển **sắp xếp** xuống server nhưng **bỏ sót vế lọc này**. Task này
trả nốt món nợ đó — và nó vốn đã cần trả rồi, chỉ là view "Trễ hạn" làm nó không thể lờ đi thêm nữa.

Không mất gì khi gỡ: server đã sắp `Task.pinned.desc()` trước (`tasks.py`, `008g` §2.3) nên task ghim
**vẫn nổi lên đầu** — chỉ là đầu của **danh sách đang lọc**, không phải đầu của mọi danh sách.

**Đạt khi:** ① bấm banner ⇒ chỉ còn task trễ hạn; ② chip "Trễ hạn" hiện active; ③ bấm "Đang mở" ⇒ về
bình thường; ④ hoàn thành task trễ cuối cùng khi đang ở view đó ⇒ tự về "Đang mở", **không** rơi vào
màn rỗng không lối ra; ⑤ task **đã ghim + đã xong** **không** xuất hiện trong tab "Đang mở" (hành vi
`ui-brief.md` §9(b), trước nay đang sai).

### 2.4 Microcopy

**(a) Xoá hẳn** `TasksScreen.tsx:760-762`:
> *"Lưu xong ô tự xoá và giữ con trỏ để gõ tiếp."*

Nó giải thích một hành vi mà người dùng biết sau lần đầu bấm — đúng thứ mà Nielsen #6/#8 bảo bỏ. Hành
vi thì **giữ nguyên**, chỉ xoá dòng chữ.

**(b) Đổi nhãn** `TasksScreen.tsx:765-768`: `"Thêm đủ chi tiết"` → **`"Thêm chi tiết"`**.
Ngắn hơn, tiếng Việt tự nhiên hơn, và hết bọc chữ xấu.

⚠️ Sau khi xoá (a), hàng `flex flex-wrap items-center justify-between` chỉ còn một con — **kiểm lại
bố cục ở 390px bằng mắt trong trình duyệt thật**, đừng giả định. Nếu chữ vẫn xuống dòng giữa cụm thì
nhớ luật ba lớp `min-w-0 shrink break-words` (`ui-brief.md`, `qa-framework.md` §3.B) — `Button` có
`shrink-0` ở lớp gốc.

### 2.5 `data-testid`

Theo quy ước `docs/qa-framework.md` §6 (`<thực-thể>-<phần-tử>`, kebab-case). **Bộ tối thiểu** —
`009`–`012` sẽ chép đúng bộ này cho note/calendar/tracker:

| `data-testid` | Gắn ở |
|---|---|
| `quick-add-input` / `quick-add-submit` | ô thêm nhanh + nút gửi |
| `quick-add-error` | chỗ hiện lỗi của thêm nhanh |
| `task-list` | vùng chứa danh sách thẻ |
| `task-card` | mỗi `Card` — **kèm `data-task-id={task.id}`**, không nhét id vào `testid` |
| `task-title` · `task-checkbox` · `task-pin` · `task-edit` · `task-delete` | trong mỗi thẻ |
| `task-detail-dialog` · `task-create-dialog` | hai `DialogContent` |
| `filter-open` · `filter-completed` · `filter-all` · `filter-overdue` | từng chip lọc |
| `overdue-banner` | banner ở §2.3 |

Không dùng `data-testid` để móc CSS. Không xoá/đổi `aria-label` đang có để thay bằng `testid` — hai
thứ phục vụ hai đối tượng khác nhau.

### 2.6 Đồng bộ đa thiết bị — `refetchInterval`

> 📝 **2026-08-16 — SUPERSEDED bởi `021`.** Chủ đã chốt policy cân bằng mới: Task 1s;
> Notes/Tracker/Subscription 15s; Calendar + session + reminder-confirm không interval; query mới
> mặc định không poll. Mọi interval chỉ chạy khi query khoẻ và browser đang active, dừng ở hidden/
> background; focus/foreground return và mutation vẫn refetch. Phần còn lại của §2.6 dưới đây là
> decision/receipt lịch sử của 018, **không còn là policy để implementation mới chép theo**. Tại
> thời điểm note này, 021 mới là spec approved; code chỉ đổi ở PR implementation riêng của 021.

**Vấn đề:** chủ dùng app trên iPhone và máy tính. Sửa ở máy này thì máy kia đứng im tới khi tải lại
trang. TanStack Query **không** đẩy dữ liệu server→client; nó chỉ tự làm mới khi **chính nó** vừa
mutate.

**Phải làm:** đặt trong `main.tsx`, chỗ khởi tạo `QueryClient`, với hằng đặt tên
`LIVE_REFETCH_MS = 1000` — **dạng hàm, không phải số trần**:

```ts
refetchInterval: (query) => (query.state.status === 'error' ? false : LIVE_REFETCH_MS)
```

🔒 **Vì sao phải là dạng hàm — đây là chỗ bản spec đầu tiên đã SAI, giữ lại lý do:**
`refetchInterval` dạng số **vẫn tiếp tục chạy khi query đang ở trạng thái lỗi**. Bản đầu của spec này
lập luận rằng nhịp 1s "không phải sự cố Neon 22/07 mặc áo khác vì nó chỉ chạy khi có người dùng thật
đang nhìn" — **lập luận đó có một lỗ**: một tab bị bỏ quên ở **màn đăng nhập** (query `session` lỗi
`401`, `App.tsx:105-135`) sẽ gọi `GET /api/me` **mỗi giây, vô hạn**. Mà `/api/me` đi qua
`require_session` ⇒ **chạm DB**. Tức là đúng hình dạng sự cố cũ: một nhịp đều đặn giữ Neon thức mà
**không có ai đang dùng app**. Dạng hàm đóng cửa đó, và cũng thôi nện một endpoint đang hỏng.

**Và query `session` trong `App.tsx` phải tự khai `refetchInterval: false`.** Nó không cần nhịp 1s:
`refetchOnWindowFocus` (mặc định `true`) đã bắt được ca "quay lại tab thì kiểm phiên", còn phiên thì
có TTL tính bằng tháng. Đây cũng là **ví dụ mẫu cho luật opt-out** ngay dưới đây — 009–012 sẽ chép.

**Ba điều còn lại, ghi vào chú thích tại chỗ** *(người đọc sau sẽ gắn cờ đoạn này, và họ có lý do
chính đáng để gắn — chú thích tồn tại để trả lời họ)*:
- Sự cố Neon 22/07 là **health check của Fly** ping DB mỗi 30s **vĩnh viễn, không có người dùng nào**.
  Sau bản vá dạng hàm ở trên, nhịp này chỉ sống khi có **tab đang mở, đang được nhìn, và query đang
  khoẻ**.
- `refetchIntervalInBackground` mặc định là `false` ⇒ tab ẩn/mất focus thì TanStack **tự dừng** qua
  Page Visibility API. **Không tự dò, không tự viết listener.**
- Neon tính theo **compute-hour trên cửa sổ active**, không theo số request ⇒ một giờ người dùng thật
  ngồi trước app tốn như nhau dù nhịp là 1s hay 20s. TanStack **dedup theo query key** ⇒ request không
  chồng lên nhau; cộng `AbortSignal.timeout(20s)` của `008i`, xấu nhất là một lượt bị bỏ qua.

⚠️ **Cảnh báo để lại cho 009–012, không phải việc của task này:** mọi mutation hiện tại đều
**pessimistic** — giao diện đọc thẳng dữ liệu server (`checked={task.status === 'completed'}`), không
có optimistic update nào để một lượt refetch giữa chừng lật ngược. **Ngày nào một slice thêm optimistic
update, nhịp 1s biến thành máy roll-back**: refetch hạ cánh trước khi server commit là thấy giá trị cũ
đè lên giá trị vừa bấm. Slice đó phải xử lý (`onMutate` + `cancelQueries`) **hoặc** nâng nhịp lên.

**Vì sao đặt ở `defaultOptions` (opt-out) chứ không đặt từng query (opt-in):** hai kiểu hỏng khác
nhau về **độ ồn**. Quên opt-in ⇒ slice đó lặng lẽ không đồng bộ, **không có triệu chứng nhìn thấy
được**. Quên opt-out cho một query đắt ⇒ thấy ngay trong tab Network. Chọn kiểu hỏng ồn ào.
⇒ **Chú thích phải nói rõ:** query nào đắt thì **tự khai `refetchInterval: false`**.

**Không** đặt `refetchIntervalInBackground: true`. **Không** đụng `refetchOnWindowFocus` (mặc định
`true`, đang đúng).

### 2.7 Playwright — suite đầu tiên

**Kiến trúc đã chốt: test giao diện với `/api/**` giả lập ở tầng mạng (`page.route`).** Không backend,
không Postgres, không đăng nhập.

*Lý do, và giới hạn — đọc hết trước khi định làm khác:*
- 5 bug ở §2.1–2.4 đều là bug **thuần giao diện** (bị cắt, vùng bấm, chế độ lọc, chữ). Backend thật
  thêm **0** độ phủ cho chúng.
- Mọi route đều yêu cầu session (`require_session` ở tầng router) ⇒ e2e thật cần đăng nhập Google,
  bất khả trong CI. Ba đường đi: giả lập mạng ✅ · chèn thẳng một dòng `session` vào DB test (**cửa
  nâng cấp đã ghi nhận**, dùng khi có slice cần e2e thật, ví dụ `012`) · đường vòng xác thực trong
  code app ❌ **cấm** (§1.6).
- Suite hay flake là suite bị bỏ qua, và một suite bị bỏ qua tệ hơn không có suite.
- 🔒 **Giới hạn phải nói thẳng, không giấu:** fixture giả lập **sẽ âm thầm lạc hậu** khi hình dạng API
  đổi, và **không có gì đỏ lên**. Giảm thiểu bằng cách để **toàn bộ fixture trong đúng một module**
  (`frontend/e2e/fixtures/tasks.ts`), có chú thích trỏ tới `TaskRead` ở
  `backend/app/domain/tasks.py`. Ghi giới hạn này vào PR description.

**Phải làm:**
- `npm i -D @playwright/test`; `frontend/playwright.config.ts` với **hai project**: `mobile`
  (390×844) và `desktop` (1280×800).
- `webServer` chạy trên **bản build** (`npm run build` rồi `vite preview`), không chạy `vite dev` —
  gần với prod hơn và bắt được lỗi chỉ xuất hiện sau build.
- 🔒 **`serviceWorkers: 'block'` trong `playwright.config.ts`** (`use`/context options). `vite.config.ts`
  bật `VitePWA({ registerType: 'autoUpdate' })` ⇒ bản `preview` **có service worker thật** đang chạy
  trên trang. ⚠️ **Không khẳng định chắc chắn nó chặn `/api/*`** — cấu hình hiện tại chỉ khai
  `navigateFallbackDenylist: [/^\/auth\//, /^\/api\//]` (loại trừ **điều hướng trang**, không phải
  fetch/XHR) và **không có `runtimeCaching`** cho `/api/*`, nên có thể request API vẫn lọt thẳng ra
  mạng. Đặt `serviceWorkers: 'block'` **dù vậy** vì đây là khuyến nghị phòng thủ chuẩn khi test
  Playwright trên một trang có SW đang active — rủi ro không nằm ở việc SW này *xử lý* request thế
  nào, mà ở việc **có một SW active là đủ để một số bản Playwright/Chromium đọc lệch tầng CDP** so
  với khi không có SW. Rẻ để bật, không có lý do để bỏ qua dù chưa đo được app này có dính hay không.
- Giả lập `/api/me` (trả session hợp lệ) + `/api/tasks*` + các route ghi. Thiếu `/api/me` là app
  đứng ở màn đăng nhập và mọi test rơi vào một lỗi khó hiểu.
- Dữ liệu fixture theo **`docs/qa-framework.md` §5**: đủ bộ ác ý **và** ≥ 30 mục có mục nằm ngoài màn
  đầu, ≥ 3 mục trễ hạn nằm rải rác.
- Script `"e2e": "playwright test"` trong `frontend/package.json`.
- ⚠️ **`e2e/` phải được khai báo ở CẢ BA nơi**, không nơi nào tự suy ra được từ nơi khác:
  1. **vitest** — không có `vitest.config.ts`, vitest đọc `vite.config.ts` và include mặc định khớp
     `**/*.spec.ts` ⇒ nó sẽ **nhặt nhầm file e2e** và đỏ. Loại `e2e/` ra.
     🔒 `test.exclude` **thay thế** danh sách mặc định chứ không cộng dồn — phải trải
     `configDefaults.exclude` vào, nếu không vitest quay sang bới `node_modules/`.
     *(Test hiện có nằm ở `frontend/tests/` + `src/lib/uuidv7.test.ts` — đừng làm chúng biến mất.)*
  2. **tsconfig** — `tsconfig.test.json` có `include: ["tests"]`, không phủ `e2e/`.
  3. **eslint** — `eslint.config.js` áp `files: ['**/*.{ts,tsx}']` với `globalIgnores(['dist'])` và
     **chỉ có `globals.browser`**; file e2e chạy ở Node và đi qua plugin React.
  **Nghiệm thu là cả ba lệnh cùng xanh** (`npm run lint`, `npm test`, `npm run build`) — chọn cách vá
  nào là quyền của executor, nhưng đừng vá một nơi rồi tin hai nơi kia tự khớp.
- **Job CI mới trong `.github/workflows/ci.yml`**, tên **`Frontend e2e`** (`npx playwright install
  --with-deps chromium`).
  🔒 **Không đụng ruleset, không thêm nó vào required checks, không đổi tên 6 job đang có** (`Backend
  checks` · `Production dependency check` · `Repository hooks` · `Secret scan` · `Frontend checks` ·
  `Migration QA` — đọc `ci.yml`, đừng đoán số). Required
  check trỏ vào một job không tồn tại trên nhánh kia làm **mọi PR treo vĩnh viễn** — dự án này đã dính
  đúng lỗi đó (26/07). Việc bật required là của T1/chủ, sau, và chỉ trên `protect-develop`.

**Nội dung suite — viết theo acceptance, tự chọn selector từ bộ `data-testid` ở §2.5:**

| Kịch bản | Phải khẳng định |
|---|---|
| Smoke | Danh sách hiện đủ số thẻ từ fixture |
| §2.2 vùng bấm | Chạm khoảng trống trong thẻ ⇒ `task-detail-dialog` mở |
| §2.2 không lồng | Chạm `task-pin` ⇒ gọi PATCH, `task-detail-dialog` **không** mở |
| §2.2 trả focus | Mở từ thân thẻ rồi `Escape` ⇒ focus ở `task-title` của thẻ đó, không ở `body` |
| §2.3 banner | Bấm `overdue-banner` ⇒ danh sách chỉ còn task trễ; `filter-overdue` ở trạng thái active |
| §2.3 ghim không xuyên lọc | Task **ghim + đã xong** không hiện ở `filter-open` **và** không hiện ở `filter-overdue` |
| §2.3 ngõ cụt | Đang ở view `overdue`, hoàn thành task trễ cuối ⇒ tự về `filter-open` |
| §2.4 microcopy | Chuỗi *"Lưu xong ô tự xoá"* **không còn tồn tại** trong DOM |
| §3.B không tràn | Ở project `mobile`: `scrollWidth <= innerWidth` |
| Thêm nhanh | Gõ + gửi ⇒ POST đúng một lần, ô được dọn |

### 2.8 Test (ngoài Playwright)

Giữ vitest cho phần logic thuần. Nếu §2.3 sinh hàm chọn view (`isOverdue`, lọc theo view, luật tự
chuyển về `open`) thì **tách ra `task-ui.ts`** và test ở đó — đúng khuôn hiện có (`task-ui.ts` là
"pure state rules kept testable without a browser runtime").

🔒 **Ít nhất một test Playwright phải chứng minh biết đỏ, theo đúng quy trình đo được** (không phải một
câu văn trong PR): chọn một test (khuyến nghị: kịch bản §2.3 "ghim không xuyên lọc") → **tạm** đảo
ngược đúng một điều kiện nó canh trong code app (ví dụ trả `task.pinned ||` về như cũ) → chạy
`npx playwright test`, **dán log đỏ thật** vào PR kèm đúng lý do đỏ → hoàn nguyên code → chạy lại,
**dán log xanh**. Hai đoạn log là biên lai; thiếu một trong hai là chưa chứng minh được gì. *(Test
chạy ở trạng thái đúng rồi thấy xanh không chứng minh nó đang bảo vệ điều gì — cùng quy trình
`008m` đã dùng cho race-proof.)*

## 3. KHÔNG được làm

- **Không** thêm đường vòng xác thực cho test, dù chỉ ở `APP_ENV=local` (§1.6).
- **Không** nới `TaskFilter` trong `task-ui.ts` để nhét `'overdue'` (§1.3).
- **Không** gắn `tabIndex`/`role="button"` lên `Card` (§2.2).
- **Không** đổi tên 6 required check đang có (§2.7), **không** đụng ruleset, **không** thêm `Frontend e2e`
  vào required checks (§2.7).
- **Không** đụng backend: không route mới, không đổi schema, **không migration**.
- **Không** đụng đường mang dữ liệu ghim từ `localStorage` (`TasksScreen.tsx:581-655`) — nó là vá
  tình thế một lần của `008g`, đang chạy đúng.
- 🔒 **Không** viết đè toast Hoàn tác của `008f` (`remove.onSuccess`, `duration: 10000`). Thấy mình
  đang sửa dòng nào liên quan tới `toast` thì dừng lại. Trước khi commit: xoá một task vẫn phải hiện
  toast có nút **Hoàn tác** và nút đó vẫn chạy.
- 🔒 **Không** `await invalidateQueries` trong `onSuccess` (lỗi `008i`), **không** gỡ
  `AbortSignal.timeout` trong `api.ts`.
- **Không** thêm dark mode, không hardcode màu, không viết thẻ `<button>`/`<input>` thô
  (`ui-brief.md` §6).
- **Không** đổi hành vi thêm nhanh ở §2.4a — chỉ xoá dòng chữ mô tả nó.

## 4. Acceptance — kiểm chứng được

1. `npm run lint` · `npm test` · `npm run build` xanh.
2. `npx playwright test` xanh **cả hai project** (`mobile` + `desktop`), chạy cục bộ.
3. Ít nhất một test Playwright đã **chứng minh biết đỏ**, ghi rõ trong PR (§2.8).
4. `gh pr checks <PR>` xanh — **7 check** (6 cái cũ ở §2.7 **+ `Frontend e2e`**).
5. Đo và **chép số** vào PR:
   - `refetchInterval`: tab đang mở & focus ⇒ **~60 request/60s**; tab ẩn ⇒ **0 request/60s**.
   - 🔒 **Ở màn đăng nhập (chưa đăng nhập) ⇒ 0 request `/api/me` sau lượt 401 đầu tiên.** Đây là ca
     mà bản spec đầu bỏ sót (§2.6) — không đo thì không biết bản vá dạng hàm có ăn không.
   - Ở 390px: `document.documentElement.scrollWidth` **==** `window.innerWidth`.
   - Chiều cao đích chạm của `overdue-banner` (**≥ 44px**) — bằng `getBoundingClientRect()`.
6. Tooltip của **thẻ cuối cùng, sát đáy màn** hiện trọn vẹn — kèm ảnh chụp trong PR (soi ảnh trước
   khi dán: `AGENTS.md`). **Kèm một lượt kiểm tay trên iPhone thật**: chạm vào tiêu đề **không** để
   lại lớp nổi nào trên màn (§2.1).
7. Chuỗi `"Lưu xong ô tự xoá"` grep ra **0** trong `frontend/src/`.

## 5. Báo cáo

Biên lai, không phải lời khai: số PR + `gh pr checks` xanh + diff đọc được.
Tách rõ **đã chạy** / **chưa chạy** / **vì sao vẫn tin là đúng** (`agent-tasks/README.md` §Quy ước
BÁO CÁO). Cái gì sandbox chặn thì nói thẳng là chưa verify được, đừng suy luận rồi khẳng định.

Trong PR description phải có:
- giới hạn của fixture giả lập (§2.7) — để người làm `009` biết mình đang thừa hưởng gì;
- danh sách `data-testid` đã đặt — `009`–`012` chép từ đó;
- quyết định nào là judgment call của executor (mục nào spec không nói rõ) — **mọi quyết định L2 phải
  hiện trong PR description**.

## 6. Sau khi merge — việc của T1, không phải của executor

1. **Không có migration.** Đừng chạy `alembic upgrade` theo quán tính (`008f`/`008i` cũng vậy).
2. Verify SHA sống ở `/api/readyz` khớp `git rev-parse HEAD`.
3. 🔒 **Chạy một lượt QA theo `docs/qa-framework.md`** trên prod, giao **T3** (không phải T1 — luật
   chi phí 25/07). Đây là lần dùng thật đầu tiên của khung QA ⇒ báo cáo phải trả lời được **hai**
   câu: *app có mục nào đỏ không* **và** *khung QA có chỗ nào không dùng được / thiếu / mơ hồ không*.
   Kết quả ghi vào §9 nhật ký của file đó.
4. Cân nhắc bật `Frontend e2e` thành required check **trên `protect-develop`** (không phải
   `protect-main`) sau khi nó chạy ổn định vài PR.

## 7. Lượt phản biện trước khi giao executor

*(Mỗi spec đi qua **hai lượt khác câu hỏi**: T3 hỏi "spec sai ở đâu", T2 hỏi "spec không làm được ở
đâu" — `CLAUDE.md` 26/07. Kết quả fold vào §2/§3 ở trên, tóm tắt tại đây.)*

### Lượt 1 — T3 (`gemini-3.1-pro-high`), *"spec sai ở đâu"* — ✅ 2026-07-29

Đọc trực tiếp `TasksScreen.tsx` · `App.tsx` · `task-ui.ts` · `main.tsx` · `vite.config.ts` ·
`eslint.config.js` · `ci.yml`. **6 finding — 5 đúng (đã fold), 1 sai (đã bác).** T1 kiểm tay từng
mục bằng cách mở đúng file/dòng nó dẫn.

**Đã fold:**

1. **[CRITICAL] `refetchInterval` số trần vẫn chạy khi query lỗi** ⇒ tab bỏ quên ở màn đăng nhập gọi
   `/api/me` mỗi giây vĩnh viễn, mà route đó chạm DB ⇒ **đúng hình dạng sự cố Neon 22/07** mà chính
   spec vừa lập luận là nó không phải. → §2.6 đổi sang dạng hàm + `session` tự khai `false`. *Đây là
   finding đắt nhất lượt này: nó không bắt lỗi kỹ thuật, nó bắt **một lỗ trong lập luận biện minh**.*
2. **[MAJOR] Vế `task.pinned ||` ở `TasksScreen.tsx:687-691`** làm view "Trễ hạn" không bao giờ đúng
   được. → §2.3, và hoá ra đó là món nợ `ui-brief.md` §9(b) mà `008g` bỏ sót.
3. **[MAJOR] Service worker của `vite-plugin-pwa` chặn request trước `page.route`** ⇒ mock của
   Playwright bị đi vòng qua trên bản `preview`. → §2.7, `serviceWorkers: 'block'`.
4. **[MAJOR] Đường trả focus đứt khi mở Dialog từ thân thẻ** (`detailsReturnRef` chỉ được đặt bởi nút
   tiêu đề). → §2.2.
5. **[MAJOR] `closest()` một mình không chặn được thao tác bôi đen chữ** — spec đặt yêu cầu đúng
   nhưng kê cơ chế không đủ để đạt yêu cầu đó. → §2.2, thêm `window.getSelection()`.
   *(Finding #7 [MINOR] về eslint gộp vào đây: đã tổng quát hoá thành luật "khai `e2e/` ở cả ba nơi"
   thay vì đoán trước nơi nào sẽ đỏ.)*

**Đã bác — 1 mục:**

- **[MINOR] "Radix Tooltip sẽ bật lên và kẹt lại khi chạm trên iOS".** Radix `Tooltip` **lọc theo
  `pointerType`** và đóng ở `pointerdown` — nó *không* mở bằng chạm, nên không có gì kẹt lại. Không
  thêm code lọc `pointerType` như finding đề nghị. **Nhưng đây là hành vi thư viện chứ không phải
  thứ đã đo trong dự án này**, nên thay vì bác trắng, §2.1 + §4.6 giữ lại **một bước kiểm tay trên
  iPhone thật** — rẻ, và nếu T3 đúng thì nó lộ ra ở đúng chỗ đó.

### Lượt 2 — T2 (Codex, `gpt-5.6-sol`), rubric 6 trục đầy đủ, ưu tiên "thử thật" ở trục khả thi — ✅ 2026-07-29

Chạy sau khi lượt T3 đã fold, đúng thứ tự khung hạng-đôi (`devops-brief.md` §7.3.i). **4 finding —
2 fold thẳng, 1 fold có làm rõ, 1 ghi nhận vận hành.** Không có finding CRITICAL.

**Đã fold:**

1. **[MAJOR] Tooltip không khớp nghĩa đen `ui-brief.md:87`** — §5 (chốt trước 25/07) ghi tooltip phải
   *"chạm để mở, chạm ngoài để đóng"*; Radix Tooltip (§2.1) không mở bằng chạm. **Đúng họ lỗi quen
   thuộc của dự án**: `ui-brief.md` §9(a) (25/07) đã nới luật hover cho **đúng tooltip này** bằng lý
   lẽ "Dialog là đường thay thế đủ", nhưng không quay lại sửa câu chữ cụ thể ở §5 — hai quyết định
   đều đúng, khoá nhau bởi một câu chưa ai xoá. Đã thêm dòng chốt vào `ui-brief.md` §5 (dated note
   29/07) đóng vòng, không phải sửa code — 008e đã đúng theo cách đọc này từ đầu.
2. **[MAJOR] Đếm sai job CI: spec ghi "5 job đang có", `ci.yml` có 6** (`Backend checks` ·
   `Production dependency check` · `Repository hooks` · `Secret scan` · `Frontend checks` ·
   `Migration QA`). Lỗi đếm thuần, sửa cả 3 chỗ trong spec.

**Đã fold có làm rõ:**

3. **[MINOR, INFERRED] Lý do `serviceWorkers: 'block'` nêu chắc như đinh trong bản trước** — T2 đọc
   `vite.config.ts` thấy `navigateFallbackDenylist` chỉ loại trừ **điều hướng trang**, không phải
   fetch/XHR, và không có `runtimeCaching` cho `/api/*` ⇒ chưa có gì chứng minh SW này thật sự chặn
   API. **Vẫn giữ `serviceWorkers: 'block'`** — đây là khuyến nghị phòng thủ chuẩn khi test trên
   trang có SW active, không phụ thuộc SW đó có xử lý `/api/*` hay không — nhưng đã sửa câu chữ trong
   spec để không khẳng định quá tay điều chưa đo được.

**Ghi nhận vận hành, không fold vào spec:**

4. **[MINOR, axis 6] "Chứng minh biết đỏ" chỉ là văn xuôi PR, không có quy trình đo được** — đã sửa
   §2.8 thành quy trình cụ thể (đảo điều kiện → log đỏ → hoàn nguyên → log xanh, cả hai đoạn log dán
   vào PR), theo đúng khuôn `008m` đã dùng cho race-proof.

**🔒 Bài học vận hành — quan trọng hơn cả 4 finding:** T2 chạy lượt này **không có `-s
danger-full-access`**, dù mục đích cả lượt là "thử thật" ở trục #3. Kết quả: `npm install` chết
`ENOTCACHED` (sandbox chặn mạng), `vite preview`/`npm run build` chết `EPERM` khi spawn native binary
(Tailwind oxide). T2 tự báo đúng — *"đây là giới hạn môi trường, không phải bằng chứng spec sai"* —
và không suy diễn quá lời. Nhưng hệ quả là **trục #3 (khả thi) gần như không được kiểm chứng
empirically như rubric đòi**: cả 4 finding thật đều tới từ đọc code (trục #1/#2/#6), không phải từ
chạy thử. ⇒ **Sửa vào `devops-brief.md` §7.3.i**: giao T2 review theo hạng-đôi mà muốn trục #3 được
trả lời bằng "thử thật" thì phải **tường minh xin `-s danger-full-access`** trong prompt giao việc —
`write: true` của lớp forwarder không tự động kèm quyền mạng/spawn. Đây cũng là mảnh còn thiếu của
việc treo từ 27/07 ("probe cờ nào đúng cho lệnh không tương tác") — nay biết thêm: thiếu cờ thì lượt
review tự động **rơi về INFERRED trên trục #3**, không báo lỗi, chỉ báo "không thử được".

Kết luận: **agy/Codex là cố vấn, T1 kiểm tay từng mục** — cả 4 finding đã kiểm bằng cách đọc đúng
file/dòng nó dẫn. Spec sẵn sàng giao thi công thật.
