# Mimi — workspace của một Owner

Mỗi danh tính login trong `ALLOWED_EMAILS` server là một cửa vào cùng ứng dụng
của Owner. Khi `MIMI_OWNER_WORKSPACE_ENABLED=true`, Mimi dùng một namespace ổn
định cho hội thoại mới, cùng lịch sử STANDARD qua các lần logout/login hoặc
thiết bị khác. Flag mặc định **false**; release preset trong `fly.toml` bật
**true**. Cấu hình source chưa phải bằng chứng production đã được bật.

## Lịch sử và idempotence

Namespace chung có UUID cố định theo version policy, không phụ thuộc thứ tự
allowlist, login đang chọn, session hay thiết bị. Server tính alias legacy bằng
đúng HMAC cũ từ từng email đã normalize trong allowlist và secret hiện hành.
Không lấy danh sách owner từ DB, không nhận owner/alias từ request. Identity ngoài
allowlist không truy cập các API Mimi khi flag bật, kể cả một session cũ còn
sống. Flag không thay đổi vòng đời session và các API ngoài Mimi.

Không rebind hay migrate dữ liệu: `owner_id`, conversation/client/message/run IDs,
DEK đã wrap, ciphertext/AAD, sequence/frontier, lease, event/checkpoint/selection,
feedback, receipt/refresh và timestamps cũ giữ nguyên. Run mới trên hội thoại cũ
vẫn bind lease với **owner đã lưu của hội thoại đó**. History dùng cùng thứ tự
`updated_at DESC, id DESC` và keyset cursor; việc bật flag không ghi timestamps.

Tạo conversation với client ID được serialize bằng transaction advisory lock
theo workspace + client ID, áp dụng chung cho mọi login được phép:

- Không có match: tạo một conversation mới trong namespace chung.
- Có đúng một match STANDARD trong workspace/alias: trả lại conversation cũ.
- Có nhiều match legacy: trả **409**
  `conversation_client_id_ambiguous_use_conversation_id`, không chọn ngẫu nhiên,
  không remap/xóa/gộp row. Tất cả vẫn hiện trong History và mở bằng ID riêng.
  Để tạo conversation riêng, dùng client ID mới. Request thiếu client ID vẫn là
  một lần tạo mới, không có cam kết retry idempotence cho request đó.
- Khi flag off, retry key đã giữ bởi namespace chung nhưng không thấy được sẽ
  trả **409** `conversation_client_id_unavailable`. Không tạo row mới và không
  trả ID/tựa đề của row bị ẩn. Bật lại flag để tiếp tục retry bằng đúng key.
  Bản code này dùng cùng lock theo client ID ở cả hai trạng thái flag.

Message client ID tiếp tục chỉ unique trong conversation đã chọn; Confirm dùng
global idempotency key + exact change-set/digest/nonce/decision. Dùng lại key đã
Confirm để Reject trả conflict, giữ nguyên receipt. Context, provenance và Resume chỉ lấy history
của **conversation ID đã chọn**, không lấy union transcript workspace. Calendar
text tiếp tục dùng các rules đọc lại/không gửi lại prose cũ của [Calendar reads](calendar-read.md).

## Gates giữ nguyên

Login/OAuth allowlist, opaque session, logout/revoke, same-origin/CSRF, encryption,
explicit Confirm, source/CAS/receipt và admission/run/conversation locks vẫn áp dụng.
Private unlock thuộc từng session, không chia sẻ theo workspace. Mimi hiện chỉ
truy cập STANDARD nonprivate conversations, kể cả khi PIN đã mở. Notifications
dùng các alias hợp lệ cho attention và vẫn cần device proof/opt-in/revision cùng
exact intent → conversation binding. Push không mở rộng từ một legacy opt-in
sang namespace khác. Release giữ notifications **off**; quyền thiết bị là opt-in
riêng, không tự thu hồi chỉ bằng cách bỏ một login khỏi allowlist. Xác minh thu
hồi thiết bị riêng trước một lần bật notifications.
Nhánh Mimi trong Reminder History dùng cùng alias; ledger đánh dấu đã xử lý và
prepared bulk của Reminder giữ namespace và quyền của login cũ. Experimental
workflow pilot có store riêng và không đổi namespace trong release này.

Local có `ALLOWED_EMAILS` rỗng giữ namespace synthetic theo từng identity như test
cũ, không tự gộp arbitrary test owners. Production với allowlist rỗng fail closed;
đây không phải đường thay thế production authentication.

## Cutover và rollback không ghi lại dữ liệu

Sau review độc lập, QA synthetic và gates ở exact release SHA, release executor
triển khai qua release flow với flag trong `fly.toml`. Không chạy SQL/Alembic/data
rebind cho slice này; schema không đổi. Không thêm email, đổi encryption key hay
OAuth secret. Sau deploy kiểm exact readiness commit/DB và hành trình history
theo quyền acceptance riêng; test local không chứng minh production/device.

Rollback ưu tiên flag **false** ở cùng code qua release flow: chỉ namespace cũ
của login hiện hành hiển thị, hội thoại chung và alias còn lại tạm ẩn, không bị
xóa. Bật lại **true** phục hồi union. Đợi các run đang mở kết thúc trước
đổi policy; không trộn writer bản cũ và mới. Rollback code về trước slice cũng
không hiểu namespace chung; ưu tiên feature-off thay vì downgrade dữ liệu.

Legacy alias phụ thuộc **allowlist và OAuth secret hiện hành**. Bỏ identity khỏi
allowlist cũng bỏ alias legacy của identity đó; đổi secret không tự phát hiện
namespace HMAC cũ. Cần quyết định/cutover riêng trước các thay đổi này, không giữ
alias tùy ý hoặc đọc mọi DB owner để bù. Namespace hội thoại mới không phụ thuộc
secret; không có migration cần thực hiện trong release này.

Source: [policy](../../backend/app/agent/owner_workspace.py),
[service](../../backend/app/agent/service.py),
[notifications](../../backend/app/agent/notifications.py).
Tests: [namespace](../../backend/tests/test_mimi_owner_workspace.py),
[PG/API/context](../../backend/tests/test_mimi_owner_workspace_pg.py).
