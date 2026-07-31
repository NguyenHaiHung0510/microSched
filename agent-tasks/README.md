# agent-tasks/ — hàng đợi việc giao cho agent

Mỗi file `NNN-<slug>.md` là **một spec tự-chứa** để giao cho một agent chạy độc lập.

> 📁 **`harness-audit/`** (thêm 2026-07-22) — thư mục con, đánh số riêng `01`/`02`, **không** thuộc hàng đợi 001–012. Chứa spec để kiểm tra và đồng bộ **chính bộ máy làm việc** (Claude ↔ Codex) khi chuyển từ chuyển-tay sang Claude-điều-phối-Codex. Output đổ vào `harness-reports/` ở gốc repo (thư mục có trong git, **nội dung thì không** — xem README trong đó).

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
| **008a** | `app/core/crypto.py` — AES-GCM + prefix `enc:v1:` | ✅ **DONE (2026-07-24)** — PR #14, merge `082c6e9`, deploy verified (app trả `commit` khớp SHA, `db up`). Seam 3 hàm `encrypt`/`decrypt`/`is_encrypted` + hằng `enc:v1:`, test tự-chứa 12 case. **Viết bởi Agent Opus/T1** (lần đầu Claude spawn agent thi công), review tay: đạt chuẩn AES-256-GCM. |
| **008b** | **CD** — merge `develop` → build → `fly deploy` → smoke test | ✅ **DONE (2026-07-22)** — trigger chỉ ở `develop`; smoke test kiểm cả git SHA; cron heartbeat chạy nhịp ngày và không chạm DB. **Nhắc thuốc đẩy sang 011** vì cron 5 phút sẽ giữ Neon thức; **script soi hóa đơn đẩy sang 008c** để không phình PR và thêm secret ngoài phạm vi. Khối B vẫn chờ chủ + T1 nghiệm thu sau merge. |
| 008c | Tính năng theo dõi chi phí hạ tầng (Fly/Neon) tích hợp trong app + phát hiện renew tự động + CRON 3 ngày cảnh báo | Tách khỏi 008b (2026-07-22). **📝 2026-07-31: chủ nâng phạm vi** từ "script đứng ngoài in bảng" thành tính năng thật trong microSched (fetch cùng nhịp app dùng + CRON riêng Cloud Scheduler); ý chính là tự phát hiện lúc gói cước renew bằng cách so hiệu số giữa 2 lần đo (số đo mới < số cũ hẳn ⇒ vừa tất toán chu kỳ). Chi tiết đầy đủ + lý do: `cost-brief.md` §7.4. **Vẫn KHÔNG chặn gì, ưu tiên thấp — làm khi rảnh**, giao T2 tự thiết kế toàn bộ (không chỉ thi công theo spec có sẵn). |
| 008d | 3 mục tồn từ security review toàn dự án (2026-07-23) | ✅ **DONE (2026-07-24)** — PR #15 (migration `0002` che `note.title` + test tĩnh) + #16 (gitleaks +5 biến quyền cao, `compare_digest` bytes), merged; migration **đã áp Neon + query `pg_constraint` xác nhận**; live `c68b710`. Agent-Opus/MAX thi công, T1 verify. — *lịch sử:* Mục 2 (gitleaks bỏ sót `NEON_OWNER_URL`) + mục 3 (`compare_digest` non-ASCII → 500) là việc máy móc. Mục 1 từng là quyết định treo (`task` che cả title khi private, `note` chỉ che body — hoá ra **cả hai đều đúng spec**, vì §6 viết `task.*` và `note.body_md` trong cùng một ô) → **chủ chốt 2026-07-23: che `note.title`; bảng con `*_item` do app canh, không phải DB** (`tracking-brief.md` §6). Nên chạy **trước 008** trong lúc bảng còn rỗng: sửa bây giờ là DDL thuần, sửa sau là migration có backfill. |
| **008** | **task slice** — API + UI + test, đi trọn một entity | **Task đặt khuôn**: hình dạng error response, phân trang, cách đăng ký router, cách gọi crypto seam. Mọi slice sau bắt chước — kể cả bắt chước *quy trình nghiệm thu*, nên 008b phải xong trước. Chạy **một mình**. |
| **018** | Batch polish `TasksScreen.tsx` (tooltip bị cắt · vùng bấm cả thẻ · banner trễ hạn · 2 microcopy · `data-testid`) + `refetchInterval` đồng bộ đa thiết bị + **Playwright suite đầu tiên** | ✅ **DONE 2026-07-31** — PR #52 (spec + `docs/qa-framework.md`) → PR #53 (thi công), merge + live `d6bd782`. Chuỗi kiểm: T3+T2 review spec (hạng-đôi, `devops-brief.md` §7.3.i) → Codex thi công qua **CLI trực tiếp** (không phải skill `codex:rescue` — chỉ map tới `workspace-write`) → T1 verify bắt 5 bug hạ tầng test → T3 review lần 2 **trên diff thật** bắt thêm 4 finding. Harness Playwright (`frontend/e2e/`, `data-testid` convention, CI job `Frontend e2e`) sẵn sàng cho `009`–`012` kế thừa. Chi tiết đầy đủ: `CLAUDE.md` 📝 31/07. |
| **009** | note slice | ⇢ song song được (điều kiện: `devops-brief.md` §8). **Việc kế tiếp thật sự: chi tiết hoá §2 thành dòng file/hàm cụ thể** (như `008m` đã làm) — `018` đã xong, harness sẵn sàng kế thừa. |
| 010 | calendar + import `.ics/.xlsx` | ⇢ song song được. Giải luôn `migration-mapping-brief.md` §3 (121 dòng lịch lệch) |
| 011 | tracker capture (ghi log) **+ nhắc thuốc** | **Bắt buộc có 008a** — `entry.amount` CHECK vô điều kiện, không ghi nổi plaintext. **Nhận nhắc thuốc từ 008b (2026-07-22):** cron 5 phút/lần hỏi DB "tới giờ chưa" = **sự cố Neon 22/07 mặc áo khác** (nhịp tối thiểu GH Actions cron đúng bằng cửa sổ idle Neon). Lời giải — lịch tính trước vs PWA notification (vướng caveat iOS, `frontend-brief.md`) — là **quyết định thiết kế chưa chốt**, không thuộc task hạ tầng. |
| 012 | cutover migration + verify | Theo `migration-mapping-brief.md` §5 |
| **016** | private unlock — PIN 6 số + Argon2id, `private_until` TTL 36 phút | ✅ **DONE (2026-07-31)** — PR #67 (code, live `de95d30`) + PR #68 (2 dated note vào `auth-brief.md` §3). Đảo 2 chi tiết thiết kế khi thi công thật: bí mật là **PIN 6 chữ số** (không phải passphrase), TTL **36 phút** + throttle **thang leo 10/20/36 toàn cục**. QA 7 trục trên production xác nhận cửa một chiều đã đóng (unlock/lock round-trip bằng PIN thật, throttle sống sót qua reload). Nợ nhỏ còn treo: 2 chỗ non-text contrast dưới ngưỡng WCAG 1.4.11 (viền badge throttled `1,17:1`, viền input `1,32:1`) — chưa fix, không chặn. |
| **017** | outbox offline — Dexie + hàng đợi ghi | Thiết kế đã khoá ở `frontend-brief.md` §2 (Dexie + outbox tự viết, không sync-engine) và luồng ghi ở `tracking-brief.md:150`. **Chưa có spec thi công.** Hai seam (UUIDv7 sinh ở client + ghi idempotent) đã mở sẵn ở `008m` — 017 chỉ còn dựng hàng đợi thật lên trên hai seam đó. Đề xuất chạy sau 011, theo đúng lý lẽ `008m` dùng để hoãn nó: dựng một lần cho cả 4 loại thực thể rẻ hơn dựng riêng cho task rồi nới bốn lần. |
| — | **phiên AI Bước 1** (embedding provider, dimension, LLM mặc định, hybrid retrieval) | ✅ chốt 2026-07-22: **sau 012, không sớm hơn**. `forward-spec.md` §60 đã hạ nó từ *chặn đường* xuống *rẻ và để sau* (cột `vector` nullable ⇒ thêm sau chỉ là một migration nhỏ), và ở cỡ dữ liệu này hai chân structured+keyword gánh gần hết. **⚠️ Điều kiện vào phiên:** phải xử lý ⚠️ OPEN ở `schema-physical-brief.md` §125 (**luật "cột mã hoá không bao giờ có embedding"**) **TRƯỚC** khi chọn provider — chọn provider rồi mới nhớ ra là chọn mù. Nay có thêm điều kiện thứ hai: **016 phải xong** (xem trên). |

