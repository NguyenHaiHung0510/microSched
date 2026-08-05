# 011a-QA — Spec QA cho tracker capture + dashboard

> **Executor: T3 · Bậc: L2 · Effort: high · Trạng thái: DRAFT**
>
> Nguồn bắt buộc: `docs/qa-framework.md`, `agent-tasks/011a-tracker-capture-dashboard.md`,
> `docs/tracking-brief.md` §8, và `docs/ui-brief.md` §6. Đây là spec QA độc lập cho lô `011a`;
> nó không thay thế review quyết định của chủ và không cho phép T3 tự đổi product contract.

## 0. Bối cảnh & Mục tiêu QA 011a

`011a` đưa vào sử dụng ba bề mặt dữ liệu `tracker_group` / `tracker` / `entry` và một màn
`TrackerScreen` gồm:

- `CaptureGrid`: lưới nút ghi một chạm, sắp thứ tự theo tần suất + lần ghi gần nhất;
- `TrackerCard`: nút ghi cho `event`, ô tiền cho `money`, ô số lượng cho `quantity`, ghi lùi giờ;
- `EntryEditDialog`: sửa thời điểm, số lượng, tiền, giá gốc và ghi chú sau khi đã ghi;
- `GroupForm`: tạo/sửa nhóm `health` hoặc `finance`;
- `DashboardPanel`: A1–A4 cho hành vi và F1–F5 cho tài chính.

Mục tiêu của QA không chỉ là chứng minh API trả `200`. T3 phải chứng minh bằng hành vi lặp lại
rằng chủ có thể:

1. nhìn thấy trạng thái hệ thống và biết phải làm gì tiếp theo khi tải, ghi, sửa hoặc lỗi;
2. ghi một sự kiện trong dưới 3 giây mà không bị double-tap, không bị long-press tạo hai `Entry`,
   và không bị lưới đổi chỗ dưới ngón tay;
3. nhập đúng `0đ`, `100.000đ` và `99.999.999.999đ`, nhìn thấy số sẽ gửi trước khi lưu, không bị
   tràn ngang hoặc mất chữ;
4. khoá/mở private gate mà không làm lộ sự tồn tại, tên, entry hoặc tổng tiền của tracker riêng
   tư;
5. dùng Undo đúng bản chất: entry đã ghi thật, Undo chỉ là đường tắt tới soft-delete/restore;
6. đọc được dashboard rỗng, đang tải, có dữ liệu, lỗi và dữ liệu hỏng mà không nhầm số 0 với lỗi
   tải hoặc nhận một con số thiếu dữ liệu là số đầy đủ.

### 0.1 Phạm vi và môi trường

**Bắt buộc:**

- QA thao tác lặp do T3 chạy trước; T2 dùng `control-chrome` chỉ khi T3 bị chặn. T1 viết kịch bản,
  đọc biên lai và kiểm tay finding; không chạy lượt thao tác lặp thay T3.
- Môi trường browser acceptance là `https://microsched.fly.dev`, bản production đang chạy thật;
  không dùng `vite dev` để đóng acceptance. Playwright mock API chỉ chứng minh UI/harness, không
  chứng minh deploy, cookie, service worker, Neon hoặc production config.
- Viewport chính là **390 × 844**. Trước khi đo phải đọc `window.innerWidth` thật; không tin riêng
  kết quả resize của công cụ. Viewport phụ là **1280 × 800** để kiểm desktop và đường thay thế cho
  thao tác long-press.
- Có ít nhất một lượt trên iPhone thật để kiểm bàn phím ảo, safe area, touch và việc ô nhập cuối
  màn không bị bàn phím che.
- Dữ liệu QA tạo trên production phải có tiền tố/nhãn QA dễ nhận biết. Không xoá, sửa, archive hay
  restore dữ liệu không do chính lượt QA tạo. Không nhập secret, email thật hoặc PIN thật vào
  artifact; không cố ý thử throttle PIN trên tài khoản production.

**Không thuộc lô này:** `subscription`/F6 (`011c`), Web Push/cron (`011b`), Dexie/offline đầy đủ
(`017`), migration mới, AI insight, streak, heatmap, run-rate, tổng tiết kiệm và thay đổi decision
record. Với schema, chỉ kiểm chứng rằng bốn bảng/cột đã có như spec 011a nói; không tạo migration.

### 0.2 Điểm cần giữ nguyên decision record

`tracking-brief.md` §8.1 và spec thi công 011a đã khóa Undo toast/action **10 giây**; code hiện tại
cũng đặt `duration: 10_000`. Yêu cầu giao việc này nêu **“Undo banner 5s”**, nên QA contract trong
file này được hiểu thành hai checkpoint:

- tại `t ≈ 5s`: banner và action `Hoàn tác` vẫn nhìn thấy, bấm được, và entry khôi phục đúng;
- sau `t > 10s`: action hết hạn và không còn bấm được.

Nếu ý định product là **đổi thời lượng hết hạn từ 10 giây xuống 5 giây**, T3 phải ghi `BLOCKED` và
chờ chủ cập nhật đồng thời `docs/tracking-brief.md`, spec 011a, code và test. Không được sửa một
phía rồi coi là đạt.

## 1. Ma trận 4 trục

