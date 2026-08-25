# QA SPEC — Đợt nâng cấp UI/UX 022 (Dogfooding Polish)

> **Trạng thái:** DRAFT · Ngày tạo: 2026-08-25
> **Commit gốc:** bbbd52d (feat/022-dogfooding-ux-polish, PR #173)
> **Thiết bị mục tiêu:** iPhone Safari (chính), Chrome desktop (phụ)
> **Quy trình QA:** Post-Cutover Neon Ephemeral Branch (§9 AGENTS.md)

---

## 1. Mục tiêu

Xác nhận 5 nhóm tính năng trong đợt polish 022 hoạt động đúng trên cả mobile
và desktop, không phá vỡ hành vi cũ, và tuân thủ hệ thiết kế đã chốt
(docs/ui-brief.md).

| # | Nhóm | Phạm vi |
|---|------|---------|
| A | Calendar View | Date Cell border revert, Sticky Header 2 tầng, Xoá task/buổi |
| B | Note và Lời nhắn tương lai | Speech Bubble Callout, Icon Sửa/Xoá, Nút gửi lời nhắn |
| C | Tracker Tab | Khối Tài chính, so sánh cùng kỳ, Lưới ghi nhanh gom nhóm |
| D | Bảng màu 1-chạm | 5 chấm màu curated + nút Sửa nguồn lịch |
| E | Quy trình QA | Ephemeral Neon Branch, Data Scrambler, bypass OAuth |

---

## 2. Ma trận trạng thái (State Matrix)

### 2.1 Calendar View — DayCell Border

| Trạng thái | Điều kiện | Kỳ vọng border |
|------------|-----------|----------------|
| Ngày hôm nay | isToday === true | border-primary bg-accent |
| Ngày khác cùng tháng | isToday === false | border-transparent — KHÔNG viền mỏng |
| Đang kéo thả vào | isDragOver === true | border-primary bg-primary/10 ring-2 |
| Ô tháng khác (padding) | isSameMonth === false | opacity-0 pointer-events-none |

### 2.2 Sticky Header

| Tầng | Nội dung | Hành vi khi cuộn |
|------|----------|------------------|
| Tầng 1 | Tháng/Năm + Nút Hôm nay + Quick Task Bar (desktop) | Sticky top-0 z-10 |
| Tầng 2 | 7 nhãn thứ: T2 T3 T4 T5 T6 T7 CN | Cố định dưới Tầng 1 |

### 2.3 Xoá trong DayDetailDialog

| Đối tượng | Cơ chế | Toast hoàn tác | Duration |
|-----------|--------|----------------|----------|
| Task | Trash2 rồi DELETE /api/tasks/:id | Có — restoreTask | 8000ms |
| Buổi | Trash2 rồi confirm dialog rồi DELETE events/:id | Không — toast.success | Mặc định |

### 2.4 Speech Bubble (Lời nhắn tương lai)

| Phần tử | CSS / Icon | Hành vi |
|---------|------------|---------|
| Callout | bg-amber-50/70 border-amber-200/90, header text-amber-900 | Tone vàng ấm |
| Icon Sửa | Pencil size-3, hover bg-amber-200/60 | Mở dialog sửa |
| Icon Xoá | Trash2 size-3, text-bad | Xoá trực tiếp |
| Nút trigger | 💬 Gửi lời nhắn tương lai | Mở dialog nhập |

### 2.5 Tracker — Khối Tài chính

| Phần tử | Nguồn | Hiển thị |
|---------|-------|----------|
| Tiêu đề | currentVietnamMonth() | Tài chính tháng X năm Y |
| Tổng chi | dashboard.f1_total | VNĐ extrabold tabular-nums |
| So sánh | f2_current - f2_previous | nhiều hơn/ít hơn + màu bad/ok |
| Nút Đăng ký | subscriptions count | Đăng ký · N khoản → /subscription |

### 2.6 Lưới ghi nhanh — Gom nhóm (CaptureGrid)

| Trạng thái | Mặc định | Hành vi |
|------------|----------|---------|
| Nhóm đã gán | collapsedGroups = Set() → mở rộng | Hiện tracker khi mount |
| Chưa phân nhóm | unassignedCollapsed = false → mở rộng | Cũng mở |
| Nút toggle | Thu gọn / Mở rộng tất cả | Đảo đồng thời |

> Lưu ý: TrackerScreen tab quản lý nhóm có collapsedGroups riêng (thu gọn mặc định).

### 2.7 Bảng màu 1-chạm

| # | Key | Hex | Label |
|---|-----|-----|-------|
| 1 | rose | #e8698c | Hồng ấm |
| 2 | teal | #0d9488 | Xanh mòng két |
| 3 | indigo | #4f46e5 | Chàm hoàng gia |
| 4 | orange | #ea580c | Cam san hô |
| 5 | emerald | #10b981 | Xanh lục bảo |

| Phần tử | Hành vi |
|---------|---------|
| Chấm đang chọn | border-foreground ring-2 scale-105 + Check trắng |
| Chấm chưa chọn | border-transparent, hover scale-110 |
| Nút Sửa nguồn | Mở SourceForm với initialColor + initialName |

---

## 3. Test Cases

### 3.A Calendar View

#### A-01 Border REVERT: Ngày hôm nay có viền hồng, ngày khác không viền

**Precondition:** Đăng nhập, mở tab Lịch tháng (grid view).

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Quan sát ô ngày hôm nay | Viền hồng (border-primary), nền accent nhạt |
| 2 | Quan sát ô ngày hôm qua | Không viền — border-transparent, nền trắng |
| 3 | Quan sát ô ngày mai | Không viền — border-transparent, nền trắng |
| 4 | Cuộn xuống tháng sau, quan sát các ô | Tất cả border-transparent, chỉ ô today viền |

**Regression check:** Đảm bảo KHÔNG còn border-border/60 ở bất kỳ ô nào khác today.

#### A-02 Sticky Header Tầng 1: Tháng/Năm + Nút Hôm nay

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Mở lịch tháng, ghi nhận header hiện tại | Hiển thị "Tháng X năm YYYY" + nút "Hôm nay" |
| 2 | Cuộn xuống 2-3 tuần | Header Tầng 1 dính đầu container, không bị cuốn đi |
| 3 | Bấm nút "Hôm nay" | Lịch cuộn về ô today, header cập nhật đúng tháng |
| 4 | Cuộn tiếp qua ranh tháng | Header tự cập nhật tên tháng theo vùng đang nhìn |

#### A-03 Sticky Header Tầng 2: Nhãn thứ T2..CN cố định

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Cuộn xuống bất kỳ | Dải T2 T3 T4 T5 T6 T7 CN dính ngay dưới Tầng 1 |
| 2 | Cuộn lên lại | Dải vẫn cố định, không nhảy |
| 3 | Kiểm tra trên mobile (iPhone) | Dải vẫn sticky, không bị trồi lên trồi xuống |

#### A-04 Quick Task Bar (desktop only)

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Mở lịch trên desktop (>= 640px) | Quick Task Bar hiện trong sticky header |
| 2 | Nhập "Test task" vào ô input | Chip kéo thả xuất hiện bên phải input |
| 3 | Bấm Enter hoặc nút Thêm | Task tạo cho ngày hôm nay, toast "Đã thêm task" |
| 4 | Kéo chip thả vào ô ngày khác | Task tạo cho ngày đó |
| 5 | Thu nhỏ cửa sổ < 640px | Quick Task Bar ẩn đi |

#### A-05 Xoá task trong DayDetailDialog (toast hoàn tác 8s)

**Precondition:** Có ít nhất 1 task gán ngày. Mở DayDetailDialog bằng cách chạm ô ngày.

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Bấm icon Trash2 cạnh task | Task biến khỏi danh sách |
| 2 | Quan sát toast | Toast hiện 'Đã xoá "tên task"' + nút "Hoàn tác" |
| 3 | Đợi 8 giây | Toast tự đóng |
| 4 | (Lặp lại) Bấm Trash2, rồi bấm "Hoàn tác" trong vòng 8s | Task khôi phục, hiện lại trong dialog |
| 5 | Kiểm tra API | POST /api/tasks/:id/restore trả 200 |

#### A-06 Xoá buổi (event) trong DayDetailDialog

**Precondition:** Có ít nhất 1 buổi (event) trong ngày, nguồn manual.

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Bấm icon Trash2 cạnh buổi | Confirm dialog mở: "Xoá buổi?" |
| 2 | Bấm nút "Xoá" trong confirm | Buổi biến khỏi danh sách, toast "Đã xoá buổi" |
| 3 | Bấm "Huỷ" thay vì "Xoá" | Dialog đóng, buổi vẫn còn |
| 4 | Kiểm tra toast | KHÔNG có nút hoàn tác (khác task) |

---

### 3.B Note và Lời nhắn tương lai

#### B-01 Speech Bubble Callout — Hiển thị đúng tone

**Precondition:** Có ít nhất 1 note đã có lời nhắn tương lai (future_reflection).

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Mở tab Note | Ghi chú có lời nhắn hiển thị callout bubble |
| 2 | Quan sát callout | Nền vàng ấm bg-amber-50/70, viền border-amber-200/90 |
| 3 | Quan sát header callout | Icon 💬, chữ "Lời nhắn từ tương lai", text-amber-900 |
| 4 | Quan sát shadow | shadow-sm nhẹ, tách khỏi nền note |
| 5 | So sánh mobile vs desktop | p-2.5 (compact) vs p-3 (list view) — cả hai tone giống nhau |

#### B-02 Icon Sửa (Pencil) lời nhắn

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Bấm icon Pencil trên callout | Dialog sửa lời nhắn mở |
| 2 | Sửa nội dung, bấm gửi | Toast "Đã sửa lời nhắn từ tương lai" |
| 3 | Quan sát callout sau khi sửa | Nội dung cập nhật ngay |

#### B-03 Icon Xoá (Trash2) lời nhắn

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Bấm icon Trash2 trên callout | Lời nhắn biến mất (xoá trực tiếp, không confirm) |
| 2 | Quan sát callout | Callout bubble biến mất khỏi note |
| 3 | Kiểm tra hover icon | hover bg-amber-200/60, text-bad giữ nguyên |

#### B-04 Nút Gửi lời nhắn tương lai

**Precondition:** Note chưa có lời nhắn tương lai.

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Cuộn đến note, tìm nút 💬 | Nút "💬 Gửi lời nhắn tương lai" hiện dưới note |
| 2 | Bấm nút | Dialog mở, title "Lời nhắn từ tương lai · tên note" |
| 3 | Nhập nội dung, bấm "Gửi lời nhắn" | Toast success, callout bubble xuất hiện trên note |
| 4 | Bấm nút khi note đã có lời nhắn | (Tuỳ logic) Mở dialog sửa hoặc thêm |
| 5 | Gửi nội dung rỗng | Nút submit disabled hoặc validation chặn |

---

### 3.C Tracker Tab

#### C-01 Khối Tài chính tháng X năm Y — Hiển thị đầu trang

**Precondition:** Đăng nhập, mở tab Tracker. Có ít nhất 1 tracker loại tiền.

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Mở tab Tracker | Khối Tài chính là phần tử ĐẦU TIÊN hiển thị |
| 2 | Quan sát tiêu đề | "Tài chính tháng X năm Y" — uppercase, tracking-wider, text-primary |
| 3 | Quan sát nền Card | bg-gradient-to-br from-brand-50/60 to-card, border-brand-200 |
| 4 | Kiểm tra tháng | Đúng tháng hiện tại theo giờ Việt Nam |

#### C-02 Tổng chi tháng (f1_total) và so sánh cùng kỳ

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Đọc số f1_total | Số VNĐ định dạng đúng (dấu chấm phân cách nghìn) |
| 2 | Đọc so sánh cùng kỳ | "nhiều hơn X đ" (text-bad) hoặc "ít hơn X đ" (text-ok) |
| 3 | Kiểm tra khi f2_current === f2_previous | Hiện "bằng 0 đ" |
| 4 | Kiểm tra dòng phụ | Hiện "f2_current · kỳ trước f2_previous" |
| 5 | Dashboard panel (trong Nhịp ghi) | Cùng số f1_total, f2 delta nhất quán |

#### C-03 Nút Đăng ký · N khoản

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Đọc nút | "Đăng ký · N khoản" — N = số subscription thực |
| 2 | Bấm nút "Đăng ký định kỳ" | Navigate sang /subscription |
| 3 | Quay lại tab Tracker | Khối Tài chính vẫn hiện đúng |

#### C-04 Lưới ghi nhanh — Gom nhóm mở rộng mặc định

**Precondition:** Có ít nhất 2 nhóm tracker, mỗi nhóm >= 1 tracker.

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Mở tab Tracker lần đầu (fresh mount) | Tất cả nhóm MỞ RỘNG, hiện đầy đủ TrackerCard |
| 2 | Quan sát nhóm "Chưa phân nhóm" | Cũng mở rộng (unassignedCollapsed = false) |
| 3 | Bấm header nhóm bất kỳ | Nhóm đó thu gọn |
| 4 | Bấm lại header | Nhóm mở rộng lại |
| 5 | Bấm "Thu gọn tất cả" | Tất cả nhóm thu gọn đồng thời |
| 6 | Bấm "Mở rộng tất cả" | Tất cả nhóm mở rộng đồng thời |
| 7 | Navigate sang tab khác rồi quay lại | State collapse RESET — tất cả mở rộng lại |

#### C-05 Ghi nhanh 1-chạm vẫn hoạt động trong nhóm

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Bấm TrackerCard trong nhóm đang mở | Toast "Đã ghi tên tracker" + nút Hoàn tác |
| 2 | Card bị lock tạm (chống double-tap) | Card disabled trong UNLOCK_MS |
| 3 | Bấm Hoàn tác trong toast | Entry bị xoá, card unlock |

---

### 3.D Bảng màu 1-chạm

#### D-01 Hiển thị 5 chấm màu curated trong SourceForm

**Precondition:** Mở dialog Sửa nguồn lịch hoặc Thêm nguồn lịch.

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Mở dialog Sửa/Thêm nguồn | Hiện 5 chấm tròn: rose teal indigo orange emerald |
| 2 | Chấm đang chọn | Viền foreground, ring-2, scale-105, icon Check trắng bên trong |
| 3 | Hover chấm chưa chọn | border-border, scale-110 |
| 4 | Bấm chấm khác | Check chuyển sang chấm mới, label dưới cập nhật |
| 5 | Kiểm tra label | "Hồng ấm" / "Xanh mòng két" / "Chàm hoàng gia" / "Cam san hô" / "Xanh lục bảo" |

#### D-02 Hex đúng với preview

| Chấm | Hex kỳ vọng | Kiểm tra |
|------|-------------|----------|
| rose | #e8698c | DevTools: backgroundColor chấm === hex |
| teal | #0d9488 | DevTools: backgroundColor chấm === hex |
| indigo | #4f46e5 | DevTools: backgroundColor chấm === hex |
| orange | #ea580c | DevTools: backgroundColor chấm === hex |
| emerald | #10b981 | DevTools: backgroundColor chấm === hex |

#### D-03 Nút Sửa nguồn lịch

**Precondition:** Có ít nhất 1 nguồn lịch đã tạo.

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Mở tab Lịch (list view), bấm Sửa nguồn | Dialog SourceForm mở |
| 2 | Quan sát initialColor | Chấm tương ứng với màu nguồn hiện tại đang được chọn |
| 3 | Quan sát initialName | Tên nguồn hiện tại điền sẵn trong input |
| 4 | Đổi màu + tên, bấm "Lưu thay đổi" | Nguồn cập nhật, event cards đổi chấm màu |
| 5 | Đổi màu thôi (giữ tên) | Cập nhật thành công |

#### D-04 Màu áp dụng đúng lên calendar chip

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Đổi màu nguồn sang "indigo" | Chip event trong DayCell đổi nền indigo |
| 2 | Kiểm tra DayDetailDialog | Buổi cùng nguồn cũng đổi chấm màu |
| 3 | Kiểm tra list view (CalendarScreen) | EventCard chấm tròn đổi backgroundColor |

---

### 3.E Quy trình QA — Ephemeral Neon Branch

#### E-01 Tạo branch và Data Scrambler

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | neonctl branches create --name qa-022-ux-polish --parent main | Branch tạo thành công |
| 2 | Chạy prepare_qa_branch với branch URL | Text scrambled 1:1, private re-encrypt bằng QA Key |
| 3 | Kiểm tra PIN | PIN reset thành 123456 |
| 4 | Kiểm tra push token / audit log | Đã xoá sạch |
| 5 | Kiểm tra session | owner@test.local sẵn sàng |

#### E-02 Bypass OAuth và test PIN

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Bơm cookie ms_session=qa_token | Bypass Google OAuth, vào app thẳng |
| 2 | Nhập PIN 123456 | Private gate mở khóa thành công |
| 3 | Dùng PIN sai (000000) | Private gate từ chối |
| 4 | Đặt env NEON_QA_BRANCH=1 | Test runner guard bật |

#### E-03 Dọn dẹp branch

| Bước | Hành động | Expected |
|------|-----------|----------|
| 1 | Xuất receipt nghiệm thu | Ghi lại kết quả test |
| 2 | neonctl branches delete qa-022-ux-polish | Branch xoá thành công |
| 3 | Kiểm tra neonctl branches list | Không còn branch qa-022-ux-polish |

---

## 4. Gating Criteria

### 4.1 P0 — Chặn release (phải pass hết)

| ID | Tiêu chí | Bằng chứng |
|----|----------|------------|
| P0-1 | DayCell border revert: ngày khác today KHÔNG có viền mỏng | Screenshot mobile + desktop |
| P0-2 | Xoá task có toast hoàn tác 8s, hoàn tác khôi phục thành công | Video/GIF hoặc test log |
| P0-3 | Sticky header 2 tầng dính khi cuộn trên iPhone Safari | Screenshot khi cuộn |
| P0-4 | Lưới ghi nhanh mở rộng mặc định khi mount | Screenshot fresh load |
| P0-5 | Bảng màu 5 chấm hiển thị đúng hex, chọn được | DevTools screenshot |
| P0-6 | Nút Hôm nay cuộn về đúng ô today | Thao tác trực tiếp |
| P0-7 | Data Scrambler chạy xong, PIN 123456 hoạt động | Console log |

### 4.2 P1 — Nên pass (chấp nhận workaround tạm)

| ID | Tiêu chí | Bằng chứng |
|----|----------|------------|
| P1-1 | Speech Bubble callout tone amber đúng | Screenshot |
| P1-2 | Icon Pencil/Trash2 trên callout hoạt động | Thao tác |
| P1-3 | Khối Tài chính hiện đúng tháng, f1_total, f2 delta | Screenshot + so API |
| P1-4 | Nút Đăng ký navigate đúng /subscription | Thao tác |
| P1-5 | Quick Task Bar ẩn trên mobile, hiện trên desktop | Resize screenshot |
| P1-6 | Xoá buổi có confirm dialog, không có hoàn tác | Thao tác |

### 4.3 P2 — Nice to have

| ID | Tiêu chí | Bằng chứng |
|----|----------|------------|
| P2-1 | Hover effect trên chấm màu scale-110 mượt | Visual |
| P2-2 | Toast sonner theme=light (không flash dark trên iPhone dark mode) | iPhone dark mode test |
| P2-3 | Chip kéo thả từ Quick Task Bar sang DayCell | Desktop drag test |

---

## 5. Acceptance Checklist

> Mỗi dòng phải có bằng chứng cụ thể (screenshot / console log / video).
> Chưa kiểm được thì ghi "CHƯA VERIFY" — đó là câu trả lời hợp lệ.

### 5.1 Calendar View

- [ ] A-01: Border revert xác nhận trên mobile
- [ ] A-01: Border revert xác nhận trên desktop
- [ ] A-02: Sticky header Tầng 1 dính khi cuộn (mobile)
- [ ] A-02: Sticky header Tầng 1 dính khi cuộn (desktop)
- [ ] A-03: Nhãn thứ T2..CN cố định dưới Tầng 1
- [ ] A-04: Quick Task Bar hiện/ẩn đúng breakpoint
- [ ] A-05: Xoá task + toast 8s + hoàn tác thành công
- [ ] A-06: Xoá buổi + confirm dialog + không hoàn tác

### 5.2 Note và Lời nhắn tương lai

- [ ] B-01: Callout bubble tone amber đúng (mobile)
- [ ] B-01: Callout bubble tone amber đúng (desktop)
- [ ] B-02: Sửa lời nhắn qua Pencil icon
- [ ] B-03: Xoá lời nhắn qua Trash2 icon
- [ ] B-04: Gửi lời nhắn tương lai mới thành công

### 5.3 Tracker Tab

- [ ] C-01: Khối Tài chính hiện đầu trang
- [ ] C-02: f1_total và f2 delta hiển thị đúng + đúng màu
- [ ] C-03: Nút Đăng ký · N khoản navigate /subscription
- [ ] C-04: Lưới ghi nhanh gom nhóm mở rộng mặc định
- [ ] C-04: Toggle Thu gọn/Mở rộng tất cả hoạt động
- [ ] C-05: Ghi nhanh 1-chạm trong nhóm + toast hoàn tác

### 5.4 Bảng màu 1-chạm

- [ ] D-01: 5 chấm hiển thị đúng hex
- [ ] D-01: Chấm đang chọn có Check + ring
- [ ] D-03: Sửa nguồn lịch với initialColor đúng
- [ ] D-04: Màu áp dụng đúng lên calendar chip

### 5.5 Quy trình QA

- [ ] E-01: Ephemeral branch tạo + Data Scrambler chạy xong
- [ ] E-02: Bypass OAuth + PIN 123456 hoạt động
- [ ] E-03: Branch dọn dẹp sau khi xuất receipt

### 5.6 Regression

- [ ] Không phá vỡ: Task toggle (checkbox) trong DayCell
- [ ] Không phá vỡ: Dời task giữa các ngày (DayDetailDialog)
- [ ] Không phá vỡ: Import ICS file
- [ ] Không phá vỡ: Private gate lock/unlock
- [ ] Không phá vỡ: Font Nunito Variable render tiếng Việt có dấu
- [ ] Không phá vỡ: Toast sonner theme=light trên iPhone dark mode

---

## 6. Dữ liệu ác ý (Adversarial Data — theo ui-brief.md §9d)

Mọi test case hiển thị text (task title, note body, tracker name, lời nhắn)
phải thử với bộ dữ liệu tối thiểu sau:

| Loại | Mẫu | Kiểm tra |
|------|------|----------|
| Chuỗi dài không dấu cách | 70 ký tự liền "aaaaaa...a" | Truncate hoặc xuống dòng, không tràn |
| Tiếng Việt dấu dày | ~150 ký tự "Đề cương ôn tập ế ữ ộ ằ..." | Dấu không bị cắt theo chiều cao dòng |
| CHỮ HOA CÓ DẤU | "ĐỀ CƯƠNG ÔN TẬP MÔN TOÁN" | Dấu trên chữ hoa không đè lên dòng trên |
| Emoji lẫn chữ | "📚 Học bài 🎯 thi cử" | Emoji render đúng, không vỡ layout |
| 1 ký tự | "A" | Card/chip không bị méo |
| Thừa khoảng trắng | "  test  " | Trim khi lưu, hiển thị gọn |
| Toàn khoảng trắng | "   " | Bị từ chối khi submit |

---

## 7. Bản đồ file tham chiếu

| Tính năng | File chính | Test ID |
|-----------|-----------|---------|
| DayCell border | frontend/src/DayCell.tsx | A-01 |
| Sticky header | frontend/src/CalendarScrollView.tsx | A-02, A-03 |
| Quick Task Bar | frontend/src/CalendarScrollView.tsx | A-04 |
| Xoá task (DayDetail) | frontend/src/DayDetailDialog.tsx | A-05 |
| Xoá buổi (DayDetail) | frontend/src/DayDetailDialog.tsx | A-06 |
| Task restore | frontend/src/task-undo.ts | A-05 |
| Speech Bubble | frontend/src/NotesScreen.tsx | B-01..B-04 |
| Khối Tài chính | frontend/src/TrackerScreen.tsx | C-01..C-03 |
| Dashboard panel | frontend/src/DashboardPanel.tsx | C-02 |
| CaptureGrid gom nhóm | frontend/src/CaptureGrid.tsx | C-04, C-05 |
| Bảng màu swatch | frontend/src/SourceForm.tsx | D-01..D-03 |
| Curated swatches | frontend/src/calendar-ui.ts | D-02 |
| Weekday labels | frontend/src/calendar-scroll.ts | A-03 |
| QA script | scripts/prepare_qa_branch.py | E-01 |
