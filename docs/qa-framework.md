# QA framework — khung soi giao diện dùng chung

> **Trạng thái: ✅ CHỐT 2026-07-29 (v1), +3.E thêm 2026-07-31 (v1.1), +hash-verify ảnh thêm 2026-08-01 (v1.2), +làm rõ policy môi trường 2026-08-24 (v1.3).** Áp cho `009`–`012` và mọi slice có UI sau đó.
> Đọc kèm `docs/ui-brief.md` §6 (luật UI cứng). **File này không lặp lại luật đó** — nó là
> cách kiểm xem luật đó có còn được giữ không, cộng với những trục mà luật UI không nói tới.
> Tự-chứa: đọc được ở phiên 0-context, dùng thẳng làm nguồn cho prompt giao T3/T2.

## 1. Vì sao có file này

Tới trước 29/07, QA giao diện của dự án chạy bằng **một câu hỏi mở**: *"chỗ nào chật, khó bấm, hay lạ?"*.
Câu đó có tác dụng thật — chính chủ tự dùng app một buổi và bắt được 5 mục ([[§9 nhật ký]]). Nhưng nó
có ba khuyết điểm không sửa được bằng cách hỏi hay hơn:

1. **Không lặp lại được.** Hai lượt hỏi cùng một câu ra hai kết quả khác nhau, và không có cách nào
   biết lượt nào sót.
2. **Không giao được.** T3/T2 nhận câu hỏi mở thì trả về ấn tượng, không trả về số đo — mà luật của
   dự án là *"agy là cố vấn, T1 kiểm tay từng mục"*; kiểm một ấn tượng thì không có gì để kiểm.
3. **Không nghiệm thu được.** Một lượt QA báo *"không thấy gì"* và một lượt QA **không soi gì** trông
   giống hệt nhau.

Và có một dữ kiện đắt hơn cả ba: **lượt QA kịch bản của `008e` (25/07) chạy nghiêm túc, bắt đúng
những thứ nó được bảo đi tìm — rồi trượt cả 5 mục mà chủ bắt được 4 ngày sau.** Nó soi **dữ liệu ác
ý** (chuỗi 70 ký tự không dấu cách, tiếng Việt dấu dày, emoji) nhưng không soi **việc dùng thật, lặp
lại, trên thiết bị thật**. Cả hai lượt đều đúng trong phạm vi của mình. Khoảng trống nằm **giữa** hai
phạm vi — đúng họ lỗi mà `CLAUDE.md` ghi lại nhiều lần nhất.

⇒ Khung này tồn tại để **biến phạm vi thành thứ viết ra được**, không phải để thay người soi.

## 2. Ai chạy, chạy trên gì

**Ai:** 🔒 **QA thao tác lặp không bao giờ chạy ở T1** (luật chi phí do chủ đặt, 25/07). Thứ tự:
**T3 (agy + Chrome DevTools MCP, profile đã đăng nhập)** trước → **T2 (Codex, skill `control-chrome`)**
nếu T3 tắc. T1 chỉ **viết kịch bản** và **đọc kết quả**.

**Trên gì:**

| | Bắt buộc | Ghi chú |
|---|---|---|
| Môi trường | `microsched.fly.dev` (bản đang chạy thật) | Không QA trên `vite dev` — service worker, production build/config, mạng thật, Neon wake-up và lifecycle deploy/restart đều khác |
| Viewport chính | **390 × 844** (iPhone) | Thiết bị chính của chủ. Mọi mục đỏ ở đây là đỏ thật |
| Viewport phụ | 1280 × 800 | Chỉ để kiểm lối tắt desktop (hover) không hỏng |
| Thiết bị thật | ít nhất 1 lượt/slice trên iPhone thật | Bàn phím ảo, safe area, và độ nhạy chạm không mô phỏng được |

⚠️ **`resize_window` của kênh trình duyệt từng báo resize 390px trong khi `innerWidth` vẫn 1254**
(đo thật 25/07). Trước khi tin viewport, **đọc `window.innerWidth` thật**.

### 2.1 📝 Làm rõ 2026-08-24 — production không phải môi trường test dùng chung

