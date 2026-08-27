# Task 034 — Project journey narrative

> **Trạng thái: ✅ OWNER-APPROVED**
> **Branch:** `docs/034-project-journey-narrative`
> **Base exact:** `16ada1a7fd36b526f92a6bf1d7de44db044b9865`

## Mục tiêu

Thay câu hero PTIT → AI Engineer trong README bằng một narrative ngắn, recruiter-friendly nhưng có giọng cá nhân, mô tả microSched như chặng thứ ba và phiên bản trưởng thành nhất hiện tại của hành trình xây công cụ cá nhân.

## Phạm vi bắt buộc

1. Chỉ sửa `README.md` và file task spec này.
2. README phải liên kết đúng ba chặng theo repo public:
   - `Code_HoTro_HocTap`: CLI C++ sơ khai từ năm nhất.
   - `VC_QuanLyThoiGian`: desktop Python/Flet, vibe-coded, đóng gói `.exe`.
   - `microSched`: tiếp tục phát triển harness engineering và AI engineering.
3. Narrative phải nhấn sự trưởng thành trong tư duy sản phẩm, kỹ thuật và cách cộng tác với AI.
4. Giữ fact microSched được dùng thật từ `21/07/2026`; không claim mọi roadmap đã shipped.

## Không được làm

- Không sửa app code, docs khác, workflow, metadata GitHub, UI hoặc dependency.
- Không dùng giọng sáo rỗng/portfolio quá đà.
- Không thêm screenshot, video, homepage placeholder hay claim AI feature chưa shipped.

## Acceptance

- README có hai link public đúng URL và narrative dễ đọc ở phần hero.
- Diff chỉ gồm `README.md` và `agent-tasks/034-project-journey-narrative.md`.
- Markdown/link sanity check, `pre-commit` và `git diff --check` chạy được.
- Commit dùng file UTF-8 qua `git commit -F`; push branch và mở PR vào `develop`, không merge.

## Evidence boundary

- `[ĐÃ CHẠY]` chỉ dùng cho command/receipt thật trên branch này.
- `[SUY LUẬN]` là diễn giải public-facing từ yêu cầu owner và repo public; không thay thế CI, production, browser hoặc physical-device receipt.
