# DevOps / repo & CI — microSched

> **Trạng thái:** ✅ CHỐT phần nền (2026-07-19). Phần auto-review PR = ⏸ DEFER tới khi có code.
> **Tra cứu giá/chính sách: 2026-07-19** — mục §4 phụ thuộc chính sách vendor, **soi lại ~3 tháng** (giống `cost-brief.md`; không để pricing drift làm hỏng quyết định).
> **2026-07-20:** thêm **§7 — harness 3 tầng + công cụ AI cá nhân** (✅ CHỐT, tra giá live cùng ngày; soi lại ~10/2026 cùng `cost-brief.md` §6).
> Decision record tự-chứa. Nguyên tắc: **DevOps bắt đầu nhẹ từ sớm**, dựng hàng rào *trước* khi có thứ để rò rỉ.

---

## 1. Repo — ✅ CHỐT PUBLIC (2026-07-19)

`github.com/NguyenHaiHung0510/microSched` — **public, cố ý giữ public.**

**Threat model của chính chủ (quan trọng — chi phối mọi quyết định bảo mật sau này):**
- **KHÔNG ngại:** người vào đọc code (*"biết đâu lại là nhà tuyển dụng"* — repo còn là portfolio cho mục tiêu AI-eng), hay AI crawl nội dung (không có động cơ khai thác).
- **NGẠI:** **social engineering** — đây mới là lý do thật đằng sau private mode (`tracking-brief.md` §5) và noti nhắc thuốc kín đáo (§12). Nói cách khác: rủi ro không nằm ở *ai đọc được repo*, mà ở *thông tin cá nhân bị dùng để dựng pretext*.
- **Đánh đổi đã biết khi giữ public:** secret scanning + push protection **free** (private repo cần GitHub Advanced Security trả phí) + giữ được giá trị portfolio. Đổi lại: `docs/tracking-brief.md` §12 có ví dụ noti nêu tên một loại thuốc thật → chính chủ đã cân nhắc và **chấp nhận**; nếu đổi ý, sửa ví dụ thành trung tính (git history vẫn còn, muốn sạch hẳn phải rewrite).

## 2. Git workflow — ✅ CHỐT

- **Nhánh:** làm việc trên `develop` → PR vào `main`. `main` = trạng thái đã duyệt.
- **Ruleset `protect-main`** (đã bật trên GitHub): chặn xóa nhánh, chặn force-push, **bắt buộc PR** để vào `main`.
  - **`required_approving_review_count: 0` là CỐ Ý** — dự án một người; đòi 1 approval sẽ tự khóa chính mình (không ai tự duyệt PR của mình được). Rule vẫn có giá trị: ép mọi thay đổi đi qua PR (có chỗ để đọc lại diff) + chặn tai nạn force-push.
