## 📋 BÁO CÁO KIỂM CHỨNG CƠ CHẾ AUTO-STOP & AUTO-START

**Tên ứng dụng:** `microsched`

**Nền tảng:** Fly.io (Region: `sin` - Singapore, Machine ID: `d8d9564b42e9e8`)

**Mục tiêu:** Tối ưu hóa chi phí vận hành bằng cách cho phép server tự động ngắt (Stop) khi không có truy cập và tự động bật lại (Start) khi có request mới.

---

## I. TỔNG HỢP CÁC THAY ĐỔI CẤU HÌNH (`fly.toml`)

Để đạt được mục tiêu tối ưu, cấu hình dịch vụ HTTP (`[http_service]`) đã được điều chỉnh như sau:

| Thông số | Cấu hình ban đầu | Cấu hình cập nhật | Tác động kỹ thuật |
| --- | --- | --- | --- |
| **`auto_stop_machines`** | `false` | `"stop"` | Cho phép Fly Proxy tự phát lệnh ngắt Machine khi không có lưu lượng truy cập thực tế. |
| **`min_machines_running`** | `1` | `0` | Cho phép giảm số lượng Machine hoạt động tối thiểu về 0 (thay vì bắt buộc giữ 1 máy chạy 24/7). |
| **`auto_start_machines`** | `true` | `true` | Đảm bảo Fly Proxy tự kích hoạt mở lại Machine khi có request HTTP đến. |

---

## II. THÔNG BÁO TỪ FLY DOCTOR

