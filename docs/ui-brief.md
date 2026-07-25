# UI brief — hệ thiết kế microSched

> **Trạng thái: ✅ CHỐT 2026-07-25.** Đây là *khuôn*: 008 (task) dựng theo nó, và 009–012 (note, lịch, tracker) **chép lại nó**. Sai ở đây là sai cả loạt, nên mọi thay đổi phải thêm dated note chứ đừng viết đè.
>
> File này tự đủ, đọc không cần ngữ cảnh hội thoại. Bản kiểm kê app cũ nằm ở `docs/_local/` (**gitignore, chỉ local** — nó mô tả dữ liệu thật đang dùng).

## 1. Vì sao có file này

Slice task của 008 đi trọn tầng và chạy đúng, nhưng giao diện thì hỏng — và nguyên nhân **không phải người thi công kém**:

| Đo được | Hệ quả |
|---|---|
| `index.css` khai 11 token, **10 token là xám** (`oklch(… 0 0)`) | Không có màu nào để dùng |
| `components.json` khai `baseColor: "neutral"` | Mọi component sinh thêm cũng sẽ xám |
| `font-family: Arial, Helvetica` | Mặc định template Vite, chưa ai chọn |
| Toàn dự án có **1** component shadcn (`button`) | Mọi input/thẻ/chip phải viết tay, lặp lại |
| `iconLibrary: "lucide"` nhưng **không cài `lucide-react`** | Không có icon ⇒ nút phải dùng chữ "Sửa"/"Xoá" |

**Bài học mang sang 009–012: repo trống thiết kế thì executor ra sản phẩm trống thiết kế.** Nó chỉ bắt chước được cái đang có — đo thật ở 008: Codex tự dùng `Button` của shadcn vì `App.tsx` đã dùng, *không* vì ai bảo nó.

## 2. Hướng thiết kế ✅ CHỐT — "B · hồng ấm"

Bốn hướng được dựng thành trang chạy được cho chủ chọn tận mắt (`docs/_local/ui-drafts.html`). Chốt **B**.

| | Hướng | Kết quả |
|---|---|---|
| A | Hồng tinh chỉnh — giữ `#D81B60` nguyên bản | loại |
| **B** | **Hồng ấm `#E8698C`, bo góc lớn, bóng mềm, không viền** | **✅ CHỌN** |
| C | Sổ tay kẻ dòng — nền giấy, dòng kẻ làm cấu trúc | loại |
| D | Thời khoá biểu — lưới chặt, số đều cột, màu chỉ mang nghĩa | loại |

**"Copy y nguyên app cũ" đã bị loại bằng số đo, không phải bằng gu:**
- Cửa sổ cứng `1400×900`, sidebar cứng `400px` / `220px`, và `breakpoint / media query` = **không tồn tại** ⇒ app cũ không có khái niệm responsive, không đi xuống iPhone được.
- Cỡ chữ chạm đáy **8–11px** — không đọc nổi trên cảm ứng.
- `font_family` xuất hiện **0 lần** trong 4.074 dòng UI ⇒ font hiện tại là tai nạn, copy nó là đóng khung tai nạn thành quyết định.

Cái **được** giữ là *danh tính* (màu hồng — quyết định thật của chủ) và *cơ chế* (§5), không phải hình khối.

## 3. Font ✅ CHỐT — Nunito Variable

**Chọn Nunito**, chủ chọn bằng mắt trên dải chữ 11→21px có dấu dày (`docs/_local/ui-b-refined.html`).

Tiêu chí là **kỹ thuật, không phải gu**: rủi ro lớn nhất của font tiếng Việt ở cỡ nhỏ là **dấu chồng lên nhau** (`ế · ữ · ộ · ằ`, và chữ hoa có dấu như `ĐỀ CƯƠNG` đè lên dòng trên). Ứng viên còn lại là Be Vietnam Pro; đã dựng nút đổi qua lại và **chứng minh ba font render khác nhau thật** (cùng một chuỗi ra 215,6 / 225,7 / 212 px) trước khi để chủ chọn — nếu không sẽ là chọn giữa ba bản dự phòng giống hệt nhau.

