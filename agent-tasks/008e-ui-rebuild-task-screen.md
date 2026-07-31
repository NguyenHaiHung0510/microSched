# 008e — dựng bộ component + làm lại màn Task theo hệ thiết kế

> **Executor: Codex (T2).** Nhánh `feat/008e-ui-rebuild` → PR nhỏ vào `develop`.
> Spec tự-chứa. Đọc `CLAUDE.md` + `AGENTS.md` trước, và **`docs/ui-brief.md` là luật của task này**.

## 0. Bối cảnh — vì sao có task này

008 Phase 1 đi trọn tầng dữ liệu và **chạy đúng**: store, cửa đọc, 7 endpoint, test hợp đồng. Task này **không đụng gì vào phần đó**. Chỉ giao diện bị làm lại.

Giao diện hỏng không phải vì người thi công kém, mà vì **repo lúc đó không có gì để bám**: `index.css` chỉ có 10 token xám, `components.json` khai `baseColor: neutral`, font là mặc định Vite, và toàn dự án có đúng **một** component shadcn. Nay ba thứ đó đã có: token thật, `docs/ui-brief.md`, và luật trong `AGENTS.md`.

## 1. Đã KHOÁ — chép ra code, không mở lại

Đọc `docs/ui-brief.md` toàn bộ. Tóm phần bắt buộc:

- **Hướng B "hồng ấm"**, light mode. Không tự thêm dark mode.
- **Token đã dựng xong** ở `frontend/src/index.css`. Được phép **thêm** token mà `shadcn add` đòi (ví dụ biến animation, `--sidebar-*`) — đó là điều kiện để CLI chạy. **Không được sửa hay xoá** token màu/bo góc/bóng đã có, và **không tự chế màu mới**: cần một sắc thái chưa có thì dừng và hỏi. Mọi token thêm vào phải liệt kê trong PR description.
- 🔒 `--rose-500` là màu nhận diện nhưng **KHÔNG được mang chữ** (3,07:1). Mọi nền có chữ trắng dùng `--primary` (= rose-700, 5,78:1). Đừng "sửa cho tươi hơn" — con số đó là lý do nó tồn tại.
- 🔒 **Không dùng `--n-400` cho chữ** (2,54:1). Chữ mờ nhất là `--muted-foreground`.
- 🔒 **Không hardcode màu.** Không `text-neutral-500`, không `#hex`, không `oklch(...)` trong component. Mọi màu qua class Tailwind ánh xạ token (`bg-primary`, `text-muted-foreground`, `bg-brand-50`, `text-bad`, …).
- 🔒 **Không đặt chiều cao cứng cho thẻ.** Thẻ giãn theo nội dung.
- 🔒 **Chữ không nhỏ hơn 12px.**
- 🔒 **Không có tương tác nào chỉ sống bằng `hover`** — thiết bị chính của chủ là iPhone.

🎯 **Bản dựng tham chiếu — mở nó ra trước khi viết dòng code đầu tiên.** `docs/_local/ui-b-refined.html` là trang HTML chạy được mà **chủ đã bấm chọn**; nó nằm trên đĩa cùng thư mục làm việc của bạn (gitignore, nên không có trong repo công khai). Nó là *đích thị giác*: mở ra, xem, rồi chép lại bố cục / khoảng cách / hình khối sang React. Đừng đọc §5 rồi tự tưởng tượng ra một giao diện khác — chỗ nào `ui-brief.md` và bản dựng nói khác nhau thì **`ui-brief.md` thắng về luật (màu, tương phản, cỡ chữ), bản dựng thắng về hình**.

Bạn có sẵn skill giúp việc này trong kho của mình: `product-design/url-to-code` (dựng lại giao diện từ một trang có thật) và `product-design/design-qa` (tự soát trước khi báo xong). Dùng chúng.

**Kích thước chạm:** thang `radix-nova` nhỏ (nút mặc định 32px). Hành động chính dùng `size="lg"`, nút icon dùng `icon-lg`. **Không bỏ `text-base` khỏi `Input`** — chữ dưới 16px làm Safari iOS tự phóng to trang khi chạm vào ô nhập.

## 2. Phải làm