Mỗi finding phải có ít nhất một trong hai loại bằng chứng: `file:line` đọc từ source hoặc số đo/
selector lấy từ DOM thật. Cảm nhận “trông ổn” không được đưa vào bảng phát hiện đạt điều kiện. Mức
độ dùng theo khung chung: 🔴 dưới ngưỡng cứng hoặc chặn việc cần làm; 🟡 khó chịu lặp lại nhưng
không chặn; ⚪ taste/opinion, không phải pass/fail.

### 1.1 Nielsen — 10 heuristics

| # | Heuristic | Câu hỏi riêng cho 011a | Tiêu chí đạt và bằng chứng bắt buộc |
|---|---|---|---|
| 1 | Trạng thái hệ thống nhìn thấy được | Khi tải tracker/dashboard, khi bấm ghi, khi lưu form và khi Undo đang chạy, chủ có biết app đang làm gì không? | Có trạng thái loading/pending rõ; nút đổi nhãn hoặc `disabled`; trạng thái tự thay đổi dùng `role="status"`/`aria-live` nhỏ. Ghi thời điểm bấm → trạng thái xuất hiện và selector thực tế. |
| 2 | Khớp với thế giới thật | Chữ “tracker”, “entry”, “payload”, “sync”, “soft-delete” hoặc thuật ngữ backend có lọt ra UI không? | Người dùng đọc được bằng tiếng Việt tự nhiên: “Bản ghi”, “Nhóm”, “Số tiền”, “Lưu trữ”. Nếu thấy thuật ngữ kỹ thuật, ghi nguyên văn + selector. |
| 3 | Người dùng kiểm soát được | Có lối ra nhìn thấy được khỏi form/dialog/backdate/private mode không? Ghi nhầm có Undo không? | Dialog có Huỷ/đóng và trả focus; archive/group delete có xác nhận; ghi entry có Undo; private gate có khoá/mở rõ; không yêu cầu browser Back để thoát. |
| 4 | Nhất quán và theo chuẩn | Cùng một hành động ở card, danh sách entry và dialog có cách gọi/hiển thị nhất quán không? | Dùng component trong `@/components/ui/*`; không có thẻ native thô ngoài primitive đã chuẩn hoá; cùng hành động dùng cùng microcopy và trạng thái pending. |
| 5 | Chặn lỗi từ đầu | Submit trắng, tiền không hợp lệ, `money` thiếu amount, hoặc `quantity` thiếu unit có bị chặn trước request không? | Nút disabled khi invalid; không phát POST/PATCH invalid; backend 422 được trình bày như lỗi có hướng xử lý, không phải 500. Ghi request count và response status. |
| 6 | Nhận ra hơn phải nhớ | Card có cho biết lần cuối ghi lúc nào không? Ô tiền có cho biết số sẽ gửi không? | `tracker-last-seen` hiện “Chưa ghi/Vừa xong/...”; preview tiền lấy từ đúng số sẽ gửi; không giải thích dài dòng điều mà layout đã tự thể hiện. |
| 7 | Linh hoạt và lối tắt | Long-press có đường tương đương nhìn thấy trên desktop không? Có hành động nào chỉ tới được bằng hover không? | `tracker-backdate`/menu nhìn thấy được; thao tác chạm không cần hover; long-press không phải đường duy nhất để ghi lùi giờ. Kiểm cả 390px và 1280px. |
| 8 | Tối giản | Mỗi CTA, dòng trạng thái, cảnh báo và metric có trả lời một nhu cầu thật không? | Không có dòng hướng dẫn lặp lại thông tin đã hiện bằng icon/label; không thêm màn dashboard riêng ngoài contract. Finding taste ghi riêng, không giả làm lỗi cứng. |
| 9 | Giúp nhận ra và thoát khỏi lỗi | Lỗi tải/lưu/Undo có nói chuyện gì xảy ra và bước tiếp theo không? Lỗi có bị nằm trong dialog đã đóng không? | Có `role="alert"`/toast còn nhìn thấy sau khi dialog đóng, có “Thử lại” khi phù hợp, form giữ dữ liệu để sửa lại; tuyệt đối không chỉ có “Đã xảy ra lỗi.” |
| 10 | Trợ giúp và tài liệu | Giao diện có cần một bài hướng dẫn mới dùng được không? | Không cần help riêng cho flow cơ bản; nếu phải viết hướng dẫn để giải thích một affordance đang không tự rõ, ghi đó là dấu hiệu cần sửa #6, không làm tài liệu che lỗi UI. |

### 1.2 Touch target theo HIG — ngưỡng chính ≥ 44px

Đo bằng `getBoundingClientRect()` trên DOM thật ở `window.innerWidth === 390`, không suy từ class
Tailwind hoặc kích thước glyph icon.

