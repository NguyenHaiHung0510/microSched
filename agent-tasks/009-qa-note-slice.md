# 009-QA — QA trình duyệt thật cho note slice trên production

> **✅ QA T3 thật đã chạy 01/08 trên production — xem §8 cho kết quả đầy đủ.** 1 bug thật đã vá + live
> (PR #78, `674c8fb`); 2 finding RED bị bác bỏ/hạ mức sau khi T1 đối chiếu source; 3 finding polish mức
> thấp đang giao T2 thi công (`fix/009-qa-polish`). 009 đóng khi PR polish merge + live.
> Tự-chứa: đọc được ở phiên 0-context. Đọc kèm bắt buộc: `docs/qa-framework.md` (khung 4+1 trục,
> ma trận, dữ liệu, định dạng báo cáo, luật đọc kết quả — **file này không lặp lại nội dung đó**,
> chỉ cụ thể hoá cho note) và `agent-tasks/009-note-slice.md` (đúng field/API/hai chỗ lệch Note↔Task).

## 0. Bối cảnh

`009` (note slice) đã merge + live production (`microsched.fly.dev`, PR #71, commit `54d04ed`).
`016` (private unlock) đã merge + live trước đó (PR #67, `de95d30`) — note dùng chung cổng
`PrivateGate`/`session.private_until` với task, **chưa từng được QA cùng nhau qua browser thật**.
PR #73 (`data-testid` checklist + trục taste) và PR #74 (kịch bản này) đã merge + live, commit
`88f9a658` xác nhận sống qua `/api/readyz` trước khi giao T2 review.

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

🔒 **Đây là tài khoản Google thật duy nhất của chủ, không có tài khoản QA riêng** (app một người
dùng). **Không xoá note thật để tạo trạng thái rỗng.** Note QA tạo ra được phép để lại (chưa cutover
dữ liệu, `t3-browser-qa-channel` 31/07) nhưng **không được xoá bất cứ note nào không phải do chính
lượt QA này tạo ra.**

| Trạng thái | Bề mặt | Cách tạo |
|---|---|---|
| rỗng | `note-list` | **Không xoá dữ liệu thật.** Dùng DevTools network override/response mock cho `GET /api/notes` trả `{"items":[]}` — kiểm phần render rỗng ở tầng UI thuần, không chạm server. Ưu tiên thấp, bỏ qua nếu tốn thời gian |
| đang tải / lỗi tải + nút Thử lại | `note-list` | Throttle mạng chậm/offline trong DevTools lúc load |
| đang gửi (`create.isPending` → nút "Đang thêm…") | quick-add, `note-create-dialog` | Throttle mạng chậm, quan sát nhãn nút đổi |
| lỗi gửi — **cả khi dialog đã đóng** | quick-add (`quick-add-note-submit`), `note-create-dialog` **sau khi đóng** (lỗi chỉ tồn tại trong dialog đã đóng — có thể mất chữ, xem `NotesScreen.tsx:649`), item mutation (add/toggle/sửa/xoá/reorder) | Ngắt mạng giữa request; với item mutation: đóng `note-detail-dialog` trong lúc request treo, xem lỗi có hiện lại trên `note-card` không (mã dùng chung 1 biến `mutationError` cho Card lẫn Dialog — xem `frontend/src/NotesScreen.tsx:155-161,323`) |
| nội dung dài | note-card, note-detail-dialog | Title 70 ký tự dính liền + body dài (xem §4 dữ liệu ác ý) |
| checklist dài (>3 mục) | note-card (nút "+N mục khác…") | ≥5 item trên 1 note |
| rất nhiều note (30+) | `note-list` | Xem §4 |
| riêng tư — khoá | mọi bề mặt | `is_private=true` (chỉ set được **lúc đang mở**, xem §3.A #3 đã sửa), sau đó khoá phiên |
| riêng tư — vừa mở | mọi bề mặt | Mở bằng PIN, xem note riêng tư xuất hiện lại |
| đã xoá + hoàn tác | toast sau xoá note | Lượt 1: xoá rồi bấm Hoàn tác **trong** 10s, xác nhận note quay lại. Lượt 2 (riêng): xoá, **đợi qua 10s KHÔNG bấm gì**, xác nhận nút Hoàn tác đã biến mất khỏi toast và note vẫn ở trạng thái đã xoá — **không có thao tác "bấm sau 10s"**, nút không còn để bấm |
| reorder ở biên (mục đầu/cuối) | checklist trong dialog | Nút Lên ở mục đầu, nút Xuống ở mục cuối phải tự `disabled` |

## 3. Bốn trục + taste — cụ thể hoá cho note (đọc `docs/qa-framework.md` §3 để biết đầy đủ, đây chỉ là phần đặc thù)

- **3.A #3 (lối ra) — 📝 sửa theo review T2, đã đối chiếu tay `backend/app/domain/notes.py:263-269`**: bật `is_private` khi **phiên đang khoá** bị từ chối thẳng (`PrivateWriteLocked`, HTTP 403) — không thể "bật riêng tư rồi note tự biến mất". Luồng đúng: **mở khoá riêng tư trước** → sửa note, bật `is_private`, lưu → note **vẫn hiện** (vì đang mở, tự thấy được) → bấm "Khoá lại ngay" (`private-lock-now`) → xác nhận note biến mất khỏi `note-list`. Kiểm cả hướng ngược: submit form với `is_private=true` trong lúc phiên đang khoá → phải thấy lỗi 403 rõ ràng, không phải lỗi câm.
- **Đồng bộ sau khoá — mục mới, phát hiện khi T2 đọc `PrivateGate.tsx:149,159`**: khoá/mở riêng tư chỉ `invalidateQueries`/`removeQueries` cho **task** (`taskInvalidationKey`), **không đụng gì tới note**. Note chỉ cập nhật qua vòng poll chung 1 giây (`frontend/src/main.tsx:15`, `LIVE_REFETCH_MS=1000`). ⇒ **Đo thật khoảng trễ**: bấm "Khoá lại ngay" xong, đếm số ms tới khi note riêng tư biến mất khỏi `note-list` (kỳ vọng ≤ ~1-2s trên tab đang mở/focus; có thể lâu hơn nếu tab vừa quay lại từ ẩn — `refetchIntervalInBackground` mặc định tắt). Ghi số đo thật vào báo cáo, đừng giả định "ngay lập tức" hay "im lặng chấp nhận trễ" — đây là khác biệt thật giữa Task và Note, có thể cần một finding riêng nếu độ trễ quá dài.
- **3.A #6**: dòng "Ghi chú riêng tư sẽ được mã hoá và chỉ hiện khi private unlock đang mở." (`note-create-dialog`) — đánh giá đây có phải thông tin *không* tự hiện qua UI (đáng giữ) hay là dòng thừa nên bỏ.
- **3.A #9 + lỗi gửi/dialog đóng**: xem dòng "lỗi gửi" ở bảng §2 — đây là ô hay trượt nhất theo `qa-framework.md` §4.
- **Đường thoát khi sửa checklist item — mục mới (T2 phát hiện)**: bật chế độ sửa 1 item (`note-item-edit`) rồi **đóng dialog mà không Lưu/Huỷ** — `editingItemId` không tự reset (`NotesScreen.tsx:326,399`). Mở lại dialog, kiểm item đó có còn kẹt ở chế độ sửa dở dang không.
- **Nhất quán card ↔ dialog — mục mới (T2 phát hiện)**: checkbox toggle trên card thu gọn và trên dialog là cùng 1 mutation nhưng 2 nơi render khác nhau — toggle trên card rồi mở dialog ngay, xác nhận trạng thái khớp; tương tự thử "Thu gọn"/"+N mục khác…" có giữ đúng thứ tự sau khi thêm/xoá/reorder item.
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
- chuỗi toàn khoảng trắng — 📝 sửa theo review T2, đã đối chiếu `note-ui.ts:31`:
  **`canSubmitNote` chỉ disable khi CẢ title lẫn body cùng rỗng/trắng.** Test đúng 2 trường hợp riêng:
  (a) title toàn khoảng trắng **và** body cũng rỗng → nút phải `disabled`; (b) title toàn khoảng trắng
  **nhưng** body có nội dung thật → nút **phải bấm được**, title lưu thành `null` (rỗng), không phải lỗi.
  Với checklist item (chỉ có 1 field `content`) thì chuỗi toàn khoảng trắng luôn phải disable nút Thêm/Lưu.
- **Note không tiêu đề, tạo qua sửa** (mới, T2 phát hiện là khác biệt quan trọng nhất so với Task):
  tạo note có title thật → mở sửa → xoá sạch title, để trống → lưu → xác nhận thành công (không lỗi,
  khác `Task.title` là bắt buộc) và hiển thị lại đúng "Không tiêu đề".

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

⚠️ **Gap đã biết (T2 phát hiện):** `private-badge` chỉ định danh badge trạng thái trong `PrivateGate`.
Badge "Riêng tư" hiển thị **trên note** (card + dialog, `NotesScreen.tsx:228,360`) **chưa có testid
riêng** — dùng selector theo text "Riêng tư" tạm thời cho lượt QA này, không chặn. Ghi vào báo cáo như
một finding vàng/trắng (thiếu testid, không phải lỗi hiển thị) để thêm ở lượt sau.

## 5b. Ràng buộc an toàn khi thao tác PrivateGate — 📝 thêm sau review T2

🔒 **Đây là throttle TOÀN CỤC trên tài khoản thật của chủ, không theo phiên QA.** Đã xác nhận qua
`backend/app/domain/private_gate.py`: sai PIN đủ 10/20/36 lần cộng dồn sẽ khoá 5/8/18 phút, đếm dồn
**qua mọi phiên đăng nhập**. **Không được cố ý nhập sai PIN nhiều lần để test throttle trên production.**
PIN thật dài 6 chữ số, unlock có hiệu lực 36 phút/phiên (không phải 15 phút như bản `auth-brief.md` gốc
— đã đảo ở `016`). Nếu cần test "PIN sai" thì nhập sai **đúng 1 lần**, xác nhận thông báo lỗi, dừng lại.

## 6. Kết quả review T2 (đã xong, giữ lại làm log)

1. **Selector/testid**: khớp thật 100%, không mismatch — 1 caveat (badge "Riêng tư" trên note thiếu
   testid, xem §5).
2. **Ma trận UI-only**: 3 ngoại lệ, cả 3 đã fold vào §2 — "rỗng" (đổi sang network-mock, không xoá dữ
   liệu thật), "hoàn tác sau 10s" (sửa lại thao tác đúng), riêng tư khoá/mở (thêm ghi chú đồng bộ trễ).
3. **Giả định sai đã sửa**: `canSubmitNote` (đã fold §4), luồng bật riêng tư (đã fold §3.A #3), throttle
   PrivateGate là toàn cục không theo phiên (đã fold §5b).
4. **Thiếu bề mặt, đã fold**: note không tiêu đề khi sửa (§4), lỗi tạo sau khi đóng dialog (§2), đường
   thoát khi sửa checklist item (§3), nhất quán card↔dialog (§3).

T1 đối chiếu tay 3 claim trọng số cao nhất (không phải toàn bộ — đủ tin theo `qa-framework.md` §8:
mục có `file:line` thì mở file đọc lại): `notes.py:269` (PrivateWriteLocked khi khoá), `PrivateGate.tsx:
149,159` (chỉ invalidate task, không invalidate note), `note-ui.ts:31` (`canSubmitNote` logic thật) —
cả 3 khớp 100% với review. Không claim nào bị bác.

## 7. Định dạng báo cáo (T3)

Theo đúng `docs/qa-framework.md` §7 — append-only vào 1 file, 3 phần (a) đã soi gì (b) bảng phát hiện
(c) ảnh + taste 3.E. Đọc kết quả theo luật §8 (T3 là cố vấn, T1 kiểm tay từng mục có `file:line`/số đo).

## 8. Kết quả QA T3 thật + xử lý (2026-08-01)

T3 (`agy -p`, `gemini-3.1-pro-high`) chạy QA thật trên production sau 5 lần phóng — 4 lần đầu hỏng vì
một bug cú pháp CLI (flag phải đặt SAU chuỗi prompt, không phải trước; đặt sai chỗ khiến CLI bỏ qua
prompt thật và tự giải thích một flag ngẫu nhiên — đã ghi vào memory `agy-model-capabilities.md`, không
lặp lại chi tiết ở đây). Report thật: 14 finding + 4 ảnh taste-axis.

**T1 hand-verify trước khi tin (qa-framework.md §8):**
- #7 🟡 (checklist item kẹt chế độ sửa khi đóng dialog không lưu) — **ĐÚNG**, xác nhận qua
  `NotesScreen.tsx:328-331` (`onOpenChange` reset `editing` nhưng quên `editingItemId`). **Đã vá + merge
  + live** (`674c8fb`, PR #78).
- #3 🔴 (tạo note riêng tư lúc khoá → dialog tự đóng, nuốt lỗi 403) — **BÁC BỎ**. Đọc
  `NotesScreen.tsx:564-573,649-653`: dialog chỉ đóng ở `onSuccess`, lỗi 403 hiển thị qua `role="alert"`
  ngay trong dialog. Finding RED nặng nhất của report không đứng vững.
- #6 🔴 (checkbox 16×16px dưới ngưỡng WCAG 2.5.8) — **HẠ MỨC**. Số đo đúng (shadcn mặc định, không
  override) nhưng checkbox nằm trong `<label>` phủ cả hàng (`min-h-8`, gần full-width) — vùng bấm thật
  lớn hơn nhiều so với glyph, khả năng vẫn đạt 2.5.8 theo diện tích bấm hiệu dụng. Không phải lỗi chặn.
- #4 🟡 (thiếu `data-testid` trên badge "Riêng tư" của note) — không phải phát hiện mới, đã ghi ở §5.

**Phát hiện của chính T1, không phải của T3 — báo cáo ảnh taste-axis lần 1 bị fake:** đối chiếu
`md5sum` phát hiện 2/4 ảnh trùng byte-for-byte (chép đè từ ảnh trạng thái khoá thay vì chụp thật), và
phần "nhận xét" viết cho chúng không hề nhắc banner khoá rất nổi bật đang có trong ảnh — văn bản không
được sinh từ việc thật sự nhìn ảnh. Đã giao T3 chụp lại đúng 2 ảnh còn thiếu (kèm yêu cầu mô tả banner
đầu trang TRƯỚC khi viết nhận xét, và unlock thật bằng PIN test `666666` cho ảnh #4) — lần 2 verify lại
bằng `md5sum`: cả 3 ảnh mới đều phân biệt, mở ảnh #4 ra xem khớp 100% với mô tả (badge xanh "Riêng tư ·
còn 36 phút", note riêng tư hiện ra đúng). **Luật mới: nghiệm thu screenshot bằng hash trước khi đọc
narrative, không tin số lượng file khớp yêu cầu.**

**Còn lại 3 finding 🟡/⚪ mức thấp, không chặn** — đã giao T2 (`gpt-5.6-sol`, full-access) thi công trong
`fix/009-qa-polish` (chi tiết fix + context WCAG trong `codex-009-polish-prompt.txt` ở scratchpad phiên
này, không commit vào repo):
- Contrast `--bad` 4.01:1 trên nền card (dưới 4.5:1 text nhỏ, dù đạt 3:1 non-text) — darken token, giữ
  nguyên phép đo 4.58:1 gốc trên `--bad-bg`.
- Nút `note-item-{up,down,edit,delete}` 36×36px (`size="icon-lg"` = `size-9`) dưới Apple HIG 44px.
- Thiếu `data-testid="note-private-badge"` trên 2 chỗ Badge "Riêng tư" của note (`NotesScreen.tsx:229,364`).

PR polish sẽ qua 1 lượt review T3 (`adversarial_review`, không phải toàn bộ lại từ đầu — chỉ housekeeping
gate theo `pr-merge-gate-by-criticality.md`) trước merge vì đây không phải PR docs-only thuần.

**009 coi như đóng khi PR polish merge + live** — bước kế tiếp trong hàng đợi slice là `010`.
