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
2. `0021` là expand-only: sáu bảng miGarden, chỉ index/constraints/triggers và privilege trên bảng mới; không sửa bảng sản phẩm khác hay tạo config/lịch/identity mặc định. Schema role phải có quyền migration; app role thêm/sửa projection và thêm (không update/delete) config/raw report/boot. Lưu backup/restore receipt và kết quả rehearsal đã được duyệt trước khi apply. Deploy không tự chạy Alembic; đặt migration lane đi tiến `0021→0022` trước enable app và thiết bị. Giữ ứng dụng cũ read-only hoặc flag off trong lúc kiểm; rollback app-only, giữ nguyên schema/evidence.
3. Image mặc định **tắt miGarden**. Trước enable, xác nhận readiness exact deployed SHA + db up; xác minh `0022`/quyền, rollback và origin HTTPS riêng. Trong một bước commissioning được Owner cấp quyền, tạo **identity production và token 256 bit mới**, giữ hash scoped `zone-a`, `device_environment=production`; firmware production phải tin CA production, không mang profile QA. CLI QA cố ý không cấp credential production. Thu hồi/ngừng credential QA và không copy row DB QA sang production. Không dùng ảnh/lịch/record giả làm trạng thái vận hành.
4. Bật `MIGARDEN_ENABLED` và explicit `MIGARDEN_PUBLIC_ORIGIN` theo lần phát hành được cấp quyền. Kiểm chưa có lịch tự enable; cặp desired/applied, boot, STOP, hồ sơ phiên và điều kiện tại tủ. Kiểm report pace/bandwidth/storage và deploy readiness. Device, điện/nút, van tay, contained water và field nghiệm thu riêng. Hạn mức ở web là nội dung desired; chỉ ESP32 quyết định budget theo cấu hình đã áp dụng và sổ bản địa.
5. Nếu cần rút app: xác nhận tủ an toàn bằng đường tại nguồn theo quyền Owner/PM trước khi ngắt giao tiếp; **flag off không phải STOP** và lịch local có thể tiếp tục. Tắt flag/đưa app về revision tương thích, giữ schema và biên nhận; với cấu hình sai, lưu nội dung sửa bằng CAS, yêu cầu device xác nhận ref mới (không ghi đè ref cũ). Không downgrade DB thật hoặc reset ledger/NVS để giải quyết unknown. Downgrade dùng **chỉ** tại rehearsal throwaway với xác nhận rõ mất sáu bảng mới. Nếu đã cấp quyền thực thi mà mất báo cáo, dùng STOP/đối soát; không tạo một START mới để thử trạng thái.

## Payload và giới hạn bằng chứng

Exchange tối đa 32 KiB, 16 report/request, burst 24 và 8 exchange/giây/tiến trình cho identity đã xác thực; firmware giữ nhịp riêng theo wire (15s idle/5s active; theo sự kiện, backlog và backoff). Tính tham chiếu: 5.760 exchange idle/ngày/controller; chưa đo hạ tầng production. History trang 1–50, daily 7/30 ngày dùng tối đa 4.096 phiên đóng trong cửa sổ; kết quả luôn có chỉ dấu coverage, không xác nhận mọi record đã lên. Wire không có watermark ngày; projected vector không biến một ngày trống thành 0. Chưa chọn archival/retention; không xóa refs/receipts để làm DB gọn.

Bản ứng viên giữ một lần grant, sau commit. Mất response đã cấp quyền cần receipt từ thiết bị; timeout và snapshot off mới không tự xóa kết quả chưa rõ. Thiết bị vẫn thực thi final gate và sổ bền riêng; web không suy ngõ ra báo tắt thành nước đã ngừng.

## Sửa theo independent review: STOP và đối soát

Sau `0021`, áp dụng [migration 0022](../../backend/alembic/versions/0022_migarden_stop_reconciliation.py) trước khi chạy bản đã sửa review. Bản này thêm ba giá trị supporting cho provenance STOP/failed ingest, không đổi wire v1 hoặc lịch sử config/Session. Có thể thử downgrade `0022→0021→head` chỉ trên DB disposable; không downgrade DB đang vận hành.

