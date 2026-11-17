# miGarden trong microSched · Chạy thử và kế hoạch phát hành N01

MiGarden nằm ở **Ứng dụng → miGarden → Tổng quan / Cấu hình**. Web giữ bản cấu hình mong muốn, nhận bản đã áp dụng và ghi lại điều Controller báo. ESP32 vẫn giữ lịch, nút, hạn mức, deadline, STOP và sổ an toàn. Chưa provision hoặc chưa áp dụng cấu hình: không cho START từ web. Không bật lịch mẫu. Mặc định nút 15 phút, tối đa mỗi lượt 30 phút và tổng 120 phút trong bất kỳ 180 phút nào.

- [Hợp đồng API/QA provision](n01-api.md)
- [54 ca và các phần còn chờ](n01-qa-matrix.md)
- [Migration 0021](../../backend/alembic/versions/0021_migarden_zone_a.py)

## Chạy full app cô lập

Tạo DB PostgreSQL 18 + pgvector disposable có tên `microsched_n01_*`, dùng role bootstrap/migrator/app tách như Migration QA. Dùng env-file ngoài Git để chứa mật khẩu synthetic. Docker chỉ bind loopback. Ví dụ cho lane appcheck: container `microsched-n01-appcheck-pg`, `127.0.0.1:21891→5432`, image `pgvector/pgvector:pg18`. PM cấp tên/cổng riêng cho cell tích hợp.

Từ root, build PWA với lệnh repo:

```powershell
Push-Location frontend
npm ci
npm run build
Pop-Location
```

Từ `backend`, trước hết nạp các biến từ env-file QA riêng vào tiến trình terminal. File cần khai `CI_PG_BOOTSTRAP_URL`, `CI_MIGRATOR_PASSWORD`, `CI_APP_PASSWORD`, `NEON_MIGRATOR_URL` hoặc `CI_MIGRATOR_URL` cho migrator, và `DATABASE_URL` cho **role app**. Mọi URL phải trỏ vào DB disposable nói trên. Đặt `APP_ENV=local`, `MIGARDEN_ENABLED=true`, `MIGARDEN_PUBLIC_ORIGIN=http://127.0.0.1:8871` và `SESSION_COOKIE_SECURE=false` cho browser loopback. Không dùng các giá trị production hay copy file .env từ checkout khác.

```powershell
uv sync --frozen
uv run --frozen python -m scripts.prepare_ci_database
uv run --frozen alembic upgrade head
uv run --frozen python -m scripts.check_migration_drift
uv run --frozen python -m scripts.provision_migarden_qa issue --device-id qa-controller-a --output ../.local/n01/qa-device.token
uv run --frozen uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8871 --no-access-log
```

`/api/readyz` phải trả db up và commit khớp bản định kiểm (đặt `GIT_SHA` theo SHA đã xác minh). Browser local vào `http://127.0.0.1:8871/auth/dev-session` trên Chromium cô lập. Sau khi đăng nhập, mở miGarden, tạo cấu hình (ban đầu lịch tắt), lưu và chờ thiết bị. Để thử PWA + API, dùng bundle `dist` do backend phục vụ; có thể dùng Vite với `VITE_BACKEND_ORIGIN` và origin app đúng cổng Vite nếu phát triển.

PM ghép HTTPS `8765` với CA/leaf QA riêng và chỉ chuyển tiếp **POST** `/api/migarden/device/exchange` từ IP đã cấp vào loopback. Không proxy API người dùng hay `/auth/dev-session` ra LAN. Token QA là một file text mới quyền đọc riêng do runner dùng; DB chỉ chứa SHA-256. Không in, truyền secret trong argv, tái dùng giữa QA/production hoặc đưa vào browser evidence. Provision CLI chỉ chạy local, DB loopback tên N01, ID `qa-*`. Lệnh `revoke` chặn token và hủy START chưa grant; giữ lịch sử, ref, và unknown. Thu hồi không gửi STOP vật lý, cũng không tắt lịch local đã áp dụng. Khi rotate trên đúng binding: revoke trước, cấp file khác, cập nhật thiết bị bằng runner riêng theo quyền PM.

