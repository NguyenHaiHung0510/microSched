# Task 058D — Mimi P1R dogfood recovery and interaction shell receipt

Date: 2026-09-20
Branch: eat/058-mimi-dogfood-recovery
Base commit: origin/develop@5b195a0714763a8a8673bf03aba6c7bbda663027
Status: **COMPLETED & OWNER-APPROVED — READY FOR MERGE INTO DEVELOP**

## 1. Outcome

Khép lại hoàn toàn lỗi Dogfood P1 (2026-09-16) và hoàn thiện toàn bộ tương tác giao diện và runtime contract theo spec hợp nhất:

1. **Kiến trúc giao diện nhị nguyên (Dual-Surface Architecture):**
   - **Side-chat (MimiDock):** Bảng điều khiển đồng hành nằm ở cạnh phải, mở song song với Task, Lịch, Ghi chú, Theo dõi. Hỗ trợ chuyển đổi nhanh giữa các cuộc trò chuyện và tạo hội thoại mới trực tiếp từ thanh tiêu đề.
   - **Mimi Control Center (Tab Mimi):** Đại bản doanh quản trị tổng thể với 4 phân hệ thực tế: *Tổng quan (Overview)*, *Hoạt động (Activity)*, *Hội thoại (Conversations)*, và *Cấu hình (Settings)*.
2. **Trải nghiệm hội thoại Workspace (Gemini Web-inspired):**
   - **Thanh bên trái (Cuộc trò chuyện):** Tích hợp ô tìm kiếm tức thì, phân loại *Đang dùng* / *Đã lưu*, danh mục *Đã ghim (Pinned)* lưu bền vững qua localStorage.
   - **Menu 3 chấm tinh gọn:** Gom toàn bộ thao tác (Ghim/Bỏ ghim, Đổi tên, Lưu trữ/Khôi phục) vào DropdownMenu từ radix-ui.
   - **Chỉ báo trạng thái sinh động:** Chấm vàng nhỏ khi cần xác nhận, spinner khi Mimi đang xử lý ngầm ở nền, chấm notify khi hoàn tất.
   - **Gập mở 2 phía linh hoạt (Foldable Rails):** Cả thanh bên trái lẫn thanh Workspace Rail bên phải đều gập/mở inline êm ái, loại bỏ hoàn toàn modal popup gây che khuất màn hình.
   - **Co giãn kịch trần (Full-height Stretch):** Đồng bộ chiều cao h-[calc(100dvh-5.5rem)] min-h-[40rem], giữ khung nhập liệu luôn nằm gọn trong tầm nhìn ngay cả trên cửa sổ trình duyệt không bật F11.
   - **Công thái học bàn phím:** Nhấn Enter để gửi nhanh, Shift + Enter xuống dòng, kiểm tra isComposing chống lỗi gõ tiếng Việt có dấu.
3. **Đồng bộ Nhận diện thương hiệu (Brand Identity Task 059):**
   - Hợp nhất nhánh develop mới nhất (commit 5b195a0).
   - Thay thế toàn bộ icon Bot cũ bằng component vector nguyên bản <MimiAvatar /> hỗ trợ 4 trạng thái sinh học: idle, 	hinking, xecuting, eady.
4. **Hợp đồng bảo vệ và Runtime an toàn (Backend Guards):**
   - **CAS Concurrency Guard:** Ngăn chặn tuyệt đối race-condition khi sửa preview; chỉ cho phép supersede đúng change_set_id, digest_sha256 và generation hợp lệ.
   - **Route Qualification Guard:** Thêm MIMI_ROUTE_FORCED_TOOL_CHOICE (
one | equired | unction), kiểm tra endpoint thực tế trước khi gửi forced tool choice.
   - Luồng SSE stream tách bạch với vòng đời server, hỗ trợ hủy run và Resume từ checkpoint.

## 2. Bằng chứng kiểm chứng (Verification Proofs)

| Bộ kiểm thử | Kết quả | Ghi chú |
|---|---|---|
| Frontend Lint | PASS | ESLint: 0 error, 0 warning |
| Frontend Typecheck | PASS | 	sc --noEmit: 0 error |
| Frontend Unit Tests | PASS | Vitest: 23 files passed, 160/160 tests passed |
| Frontend Production Build | PASS | Vite bundle + PWA surface guard + Apple icon guard |
| Playwright E2E | PASS | 4/4 kịch bản passed (Desktop 1280px & Mobile 390px) |
| Backend Lint & Format | PASS | Ruff: all checks passed |
| Backend Contracts | PASS | Pytest: 14 passed, 1 skipped (Postgres lane) |
| Pre-commit Hooks | PASS | Secret scan, merge conflict, trailing whitespace |
| Owner Local Preview | PASS | Đã duyệt trực tiếp trên giao diện local cổng 5158 |

## 3. Biên giới bàn giao

- Toàn bộ thay đổi mã nguồn nằm gọn gàng trên nhánh eat/058-mimi-dogfood-recovery.
- Sẵn sàng mở Pull Request vào develop để khép lại Task 058.