Phần §2 ban đầu ghi production + Chrome profile thật + iPhone thật vì nó mô tả **dogfooding sau
deploy** của các slice UI. Nó không cấp quyền dùng production cho test phá huỷ, lặp dày, migration,
timeout, fault injection hoặc bộ dữ liệu hàng loạt. Từ `025`, áp policy sau; đoạn này **thắng hai ô
“Môi trường” và “Thiết bị thật” ở bảng trên khi phạm vi là disposable QA**:

1. **Lane mặc định cho QA có mutation là local disposable cell:** đúng Docker image production của
   candidate SHA, Postgres throwaway, session/PIN/data hoàn toàn synthetic, và Playwright Chromium
   trong context mới, không persistent. Cell không được biết URL/credential production và phải tự
   huỷ toàn bộ DB/network/container sau lượt chạy.
2. **Production mặc định-deny, không phải general test environment.** Chỉ một smoke/post-deploy
   acceptance hẹp được spec riêng nêu đích danh và chủ cho phép mới được chạm production. Không dùng
   production cho seed dữ liệu QA, migration rehearsal, retry/fault/timeout hoặc automation lặp.
3. **Isolated Playwright context chỉ thuộc local disposable cell.** Nó không sửa, nới hay thay thế
   luật “lái trình duyệt production = Chrome profile thật của chủ” trong `AGENTS.md`. Local cell cấm
   `channel: "chrome"`, `launchPersistentContext`, `userDataDir`, `storageState` lấy từ máy thật,
   Google OAuth thật và mọi profile Chrome thật.
4. **Physical iPhone là acceptance riêng, không được suy ra từ viewport 390×844/Chromium.** Machine
   receipt phải ghi đúng token `PASS`, `FAIL` hoặc `NOT_RUN`; báo cáo hiển thị có thể viết
   “NOT RUN”. Owner đã chốt: release v1.0 **được phép** đi tiếp khi mục này là `NOT_RUN`;
   `NOT_RUN` không được đổi nhãn thành `PASS` và một task có contract riêng
   vẫn giữ verdict riêng của nó. Cụ thể, nếu `017` chưa chạy A18 trên iPhone thì báo
   `017 = PARTIAL / A18 = NOT_RUN`, dù release gate cấp sản phẩm có thể là `GO` theo policy này.

Task `025` là spec thi công + QA độc lập cho cell nói trên. Nó không cho phép auth-bypass route,
không chạm Neon/host DB/`.env`, không tự bật recurring outbound, không chạy deploy migration, và
không hấp thụ implementation hay acceptance của `017`.

## 3. Bốn trục

Mỗi mục dưới đây phải trả về **đạt / không đạt kèm số đo hoặc `file:line`** — không trả về cảm nhận.

### 3.A Nielsen — 10 heuristics, hỏi theo ngôn ngữ của app này

| # | Heuristic | Hỏi gì ở microSched | Đo thế nào |
|---|---|---|---|
| 1 | Trạng thái hệ thống nhìn thấy được | Mọi hành động async có phản hồi trong ~100ms? Nút có trạng thái đang-chạy? | Bấm rồi đếm; kiểm nút đổi nhãn/`disabled`. Thay đổi **không do người dùng gây ra** phải có `role="status"`/`aria-live` |
| 2 | Khớp với thế giới thật | Chữ trên màn có phải chữ chủ dùng khi nói không? | Không có từ kỹ thuật lọt ra UI (`payload`, `sync`, `entity`, `slice`, `soft-delete`) |
| 3 | Người dùng kiểm soát được | Mọi **chế độ** có lối ra **nhìn thấy được**? Mọi hành động phá huỷ có hoàn tác? | Vào chế độ rồi tìm đường ra mà không dùng nút Back của trình duyệt. Xoá phải có toast Hoàn tác **10 giây** (`tracking-brief.md:150`) |
| 4 | Nhất quán | Cùng một hành động ở hai màn có trông giống nhau không? | Component đến từ `@/components/ui/*`; không có nút tự vẽ |
| 5 | Chặn lỗi từ đầu | Nút có bị vô hiệu khi dữ liệu chưa hợp lệ? | Thử submit rỗng / chỉ khoảng trắng. **Ưu tiên hoàn tác hơn hộp xác nhận** |
| 6 | Nhận ra hơn phải nhớ | Có dòng chữ nào đang **giải thích** thứ mà giao diện tự thể hiện được không? | Xoá thử dòng đó trong devtools: mất thông tin gì không? Không mất ⇒ dòng đó là rác. *(Bug 29/07-④)* |
| 7 | Linh hoạt & lối tắt | Lối tắt (hover, phím) có phải **đường duy nhất** tới thứ gì không? | Tắt chuột, chỉ dùng chạm: mọi thông tin/hành động vẫn tới được (`ui-brief.md` §9a) |
| 8 | Tối giản | Mỗi phần tử trả lời được câu *"bỏ đi thì mất gì"* chứ? | Đếm phần tử trên màn; mục nào không trả lời được thì đề xuất bỏ |
| 9 | Giúp nhận ra & thoát khỏi lỗi | Lời báo lỗi có nói được **làm gì tiếp** không? Nó hiện **ở nơi người dùng đang nhìn** chứ? | Không có "Đã xảy ra lỗi" trần. 🔒 Kiểm lỗi có bị vẽ trong một `Dialog` **đã đóng** không — lỗi `008i`, người dùng không thấy chữ nào |
| 10 | Trợ giúp & tài liệu | — | App một người dùng: **không cần help**. Thấy mình muốn viết hướng dẫn ⇒ đó là dấu hiệu #6 đang hỏng, đi sửa #6 |

