# miGarden N01 · Ma trận 54 ca cho ứng viên microSched

Nguồn: Bước 07 §6.4, 54/54 anchor; dùng với Bước 01–10, wire `migarden.zone-a.v1` và Clarification A. Ma trận này là chỉ mục **app lane**. Mỗi dòng chỉ nêu phần test có thể quyết định. PASS test adapter không là PASS toàn ca thiết bị; cột cuối nói rõ phần cần PM, firmware hoặc tủ. Source cuối = commit chứa tài liệu này; base microSched `79d324fb5ee244a7e01d44d223d8b598e7a80dd8`. Build/firmware/partition/ESP32 và independent acceptance do PM bind riêng.

| Mã bằng chứng | Cách chạy và oracle |
|---|---|
| WIRE / LIMIT | [test_migarden_wire.py](../../backend/tests/test_migarden_wire.py): kiểm response shape, Clarification A, 4 kiểu lịch và UTC+7, biên hiệu lực, giới hạn và capability phân môi trường. |
| PG-CFG | [test_migarden_pg.py](../../backend/tests/test_migarden_pg.py): `test_pg_owner_cas_applied_and_immutable_role`. |
| PG-AUTH | Cùng file: `test_pg_auth_origin_scope_body_bounds_and_revoke`. |
| PG-REMOTE | Cùng file: `test_pg_received_grant_once_stop_and_dedup`. |
| PG-FENCE | Cùng file: `test_pg_expiry_unknown_boot_epoch_and_stop_cancellation`. |
| PG-LOG | Cùng file: `test_pg_history_midnight_unknown_disposition_and_isolated_ack`. |
| PG-GAP | Cùng file: `test_pg_terminal_loss_after_active_snapshot_blocks_start`. |
| UI | [Playwright full app](../../frontend/integrated/migarden.spec.ts) (thiết bị gửi synthetic report vào API thật); [Vitest](../../frontend/src/features/migarden/presentation.test.ts) (giờ Hà Nội, đồng hồ fresh/stale). Đây là các test author, không phải chứng nhận độc lập. |

