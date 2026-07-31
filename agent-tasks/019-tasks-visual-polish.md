# 019 — TasksScreen: sửa viền `border-transparent` bị đè + tooltip subtask kiểu D

> Executor: T2 Codex (CLI trực tiếp) · Bậc: Sol · Effort: high (đổi hành vi thị giác + click, cần review tay trên bản build thật) · **Skill gợi ý:** không cần · **MCP cần:** không cần (Playwright chạy bằng `npm`/Chromium cục bộ, không cần Docker/DB — xem §Việc của CHỦ)

Trạng thái: ⚠️ OPEN

## Bối cảnh

Chủ dựng một mockup so sánh (`docs/_local` — không phải nguồn thi công, chỉ để chốt quyết định) và phát hiện + chốt 3 việc trong một phiên tư vấn UI:

1. **Viền mỏng bám sát chữ ở tiêu đề task** ("test", "bonjour") — không phải taste, là bug CSS thật.
2. **"+ Thêm chi tiết" có viền lệch, như bị "cắt mất một góc"** — cùng họ bug với (1), cộng thêm một xung đột padding khác.
3. **Tooltip subtask** đang dùng `" · "` cho hai vai trò khác nhau (ngăn nhãn/nội dung VÀ ngăn từng mục) → chốt đổi sang **kiểu D**: eyebrow label + danh sách đánh số, cắt còn 3 mục đầu + nút "+N mục nữa" **bấm được** (không chỉ gạch dưới trang trí) dẫn thẳng ra dialog chi tiết task.

## Gốc lỗi (1)+(2) — đọc trước khi sửa

`frontend/src/index.css:161-163`:
```css
* {
  border-color: var(--border);
}
```
Luật này nằm **ngoài mọi `@layer`**. Theo spec CSS Cascade Layers, một luật không nằm trong layer nào luôn thắng luật nằm trong layer (kể cả layer `utilities` của Tailwind) — **bất kể specificity hay thứ tự viết trước/sau**. `@import "tailwindcss"` khai `@layer theme, base, components, utilities;`, nên mọi class Tailwind (kể cả `border-transparent` mà base class của `<Button>` — `frontend/src/components/ui/button.tsx:8` — dùng để tắt viền) đều nằm TRONG layer `utilities`, và vì vậy thua luật `*{border-color:...}` này. Kết quả: mọi `<Button>` ghost/link hiện màu `--border` (n-200) dù code nói rõ `border-transparent`.

Bẫy thứ hai riêng ở "+ Thêm chi tiết" (`TasksScreen.tsx:838`): class có điều kiện `has-data-[icon=inline-start]:pl-1.5` (từ size `sm` trong `buttonVariants`) có specificity cao hơn `px-0` viết sau trong className — nó thắng ở cạnh trái, không có class tương ứng ở cạnh phải, nên padding lệch, viền (vốn đã hiện ra vì bug ở trên) trông "cắt mất một góc".

## Việc phải làm

### 1. `frontend/src/index.css:161-163` — bọc trong `@layer base`

```css
@layer base {
  * {
    border-color: var(--border);
  }
}
```
Chỉ bọc đúng luật `* {}` này. `body {...}` ngay dưới nó (dòng 165-173) không xung đột với utility nào — bọc thêm cũng được, không bọc cũng không sao, tuỳ Codex, không phải trọng tâm của task.

**Không** đụng giá trị `--border` hay bất kỳ token màu nào khác trong file này.

### 2. `frontend/src/TasksScreen.tsx:290-329` — tooltip kiểu D

Thay khối `<TooltipContent>` hiện tại bằng bố cục: eyebrow label (uppercase, nhỏ, mờ) → danh sách đánh số tối đa 3 mục đầu → nếu còn dư thì một nút "+N mục nữa" bấm được, dẫn ra dialog chi tiết (dùng lại đúng `openDetails` đã có sẵn ở dòng 218 — cùng hàm mà tiêu đề đang dùng, không viết logic mới). Khối ghi chú giữ nguyên vị trí, đổi nhãn "Ghi chú · " thành eyebrow riêng dòng.

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
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="-mx-1.5 -my-1 mt-1 h-auto w-fit justify-start rounded px-1.5 py-1 text-xs font-semibold text-tooltip-foreground underline decoration-tooltip-foreground/50 underline-offset-2 hover:bg-tooltip-foreground/10 hover:text-tooltip-foreground hover:decoration-tooltip-foreground"
            onClick={openDetails}
          >
            +{task.items.length - 3} mục nữa
          </Button>
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