### 2.1 Bộ component shadcn — ✅ T1 ĐÃ DỰNG XONG, ĐỪNG LÀM LẠI
`frontend/src/components/ui/` đã có đủ **9 component**: `badge` · `button` · `card` · `checkbox` · `dialog` · `input` · `select` · `sonner` · `textarea`. `lucide-react` đã cài. Token `--radius` đã thêm vào `index.css`. `next-themes` đã bị gỡ có chủ ý (`ui-brief.md` §8c).

**Không chạy `npx shadcn@latest add` trong task này.** Nếu thật sự thiếu một component nào → **dừng và hỏi**, đừng tự thêm: CLI có 4 cái bẫy đã ghi ở `ui-brief.md` §8 và cái nào cũng báo thành công khi hỏng.

Việc của bạn bắt đầu ở 2.2. Chỉ dùng lại những component trên; **không sửa file nào trong `components/ui/`** trừ khi có lý do nêu rõ trong PR.

### 2.2 Làm lại màn Task
Sửa `App.tsx`, `TasksScreen.tsx`, `TaskForm.tsx` theo `ui-brief.md`. **Không đổi `api.ts`, `task-ui.ts`, hay bất kỳ hợp đồng API nào** — chỉ tầng trình bày.

Sáu cơ chế bắt buộc có (`ui-brief.md` §5):

| Cơ chế | Yêu cầu kiểm được |
|---|---|
| Quick-add + Enter | Submit xong ô **tự xoá và giữ focus** — gõ liên tục không cần chạm chuột |
| Ghim | Thẻ ghim nổi lên **đầu danh sách**, bất chấp bộ lọc đang chọn |
| Gấp tràn | Quá 3 mục checklist thì gấp thành `+N mục khác…`, bấm để mở |
| Tick trên thẻ | Tick được ngay trên thẻ, có gạch ngang + đếm `X/Y mục nhỏ` |
| Chi tiết dạng popup | **Chạm để mở, chạm ngoài để đóng.** Hover chỉ là bổ sung cho desktop |
| Banner trễ hạn | Ghim trên cùng, dùng `bg-bad-bg text-bad` |

⚠️ **Ghim chưa có trong data model** — `task` không có cột `pinned`. **Task này KHÔNG thêm migration.** Dựng UI ghim ở dạng trạng thái client (`localStorage`) và **ghi rõ trong PR description** rằng đây là tạm thời, cần một slice riêng để đưa xuống DB. Nếu thấy cách nào khác gọn hơn thì **dừng và hỏi**, đừng tự đổi schema.

### 2.3 Vệ sinh
- Xoá 2 thẻ `<button>` thô còn lại trong `TaskForm.tsx` — thay bằng `Button`.
- Mọi `<input>`/`<select>` thô thay bằng component tương ứng.
- Không còn chuỗi class màu cứng nào trong 3 file UI.

## 3. KHÔNG được làm

- **Không** sửa `components.json`, `vite.config.ts`, `index.html`, `tsconfig*.json`. **`index.css` giờ đã đóng** — T1 đã thêm nốt token cần thiết ở nhịp scaffold; cần một sắc thái chưa có thì **dừng và hỏi**, đừng tự chế.
- **Không** đụng `backend/`, migration, hay bất kỳ file test backend nào.
- **Không** đổi `api.ts` / `task-ui.ts` / hình dạng request-response.
- **Không** thêm dark mode.
- **Không** thêm dependency nào cả — bộ cần dùng đã cài đủ. Muốn thêm → dừng, hỏi.
- **Không** cài lại `next-themes` (đã gỡ có chủ ý) và **không** chạy `npx shadcn@latest add` (xem 2.1).
- **Không** đổi tên required check trong CI.
- **Không** tự thêm cột / migration cho `pinned` (xem 2.2).

## 4. Acceptance — kiểm chứng được