| Mục đo | Ngưỡng | Selector/điều kiện |
|---|---:|---|
| Hành động chính | **≥ 44 × 44 CSS px** | `tracker-button`, `Tracker mới`, `Nhóm mới`, submit/cancel chính trong các form/dialog |
| Icon action | **≥ 44 × 44 CSS px** | `tracker-backdate`, `entry-edit`, `entry-undo`, archive, sửa/xoá nhóm, đóng dialog, private lock/unlock |
| Ô nhập và vùng label | vùng chạm hữu dụng ≥44px; chữ ô nhập **≥16px** | `tracker-amount-input`, tên/đơn vị/ghi chú, các input trong `entry-edit-dialog` và `group-form` |
| Khoảng cách đích liền kề | **≥ 8px** | Đo khoảng cách giữa các `DOMRect`, không tính khoảng trống chỉ do nhìn bằng mắt |
| Card/object | toàn vùng card có thể chạm để ghi/mở | Chạm khoảng trống trong card vẫn đi đúng action; nested button không bị click nhầm |
| Tuyệt đối tối thiểu | **không dưới 24 × 24** | Dưới mức này là 🔴 theo WCAG 2.5.8, kể cả khi action không phải primary |
| Cuộn ngang | **0** | `document.documentElement.scrollWidth <= window.innerWidth` tại 390px |
| Popover/dialog | không bị cắt | lớp nổi phải portal đúng; kiểm thêm card cuối màn, không chỉ card đầu |

T3 phải dán bảng đo gồm `selector`, `width`, `height`, `x`, `y`, `gap` và viewport vào báo cáo.
Một test có `toBeVisible()` nhưng không có số đo kích thước chưa đóng được trục này.

### 1.3 WCAG — tập trung vào non-text contrast và focus

| Mục | Ngưỡng/tiêu chí | Cách lấy biên lai |
|---|---:|---|
| Viền input/card có nghĩa | **≥ 3:1** so với nền liền kề | Lấy màu đã render từ computed style/pixel sampler, tính ratio và ghi cặp màu + selector |
| Icon mang nghĩa | **≥ 3:1** | Đo icon archive, sửa, xoá, backdate, lock, warning và icon trạng thái; không coi icon là “trang trí” nếu người dùng dựa vào nó |
| Focus indicator | **≥ 3:1** và nhìn thấy được | Tab qua mọi action ở mobile/desktop; đo vòng focus trên nền card, nền primary và nền dialog |
| Chữ thường | **≥ 4,5:1**; chữ lớn ≥3:1 | Đo lại các label/error/secondary text có màu custom; không suy từ token hoặc mắt nhìn |
| Bàn phím | không bẫy focus; Dialog trả focus về opener | Ghi thứ tự tab, phần tử nhận focus trước/sau dialog và trường hợp focus khi lỗi |
| `aria-live`/`role` | vùng nhỏ, chỉ đọc thông tin cần thiết | Không bọc cả `TrackerScreen`; trạng thái ghi/lỗi không đọc lại toàn màn hình |
| Icon button name | có action + object | Ví dụ “Ghi lùi giờ cho …”, “Lưu trữ …”; kiểm `aria-label` trong DOM thật, không dùng tên hiển thị làm selector |

Đặc biệt không được chỉ đo chữ trên nền. Viền, icon, focus ring và chỉ báo trạng thái là non-text
contrast theo WCAG 1.4.11; thiếu số đo của chúng là `CHƯA verify được`, không phải đạt.

### 1.4 Microcopy tiếng Việt chuẩn

| Quy tắc | Kiểm trên 011a | Tiêu chí đạt |
|---|---|---|
| Đọc tự nhiên | Đọc thành tiếng toàn bộ CTA, empty/loading/error, warning và Undo | Câu là tiếng Việt người dùng thực sự nói; không có “tôi”, không có giọng kỹ thuật |
| Nhãn hành động | Nút tạo/sửa/xoá/lưu/ghi/hoàn tác/thử lại | Ưu tiên động từ + tân ngữ, tối đa 3 từ trong hàng ngang; không dùng chữ mơ hồ như “Xác nhận” nếu chưa nói hành động |
| Lỗi | 403 private, 409 trùng tên, 422 invalid, timeout/network, dashboard corrupted | Nói **điều gì xảy ra + làm gì tiếp**; lỗi form hiện ở nơi đang nhìn, không chỉ trong Dialog đã đóng |
| Empty/loading | Grid, entry list, group list, dashboard | “Chưa có …” khác “Đang tải…” khác “Không tải được …”; không dùng số 0 để giả loading |
| Tiền | 0đ, 100.000đ, 99.999.999.999đ, preview và dashboard | Dấu chấm phân cách kiểu `vi-VN`, hậu tố `₫`, không scientific notation, không nuốt im lặng ký tự người dùng nhập |
| Private | khoá/mở private gate và tracker riêng tư | Không nói ra tên/số lượng/tổng của dữ liệu đang bị khoá; thông báo khoá phải đủ để chủ biết cách mở lại |
| Undo | toast sau ghi/xoá | “Hoàn tác” là hành động rõ; không biến toast thành hộp xác nhận; copy không hứa thời lượng khác contract |

Assertion trên text được phép để kiểm microcopy, nhưng selector để bấm/định vị test phải là
`data-testid`/role/thuộc tính id, không bám vào câu tiếng Việt.

## 2. Ma trận Màn × Trạng thái

Mỗi ô dưới đây là một lần kiểm thật. `N/A` chỉ được ghi khi surface không được mount theo đúng
thiết kế, kèm lý do; không được dùng `N/A` để bỏ qua trạng thái có thể tạo bằng fixture.

