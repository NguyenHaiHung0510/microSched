# Phục hồi lượt bị ngắt và nhịp đồng bộ miGarden

Lượt bị ngắt khi Controller khởi động lại vẫn có kết quả **chưa rõ**, thời lượng thực tế **NULL**. Khi Controller đã đối soát an toàn lượt đó, app có thể cho phép **một yêu cầu tưới mới**; không chạy lại lệnh cũ. Recovery dùng dữ liệu có từ schema `0022`. V2.1.0 thêm health trên `0023` và negotiate quiet/health trong wire `migarden.zone-a.v1`.

## Bằng chứng phục hồi cho đúng một lượt

Firmware gửi loại report hiện có `recovered`, với `payload.reason=REBOOT_INTERRUPTED_RECOVERED`. `session_id`, `request_id` (kể cả null), `config_ref` và `trigger_source` phải khớp phiên gốc. App kiểm terminal đã lưu có loại `session_ended`, kết quả `unknown`, lý do `REBOOT_INTERRUPTED` và thời lượng thực tế NULL. Nếu là lượt từ web, command gốc phải là START đã có grant, đúng config/boot gốc và đang unknown.

Report phục hồi là **bằng chứng lịch sử bền**, mang boot/sequence lúc Controller đã commit việc đối soát. Nó có thể tới server lần đầu qua boot kế tiếp hoặc trong lúc một lượt local mới đang chạy. Không đổi boot của report thành boot vận chuyển và không đòi snapshot hiện tại OFF để nhận report. Sequence của journal tăng bền qua reboot: marker phải sau terminal; thời điểm có clock tin cậy không được đi lùi trước terminal hoặc nằm trong tương lai. Boot của envelope/snapshot vẫn qua các kiểm tra current/epoch/watermark cũ; receipt lịch sử không đổi boot hiện tại hoặc chứng nhận snapshot cũ là mới. NEW START riêng vẫn cần current Ready/OFF, snapshot fresh và mọi gate admission. Đây là báo cáo xử lý của Controller, không phải lệnh OPEN, đo dòng nước hay xác nhận cơ khí.

Report được kiểm và ghi trong savepoint riêng dưới khóa Zone, chỉ ACK sau outer commit. App đánh dấu kết quả supporting `recovered` trên chính receipt mới đã được kiểm. Admission dùng subquery tương quan receipt với phiên cụ thể; không suy mọi raw report cũ có tên `recovered` đều là bằng chứng. Command remote tương ứng chuyển sang trạng thái điều khiển `recovered`; Session và raw terminal vẫn giữ nguyên unknown/NULL. Unknown khác, unidentified execution, storage/ready và report reconciliation không được clear hàng loạt.

Retry cùng ID/nội dung không nhân effect. Cùng ID khác nội dung hoặc terminal mâu thuẫn sau khi đã lưu interruption giữ chặn đối soát, kể cả khi marker phục hồi chưa đến. START gốc hợp lệ đến muộn được giữ làm raw evidence, không ghi đè kết quả hay mở lại lượt. Hoạt động mới mang ID phiên đã phục hồi giữ chặn. Với report phụ thuộc terminal từ boot khác đến trước terminal, app có thể ACK riêng terminal và giữ report phục hồi chưa ACK; gửi lại đúng report sau đó mới gỡ mục lỗi của chính nó. Không bỏ report chưa ACK để làm thông đường.

**Thứ tự rollout:** giao app đọc được marker này trước, rồi parent mới cho firmware mới phát marker. Server cũ chỉ hiểu generic `recovered` có thể ACK mà không phục hồi admission. Firmware phải giữ bằng chứng reboot và accounting bền; app không dựng lại provenance đã mất trong journal cũ. Nếu không chứng minh đúng nguyên nhân, giữ blocked và đối soát riêng. Không reset history/journal/credentials để phục hồi.

## Nhịp v2.1.0 và N03 quiet

UI dùng Tổng quan, Cấu hình và Lịch sử, với trạng thái pending/confirmed theo từng biên nhận. State poll là 1 giây trên trang điều khiển khi đang có hoạt động người dùng, 30 giây khi lỗi hoặc chưa cấu hình. Background/hết cửa sổ hoạt động dừng poll. Query key chung giữ dedup giữa consumer; một request bị treo không tạo hàng đợi poll. Không tự retry mutation hoặc coi receipt là đang tưới.

Khi mở/quay lại miGarden hoặc có thao tác pointer/keyboard/focus, UI gửi một lần `X-MiGarden-Visible: 1` cùng `X-MiGarden-Active-For` trong state GET kế tiếp. Signal mang thời gian hoạt động còn lại, tối đa 5 phút. State GET có signal hoặc action hợp lệ cập nhật cửa sổ hiện diện và lease foreground 30 giây trong memory app process. Poll về sau không tự gia hạn. Restart process làm mất lease.

Với firmware v1 gốc, lease chỉ gợi ý 2 giây cho exchange hợp lệ và thật sự idle. Nhịp gốc 15 giây idle/5 giây active do firmware giữ. Với `quiet-health-v1`, app giảm lượt chạm DB khi context giữ nguyên, đầu ra off, không có phiên/report và đã qua cửa sổ hiện diện cũng như tail 10 phút sau phiên. Reconcile lại trong cửa sổ 6 giờ. HTTP 202 gợi ý thử lại sau 5 giây và không mang ACK, config, grant hay freshness. Authoritative exchange thành công mặc định gợi ý 2 giây nếu chưa có retry hint khác. Work mới đi qua exchange có kiểm chứng, giữ bounded backoff khi lỗi. Health tùy chọn không đánh thức DB khi idle và không tham gia control.

**Giới hạn latency:** mở trang chỉ tác động từ exchange kế tiếp. Nhịp UI rút ngắn bước hiển thị báo cáo. Thời gian tại radio, GPIO, van và dòng nước cần đo riêng.

**Trạng thái UI:** lượt đọc lỗi hoặc dữ liệu cũ giữ báo cáo đã xác minh. Khi mất kết nối, thời lượng hiển thị dừng ở mẫu đã báo và START từ web bị chặn. Sau 15 giây freshness của snapshot, trạng thái hiện tại chuyển sang chưa rõ và UI giữ mốc xác nhận cuối. Đồng hồ chỉ được ngoại suy trong chế độ live dựa trên snapshot đủ điều kiện.

Lease và quiet gate là best-effort trong một app process. Đo resource và chi phí theo exact candidate và workload thực tế. Rollback dùng app/firmware tương thích và giữ ledger, schema cùng biên nhận.

## Bằng chứng và giới hạn

`test_migarden_recovery_pg.py` kiểm local/remote, đúng tuple/terminal và thứ tự journal, first delivery sau reboot kế tiếp/khi lượt local mới đang chạy, other unknown, NULL actual, late original START, contradictory terminal, duplicate/cross-boot, commit failure, START mới và lease expiry/drain/STOP/grant. Các ca `test_migarden_pg.py` giữ regression poison/STOP/CAS. Frontend kiểm activity chỉ gửi một lần, visibility/backoff và wording. Bằng chứng exact source/build/test log được bind ở handoff; source/local test không thay final CI, independent review, actual firmware hay production readiness.

Artifact và provisioning giữ [runbook N01](n01-runbook.vi.md): policy 900/1800/7200 giây trong cửa sổ 10800 giây, automatic schedule OFF khi handoff. Không đưa synthetic fixture, trial value hoặc QA credential của miGarden vào PWA/runtime/production. History thao tác thực vẫn giữ nguyên; chart không cộng planned duration thành thời lượng đã đo.
