# miGarden N01 · Hợp đồng adapter microSched

Device: `POST /api/migarden/device/exchange`, bearer riêng, JSON `migarden.zone-a.v1`. Không mở session người dùng trên route này. Wire do miGarden giữ, các model tương ứng nằm trong `app.domain.migarden.wire`. Zone/binding cố định: `zone-a` / `zone-a-v1`.

Human: session microSched. Mutations gửi JSON, `X-MiGarden-CSRF: 1`, Origin đúng origin của app, Sec-Fetch-Site cùng origin khi header có mặt. Không có offline outbox. Tất cả ngày-giờ trong JSON là UTC; ngày hiển thị và bộ lọc theo Hà Nội (UTC+7).

| API | Input | Response |
|---|---|---|
| GET state | — | `zone_id, binding_ref, server_time, connection, last_seen_at, snapshot, snapshot_received_at, config, start_block_reason, stop_available, start_request, stop_request, next_schedule` |
| GET config | — | `desired, desired_saved_at, applied, applied_confirmed_at, application_status, reason` |
| PUT config | `{expected_config_ref, policy, schedule}` | Cùng model GET config; 409 nếu CAS sai, 422 nếu nội dung sai. Các key policy/schedule y hệt wire |
| POST start/preview | `{duration_seconds}` | `{preview_id, expires_at, context: {zone_id, binding_ref, config_ref, boot_id, control_epoch}, duration_seconds}` |
| POST start/confirm | `{preview_id}` | `{request_id, kind, status, reason, confirmed_at, expires_at, duration_seconds, config_ref}`. Lặp lại cùng preview đã confirm đọc kết quả cùng ID |
| POST stop | `{}` | Cùng response request; ghi yêu cầu, không trả giả rằng đã dừng |
| GET history | `limit` 1–50, cursor, from_day/to_day, source, result (tùy chọn) | `{items, next_cursor, coverage}`; mỗi item giữ event/received time, source, ref, result, duration đã báo nếu có |
| GET history (N02) | `view=sessions`, cùng tham số lọc/phân trang | `{items, next_cursor, coverage, totals}`; một dòng mỗi phiên có báo cáo bền, thêm các thao tác riêng kể cả Dừng khi đã tắt. Mỗi dòng có `started_at`, `ended_at` và `evidence` từ bản ghi liên quan. View mặc định vẫn trả event như trước. |
| GET daily | `days=7|30` | `{days: [{day, schedule_seconds, remote_seconds, local_button_seconds, coverage}], forecast}` |

`connection`: `unconfigured | waiting | fresh | stale`. `application_status`: `not_saved | pending | applied | rejected`. `snapshot` là projection wire, có thể null. Stale không làm mới bởi event cũ. `next_schedule`/`forecast`: `{status, config_ref, next_at, day, duration_seconds, day_total_seconds}`; forecast của bản **đã áp dụng**, không phải cam kết Controller sẽ thực thi. Wire v1 không có watermark xác nhận đầy đủ một ngày; ngày không có duration định vị được giữ unknown, có tổng đã báo thì partial.

Lịch sử N02 lọc ngày Hà Nội của report kết thúc, hoặc của report bắt đầu nếu phiên chưa có terminal. Dòng không rõ ngày vẫn xem được khi bỏ lọc ngày. Tổng dùng toàn bộ kết quả lọc trong tối đa 31 ngày, không phụ thuộc trang hiện tại. Phiên kết thúc qua nửa đêm được cộng trọn thời lượng đã báo vào ngày terminal của Lịch sử; biểu đồ ngày vẫn chia theo phần thời gian nằm trong mỗi ngày. Nếu bộ lọc quá rộng, vượt trần 4.096 phiên đo được hoặc không có căn cứ, không hiện tổng ước lượng; thời lượng thiếu giữ `null`. Thao tác Dừng không có phiên không góp vào tổng.

`pending → received → granted → started → completed|stopped|fault` mô tả các mức bằng chứng của START; có thể `rejected|canceled|expired|unknown`. Grant được commit trước response, không phát lại sau mất response. Hết hạn sau grant không chứng minh chưa tác động. STOP dùng `stop_requested|stop_received|stop_confirmed|stop_unconfirmed|stop_stale|rejected`. `stop_processed` là biên nhận xử lý của Controller gắn với STOP ID; `stop_unconfirmed` tiếp tục giao/đối soát cùng ID và chặn START; hết hạn chờ không tự xóa. `stop_confirmed` có nghĩa đã yêu cầu CLOSE hoặc báo đã off, chưa chứng minh dòng nước đã ngừng. Epoch/off đơn thuần không gán thành remote STOP đã tới. `occurrence_decided` chỉ ghi nhận cơ hội lịch, không tạo phiên hoặc phút tưới. Không thêm key trên wire. Không suy từ output/receipt thành van thực sự đóng.

Provision QA từ `backend`:

```powershell
uv run --frozen python -m scripts.provision_migarden_qa issue --device-id qa-controller-a --output ../.local/n01/qa-device.token
uv run --frozen python -m scripts.provision_migarden_qa revoke --device-id qa-controller-a
```

Dùng `APP_ENV=local`, `DATABASE_URL` chỉ rõ DB loopback `microsched_n01_*` đã migrate, `MIGARDEN_ENABLED=true` khi chạy app. File chỉ gồm token dạng text; không ghi Wi-Fi/CA/host hay in giá trị. Parent cấp file đích riêng bên dưới `.local` của checkout này và chỉ đọc qua runner riêng. QA identity `qa-controller-a`; production sử dụng identity và credential được cấp riêng dưới quyền phát hành, không tái dùng file/row QA.