| Màn/bề mặt | Rỗng | Đang tải | Có dữ liệu | Lỗi | Tràn số tiền / nội dung dài |
|---|---|---|---|---|---|
| `CaptureGrid` | DB/mock không có tracker: hiện empty state có đường tới “Tracker mới”; không có nút ma, không nhầm với loading | Chưa có `data`: hiện loading/status, không hiện “Chưa có tracker nào” như thể đã tải xong | Có 3–30+ tracker; thứ tự đúng; sau ghi thứ tự không đổi dưới ngón tay; lưới cuộn dọc, không ngang | GET trackers/groups lỗi: alert nằm trên màn + “Thử lại”; retry thành công render lại grid; không để lỗi trong Dialog đã đóng | Tên 70 ký tự không dấu cách, tiếng Việt dấu dày, emoji; grid vẫn `scrollWidth <= innerWidth`; money card không làm card/CTA tràn |
| `TrackerCard` | Không có card khi grid rỗng; không render placeholder có thể bấm | Với mutation pending: nhãn `Đang ghi…`, nút bị khoá, một request duy nhất; money input pending cũng bị khoá | `event` bấm một lần ghi; `money` mở đúng một input; `quantity` hiện unit; A1 hiện lần cuối; long-press mở ghi lùi giờ và không sinh click thứ hai | POST/PATCH/Undo lỗi: action mở lại được, lỗi có hướng xử lý; không mất input chưa gửi; toast/alert vẫn thấy khi Dialog liên quan đã đóng | `0`, `100.000`, `99.999.999.999`; preview đúng số gửi; format không scientific; tên dài wrap được, không cắt mất nút |
| `EntryEditDialog` | Không có `entry` thì dialog không mount; không thể mở dialog rỗng từ list; field optional vẫn phân biệt rỗng hợp lệ/invalid | Submit đổi nhãn `Đang lưu…`, giữ focus và không double-submit; dialog chỉ đóng sau success | Mở từ `entry-row`, sửa thời điểm/tiền/giá gốc/số lượng/note; gửi datetime có `+07:00`; không cho đổi `tracker_id`; focus trả opener | Ép PATCH lỗi khi dialog đang mở và sau khi đóng; lỗi phải ở page-level toast/alert còn thấy, form không mất dữ liệu, có bước retry/sửa | Amount/list amount ở ba giá trị bắt buộc; ghi chú 150 ký tự dấu dày/emoji; dialog không bị cắt và bàn phím không che field đang gõ |
| `GroupForm` | Tên rỗng/toàn khoảng trắng: submit disabled, không POST; DB rỗng vẫn tạo được group mới từ CTA | Nút đổi `Đang lưu…`, controls disabled, đúng một POST/PATCH; không đóng form sớm | Tạo/sửa đúng `kind`; sửa không cho đổi kind; group count cập nhật; xoá group có xác nhận và tracker chuyển “Chưa nhóm” | 409 trùng tên, 422/timeout/network: thông báo nguyên nhân + bước tiếp theo; giữ giá trị đang nhập; retry không đẻ nhóm thứ hai | Tên group 70 ký tự, tiếng Việt 150 ký tự dấu dày, CHỮ HOA CÓ DẤU, emoji; form wrap và không tràn ngang |
| `DashboardPanel` | Dashboard `200` với không có entry: hiện số 0/empty phù hợp, không 404, không gắn lỗi; F1–F5 và A3/A4 không bị bỏ bằng cách im lặng | Có panel loading/status; không hiển thị số cũ như số hiện tại nếu query chưa settle; không nhầm loading với rỗng | Kiểm A1–A4/F1–F5 với fixture biết trước; private lock loại dữ liệu private; archive vẫn giữ entry trong F1–F5; F4 sort sau giải mã | Dashboard lỗi hoặc một ciphertext hỏng: alert + retry; ciphertext hỏng không làm trắng cả panel, có cảnh báo số liệu có thể thiếu; lỗi đọc một entry riêng vẫn khác lỗi aggregate theo contract | Tổng và top entry với `0`, `100.000`, `99.999.999.999`; định dạng đúng, không overflow; 30+ entry không cắt F4/scroll ngang |

### 2.1 Checkpoint riêng tư áp cho cả ma trận

Tạo một tracker `is_private=true` và ít nhất một entry khi private gate đang mở. Sau đó:

1. bấm khoá private gate;
2. kiểm `CaptureGrid`, `TrackerCard`, entry list và `DashboardPanel` không còn tên, entry, tổng hoặc
   dấu hiệu cho biết có bao nhiêu dữ liệu private;
3. không dùng URL/query/selector để suy ra tên hidden từ response đã bị lọc;
4. bấm mở khoá bằng luồng UI thật, không gọi API bypass;
5. kiểm tracker, entry và số liệu quay lại đúng, không tạo bản ghi trùng;
6. đo độ trễ từ thao tác lock/unlock tới UI cập nhật và ghi số đo thật.

Không cố ý nhập sai PIN đủ ngưỡng trên production. Nếu cần kiểm một lần lỗi PIN, chỉ nhập sai một
lần rồi dừng; throttle toàn cục không phải dữ liệu test có thể reset tuỳ ý.

### 2.2 Lỗi phải sống sau khi Dialog đóng

Đây là ô bắt buộc, không được bỏ qua vì “toast bình thường đang hiện”. T3 phải:

