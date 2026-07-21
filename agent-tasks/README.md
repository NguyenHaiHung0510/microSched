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
- **Liệt kê mọi "công tắc môi trường" chủ phải bật tay** vào mục *Việc của CHỦ trước khi chạy task* (bổ sung 2026-07-20). Máy chủ **cố ý không để dịch vụ nặng tự khởi động** (Docker Desktop là ví dụ — tốn RAM, chậm boot, nên tắt mặc định). Executor gặp daemon chưa chạy sẽ tưởng môi trường hỏng và đốt một vòng escalate cho thứ chỉ cần bấm một nút. → Task nào cần Docker/DB local/VPN/dịch vụ nền nào khác thì **ghi rõ thành checkbox**, kèm đúng thông báo lỗi sẽ gặp nếu quên bật, để nhận ra ngay thay vì đi debug.
- **Ghi kèm Skill + MCP ở header** (bổ sung 2026-07-20), dạng:
  `> Executor: … · Bậc: … · Effort: … · **Skill gợi ý:** … · **MCP cần:** …`
  **Luật cứng: skill/MCP là trợ lực, KHÔNG phải điều kiện.** Mọi thứ liệt kê ở đó phải thay thế được bằng tiêu chí viết rõ trong thân spec — spec vẫn phải chạy trọn vẹn bởi executor *không có* skill đó. Lý do: specs ở đây tự-chứa và **executor-agnostic** by design (xem `AGENTS.md`); buộc spec vào một skill là buộc nó vào một harness, mất đúng tính chất khiến 003/004 giao cho ai cũng chạy được. Skill làm việc *nhanh hơn*, không làm việc *khác đi*.
  Phân bổ theo loại việc: **task build** hiếm khi cần MCP · **task test** là chỗ của MCP (Chrome-DevTools/Playwright, vai T3 — `docs/devops-brief.md` §7) · **task UI có quyết định thẩm mỹ thật** là chỗ của design skill (vd `superdesign`) — **không** dùng cho UI kỹ thuật thuần như trang chào của 004.

## Hàng đợi
| # | Việc | Trạng thái |
|---|---|---|
| 001 | pre-commit + gitleaks (chặn secret trước khi commit) | ✅ DONE (2026-07-19) — đã kiểm chứng thật |
| 002 | gitleaks: rule riêng cho connection string DB (lỗ phát hiện khi kiểm chứng 001) | ✅ DONE (2026-07-19) — đã kiểm chứng thật |
| 003 | Scaffold backend — FastAPI skeleton + tooling + CI nền | ✅ DONE (2026-07-20) |
| 004 | Scaffold frontend — Vite/React/shadcn, serve cùng origin | ✅ DONE (2026-07-20) |
| 005 | Docker multi-stage + deploy Fly.io đầu tiên | ✅ DONE (2026-07-20) |
| 006 | Neon + role riêng + đúc DDL thật (Alembic 0001 + QA gates) | ✅ DONE (2026-07-21) — **PR đáng review kỹ nhất chuỗi** |
| 007 | Auth: Google OIDC + allowlist + session server-side | 📋 TODO (sau 006) — security-critical, executor T1 hoặc T2-Sol |

**Từ 003 (phase B — scaffold):** executor mặc định = **T2 Codex** theo `docs/devops-brief.md` §7; task code chạy trên branch `feat/NNN-<slug>` → PR nhỏ vào `develop` để T1 review diff (docs vẫn commit thẳng `develop`). Chuỗi 003→007 = **walking skeleton**: trang thật trên `*.fly.dev` có login Google. Sau 007 (chưa spec, đừng tự chế): private unlock (Argon2id) · outbox offline · cutover migration · CI-deploy.
