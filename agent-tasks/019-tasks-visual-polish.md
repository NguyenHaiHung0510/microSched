# 019 — TasksScreen: sửa padding lệch "+ Thêm chi tiết" + tooltip subtask kiểu D (tĩnh)

> Executor: T2 Codex (CLI trực tiếp) · Bậc: Sol · Effort: medium (thuần CSS/JSX tĩnh, không còn logic click mới) · **Skill gợi ý:** không cần · **MCP cần:** không cần (Playwright chạy bằng `npm`/Chromium cục bộ, không cần Docker/DB — xem §Việc của CHỦ)

Trạng thái: ✅ DONE 2026-08-01 — PR #75 merge (`ca49c3d`), live production xác nhận qua `/api/readyz` (`commit` khớp `e7c7845`, HEAD của `develop` ngay sau merge). Thi công qua Codex (`gpt-5.6-sol`, high, full-access) trong worktree cô lập (`../microsched-wt-019`) — chủ ý tách khỏi cây làm việc chính vì có phiên Claude/Codex khác chạy song song trong cùng thư mục lúc đó, không collision. T1 tự đọc diff (đúng 3 file: `TasksScreen.tsx`, `frontend/e2e/tasks.spec.ts`, `agent-tasks/README.md`, không lệch phạm vi) + verify độc lập `gh pr checks 75` (10/10 xanh) trước khi merge.

## Bối cảnh

Chủ dựng một mockup so sánh (`docs/_local` — không phải nguồn thi công, chỉ để chốt quyết định) và phát hiện + chốt 3 việc trong một phiên tư vấn UI. Bản spec đầu có sai sót, đã sửa sau khi T3 (`gemini-3.1-pro-high`, `adversarial_review`) review — đọc kỹ hai mục dưới trước khi thi công, đừng làm theo bản trực giác ban đầu:

1. ~~**Viền mỏng bám sát chữ ở tiêu đề task**~~ — **ĐÃ ĐÓNG, không thuộc phạm vi task này nữa.** Gốc lỗi đúng là `index.css` có `* { border-color: var(--border); }` nằm ngoài `@layer`, thua layer `utilities` của Tailwind theo đúng spec CSS Cascade Layers — chẩn đoán này đúng, nhưng **commit `e439b36` (31/07, "fix(016): sửa viền cổng riêng tư trượt non-text contrast") đã bọc `@layer base` từ trước**, qua một luồng điều tra khác (nợ non-text-contrast của `016`) chạy song song lúc spec này đang được viết. Kiểm lại `frontend/src/index.css` quanh dòng 160-168 trước khi làm gì — nếu thấy `@layer base { * { border-color: var(--border); } }` đã có sẵn thì **không làm gì thêm ở đây**, mục này chỉ giữ lại làm hồ sơ.
2. **"+ Thêm chi tiết" có padding lệch** — vẫn còn thật, độc lập với mục 1 (T3 xác nhận đúng 100%). Không còn viền để "trông thấy" lệch nữa (viền đã hết nhờ mục 1 tự đóng), nhưng padding vẫn lệch thật, icon+chữ bị đẩy sang phải ~6px so với đúng — vẫn đáng sửa.
3. **Tooltip subtask** đang dùng `" · "` cho hai vai trò khác nhau (ngăn nhãn/nội dung VÀ ngăn từng mục) → đổi sang **kiểu D**: eyebrow label + danh sách đánh số, cắt còn 3 mục đầu + dòng "… và N mục nữa". **Không bấm được** — xem lý do ở §3 dưới, đây là điểm bản duyệt ban đầu của chủ đã đổi sau review.

## Gốc lỗi mục 2 — đọc trước khi sửa

Ở "+ Thêm chi tiết" (`TasksScreen.tsx:838`): class có điều kiện `has-data-[icon=inline-start]:pl-1.5` (từ size `sm` trong `buttonVariants`, `button.tsx`) có specificity CSS cao hơn `px-0` viết sau trong className của chính nút này — nó thắng ở cạnh trái, không có class tương ứng ở cạnh phải (`has-data-[icon=inline-start]:pr-1.5` không áp dụng vì icon là `inline-start`, không phải `inline-end`), nên padding-left ra 6px trong khi padding-right ra 0px.