- giữ request create/update/delete pending bằng route delay;
- đóng `EntryEditDialog`, `GroupForm` hoặc dialog archive trong lúc request chưa settle;
- trả lỗi 409/422/500 hoặc timeout;
- kiểm có `role="alert"` hoặc toast ở document-level, có nội dung hành động được;
- kiểm nút/form không bị kẹt `pending` vĩnh viễn và dữ liệu người dùng đã nhập không biến mất vô lý.

Nếu chỉ nhìn thấy lỗi khi dialog mở, ghi 🔴 với selector và thời điểm; không hạ thành “khó chịu”.

## 3. Bộ dữ liệu test bắt buộc

Fixture phải tái tạo được qua `frontend/e2e/fixtures/tracker.ts` và phải reset giữa test. Khi QA
production, tạo dữ liệu tương đương nhưng không xoá dữ liệu người dùng. Mọi số dưới đây là giá trị
đầu vào/đầu ra phải ghi nguyên văn trong report.

| ID dữ liệu | Dữ liệu bắt buộc | Dùng ở đâu | Kỳ vọng kiểm được |
|---|---|---|---|
| D-01 | Tên **70 ký tự liên tục, không khoảng trắng** | tracker, group, entry note nếu có | Wrap được; không đẩy action khỏi màn; không làm `scrollWidth` vượt viewport; lưu/đọc lại nguyên chuỗi |
| D-02 | Tiếng Việt khoảng 150 ký tự, dấu dày (`ế ữ ộ ằ`), có xuống dòng nếu phù hợp | tracker/group name, note, error/empty copy | Dấu không chồng/cắt; chiều cao tự giãn; không dùng chiều cao cứng để che lỗi |
| D-03 | **CHỮ HOA CÓ DẤU** | card, form, dashboard F3/F4 | Font Nunito đọc được; không overflow; contrast vẫn đủ |
| D-04 | Emoji trộn chữ và một ký tự đơn | tracker name, group name, note | Render ổn, không mất glyph; không làm icon/action lệch |
| D-05 | Chuỗi toàn khoảng trắng và khoảng trắng hai đầu | GroupForm, TrackerForm, EntryEditDialog note | Trim/validation đúng; submit trắng bị chặn; không có request invalid; field hợp lệ khác không bị xoá ngoài ý muốn |
| D-06 | Tiền **0đ** (`0`) | money tracker, EntryEditDialog, dashboard | 0 là giá trị hợp lệ; echo `0 ₫`; không bị coi là empty/false; F1/F5 cộng đúng |
| D-07 | Tiền **100.000đ** (`100000`) | money capture, edit, F1/F2/F3/F4/F5 | Echo và display `100.000 ₫`; payload là số `100000`; không dùng chuỗi đã format để gửi |
| D-08 | Tiền **99.999.999.999đ** (`99999999999`) | money capture, list amount, top-5/dashboard | Không scientific notation, không làm vỡ card/dialog; cộng và sort đúng bằng Decimal/server contract |
| D-09 | Một `list_amount` khác `amount`, gồm cả `list_amount=0` | EntryEditDialog, entry row, F3/F4 nếu hiển thị | Không trộn giá gốc với giá thực trả; không tự thêm toggle `app_setting` trong 011a |
| D-10 | Private tracker + entry, gate **lock → unlock** | grid, card, entry list, dashboard | Lock ẩn qua cổng cha; unlock hiện lại; không lộ existence/name/tổng; không tạo trùng khi refresh |
| D-11 | Undo banner: ghi entry tại `t=0`, kiểm ở **t≈5s** | toast/banner + list/dashboard | Banner/action còn thấy và bấm được; click Undo soft-delete/restore đúng entry; kiểm tiếp `t>10s` action hết hạn theo contract hiện hành |
| D-12 | Ít nhất **30 tracker/entry**; tối thiểu 3 item trễ hạn/rải rác; hỗn hợp event/money/quantity, private/public, archived/live | grid, entry list, dashboard | Không chỉ kiểm “Item 1..5”; kiểm card cuối màn, scroll dài, banner/alert, thứ tự ổn định và aggregate không mất item |
| D-13 | Một entry ciphertext hỏng trong aggregate fixture | Dashboard | Dashboard vẫn `200`, báo số bản ghi hỏng và số liệu còn lại đúng; không log ciphertext/secret; đường đọc một entry hỏng giữ đúng contract lỗi riêng |
| D-14 | Thời gian hôm qua, 2 giờ trước, custom datetime-local và tháng rỗng | backdate, EntryEditDialog, dashboard | Request có offset `+07:00`; hiển thị theo `Asia/Ho_Chi_Minh`; tháng hợp lệ rỗng trả 0/empty, không 404 |

### 3.1 Quy tắc tạo fixture và đối chiếu

- Mỗi tracker/entry/group có UUID test ổn định và truyền id qua `data-tracker-id`, `data-entry-id`,
  `data-group-id`; không nhét id vào `data-testid`.
- Fixture phải có state chuyển được: POST tạo, PATCH sửa, DELETE soft-delete, POST restore. Nếu
  mock chỉ trả response tĩnh thì không thể chứng minh Undo, private round-trip hoặc double-submit.
- Dashboard fixture phải có tổng đã tính trước cho F1–F5 và một expected snapshot JSON. T3 dán cả
  response thực tế lẫn expected diff; không chỉ kiểm `toBeVisible()`.
