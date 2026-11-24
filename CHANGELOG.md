# Changelog

## 2.1.0 — release candidate

- **Mimi Calendar STANDARD** đọc sự kiện và mốc ngày đã lưu trong phạm vi được hỗ trợ, có chỉ dấu coverage và đọc lại nguồn khi tiếp tục. Calendar là năng lực chỉ đọc. [Calendar reads](docs/mimi/calendar-read.md)
- **Mimi Owner history** dùng chung lịch sử STANDARD giữa các login được phép của một Owner. Hội thoại cũ vẫn mở được qua legacy aliases, giữ nguyên dữ liệu và ID. [Owner workspace](docs/mimi/owner-workspace.md)
- **Mimi Voice v1/v2** đưa mic và loa vào hội thoại STANDARD. V1 có hỏi đáp và đọc Calendar. V2 thêm thao tác Task theo nhóm, review và Confirm, cùng diff theo receipt và undo khi guard còn đạt. Khi Owner bật Auto, v2 có thể áp dụng nhóm 1–5 Task STANDARD đủ điều kiện, có inverse và không phát sinh hiệu ứng reminder hoặc tác động ra ngoài. Khi ngắt kết nối, đối chiếu receipt đã lưu trước khi thử lại. [Voice](docs/mimi/voice.md)
- **miGarden Khu A** vào điều hướng chung với Tổng quan, Cấu hình và Lịch sử. App ghi yêu cầu tưới có preview/confirm và yêu cầu dừng có đối soát. ESP32 giữ quyết định chạy/dừng, giới hạn an toàn, journal và điều khiển đầu ra. Báo cáo phục hồi đúng lượt sau reboot có thể mở đường cho một yêu cầu mới. Kết quả lượt cũ vẫn unknown, thời lượng thực tế vẫn để trống.
- **Lịch tưới và truy vết** hiển thị riêng bản đã lưu đang chờ và bản ESP32 đã xác nhận. Lịch sử ghi phiên và thao tác theo bằng chứng, liên kết phiên bản qua `config_ref`. Biểu đồ cộng thời lượng đã báo khi đủ căn cứ.
- **ESP32 health và N03 quiet** bổ sung chẩn đoán theo mẫu cùng chế độ idle giảm lượt chạm DB qua extension tùy chọn của wire v1. Khi lượt đọc nền lỗi hoặc về muộn, UI giữ báo cáo đã xác minh. Khi đứt kết nối, đồng hồ dừng ở thời lượng đã báo. Đến hạn freshness 15 giây, UI hạ trạng thái về chưa rõ và giữ mốc xác nhận gần nhất. [miGarden](docs/migarden/n01-status.md)
- **Schema miGarden** đi tiến qua `0021–0023` cho N01, STOP/reconciliation và health theo giờ. [Data model](docs/engineering/data-model.md)

### Qualification

Mốc app `366265714abecd3d4d1f73025f81d338c602da39`. Mốc source firmware `9ee5047b81e9de9764921be4122a3ac0117e429c` trên `miGarden/develop` qua PR #6. Xác nhận CI, schema, readiness ở đúng bản triển khai và nghiệm thu Mimi với live provider/thiết bị cần receipt theo từng môi trường. miGarden giữ các mốc tích hợp app/controller, thử khô, thử nước có kiểm soát và nghiệm thu tưới tại hiện trường theo phạm vi đã kiểm. Xem [Operations](docs/operations/runbook.md) và [Verification](docs/verification/README.md).

## 2.0.0 — release candidate

Mốc sản phẩm sau v1.6; publication/tag và production acceptance do release executor xác nhận riêng.

- Responsive shell/navigation và vùng tracker, safe PWA update bảo toàn draft/pending work (096).
- Nội dung Task/Note/History gọn hơn, calendar toolbar nhóm lại và đọc nội dung dài thuận tiện hơn (097).
- Note reader, chuyển đọc/sửa và lịch sử Task được cải thiện (098).
- Durable IndexedDB outbox cho 11 Task/checklist/Entry commands: local admission, optimistic projection, ordered replay, unknown/auth/private/version holds và queue resolution (091, PR272).
- Calendar time/movement, reminder history/handling, funding/income Entry và tracker/notes usability được bổ sung.
- Mimi Task/checklist: bounded query/inspect/content, collection selection, proposals/revision, frozen explicit Confirm, receipt/recovery; cải thiện context/routing, feedback và workspace. Module Mimi tổng thể vẫn đang phát triển.
- Package locks cập nhật hẹp theo advisory floors; technical docs được gom theo architecture/data/setup/operations/verification, cùng live contracts và assets thực sự đang dùng.

### Qualification

Outbox không phải all-app offline. Mimi Task/checklist delivery không đồng nghĩa mọi năng lực agent đã hoàn tất. QA hiện có là scoped/cumulative và có recovery/failure được giữ nguyên; physical iPhone/Safari, live provider, schema và exact-head runtime/production chỉ được coi đạt khi có receipt tương ứng. Xem [Verification](docs/verification/README.md). Không có homepage redesign hay feature mới được thêm trong đợt repository hygiene.
