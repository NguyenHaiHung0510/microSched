# 011e — CronTimer startup observability receipts

## Bối cảnh đã kiểm chứng

`011d` đã được merge qua PR #115 và activation đã merge/deploy qua PR #117. Fly đang có đúng một
Machine, `ENABLE_INPROCESS_CRON=true`, VAPID secrets deployed và `/api/readyz.commit` khớp SHA merge.
Nhưng log production sau deploy chỉ cho thấy Uvicorn/Fly: hai log hiện tại của `CronTimer` dùng
`logger.info`, không tạo được receipt bắt buộc ở `011d` §6.5.

Đây là **observability gap**, không phải bằng chứng timer đã chết. Không được suy diễn từ HTTP liveness
rằng timer đã chạy; cần phát được biên lai structured, không nhạy cảm.

## Phạm vi writer

Chỉ được sửa:

- `backend/app/core/cron_timer.py`
- `backend/tests/test_cron_timer.py`
- file task này (để ghi receipt ngắn nếu cần sau QA)

Không sửa `fly.toml`, workflow, schema/migration, route/health endpoint, VAPID/push code hay secret.
Không tạo endpoint timer công khai, không thêm dependency/scheduler/DB polling, không dùng data/secret
production hoặc Chrome.

## Yêu cầu

1. Khi timer enabled bắt đầu `run()`, emit đúng structured receipt
   `cron_timer_started mode=inprocess`.
2. Sau mỗi snapshot load thành công, emit structured receipt bắt đầu
   `cron_timer_queue_loaded` và chỉ có metadata cần để vận hành: ít nhất `reason`, `tracker_count`,
   `subscription_count`, `lead_days`, `queue_size`; có thể thêm pending aggregate count. Không log
   tên tracker/subscription, reminder text, ciphertext, push endpoint, VAPID/DB/cookie/token/email.
3. Chọn logging mechanism khiến hai receipt nhìn thấy ở Fly với runtime logging hiện tại, nhưng không
   biến liveness thành DB probe, không tạo log spam/poll, và không làm warning/error receipt hiện hữu
   mất ý nghĩa. Ghi rõ trade-off trong PR.
4. Thêm test rõ ràng cho hai receipt và metadata safe. Test phải biết đỏ: cố ý gỡ token đang canh, thấy
   fail đúng assertion, hoàn nguyên, rồi chạy xanh. Ghi raw output của red/green trong PR body.
5. Chạy tối thiểu `uv run pytest tests/test_cron_timer.py -q`, `uv run pytest tests/test_cron_disabled_mode.py -q`,
   `git diff --check`, gitleaks/hook; chờ CI xanh. Tất cả output thực tế đưa vào PR body, không tóm tắt.

## Acceptance sau merge (T1 thực hiện)

Deploy production và lấy exact log `cron_timer_started mode=inprocess` cùng
`cron_timer_queue_loaded reason=startup ...`; sau đó mới đánh dấu startup/queue lane đạt. Mutation reload,
dispatch Web Push, iPhone và Neon-idle vẫn là lane riêng, chưa được claim từ task này.
