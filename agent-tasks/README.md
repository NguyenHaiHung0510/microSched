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

## Quy ước BÁO CÁO (bổ sung 2026-07-21 — sau 007)

**Executor phải tách rõ hai thứ trong báo cáo/PR: cái đã CHẠY và cái chỉ SUY LUẬN.**

Không viết *"đã làm xong X và nó chạy"*. Viết:
> **Đã chạy:** `pytest` 34 pass · `ruff` sạch · `vite build` ok
> **CHƯA chạy:** hành vi nút đăng xuất trên trình duyệt thật
> **Vì sao vẫn tin là đúng:** *(lập luận — và nói thẳng rằng đây là lập luận, không phải bằng chứng)*

**Lý do (số liệu thật từ 007, cùng một model, cùng một ngày):** lỗi lọt tới chủ **không** phân bố đều theo độ khó, mà bám đúng vào tầng executor **không chạy được** thứ mình viết — backend có pytest: 0 lỗi lọt; frontend/trình duyệt không có vòng lặp nào: 4 lỗi lọt. Biên độ chênh đó **lớn hơn khoảng cách giữa các tier model**.

⇒ Hệ quả cho việc giao task:
- **Sức mạnh model và vòng lặp kiểm chứng là hai trục khác nhau, và trục vòng lặp thắng.** Model yếu hơn mà *chạy thử rồi mới nói* đáng tin hơn model mạnh *suy luận rồi khẳng định*.
- §7 `devops-brief` phân tier theo blast-radius vẫn đúng, nhưng **thiếu một trục**: việc nào cần trình duyệt thì giao cho **thứ lái được trình duyệt** (T3 + MCP Chrome-DevTools), bất kể tier.
- **Build/CI xanh chỉ chứng minh code biên dịch và unit test qua — không chứng minh hành vi.** Acceptance đụng bản build production (Docker, PWA/service worker, cookie, redirect, OAuth) **bắt buộc** có bước nhìn bằng mắt trên bản deploy thật, ghi rõ *nhìn cái gì*.
- Việc của người review đổi: **kiểm xem ranh giới "đã chạy / chưa chạy" có trung thực không**, và có gì quan trọng đang nằm im trong vùng "chưa chạy" không — thay vì làm lại công việc.

## Hàng đợi
| # | Việc | Trạng thái |
|---|---|---|
| 001 | pre-commit + gitleaks (chặn secret trước khi commit) | ✅ DONE (2026-07-19) — đã kiểm chứng thật |
| 002 | gitleaks: rule riêng cho connection string DB (lỗ phát hiện khi kiểm chứng 001) | ✅ DONE (2026-07-19) — đã kiểm chứng thật |
| 003 | Scaffold backend — FastAPI skeleton + tooling + CI nền | ✅ DONE (2026-07-20) |
| 004 | Scaffold frontend — Vite/React/shadcn, serve cùng origin | ✅ DONE (2026-07-20) |
| 005 | Docker multi-stage + deploy Fly.io đầu tiên | ✅ DONE (2026-07-20) |
| 006 | Neon + role riêng + đúc DDL thật (Alembic 0001 + QA gates) | ✅ DONE (2026-07-21) — **PR đáng review kỹ nhất chuỗi** |
| 007 | Auth: Google OIDC + allowlist + session server-side | ✅ **DONE (2026-07-21)** — nghiệm thu thật trên fly.dev, 34 test; **walking skeleton khép**. 4 lỗi chỉ lộ ra ở trình duyệt → `auth-brief.md` §6.3 |

**Từ 003 (phase B — scaffold):** executor mặc định = **T2 Codex** theo `docs/devops-brief.md` §7; task code chạy trên branch `feat/NNN-<slug>` → PR nhỏ vào `develop` để T1 review diff (docs vẫn commit thẳng `develop`). Chuỗi 003→007 = **walking skeleton**: trang thật trên `*.fly.dev` có login Google.

## Sau 007 — phase C (lộ trình; **chỉ 008b có spec — phần còn lại đừng tự chế**)

Ghi 2026-07-21. Bản trước của mục này liệt kê *"private unlock · outbox · cutover migration · CI-deploy"* và **sót hẳn CRUD + UI** — tức khối việc lớn nhất của dự án không nằm trong hàng đợi. Vá lại:

