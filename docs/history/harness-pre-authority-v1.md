# Historical harness receipts — not current policy

Moved on 2026-09-06 from docs/devops-brief.md §7. Historical content below is preserved for rationale, not instructions, authority or current model/tool availability. Current policy: [harness-policy.md](../harness-policy.md). Earlier blanket authorization schema remains in Git history at pre-migration commit 58718ace321782d6f10515956cc851b48c861068.

### Historical harness receipts — RETIRED

Các mục tiếp theo của §7 là receipt lịch sử, giữ để truy nguyên quyết định và failure mode; không phải policy, runtime catalog hoặc routing hiện hành. ClaudeRelay đã RETIRED, không dành thêm maintenance/QA.

Bối cảnh: bước vào phase B (scaffold), chính chủ chốt bộ công cụ thi công. Tra giá/thị trường **live 2026-07-20** (nguồn cuối mục — thị trường coding-plan đổi theo quý, đừng tin con số này quá 10/2026). Nguyên tắc phân vai: **theo blast-radius của lỗi, không theo độ to của việc** (cùng nguyên tắc sequencing AI của chính app).

| Tầng | Công cụ | Vai |
|---|---|---|
| **T1 — óc** | **Codex Desktop (Main Thread)** (GPT-5.6 Sol/xhigh; PAYG: Antigravity Opus/Gemini 3.6 Flash) | Lập kế hoạch, viết spec `agent-tasks/`, ADR khi có quyết định mới, **review diff cuối trước merge**, debug khi T2 bế tắc, và chỉ đạo chiến lược |
| **T2 — tay** | **Codex / OpenCodex Sub-agents** (`spawn_agent`) | Thi công agent-tasks theo spec trên `feat/NNN-<slug>`. **Sol** (high): Auth/DDL/Crypto/bug khó · **Terra** (medium): CRUD/UI/wiring · **Luna** (low/medium): sửa vặt/lint/test-loop · **PAYG**: `gemini-3.6-flash` hoặc `deepseek-v4-flash-latest` qua OpenRouter |
| **T3 — máy chạy test & phản biện** | **OpenCodex Sub-agents** (`spawn_agent`) | **Phản biện 6 trục (§7.3i) & CHẠY TEST** (Playwright e2e/unit/smoke). **Gemini 3.6 Flash**: test runner chính & phản biện nhanh · **Gemini 3.1 Pro (high)**: soát lỗi chuyên sâu · **OpenRouter**: DeepSeek V4 Pro / Flash (bản trả phí) |

**Flow một agent-task (code):** T1 viết spec → T2 thi công trên `feat/NNN-<slug>`, tự chạy test + pre-commit → PR nhỏ vào `develop` → T1 review diff theo 3 câu (*đúng spec? đúng brief? có tự phát minh kiến trúc không?*) → chính chủ merge. **Escalation:** T2 bí >2 vòng hoặc muốn làm khác điều đã ✅ CHỐT → dừng, ghi nhận, đẩy lên T1. `docs/` là luật — chỉ chính chủ + T1 sửa nội dung quyết định.

**Ranh giới dữ liệu cho tool bên thứ ba (3 luật — suy từ threat model §1):**
1. **Code + docs = public** (repo vốn public) → tier nào chạm cũng được, kể cả tool Trung Quốc nếu sau này dùng.
2. **`.env` / secret / token** → không tier nào cả — agent code bằng `.env.example`; giá trị thật chỉ chính chủ đặt tay vào `.env` local / Fly secrets.
3. **Data thật** (Postgres cũ `microschedule_v2`, cutover migration, export cá nhân) → chỉ tool local do chính chủ giám sát với model T1. Code vốn công khai — *data* mới là tài sản của threat model này.

**Vì sao Codex, và đã loại gì (tra 2026-07-20):** cùng mốc \$20 không có lựa chọn mạnh hơn cho long-horizon infra — Codex dẫn Terminal-Bench 2.1 (~83% vs ~79% Claude Code/Opus 4.8), và 07/2026 OpenAI **bỏ cap 5h chỉ còn cap tuần** → hợp kiểu làm burst cuối tuần. Phase B toàn việc "sai âm thầm thành nợ" (Alembic/Docker/auth) — không phải chỗ tiết kiệm \$8 để nhận model bậc dưới. Đã loại: **gói Trung không còn rẻ như 2025** — GLM Lite \$12.6–18/mo (promo \$3 đã chết 02/2026; quota multiplier 3× giờ cao điểm trên GLM-5.x — *trùng giờ làm việc VN*), MiniMax entry nay \$20, Kimi ~\$28 quy đổi, Qwen \$50 (free tier đóng 04/2026) → **GLM Lite = phương án ngân sách dự phòng** khi việc còn lại là bulk (re-check 10/2026); **Cursor \$20** — IDE, sai hình dạng workflow spec→CLI-agent; **Copilot Pro \$10** — \$15 credits không đủ workhorse (để dành cho auto-review, §4); **DeepSeek V4** (ra 07/2026) — API pay-per-token siêu rẻ (\$0.14–0.435/M input), ghi sổ làm **van xả bulk**, chưa mua; **Grok Build** (ra 08/07) — quá mới; **Antigravity** (free trong gói Google sẵn) — không làm T2 vì kinh nghiệm chính chủ với hệ Google agentic, giữ làm fallback \$0. Lưu ý đọc benchmark: Terminal-Bench đo "tay" (agentic execution) — không đo "óc giữ luật dự án"; context/ritual/briefs sống ở hệ Claude → **mua Codex không đổi vai T1**.