Lý do từng chi tiết, đừng đổi mà không hỏi:
- **`text-xs` (12px) cho eyebrow, không nhỏ hơn** — `ui-brief.md` §6 / `AGENTS.md` khoá cứng "chữ không nhỏ hơn 12px". Bản nháp ban đầu của chủ dùng cỡ nhỏ hơn cho eyebrow, **đã tự sửa lại đúng luật này** trước khi đưa vào spec — đừng làm nhỏ lại "cho gọn".
- **`underline` viết cứng trong className, không dùng `hover:underline` mặc định của `variant="link"`** — `AGENTS.md` cấm "tương tác chỉ sống bằng hover" (thiết bị chính của chủ là iPhone, không có hover). Gạch chân phải hiện SẴN, không đợi hover mới hiện.
- **`hover:bg-tooltip-foreground/10` chứ không phải `hover:bg-white/10`** — không hardcode màu; `--color-tooltip-foreground` đã có sẵn trong `@theme inline` (`index.css:120`) nên đây vẫn là token, chỉ thêm modifier opacity.
- **`hover:text-tooltip-foreground` bắt buộc phải override** — variant `ghost` gốc có `hover:text-foreground` (màu tối, dùng cho nền sáng); tooltip nền tối (`--tooltip` = n-900), không override thì hover làm chữ biến mất (tối trên tối).
- **`-mx-1.5 -my-1` + `px-1.5 py-1`** — mở rộng vùng bấm mà không đẩy lệch vị trí chữ so với dòng phía trên (đúng ý chủ: "cho vùng bấm xung quanh", không cần thêm chữ "xem đủ").
- **Copy "+N mục nữa" khác với "+N mục khác…" ở thân thẻ (`TasksScreen.tsx:434`)** — đây là CHỦ Ý, không phải chép nhầm: hai nút khác hành vi (thân thẻ mở rộng tại chỗ trong card; tooltip mở dialog chi tiết). Chữ đúng theo lời chủ chọn, giữ nguyên, đừng "thống nhất" hai chữ lại làm một.
- **Dùng lại `openDetails` (dòng 218), không viết hàm mới** — nó đã tự set `detailsReturnRef` + `setEditing(false)` + `setDetailsOpen(true)`, đúng hành vi cần, và giữ nguyên hành vi trả focus khi đóng dialog mà comment ở dòng 213-215 đã giải thích.
- `Button` đã được import ở đầu file (dùng ở nhiều chỗ khác trong cùng component) — không cần thêm import.

### Việc KHÔNG được làm
- Không viết `<button>` thô cho nút "+N mục nữa" — dùng `Button` từ `@/components/ui/button` (luật `AGENTS.md` dòng 12, "không thẻ thô").
- Không đổi cấu trúc/copy của phần mở rộng checklist trong THÂN THẺ (`visibleItems`/`hiddenItems`, dòng 208-209, 420-434) — đó là tính năng khác, đã đúng, không thuộc phạm vi task này.
- Không đổi `--border` hay bất kỳ token màu nào trong `index.css` ngoài việc bọc `@layer`.
- Không đổi `frontend/src/components/ui/button.tsx` — base class của Button đã đúng (`border-transparent`); lỗi nằm ở `index.css` đè nó, không phải ở Button.
- Không đụng `NoteForm.tsx`/`NotesScreen.tsx` hay bất kỳ file thuộc `009-note-slice` — hai việc độc lập, task này chạy trên nhánh riêng.

## Acceptance

1. `cd frontend && npm run lint` sạch, `npm run test` xanh, `npm run build` xanh.
2. Playwright (`npm run e2e`), không cần Docker/backend thật — toàn bộ mock qua `taskApi` fixture (`frontend/e2e/fixtures/tasks.ts`):
   - Test mới hoặc mở rộng test đã có ở `frontend/e2e/tasks.spec.ts` (gần test "last card tooltip is portalled..." dòng 132) cho **`task-012` ("Checklist nhiều mục", đã có sẵn 4 items trong fixture — không cần thêm fixture mới)**: hover/mở tooltip của task này, assert tooltip hiện đúng 3 mục đầu + nút có text `"+1 mục nữa"`.
   - Assert **click** vào nút đó mở dialog chi tiết task (`page.getByTestId('task-create-dialog')` dùng chung id với dialog sửa/tạo — kiểm bằng tiêu đề dialog hoặc field hiển thị đúng task-012, xem cách các test khác trong file này assert dialog đã mở, ví dụ test "clicking card whitespace opens the detail dialog" dòng 26).
   - Assert computed style: `getComputedStyle(titleButton).borderColor` là `transparent`/`rgba(0, 0, 0, 0)` cho một tiêu đề bất kỳ (ví dụ task-001) — chứng minh bug (1) đã hết, không chỉ "nhìn ok".
3. Screenshot tay (desktop + mobile project, giống cách test dòng 151 đã lưu `output/playwright/*.png`) xác nhận bằng mắt: tiêu đề không còn viền, "+ Thêm chi tiết" không còn hộp lệch, tooltip task-012 đúng bố cục kiểu D.
4. PR mô tả rõ 3 mục đã sửa, dẫn đúng dòng file đã đổi, và trạng thái `gh pr checks <PR>` xanh trước khi báo xong (biên lai, không phải lời khai).

## Việc của CHỦ trước khi chạy task

Không có — task này không chạm DB/migration/Docker. `npm run e2e` tự dựng build (`vite preview`) và mock toàn bộ API qua fixture, không cần backend thật chạy nền.
