# agent-tasks/ — hàng đợi việc giao cho agent

Mỗi file `NNN-<slug>.md` là **một spec tự-chứa** để giao cho một agent chạy độc lập.

## Cách dùng
1. Mở một session Claude Code mới trong repo này.
2. Ra lệnh: *"Đọc `agent-tasks/001-precommit-gitleaks.md` và thực hiện đúng spec đó."*
3. Agent làm xong → chính chủ (hoặc agent điều phối) review theo mục **Acceptance** trong spec.
4. Xong thì đổi `Trạng thái:` ở đầu file thành `✅ DONE (ngày)` — **không xóa file**, giữ làm lịch sử.

## Quy ước viết spec
- **Tự-chứa**: đọc được ở session 0-context. Không tham chiếu hội thoại cũ, chỉ tham chiếu file trong repo.
- **Nêu rõ ràng buộc + lý do**, không chỉ ra lệnh — agent cần biết *tại sao* để xử lý đúng lúc gặp tình huống ngoài spec.
- **Acceptance kiểm chứng được** (chạy lệnh nào, thấy output gì), không phải "làm cho tốt".
- **Nói rõ cái KHÔNG được làm** — phần này quan trọng ngang phần phải làm.
- Mỗi spec ghi sẵn **model tier + effort đề xuất** để chính chủ chọn đúng mức, không đốt token thừa.

## Hàng đợi
| # | Việc | Trạng thái |
|---|---|---|
| 001 | pre-commit + gitleaks (chặn secret trước khi commit) | ✅ DONE (2026-07-19) — đã kiểm chứng thật |
| 002 | gitleaks: rule riêng cho connection string DB (lỗ phát hiện khi kiểm chứng 001) | ✅ DONE (2026-07-19) — đã kiểm chứng thật |
| 003 | Scaffold backend — FastAPI skeleton + tooling + CI nền | ✅ DONE (2026-07-20) |
| 004 | Scaffold frontend — Vite/React/shadcn, serve cùng origin | ✅ DONE (2026-07-20) |
| 005 | Docker multi-stage + deploy Fly.io đầu tiên | 📋 TODO (sau 004) |
| 006 | Neon + role riêng + đúc DDL thật (Alembic 0001 + QA gates) | 📋 TODO (sau 005) — **PR đáng review kỹ nhất chuỗi** |
| 007 | Auth: Google OIDC + allowlist + session server-side | 📋 TODO (sau 006) — security-critical, executor T1 hoặc T2-Sol |

**Từ 003 (phase B — scaffold):** executor mặc định = **T2 Codex** theo `docs/devops-brief.md` §7; task code chạy trên branch `feat/NNN-<slug>` → PR nhỏ vào `develop` để T1 review diff (docs vẫn commit thẳng `develop`). Chuỗi 003→007 = **walking skeleton**: trang thật trên `*.fly.dev` có login Google. Sau 007 (chưa spec, đừng tự chế): private unlock (Argon2id) · outbox offline · cutover migration · CI-deploy.