**Bổ sung 2026-07-20 (cuối phiên — 2 câu hỏi muộn của chính chủ):**
1. **Codex vs Claude Code về memory:** ChatGPT Plus **không cắm được** vào Claude Code (OpenAI không mở endpoint Anthropic-compatible; các shim cộng đồng = mong manh/xám ToS, không dùng). Nhưng nỗi lo "Codex thiếu memory" hóa ra ngược: Codex CLI 2026 có `AGENTS.md` (tương đương CLAUDE.md, ~32KiB) **+ memory tự động cross-session** (lifecycle create/consolidate/clean, sanitize secret, compaction 2 tầng). Quan trọng hơn: memory thật của dự án này **nằm trong repo by design** (CLAUDE.md + briefs + specs tự-chứa) — executor nào cũng đọc được; auto-memory của hệ Claude là của T1, T1 giữ. → đã thêm **`AGENTS.md`** ở gốc repo làm cầu nối.
2. **Lane PAYG "tháng nhẹ" (T2b — mở rộng mục van xả):** tháng thuần-học ít code thì **skip sub Codex tháng đó**, chạy PAYG: ví token duy nhất = **OpenRouter** (trùng luôn kiến trúc app — `architecture-brief.md` §8 đã chốt OpenRouter cascade cho Bước 1, nên học nó là học luôn phần sẽ code); mẹo: **nạp \$10 một lần (không hết hạn) → free-models từ 50 lên 1.000 req/ngày vĩnh viễn**; phí topup 5.5% (+min \$0.80) → nạp cục \$10+, đừng nạp lắt nhắt. Harness cho lane này: **OpenCode** (mở, cắm mọi provider) hoặc **Claude Code + endpoint Anthropic-compatible** (DeepSeek V4 / GLM / Kimi / MiniMax đều có hướng dẫn chính chủ — xem repo tổng hợp `Alorse/cc-compatible-models`; tính năng harness như CLAUDE.md/skills là **local, đi theo harness không theo model**; unofficial — chấp nhận cho lane phụ, không cho T1). Chi phí thật với model rẻ (DeepSeek V4 \$0.14–0.435/M input + cache): **~\$2–5/tháng**. Không rải tiền nhiều ví (NanoGPT/Chutes/reseller "giảm 50–70%" = thêm rủi ro nguồn/uptime — cùng triết lý chống split-brain); LiteLLM/Portkey = đồ production team, thừa. ⚠️ PAYG **frontier** cho agentic dài vẫn đắt hơn sub (vì thế sub tồn tại) — lane này sống bằng model rẻ.
3. **Credit đang om (kiểm kê + expiry):** OpenAI \$5 + **daily-free theo data-sharing còn chạy 2026** (~1M tokens/ngày model lớn + 2.5M/ngày mini ở tier thấp; reset hằng ngày = **use-it-or-lose-it, om là phí**; điều kiện = prompt được dùng để train → **chỉ việc public-context**, khớp sẵn R3) · 2× Google acc thường: Gemini API free tier **per-project** (~04/2026 siết: Pro bị rút khỏi free, Flash còn ~1.500 req/ngày) — ⚠️ **bẫy: bật billing trên project là MẤT free tier của project đó** → acc có 300K VND credit phải tách project riêng, 2 acc free giữ nguyên không-billing · **việc đầu tiên: check ngày hết hạn từng credit.** Earmark: eval/embedding/cascade-dev của Bước 1 + judge second-opinion — không đụng private data.