*(Thông tin copy y nguyên nội dung từ giao diện [Logs & Errors](https://fly.io/apps/microsched/monitoring))*

> ### Fly Doctor
>
>
> #### Symptom: App is not listening to the expected port
>
>
> Something in your code or configuration is preventing your app from listening on `0.0.0.0` at the port specified by your fly.toml `internal_port` `8000`. Your users will see error 502 accessing your app. This is an issue with your application code.
> * Your app could be missing environment variables. Some frameworks require specific environment variables to be set otherwise they stop your app.
> * The app could be listening to the wrong port, you can either change your fly.toml `internal_port` or modify your application code to listen on the correct port.
> * Make sure your app is listening to `0.0.0.0` and not `localhost` or `127.0.0.1`.
> * Your app could not be listening at all, check your logs to make sure it's running correctly.
>
>
> After making the necessary changes, you can deploy the updates from the deployments page or `fly deploy` on your computer.

---

## III. CHUỖI LOG & MỐC THỜI GIAN THỰC TẾ CHI TIẾT (ENRICHED)

Dưới đây là toàn bộ chuỗi log hệ thống thu thập từ giao diện [Logs & Errors](https://fly.io/apps/microsched/monitoring):

```text
================================================================================
GIAI ĐOẠN 1: TÁI KHỞI ĐỘNG CẤU HÌNH BAN ĐẦU & SẴN SÀNG NHẬN HEALTH CHECK
================================================================================
02:22:40 Pulling container image registry.fly.io/microsched@sha256:a336b55104c6172eeeb1e6ea2d770ef13be5c1bddf1995a5066bc919726ad48b
02:22:40 Container image registry.fly.io/microsched@sha256:a336b55104c6172eeeb1e6ea2d770ef13be5c1bddf1995a5066bc919726ad48b already prepared
02:22:41 Configuring firecracker
02:22:41 INFO Sending signal SIGINT to main child process w/ PID 642
02:22:41 INFO: Shutting down
02:22:41 INFO: Waiting for application shutdown.
02:22:41 INFO: Application shutdown complete.
02:22:41 INFO: Finished server process [642]
02:22:42 INFO Main child exited normally with code: 0
02:22:42 INFO Starting clean up.
02:22:42 [45208.391901] reboot: Restarting system
02:22:43 2026-07-23T02:22:43.338814894 [01KY6CGEZ229T0R4Q50VTMZ8DD:main] Running Firecracker v1.14.4
02:22:43 2026-07-23T02:22:43.339067489 [01KY6CGEZ229T0R4Q50VTMZ8DD:main] Listening on API socket ("/fc.sock").
02:22:44 INFO Starting init (commit: d21f468d)...
02:22:44 INFO Preparing to run: `uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000` as microsched
02:22:44 INFO [fly api proxy] listening at /.fly/api
02:22:44 Machine created and started in 3.946s
02:22:44 Health check 'servicecheck-00-http-8000' on port 8000 has failed. Your app is not responding properly. Services exposed on ports [80, 443] will have intermittent failures until the health check passes.
02:22:45 2026/07/23 02:22:45 INFO SSH listening listen_address=[fdaa:9f:45c6:a7b:186:d37b:71e0:2]:22
02:22:49 INFO: Started server process [641]
02:22:49 INFO: Waiting for application startup.
02:22:49 INFO: Application startup complete.
02:22:49 INFO: Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
02:22:49 INFO: 172.19.16.185:39970 - "GET /api/healthz HTTP/1.1" 200 OK
02:22:49 Health check 'servicecheck-00-http-8000' on port 8000 is now passing.

================================================================================
GIAI ĐOẠN 2: CHUỖI HEALTH CHECK ĐỊNH KỲ NỘI BỘ (30 GIÂY/LẦN)
================================================================================
02:23:19 INFO: 172.19.16.185:58884 - "GET /api/healthz HTTP/1.1" 200 OK
02:23:49 INFO: 172.19.16.185:33092 - "GET /api/healthz HTTP/1.1" 200 OK
02:24:19 INFO: 172.19.16.185:44236 - "GET /api/healthz HTTP/1.1" 200 OK
02:24:49 INFO: 172.19.16.185:53224 - "GET /api/healthz HTTP/1.1" 200 OK
02:25:19 INFO: 172.19.16.185:33098 - "GET /api/healthz HTTP/1.1" 200 OK
02:25:49 INFO: 172.19.16.185:51500 - "GET /api/healthz HTTP/1.1" 200 OK
02:26:19 INFO: 172.19.16.185:61620 - "GET /api/healthz HTTP/1.1" 200 OK
02:26:49 INFO: 172.19.16.185:64466 - "GET /api/healthz HTTP/1.1" 200 OK
02:27:19 INFO: 172.19.16.185:36968 - "GET /api/healthz HTTP/1.1" 200 OK
02:27:49 INFO: 172.19.16.185:41736 - "GET /api/healthz HTTP/1.1" 200 OK
02:28:19 INFO: 172.19.16.185:55962 - "GET /api/healthz HTTP/1.1" 200 OK
02:28:49 INFO: 172.19.16.185:44784 - "GET /api/healthz HTTP/1.1" 200 OK
02:29:19 INFO: 172.19.16.185:43292 - "GET /api/healthz HTTP/1.1" 200 OK

================================================================================
GIAI ĐOẠN 3: KÍCH HOẠT AUTO-STOP (MÁY DỪNG HOÀN TOÀN)
================================================================================
02:29:33 App microsched has excess capacity, autostopping machine d8d9564b42e9e8. 0 out of 1 machines left running (region=sin, process group=app)
02:29:33 INFO Sending signal SIGINT to main child process w/ PID 641
02:29:33 INFO: Shutting down
02:29:33 INFO: Waiting for application shutdown.
02:29:33 INFO: Application shutdown complete.
02:29:33 INFO: Finished server process [641]
02:29:34 INFO Main child exited normally with code: 0
02:29:34 INFO Starting clean up.
02:29:34 [ 410.670804] reboot: Restarting system

================================================================================
GIAI ĐOẠN 4: KÍCH HOẠT AUTO-START KHI TRUY CẬP WEBSITE
================================================================================
02:32:01 Starting machine
02:32:01 2026-07-23T02:32:01.420032558 [01KY6CGEZ229T0R4Q50VTMZ8DD:main] Running Firecracker v1.14.4
02:32:01 2026-07-23T02:32:01.420318233 [01KY6CGEZ229T0R4Q50VTMZ8DD:main] Listening on API socket ("/fc.sock").
02:32:02 INFO Starting init (commit: d21f468d)...
02:32:02 INFO Preparing to run: `uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000` as microsched
02:32:02 INFO [fly api proxy] listening at /.fly/api
02:32:02 Machine started in 1.672s
02:32:02 machine started in 1.792627504s
02:32:03 2026/07/23 02:32:03 INFO SSH listening listen_address=[fdaa:9f:45c6:a7b:186:d37b:71e0:2]:22
02:32:03 Health check 'servicecheck-00-http-8000' on port 8000 has failed. Your app is not responding properly. Services exposed on ports [80, 443] will have intermittent failures until the health check passes.
02:32:07 INFO: Started server process [642]
02:32:07 INFO: Waiting for application startup.
02:32:07 INFO: Application startup complete.
02:32:07 INFO: Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
02:32:07 INFO: 172.19.16.185:61882 - "GET /api/healthz HTTP/1.1" 200 OK
02:32:07 machine became reachable in 4.508853797s

================================================================================
GIAI ĐOẠN 5: XỬ LÝ LƯU LƯỢNG THỰC TẾ & TIẾP TỤC DUY TRÌ BÌNH THƯỜNG
================================================================================
02:32:07 INFO: 172.16.16.186:51600 - "GET /vite.svg HTTP/1.1" 200 OK
02:32:07 Health check 'servicecheck-00-http-8000' on port 8000 is now passing.
02:32:08 waiting for machine to be reachable on 0.0.0.0:8000 (waited 5.196220357s so far)
02:32:08 machine became reachable in 5.196758677s
02:32:08 INFO: 172.16.16.186:51608 - "GET /api/me HTTP/1.1" 401 Unauthorized
02:32:08 INFO: 172.16.16.186:51612 - "GET /api/me HTTP/1.1" 401 Unauthorized
02:32:09 INFO: 172.16.16.186:51620 - "GET /sw.js HTTP/1.1" 304 Not Modified
02:32:10 INFO: 172.16.16.186:51628 - "GET /workbox-9c191d2f.js HTTP/1.1" 304 Not Modified
02:32:37 INFO: 172.19.16.185:42846 - "GET /api/healthz HTTP/1.1" 200 OK
02:33:07 INFO: 172.19.16.185:34598 - "GET /api/healthz HTTP/1.1" 200 OK
02:33:37 INFO: 172.19.16.185:61348 - "GET /api/healthz HTTP/1.1" 200 OK
02:34:07 INFO: 172.19.16.185:57608 - "GET /api/healthz HTTP/1.1" 200 OK
02:34:20 INFO: 172.19.16.185:36284 - "GET /api/healthz HTTP/1.1" 200 OK
02:34:50 INFO: 172.19.16.185:53344 - "GET /api/healthz HTTP/1.1" 200 OK

```

---

## IV. BẢNG THỐNG KÊ MỐC THỜI GIAN THỰC TẾ ENRICHED

*(Thông tin do AI Model **Gemini** tự bổ sung và tổng hợp dựa trên dữ liệu nhật ký hệ thống hiển thị trực tiếp từ [Fly.io Dashboard](https://fly.io/apps/microsched/monitoring))*

| Mốc thời gian | Sự kiện | Chi tiết đo lường |
| --- | --- | --- |
| **`02:22:49` – `02:29:19**` | Duy trì Health Check | Nhận liên tục 14 requests `GET /api/healthz` (chu kỳ chính xác 30s/lần). |
| **`02:29:19` $\rightarrow$ `02:29:33**` | Phát hiện Idle | **14 giây** kể từ health check cuối cùng để Fly Proxy xác định không có traffic người dùng và ra lệnh Auto-Stop. |
| **`02:29:33` $\rightarrow$ `02:29:34**` | Tắt ứng dụng (Shutdown) | **1 giây** để gửi `SIGINT`, hoàn tất cleanup và đưa Machine về trạng thái `STOPPED`. |
| **`02:29:34` $\rightarrow$ `02:32:01**` | Trạng thái nghỉ | **2 phút 27 giây** Machine hoàn toàn dừng hoạt động (0/1 máy chạy, 0% CPU/RAM). |
| **`02:32:01`** | Nhận request từ Web | Người dùng mở trang web [frontend](https://microsched.fly.dev/), Fly Proxy kích hoạt Auto-Start. |
| **`02:32:01` $\rightarrow$ `02:32:02**` | Boot MicroVM | **`1.672 giây`** (`Machine started in 1.672s`) để bật VM Firecracker v1.14.4. |
| **`02:32:02` $\rightarrow$ `02:32:07**` | Start App (Uvicorn) | **~5 giây** để khởi tạo tiến trình Python/Uvicorn (`Started server process [642]`). |
| **`02:32:07`** | Reachable Time | Máy chính thức phản hồi: **`4.508853797s`** (`machine became reachable`). |
| **`02:32:07` – `02:32:10**` | Phục vụ Requests | Trả về 5 requests thực tế (`/vite.svg` 200 OK, `/api/me` 401, `/sw.js` 304, v.v.). |

Dưới đây là đoạn phân tích bổ sung dành riêng cho thông báo từ **Fly Doctor** vừa xuất hiện trong log trước đó. Bạn có thể chép đoạn này để append (nối tiếp) trực tiếp vào cuối báo cáo đã lập:

---

## V. PHÂN TÍCH CHUYÊN SÂU THÔNG BÁO TỪ FLY DOCTOR

*(Phân tích và đánh giá kỹ thuật dưới đây do AI Model **Gemini** thực hiện, dựa trên nội dung cảnh báo do hệ thống chẩn đoán tự động Fly Doctor ghi nhận trong log).*

### 1. Bản chất của cảnh báo

Trong quá trình khởi động Machine (tại các mốc mốc thời gian `02:22:44` và `02:32:03`), Fly Doctor đưa ra cảnh báo:

> *"App is not listening to the expected port... Health check 'servicecheck-00-http-8000' on port 8000 has failed."*

Cảnh báo này xuất hiện do **sự lệch pha về thời gian (timing issue)** giữa chu kỳ kiểm tra của Fly Proxy và tiến trình khởi chạy ứng dụng Python/Uvicorn:

* **Thời điểm Fly Proxy kiểm tra (`02:32:01 – 02:32:03`):** MicroVM Firecracker vừa được bật lên, Fly Proxy lập tức gửi HTTP probe đến cổng `8000`. Lúc này tiến trình Uvicorn chưa hoàn tất khởi tạo nên chưa lắng nghe trên cổng `8000`, dẫn đến lỗi kết nối tạm thời.
* **Thời điểm Uvicorn sẵn sàng (`02:32:07`):** Tiến trình server hoàn tất `Application startup complete` và mở socket lắng nghe trên `0.0.0.0:8000`. Ngay lập tức ở mốc `02:32:07`, Health check đổi trạng thái thành `passing` (`200 OK`).

### 2. Đánh giá mức độ ảnh hưởng

* **Không phải lỗi mã nguồn hay cấu hình cổng (False Alarm):** Mặc dù Fly Doctor gợi ý ứng dụng có thể lắng nghe sai cổng (`localhost` thay vì `0.0.0.0`) hoặc thiếu biến môi trường, thực tế log Uvicorn xác nhận server đã binding chuẩn xác: `Uvicorn running on [http://0.0.0.0:8000](http://0.0.0.0:8000)`.
* **Trải nghiệm người dùng:** Trạng thái lỗi chỉ kéo dài trong cửa sổ thời gian khởi động app (**~4.5 giây**). Ngay khi app sẵn sàng, Fly Proxy đã chuyển hướng request thành công và trả về dữ liệu bình thường (`200 OK`, `304 Not Modified`) mà không bị gián đoạn hay trả về lỗi `502 Bad Gateway` cho người dùng cuối.

### 3. Đề xuất tối ưu (Tùy chọn)

Nếu muốn loại bỏ hoàn toàn thông báo cảnh báo nhiễu này từ Fly Doctor trong các lần Cold Start sau, có thể điều chỉnh tham số kiểm tra sức khỏe trong file `fly.toml`:

* **Tăng `initial_delay` (hoặc `grace_period`):** Cấu hình cho Fly Proxy chờ khoảng `5s` sau khi bật Machine mới bắt đầu gửi request Health Check đầu tiên, tương ứng với thời gian boot thực tế của Uvicorn.
