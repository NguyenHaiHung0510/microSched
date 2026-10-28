# Durable outbox — Task/checklist/Entry

Core này đã được tích hợp qua [PR272](https://github.com/NguyenHaiHung0510/microSched/pull/272); rộng hơn “offline cache”, hẹp hơn all-app offline. Source nằm trong [frontend/src/outbox](../../frontend/src/outbox) và các Task/Entry hooks, ACK/idempotency routes trong [backend web](../../backend/app/web).

## Contract hiện hành

- 11 typed commands cho Task/checklist và Entry của tracker đã tồn tại. Note/Calendar/Tracker setup/Subscription/Reminder và Mimi vẫn cần mạng theo domain hiện tại; không có generic HTTP/URL queue.
- Admission vào IndexedDB phải thành công trước local projection/đóng form. IDB abort giữ input chỉnh sửa được và cho retry; không fallback gửi HTTP khi admission hỏng.
- Mỗi operation giữ client identity, immutable envelope/protocol, aggregate ordering và projection thuần. “Đã lưu local/đang chờ” khác server ACK; canonical response cập nhật lại cache khi đã có.
- Lost ACK/outcome unknown giữ đúng operation ID để reconcile/replay an toàn; auth/principal/private/version/capability mismatch chuyển hold rõ ràng. Hash/digest của queue dùng cho corruption/binding, không thay cookie authentication.
- V1 transport có optional principal/protocol headers; server session/visibility vẫn là authority. Legacy client không gửi headers vẫn theo contract tương thích hiện có.
- Public offline bootstrap dùng persisted public cache. Private query/editor surfaces bị mask/purge khi khóa; new private admission cần online + session verified + unlocked. Existing admitted private pending/unknown payload là tradeoff đã được duyệt; không mở rộng nó sang persist private query responses hoặc generic drafts.
- Public drafts giữ qua visibility/update transitions; private draft lifecycle theo gate. Domain 401 kết thúc stale signed-in shell. Undo/compensation không được tạo duplicate hoặc đảo thứ tự cùng aggregate.
- Safe service-worker update giữ pending/unknown/draft, kiểm protocol compatibility và không ép reload/site clear/unregister để làm test pass. Pre-V1 Owner-profile upgrade và physical storage quota khác các synthetic version/IDB-abort tests.

Nguồn acceptance giữ qualified/cumulative: outbox có 5/5 kết quả tích lũy theo báo cáo 23Oct, gồm lost ACK/replay, IDB abort và SW; không phải một lượt mọi case đều xanh. Các matrix cũ rộng hơn đã được supersede đúng phạm vi, không tạo nghĩa vụ all-app offline. Xem [verification provenance](../verification/README.md); runtime/device/production của một revision mới phải có receipt riêng.