**📝 2026-07-28 — tách "private unlock · outbox offline" khỏi ô không-số thành 014/015.** Trước đó cả hai chia chung một dòng `—` trong bảng, không spec, không acceptance, không ai sở hữu — dạng tồn tại yếu nhất trong hàng đợi này, trong khi `auth-brief.md` §3 đã khoá thiết kế Argon2id rất kỹ. Phát hiện kèm theo lúc soát: toggle riêng tư đã sống trên UI mà chưa có cổng mở khoá phía sau — một cửa một chiều đang chạy thật trên production. Đánh số không đổi thứ tự thực thi đã có, chỉ đổi tư cách từ "ghi chú" thành "mục hàng đợi có chủ".

**📝 2026-07-28 (muộn hơn, phiên `008g`) — 🔒 số vừa gán ở note trên ĐÃ TRÙNG với hai spec có thật, đổi lại thành 016/017.** `014`/`015` không rảnh: `agent-tasks/014-cron-rss-watch.md` và `agent-tasks/015-gitleaks-history-scan.md` đã tồn tại từ phiên DevSecOps 26/07 — một cái đã **live**, một cái đang `⚠️ OPEN`. Cùng một buổi đánh số hai việc thật lên hai số đã có chủ, không ai kiểm `ls agent-tasks/` trước khi gõ số vào bảng. Đã đổi hai dòng trên thành **016** (private unlock) / **017** (outbox offline); không mục nào đổi nội dung hay thứ tự thực thi. ⇒ **Luật thêm:** trước khi gán một số task mới, `ls agent-tasks/` xem số đó đã có file chưa — bảng tổng hợp trong README và thư mục file là hai nơi có thể lệch nhau, và không có cơ chế nào tự báo khi chúng lệch.