| Bước 07 | Oracle app | Phần chứng minh / giới hạn |
|---|---|---|
| UC01-normal | PG-CFG, UI | Lưu pending → config_applied và snapshot khớp → applied; firmware lưu nguyên tử chưa chạy. |
| UC01-A01 | WIRE/LIMIT, UI | Bước 15s/thứ/hiệu lực đúng; từ chối dữ liệu sai. |
| UC01-A02 | PG-CFG | Stale vẫn đọc desired/applied; forecast dùng ref applied. Chưa chạy offline và pause trên bo. |
| UC01-A03 | PG-CFG | Hai CAS đồng thời: một thành công; báo cũ không kéo applied lùi. |
| UC01-A04 | PG-CFG, PG-LOG | Chờ bằng chứng; dedup retry/lost ACK. Chưa cắt kết nối thật quanh apply. |
| UC01-A05 | PG-CFG, PG-REMOTE | Cấu hình mới không sửa report/duration. Bo giữ deadline lúc apply/pause: NOT_RUN. |
| UC01-A06 | PG-CFG | Giữ ref cũ và reason khi thiết bị báo ghi lỗi. Lỗi flash thật: NOT_RUN. |
| UC01-A07 | PG-CFG | Web không bù occurrence, giữ bản nội dung; ledger/cutover của firmware: NOT_RUN. |
| UC01-A08 | PG-REMOTE, WIRE | Applied không thay clock/ready; STOP khi clock unknown. Recovery timebase: NOT_RUN. |
| UC02-normal | PG-LOG, WIRE | Nhận lượt đóng từ thiết bị và dự báo theo lịch; bo tự chạy đến hạn: NOT_RUN. |
| UC02-A01 | PG-LOG | Report/Session dedup; không chứng minh đánh giá lặp/cutover tại bo. |
| UC02-A02 | PG-CFG, UI | Stale rõ, đọc bản cũ; AP/WAN/microSched-down trên firmware: NOT_RUN. |
| UC02-A03 | PG-LOG | Bỏ qua có reason, không tạo session. Kiểm sổ/budget và không catch-up tại bo: NOT_RUN. |
| UC02-A04 | PG-GAP, PG-REMOTE | Snapshot đang chạy chặn start; arbitration nhiều nguồn ở bo: NOT_RUN. |
| UC02-A05 | PG-REMOTE | STOP và terminal duration có bằng chứng; deadline/đóng thật: NOT_RUN. |
| UC02-A06 | NOT_RUN | Fault và unknown có model; lỗi cơ khí/cutoff/van/nước cần tủ thật. |
| UC02-A07 | PG-FENCE, PG-GAP | Boot/terminal fencing và unknown trên web; mất điện/tủ: NOT_RUN. |
| UC02-A08 | PG-CFG | Đọc được lỗi storage qua báo cáo; journal hỏng/đầy/safe stop tại thiết bị: NOT_RUN. |
| UC02-A09 | PG-CFG, PG-FENCE | Zone/binding cố định; ref lịch sử bất biến. Mapping vật lý: NOT_RUN. |
| UC02-A10 | WIRE, PG-LOG | Không bịa duration/day khi clock thiếu; monotonic deadline local: NOT_RUN. |
| UC03-normal | PG-LOG, PG-GAP | Nguồn nút không phụ thuộc human auth ở exchange. Hai nút thật: NOT_RUN. |
| UC03-A01 | PG-LOG | Có thể sync bản ghi muộn; START/STOP trên bo khi mất mạng: NOT_RUN. |
| UC03-A02 | PG-LOG, PG-REMOTE | Từ chối/STOP có evidence riêng, kể cả không có Session. Kiểm local gates: NOT_RUN. |
| UC03-A03 | PG-GAP | Web không cho mở khi busy; bounce/giữ nút local: NOT_RUN. |
| UC03-A04 | PG-LOG | History local_button, không gán danh tính người bấm. |
| UC03-A05 | NOT_RUN | Board mất điện/treo, khóa tay, cutoff và residual flow cần thiết bị/tủ thật. |
| UC03-A06 | PG-GAP, PG-FENCE | Unknown chặn START web trên binding chung; feedback/fail-safe local: NOT_RUN. |
| UC03-A07 | NOT_RUN | Không thể suy fault storage, accounting hoặc safe stop tại bo từ receipt HTTP. |
| UC03-A08 | PG-CFG, PG-LOG | Ref payload/history giữ nội dung; resolve mapping trước OPEN local: NOT_RUN. |
| UC04-normal | PG-REMOTE, UI | Xem trước/xác nhận, candidate/received/grant/report, STOP processing. OPEN thực và TLS bo: NOT_RUN. |
| UC04-A01 | PG-AUTH, PG-FENCE | Session khác bearer, origin guard, stale/unknown không grant; STOP không dùng cửa OPEN. |
| UC04-A02 | PG-FENCE | Receipt trễ hơn TTL không grant; kiểm final local expiry/packet delay: NOT_RUN. |
| UC04-A03 | PG-REMOTE, PG-AUTH | Lặp confirm/receipt không nhân action, candidate giữ context. Replay ở thiết bị: NOT_RUN. |
| UC04-A04 | PG-FENCE, PG-GAP | TTL sau possible execution không đổi thành canceled; không phát START mới. |
| UC04-A05 | PG-FENCE, PG-REMOTE | Pending bị hủy trước grant; STOP song song không dùng busy gate; xử lý local: NOT_RUN. |
| UC04-A06 | PG-FENCE | Chỉ canceled khi chưa grant; grant mất kết quả cho unknown. |
| UC04-A07 | PG-FENCE, PG-GAP | Boot mới không nhận grant cũ; chưa đủ evidence giữ block; tủ/driver/ledger: NOT_RUN. |
| UC04-A08 | PG-FENCE | Epoch đổi làm mất preview; ref/boot của candidate bị bind; xác nhận local cuối: NOT_RUN. |
| UC04-A09 | PG-FENCE, UI | STOP requested/processed/stale tách riêng; offline hoặc chưa có report không hiện đã dừng nước. |
| UC05-normal | PG-LOG, PG-REMOTE, UI | Sync nền, đọc có auth, history/filters/chart từ report. Cross-repo runtime: NOT_RUN. |
| UC05-A01 | PG-CFG, UI | Stale và forecast last-applied; history không cần kết nối sống với bo. |
| UC05-A02 | PG-LOG | Adapter nhận backlog không replay; ngắt service trong lượt thật: NOT_RUN. |
| UC05-A03 | PG-CFG, PG-LOG | Source time/receipt riêng, old boot không lùi projection. |
| UC05-A04 | PG-AUTH, PG-LOG | Duplicate/collision được phân biệt; invalid batch rollback, không ACK giả. |
| UC05-A05 | PG-REMOTE, PG-LOG | Retry cùng ID nhận ACK, không grant lại hoặc cộng lại duration. |
| UC05-A06 | NOT_RUN | Đo backlog/queue/atomic journal trên firmware, không xóa hoặc ép record. |
| UC05-A07 | PG-LOG, UI | Chỉ hiển thị thời lượng đầu ra báo về; không claim van/flow/thể tích. |
| UC05-A08 | PG-CFG, PG-LOG | Applied/desired đổi không sửa ref gốc; history resolve chính ref còn giữ. |
| UC05-A09 | WIRE, UI | Thiếu dữ liệu, paused/no future, trạng thái tải/lỗi/stale; không gán 0 cho ngày không rõ. |
| LC01 | PG-REMOTE, PG-FENCE | STOP chặn grant; mất kết quả sau grant vẫn unknown; latch/epoch local: NOT_RUN. |
| LC02 | PG-CFG, WIRE | Forecast chuyển theo applied; no-double/no-retime/no-catch-up ở bo: NOT_RUN. |
| LC03 | PG-CFG, PG-FENCE, PG-LOG | Context khóa theo ref/boot/epoch, lịch sử giữ nội dung ngày cũ; mapping tủ: NOT_RUN. |
| S2-AT-NET01 | NOT_RUN | Phải ngắt AP/Wi-Fi trước và trong lượt thật; browser offline khác phép kiểm này. |
| S2-AT-NET02 | NOT_RUN | Phải giữ AP/đứt WAN trước và trong lượt; không lấy app down hoặc browser offline thay. |