- Với private gate, fixture phải lọc giống server: lock không trả row private. Không “giấu bằng CSS”
  rồi tuyên bố privacy pass.
- Với lỗi, route phải có mode `delay`, `network-failure`, `409`, `422`, `500`; report ghi mode và
  request count.

## 4. Kịch bản Playwright e2e suite & `data-testid` convention

### 4.1 Harness và lệnh chạy

Playwright dùng preview build và fixture API deterministic. Giữ `serviceWorkers: 'block'` trong
harness hiện có để route mock không bị service worker làm nhiễu; điều đó không thay thế kiểm tra
service worker/production trên browser thật.

Chạy đúng thư mục `frontend`:

```powershell
cd frontend
npm run e2e -- --list
npm run e2e -- --project=mobile e2e/tracker.spec.ts
npm run e2e -- --project=desktop e2e/tracker.spec.ts
```

`--list` chỉ chứng minh test được discover. Acceptance cần output của lần test thực thi ở cả mobile
và desktop. Mỗi test phải độc lập, không dựa vào thứ tự test trước, không gọi API thật ngoài scope
fixture; nếu route mock không match thì fail loud thay vì fallback âm thầm sang một backend không
được kiểm soát.

### 4.2 Bộ scenario tối thiểu

| Mã | Scenario | Assertions máy bắt buộc |
|---|---|---|
| PW-01 | Empty/loading grid + dashboard | `tracker-grid-empty`, `tracker-grid-loading`, `dashboard-empty`, `dashboard-loading` phân biệt đúng; không có request POST |
| PW-02 | Load error + retry | `tracker-grid-error`/`dashboard-error` hiện; retry phát đúng GET; success render lại; alert có hướng xử lý |
| PW-03 | Create group/tracker từ DB rỗng | Submit whitespace không request; dữ liệu hợp lệ POST đúng một lần; dialog đóng sau success và item xuất hiện |
| PW-04 | One-tap event | Click `tracker-button` một lần ⇒ đúng một POST entry, đúng `tracker_id`, toast Undo hiện; grid order không đổi |
| PW-05 | Money 0/100000/99999999999 | Input chỉ nhận digit; preview khớp payload; mỗi giá trị tạo đúng một entry; display không overflow |
| PW-06 | Quantity và unit | Input/unit đúng; thiếu giá trị bị chặn; entry payload không có amount; submit không double-fire |
| PW-07 | Long-press | Dispatch `touchstart` → chờ 500ms → `touchend`; backdate dialog hiện; submit tạo đúng một entry có `+07:00`; synthetic click không tạo entry thứ hai |
| PW-08 | Undo checkpoint | Sau capture, ở t≈5s `undo-banner` + `undo-action` visible/enabled; click gọi DELETE/restore đúng id; sau t>10s action biến mất theo contract |
| PW-09 | Edit entry | Mở đúng row; sửa time/money/list amount/quantity/note; PATCH đúng id; không có `tracker_id` trong payload; success trả focus về opener |
| PW-10 | Error sau khi đóng dialog | Delay mutation, đóng dialog, trả 409/422/500; page-level alert/toast vẫn visible; form mở lại không mất input; retry có request mới |
| PW-11 | Group CRUD + delete confirmation | Tạo/sửa/xoá đúng; kind edit không đổi; delete cần confirm; tracker con chuyển “Chưa nhóm”; cancel không mutates |
| PW-12 | Private lock/unlock | Lock làm private row biến mất khỏi fixture response/UI và dashboard; unlock hiện lại đúng id; không lộ tên qua empty/error copy |
| PW-13 | Dashboard exact snapshot | F1–F5/A2–A4 khớp expected JSON; empty = 0; corrupted count/warning đúng; F4 top-5 đúng thứ tự |
| PW-14 | 30+ records + long content | Card/list cuối màn render; `scrollWidth` không vượt; không action nào chỉ hover; mobile và desktop đều tới được |
| PW-15 | Geometry/accessibility smoke | Evaluate tất cả selector interactive: rect ≥44; gap ≥8; input font ≥16; focus traversal không bẫy; aria-label có object |

### 4.3 Quy ước `data-testid`

`data-testid` là thuộc tính test thuần: không dùng làm CSS/style hook, không chứa id, không đổi
theo microcopy. Nếu DOM hiện tại thiếu một testid trong bảng, T2 phải thêm testid trước khi giao
T3; T3 không được thay bằng selector chữ tiếng Việt rồi coi là tương đương.