Chi phí cả stack + bảng giá đối chiếu: `cost-brief.md` §6. Nguồn chính: [Codex với gói ChatGPT](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan) · [bỏ cap 5h 07/2026](https://explainx.ai/blog/chatgpt-codex-5-hour-limit-removed-weekly-reset-july-2026) · [Terminal-Bench ranking](https://www.morphllm.com/ai-coding-agent) · [giá GLM](https://www.aipricing.guru/z-ai-subscription-pricing/) · [MiniMax pricing docs](https://platform.minimax.io/docs/guides/pricing-token-plan) · [Qwen đóng free tier](https://inventivehq.com/blog/qwen-code-still-free-2026-shutdown) · [DeepSeek V4](https://www.tldl.io/resources/deepseek-api-pricing) · [Gemini CLI bị cắt (The Register)](https://www.theregister.com/ai-ml/2026/05/20/bye-bye-gemini-cli-google-nudges-devs-toward-antigravity/5243605)

---

### 7.1 📝 2026-07-21 — RETIRED receipt: ba lỗi chỉ trình duyệt mới thấy

Ngày thi công 007 đẻ ra ba lỗi mà **không** công cụ nào của T1/T2 bắt được — kể cả security-review Opus MAX chạy riêng trên diff (nó soi *code*, ba lỗi này không nằm trong code):

| Lỗi | Vì sao code-review + pytest mù |
|---|---|
| Thiếu `httpx` ở production | pytest chạy **với** nhóm `dev`, nơi httpx sẵn có cho TestClient → nhóm dev **che** một dependency production bị thiếu. Viết thêm bao nhiêu test cũng không lộ ra. |
| Service worker nuốt `/auth/*` | chỉ tồn tại ở **bản build PWA thật**; dev server không đăng ký SW, pytest không có trình duyệt |
| `?code=...` nằm lại trên URL ở nhánh bị từ chối | chỉ thấy khi **nhìn thanh địa chỉ**, và chỉ ở đúng nhánh từ chối — nhánh hợp lệ redirect đi nên sạch |

Cái thứ ba do **chính chủ** phát hiện, bằng một thao tác mà không agent nào làm: **đối chiếu URL giữa nhánh hợp lệ và nhánh bị từ chối**, rồi hỏi vì sao khác nhau.

⇒ Vai **T3** (chạy test + MCP Chrome-DevTools/Playwright, `§7`) **không phải phần rườm rà của quy trình** — nó là tầng duy nhất nhìn được lớp lỗi này. Kỷ luật rút ra:

- **`flyctl deploy` + mở trình duyệt thật là MỘT BƯỚC NGHIỆM THU RIÊNG**, không phải thủ tục hành chính sau khi "đã test xong".
- Task nào đụng tới **bản build production** (Docker, PWA/service worker, cookie, redirect, OAuth) thì mục Acceptance **bắt buộc** có bước nhìn bằng mắt trên bản deploy thật — ghi rõ *nhìn cái gì*, không ghi "kiểm tra hoạt động".
- Xanh CI ≠ chạy được. Ba lỗi trên đều xảy ra khi CI xanh 100%.

### 7.2 ✅ ĐÓNG 2026-07-22 — RETIRED receipt: agent lái Chrome profile thật của chủ

Kiểm chứng thật bằng Codex: **chạy tốt**, chuyển được giữa nhiều profile, đi trọn luồng OAuth trên `microsched.fly.dev` (tài khoản trong allowlist vào được; tài khoản ngoài allowlist bị chặn đúng, sang `/auth/denied`), và **không** chạm trực tiếp cookie/mật khẩu/profile store.

⇒ **Hệ quả cho việc phân vai: trục "ai lái được trình duyệt" không còn trùng với trục tier.** §7.1 rút ra luật *"việc cần trình duyệt thì giao cho thứ lái được trình duyệt, bất kể tier"* trong bối cảnh chỉ T3 làm được. Nay T2 cũng làm được ⇒ **task browser không còn phải cắt đôi giữa hai tầng** — người viết code và người nhìn nó chạy có thể là một, đúng thứ [[feedback-verification-loop-over-model]] gọi là vòng lặp kiểm chứng. T3 vẫn giữ vai chạy test diện rộng.

⚠️ **Nhưng ranh giới dữ liệu siết lại, không nới ra.** Profile đó **không phải môi trường test** — nó là máy của chủ, đang đăng nhập sẵn mọi thứ. Luật đầy đủ ghi ở **`AGENTS.md`** mục *"Lái trình duyệt"* (chỉ dùng tài khoản được nêu tên; không rời phạm vi app; không đọc cookie/history/autofill; soi ảnh chụp trước khi dán; không đổi setting). Hai điểm đáng nhắc lại ở đây vì chúng thuộc threat model §1 chứ không thuộc kỹ thuật:

- **Có một tài khoản chính chủ cấm đụng.** Tên tài khoản **không ghi vào repo** — chỉ nêu trong prompt giao việc.
- **Không dán địa chỉ email thật vào PR/commit/docs.** Repo public + threat model = social engineering ⇒ danh sách tài khoản là vật liệu dựng pretext. Viết theo vai (*"tài khoản trong allowlist"*), không viết địa chỉ.

### 7.3 ✅ CHỐT 2026-07-22 — RETIRED receipt: Claude điều phối Codex trực tiếp

Bối cảnh: sau 003→008b, chính chủ đã đủ tin để bỏ khâu **copy prompt/báo cáo qua lại giữa hai harness**. Chính chủ nói rõ đây là đánh đổi có ý thức: *"chọn thêm risk 40% để đổi lấy hiệu suất, rồi tiến tới nâng cấp harness eng để giảm risk xuống như thủ công mà vẫn giữ hiệu suất."*

**Rủi ro thật không phải một khối — tách ra thì chỉ một thứ đáng sợ.** Chuyển tay đang giữ ba thứ: ⓐ chủ đọc spec trước khi Codex chạy (nhỏ — spec do T1 viết, duyệt sau được), ⓑ **chủ đọc báo cáo Codex trước khi Claude tin nó** 🔴, ⓒ nhịp nghỉ để chủ nghĩ. Chỉ ⓑ là rủi ro thật, vì đã đo được: task 004 executor **khai sai về chính việc nó vừa làm** ("chưa có dependency" trong khi lockfile 263KB nằm trên đĩa). Bỏ chủ ra khỏi vòng mà không thay gì vào ⇒ Claude tin lời khai ⇒ lỗi lan sang bước sau. **Cách vá đã có sẵn trong dự án: 008b không kiểm `status: ok` mà kiểm git SHA đã deploy.** Cùng hình dạng ⇒ luật trục:

> **Luật biên lai — Claude KHÔNG BAO GIỜ nhận prose làm bằng chứng.** Task chỉ "xong" khi có **số PR + `gh pr checks` xanh + diff đọc được**. Ghi vào `AGENTS.md` để executor cũng biết.

### a) Công cụ: `openai/codex-plugin-cc` — ✅ dùng

Plugin chính chủ OpenAI (Apache-2.0, v1.0.6 ngày 08/07/2026). **Không** nhúng model OpenAI vào Claude Code — nó là **client**: bọc *Codex app server*, gọi **binary `codex` cài trên máy**, *"applies the same configuration"*. Lệnh: `/codex:review` · `/codex:adversarial-review` · `/codex:rescue` (giao task, có `--background/--wait/--resume/--model/--effort`) · `/codex:transfer` · `/codex:status` · `/codex:result` · `/codex:cancel`. `/codex:result` trả **session ID**, `codex resume <id>` mở tiếp trong Codex thật.

- **Điều kiện cài (kiểm thật trên máy chủ 2026-07-22):** Node v24.15.0 ✓ (cần ≥18.18). Nhưng **`codex` KHÔNG có trên PATH** — máy đang chạy Codex **desktop app**, CLI ẩn ở `…\AppData\Local\OpenAI\Codex\bin\<hash>\codex.exe` (codex-cli 0.145.0-alpha.27), **thư mục có hash nên đổi mỗi lần app update ⇒ không thêm vào PATH được**. Đường sạch: `npm install -g @openai/codex`; bản npm dùng chung `CODEX_HOME` ⇒ chung auth/config/memories. `auth.json` là **ChatGPT tokens, không có API key** ⇒ delegation ăn vào **cap tuần của Plus**, không sinh hoá đơn PAYG.
- **⛔ KHÔNG bật review gate** (`/codex:setup --enable-review-gate`). Chính README cảnh báo nó tạo vòng lặp Claude↔Codex dài và đốt limit nhanh; và nó đặt cổng **sai chỗ** — chặn *câu trả lời của Claude* thay vì chặn *diff*.
- **Cây làm việc:** plugin chạy Codex trong **cwd của Claude** (chưa có tài liệu nói khác — `01-codex-self-audit` mục 5 sẽ trả lời). ⇒ Luật tạm: **`--background` thì Claude không được chạm cây làm việc**; cần chạy song song thì dùng lane slot (mục e).

### b) Bộ nhớ: **không có cầu nối** — và Codex đã tốt hơn tưởng

Cái được dùng lại là **bề mặt UI của Claude Code** (slash command, subagent, hook), **không** phải óc/memory/`CLAUDE.md`/skill của Claude. Codex khi bị gọi chỉ đọc: `~/.codex/config.toml` + `~/.codex/memories/` + `AGENTS.md` trong repo + prompt Claude gửi.

**Kiểm thật `~/.codex/` ngày 22/07 — nỗi lo "Codex thiếu memory" (§7 note 1, 20/07) nay có bằng chứng đảo chiều:** `memories/MEMORY.md` 18KB + `raw_memories.md` 17KB + `memory_summary.md` 4,3KB + 4 `rollout_summaries/` (task 003/004/005/006), **và cả thư mục là một git repo**. Nó **tự** rút ra đúng những bài đã phải dạy tay: *"dán output thật vào PR, đừng tóm tắt"* · *timeout ≠ chưa làm gì* · giữ tên job CI · tiếng Việt qua file UTF-8 · dừng sau ~2 vòng bí · tách ba role DB Neon. Nó còn **tự viết một skill**: `~/.codex/memories/skills/microsched-verify-and-pr/SKILL.md`.

⇒ Chỗ Codex thua **không phải cơ chế mà là thứ được nhớ**: memory Codex toàn tri thức *thợ*; memory Claude có thêm tầng *cách làm việc với chủ*.

**✅ Luật ba kênh (chốt) — không copy file bộ nhớ qua lại:**

| Nội dung | Sống ở đâu | Vì sao |
|---|---|---|
| Luật riêng dự án microSched | `AGENTS.md` (trong git, review được) | đã chạy tốt từ 20/07 |
| Cách làm việc **xuyên dự án** với chủ | **`~/.codex/AGENTS.md`** | file này **đang rỗng** → đã viết 22/07 (báo cáo, timeout, ràng buộc-vận-hành, phạm vi/điểm dừng, bẫy PowerShell, cách nói ở tầng của chủ) |
| Tri thức thao tác lặt vặt | auto-memory mỗi bên | để cơ chế tự chạy |

Ba lý do **không** đổ `~/.claude/.../memory/*.md` vào `~/.codex/memories/`: ① nhân bản sự thật = split-brain, đúng anti-pattern `CLAUDE.md` mở đầu bằng nó; ② thư mục đó là *generated state*, có lifecycle consolidate sẽ **nuốt mất** thứ đặt tay vào; ③ local-only, ngoài git, chủ không review/diff được. Docs OpenAI nói cùng điều: *"Keep required team guidance in `AGENTS.md`… Treat memories as a helpful recall layer, not as the only source for rules that must always apply."*

**⚠️ CHƯA KIỂM (2 mục, có task để trả lời):** ① docs Memories chỉ mô tả phiên **interactive**, **không nói gì** về phiên app-server ⇒ chưa biết đường plugin có được inject memories không. ② config có `memories.disable_on_external_context = true` ⇒ phiên chạm MCP/web-search **không sinh memory mới**. → `agent-tasks/harness-audit/01-codex-self-audit.md`, chạy **hai lần (Codex app / qua plugin) rồi lấy hiệu số** — một lần chạy chỉ cho một bức ảnh; hai lần cho một phép trừ.

### c) ✅ Thang triage **L1/L2/L3** — Claude tự quyết cái gì tới tay chủ

Yêu cầu của chính chủ: *"Claude không được hỏi mình mọi lúc, đã đến lúc harness eng lên tầng cao hơn."* **Trục phân loại = blast radius + khả năng đảo ngược**, không phải "quan trọng" (không quyết được) và không phải "khó" (nhầm trục).

| Mức | Nội dung | Ai quyết | Chủ nghe thế nào |
|---|---|---|---|
| **L1** | đụng điều đã ✅ CHỐT trong `docs/` · auth/session/crypto/private gate · schema/migration/DDL · **chạm hạn mức tiền hay quota** · hành vi deploy/CD · hai brief mâu thuẫn · khó đảo ngược | **chủ** — dừng luồng | chi tiết: *hỏng chuyện gì của bạn* → cơ chế → **số đo thật** → hai lựa chọn + khuyến nghị |
| **L2** | convention **sẽ bị copy về sau** (tên route, hình dạng error response, phân trang, tên miền nghiệp vụ) · thêm dependency · đánh đổi trong một slice | **Claude**, ghi lại | 3–5 dòng **+ một dòng trong PR description** |
| **L3** | test đỏ/lint/type/wiring/typo · retry sau timeout · câu hỏi spec/brief **đã trả lời sẵn** | **Claude**, im lặng | không báo |

**Bốn luật giữ thang không trôi:** ① không chắc mức nào ⇒ **mặc định L1**; ② quyết L2 **ba lần cùng một vùng** ⇒ đó thật ra là L1 (brief thiếu một quyết định), đẩy lên; ③ Claude **không tự nâng gì lên "đã chốt"** trong `docs/` — L2 là *tạm*; ④ **mọi L2 phải hiện trong PR description** — đây là thứ khiến thang không phải là giấu việc: **không quyết định nào biến mất, chỉ đổi chỗ chủ đọc nó**, từ chat sang mô tả PR, đúng lúc chủ cầm nút merge.

**Ngoại lệ 008 (task đặt khuôn): L2 → L1.** Trên task đặt convention cho cả dự án, một quyết định convention *có* blast radius toàn dự án theo đúng định nghĩa — §8 gọi lớp lỗi này là *"xung đột ngữ nghĩa, nguy hơn conflict git vì git không báo gì"*. Áp dụng nhất quán luật blast-radius, không phải biệt lệ. Hết 008, L2 về mức thường.

**Hiệu chuẩn bắt buộc ở lần chạy đầu:** sau khi task merge, Claude **liệt kê mọi mục đã tự xử ở L3 và mọi L2 đã tự quyết**; chủ đọc một lần, khoanh cái nào lẽ ra phải leo mức. ~10 phút, và nó biến "Claude tự quyết" từ niềm tin thành **số đo**.

**Rủi ro mới thang KHÔNG chữa:** Claude-điều-phối là **điểm hỏng mới** — hiện Claude hiểu sai một spec thì hỏng một task và chủ thấy ngay; khi điều phối, cách hiểu sai đó **nhân bản vào N luồng**. Luật biên lai vẫn bắt ở cửa merge, nhưng **sau khi đã phí N lần công** ⇒ không mở nhiều luồng trên slice mà thiết kế chưa yên.

**⚠️ Cơ chế "Codex hỏi ngược Claude" là theo LƯỢT, không phải hội thoại.** Job nền không có kênh ngược sống: Codex gặp chỗ mơ hồ thì **dừng**, câu hỏi nằm trong `/codex:result`, Claude phải **chủ động poll** rồi đáp bằng `--resume`. ⇒ Hỏi là **đắt** ⇒ spec phải **liệt kê sẵn cái gì đã được quyết**, Codex chỉ được dừng cho thứ ngoài danh sách. Cái giá của kiến trúc này rơi đúng vào chỗ nên rơi: **spec tốt hơn**.

### d) ✅ Lộ trình bốn pha

| Pha | Nội dung | Mốc |
|---|---|---|
| **0** | cài `codex` global + plugin (**không** review gate) → chạy `harness-audit/01` hai lần A/B → chạy `02` | trước 008 |
| **1** | **chỉ review, chưa giao việc**: mỗi diff trước merge chạy `/codex:adversarial-review` **+** `/security-review` của Claude Code — **hai engine khác nhà**, độc lập thật. Đây cũng là phương án rẻ nhất cho §4 (auto-review PR, DEFER từ 19/07) và **không trao thêm quyền cho ai** | 008a + 008 |
| **2** | giao việc thật qua `/codex:rescue` **một luồng** + bật thang. **008 là lần chạy đầu** — mẫu hiệu chuẩn tốt hơn 009 vì task đặt khuôn đẻ nhiều tình huống L2. Executor 008 = **T2 Codex Sol/high** (không phải T1: §7 giao T1 code chỉ với security-critical; 008 là CRUD slice) | 008 |
| **3** | mở luồng thứ hai + thử Jules/Antigravity | 009–010 |

⚠️ Hai review pass ở pha 1 **không** thay bước nhìn bằng mắt: §7.1 đã đo — security-review Opus MAX soi *code* rất tốt nhưng **mù cả ba lỗi 007** vì chúng không nằm trong code.

### e) ✅ Neon ra khỏi vòng lặp dev — **lane slot**

Đề xuất của chính chủ: dev + test chạy **local hoàn toàn**. Đúng, và nó giải nhiều hơn một vấn đề — xem note 2026-07-22 ở cuối §8.

- ⛔ **Postgres phải trong Docker, KHÔNG dùng instance Postgres của máy.** `CLAUDE.md` hard boundary: instance đó chứa `microschedule_v2` — **nguồn migration thật, chủ vẫn sửa hằng ngày** — và superuser `postgres` đang phục vụ nhiều dự án khác. Công thức có sẵn: CI job `Migration QA` đã chạy **PG18 + pgvector**, chỉ việc nâng thành `docker-compose` dev.
- ✗ **Bỏ nhánh "app trên Fly + Postgres local"**: máy Fly không với tới Postgres trên máy chủ (không địa chỉ public, phải dựng tunnel).
- Neon còn phục vụ đúng ba việc: **CI Migration QA · app trên Fly · nghiệm thu cuối**.

**Lane slot — một "luồng" là một bó cấu hình CỐ ĐỊNH, khai báo một lần dùng mãi.** (Đừng tạo worktree theo từng branch: path mới mỗi task ⇒ phải thêm `trust_level` mỗi task ⇒ sẽ quên.)

| | lane1 | lane2 |
|---|---|---|
| worktree | `…\microsched-wt\lane1` | `…\microsched-wt\lane2` |
| cổng app | 8001 | 8002 |
| Postgres (Docker) | 5433 | 5434 |
| OAuth redirect URI | `http://localhost:8001/auth/callback` | `…:8002/…` |
| `trust_level` trong `~/.codex/config.toml` | thêm **một lần** | thêm **một lần** |

Task mới chỉ `git -C lane1 switch -c feat/NNN-slug` — path không bao giờ đổi.

**⏳ Việc của chủ (đụng cấu hình OAuth app ⇒ L1):** Google Cloud Console → Credentials → OAuth client của microSched → *Authorized redirect URIs* → thêm `:8001` và `:8002`, **không xoá** `:8000` và `https://microsched.fly.dev/auth/callback`. **Không cần sửa code** — đã tra: `auth.py` dựng redirect URI từ chính request đến (`request.url_for("auth_callback")`, ép https trừ loopback), có test khoá hành vi ở `test_auth.py`.

**📌 Đề xuất chưa làm — cổng máy cho chuỗi Alembic:** thêm vào job `Migration QA` một bước bắt `alembic heads` trả **đúng 1 dòng**, >1 thì đỏ. Quy ước "một luồng sở hữu chuỗi migration" là **không đủ** vì git im lặng khi có hai head; đây đúng loại *test cho hành vi vắng mặt* mà sự cố Neon dạy.

### f) 📋 Jules + Antigravity — ghi sổ, **thử ở 008/009** (chủ dặn nhắc lại)

Thang L1/L2/L3 **mở lại được cánh cửa §8 từng đóng**, vì §8 bác song song do nút cổ chai là băng thông review của chủ — mà thang tấn công thẳng nút đó. Nhưng hai thứ này **khác hình dạng, đừng gộp**:

- **Jules** (Google AI Pro sẵn có: **100 task/ngày, 15 concurrent, Gemini 3 Pro**) — cloud VM + clone repo + PR, gán label `jules` vào issue là chạy ⇒ **tự động hoá được**, cắm vào pipeline được.
- **Antigravity / `gemini-3.6-flash-tiered`** (xuất hiện trong model selector **21/07/2026**) — **chưa GA, không API công khai, không Vertex** ⇒ chỉ là **ghế thủ công** trong IDE của nó, **không thể là một chặng pipeline**. Hợp vai T3 (chạy test + report), không hợp vòng lặp tự động.

> **📝 2026-07-24 — ĐẢO nửa dòng Antigravity ngay trên: giờ nó *là* một kênh giao việc lập trình được.** Antigravity đã có **CLI `agy`** + MCP wrapper **`agy-bridge`** (cài `-s user`, `claude mcp add-json`) ⇒ T1 đẩy việc thẳng cho Gemini **không cần ghế thủ công trong IDE nữa**. Đây là lớp **de-manualize kênh T1→T3**, song song `codex-plugin-cc` (T1→T2) — **KHÔNG** đổi luật 3 tầng (T3 vẫn bị điều hướng), chỉ đổi *ai bấm nút giao*. **Hai lane chốt (bắt đầu HẸP):** ① phản biện khác-họ (`adversarial_review`, thêm góc nhìn ngoài T2); ② tìm fact/đọc nhiều file (`analyze_files`/`deep_search`/`web_lookup`, tiết kiệm context T1). Không code, không quyết định, không chạm secret. **Đo tận tay (biên lai):** server nối, 6 tool; auto-routing **rơi về "agy default"** (`no preferred model available`) ⇒ **phải truyền `model:` tên thật từ `agy models`** — fact-finding + phản biện thường `gemini-3.6-flash-high` (bắt đủ 2 lỗ critical gài sẵn, 0 bịa, trích đúng dòng), review vét cạn `gemini-3.1-pro-high`; **đừng** chọn `claude-*` của agy cho adversarial (mất tác dụng khác-họ). Kết quả agy là **cố vấn**, không phải biên lai code. Chi tiết vận hành + tên model cứng: `CLAUDE.md §"Delegation qua agy-bridge"` + memory `agy-model-capabilities`.
>
> **Quota Google AI Pro (2 account) ưu tiên cho agy, KHÔNG dồn vào Jules.** Cập nhật §7.f dưới đây (kế hoạch "thử Jules 5 task ở 008/009"): chủ phán 24/07 **Jules hiện quá phế** — một workflow tự do đốt lượng quota khổng lồ *và* vẫn phải lọc PR của nó (bất đối xứng chi phí lọc ở dòng dưới) = lỗ ròng. Thà để cùng 2 account đó nuôi **agy (hỗ trợ T1) + tầng test T3** hơn là ném vào Jules. **Lane Jules: hoãn**, không đóng vĩnh viễn — mở lại khi có lý do đo được, không phải theo lịch 008/009.

**⚠️ Bất đối xứng chi phí lọc:** lọc PR của Codex-do-Claude-brief thì **rẻ** (Claude có sẵn mô hình "đáng lẽ thế nào"); lọc PR Jules chạy tự do thì **đắt** — phải dựng lại ý định từ diff, gần bằng tự viết. Một bộ lọc chỉ tiết kiệm băng thông khi nó **từ chối được rẻ**.

⇒ **Mở bằng số, không bằng niềm tin:** thử **5 task** loại *"đúng/sai do CI quyết"* (viết test theo danh sách T1 đã đặc tả — bulk, phán đoán thấp, blast radius ≈ 0). Đo **tỉ lệ PR được nhận** + **thời gian Claude tốn mỗi PR để lọc**. Nhận <50% hoặc lọc tốn gần bằng tự viết ⇒ **đóng lane**. Chuỗi lọc mong muốn về sau `T2 → T1 → chủ`; **lần đầu chạy thẳng `Claude → chủ`** cho chắc, thêm tầng sau khi có lòng tin.

> **📝 2026-07-31 — sửa danh tính + lịch Jules, chủ xác nhận trực tiếp.** PR/commit gắn nhãn *"⚡ Bolt: …"* và *"🛡️ Sentinel: …"* (vd #55, #56) **chính là hai tác vụ định kỳ của Jules** nói ở trên — "Bolt" = tác vụ performance, "Sentinel" = tác vụ security; không phải bot/dịch vụ ngoài nào khác. Vẫn đúng T3/Gemini 3.1 Pro trên nền Jules, không đổi vai trong thang 3 tầng. **Lịch đúng (đè lịch sai ghi ở note 29/07 phía trên — nightly 23h cho security là SAI):** **cả hai tác vụ chạy hàng tuần, Chủ Nhật 23:30**, tới **2026-09-30** (không phải 2026-08-15 như ghi nhầm trước đó). PR của hai tác vụ này **vẫn cần soát định kỳ và xử lý** như PR Jules thường — không tự động merge theo đề xuất của nó, theo đúng luật cố-vấn-không-phải-biên-lai đã chốt 29/07.

### g) Nơi để việc + báo cáo

- **`agent-tasks/harness-audit/`** — spec đối soát harness, đánh số riêng `01`/`02` (không thuộc hàng đợi 001–012).
- **`harness-reports/`** — output. `.gitignore` giữ `README.md` trong git, **chặn nội dung**: repo public + threat model social engineering, mà báo cáo mô tả thói quen làm việc và bộ nhớ cá nhân — **không phải secret nên gitleaks không chặn**, dòng `.gitignore` là cơ chế duy nhất. Kiểm chứng bằng `git add -n`: chỉ `README.md` vào được index.
- **Vòng đời:** `harness-reports/` là **chỗ tạm ứng, không phải kho** — phát hiện nhập vào `AGENTS.md`/`~/.codex/AGENTS.md`/`docs/` xong thì dọn. Mục tiêu là **giảm** số nơi chứa sự thật.

*Nguồn (tra live 2026-07-22):* [codex-plugin-cc](https://github.com/openai/codex-plugin-cc) · [Codex Memories (OpenAI)](https://learn.chatgpt.com/docs/customization/memories) · [Neon free plan limits](https://neon.com/faqs/free-plan-limits-and-quotas) · [Jules pricing 2026](https://hackup.ai/ai-plans/jules/) · [Gemini 3.6 Flash in Antigravity](https://antigravity.google/blog/gemini-3-6-flash-in-google-antigravity)

### h) 📝 2026-07-27 — quota T1 là nút cổ chai mới; Codex được cấp full-access git/Docker; chính sách model/effort theo loại việc

**Bối cảnh:** dù đã áp đúng harness (T1 không thi công, mọi CRUD đi T2/T3), riêng phần **"điều phối + check"** còn lại của T1 vẫn ăn **~25%/ngày quota Opus/high**, 3 ngày chạm 91% quota tuần. Chẩn đoán, không suy đoán:

1. **Trên gói Pro, Opus và Sonnet dùng CHUNG một pool token**, và Opus tốn **3–5× token** của Sonnet cho cùng việc. Effort (`low/medium/high`) là **trục độc lập** nhân thêm lên trên. Dùng Opus+high cho **mọi** việc — kể cả việc lặt vặt — là tổ hợp đốt quota nhanh nhất.
2. **Phần "check" tốn nhất không phải judgment mà là cơ học:** vì Codex qua đường plugin bị sandbox chặn Docker/`.git` (xem mục b dưới), T1 phải **tự chạy lại toàn bộ verification bằng tay** (ruff, pytest, build) — cơ học × context dài (~1300 dòng `CLAUDE.md` + hàng chục memory) × effort cao = đốt quota dù không có gì sai.
3. Benchmark thật (07/2026): trên **Terminal-Bench 2.1** — đúng sân của T2 — **Sol dẫn 88.8% vs Sonnet 5 chỉ 80.4%**. Nghĩa là *"T1 phải mạnh hơn T2 mới quản được T2"* không đứng vững từ số đo — giá trị của vai quản lý đến từ **spec rõ + test độc lập + hai reviewer khác họ** (cơ chế đã có), không phải từ chênh lệch IQ.

**a) ✅ Chính sách model/effort theo loại việc (mới, thay "Opus/high mặc định"):**

| Loại việc | Model/effort | Vì sao |
|---|---|---|
| Security-critical, ops không hoàn tác, hoà giải khi T2/T3 bất đồng, quyết định kiến trúc | **Opus/high** (giữ nguyên) | Ít khối lượng, đáng tiền — đúng chỗ frontier reasoning trả công |
| Điều phối/bookkeeping còn lại: đọc receipt, draft spec lần đầu, report đóng phiên, đọc doc | **Sonnet 5/medium** (mới) | Không phải judgment call; Sonnet không rõ ràng yếu hơn T2 trên đúng loại việc T2 làm (mục 3 trên) |

**b) ✅ Codex được cấp full-access cho git/Docker (chủ chốt 2026-07-27, tin tưởng năng lực gpt-5.6-sol/terra):**

Xác nhận lại kỹ thuật (đã ghi trong comment `~/.codex/config.toml` từ 25/07, nay đo khớp với docs Codex CLI công khai): sandbox Windows ở `workspace-write` đóng **`Deny Write` ACE** lên `.git` bất kể `writable_roots` (Deny luôn thắng Allow trên Windows); Docker bị chặn vì lý do khác (quyền daemon/named-pipe dưới restricted-token). `danger-full-access` gỡ **toàn bộ** sandbox (file + network) — OpenAI gọi là elevated-risk.

**Điểm mới quan trọng:** `-s danger-full-access` và `--dangerously-bypass-approvals-and-sandbox` (kiểm bằng `codex exec --help`) là **cờ theo TỪNG LỆNH `codex exec`**, không phải config bền — khác hẳn kiểu "full-access có giám sát, hạn cứng 45 phút, tự thu hồi" đã dùng cho Agent-Opus (đó là trạng thái phiên/worktree phải nhớ đóng). Ở đây **không có gì để quên tắt** — hết lệnh là hết quyền. T1 chỉ cần gắn cờ đúng lệnh cần git/Docker, lệnh chỉ sửa code vẫn giữ `workspace-write` mặc định.

⚠️ **Chưa kiểm (cần probe ~30s trước khi giao việc thật):** vì Codex được T1 gọi **không tương tác** (không ai ngồi trả lời approval), `-s danger-full-access` một mình có thể treo chờ approval không bao giờ tới nếu `approval_policy` chưa phải `never`. `--dangerously-bypass-approvals-and-sandbox` (docs: *"intended solely for environments that are externally sandboxed"*) nhiều khả năng mới đúng cho kịch bản này. **Việc đầu phiên sau: chạy probe rẻ xác nhận cờ nào dùng được cho lệnh git/merge thật, theo đúng thói quen "đổi config Codex thì probe trước khi giao việc lớn" (25/07).**

**c) ✅ Luồng merge/DevOps thiết kế lại — KHÔNG bỏ bước review:**

