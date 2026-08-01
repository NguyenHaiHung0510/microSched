# 009-QA — QA trình duyệt thật cho note slice trên production

> **Thứ tự chạy: T2 review kịch bản này trước (feasibility — chọn đúng selector/URL/trạng thái chưa,
> thiếu gì) → fold phản hồi → T3 thực thi (agy CLI nền, profile Chrome đã đăng nhập).**
> Tự-chứa: đọc được ở phiên 0-context. Đọc kèm bắt buộc: `docs/qa-framework.md` (khung 4+1 trục,
> ma trận, dữ liệu, định dạng báo cáo, luật đọc kết quả — **file này không lặp lại nội dung đó**,
> chỉ cụ thể hoá cho note) và `agent-tasks/009-note-slice.md` (đúng field/API/hai chỗ lệch Note↔Task).

## 0. Bối cảnh

`009` (note slice) đã merge + live production (`microsched.fly.dev`, PR #71, commit `54d04ed`).
`016` (private unlock) đã merge + live trước đó (PR #67, `de95d30`) — note dùng chung cổng
`PrivateGate`/`session.private_until` với task, **chưa từng được QA cùng nhau qua browser thật**.
PR #73 (thêm `data-testid` cho checklist item của note + trục taste vào `qa-framework.md`) đã merge
— chờ xác nhận SHA sống trước khi bắt đầu QA (xem cuối phiên T1 để lấy SHA chính xác).

Đây là QA đầu tiên phủ Note + PrivateGate cùng lúc trên production thật. Không QA trên `vite dev`.

## 1. Phạm vi — 4 bề mặt

1. **`NotesScreen`** — quick-add (chỉ title) + danh sách (`data-testid="note-list"` / `"note-card"`).
2. **`note-create-dialog`** — form đầy đủ (title không bắt buộc, body, checkbox riêng tư).
3. **`note-detail-dialog`** — xem/sửa note + toàn bộ checklist trong dialog.
4. **Checklist item** — cả bản rút gọn hiện trên card (chỉ checkbox, tối đa 3 dòng + nút "+N mục
   khác…") lẫn bản đầy đủ trong dialog (checkbox/nội dung/lên/xuống/sửa/xoá).

Cộng: **tương tác PrivateGate** — bật `is_private` trên note, khoá phiên riêng tư (`private-lock-now`),
mở lại bằng PIN (`private-unlock-open` → `private-pin-input` → `private-unlock-submit`), xác nhận note
biến mất khỏi `note-list` khi khoá và quay lại khi mở.

## 2. Ma trận màn × trạng thái bắt buộc

| Trạng thái | Bề mặt | Cách tạo |
|---|---|---|
| rỗng | `note-list` | Tài khoản QA chưa có note nào (hoặc lọc tạm — xem §5 dữ liệu) |
| đang tải / lỗi tải + nút Thử lại | `note-list` | Throttle mạng chậm/offline trong DevTools lúc load |
| đang gửi (`create.isPending` → nút "Đang thêm…") | quick-add, `note-create-dialog` | Throttle mạng chậm, quan sát nhãn nút đổi |
| lỗi gửi — **cả khi dialog đã đóng** | quick-add (`quick-add-note-submit`), item mutation (add/toggle/sửa/xoá/reorder) | Ngắt mạng giữa request; với item mutation: đóng `note-detail-dialog` trong lúc request treo, xem lỗi có hiện lại trên `note-card` không (mã dùng chung 1 biến `mutationError` cho Card lẫn Dialog — xem `frontend/src/NotesScreen.tsx:155-161`) |
| nội dung dài | note-card, note-detail-dialog | Title 70 ký tự dính liền + body dài (xem §4 dữ liệu ác ý) |
| checklist dài (>3 mục) | note-card (nút "+N mục khác…") | ≥5 item trên 1 note |
| rất nhiều note (30+) | `note-list` | Xem §4 |
| riêng tư — khoá | mọi bề mặt | `is_private=true`, phiên đang khoá |
| riêng tư — vừa mở | mọi bề mặt | Mở bằng PIN, xem note riêng tư xuất hiện lại |
| đã xoá + hoàn tác (10s) | toast sau xoá note | Xoá 1 note, bấm Hoàn tác **trong** 10s và **sau** 10s (2 lượt riêng) |
| reorder ở biên (mục đầu/cuối) | checklist trong dialog | Nút Lên ở mục đầu, nút Xuống ở mục cuối phải tự `disabled` |

## 3. Bốn trục + taste — cụ thể hoá cho note (đọc `docs/qa-framework.md` §3 để biết đầy đủ, đây chỉ là phần đặc thù)

- **3.A #3 (lối ra)**: đang mở `note-detail-dialog` của 1 note, bật `is_private` trong lúc sửa (`editing=true`) → lưu → note biến mất khỏi list ngay. Dialog có tự đóng gọn gàng không, hay đứng treo/lỗi?
- **3.A #6**: dòng "Ghi chú riêng tư sẽ được mã hoá và chỉ hiện khi private unlock đang mở." (`note-create-dialog`) — đánh giá đây có phải thông tin *không* tự hiện qua UI (đáng giữ) hay là dòng thừa nên bỏ.
- **3.A #9 + lỗi gửi/dialog đóng**: xem dòng "lỗi gửi" ở bảng §2 — đây là ô hay trượt nhất theo `qa-framework.md` §4.
- **3.B chạm**: đo `getBoundingClientRect()` thật cho nút Lên/Xuống/Sửa/Xoá trong hàng checklist (`size="icon-lg"`, hàng `min-h-11`) ở 390px — đừng suy từ class.
- **3.C WCAG non-text**: đo lại contrast của Badge "Riêng tư" (`variant="secondary"`) và nút xoá icon `text-bad` **sau PR #70** (đổi cascade layer ảnh hưởng toàn app vì note tái dùng chung component với task) — đưa số đo cụ thể, không suy đoán từ đã-fix-ở-task.
- **3.D microcopy**: đọc to "Không tiêu đề" (fallback khi title rỗng) — có tự nhiên không.
- **3.E taste (mới, xem `qa-framework.md` §3.E)** — chụp ảnh thật + 2-4 câu, **không chấm đạt/không đạt**, checkpoint bắt buộc:
  1. `note-list` với ≥30 note (390px **và** 1280px)
  2. `note-detail-dialog` đang mở, checklist ≥5 mục
  3. Trạng thái riêng tư đang khoá (badge/nút trên `PrivateGate`)
  4. Trạng thái riêng tư vừa mở (note riêng tư vừa hiện lại trong list)

## 4. Dữ liệu bắt buộc

Theo đúng `qa-framework.md` §5 — **áp cho cả title note lẫn từng nội dung item checklist**, không chỉ title:
- chuỗi 70 ký tự không khoảng trắng
- tiếng Việt ~150 ký tự dấu dày
- CHỮ HOA CÓ DẤU
- emoji
- chuỗi toàn khoảng trắng (kỳ vọng: nút submit tự `disabled`, xem `note-ui.ts:canSubmitNote`)

Cộng: ≥30 note (ít nhất 1 note ≥15 checklist item), ≥2 note riêng tư xen giữa note thường (không đứng
đầu/cuối danh sách), 1 lượt QA thứ hai sau lượt đầu ít nhất vài phút (dùng lại app, không chỉ dùng 1 lần).

## 5. Bảng testid dùng làm selector (mới thêm ở PR #73, `frontend/src/NotesScreen.tsx`)

| testid | Ở đâu |
|---|---|
| `note-list`, `note-card`, `note-title`, `note-edit`, `note-delete`, `note-detail-dialog`, `note-create-dialog`, `quick-add-note-input`, `quick-add-note-submit` | Đã có từ PR #71 |
| `note-item` (+ `data-note-item-id`) | Hàng checklist, **cả** trên card rút gọn lẫn trong dialog (2 nơi, cùng tên) |
| `note-item-checkbox`, `note-item-content` | Cả 2 nơi |
| `note-item-up`, `note-item-down`, `note-item-edit`, `note-item-delete` | Chỉ trong dialog |
| `note-item-edit-input`, `note-item-edit-save` | Chỉ trong dialog, khi đang sửa 1 item |
| `note-item-add-input`, `note-item-add-submit` | Form thêm item, chỉ trong dialog |
| `private-badge`, `private-lock-now`, `private-unlock-open`, `private-pin-change-open`, `private-error`, `private-pin-input`, `private-unlock-submit` | `PrivateGate.tsx`, dùng để thao tác khoá/mở |

## 6. Việc T2 cần trả lời khi review (trước khi giao T3)

1. Selector/testid ở §5 có đúng thật trên production không (đọc lại `NotesScreen.tsx`/`PrivateGate.tsx`
   hiện tại, không tin bảng trên nếu code đã đổi)?
2. Ma trận §2 có ô nào không tạo được bằng thao tác UI thuần (không cần can thiệp DB/API tay) không —
   nếu có, ghi rõ cách tạo thay thế hoặc đánh dấu "bỏ qua, lý do X"?
3. Note nào trong §3/§4 dựa trên giả định sai về hành vi thật của code (vd: `canSubmitNote`, throttle
   PrivateGate theo `016`) — sửa lại cho khớp code hiện tại.
4. Thiếu trạng thái/bề mặt nào đáng QA mà bảng trên bỏ sót?

## 7. Định dạng báo cáo (T3)

Theo đúng `docs/qa-framework.md` §7 — append-only vào 1 file, 3 phần (a) đã soi gì (b) bảng phát hiện
(c) ảnh + taste 3.E. Đọc kết quả theo luật §8 (T3 là cố vấn, T1 kiểm tay từng mục có `file:line`/số đo).
