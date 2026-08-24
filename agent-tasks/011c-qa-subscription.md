# Kịch bản QA (QA Framework Specification) — 011c Đăng ký định kỳ

**Đối tượng:** Giao diện Quản lý Đăng ký định kỳ (Spec 011c).
**Mục tiêu:** Áp dụng nghiêm ngặt docs/qa-framework.md (4 trục Nielsen/HIG/WCAG) và luật UI (docs/ui-brief.md) để nghiệm thu phần frontend/tương tác của tính năng.

---

## (a) Ma trận màn hình × Trạng thái (Phạm vi cần soi)

Người chạy QA phải đi qua toàn bộ các giao cắt này trên Viewport **390 × 844** (ưu tiên) và **1280 × 800**:

1. **SubscriptionScreen (Danh sách đăng ký & Cài đặt F6):**
   - **Rỗng (Empty state):** Không có đăng ký nào.
   - **Đang tải (Loading):** Khung skeleton khi vừa vào tab.
   - **Lỗi tải (Error):** Lỗi mạng/backend từ chối.
   - **Nội dung dài (30+ sub):** Cuộn danh sách, test performance và hiển thị.
   - **Deep-link (?highlight=):** Cuộn tới thẻ đúng ID, URL xấu (chứa ký tự lạ, thoát HTML).
   - **Cài đặt list_price toggle (Bật/Tắt):** F6 ẩn/hiện giá gốc và thẻ danh sách phản hồi.
   - **Khóa bảo mật (Private-gated):** Tracker cha bị khóa ẩn → Danh sách rỗng, F6 biến mất (không rò rỉ).
   - **Lead-days (0-30 và ngoài biên):** Gõ 0, 3, 30 và 31 (báo lỗi hoặc backend kẹp về biên).

2. **RenewDialog (Form gia hạn/Thêm/Sửa):**
   - **Trạng thái Validation:** Ngày kết thúc < Ngày bắt đầu, tên siêu dài, số tiền rất lớn.
   - **Đang gửi (Submitting):** Trạng thái vô hiệu hóa nút bấm chống double-click.
   - **Lỗi gửi (Submit Error):** Báo lỗi Validation từ server, lỗi amount hỏng.
   - **Đóng form khi đang gửi/lỗi:** Lỗi hiện ra ngoài dialog hay bị nuốt mất?
   - **Offline/Chập chờn:** Double-submit phải idempotent.
   - **Tương tác ngày cuối tháng:** Chu kỳ mốc 31/01 sang 28/02.
   - **Tracker guard 422:** Đổi loại tracker khi đang gắn sub.
   - **Gia hạn Lapsed (Hết hạn dài ngày):** Kiểm tra hành vi kẹp ngày gia hạn về mốc tương lai (vô hiệu hóa kẹt mốc quá khứ từ UI).

3. **Dashboard F6 (Widget tổng hợp):**
   - **Trạng thái Sub:** Hỗn hợp (Active, Canceled, Expired, Auto_renew true/false). Chỉ Auto_renew true mới tính vào burn-rate.

---

## (b) Tiêu chí QA đo được (Hard Metrics)

Trả về **Đạt/Không đạt kèm số đo**, không dùng cảm nhận.