**📝 2026-07-22 — 008a và 008b KHÔNG phụ thuộc nhau.** Ràng buộc thật chỉ có hai: *008a trước mọi CRUD* và *008b trước 008* (để task đặt khuôn có CD lúc nghiệm thu). Giữa 008a↔008b không có chiều nào. ⇒ **008a đang bị chặn vì chủ chưa sinh `ENCRYPTION_MASTER_KEY`, thì chạy 008b trước — không mất gì.** Ghi lại vì thứ tự "008a → 008b" dễ bị đọc nhầm thành dây chuyền, rồi cả hàng đợi đứng chờ một biến môi trường. *(📝 cùng ngày, muộn hơn: `ENCRYPTION_MASTER_KEY` đã sinh + `.env` + Fly ⇒ **008a hết bị chặn**. Ghi chú trên giữ nguyên vì bài học về dây-chuyền-tưởng-tượng vẫn đúng, chỉ là ví dụ đã hết hiệu lực.)*

**Hai điều kiện cổng cho cutover, dễ quên:** ⓐ app phải **dùng được hằng ngày thay app cũ** (⇒ 008–010 xong) — đổ 163 task + 49 note vào Neon khi chưa xem/sửa được là tự mất daily driver; ⓑ **soi lại giá** — `cost-brief.md` ghi rõ *"bắt buộc trước khi cutover"*.

**Vì sao crypto ở 008a chứ không phải lúc cutover** (kiểm chứng 2026-07-21): dữ liệu migrate **không chạm cột mã hóa nào** — tracker/entry/subscription tạo rỗng, và 163 task + 49 note đều `is_private=false` (private mode là tính năng *mới*), mà CHECK của task/note là **có điều kiện** (`NOT is_private OR ...`) nên plaintext hợp lệ. ⇒ **rủi ro backfill dữ liệu ≈ 0**. Cái phải tránh là **retrofit code**: nếu 008 viết không có seam crypto thì lúc private-mode tới phải chọc lại mọi đường đọc/ghi task/note.
