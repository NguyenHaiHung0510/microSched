# 001 — pre-commit + gitleaks

> **Trạng thái:** ⏳ TODO
> **Model tier đề xuất:** Sonnet (tầng giữa) · **Effort:** medium
> *Lý do: việc có khuôn mẫu rõ, ít mơ hồ thiết kế — không cần Opus. Nhưng có bước cài đặt + verify thật (không chỉ viết file), nên đừng để effort thấp nhất.*

## Bối cảnh (đọc để hiểu, đừng bỏ qua)

**microSched** — web app cá nhân một-người-dùng (task/note/lịch/tracker), AI-first. Đọc `CLAUDE.md` ở gốc repo trước khi bắt đầu.

**Trạng thái hiện tại: PRE-CODE.** Repo mới chỉ có decision record trong `docs/` + một script tiện ích trong `scripts/`. **Chưa có** application code, `pyproject.toml`/`requirements.txt`, test suite, CI workflow. Đừng bịa ra lệnh build/lint/test — chúng chưa tồn tại.

**Vì sao làm việc này NGAY BÂY GIỜ, lúc còn chưa có code:**
1. Repo là **public trên GitHub** → secret lọt vào là công khai tức thì.
2. Kiến trúc đã chốt sẽ dùng `.env` cho credential Neon/Fly/LLM API key (`CLAUDE.md` mục "Hard boundaries") — **code + `.env` sắp xuất hiện**. Dựng hàng rào trước khi có thứ để rò rỉ thì rẻ hơn nhiều.
3. Đây cũng là **mục tiêu học tập** (dự án này là "dự án trục" của kế hoạch học AI-engineering — DevOps/CI là một nhánh đáng học, xem `docs/learnings-applied.md`).

**Đã có sẵn ở phía GitHub** (đừng làm lại): ruleset `protect-main` (chặn xóa/force-push, bắt buộc PR vào `main`), GitHub secret scanning + push protection đã bật. **Việc của spec này là lớp phòng thủ phía LOCAL** — chặn ngay lúc `git commit`, trước cả khi push.

## Mục tiêu

Dựng [pre-commit](https://pre-commit.com/) với hook [gitleaks](https://github.com/gitleaks/gitleaks) + một bộ hook vệ sinh cơ bản, chạy được trên **Windows (Git Bash + PowerShell)** — máy chính chủ là Windows 11.

## Phải làm

1. **`.pre-commit-config.yaml`** ở gốc repo:
   - `gitleaks` (từ repo `gitleaks/gitleaks`, pin theo tag phiên bản cụ thể, không dùng nhánh động).
   - Bộ `pre-commit-hooks` cơ bản: `check-added-large-files`, `end-of-file-fixer`, `trailing-whitespace`, `check-merge-conflict`, `check-yaml`, `detect-private-key`.
   - **Pin `rev:` cho mọi repo hook** — tra phiên bản mới nhất tại thời điểm làm (đừng chép version từ trí nhớ; version cũ có thể đã bị bỏ).
2. **Cài và kích hoạt thật**: `pre-commit install` → xác nhận `.git/hooks/pre-commit` tồn tại.
3. **Chạy thử toàn repo**: `pre-commit run --all-files`. Nếu hook vệ sinh sửa file (whitespace/EOF) → xem lại diff, đảm bảo **chỉ đụng whitespace**, không đổi nội dung/nghĩa của decision record. Repo hiện có nhiều `.md` tiếng Việt — cẩn thận không làm hỏng ký tự Unicode.
4. **Chứng minh gitleaks thật sự chặn**: tạo file tạm chứa secret giả (ví dụ một chuỗi dạng AWS key test), thử `git commit` → **phải bị chặn**. Sau đó **xóa sạch file tạm** và đảm bảo nó không lọt vào bất kỳ commit nào.
5. **Ghi tài liệu**: thêm mục ngắn vào `CLAUDE.md` (phần "Working conventions") nói repo có pre-commit và cách cài lại sau khi clone (`pre-commit install`) — vì hook **không** tự theo git clone.
6. **Cập nhật `agent-tasks/README.md`**: đổi trạng thái 001 thành `✅ DONE (ngày)`.

## KHÔNG được làm

- **Không** commit `.env`, secret thật, hay file tạm dùng để test gitleaks.
- **Không** tạo GitHub Actions workflow / CI trong task này — CI để sau khi có code thật (task riêng).
- **Không** thêm hook lint/format cho Python (`ruff`, `black`…) — **chưa có code Python**, thêm bây giờ là hook chạy vào khoảng không. Để task scaffold app.
- **Không** đụng vào `docs/*.md` ngoài phạm vi sửa whitespace tự động; đây là decision record, nội dung đã chốt.
- **Không** sửa ruleset / cấu hình bảo mật phía GitHub — đã cấu hình xong.
- **Không** rewrite git history.

## Acceptance (kiểm chứng được)

- [ ] `pre-commit --version` chạy được.
- [ ] `.pre-commit-config.yaml` tồn tại, mọi hook đều pin `rev` cụ thể.
- [ ] `.git/hooks/pre-commit` tồn tại (đã `pre-commit install`).
- [ ] `pre-commit run --all-files` **pass toàn bộ** ở lần chạy thứ hai (lần đầu có thể fail do tự sửa whitespace — đó là bình thường).
- [ ] Thử commit secret giả → **bị chặn**, và file thử đã bị xóa sạch khỏi working tree.
- [ ] `git status` sạch hoặc chỉ còn thay đổi có chủ đích.
- [ ] `CLAUDE.md` có hướng dẫn `pre-commit install` sau khi clone.

## Bàn giao

Commit lên nhánh `develop` (không phải `main` — `main` có ruleset bắt buộc PR). Message theo phong cách repo: tiếng Việt, mô tả *tại sao*, kèm dòng `Co-Authored-By:` như các commit trước (xem `git log`).