- **Quy ước commit:** **1 commit = 1 phiên quyết định** → history đọc được như nhật ký thiết kế. Message tiếng Việt, mô tả *tại sao* chứ không chỉ *cái gì*, kèm `Co-Authored-By:`.
- PR đầu tiên: [#1](https://github.com/NguyenHaiHung0510/microSched/pull/1) — gộp 3 phiên thiết kế (kiến trúc, schema vật lý, tracking).

## 3. Hàng rào secret — ✅ 2 lớp

| Lớp | Ở đâu | Chặn lúc nào | Trạng thái |
|---|---|---|---|
| GitHub **secret scanning** + **push protection** | server | lúc `git push` | ✅ đã bật (free vì repo public) |
| **pre-commit + gitleaks** | máy local | lúc `git commit` — sớm hơn | ⏳ spec `agent-tasks/001` |

Lý do cần cả hai: push protection chỉ cứu ở phút chót và chỉ với pattern provider biết; hook local chặn sớm hơn và bắt được cả secret tự chế. **`.env` đã nằm trong `.gitignore` từ commit đầu** (ràng buộc cứng ở `CLAUDE.md`).

**Kiểm chứng thật 2026-07-19** (không tin suông vào việc "đã cài xong"):
- ✅ gitleaks **chặn được**: GitHub PAT (`github-pat`), Stripe key (`stripe-access-token`) → exit 1.
- ⚠️ **LỖ ĐÃ PHÁT HIỆN:** chuỗi `postgresql://user:pass@host:5432/db` **KHÔNG bị bắt** bởi rule mặc định — trong khi **connection string Neon chính là secret số một của dự án này**. `.env` đã bị `.gitignore` chặn nên đường rò chính đã bịt; rủi ro còn lại là dán nhầm chuỗi vào file code/doc/log. → **`agent-tasks/002`** bịt lỗ này bằng rule riêng.
- 📝 Bài học quy trình: chuỗi key *mẫu* trong tài liệu AWS **không** kích hoạt gitleaks (có allowlist cho giá trị ví dụ nổi tiếng) → test hàng rào bảo mật phải dùng pattern **giống thật**, nếu không sẽ tưởng nhầm là công cụ hỏng, hoặc tệ hơn: tưởng nhầm là công cụ chạy tốt.
- ✅ **Lỗ đã bịt 2026-07-19** (`agent-tasks/002`): thêm `.gitleaks.toml` ở gốc repo (`[extend] useDefault = true` + 2 rule riêng — connection-string URI có `user:password@host` và `DATABASE_URL=`/`PGPASSWORD=` gán giá trị trông thật). Không cần sửa `.pre-commit-config.yaml` — đã kiểm tra README gitleaks v8.30.1: entry `gitleaks git --pre-commit --staged` tự tìm `.gitleaks.toml` ở target path (thứ tự ưu tiên #4) nếu không truyền `--config`/`GITLEAKS_CONFIG`. Đã test hai chiều bằng binary gitleaks v8.30.1 thật: chuỗi Neon giả có mật khẩu trông thật → bị chặn (exit 1); placeholder (`user:password`), `postgres://localhost/dbname` (không mật khẩu), và `postgresql+asyncpg://` (driver string trơn, `schema-physical-brief.md` §2) → không báo nhầm. `pre-commit run --all-files` sạch toàn repo (7/7 hook pass, kể cả gitleaks). Một dòng trong `agent-tasks/002-gitleaks-custom-rules.md` chứa nguyên văn chuỗi ví dụ dùng để test — được `gitleaks:allow` tại đúng dòng đó (không allowlist rộng tay).

## 4. Auto-review PR — ⏸ DEFER (tra 2026-07-19)

**Chưa cắm bây giờ, có lý do:** repo hiện **chưa có code** — auto-review chỉ đọc được văn bản tiếng Việt, giá trị thấp. **Cắm sau khi scaffold app.**

| Lựa chọn | Thực tế 2026-07-19 |
|---|---|
| **Claude Code GitHub Action** | ✅ **ưu tiên 1** — chính chủ đã trả tiền Claude Code, không tốn thêm subscription. Cài bằng `/install-github-app` |
| **Jules** (Google) | ✅ phương án free song song — 15 task/ngày, có action chính thức `google-labs-code/jules-action` |
| **Copilot Free** | ❌ **không** review PR trên github.com (chỉ review vùng chọn trong IDE) — dễ hiểu nhầm |
| **Copilot Pro $10/th** | ❌ không mua — 2 phương án trên đã phủ |
| **GitHub Student Pack** | ⚠️ GitHub **tạm dừng đăng ký mới** Copilot student từ 4/2026; verify *trước* mốc đó thì còn. **Chính chủ nên tự kiểm tra tài khoản** |

- 📝 **2026-07-20:** Copilot Pro $10 nay kèm cả **Claude + Codex agent** ([GitHub Changelog 26/02/2026](https://github.blog/changelog/2026-02-26-claude-and-codex-now-available-for-copilot-business-pro-users/)) nhưng chỉ ~$15 credits/tháng → vẫn không đáng làm workhorse (§7); khi tới lúc cắm auto-review thì thành một option rẻ cạnh Claude-Code-Action/Jules. DEFER giữ nguyên.

## 5. Giao việc cho agent — ✅ quy ước mới

`agent-tasks/NNN-<slug>.md` = spec tự-chứa giao cho agent chạy độc lập. Mỗi spec bắt buộc có: bối cảnh đủ để đọc ở session 0-context · việc phải làm · **việc KHÔNG được làm** · acceptance kiểm chứng được · **model tier + effort đề xuất** (để không đốt token thừa). Chi tiết: `agent-tasks/README.md`.

📝 **2026-07-20 (nâng cấp cho §2, có hiệu lực từ 003):** executor mặc định cho task **code** = **T2 Codex** (§7); code chạy trên branch **`feat/NNN-<slug>`** → **PR nhỏ vào `develop`** để T1 review diff từng task — *docs* vẫn commit thẳng `develop` như cũ.

## 6. Chưa làm (không phải quên)
- **CI workflow** (GitHub Actions) — đợi có code (**2026-07-20: đã spec** — `agent-tasks/003` phần nền lint/test/hooks, `agent-tasks/006` hàng rào QA Alembic). Khi làm, ghép luôn **hàng rào QA cho Alembic** đã chốt ở `schema-physical-brief.md` §2 (round-trip test, drift-check, chặn drop ngầm) + thử migration trên bản restore (`db-and-data-model-brief.md`).
- **Dependabot** — đợi có package manifest.
- **Deploy pipeline** (`fly deploy` qua GitHub Actions) — đã ghi hướng ở `architecture-brief.md`.

## 7. Harness 3 tầng + công cụ AI cá nhân — ✅ CHỐT 2026-07-20 (soi lại ~10/2026)

Bối cảnh: bước vào phase B (scaffold), chính chủ chốt bộ công cụ thi công. Tra giá/thị trường **live 2026-07-20** (nguồn cuối mục — thị trường coding-plan đổi theo quý, đừng tin con số này quá 10/2026). Nguyên tắc phân vai: **theo blast-radius của lỗi, không theo độ to của việc** (cùng nguyên tắc sequencing AI của chính app).

| Tầng | Công cụ | Vai |
|---|---|---|
| **T1 — óc** | **Claude Pro $20** (từ 21/07: Opus 4.8 chat + Sonnet 5 Claude Code; Fable hết trên Pro 20/07) | viết spec `agent-tasks/`, ADR khi có quyết định mới, **review diff cuối trước merge**, debug khi T2 bế tắc, và **code security-critical** (auth/session/crypto — dùng tiết chế vì chung quota với chat) |
| **T2 — tay** | **Codex trên ChatGPT Plus $20** (GPT-5.6; mua 07/2026) | thi công agent-tasks theo spec. Bậc trong Codex: **Sol** (cao) = việc khó đã có spec — auth/DDL/Docker/bug khó · **Terra** = workhorse mặc định — wiring/CRUD/UI/viết test · **Luna** (nhẹ, quota ~3–4×) = vòng lặp máy móc (test-fix-test, lint, rename). **Luật quota: Sol chỉ nhận việc đã có spec, không bao giờ nhận việc "thử xem sao"** — thứ giết limit là vòng lặp và test-spam, không phải task khó |
| **T3 — máy chạy test** | **2× Google AI Pro** (sẵn có) | **duy nhất một vai: CHẠY TEST** (unit/smoke/Postman/Chrome-DevTools-MCP UI/Playwright) theo hướng dẫn của T1/T2 — *chạy và report, không thiết kế test* (test case do T1 viết trong spec, T2 cài đặt). Kinh nghiệm chính chủ: Gemini 3.1 Pro / 3.5 Flash không đủ tin cho việc khác — nhưng test-loop đốt quota khủng và là việc khối-lượng-lớn/phán-đoán-thấp, khớp đúng quota-nhiều của Google. ⚠️ 2026-06-18: **Gemini CLI ngừng phục vụ gói AI Pro** — đường dùng còn lại là Jules / Antigravity / web |

**Flow một agent-task (code):** T1 viết spec → T2 thi công trên `feat/NNN-<slug>`, tự chạy test + pre-commit → PR nhỏ vào `develop` → T1 review diff theo 3 câu (*đúng spec? đúng brief? có tự phát minh kiến trúc không?*) → chính chủ merge. **Escalation:** T2 bí >2 vòng hoặc muốn làm khác điều đã ✅ CHỐT → dừng, ghi nhận, đẩy lên T1. `docs/` là luật — chỉ chính chủ + T1 sửa nội dung quyết định.

**Ranh giới dữ liệu cho tool bên thứ ba (3 luật — suy từ threat model §1):**
1. **Code + docs = public** (repo vốn public) → tier nào chạm cũng được, kể cả tool Trung Quốc nếu sau này dùng.
2. **`.env` / secret / token** → không tier nào cả — agent code bằng `.env.example`; giá trị thật chỉ chính chủ đặt tay vào `.env` local / Fly secrets.
3. **Data thật** (Postgres cũ `microschedule_v2`, cutover migration, export cá nhân) → chỉ tool local do chính chủ giám sát với model T1. Code vốn công khai — *data* mới là tài sản của threat model này.

**Vì sao Codex, và đã loại gì (tra 2026-07-20):** cùng mốc $20 không có lựa chọn mạnh hơn cho long-horizon infra — Codex dẫn Terminal-Bench 2.1 (~83% vs ~79% Claude Code/Opus 4.8), và 07/2026 OpenAI **bỏ cap 5h chỉ còn cap tuần** → hợp kiểu làm burst cuối tuần. Phase B toàn việc "sai âm thầm thành nợ" (Alembic/Docker/auth) — không phải chỗ tiết kiệm $8 để nhận model bậc dưới. Đã loại: **gói Trung không còn rẻ như 2025** — GLM Lite $12.6–18/mo (promo $3 đã chết 02/2026; quota multiplier 3× giờ cao điểm trên GLM-5.x — *trùng giờ làm việc VN*), MiniMax entry nay $20, Kimi ~$28 quy đổi, Qwen $50 (free tier đóng 04/2026) → **GLM Lite = phương án ngân sách dự phòng** khi việc còn lại là bulk (re-check 10/2026); **Cursor $20** — IDE, sai hình dạng workflow spec→CLI-agent; **Copilot Pro $10** — $15 credits không đủ workhorse (để dành cho auto-review, §4); **DeepSeek V4** (ra 07/2026) — API pay-per-token siêu rẻ ($0.14–0.435/M input), ghi sổ làm **van xả bulk**, chưa mua; **Grok Build** (ra 08/07) — quá mới; **Antigravity** (free trong gói Google sẵn) — không làm T2 vì kinh nghiệm chính chủ với hệ Google agentic, giữ làm fallback $0. Lưu ý đọc benchmark: Terminal-Bench đo "tay" (agentic execution) — không đo "óc giữ luật dự án"; context/ritual/briefs sống ở hệ Claude → **mua Codex không đổi vai T1**.

Chi phí cả stack + bảng giá đối chiếu: `cost-brief.md` §6. Nguồn chính: [Codex với gói ChatGPT](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan) · [bỏ cap 5h 07/2026](https://explainx.ai/blog/chatgpt-codex-5-hour-limit-removed-weekly-reset-july-2026) · [Terminal-Bench ranking](https://www.morphllm.com/ai-coding-agent) · [giá GLM](https://www.aipricing.guru/z-ai-subscription-pricing/) · [MiniMax pricing docs](https://platform.minimax.io/docs/guides/pricing-token-plan) · [Qwen đóng free tier](https://inventivehq.com/blog/qwen-code-still-free-2026-shutdown) · [DeepSeek V4](https://www.tldl.io/resources/deepseek-api-pricing) · [Gemini CLI bị cắt (The Register)](https://www.theregister.com/ai-ml/2026/05/20/bye-bye-gemini-cli-google-nudges-devs-toward-antigravity/5243605)

---
*Cập nhật khi: bật auto-review, dựng CI, đổi repo visibility, hoặc đổi công cụ harness. Soi lại §4 + §7 sau ~3 tháng (~10/2026 — chính sách/giá vendor đổi nhanh). Thêm note có ngày — không xóa kết luận cũ.*
