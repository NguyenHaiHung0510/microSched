# AGENTS.md — hướng dẫn cho executor ngoài hệ Claude (Codex, OpenCode, …)

Đọc **`CLAUDE.md`** trước tiên — đó là luật của repo này (trạng thái dự án, quyết định đã khóa, hard boundaries, working conventions). Mọi điều trong đó áp dụng cho bạn y như cho Claude Code.

Thêm cho agent thi công (vai T2 theo `docs/devops-brief.md` §7):

- Việc được giao nằm ở `agent-tasks/NNN-<slug>.md` — spec tự-chứa. Làm **đúng spec, không hơn**; mục "KHÔNG được làm" quan trọng ngang mục "Phải làm".
- Code trên branch **`feat/NNN-<slug>`** → PR nhỏ vào `develop`. Không commit thẳng `develop` (docs mới được phép), không đụng `main`.
- `docs/*.md` là decision record **đã chốt** — chỉ sửa đúng mục spec giao. Muốn làm khác điều đã ✅ CHỐT, hoặc thấy 2 brief mâu thuẫn → **dừng, ghi nhận, để chính chủ/T1 quyết** — đừng tự phát minh kiến trúc.
- Không bao giờ hỏi hay echo secret thật; code bằng `.env.example` (giá trị thật do chính chủ đặt tay). pre-commit + gitleaks đang hoạt động — đừng tìm cách vòng qua.
- Bí quá ~2 vòng thử → dừng + báo cáo kèm log, đừng đoán tiếp.
- **Lệnh bị timeout ≠ lệnh chưa làm gì.** Exit code chỉ nói "tôi bị giết", không nói "không có gì xảy ra" — `npm install` / `docker build` / `uv sync` thường đã ghi xong phần lớn công việc trước khi bị cắt. **Bắt buộc kiểm tra trạng thái thật trên đĩa** (`npm ls --depth=0`, `ls`, `git status`) trước khi kết luận thất bại. *Sự cố thật 2026-07-20 (task 004): báo "chưa có dependency/lockfile" trong khi lockfile 263KB và `node_modules` đầy đủ đang nằm đó — chỉ là lệnh vượt ngưỡng ~124s.* Với lệnh cài đặt dài: chia nhỏ thay vì một lệnh lớn.
- **`git add` xong chưa chắc file đã vào index — phải xác nhận.** `.gitignore` ở gốc repo theo khuôn Python và **nuốt im lặng** một số đường dẫn của hệ JS. Sau khi add, chạy `git status --short` + `git ls-files <thư-mục>`; nghi ngờ thì `git check-ignore -v <file>`. *Sự cố thật 2026-07-20 (task 004): mẫu `lib/` (thư mục phân phối Python) nuốt mất `frontend/src/lib/utils.ts` của shadcn → build local xanh (file có trên đĩa) nhưng CI đỏ (file không có trong git).* **Bài học chung: build local xanh không chứng minh gì về thứ bạn đã commit — chỉ CI mới chứng minh.**
- **Chờ CI xong rồi mới báo cáo hoàn thành.** Acceptance ghi "CI xanh" thì phải thật sự thấy xanh: `gh pr checks <PR> --watch`. Verify local pass mà CI đỏ = task **chưa xong**.
- Commit message tiếng Việt, giải thích *tại sao*, kèm `Co-Authored-By:` của agent thực thi (xem `git log`).
- **Text tiếng Việt phải đi qua file UTF-8, không qua tham số inline.** Mô tả PR: ghi ra file `.md` rồi `gh pr create --body-file <file>` — **không bao giờ** `--body "..."`. Commit message dài: `git commit -F <file>`. *Lý do (sự cố thật, PR #5 ngày 2026-07-20): truyền inline qua PowerShell làm mất toàn bộ dấu tiếng Việt (→ `?`) và nuốt ký tự `"` trong output JSON dán kèm. Mất dấu là **mất hẳn**, không decode ngược được — phải viết lại tay.*
