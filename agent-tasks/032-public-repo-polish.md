# Task 032 — Public repository polish

> **Trạng thái: ✅ OWNER-APPROVED**
> **Branch:** `docs/032-public-repo-polish`
> **Original authoring base:** `14787f5366d9e487df9dff4f7fd44d635fe09be9`
> **Rebased onto:** `c961b5b37439e6dbe588f110f3cbc560d8a497dc`

## Mục tiêu

Làm public surface của microSched dễ hiểu với recruiter/public visitor nhưng trung thực với trạng thái code hiện tại: README tiếng Việt ngắn, license rõ, security/contributing tối thiểu, frontend README không còn boilerplate và ignore rules phủ đúng generated local artifacts.

## Phạm vi bắt buộc

1. Tạo README root theo thứ tự: hero/badges; định vị personal software laboratory/app toàn năng và dự án trục từ Software Engineering PTIT tới AI Engineer; dùng thật từ 21/07/2026; core features đã có; ecosystem future/in-progress (miGarden, microLink, Mimi) không claim shipped; architecture; thực tế hạ tầng; local setup; quality/security; roadmap honest; MIT.
2. Tạo `LICENSE` bằng nguyên văn MIT với `Copyright (c) 2026 Nguyễn Hải Hưng`; README nêu logo/icon project thuộc MIT còn dependencies/assets bên thứ ba theo license riêng.
3. Tạo `SECURITY.md` dùng GitHub private vulnerability reporting, không email và không public secret/personal data.
4. Tạo `CONTRIBUTING.md`: PR vào `develop`, discuss thay đổi lớn, cấm secret/real personal data.
5. Thay `frontend/README.md` boilerplate bằng hướng dẫn setup/scripts/PWA-offline boundary thật.
6. Thêm `/worktrees/` và `/output/` vào `.gitignore`, kèm comment lý do; audit không được che source path ngoài scope.

## Không được làm

- Không sửa app code, UI, workflow, decision brief, deploy config hay dependency.
- Không thêm screenshot/video/homepage placeholder.
- Không claim AI assistant, cascade, MCP, full offline outbox, iPhone Safari acceptance hoặc production health đã hoàn tất.

## Acceptance

- Markdown/link sanity check chạy được; không còn boilerplate Vite ở `frontend/README.md`.
- `git diff --check` exit 0.
- Diff chỉ nằm trong các file được task cho phép.
- `git status --short` và `git ls-files` xác nhận scope sau stage.
- Commit dùng UTF-8 file qua `git commit -F`; chưa push/open PR trong task này.

## Evidence boundary

- `[ĐÃ CHẠY]` = output command kiểm tra trên worktree/branch này.
- `[SUY LUẬN]` = diễn giải public-facing dựa trên code/decision brief; không thay thế CI, production, browser hoặc physical-device receipt.
