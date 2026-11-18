# Phục hồi lượt bị ngắt và nhịp đồng bộ miGarden

Lượt bị ngắt khi Controller khởi động lại vẫn có kết quả **chưa rõ**, thời lượng thực tế **NULL**. Khi Controller đã đối soát an toàn lượt đó, app có thể cho phép **một yêu cầu tưới mới**; không chạy lại lệnh cũ. Phần này triển khai trên schema `0022`, không thêm migration hoặc đổi wire `migarden.zone-a.v1`.

## Bằng chứng phục hồi cho đúng một lượt

Firmware gửi loại report hiện có `recovered`, với `payload.reason=REBOOT_INTERRUPTED_RECOVERED`. `session_id`, `request_id` (kể cả null), `config_ref` và `trigger_source` phải khớp phiên gốc. App kiểm terminal đã lưu có loại `session_ended`, kết quả `unknown`, lý do `REBOOT_INTERRUPTED` và thời lượng thực tế NULL. Nếu là lượt từ web, command gốc phải là START đã có grant, đúng config/boot gốc và đang unknown.

Report phục hồi là **bằng chứng lịch sử bền**, mang boot/sequence lúc Controller đã commit việc đối soát. Nó có thể tới server lần đầu qua boot kế tiếp hoặc trong lúc một lượt local mới đang chạy. Không đổi boot của report thành boot vận chuyển và không đòi snapshot hiện tại OFF để nhận report. Sequence của journal tăng bền qua reboot: marker phải sau terminal; thời điểm có clock tin cậy không được đi lùi trước terminal hoặc nằm trong tương lai. Boot của envelope/snapshot vẫn qua các kiểm tra current/epoch/watermark cũ; receipt lịch sử không đổi boot hiện tại hoặc chứng nhận snapshot cũ là mới. NEW START riêng vẫn cần current Ready/OFF, snapshot fresh và mọi gate admission. Đây là báo cáo xử lý của Controller, không phải lệnh OPEN, đo dòng nước hay xác nhận cơ khí.

Report được kiểm và ghi trong savepoint riêng dưới khóa Zone, chỉ ACK sau outer commit. App đánh dấu kết quả supporting `recovered` trên chính receipt mới đã được kiểm. Admission dùng subquery tương quan receipt với phiên cụ thể; không suy mọi raw report cũ có tên `recovered` đều là bằng chứng. Command remote tương ứng chuyển sang trạng thái điều khiển `recovered`; Session và raw terminal vẫn giữ nguyên unknown/NULL. Unknown khác, unidentified execution, storage/ready và report reconciliation không được clear hàng loạt.

Retry cùng ID/nội dung không nhân effect. Cùng ID khác nội dung hoặc terminal mâu thuẫn sau khi đã lưu interruption giữ chặn đối soát, kể cả khi marker phục hồi chưa đến. START gốc hợp lệ đến muộn được giữ làm raw evidence, không ghi đè kết quả hay mở lại lượt. Hoạt động mới mang ID phiên đã phục hồi giữ chặn. Với report phụ thuộc terminal từ boot khác đến trước terminal, app có thể ACK riêng terminal và giữ report phục hồi chưa ACK; gửi lại đúng report sau đó mới gỡ mục lỗi của chính nó. Không bỏ report chưa ACK để làm thông đường.

**Thứ tự rollout:** giao app đọc được marker này trước, rồi parent mới cho firmware mới phát marker. Server cũ chỉ hiểu generic `recovered` có thể ACK mà không phục hồi admission. Firmware phải giữ bằng chứng reboot và accounting bền; app không dựng lại provenance đã mất trong journal cũ. Nếu không chứng minh đúng nguyên nhân, giữ blocked và đối soát riêng. Không reset history/journal/credentials để phục hồi.

## Lease hoạt động hữu hạn

UI vẫn dùng Tổng quan/Cấu hình và trạng thái pending/confirmed hiện có. State poll là 1 giây khi trang điều khiển đang hiển thị; background tạm dừng, lỗi và chưa cấu hình dùng 30 giây. Query key chung giữ dedup giữa consumer; một request bị treo không tạo hàng đợi poll. Không tự retry mutation hoặc coi receipt là đang tưới.

Khi mở/quay lại miGarden hoặc có thao tác pointer/keyboard/focus, UI gửi **một lần** header `X-MiGarden-Visible: 1` trong state GET kế tiếp. Poll tự động về sau không lặp header. State GET thành công có signal, hoặc action điều khiển/cấu hình hợp lệ, gia hạn một lease trong memory app process trong 30 giây. Không có signal mới thì lease hết hạn dù tab vẫn mở và polling. Không lưu identifier/session riêng vào lease; restart process mất lease và về nhịp gốc.

Trong lease, chỉ exchange hợp lệ và thật sự idle mới nhận `retry_after_seconds=2`: không reports/ACKs/desired config/candidate/grant/STOP, không inflight, reconciliation hoặc uncertainty. Active vẫn theo nhịp firmware 5 giây; hết lease, idle về 15 giây. Response đã có retry/backoff, poison path, auth failure và report drain không bị thay bằng hint. Firmware phải phân biệt hint idle với error backoff để event mới vẫn đánh thức/drain ngay.

**Giới hạn latency:** mở trang không đánh thức Controller trước exchange kế tiếp. Lệnh đầu có thể còn chờ phần còn lại của nhịp idle 15 giây; hint 2 giây chỉ có hiệu lực sau khi firmware nhận được nó. Nhịp UI 1 giây rút ngắn bước hiển thị báo cáo, không chứng minh radio, GPIO, van hoặc flow nhanh tương ứng. Không thêm push/queue/service để đưa ra một lời hứa instant.

Về số request lý thuyết: trong 30 giây lease có tối đa khoảng 15 idle exchange, so với khoảng 2 ở nhịp 15 giây. Tab điều khiển hiển thị liên tục có khoảng 60 state GET/phút, trước các request history/chart; thao tác liên tục có thể gia hạn lease liên tục. Đây là phép tính cấu hình, không phải measurement hoặc bảo đảm quota/chi phí Neon. Tài nguyên thực và topology process là gate release của parent. Lease là best-effort trong một app process, không đồng bộ giữa nhiều instance. Rollback riêng latency trả polling UI về 5/15 giây và bỏ hint; không thay wire hay xóa ledger.

## Bằng chứng và giới hạn

`test_migarden_recovery_pg.py` kiểm local/remote, đúng tuple/terminal và thứ tự journal, first delivery sau reboot kế tiếp/khi lượt local mới đang chạy, other unknown, NULL actual, late original START, contradictory terminal, duplicate/cross-boot, commit failure, START mới và lease expiry/drain/STOP/grant. Các ca `test_migarden_pg.py` giữ regression poison/STOP/CAS. Frontend kiểm activity chỉ gửi một lần, visibility/backoff và wording. Bằng chứng exact source/build/test log được bind ở handoff; source/local test không thay final CI, independent review, actual firmware hay production readiness.

Artifact và provisioning giữ [runbook N01](n01-runbook.vi.md): policy 900/1800/7200 giây trong cửa sổ 10800 giây, automatic schedule OFF khi handoff. Không đưa synthetic fixture, trial value hoặc QA credential của miGarden vào PWA/runtime/production. History thao tác thực vẫn giữ nguyên; chart không cộng planned duration thành thời lượng đã đo.
