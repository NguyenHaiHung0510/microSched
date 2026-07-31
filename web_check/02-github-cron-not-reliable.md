# BÁO CÁO KỸ THUẬT: PHÂN TÍCH WORKFLOW CRON HEARTBEAT

---

## 1. Tổng quan Cấu hình (`cron.yml`)

Workflow GitHub Actions [cron.yml](https://github.com/NguyenHaiHung0510/microSched/blob/develop/.github/workflows/cron.yml) đóng vai trò làm trigger định kỳ để gửi một POST request dạng "heartbeat" tới hệ thống backend sản xuất, nhằm giữ cho dịch vụ hoặc tiến trình xử lý không rơi vào trạng thái idle/sleep.

* **Trigger:**
* `schedule`: Chuỗi Cron `"17 3 * * *"` (chạy lúc 03:17 UTC hàng ngày).
* `workflow_dispatch`: Hỗ trợ kích hoạt thủ công từ GitHub UI.


* **Quyền hạn (`permissions`):** Tối ưu hóa nguyên tắc privilege tối thiểu với `contents: read`.
* **Execution Payload:** Thực thi lệnh `curl` với phương thức `POST` gửi token xác thực `CRON_TOKEN` qua HTTP Header `Authorization` tới endpoint:
`[https://microsched.fly.dev/api/cron/heartbeat](https://microsched.fly.dev/api/cron/heartbeat)`

---

## 2. Quy đổi Thời gian Thực thi (Timezone Mapping)

* **Cấu hình:** `03:17 UTC`
* **Múi giờ địa phương (ICT / UTC+7):**

$$\text{03:17 UTC} + 7\text{ giờ} = \text{10:17 AM (ICT)}$$



Lịch chạy cố định của workflow này là **10:17 AM hàng ngày (giờ Việt Nam)**.

---

## 3. Phân tích Nguyên nhân Workflow Không Kích Hoạt Sáng Nay

Nếu kiểm tra trong tab **Actions** và thấy workflow không được trigger vào thời điểm kỳ vọng, các nguyên nhân kỹ thuật cốt lõi gồm:

1. **Sai nhánh tích hợp (Default Branch Requirement):**
* GitHub Actions **chỉ kích hoạt** các scheduled workflow nằm trên nhánh mặc định (`main` hoặc `master`).
* *Nguyên nhân hiện tại:* File [cron.yml](https://github.com/NguyenHaiHung0510/microSched/blob/develop/.github/workflows/cron.yml) đang nằm trên nhánh `develop`. Nếu nhánh này chưa được merge vào branch mặc định, Cron Engine của GitHub sẽ bỏ qua file cấu hình này.


2. **Khung giờ chạy chưa tới:**
* Do lịch thực thi được thiết lập vào **10:17 AM (ICT)**, nếu kiểm tra vào các thời điểm sớm hơn trong buổi sáng, công việc vẫn nằm trong hàng chờ dự kiến.


3. **Độ trễ và nghẽn hàng chờ từ GitHub Actions Scheduler:**
* Lịch chạy scheduled của GitHub Actions không đảm bảo độ chính xác theo thời gian thực (real-time/deterministic). Vào các khung giờ cao điểm, job có thể bị delay từ 15 đến 60 phút do thiếu hụt tài nguyên Shared Runner.


4. **Tự động Disable do Repo Inactivity:**
* GitHub tự động vô hiệu hóa các scheduled workflow nếu repository không có commit hoặc hoạt động mới trong vòng 60 ngày liên tục.



---

## 4. Bảng Tóm tắt & Đề xuất Khắc phục

| Vấn đề | Hành động khắc phục |
| --- | --- |
| **Workflow nằm trên branch `develop**` | Merge `.github/workflows/cron.yml` vào nhánh mặc định (`main`/`master`). |
| **Cần kiểm tra ngay lập tức** | Truy cập tab **Actions** $\rightarrow$ chọn **Cron heartbeat** $\rightarrow$ bấm **Run workflow** (Manual Trigger). |
| **Định thời hạn chế độ trễ** | Nếu cần độ chính xác cao về thời gian, cân nhắc chuyển sang các dịch vụ Cron chuyên dụng bên ngoài (như Cron-job.org hoặc Cloudflare Workers Cron Triggers) để gọi webhook. |