## Việc phải làm

### 1. `frontend/src/TasksScreen.tsx:290-329` — tooltip kiểu D, TĨNH (không bấm được)

**⚠️ Đảo so với bản duyệt đầu tiên của chủ.** Bản đầu định làm dòng "+N mục nữa" bấm được, dẫn ra dialog chi tiết. T3 (`adversarial_review`, `gemini-3.1-pro-high`) chỉ ra: `TooltipContent` là Radix `Tooltip` (`frontend/src/components/ui/tooltip.tsx`) — loại tooltip này tự đóng ngay khi con trỏ rời khỏi trigger, và theo WAI-ARIA `role="tooltip"` không được chứa phần tử focusable. Nút bấm bên trong sẽ **không bao giờ đăng ký được click** (tooltip biến mất trước khi sự kiện tới), và trên iPhone (thiết bị chính của chủ) vốn không có hover thật thì tooltip này còn khó mở hơn. Hỏi thêm T3 hướng thay (đổi sang `HoverCard`) thì vẫn vướng đúng vấn đề — `HoverCard` cũng là cơ chế hover, không giải quyết gì cho cảm ứng. Vì tiêu đề task đã có sẵn đường mở dialog chi tiết (`openDetails`, dòng 218) — bấm cả thẻ hoặc tiêu đề là ra đủ checklist — tooltip **không cần** làm thêm việc đó nữa: giữ nó tĩnh, trung thực, không hứa hẹn một affordance không hoạt động được.

Thay khối `<TooltipContent>` hiện tại bằng bố cục: eyebrow label (uppercase, nhỏ, mờ) → danh sách đánh số tối đa 3 mục đầu → nếu còn dư thì một dòng chữ tĩnh "… và N mục nữa". Khối ghi chú giữ nguyên vị trí, đổi nhãn "Ghi chú · " thành eyebrow riêng dòng.

```tsx
{task.body_md || task.items.length > 0 ? (
  <TooltipContent>
    {task.items.length > 0 ? (
      <div>
        <span className="block text-xs font-extrabold tracking-wide uppercase opacity-70">
          Checklist ({task.items.length})
        </span>
        <ol className="mt-1 space-y-0.5">
          {task.items.slice(0, 3).map((item, index) => (
            <li key={item.id} className="flex gap-1.5">
              <span className="opacity-60">{index + 1}.</span>
              {item.content}
            </li>
          ))}
        </ol>
        {task.items.length > 3 ? (
          <p className="mt-1 text-xs opacity-70 italic">
            … và {task.items.length - 3} mục nữa
          </p>
        ) : null}
      </div>
    ) : null}
    {task.body_md ? (
      <div className={task.items.length > 0 ? 'mt-2' : ''}>
        <span className="block text-xs font-extrabold tracking-wide uppercase opacity-70">
          Ghi chú
        </span>
        {task.body_md}
      </div>
    ) : null}
  </TooltipContent>
) : null}
```

Lý do từng chi tiết:
- **`text-xs` (12px) cho eyebrow và dòng "… và N mục nữa", không nhỏ hơn** — `ui-brief.md` §6 / `AGENTS.md` khoá cứng "chữ không nhỏ hơn 12px".
- **Không có phần tử focusable/bấm được nào trong `TooltipContent`** — đây là ràng buộc cứng, không phải gợi ý; xem lý do ở trên. Nếu sau này muốn "+N nữa" bấm được thật, đó là một quyết định UX khác (đổi cơ chế mở, không chỉ đổi copy) — không tự làm trong task này.
- **Copy "… và N mục nữa" khác với "+N mục khác…" ở thân thẻ (`TasksScreen.tsx:434`)** — CHỦ Ý, không phải chép nhầm: hai chữ ở hai chỗ khác nhau, một là nhãn tĩnh trong tooltip, một là nút bấm mở rộng thật trong thân thẻ. Đừng "thống nhất" lại làm một.

### 2. `frontend/src/TasksScreen.tsx:838` — sửa padding lệch "+ Thêm chi tiết"