- **F1 — Đích provision:** CLI chỉ đọc process input; `Settings(_env_file=None)`, URL explicit và engine factory phải trùng hoàn toàn. URL QA không được mang query để đổi host/database ngầm. Không dùng cached engine của app, không fallback dotenv và không in DSN/token.
- **F2 / D1 / D4 — Poison report:** từng record hợp lệ được ingest và project trong savepoint riêng. Ví dụ: nếu một report lỗi đi cùng `stop_processed` đúng request và đúng boot, app sẽ ACK receipt STOP đó sau khi transaction ngoài đã commit. Report lỗi hoặc ID có nhiều nội dung trong cùng gói không nhận ACK. Gói có lỗi vẫn có thể giao STOP đúng boot; không gửi desired config, candidate hoặc grant, và không dùng snapshot để xác lập trạng thái. App trả `retry_after_seconds=30`. Root/version/target và giới hạn body/count vẫn bắt buộc.
- **F3 / D5 — Chưa xác nhận Dừng:** `stop_unconfirmed` vẫn là STOP cần giao/đối soát; thời gian trôi, negative receipt và trạng thái off không mở lại remote START. Lặp thao tác Dừng giữ cùng ID nếu cùng boot. Chỉ `stop_processed` tích cực gắn đúng request/boot mới xác nhận xử lý. Sau reboot, Owner gửi STOP mới cho đích mới; receipt tích cực của STOP mới đối soát các STOP cũ bằng ID mới. Receipt âm đến sau vẫn được lưu nhưng không mở lại STOP đã confirmed/stale. ACK không khẳng định nước ngừng.
- **F4 — Boot chưa có clock:** một boot chưa từng xác lập có thể thành **đích STOP tạm**, tách khỏi boot/current snapshot dùng cho START. Không dùng nó để cấp quyền, đổi applied hoặc dự báo; một boot đã retired không thay target/current bằng việc gửi lại. Khi nhiều boot unknown cạnh tranh, không chọn cái tới cuối làm current. Boot mới chỉ thành current cho START khi observation fresh, có thứ tự so với watermark đang giữ và đạt mọi gate. Pending STOP cần receipt, kể cả sau chuyển boot.
- **F5 — Applied:** snapshot unknown/unordered không đổi last-applied hoặc forecast, kể cả epoch cao hơn. Thông tin đang thấy ở snapshot có thể chưa resolve; ứng dụng chỉ dùng bản đã xác nhận để dự báo.
- **F6 — Giới hạn phục hồi:** nếu đã thấy output on nhưng không resolve được Session/grant, `unidentified_execution` giữ chặn remote START. STOP vẫn dùng được. Snapshot off, TTL, boot mới và terminal của lượt khác **không** là bằng chứng đủ để xóa. Bản N01 không có API tự mở khóa hoặc công cụ reset cờ/sổ. Muốn khôi phục cần Owner/PM xác minh exact Controller/binding/boot và nguồn evidence gắn với possible execution, kiểm an toàn tại tủ, rồi duyệt phương án đối soát có thể kiểm chứng. Nếu không có evidence, giữ fail-closed là disposition; không sửa DB/NVS để làm QA xanh.
- **F7 — Bootstrap:** chạy lại bootstrap sau migration phải tiếp tục giữ config/report/boot append-only. Grant chung và revoke ngoại lệ nằm cùng transaction. Phép thử throwaway tạo violation quyền UPDATE/DELETE có chủ đích, xác nhận nó bị phát hiện, chạy bootstrap để phục hồi và kiểm quyền bằng role app. Không chạy bootstrap production trong N01.

App đối soát từng report theo fingerprint nội dung và boot nguồn, kể cả backlog được gửi lại từ một boot khác. Mục chỉ được gỡ khi đúng record đó được ghi và project thành công. Snapshot off, thời gian trôi, gói trống hoặc nội dung mới dùng cùng event ID không gỡ được mục cũ. Ledger giữ tối đa 512 mục. Nếu số lỗi vượt trần hoặc ledger cũ không đủ provenance, app giữ cờ chặn remote START; N01 không có lệnh tự clear. Giữ nguyên DB và bằng chứng để Owner/PM đối soát. Nếu cần rollback về app trước sửa ledger, giữ flag miGarden off: app cũ không đọc an toàn ledger mới. Quay lại bản đọc được ledger để mở lại miGarden.

Bằng chứng tập trung ở `test_migarden_review.py`, `test_pg_review_*`, `test_pg_groupfix_*`, `test_migarden_reconciliation.py` và `test_migarden_bootstrap_pg.py`. Retest độc lập của parent vẫn là gate riêng.


## Packet cấp credential production để Owner duyệt