| # | Việc | Ghi chú |
|---|---|---|
| **008a** | `app/core/crypto.py` — AES-GCM + prefix `enc:v1:` | Nhỏ (~60–80 dòng + test). **Không phải phiên thiết kế** — cơ chế đã chốt (`schema-physical-brief.md` §7.1), format đã chốt (K18), vị trí khóa đã chốt (`db-and-data-model-brief.md` §6). Chạy **ngay sau 007, trước mọi CRUD**. ⚠️ Cần `ENCRYPTION_MASTER_KEY` — **chủ chưa sinh** (xem `backend/.env.example`, bảng cấp phát). |
| **008b** | **CD** — merge `develop` → build → `fly deploy` → smoke test | ✅ **DONE (2026-07-22)** — trigger chỉ ở `develop`; smoke test kiểm cả git SHA; cron heartbeat chạy nhịp ngày và không chạm DB. **Nhắc thuốc đẩy sang 011** vì cron 5 phút sẽ giữ Neon thức; **script soi hóa đơn đẩy sang 008c** để không phình PR và thêm secret ngoài phạm vi. Khối B vẫn chờ chủ + T1 nghiệm thu sau merge. |
| 008c | Script soi hoá đơn Fly/Neon → in bảng so ngưỡng | Tách khỏi 008b (2026-07-22). `cost-brief.md` §7.4 định gộp vì *"đúng lúc hạ tầng cron ra đời"* — nhưng hạ tầng đó **còn nguyên sau 008b**, gộp chỉ làm PR phình gấp đôi + cần thêm 2 secret. Không chặn 008. |
| **008** | **task slice** — API + UI + test, đi trọn một entity | **Task đặt khuôn**: hình dạng error response, phân trang, cách đăng ký router, cách gọi crypto seam. Mọi slice sau bắt chước — kể cả bắt chước *quy trình nghiệm thu*, nên 008b phải xong trước. Chạy **một mình**. |
| 009 | note slice | ⇢ song song được (điều kiện: `devops-brief.md` §8) |
| 010 | calendar + import `.ics/.xlsx` | ⇢ song song được. Giải luôn `migration-mapping-brief.md` §3 (121 dòng lịch lệch) |
| 011 | tracker capture (ghi log) **+ nhắc thuốc** | **Bắt buộc có 008a** — `entry.amount` CHECK vô điều kiện, không ghi nổi plaintext. **Nhận nhắc thuốc từ 008b (2026-07-22):** cron 5 phút/lần hỏi DB "tới giờ chưa" = **sự cố Neon 22/07 mặc áo khác** (nhịp tối thiểu GH Actions cron đúng bằng cửa sổ idle Neon). Lời giải — lịch tính trước vs PWA notification (vướng caveat iOS, `frontend-brief.md`) — là **quyết định thiết kế chưa chốt**, không thuộc task hạ tầng. |
| 012 | cutover migration + verify | Theo `migration-mapping-brief.md` §5 |
| — | **phiên AI Bước 1** (embedding provider, dimension, LLM mặc định, hybrid retrieval) | ✅ chốt 2026-07-22: **sau 012, không sớm hơn**. `forward-spec.md` §60 đã hạ nó từ *chặn đường* xuống *rẻ và để sau* (cột `vector` nullable ⇒ thêm sau chỉ là một migration nhỏ), và ở cỡ dữ liệu này hai chân structured+keyword gánh gần hết. **⚠️ Điều kiện vào phiên:** phải xử lý ⚠️ OPEN ở `schema-physical-brief.md` §125 (**luật "cột mã hoá không bao giờ có embedding"**) **TRƯỚC** khi chọn provider — chọn provider rồi mới nhớ ra là chọn mù. |
| — | private unlock (Argon2id) · outbox offline | xen vào theo nhu cầu, không chặn cutover |

**📝 2026-07-22 — 008a và 008b KHÔNG phụ thuộc nhau.** Ràng buộc thật chỉ có hai: *008a trước mọi CRUD* và *008b trước 008* (để task đặt khuôn có CD lúc nghiệm thu). Giữa 008a↔008b không có chiều nào. ⇒ **008a đang bị chặn vì chủ chưa sinh `ENCRYPTION_MASTER_KEY`, thì chạy 008b trước — không mất gì.** Ghi lại vì thứ tự "008a → 008b" dễ bị đọc nhầm thành dây chuyền, rồi cả hàng đợi đứng chờ một biến môi trường. *(📝 cùng ngày, muộn hơn: `ENCRYPTION_MASTER_KEY` đã sinh + `.env` + Fly ⇒ **008a hết bị chặn**. Ghi chú trên giữ nguyên vì bài học về dây-chuyền-tưởng-tượng vẫn đúng, chỉ là ví dụ đã hết hiệu lực.)*

**Hai điều kiện cổng cho cutover, dễ quên:** ⓐ app phải **dùng được hằng ngày thay app cũ** (⇒ 008–010 xong) — đổ 163 task + 49 note vào Neon khi chưa xem/sửa được là tự mất daily driver; ⓑ **soi lại giá** — `cost-brief.md` ghi rõ *"bắt buộc trước khi cutover"*.

**Vì sao crypto ở 008a chứ không phải lúc cutover** (kiểm chứng 2026-07-21): dữ liệu migrate **không chạm cột mã hóa nào** — tracker/entry/subscription tạo rỗng, và 163 task + 49 note đều `is_private=false` (private mode là tính năng *mới*), mà CHECK của task/note là **có điều kiện** (`NOT is_private OR ...`) nên plaintext hợp lệ. ⇒ **rủi ro backfill dữ liệu ≈ 0**. Cái phải tránh là **retrofit code**: nếu 008 viết không có seam crypto thì lúc private-mode tới phải chọc lại mọi đường đọc/ghi task/note.
