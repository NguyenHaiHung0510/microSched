# Changelog

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