Nút hiện tại:
```tsx
<Button className="h-auto px-0 py-1 text-xs" size="sm" variant="link">
  <Plus data-icon="inline-start" />
  Thêm chi tiết
</Button>
```
`size="sm"` áp `has-data-[icon=inline-start]:pl-1.5` (xem `button.tsx`), thắng `px-0` ở cạnh trái vì specificity cao hơn, không có gì thắng ở cạnh phải → padding-left 6px, padding-right 0px, icon+chữ lệch phải so với các phần tử cùng hàng. Sửa bằng cách khoá cứng cả hai cạnh về 0, không dựa vào `px-0` một mình:
```tsx
<Button className="h-auto py-1 pl-0! pr-0! text-xs" size="sm" variant="link">
  <Plus data-icon="inline-start" />
  Thêm chi tiết
</Button>
```
Dùng modifier `!` (important) của Tailwind v4 để `pl-0`/`pr-0` thắng chắc chắn cả hai cạnh của điều kiện `has-data-*`, không phụ thuộc thứ tự các class được tailwind-merge nối lại. Nếu Codex thấy cách khác gọn hơn cho cùng kết quả (padding trái = phải = 0 bất kể có icon hay không) thì được, miễn acceptance §3 dưới đo đúng.

### Việc KHÔNG được làm
- Không viết `<button>` thô — giữ nguyên `Button` từ `@/components/ui/button` cho cả hai chỗ sửa.
- Không thêm bất kỳ `onClick`/phần tử tương tác nào vào bên trong `TooltipContent` — xem lý do ở mục 1.
- Không đổi cấu trúc/copy của phần mở rộng checklist trong THÂN THẺ (`visibleItems`/`hiddenItems`, dòng 208-209, 420-434) — đó là tính năng khác, đã đúng, không thuộc phạm vi task này.
- Không đổi gì trong `frontend/src/index.css` — bug viền (mục 1 cũ) đã đóng ở `e439b36`, không phải việc của task này.
- Không đổi `frontend/src/components/ui/button.tsx` — sửa tại chỗ dùng (`TasksScreen.tsx`), không đổi hợp đồng chung của component dùng ở nhiều nơi khác.
- Không đụng `NoteForm.tsx`/`NotesScreen.tsx` hay bất kỳ file thuộc `009-note-slice` — hai việc độc lập, task này chạy trên nhánh riêng.

## Acceptance

1. `cd frontend && npm run lint` sạch, `npm run test` xanh, `npm run build` xanh.
2. Playwright (`npm run e2e`), không cần Docker/backend thật — toàn bộ mock qua `taskApi` fixture (`frontend/e2e/fixtures/tasks.ts`):
   - Test mới hoặc mở rộng test đã có ở `frontend/e2e/tasks.spec.ts` (gần test "last card tooltip is portalled..." dòng 132) cho **`task-012` ("Checklist nhiều mục", đã có sẵn 4 items trong fixture — không cần thêm fixture mới)**: hover mở tooltip, assert hiện đúng 3 mục đầu (thứ tự 1./2./3.) và dòng chữ chứa `"và 1 mục nữa"`. Assert tooltip **không** chứa phần tử `button`/`[role="button"]` nào (đúng ràng buộc "tĩnh").
   - Assert bounding box của nút "+ Thêm chi tiết" (`page.getByRole('button', { name: /Thêm chi tiết/ })`) có `paddingLeft === paddingRight` qua `getComputedStyle` (hoặc so khoảng cách từ icon tới mép trái ≈ khoảng cách từ chữ cuối tới mép phải).
3. Screenshot tay (desktop + mobile project, giống cách test dòng 151 đã lưu `output/playwright/*.png`) xác nhận bằng mắt: "+ Thêm chi tiết" không còn lệch, tooltip task-012 đúng bố cục kiểu D tĩnh.
4. PR mô tả rõ 2 mục đã sửa (không phải 3 — mục viền đã đóng từ trước), dẫn đúng dòng file đã đổi, và trạng thái `gh pr checks <PR>` xanh trước khi báo xong (biên lai, không phải lời khai).

## Việc của CHỦ trước khi chạy task

Không có — task này không chạm DB/migration/Docker. `npm run e2e` tự dựng build (`vite preview`) và mock toàn bộ API qua fixture, không cần backend thật chạy nền.