Chạy `npx --no-install playwright test --config playwright.migarden.config.ts` trong `frontend` với `N01_DEVICE_TOKEN_FILE` trỏ đến file QA, DB fresh cho hành trình. `N01_BROWSER_ORIGIN` tùy chọn nếu đổi cổng. Bài test thao tác UI thật và gửi record synthetic qua device API; chỉ chạy trên cell local đúng fixture đã đóng băng. Không đưa traces, seed/test code hoặc token vào release.

## Migration và cutover production để review

1. Freeze microSched exact head/base, firmware source/build/partition, wire v1 và dispositions, configuration/binding và QA matrix. Review app/device rồi mới push PR vào develop ở thời điểm được cấp quyền. Chạy đúng các check CI hiện hành; review nguồn chuyển tiếp và đường STOP trước khi enable.
2. `0021` là expand-only: sáu bảng miGarden, chỉ index/constraints/triggers và privilege trên bảng mới; không sửa bảng sản phẩm khác hay tạo config/lịch/identity mặc định. Schema role phải có quyền migration; app role thêm/sửa projection và thêm (không update/delete) config/raw report/boot. Lưu backup/restore receipt và kết quả rehearsal đã được duyệt trước khi apply. Deploy không tự chạy Alembic; đặt migration lane trước enable app và thiết bị.
3. Image mặc định **tắt miGarden**. Trước enable, xác nhận readiness exact deployed SHA + db up; xác minh `0021`/quyền, rollback và origin HTTPS riêng. Trong một bước commissioning được Owner cấp quyền, tạo **identity production và token 256 bit mới**, giữ hash scoped `zone-a`, `device_environment=production`; firmware production phải tin CA production, không mang profile QA. CLI QA cố ý không cấp credential production. Thu hồi/ngừng credential QA và không copy row DB QA sang production. Không dùng ảnh/lịch/record giả làm trạng thái vận hành.
4. Bật `MIGARDEN_ENABLED` và explicit `MIGARDEN_PUBLIC_ORIGIN` theo lần phát hành được cấp quyền. Kiểm chưa có lịch tự enable; cặp desired/applied, boot, STOP, hồ sơ phiên và điều kiện tại tủ. Kiểm report pace/bandwidth/storage và deploy readiness. Device, điện/nút, van tay, contained water và field nghiệm thu riêng. Hạn mức ở web là nội dung desired; chỉ ESP32 quyết định budget theo cấu hình đã áp dụng và sổ bản địa.
5. Nếu cần rút app: xác nhận tủ an toàn bằng đường tại nguồn theo quyền Owner/PM trước khi ngắt giao tiếp; **flag off không phải STOP** và lịch local có thể tiếp tục. Tắt flag/đưa app về revision tương thích, giữ schema và biên nhận; với cấu hình sai, lưu nội dung sửa bằng CAS, yêu cầu device xác nhận ref mới (không ghi đè ref cũ). Không downgrade DB thật hoặc reset ledger/NVS để giải quyết unknown. Downgrade dùng **chỉ** tại rehearsal throwaway với xác nhận rõ mất sáu bảng mới. Nếu đã cấp quyền thực thi mà mất báo cáo, dùng STOP/đối soát; không tạo một START mới để thử trạng thái.

## Payload và giới hạn bằng chứng

Exchange tối đa 32 KiB, 16 report/request, burst 24 và 8 exchange/giây/tiến trình cho identity đã xác thực; firmware giữ nhịp riêng theo wire (15s idle/5s active; theo sự kiện, backlog và backoff). Tính tham chiếu: 5.760 exchange idle/ngày/controller; chưa đo hạ tầng production. History trang 1–50, daily 7/30 ngày dùng tối đa 4.096 phiên đóng trong cửa sổ; kết quả luôn có chỉ dấu coverage, không xác nhận mọi record đã lên. Wire không có watermark ngày; projected vector không biến một ngày trống thành 0. Chưa chọn archival/retention; không xóa refs/receipts để làm DB gọn.

Bản ứng viên giữ một lần grant, sau commit. Mất response đã cấp quyền cần receipt từ thiết bị; timeout và snapshot off mới không tự xóa kết quả chưa rõ. Thiết bị vẫn thực thi final gate và sổ bền riêng; web không suy ngõ ra báo tắt thành nước đã ngừng.