Gate riêng: full backend/frontend/hook/migration/runtime-deps/packaging; independent QA; TLS và board thật; AP/WAN; lỗi nguồn/flash; driver/nút/electrical/manual shutoff; contained water/field; physical iPhone; migration/rollout production. Không suy bằng chứng giữa các lớp. Đối chiếu [runbook N01](n01-runbook.vi.md).

## Delta sau Terra review

Các oracle `test_pg_review_*` bổ sung poison schema/conflict với STOP-only response, unconfirmed receipt không mở gate, new unknown boot chỉ là đích STOP và unordered applied không lùi. `test_migarden_review.py` kiểm exact effective DSN trước kết nối; `test_migarden_bootstrap_pg.py` kiểm role/grants thật và FAIL→restore→PASS; `test_migarden_commission_pg.py` rehearsal forward-only trên DB mới. `presentation.test.ts` và hành trình full app kiểm nhãn Gần đây dùng command status mới nhất. Các ca `test_pg_groupfix_*` và `test_migarden_reconciliation.py` kiểm recovery từng fingerprint, overflow/legacy giữ chặn, ACK STOP hợp lệ đi cùng report lỗi và sau outer commit, STOP terminal giữ nguyên, và commissioning QA khóa đúng đích trước connect. Các gate hardware, physical và retest độc lập trong 54 hàng giữ nguyên.