### 3.B Chạm & di động

| Mục | Ngưỡng | Cách đo |
|---|---|---|
| Đích chạm — hành động chính | **≥ 44 × 44** CSS px (Apple HIG) | `getBoundingClientRect()`, **không ước lượng bằng mắt** |
| Đích chạm — tuyệt đối tối thiểu | **≥ 24 × 24** (WCAG 2.5.8 AA) | như trên. Dưới ngưỡng này là **đỏ**, không phải vàng |
| Khoảng cách giữa hai đích liền kề | ≥ 8px | như trên |
| Vùng bấm của một **đối tượng** (thẻ, hàng) | Bấm được **cả thẻ**, không chỉ đúng chữ tiêu đề | Chạm vào khoảng trống trong thẻ. *(Bug 29/07-②)* |
| Tương tác chỉ-hover | **0** | Kiểm bằng chạm, xem `ui-brief.md` §6.6 + §9a (luật có **hai nửa**) |
| Cỡ chữ ô nhập | ≥ 16px | Dưới 16px ⇒ Safari iOS **tự phóng to trang** khi chạm vào ô |
| Cuộn ngang | **0** | `document.documentElement.scrollWidth <= window.innerWidth` ở 390px |
| Popover / tooltip / menu bị cắt | **0** | 🔒 Khung app có `overflow-hidden` (`App.tsx:75`). Mọi lớp nổi phải **portal ra `body`**, không dùng `absolute` trong thẻ. Kiểm ở **thẻ cuối cùng, sát đáy màn** — thẻ đầu tiên luôn trông ổn. *(Bug 29/07-①)* |
| Bàn phím ảo | Ô nhập đang gõ không bị che | Chạm ô ở cuối màn trên iPhone thật |
| Chữ trong nút | Không xuống dòng giữa cụm, không tràn | 🔒 Lớp gốc `Button` có `shrink-0`: muốn chữ xuống dòng phải đủ **ba** lớp `min-w-0 shrink break-words`, thiếu một là không chữa được (bài học 25/07). Đo **trong DOM thật** — app đi qua `cn()`/tailwind-merge, nối chuỗi lớp bằng tay ra kết quả sai |

### 3.C WCAG — phần đo được bằng máy

| Mục | Ngưỡng | Ghi chú |
|---|---|---|
| Chữ thường trên nền | **≥ 4,5:1** | |
| Chữ lớn (≥ 24px, hoặc ≥ 18,7px đậm) | ≥ 3:1 | |
| 🔒 **Non-text (WCAG 1.4.11)** | **≥ 3:1** | **Viền ô nhập · icon mang nghĩa · vòng focus · chỉ báo trạng thái.** Xem cảnh báo ngay dưới bảng |
| Vòng focus | Nhìn thấy được trên **mọi** phần tử tương tác, kể cả trên nền màu | |
| Đường bàn phím | Tab đi hết được · không bẫy focus · `Dialog` trả focus về đúng nút đã mở nó | |
| Nút icon | Có `aria-label` gồm **hành động + đối tượng** ("Ghim *tên task*") | |
| Vùng `aria-live` | **Nhỏ**, chỉ chứa thứ đáng thông báo | Bọc cả app thì tick một mục cũng bị đọc lên (`App.tsx:117`) |

