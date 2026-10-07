# Task084 — sáu follow-up microSched (Subnote, Heatmap, Calendar)

Triển khai đúng sáu outcome được duyệt theo hợp đồng QA frozen 1.1 (T1-authored):
- S1: Ticking/unticking subnote ghi nhận và di chuyển mục mà không làm danh sách còn lại bị nhảy cuộn xuống ô nhập checklist mới. Scroll anchoring giữ vị trí cuộn và focus chuyển sang logical neighbor với preventScroll.
- S2: Phản hồi lưu (ACK) thêm/sửa không xoá mất bản nháp mới hơn được gõ trong khi request đang xử lý. Quick-add, subnote add và subnote edit bảo toàn bản nháp mới hơn.
- H1: Heatmap số lần ghi 0/1/2/≥3 phân biệt rõ ràng mẫu 0/1/2 thường gặp (--heatmap-0: #f3eeef, --heatmap-1: #fbcbd8, --heatmap-2: #f0759b, --heatmap-3: #b13a5e).
- H2: Chi tiết heatmap hiển thị ngày theo giờ Việt Nam (+07:00), tên tracker và phân loại (Thu nhập, Chi tiêu, Sức khỏe, Số lượng, Thói quen), từng bản ghi (số tiền hoặc số lượng kèm đơn vị, ghi chú đầy đủ không bị cắt ngắn), hỗ trợ hover/focus trên desktop và popup xem trên thiết bị cảm ứng.
- C1: Task trên lịch tháng, chi tiết ngày và giao diện ngày thay thế (Agenda) đều mở đúng trình sửa task hiện có (TaskForm) và lưu/huỷ nhất quán.
- C2: Chi tiết ngày đã chọn (DayDetailDialog) tiếp cận được toàn bộ việc đang mở quá hạn trước ngày đó (due_on < D hoặc due_at < D lúc 00:00 +07:00), độc lập với đồng hồ Date.now(), kèm phân trang cursor để xem đủ mọi việc ngoài tháng đang hiển thị.