1. `npm run lint` sạch.
2. `npm run build` xanh.
3. `npm test` — **9/9 phải xanh.**

   🔒 **Đã có một va chạm biết trước, T1 xử sẵn — làm đúng như dưới đây, đừng tự chế cách khác.** `frontend/tests/task-form.test.tsx` khẳng định trên HTML thô, mà component shadcn render ra HTML khác kiểu thẻ thô. **Chỉ 2 khẳng định sau được phép đổi**, và phải đổi sang thứ *kiểm cùng một hành vi*, không được đổi thành thứ dễ hơn:

   | Khẳng định cũ | Được đổi thành | Vì sao |
   |---|---|---|
   | `assert.match(html, /checked=""/)` | kiểm ô đang ở trạng thái đã tick — ví dụ `data-state="checked"` | Checkbox của Radix là `<button role="checkbox">`, không có thuộc tính `checked` |
   | `assert.match(html, /P1 — cao/)` | kiểm nhãn ưu tiên đang hiển thị trên trigger của Select | Select của Radix để danh sách lựa chọn trong portal, render tĩnh không thấy option |

   **Bảy khẳng định còn lại bất khả xâm phạm** — kể cả `/disabled=""/` và `/Đang lưu…/` (chốt chặn double-submit) và `/Huỷ/`. Test nào ngoài `task-form.test.tsx` mà đỏ thì đó là **bug của bạn**, không phải va chạm: dừng và sửa code, đừng sửa test.
4. Ba lệnh kiểm bằng máy, cả ba **phải ra rỗng**:
   - `grep -rE "text-neutral-|bg-neutral-|text-gray-|bg-gray-|text-slate-|bg-slate-|oklch\(" frontend/src --include=*.tsx` — luật "không hardcode màu".
     *(Cố ý không bắt `#hex`: thuộc tính `fill`/`stroke` của SVG nội tuyến có thể cần hex hợp lệ, chặn cứng sẽ đẩy người làm đi đường vòng. Hex trong `className` vẫn bị cấm bởi §1 — T1 đọc diff để kiểm.)*
   - `grep -rn "next-themes\|useTheme" frontend/src` — light-only, xem `ui-brief.md` §8c.
   - `grep -rn "<button\|<input\|<select\|<textarea" frontend/src --include=*.tsx | grep -v "components/ui/"` — không còn thẻ thô ngoài thư viện component.
5. PR mở vào `develop`, `gh pr checks <PR>` **xanh toàn bộ** trước khi báo xong.

## 5. Báo cáo

Theo luật biên lai ở `AGENTS.md`: **số PR + `gh pr checks` xanh + diff đọc được**. Lời khai "đã xong" không đóng được task.

Trong PR description ghi rõ:
- **Cách ghim đang lưu ở đâu** và vì sao đó là tạm thời (2.2).
- Hai khẳng định test đã đổi thành gì (4.3).
- Bất cứ chỗ nào bạn phải chọn giữa hai cách và đã tự chọn.

## 6. QA sau khi có PR — dành cho T3, không phải executor

Executor **không** tự làm mục này. T1 giao riêng sau khi PR mở. Yêu cầu chung: **để lại số đo, không để lại cảm tưởng.** "Trông ổn" không phải kết quả QA.

| Trục | Phải trả về |
|---|---|
| **6 cơ chế** (§2.2) | Từng cơ chế: làm được / không, kèm ảnh chụp. Quick-add phải kiểm *ô có tự xoá và giữ focus* — đây là cái dễ báo đạt nhất mà thực tế hỏng |
| **iPhone** (390×844) | Kích thước thật của mọi đích chạm: **< 24px là đỏ**, < 40px là cảnh báo. Và: có tương tác nào chỉ mở được bằng hover không? |
| **Tương phản** | Bảng số cho mọi cặp màu mới **và cho viền focus** (non-text, WCAG 1.4.11, ngưỡng 3:1) — đúng chỗ đã sót ở PR #19 |
| **Console + network** | Cảnh báo React, key trùng, request lặp/thừa/đỏ. Nhóm lỗi này không bao giờ làm CI đỏ và mắt không thấy |
| **PWA offline** | Tắt mạng, mở lại: font còn giữ được không. Đọc `dist/sw.js`, **đếm `url:"…"` và so tổng với số địa chỉ khác nhau** — lệch nhau mới là precache trùng |
| **Bàn phím** | Tab đi hết màn hình, thứ tự hợp lý, focus luôn nhìn thấy được |

Số nào còn giá trị lâu dài (cỡ bundle, các cặp tương phản, kích thước đích chạm) thì T1 gấp vào `docs/ui-brief.md` làm mốc nền cho 009–012 so sánh.

⚠️ **T3 là cố vấn, không phải biên lai.** T1 kiểm tay từng mục nó nêu — ở PR #19 nó đúng 11/13, hai mục sai vì **suy luận thay vì đo**.