**Cách giao font — không được đổi tuỳ tiện:**
- Tự host qua `@fontsource-variable/nunito`, **không** gọi Google Fonts: đây là PWA, font qua CDN thì mở offline sẽ rơi về font hệ thống.
- Family thật là **`"Nunito Variable"`** (không phải `"Nunito"`). Là font biến thiên: **một file phủ trọn weight 200–1000**, nhưng **tách theo bộ ký tự** — mỗi subset là một `.woff2` riêng, không phải một file duy nhất cho cả font.
- Mỗi subset có `unicode-range` riêng ⇒ trình duyệt chỉ tải `latin` + `vietnamese`.
- Phải import **cả `wght-italic.css`**; thiếu nó thì `<em>`/italic ra chữ nghiêng **giả** do trình duyệt tự xiên.
- ⚠️ **`globPatterns` mặc định của `vite-plugin-pwa` KHÔNG gồm `woff2`** ⇒ font không vào precache ⇒ offline vẫn mất font. Đã vá ở `vite.config.ts`, và cố ý **không** kê `svg`/`webmanifest` vì plugin đã tự thêm (kê lại là precache trùng — đã đo 10 mục / 9 địa chỉ). Kết quả cuối: **12 mục / 12 địa chỉ** — không mục nào trùng, và không có cyrillic.
> 📝 **Đo lại 2026-07-25 (008e):** chỗ này từng ghi *"9 mục / 9 địa chỉ, có 3 subset font"*. Số **3 subset** đúng (`latin`, `latin-ext`, `vietnamese`) nhưng mỗi subset có **hai** file — nghiêng và không nghiêng — nên là 6 file font. Số 9 là bản đo **trước** khi thêm `wght-italic.css`, chép vào brief sau đó mà không đo lại. Cách kiểm dùng lại được: đọc `dist/sw.js`, đếm `url:"…"` rồi so **tổng với số địa chỉ khác nhau**; hai số lệch nhau mới là precache trùng, còn tổng tăng chỉ có nghĩa là có thêm file thật.

## 4. Màu ✅ CHỐT

Token đầy đủ ở `frontend/src/index.css`. Ba quyết định có lý do, đừng đảo mà không đọc:

**(a) Trung tính ngả ấm, không xám lạnh.** Nền `#FAF7F7` có chút hồng rất nhẹ. Xám lạnh đặt cạnh hồng ấm sẽ trông bẩn.

**(b) Ba màu ngữ nghĩa đều bị hạ độ tươi.** Xanh/cam/đỏ nguyên bản sẽ cãi nhau với hồng và làm mất khả năng phân biệt cái gì đang quan trọng.

**(c) 🔒 Luật quan trọng nhất — `--rose-500` là màu nhận diện nhưng KHÔNG được mang chữ.** Đo WCAG trên chính bản đã duyệt bằng mắt, bốn chỗ hỏng:

| Cặp màu | Đo | Cần | Xử lý |
|---|---|---|---|
| trắng trên `#E8698C` (rose-500) | **3,07:1** | 4,5 | ⇒ nền mang chữ dùng **rose-700 `#B13A5E`** (5,78:1) |
| trắng trên `#D44B74` (rose-600) | **4,15:1** | 4,5 | vẫn trượt — đừng dùng làm nền nút |
| chữ phụ `#AB999D` (n-400) | **2,54:1** | 4,5 | ⇒ chữ thấp nhất là **n-500 `#7D6B6F`** (4,69:1); n-400 chỉ cho viền/icon |
| banner trễ hạn | **4,12:1** | 4,5 | ⇒ `--bad` đậm lại thành `#B44B3B` (4,58:1) |

**Mắt không đo được tương phản** — bản vẽ trông ổn vẫn có thể trượt chuẩn. Mọi màu mới thêm về sau phải chạy lại phép đo này.