| Surface | `data-testid` bắt buộc | ID riêng đi kèm |
|---|---|---|
| Screen/grid | `tracker-screen`, `tracker-grid`, `tracker-grid-empty`, `tracker-grid-loading`, `tracker-grid-error`, `tracker-grid-retry` | — |
| Card/capture | `tracker-card`, `tracker-button`, `tracker-last-seen`, `tracker-amount-input`, `tracker-amount-preview`, `tracker-backdate`, `tracker-backdate-dialog`, `tracker-backdate-submit` | `data-tracker-id` |
| Tracker form | `tracker-form`, `tracker-name-input`, `tracker-kind-select`, `tracker-input-mode-select`, `tracker-direction-select`, `tracker-group-select`, `tracker-private-toggle`, `tracker-form-submit`, `tracker-form-error` | `data-tracker-id` khi edit |
| Group form | `group-form`, `group-name-input`, `group-kind-select`, `group-form-submit`, `group-form-cancel`, `group-form-error` | `data-group-id` khi edit |
| Entry list/edit | `entry-row`, `entry-edit`, `entry-undo`, `entry-edit-dialog`, `entry-edit-time-input`, `entry-edit-amount-input`, `entry-edit-list-amount-input`, `entry-edit-quantity-input`, `entry-edit-note-input`, `entry-edit-submit`, `entry-edit-cancel`, `entry-edit-error` | `data-entry-id`, `data-tracker-id` |
| Dashboard | `dashboard-panel`, `dashboard-empty`, `dashboard-loading`, `dashboard-error`, `dashboard-retry`, `dashboard-corrupt-warning`, `dashboard-f1-total`, `dashboard-f2-compare`, `dashboard-f3-group`, `dashboard-f4-top`, `dashboard-f5-net`, `dashboard-a2-gap`, `dashboard-a3-counts`, `dashboard-a4-trend` | `data-entry-id`/`data-tracker-id` khi dòng metric cần drill-down |
| Undo | `undo-banner`, `undo-action` | `data-entry-id` |
| Private gate | Kế thừa testid đã có: `private-lock-now`, `private-unlock-open`, `private-pin-input`, `private-unlock-submit`, `private-error` | Không đưa PIN/id vào testid |

Các selector có nhiều instance phải scope theo root + id, ví dụ:

```ts
page.locator('[data-testid="tracker-card"][data-tracker-id="tracker-001"]')
  .getByTestId('tracker-button')
page.locator('[data-testid="entry-row"][data-entry-id="entry-001"]')
  .getByTestId('entry-undo')
```

Không dùng `getByText('Hoàn tác')` để bấm action; được phép assert text “Hoàn tác” trong một
`undo-banner` đã định vị bằng testid. Testid trùng ở card/dialog chỉ hợp lệ khi đã scope rõ và
không tạo ambiguous locator toàn trang.

### 4.4 Red-proof bắt buộc cho guardrail chính

Mỗi guardrail dưới đây phải có một lượt chứng minh **biết đỏ** ở local/throwaway branch hoặc patch
tạm thời chưa commit, sau đó hoàn nguyên và chạy xanh lại. Không dùng source review thay cho log đỏ.

| Guardrail | Cố ý phá tạm thời | Output đỏ phải chỉ đúng lỗi | Sau hoàn nguyên |
|---|---|---|---|
| Long-press không tạo hai entry | Bỏ cờ suppress synthetic click/`preventDefault` | PW-07 thấy count = 2 thay vì 1 | PW-07 xanh, count = 1 |
| Private gate không rò | Bỏ filter private trong fixture/UI | PW-12 thấy private name/row khi locked | PW-12 xanh, row biến mất |
| Echo tiền | Bỏ preview hoặc đổi preview không theo payload | PW-05 không thấy đúng `= 100.000 ₫`/payload mismatch | PW-05 xanh với cả ba giá trị |
| Error không mất khi đóng Dialog | Chỉ render lỗi trong Dialog | PW-10 không tìm được page-level alert sau close | PW-10 xanh, lỗi có action |
| Chống overflow | Bỏ wrap/đổi layout làm long token tràn | PW-14 đo `scrollWidth > 390` hoặc rect action ra ngoài | PW-14 xanh, scroll ngang = 0 |
| Touch target | Tạm hạ một action xuống dưới 44px | PW-15 in đúng selector và kích thước dưới ngưỡng | PW-15 xanh, tất cả đạt |

Patch phá phải được ghi rõ là tạm thời, không commit/push/merge. Nếu môi trường không cho chạy
red-proof, ghi `CHƯA verify được`, không đổi thành “đã test”.

### 4.5 Browser acceptance ngoài Playwright

Sau suite mock, T3 phải chạy flow tương đương trên production bằng Chrome DevTools/profile được
phép và iPhone thật. Không đọc cookie/password/profile store. Phải kiểm:

- `window.innerWidth` thật, touch target, keyboard/safe-area và không scroll ngang;
- production cookie/session/private gate, không chỉ response mock;
- lock/unlock round-trip và dashboard sau refetch;
- một lượt sử dụng lại app sau vài phút hoặc ngày khác nếu có thể, vì lỗi layout/state có thể chỉ
  xuất hiện ở lần dùng thứ hai;
- screenshot checkpoint nếu T1 yêu cầu taste axis: ≥30 mục ở 390px + 1280px, dialog/long content,
  private locked, private unlocked. Mỗi ảnh phải có mô tả banner/chữ ở đầu trang và hash MD5 trước
  khi đọc nhận xét; ảnh trùng hash không được tính là hai checkpoint.

## 5. Biên lai nghiệm thu máy kiểm được

### 5.1 Artifact và định dạng report

Spec này là DRAFT và không được biến thành log kết quả bằng cách ghi đè. Khi chạy QA, append-only
vào `agent-tasks/011a-qa-results.md`, mỗi lô giữ đủ:

**(a) Đã soi những gì** — màn × trạng thái × viewport × môi trường × fixture/data id.

**(b) Phát hiện** — bảng có đúng các cột:

| # | Trục (Nielsen/HIG/WCAG/Microcopy) | Mức | Chỗ (`file:line` hoặc selector) | Số đo/raw output | Đề xuất |
|---|---|---|---|---|---|