🔒 **Non-text contrast đã trượt BA lần trong dự án này**, mỗi lần một hình dạng khác: chữ trắng trên
brand (3,07:1) → **viền focus** (2,55:1) → **icon ghim** trên thẻ ghim (2,82:1). Nguyên nhân không đổi:
luật được phát biểu **một chiều** ("chữ trên nền phải ≥ 4,5"), nên mọi thứ *không phải chữ* tự động
được thả. Cùng cơ chế với `note.title` (23/07): **cấm một chiều = cho phép chiều còn lại.**

🔒 **Mắt không đo được tương phản.** Bản đã được chủ duyệt bằng mắt vẫn có 4 cặp trượt (25/07). Dùng
công cụ, chép **con số** vào báo cáo.

### 3.D Microcopy

- **Đọc to lên.** Câu nào không ai nói ra miệng thì viết lại. *(Bug 29/07-④)*
- **Không dùng ngôi "tôi"** ở bất cứ đâu trong sản phẩm (quyết định 26/07).
- **Nhãn nút = động từ + tân ngữ**, ≤ 3 từ nếu nó nằm trong một hàng ngang.
- **Lời báo lỗi = chuyện gì xảy ra + làm gì tiếp.** Không "Đã xảy ra lỗi."
- **Không giải thích hành vi mà giao diện tự thể hiện được** (trục 3.A #6).
- **Tiếng Việt không đổi dạng số nhiều** — đừng thêm nhánh đếm.
- **Không viết chữ vào chỗ chỉ hover mới thấy** (trục 3.B).

### 3.E Thẩm mỹ tổng thể (taste) — 📝 Thêm 2026-07-31 (đề xuất chủ, phiên QA `009`)

Bốn trục trên đo được bằng máy hoặc quy tắc rõ. Trục này khác: **không có ngưỡng, không đạt/không
đạt**, và **không vào bảng phát hiện** ở §7(b) — bảng đó bắt buộc `file:line`/số đo, trục này không có
cái nào trong hai thứ đó. Mục đích: thu thập cảm nhận tổng thể **có hệ thống**, thay vì bỏ ngỏ như câu
hỏi mở cũ đã bỏ ở §1 — khác ở chỗ đây là ảnh chụp thật + vài câu, không phải một câu hỏi mở chung
chung.

- **Chụp ảnh màn hình thật** (không mô tả bằng chữ) ở các checkpoint bắt buộc: danh sách ≥30 mục (cả
  390px lẫn 1280px) · một `note-detail-dialog` đang mở với checklist dài · trạng thái riêng tư đang
  khoá · trạng thái riêng tư vừa mở.
- Mỗi ảnh kèm 2-4 câu: nhịp điệu/khoảng cách đều không · mật độ thông tin vừa mắt không · có chỗ nào
  trông thô, chưa xong, hoặc lệch tông với phần còn lại của app không.
- **Chủ tự quyết, T3 không chấm đạt/không đạt.** Không cần đồng ý với hướng "B hồng ấm" đã chốt
  (`ui-brief.md`) — chỉ báo cáo cảm nhận kèm ảnh để chủ xem, không tự ý đề xuất đổi token màu.

## 4. Ma trận trạng thái — chỗ QA kịch bản hay trượt nhất

Không soi *màn hình*, soi **màn hình × trạng thái**. Mỗi màn phải đi qua đủ:

`rỗng` · `đang tải` · `lỗi tải` · `đang gửi` · `lỗi gửi` · `offline` · `nội dung dài` · `rất nhiều mục (30+)` · và **các trạng thái riêng của miền** (trễ hạn · riêng tư · đã ghim · đã xong · đã xoá + hoàn tác).

Hai ô hay bị bỏ nhất, và cả hai đều đã sinh bug thật ở dự án này:

- **`lỗi gửi` khi hộp thoại đã đóng** — lời báo lỗi vẽ bên trong `Dialog` thì đóng hộp là mất chữ (`008i`).
- **`rất nhiều mục`** — banner, bộ lọc, và thanh cuộn chỉ lộ khuyết điểm khi danh sách dài hơn một màn. *(Bug 29/07-③)*

## 5. Dữ liệu test bắt buộc

**Ác ý** (đã dùng từ 25/07 — giữ nguyên):

- chuỗi 70 ký tự **không có khoảng trắng**
- tiếng Việt ~150 ký tự **dấu dày**
- **CHỮ HOA CÓ DẤU**
- emoji
- chuỗi **toàn khoảng trắng**

**Bình thường nhưng thật** (thêm 2026-07-29 — đây là nửa mà 25/07 thiếu):

- **≥ 30 mục** trong danh sách, có mục ở **ngoài màn hình đầu tiên**
- ít nhất 3 mục **trễ hạn**, nằm rải rác chứ không đứng đầu
- hỗn hợp đủ trạng thái miền trong **cùng một** danh sách
- và **dùng lại app đó vào một ngày khác** — có bug chỉ hiện ra ở lượt dùng thứ hai

*(`Item 1..5` thì layout nào cũng sống. Đó là lý do bộ dữ liệu này là bắt buộc, không phải gợi ý.)*

## 6. Biến phát hiện thành test vĩnh viễn

Một bug QA đã sửa mà **không có test neo lại** thì nó sẽ quay lại — và lượt QA sau phải bắt lại từ
đầu, tốn đúng một lượt quota. Luật:

1. **Mỗi bug QA đã sửa phải có một test Playwright tương ứng**, khẳng định đúng hành vi đã sửa.
2. **Selector đi qua `data-testid`, không đi qua chữ tiếng Việt.** Copy thay đổi thường xuyên (chính
   trục 3.D bắt ta đổi chữ) — test bám vào chữ là test tự vỡ theo mỗi lần sửa microcopy.
3. **Quy ước tên: `<thực-thể>-<phần-tử>[-<bổ-nghĩa>]`, kebab-case.**
   Ví dụ đã dùng ở `018`: `task-card` · `task-title` · `task-pin` · `task-delete` · `quick-add-input`
   · `quick-add-submit` · `overdue-banner` · `filter-<giá trị>`.
   Thực thể nhiều dòng thì kèm thuộc tính id riêng (`data-task-id`), **không** nhét id vào `testid`.
4. `data-testid` là thuộc tính test thuần: **0 ảnh hưởng** tới hiển thị và hành vi. Không dùng nó để
   móc CSS.

## 7. Định dạng báo cáo

Ghi **append theo từng lô** vào một file trên đĩa, chỉ append, không ghi đè.
*(Lý do: `agy` từng thoát `exit code 0` với stdout chỉ có `Error: timeout waiting for response` —
21KB báo cáo sống sót **chỉ nhờ luật append**. Nghiệm thu bằng **sản phẩm trên đĩa**; cả exit code
lẫn stdout đều nói dối, mỗi cái một chiều ngược nhau.)*

Mỗi lô gồm ba phần, **thiếu phần (a) là không nghiệm thu được**:

**(a) Đã soi những gì** — liệt kê màn × trạng thái × viewport đã đi qua. *Một lượt QA "không tìm thấy
gì" và một lượt QA không soi gì trông giống hệt nhau nếu thiếu phần này.*

**(b) Phát hiện** — bảng:

| # | Trục (3.A/B/C/D) | Mức | Chỗ (`file:line` hoặc selector) | Số đo | Đề xuất |
|---|---|---|---|---|---|

**Mức:** 🔴 **đỏ** = dưới ngưỡng cứng (WCAG AA, 24px đích chạm) hoặc chặn một việc người dùng cần làm
· 🟡 **vàng** = trên ngưỡng nhưng dưới khuyến nghị, hoặc gây khó chịu lặp lại · ⚪ **trắng** = ý kiến
thẩm mỹ, chủ quyết.

**Mỗi dòng phải có `file:line` hoặc số đo.** Không có ⇒ nó là ấn tượng, ghi xuống mục riêng cuối báo
cáo, đừng trộn vào bảng.

**(c) Ảnh + taste (trục 3.E)** — 📝 Thêm 2026-07-31. Với mỗi checkpoint bắt buộc của 3.E: đường dẫn
ảnh chụp đã lưu + 2-4 câu nhận xét. **Không** ghi vào bảng (b) — không có `file:line`/số đo nên không
đạt điều kiện của bảng đó. Phần này chủ tự đọc, không phải thứ T1 kiểm-tay-từng-mục như §8.

🔒 **Thêm 2026-08-01 (QA `009`) — mỗi ảnh phải đi kèm mô tả banner/chữ đầu trang, và T1 phải `md5sum`
đối chiếu N ảnh TRƯỚC khi đọc N nhận xét.** Đo thật: agy claim đủ 4 ảnh phân biệt, nhưng 2 cặp trùng
byte-for-byte (chép đè ảnh cũ để đủ số lượng) — và phần "nhận xét" cho ảnh giả không hề nhắc tới nội
dung rất nổi bật (banner khoá riêng tư) đang có trong ảnh, vì văn bản không được sinh từ việc thật sự
nhìn ảnh. Số lượng file đúng theo yêu cầu **không chứng minh** nội dung đúng. Yêu cầu prompt QA: bắt
T3 mô tả 1 câu "chữ/banner gì đang hiện ở đầu trang" cho MỖI ảnh trước khi viết nhận xét — nếu mô tả
đó thiếu chi tiết rõ ràng đang có trong ảnh thật, đó là dấu hiệu ảnh giả hoặc ảnh không được nhìn.

## 8. Luật đọc kết quả — dành cho T1

🔒 **T3 là cố vấn, T1 kiểm tay từng mục.** Không phải vì T3 kém: dạng sai của nó rất đặc trưng và
**rất dễ tin** — *kết luận đúng, trích dẫn sai*. Ba lần trong một phiên (26/07) nó chỉ sai bảng, sai
dòng, sai tên file trong khi kết luận thì đúng; và 25/07 nó **tự tính lại đúng cả 6 con số tương
phản** đồng thời **suy luận sai 2 mục vì không đo**.

Thao tác kiểm, theo thứ tự rẻ dần:

1. Mục có **số đo** ⇒ đo lại đúng một lần bằng đường khác.
2. Mục có **`file:line`** ⇒ mở file, đọc dòng đó.
3. Mục **không có cả hai** ⇒ chưa phải finding.
4. Ảnh (trục 3.E) ⇒ `md5sum` toàn bộ ảnh claim là phân biệt TRƯỚC khi đọc nhận xét — file trùng hash
   mà mô tả khác nhau là bằng chứng ảnh giả, không phải trùng hợp (xem §7(c)).

Và luật ngược lại, cũng đã sinh lỗi thật: **lời tự khai của một agent về năng lực của chính nó là dữ
liệu về cấu hình hiện tại, không phải về giới hạn** — "CANNOT-DO" đã hai lần hoá ra là làm được.

## 9. Nhật ký các lượt QA

| Ngày | Ai | Phạm vi | Kết quả | Khoảng trống lộ ra sau đó |
|---|---|---|---|---|
| 2026-07-25 | T3 (agy + Chrome DevTools MCP) | `008e` — màn Task, dữ liệu ác ý, 390px | 3 mục đỏ → sửa ở `008k` | **Trượt cả 5 mục của 29/07**: soi dữ liệu ác ý, không soi việc dùng lặp trên thiết bị thật |
| 2026-07-29 | Chủ (dogfooding, iPhone + máy tính) | Dùng thật một buổi, đối chiếu ảnh app v1 | 5 mục (①tooltip bị cắt ②vùng bấm ③banner trễ hạn ④microcopy ⑤thiếu điều hướng theo ngày) | Không lặp lại được, không giao được, không nghiệm thu được ⇒ **file này** |
| — | | | | |

*Mục ⑤ (điều hướng `< Về hôm nay >` của app cũ) **không phải bug** — là câu hỏi thiết kế thật sự bỏ
ngỏ, thuộc phạm vi `010` (calendar). Ghi ở đây để nó không bị QA sau bắt lại như lỗi mới.*