**(d) Chỗ thứ năm, do phản biện khác-họ bắt được sau khi (c) đã "xong".** Viền focus đặt là `rose-400` = **2,55:1** trên nền — mà viền focus thuộc *non-text contrast* (WCAG 1.4.11), vẫn cần **3:1**. Đổi sang `rose-600` (3,90:1).
> Đáng ghi vì nó là bài học chứ không phải một dòng sửa: (c) đã đo **chữ trên nền** rất kỹ rồi tuyên bố xong, nhưng **không đo thứ không phải chữ**. Một luật phát biểu theo một chiều thì chiều còn lại tự động được thả — cùng họ với bài học `note.title` ngày 23/07. **Nói to cả hai nửa.**

**(e) `--popover` phải SÁNG.** Nó là nền của Select/Dropdown/Dialog trong shadcn, không phải nền tooltip. Tooltip nền tối có token riêng `--tooltip`. Gộp hai thứ này lại thì mọi menu thả xuống sẽ đen giữa giao diện sáng.

## 5. Cơ chế giữ từ app cũ ✅ CHỐT

Chủ chọn **6** trong 10 cơ chế được kiểm kê:

| Giữ | Cơ chế | Yêu cầu thi công |
|---|---|---|
| ✅ | Quick-add + Enter | Lưu xong ô **tự xoá và giữ focus** — gõ tiếp liên tục không cần chạm chuột |
| ✅ | Ghim | Viền/nền nổi + **luôn xếp đầu**, bất chấp đang sắp xếp kiểu gì |
| ✅ | Gấp tràn `+N mục khác…` | Quá 3 mục thì gấp; thẻ không phình, lưới không vỡ |
| ✅ | Tick checklist ngay trên thẻ | Không mở dialog; kèm gạch ngang + đếm `X/Y mục nhỏ` |
| ✅ | Tooltip phân nhóm | ⚠️ **iPhone không có hover** ⇒ phải là *chạm để mở, chạm ngoài để đóng*; hover chỉ là bổ sung cho desktop |
| ✅ | Banner việc trễ hạn | Ghim trên cùng, dùng `--bad` / `--bad-bg` |

**Không lấy:** chip preset thời lượng/địa điểm, đoán icon từ tên địa điểm, chip ưu tiên tự định nghĩa — chưa cần ở 008, chưa loại vĩnh viễn.

❌ **"Don't care 😒" (xoá mềm sự kiện) — KHÔNG làm.** Đã chốt từ trước ở `schema-v1-brief.md` §108 (*"bỏ 'Don't care' event"*). Lý do của chủ: lịch học bị báo nghỉ thì **để nguyên và tự nhớ** tốt hơn là ẩn nó đi — ẩn mất tích lại gây lo.
> Ghi lại vì đây là bẫy có thật: bản kiểm kê do agent ngoài dựng **đề xuất giữ** cơ chế này, vì agent đó chỉ đọc code app cũ, **không đọc `docs/`**. Cố vấn ngoài luôn mù ngữ cảnh quyết định — T1 phải đối chiếu decision record trước khi nhận.

## 6. 🔒 Luật UI bắt buộc (áp cho mọi executor, mọi slice)

1. **Không viết `<button>` / `<input>` / `<select>` thô.** Dùng component trong `@/components/ui/*`. Thiếu thì thêm component mới, không vá tại chỗ. *(008 đã vi phạm: `TaskForm.tsx` còn 2 thẻ `<button>` thô.)*
2. **Không hardcode màu.** Mọi màu đi qua token ở `index.css`. Không `text-neutral-500`, không `#hex` trong component.
3. **Không đặt chiều cao cứng cho thẻ.** App cũ dùng `height=265px` nên chữ bị cắt và phải rê chuột mới đọc được. Thẻ giãn theo nội dung.
4. **Chữ không nhỏ hơn 12px.** App cũ xuống 8px; trên iPhone là không đọc nổi.
5. **Không dùng `n-400` cho chữ** (§4c).
6. **Không có tương tác nào chỉ sống bằng `hover`** — thiết bị chính của chủ là iPhone.
7. **Light mode.** Chủ chọn light. Token đã tách `:root` khỏi `@theme inline` nên thêm dark về sau không phải viết lại, nhưng **hiện tại không làm dark** — đừng tự thêm.

## 7. Còn mở ⚠️

