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

Bản dựng tham chiếu: `docs/_local/ui-b-refined.html` (**gitignore, chỉ có trên máy chủ**). Nếu không thấy file đó thì cứ theo `ui-brief.md` — nó tự đủ.

## 2. Phải làm

### 2.1 Bộ component shadcn còn thiếu
Thêm qua CLI (`npx shadcn@latest add …`), **không viết tay**: `card`, `input`, `textarea`, `select`, `checkbox`, `badge`, `dialog`, `sonner`.
- Cài `lucide-react` — `components.json` đã khai `iconLibrary: lucide` nhưng package chưa có, nên 008 phải dùng nút chữ "Sửa"/"Xoá".
- CLI sinh xong thì **đọc lại từng file**: nếu nó chèn token không có trong `index.css` → dừng, báo, đừng tự chế token.

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

- **Không** sửa `components.json`, `vite.config.ts`, `index.html`. `index.css` chỉ được **thêm** token CLI đòi (xem §1), không sửa/xoá cái đang có.
- **Không** đụng `backend/`, migration, hay bất kỳ file test backend nào.
- **Không** đổi `api.ts` / `task-ui.ts` / hình dạng request-response.
- **Không** thêm dark mode.
- **Không** thêm dependency ngoài `lucide-react` và những gì `shadcn add` tự kéo. Muốn thêm nữa → dừng, hỏi.
- **Không** đổi tên required check trong CI.
- **Không** tự thêm cột / migration cho `pinned` (xem 2.2).

## 4. Acceptance — kiểm chứng được

1. `npm run lint` sạch.
2. `npm run build` xanh.
3. `npm test` — **9 test hiện có vẫn phải qua**. Nếu phải sửa test thì giải thích trong PR *vì sao hành vi đổi*, đừng sửa test cho vừa code.
4. `grep -rE "text-neutral-|bg-neutral-|text-gray-|bg-gray-|text-slate-|bg-slate-|oklch\(" frontend/src --include=*.tsx` → **không ra kết quả nào**. Đây là cách máy kiểm luật "không hardcode màu".
   *(Cố ý không bắt `#hex`: thuộc tính `fill`/`stroke` của SVG nội tuyến có thể cần hex hợp lệ, chặn cứng sẽ đẩy người làm đi đường vòng. Hex trong `className` vẫn bị cấm bởi §1 — T1 đọc diff để kiểm.)*
5. PR mở vào `develop`, `gh pr checks <PR>` **xanh toàn bộ** trước khi báo xong.

## 5. Báo cáo

Theo luật biên lai ở `AGENTS.md`: **số PR + `gh pr checks` xanh + diff đọc được**. Lời khai "đã xong" không đóng được task.

Trong PR description ghi rõ:
- Danh sách component đã thêm.
- **Cách ghim đang lưu ở đâu** và vì sao đó là tạm thời (2.2).
- Bất cứ chỗ nào bạn phải chọn giữa hai cách và đã tự chọn.