**(c) Ảnh + taste** — path ảnh, hash, một câu mô tả banner/chữ đầu trang và 2–4 câu nhận xét.
Taste không được trộn vào bảng pass/fail của bốn trục.

Mọi kết luận trong report phải tách rõ:

- **Đã chạy:** dán output thật, không tóm tắt;
- **CHƯA chạy:** ghi lane và lý do cụ thể;
- **SUY LUẬN:** chỉ dùng để giải thích vì sao vẫn tin, không dùng để tick acceptance.

### 5.2 Lệnh và output tối thiểu

Chạy đúng thư mục và dán raw output tương ứng. Các lệnh dưới đây là receipt bắt buộc, không phải
gợi ý:

| Lane | Lệnh | Receipt đạt |
|---|---|---|
| Spec structure | `rg -n "Executor: T3|Bậc: L2|Effort: high|Trạng thái: DRAFT|^## [0-5]\." agent-tasks/011a-qa-tracker-slice.md` | Header và đủ mục 0–5 xuất hiện đúng file |
| Markdown whitespace | `git diff --check -- agent-tasks/011a-qa-tracker-slice.md` | Exit code 0, không output lỗi |
| Frontend lint | `cd frontend; npm run lint` | Exit code 0 và raw summary của ESLint |
| Frontend build | `cd frontend; npm run build` | Exit code 0; build production hoàn tất |
| Frontend unit/type | `cd frontend; npm test` | Exit code 0; không chỉ `tsc` riêng nếu script này là contract hiện hành |
| E2E discovery | `cd frontend; npm run e2e -- --list` | Có đủ PW-01…PW-15 hoặc danh sách test tương đương, không “0 tests” |
| Playwright mobile | `cd frontend; npm run e2e -- --project=mobile e2e/tracker.spec.ts` | Exit code 0, raw pass count, không bỏ qua test bằng `.skip` |
| Playwright desktop | `cd frontend; npm run e2e -- --project=desktop e2e/tracker.spec.ts` | Exit code 0, raw pass count |
| Backend contract | `cd backend; uv run ruff check` và `uv run pytest` | Exit code 0; nếu PG lane chưa chạy phải ghi riêng, không gộp thành xanh |
| PG/API thật | Lệnh PG/pytest theo `agent-tasks/011a-tracker-capture-dashboard.md` §7 và môi trường đã bật | Có raw response/status cho money/privacy/dashboard/corruption; Docker/Neon chưa sẵn thì `CHƯA verify được` |
| Geometry | Playwright `evaluate(getBoundingClientRect)` ở 390px | Bảng selector/width/height/gap; không chỉ ảnh chụp |
| Contrast | Script/DevTools lấy computed color/pixel + tính ratio | Mọi non-text/focus ≥3:1 và text theo ngưỡng; dán cặp màu + ratio |
| Red-proof | Chạy từng test ở trạng thái guardrail bị phá rồi hoàn nguyên | Có log đỏ đúng assertion + log xanh sau restore cho PW-05/PW-07/PW-10/PW-14/PW-15 hoặc ghi lane chưa chạy |
| Production | Chrome thật trên `microsched.fly.dev` + iPhone thật | Có viewport `innerWidth`, số đo touch/scroll, lock/unlock, trạng thái từng matrix; local mock không thay receipt này |

Nếu một lệnh timeout, trước khi kết luận thất bại phải kiểm trạng thái thật trên đĩa/process/image
theo `CLAUDE.md`; không xoá cache hay reset worktree để che dấu. Nếu retry vẫn bị cùng một lỗi môi
trường sau khoảng hai vòng, dừng lane và ghi đúng lỗi raw.

### 5.3 Definition of Done cho QA 011a

Chỉ báo cáo **QA pass** khi tất cả điều kiện sau có biên lai:

1. đủ ma trận năm surface × năm trạng thái ở §2, có ghi `N/A` hợp lệ khi cần;
2. đủ D-01…D-14, trong đó ba giá trị tiền và private lock/unlock/Undo checkpoint đều có output;
3. Playwright mobile và desktop đều thực thi, không chỉ discover; PW-07 chứng minh long-press một
   entry; PW-10 chứng minh lỗi sống sau khi đóng Dialog; PW-12 chứng minh không rò private;
4. mọi action interactive trên 390px đạt HIG ≥44px hoặc có finding rõ; không có action dưới 24px;
   non-text contrast/focus có số đo ≥3:1;
5. có red-proof cho guardrail chính và green rerun sau hoàn nguyên;
6. production browser + ít nhất một lượt iPhone thật đã chạy. Nếu không có lane này, trạng thái là
   **partial/unverified**, dù lint, build, unit và mock e2e đều xanh;
7. CI của PR code (nếu có) giữ nguyên tên required check hiện hành: `Backend checks`, `Frontend
   checks`, `Repository hooks`, `Migration QA`, `Production dependency check`; chờ check thật xanh
   trước khi nói hoàn thành.

Không được đóng QA bằng các bằng chứng sau: đọc source mà không chạy browser; `npm run e2e -- --list`
không có execution; screenshot không có hash/mô tả; một lượt local build; hoặc lời khai của agent
không kèm raw output/selector/số đo.