- ~~**Bộ component còn thiếu**~~ · ~~**`lucide-react` chưa cài**~~ — **✅ xong 2026-07-25 (008e, nhịp T1)**, xem §8.
- **Undo toast** (app cũ hoàn toàn không có) — hợp đồng "Hoàn tác = soft-delete" đã chốt ở `tracking-brief.md` §8.1; phần UI chưa dựng.
- **Dark mode** — DEFER, xem §6.7.

## 8. Bộ component ✅ dựng 2026-07-25 — và bốn cái bẫy của `shadcn add`

Có đủ **9 component** ở `frontend/src/components/ui/`: `button` (cũ) + `badge` · `card` · `checkbox` · `dialog` · `input` · `select` · `sonner` · `textarea`. Dependency thêm: `lucide-react`, `sonner`. Style `radix-nova`, import primitive từ gói hợp nhất `radix-ui` — **009–012 cứ `shadcn add`, đừng viết tay**.

Bốn thứ dưới đây đều **không làm CI đỏ**, nên phải kiểm bằng tay mỗi lần thêm component:

**(a) 🔒 CLI ghi ra sai thư mục mà vẫn báo thành công.** shadcn đọc alias `@/*` từ đúng `tsconfig.json`, nhưng dự án Vite khai `paths` trong `tsconfig.app.json` (file gốc chỉ là *solution file*, `files: []`). Không thấy `paths` thì nó **không báo lỗi** — nó tạo một thư mục **tên `@`** ở `frontend/@/components/ui/` rồi in `✔ Created 9 files`. Đã vá bằng cách khai lặp `baseUrl` + `paths` vào `tsconfig.json` (có ghi chú tại chỗ). *Cùng họ với bài học 22/07: hai file đều đúng theo luật của riêng nó, lỗi nằm ở chỗ không file nào tham chiếu file kia.*

**(b) Prompt ghi đè làm rụng component còn lại, im lặng.** Chạy `add` một lượt 8 component: tới `button.tsx` (đã có) CLI hỏi ghi đè, phiên không có bàn phím ⇒ nó dừng luôn, `dialog` **không bao giờ được tạo** mà lệnh vẫn kết thúc bình thường. ⇒ **Đếm file thật sau mỗi lần `add`, đừng đọc dòng tổng kết.** Cách chạy an toàn khi trùng tên: xoá tạm file của ta, `add`, rồi `git checkout --` để lấy lại bản của ta.

**(c) `sonner` mặc định theo dark mode của hệ điều hành.** Bản CLI sinh ra đọc theme qua `useTheme()` của `next-themes` với mặc định `"system"`. Dự án light-only và không có `ThemeProvider` ⇒ `useTheme()` trả undefined ⇒ rơi đúng vào `"system"` ⇒ **iPhone đang để dark mode sẽ thấy toast nền đen** giữa giao diện sáng. Đã chốt cứng `theme="light"` và **gỡ `next-themes`**. Làm dark mode sau thì thêm lại. *Luật light-only bị phá không phải do ai viết dark mode, mà do một **giá trị mặc định**.*

**(d) Token `--radius` trần không tồn tại.** shadcn khai một `--radius` gốc rồi suy ra sm/md/lg; ta khai thẳng từng bậc. Component nào đọc `var(--radius)` (đã gặp ở `sonner.tsx`) sẽ ra **rỗng** — không lỗi, chỉ âm thầm rơi về mặc định của thư viện. Đã thêm alias `--radius: 16px`. **Đây là token duy nhất được thêm ở 008e.**

**Ghi chú kích thước chạm:** thang `radix-nova` khá nhỏ — nút mặc định `h-8` (32px), lớn nhất `h-9` (36px). 32px **đạt** WCAG 2.2 SC 2.5.8 mức AA (24×24) nhưng **dưới** khuyến nghị 44px của Apple. ⇒ trên màn hình chạm, hành động chính dùng `size="lg"`, nút icon dùng `icon-lg`, và chừa khoảng cách giữa các đích chạm. Ô `input` đã có sẵn `text-base md:text-sm` — **đừng bỏ `text-base`**: chữ dưới 16px làm Safari iOS **tự phóng to trang** khi chạm vào ô nhập.