[Tool offline](../../backend/scripts/prepare_migarden_commission.py) đã có source; không phải admin API. `prepare` không nối DB, không đọc dotenv. Nó tạo thư mục private mới dưới checkout `.local` gồm `device.token`, `binding.sql`, `plan.json`; SQL/plan chỉ mang digest SHA-256. Lệnh `apply` là thao tác production **chưa được cấp quyền trong N01**: chỉ đọc URL ở `MIGARDEN_COMMISSION_DATABASE_URL`, kiểm exact host/port/database/role app so với packet rồi mới chạy SQL. Không lấy URL app/cached engine/develop redirect. Packet phải được Owner xem và duyệt trước. Rehearsal dùng `--environment qa`: cả prepare và apply yêu cầu host loopback, port ghi rõ trong URL, tên DB `microsched_n01_*` và không có query options. Khi apply, `localhost` được ghim vào `127.0.0.1`; tool truyền endpoint đã kiểm trực tiếp cho PostgreSQL, không dùng libpq service hay redirect.

Cách chuẩn bị khi đã có quyền tương ứng, bằng private files (các tên ví dụ không phải host/account thật):

```powershell
uv run --frozen python -m scripts.prepare_migarden_commission prepare --operation issue --environment production --device-id prod-controller-a --expected-host db.example.invalid --expected-database microsched --expected-state-file ../.local/commission/expected-state.json --output-dir ../.local/commission/review-01
```

`expected-state.json` có đúng bốn trường `device_id`, `device_environment`, `token_hash`, `revoked_at`. Cấp lần đầu: cả bốn null. Trước khi cấp/rotate/revoke, operator lấy giá trị hiện có bằng truy vấn read-only vào **file riêng**, không ước lượng trạng thái từ UI hoặc ghi đè mù:

```sql
SELECT json_build_object(
  'device_id',device_id,'device_environment',device_environment,
  'token_hash',token_hash,'revoked_at',revoked_at
) FROM microsched.migarden_zone WHERE zone_id='zone-a';
```

Nếu chưa có row, dùng trạng thái null ở trên; SQL tạo đúng row Zone A rồi khóa. `binding.sql` kiểm current_database và role, lock Zone A, so sánh cả bốn giá trị bằng `IS DISTINCT FROM`; sai thì abort cả transaction. Chỉ hỗ trợ cấp lần đầu/rotate cùng identity hoặc thu hồi. Không đổi identity tự động, không đổi QA thành production, không clear unresolved execution/report reconciliation, và không có no-op override. Rotate cần revoke credential cũ trước; mỗi issue/revoke ghi sự kiện vào audit_log với old/new digest và operation ID, không raw token. Revoke không xóa lịch sử/sổ; START chưa grant bị hủy, không khẳng định physical STOP.

Sau **phê duyệt production riêng**, operator nạp URL từ file/env riêng vào tiến trình, xác minh exact target rồi mới chạy:

```powershell
uv run --frozen python -m scripts.prepare_migarden_commission apply --plan-dir ../.local/commission/review-01
```

Cấp credential thiết bị không thay login người dùng: Owner vẫn dùng OAuth login-only/allowlist hiện có, session cookie và origin guard; không tạo human password/account mới. Device identity `prod-controller-a` giữ token riêng, chỉ cho exchange của `zone-a/zone-a-v1`, không gọi human routes. Không đưa token vào browser hay frontend bundle.

File `network-private.json` do parent/Owner giữ đúng bốn trường `wifi_ssid`, `wifi_password`, `base_url` (origin HTTPS thật), `ca_pem` (public CA root, không private key). Offline command ghép cùng token/identity của packet:

```powershell
uv run --frozen python -m scripts.prepare_migarden_commission profile --plan-dir ../.local/commission/review-01 --network-file ../.local/commission/network-private.json
```

Kết quả `release-profile.json` UTF-8 không BOM, theo firmware `mg-rel-v1/profile-v1`; mặc định `fixture_verified:false`. Chỉ dùng flag `--fixture-verified` sau khi Owner chấp thuận exact circuit/fixture evidence. FW lead/parent sở hữu công cụ ghi **đúng blob/key production** và verify readback riêng, không dùng lệnh LAB PROVISION, ảnh NVS rỗng hoặc erase để thay thế. App tool này không mở COM/flash/actuate; phương thức ghi profile release phải được bind vào package commissioning firmware trước final Owner approval.

Rehearsal synthetic kiểm fresh DB đi tiến `0021→0022`, issue → CAS replay reject → wrong-old-state reject → revoke có audit → không rotate khi unknown → phục hồi oracle thử → rotate cùng identity có audit. Xem `test_migarden_commission_pg.py`; không dùng DB có dữ liệu thật hoặc downgrade thật.
