# v1-reference.md — Logic app cũ đáng mang sang

> File **mức code**, cho người/agent dựng lại bản mới — KHÔNG phải tài liệu quyết định chiến lược. Nguồn: audit bản `develop` của `old_prj\VC_QuanLyThoiGian` (app cũ đang mid-migration, khá lộn xộn; lấy *logic hữu ích* từ chỗ sạch nhất).
> Đây là *logic* để port. Về *dữ liệu thật nằm đâu*, xem `migration-mapping-brief.md`.

## Logic domain đáng port (làm ĐÚNG, không copy nguyên bug)

**Import lịch học (.ics):** parse tay có unfold dòng ngắt; chỉ nhận event có cả thời-gian-bắt-đầu lẫn tên. Quy ước cần quyết lại:
- Cũ bỏ timezone → giờ naive. **Bản mới: lưu kèm timezone.**
- Cũ thiếu giờ kết thúc → +90 phút. Giữ mặc định này, cho cấu hình.
- Cũ thiếu địa điểm → "Trường". Giữ.
- Cũ **không chống trùng** → re-import nhân đôi. **Bản mới: chống trùng** (ý tưởng checksum của v2 — tham khảo, không copy code).

**Import lịch thi (.xlsx):** dò header trong 10 dòng đầu; map cột môn/ngày/giờ/phòng kiểu mờ; "ca 1/sáng"→07:00, "ca 2/chiều"→13:00; tiền tố `[THI]`.
- Cũ ghi cứng giờ kết thúc `"??:??"`. **Bản mới: để trống/ước lượng đàng hoàng.**

**Export JSON (feed AI lập kế hoạch):** gom lịch tương lai + task (sắp tới HOẶC quá hạn-chưa-xong), mỗi task kèm tiến độ subtask + nhãn OVERDUE/UPCOMING; hai ngả lưu file / copy clipboard. → Giữ vì đang dùng để nói chuyện với AI; chuẩn hoá thành DTO sạch.

## Đã bỏ (quyết định 18/07/2026)
- ❌ "Don't care 😒" soft-cancel event — gần như không dùng → DROP.

## ✅ Đúng-cỡ Bước 0 (đã chốt 18/07/2026)
Bản mới redesign (không giữ hành vi cũ) và các quirk trên là bug muốn sửa → **không** viết characterization test copy y hệt app cũ. Thay vào đó: port logic import/export cho đúng + đảm bảo toàn vẹn khi migrate data + học từ app cũ; **dồn công test/reliability/eval sang tính năng AI (Bước 1)** — nơi giá trị senior thật nằm.