Bản đầu đề xuất `gh pr merge --auto` (tự merge khi CI xanh) bị bác — nó bỏ qua đúng bước **T3/T2 review đã nhiều lần bắt bug thật** (008i, 008k, spec 008h... — xem các note 📝 26/07 ở `CLAUDE.md`). Luồng đúng:

1. T2 mở PR (workspace-write, như cũ).
2. T3/T2 review theo thang criticality đã có (`pr-merge-gate-by-criticality`) — **giữ nguyên, không cắt**.
3. Có vấn đề → Codex tự sửa theo feedback (workspace-write, đã chạy được, **không cần** full-access).
4. Review đạt → **Codex, full-access CHỈ cho lệnh này, tự `git push` + `gh pr merge`** — không phải `gh pr merge --auto` mù, không cần T1 bấm tay.
5. DevOps/DevSecOps thi hành (migration, gitleaks, lane PG cần Docker) → Codex full-access khi cần; T1 chỉ đọc receipt, không rerun.

**T1 còn lại sau redesign:** viết spec, đọc receipt, xử lý bất đồng/escalation, và phần thật sự critical (L1). Khối lượng cơ học gây bottleneck (mục 2) chuyển hết sang T2.

*Nguồn tra 2026-07-27:* [Claude usage limits 2026](https://www.explainx.ai/blog/claude-usage-limits-2026-timeline-explained) · [Claude Max plan pricing](https://intuitionlabs.ai/articles/claude-max-plan-pricing-usage-limits) · [Codex sandbox & approvals](https://developers.openai.com/codex/agent-approvals-security) · [Sonnet 5 vs GPT-5.6 Sol benchmarks](https://benchlm.ai/compare/claude-sonnet-5-vs-gpt-5-6-sol) · [Pull Request Automation Workflow](https://developertoolkit.ai/en/codex/lessons/pr-automation/)

### i) ✅ CHỐT 2026-07-29 — hai hạng phản biện spec + rubric hợp nhất (thay "T3 hỏi X, T2 hỏi Y")

**Vì sao đổi:** quy ước 26/07 ("T3 hỏi *spec sai ở đâu*, T2 hỏi *spec không làm được ở đâu*") tách hai
câu hỏi thành hai lượt tách biệt, và trong thực hành đã sinh ra đúng lỗ nó không lường tới: `018`
(harness Playwright + CI job mới + đặt khuôn cho 009–012) chỉ chạy lượt T3 rồi **suýt** merge — tự cho
phép hoãn lượt T2 vì hai câu hỏi bị coi là hai việc độc lập, tách được. Sai: hai câu hỏi đó chỉ là
**tập con** của một rubric đầy đủ, và một việc đặt-khuôn cần cả hai bộ mắt **trước khi merge**, không
phải trước khi giao thi công rồi thôi.

**Hai hạng — trục khác với L1/L2/L3.** L1/L2/L3 (`c` phía trên, [[harness-triage-ladder]]) trả lời
*"chủ có cần biết không"*; hạng dưới đây trả lời *"cần mấy bộ mắt trước khi giao thi công thật"*. Hai
trục compose được, không thay thế nhau.

| | Hạng đơn — chỉ T3 | Hạng đôi — cả T2 + T3 |
|---|---|---|
| Mặc định | ✅ | |
| Kích hoạt hạng đôi (≥1 mục) | | có migration · đụng auth/session/crypto/secret · **đặt khuôn** (slice/harness đầu tiên mà việc sau chép) · thêm **hạ tầng mới** (CI job, dependency, cấu hình runtime) · giả định về **môi trường thực thi** mà chỉ executor thật mới biết đúng/sai |
| Ví dụ | `008g` (đổi cột, theo khuôn có sẵn) | `008`, `013` (CI mới), `018` (CI job mới + harness Playwright mà 009–012 chép + đụng 3 hành vi đã chốt) |

**Rubric hợp nhất — cả hai engine dùng chung, không tách câu hỏi.** Mọi lượt `adversarial_review`,
bất kể giao T2 hay T3, chạy đủ sáu trục:

1. **Đúng theo decision record** — khớp `docs/*.md` phần ✅ CHỐT không, có mâu thuẫn nào không.
2. **Đúng theo code thật** — bắt buộc đọc file nguồn thật trước khi phán, không suy từ text spec.
   *(Dòng lệnh quan trọng nhất trong prompt — thiếu nó là suy luận từ mô tả, không phải phản biện.)*
3. **Khả thi khi thi công** — bước cụ thể có chạy được không, đúng ràng buộc môi trường (sandbox,
   phiên bản tool, tên CI job, thứ tự migration). Trục này **T2 có lợi thế tự nhiên** vì nó chính là
   executor.
4. **Blast radius / khó hoàn tác** — có đụng thứ không quay lại được không; mục "KHÔNG được làm" đã
   đủ chưa.
5. **Tự mâu thuẫn** — cấm một chiều mà cho phép chiều kia (họ lỗi `note.title`, 23/07), hai quyết
   định đều đúng nhưng khoá nhau (họ lỗi lặp ≥7 lần trong dự án, [[feedback_gap_between_correct_decisions]]).
6. **Acceptance đo được** — tiêu chí có kiểm chứng được thật hay chỉ "làm cho tốt".

Mỗi finding bắt buộc: **severity** (CRITICAL/MAJOR/MINOR) + **file:line trích dẫn** + nhãn
**OBSERVED/INFERRED** ([[feedback-probe-by-difference]]). Không có trích dẫn ⇒ chưa phải finding, xếp
riêng, đừng trộn vào bảng.

**T2 và T3 khác nhau ở *cách trả lời* trục #3, không ở câu hỏi được hỏi:**
- **T3 (Gemini, không có quyền thực thi):** trả lời trục #3 bằng **suy luận** đọc code.
- **T2 (Codex, chính là executor):** nên trả lời trục #3 bằng **thử thật** khi rẻ — dựng server cục
  bộ + thử một mock, hoặc probe sandbox cho đúng thao tác nghi ngờ — thay vì chỉ đọc rồi suy luận.
  Áp đúng luật đã có: *"chạy thử rồi mới nói đáng tin hơn model mạnh suy luận rồi khẳng định"*
  ([[feedback_verification_loop_over_model]]). Một finding T2 kiểu "tôi thử chạy X, nó lỗi Y" nặng
  ký hơn "tôi đọc code, X có thể lỗi".

**Thứ tự cho hạng đôi:** giao **T3 trước** (rẻ, nhanh, không cần quyền ghi) → fold → giao **T2** với
đúng rubric sáu trục, nhắc ưu tiên thử thật ở trục #3 → fold → merge. Không đảo thứ tự để tiết kiệm
— T2 phản biện *sau khi* T3 đã fold thì review đúng bản spec sắp thi công, không phải bản nháp.

**Kết quả áp dụng đầu tiên (`018`, PR #52):** lượt T3 bắt 5/6 finding thật (fold), 1 bác. Xét lại theo
hạng ở trên: `018` là hạng đôi (khớp cả 3 tiêu chí) — lượt T2 chạy tiếp trước khi merge, không merge
chỉ với 1 lượt như quy ước cũ cho phép. Lượt T2 bắt thêm 2 finding thật (đếm sai job CI · một câu
trong `ui-brief.md` chưa đóng vòng với chính bản sửa 25/07 của nó) + 1 finding làm rõ chứ không sửa
code. Chi tiết đầy đủ ở §7 của `agent-tasks/018-qa-polish-playwright.md`.

🔒 **Bài học vận hành lộ ra ngay ở lượt áp dụng đầu tiên: `write: true` của lớp forwarder KHÔNG kèm
quyền mạng hay quyền spawn tiến trình native.** T2 chạy lượt trên không có `-s danger-full-access`
dù mục đích cả lượt là trả lời trục #3 (khả thi) **bằng thử thật** — `npm install` chết `ENOTCACHED`
(sandbox chặn mạng), `vite preview` chết `EPERM` (chặn spawn binary Tailwind). T2 tự báo đúng đây là
giới hạn môi trường chứ không suy diễn thành lỗi spec — nhưng hệ quả là trục #3 gần như rơi hết về
INFERRED, đúng thứ rubric này sinh ra để tránh. ⇒ **Giao T2 review hạng-đôi muốn trục #3 được trả lời
bằng thử thật thì phải tường minh xin `-s danger-full-access` trong prompt giao việc**, không mặc
định `write: true` là đủ. Đây cũng là mảnh còn thiếu của việc treo từ 27/07 (mục `h`, *"probe cờ nào
đúng cho lệnh không tương tác"*) — nay biết thêm: thiếu cờ thì lượt review không báo lỗi, chỉ lặng lẽ
rơi về suy luận.

**🔒 Phát hiện thêm (`018`, lượt T3 thứ hai — trên chính diff thi công, không phải spec):** một spec
đặt-khuôn đáng có thêm một lượt phản biện **sau khi code thật đã viết xong**, không chỉ trước khi giao
thi công — đặc biệt nếu quá trình thi công đi qua nhiều vòng vá dưới áp lực thời gian (nhiều bàn tay,
nhiều lần sửa nhanh). Bốn finding thật (2 CRITICAL) bị lọt qua cả hai lượt review-spec ban đầu vì
chúng chỉ tồn tại trong CODE, không tồn tại trong SPEC — không cách nào một lượt đọc spec bắt được.
⇒ **Với hạng-đôi: cân nhắc thêm một lượt phản biện trên diff thật (không phải spec) khi việc thi công
đã đi qua ≥2 vòng vá bởi nhiều bên** (T1 + T2 xen kẽ) — đây không phải tiêu chí cứng như bảng hạng ở
trên, mà là tín hiệu bổ sung: *quá trình thi công lộn xộn* cũng đáng một lượt soi thêm, không chỉ
*loại việc* mới đáng.

**📝 2026-07-31 — biên T1→T2 siết thêm một nấc, sau khi T1 hai lần tự sửa code thuộc phạm vi T2
trong cùng phiên (`018`).** Chi tiết đầy đủ + bằng chứng: [[harness-eng-operating-model]] (memory),
`CLAUDE.md` 📝 31/07. Tóm tắt: **phát hiện bug trong sản phẩm T2 KHÔNG tự động cho phép T1 sửa nó** —
mặc định là dừng, trình bày, giao lại T2 qua CLI trực tiếp; T1 chỉ tự sửa khi bug nằm ngoài app-code
thật (docs/memory/gitignore/config một dòng) hoặc chủ minh thị cho phép. Lý do đảo hướng: bằng chứng
sống trong chính phiên này — Codex tự chẩn đoán đúng nguyên nhân gốc (đo bằng
`window.getSelection()` thay vì đoán), tự chạy đủ verify thật, tự khai trung thực phần chưa làm
được — chất lượng ngang hoặc hơn một lượt T1 tự làm.

---