- **Non-text contrast ≥ 3:1:** Áp dụng cho viền ô nhập (Input border), vòng focus (Focus ring), icon trạng thái (ví dụ: chuông báo, icon lịch), thẻ card. Đo bằng mã màu hex.
- **Microcopy & Màu chữ:** Chữ nhạt nhất không dưới mức contrast 4.5:1 với nền.
- **Đích chạm (Touch Targets):** Đích chạm chính (Nút Ghi gia hạn, Nút Quay lại, Toggle) phải **≥ 44×44px**. Tối thiểu cho các icon nhỏ là **≥ 24×24px**. Khoảng cách giữa các vùng chạm **≥ 8px**.
- **Kích thước font & Input:** Chữ không nhỏ hơn **12px**. Text input **≥ 16px** (chống iOS tự zoom).
- **Theme:** Ràng buộc **Light-only**. Không tự kích hoạt chế độ tối, không xám đen ngược màu.
- **Tương tác:** Không có tương tác nào **chỉ-hover** (Hover-only) trên mobile. Mọi menu/popover/dropdown phải mở bằng cú chạm.
- **Cấu trúc Component:** Không sử dụng <button>, <input>, <select> thô. Bắt buộc bọc qua @/components/ui.
- **Màu sắc:** Không hardcode màu HEX, RGB trong inline style hoặc class Tailwind (ví dụ g-[#ff0000]), bắt buộc dùng Design Token từ index.css.
- **Cuộn ngang (Horizontal Scroll):** Tuyệt đối **0 cuộn ngang** ở chiều rộng 390px. Kiểm chứng bằng document.documentElement.scrollWidth.
- **Portal Popover/Dialog:** Phải render ở gốc DOM (body/portal), kiểm tra thẻ cuối cùng của DOM tree khi mở Dialog để tránh bị container overflow cắt cụt.
- **Hành vi Toast/Undo:** Toast và nút Undo kéo dài **10 giây** (không tắt sớm trước khi người dùng kịp tương tác).

---

## (c) Bộ dữ liệu test bắt buộc

1. **Dữ liệu ác ý (Malicious):**
   - Tên đăng ký: Chuỗi 70 ký tự không dấu cách (AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA).
   - Tên có dấu tiếng Việt dày đặc: Nguyễn Vĩ Cường Hỗ Trợ Đăng Ký Ở Chỗ Này Để Xem Nó Có Lỗi Hay Không Nhé A Ă Â E Ê O Ô Ơ.
   - Toàn CHỮ HOA CÓ DẤU, chứa Emoji 🚀💸, toàn khoảng trắng (     ).
2. **Dữ liệu thực tế (Realistic):**
   - Bơm **≥ 30 subscriptions** để tạo vùng cuộn vượt quá màn hình đầu tiên (off-screen).
   - Có ít nhất **3 đăng ký sắp hết hạn** nằm rải rác.
   - Trộn lẫn 3 trạng thái: ctive, canceled, expired.
   - Số tiền: 99,999,999,999 (định dạng VND lớn không tràn khung).
   - Ngày cắt: Thiết lập ngày bắt đầu là **31/01**, bấm gia hạn 1 tháng để kiểm chứng có tự kẹp về **28/02** không, hay gây crash/nhảy cóc.

---

## (d) Checklist Playwright data-testid

Cần đảm bảo file rontend/e2e/subscription.spec.ts phủ sạch các selector sau (viết test assert chạy CI):
- **Màn hình chính:** [data-testid="subscription-screen"], [data-testid="subscription-empty"].
- **Thẻ đăng ký:** [data-testid="subscription-card"].
- **Điều hướng & Cửa sổ:** Nút Quay lại test hành vi
avigate('/') bằng cách kiểm tra history chiều về không bị lặp vô hạn.
- **Deep-link highlight:** Kiểm tra ?highlight=id không đụng querySelector bẩn (tránh injection), và phải gọi script kiểm tra cuộn (scroll) thực sự.
- **Form Cài đặt:** [data-testid="settings-list-price-toggle"], [data-testid="settings-expiry-lead-days"]. Toggle phải phản ánh ngay trên UI mà không cần tải lại trang.
- **Form Gia hạn:** [data-testid="subscription-renew-form"].
- **Bảng tổng hợp trước submit:** [data-testid="subscription-renew-summary"] có hiển thị review trước khi nhấn Ghi.
- **An toàn Submit:** Double-submit (nhấn phím Enter + Click hoặc Click đúp nút [data-testid="subscription-renew"]) phải bắt được cơ chế Idempotent 200, tạo đúng duy nhất 1 lần entry.
- **Bắt lỗi Server ngoài Dialog:** Test bắt 	oast lỗi server (Renew-error như amount hỏng) hiển thị nổi lên màn hình chính nếu form đóng.
- **Hoàn tác (Undo):** [data-testid="subscription-cancel"] -> bấm nút Hủy -> Bấm Hoàn tác ở Toast -> Cố ý ngắt kết nối mạng hoặc chặn lỗi để sinh lỗi Undo restore error và quan sát có báo lỗi Toast đỏ không.

---

## (e) Định dạng báo cáo QA (§7 + §8)

Viết nối (append) theo từng lô thực thi vào một file kết quả, chỉ định rõ thiết bị và môi trường thử nghiệm:

**(a) Đã soi những gì:**
(Ví dụ: SubscriptionScreen, Viewport 390x844, Trạng thái: nội dung dài 30+, URL highlight chứa tag HTML, double-submit chập chờn mạng).

**(b) Phát hiện (Findings):**
Bảng gồm 6 cột bắt buộc:

| # | Trục (3.A/B/C/D) | Mức (🔴/🟡/⚪) | Chỗ (ile:line hoặc selector) | Số đo (px, tỉ lệ, hex) | Đề xuất sửa chữa |
|---|---|---|---|---|---|
| 1 | 3.A (Mobile HIG) | 🔴 | [data-testid="subscription-renew"] | 20x40px | Mở rộng padding để đích chạm ≥44x44 |

**(c) Trục 3.E (Thẩm mỹ, Layout) + Hình ảnh Screenshot (Kèm md5sum):**
- Bắt buộc chụp ảnh thực tế độ phân giải **390x844** (viewport ưu tiên) và **1280x800**.
- **Luật chống ảo giác:** In ra md5sum của từng file ảnh TRƯỚC KHI viết nhận xét để đối chiếu. File trùng hash = nội dung trùng.
`
![Lỗi chữ đè viền - 390x844](screenshots/011c-mobile-error.png)
md5sum: 12ab34cd56ef7890...
Nhận xét: padding-bottom ở thẻ card màn hình nhỏ đang hiển thị sát viền chữ (đo = 2px thay vì 8px).
`

**(d) Áp dụng Luật Đọc §8 (Dành cho T1):**
- Mọi mục finding KHÔNG chứa **Số đo** hoặc **Chỗ (ile:line/selector)** sẽ bị gạt bỏ hoàn toàn (không nghiệm thu).
- T3/T2 chạy QA là cố vấn đo đạc (Cung cấp Metric). T1 là người duyệt chốt cuối.
