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

## 2.1 ✅ CHỐT 2026-07-22 — `main` nghĩa là gì, và bao giờ merge vào nó

§2 nói *"`main` = trạng thái đã duyệt"* — quá mơ hồ để hành động, và hậu quả đo được: tới 22/07, **`main` tụt sau `develop` 33 commit**, đứng im ở PR #4 (thời 003/004). Toàn bộ 005 (Docker/Fly), 006 (DDL) và 007 (auth) **không có trên `main`**. Tức `main` không phải bản đang chạy, không phải điểm rollback (nó cũ hơn cả lần deploy thành công đầu tiên), và ruleset `protect-main` đang canh một nhánh không ai dùng. **Một con trỏ chết.**

Nguyên nhân không phải lười: chưa ai định nghĩa *điều kiện* để merge, nên không bao giờ tới lúc "đủ điều kiện".

**Định nghĩa chốt: `main` = bản đang chạy trên Fly mà chính chủ đã dùng tay và tin.** Không phải "code xong" — là **"đã sờ vào và nó sống"**.

| | `develop` | `main` |
|---|---|---|
| Nhận từ | mọi `feat/NNN` qua PR nhỏ | `develop`, khi một **lát cắt dùng được** |
| Điều kiện | CI xanh | CI xanh **+ đã nghiệm thu bằng mắt trên fly.dev** |
| Nhịp | mỗi task | mỗi 008a·008 / 009 / 010 / 011 / 012 |
| Ý nghĩa | "đã build" | "đã sống" |

- **Gắn tag `v0.x` mỗi lần merge vào `main`.** Không có tag thì `main` vẫn không phải đường lùi dùng được — muốn quay về "bản chạy tốt tuần trước" phải mò commit hash.
- **Từ 008b, `main` là trigger deploy** (CD chỉ chạy từ `main`, không từ `develop`). Điều này khiến định nghĩa trên tự cưỡng chế: cái gì lên `main` là cái đó ra production.
  - **📝 2026-07-22 (muộn trong ngày) — ĐẢO LẠI: trigger deploy là `develop`.** Gạch đầu dòng trên và điều kiện ở bảng (*"đã nghiệm thu bằng mắt trên fly.dev"*) tạo một **vòng tròn**: muốn merge vào `main` phải đã thấy nó chạy trên fly.dev, mà thứ duy nhất đưa code lên fly.dev lại là merge vào `main`. Hôm nay chưa cắn vì deploy còn gõ tay từ `develop`; sau 008b thì cắn. Nặng hơn: nếu lời giải là *"vẫn deploy tay để nghiệm thu"* thì **008b không gỡ được đúng khoản ma sát nó sinh ra để gỡ**. → **Chốt (chủ): merge vào `develop` = deploy production ngay; `main` không deploy, chỉ đánh dấu release ổn định kèm tag `v0.x`.** Chi tiết: `agent-tasks/008b-cd-fly-deploy.md`.
  - **📝 2026-07-22 — `main` KHÔNG deploy, và việc kiểm chứng dời hẳn sang `develop`.** Không có trigger nào trên `main`, cả trước lẫn sau 008b. **Chủ + T3 test ngay trên `develop`** — hợp lý vì `develop` *chính là* bản đang chạy production. `main` chỉ còn là **nhãn release ổn định**; lúc cân nhắc đẩy ra có thể test + review lại kỹ, nhưng đó là tuỳ nghi, không phải cổng.
    **Nói thẳng cái đã đổi, đừng để câu chữ cũ đánh lừa người đọc sau:** định nghĩa ở dòng 33 hàm ý việc chứng minh diễn ra **tại cổng vào `main`**. Nay nó diễn ra **liên tục trên `develop`**, nên `main` không thêm lớp kiểm chứng riêng nào nữa. Giá trị còn lại — vẫn thật, chỉ khác loại — là **điểm lùi được chọn có chủ ý**: mốc mà chủ đã nhìn lại cả lát cắt và nói "đây là chỗ đáng quay về". Ai đọc `main` như một cổng chất lượng là đọc sai kể từ 2026-07-22.
    **Hệ quả phải canh:** `main` giờ **không có cơ chế tự cưỡng chế nào** — chính thứ đã làm nó tụt 33 commit thành con trỏ chết. Phanh duy nhất là workflow CD in độ tụt `main` sau mỗi lần deploy (`agent-tasks/008b` mục 1.5). Nếu con số đó cứ lớn dần qua vài tuần thì luật này đang chết lần thứ hai, và lần này đã có sẵn đồng hồ đo.
  - **Đường lùi trong mô hình mới:** đường chính là **roll-forward** (`git revert` trên `develop` → CD chạy), vì nó đi đúng con đường được chạy mỗi ngày nên luôn ở trạng thái hoạt động. Deploy-từ-tag chỉ là đường phụ (`workflow_dispatch`). Lưu ý cái *không* mất: code trên `main` **đã từng chạy production** — nó đi qua `develop` trước; thứ chưa từng được kiểm là *cơ chế* deploy-từ-ref, không phải code.
- **Hệ quả cho việc chọn thứ vào `main`:** một bản vá chưa deploy, chưa nhìn bằng mắt thì **chưa được lên `main`** dù CI xanh và diff đã review. Ví dụ đầu tiên áp luật: PR [#10](https://github.com/NguyenHaiHung0510/microSched/pull/10) (đồng bộ 33 commit) **cố ý không mang theo** bản vá healthz của PR [#11](https://github.com/NguyenHaiHung0510/microSched/pull/11) — vá đó vào `develop` trước, lên `main` ở vòng sau, sau khi deploy và nhìn Neon ngủ thật.

**Vì sao không đơn giản cho `main` bám sát `develop`:** thế thì `main` không mang thêm thông tin nào so với `develop`, và ta mất đi thứ duy nhất đáng có ở một dự án một người — **một con trỏ tới trạng thái đã được chứng minh bằng tay**. Giá trị của `main` nằm đúng ở chỗ nó *tụt lại*, và tụt lại có lý do.

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
| **Copilot Pro \$10/th** | ❌ không mua — 2 phương án trên đã phủ |
| **GitHub Student Pack** | ⚠️ GitHub **tạm dừng đăng ký mới** Copilot student từ 4/2026; verify *trước* mốc đó thì còn. **Chính chủ nên tự kiểm tra tài khoản** |

- 📝 **2026-07-20:** Copilot Pro \$10 nay kèm cả **Claude + Codex agent** ([GitHub Changelog 26/02/2026](https://github.blog/changelog/2026-02-26-claude-and-codex-now-available-for-copilot-business-pro-users/)) nhưng chỉ ~\$15 credits/tháng → vẫn không đáng làm workhorse (§7); khi tới lúc cắm auto-review thì thành một option rẻ cạnh Claude-Code-Action/Jules. DEFER giữ nguyên.

## 5. Giao việc cho agent — ✅ quy ước mới

`agent-tasks/NNN-<slug>.md` = spec tự-chứa giao cho agent chạy độc lập. Mỗi spec bắt buộc có: bối cảnh đủ để đọc ở session 0-context · việc phải làm · **việc KHÔNG được làm** · acceptance kiểm chứng được · **model tier + effort đề xuất** (để không đốt token thừa). Chi tiết: `agent-tasks/README.md`.

📝 **2026-07-20 (nâng cấp cho §2, có hiệu lực từ 003):** executor mặc định cho task **code** = **T2 Codex** (§7); code chạy trên branch **`feat/NNN-<slug>`** → **PR nhỏ vào `develop`** để T1 review diff từng task — *docs* vẫn commit thẳng `develop` như cũ.

## 6. Chưa làm (không phải quên)
- **CI nền GitHub Actions** — ✅ dựng 2026-07-20 qua `agent-tasks/003`: job backend khóa theo `uv.lock`, chạy Ruff (lint + format) và pytest; job hooks chạy toàn bộ pre-commit. `agent-tasks/006` sẽ nối thêm hàng rào QA Alembic đã chốt ở `schema-physical-brief.md` §2 (round-trip test, drift-check, chặn drop ngầm) + thử migration trên bản restore (`db-and-data-model-brief.md`).
- **Hàng rào QA Alembic** — ✅ dựng 2026-07-21 qua `agent-tasks/006`: job CI thứ 4 **`Migration QA`** (drift-check phải ra diff rỗng + round-trip `downgrade base`/`upgrade head` trên Postgres container). **Cả 4 job giờ là required status check của ruleset `protect-main`** (đăng ký ngoài git, sửa bằng API — xem cảnh báo về đổi tên job ở `agent-tasks/004`).
- **Dependabot** — **điều kiện chặn đã hết** (2026-07-21: đã có `backend/uv.lock` + `frontend/package-lock.json`). Chưa bật, chưa quyết — ứng viên cho phiên sau.
- **Deploy Fly.io lần đầu** — ✅ hoàn tất 2026-07-20 qua `agent-tasks/005`: `microsched.fly.dev`, đúng 1 Machine `shared-cpu-1x` 256MB always-on tại `sin`; không volume, Fly Postgres hay Tigris.
- **Deploy pipeline** (`fly deploy` qua GitHub Actions) — **chưa làm**; đã ghi hướng ở `architecture-brief.md`, cần chốt cách giữ token an toàn trước.
- 👁 **THEO DÕI (2026-07-21, từ 007) — cảnh báo Fly "app is not listening on 0.0.0.0:8000"** xuất hiện lần đầu ở lần deploy 007, trong khi app **vẫn chạy đúng** và DNS ✓. Giả thuyết: 007 thêm `authlib` + `httpx` → thời gian import tăng → uvicorn bind cổng **muộn hơn** lúc Fly quét socket sau khi máy khởi động. Nhiều khả năng là *race lúc khởi động*, không phải lỗi thật. **Đáng theo dõi vì máy chỉ 256MB** (`fly.toml`): nếu sau này thấy 502 lúc deploy hoặc health-check trượt, đây là chỗ soi đầu tiên; và kiểm mức RAM thật (`architecture-brief.md` cho phép lên 512MB nếu OOM). Chưa sửa — chưa có triệu chứng thật nào ngoài dòng cảnh báo.
- ⏸ **MỞ (2026-07-21) — agent tự lái Chrome profile của chủ để test UI.** Ý tưởng của chủ, đúng hướng theo §7.1 (T3 + MCP Chrome-DevTools là tầng duy nhất thấy lớp lỗi trình duyệt). **Vướng thật:** profile đó chứa 4 tài khoản Google thật đang dùng hằng ngày → chạm luật ranh giới dữ liệu §7 luật 3 (*data thật chỉ tool local do chính chủ giám sát*). Cần quyết riêng: dùng profile Chrome **tách rời chỉ để test** (sạch về ranh giới nhưng phải tự đăng nhập lại), hay cấp quyền theo từng phiên có chủ ngồi cạnh. **Không nhét vào task nào đang chạy** — quyết trước, dùng sau.
  📌 **2026-07-21 — đã va vào hậu quả thật, nâng mức ưu tiên.** Sau khi merge 006, site thật **vẫn chạy image dựng từ 005** nên `/api/healthz` không có trường `db`; `fly secrets set` chỉ restart máy chứ **không build lại image**. Phải `flyctl deploy` tay mới lên sóng. → **Mỗi task merge xong, repo tiến còn site đứng yên** — đúng dạng lệch-trạng-thái mà dự án này sinh ra để tránh, chỉ ở tầng deploy thay vì tầng dữ liệu. Càng nhiều task thì cửa sổ "code đã merge nhưng chưa chạy" càng dễ bị quên. **Ứng viên số 1 cho task ngay sau 007.**

## 7. Harness 3 tầng + công cụ AI cá nhân — ✅ CHỐT 2026-07-20 (soi lại ~10/2026)

Bối cảnh: bước vào phase B (scaffold), chính chủ chốt bộ công cụ thi công. Tra giá/thị trường **live 2026-07-20** (nguồn cuối mục — thị trường coding-plan đổi theo quý, đừng tin con số này quá 10/2026). Nguyên tắc phân vai: **theo blast-radius của lỗi, không theo độ to của việc** (cùng nguyên tắc sequencing AI của chính app).

| Tầng | Công cụ | Vai |
|---|---|---|
| **T1 — óc** | **Claude Pro \$20** (từ 21/07: Opus 4.8 chat + Sonnet 5 Claude Code; Fable hết trên Pro 20/07) | viết spec `agent-tasks/`, ADR khi có quyết định mới, **review diff cuối trước merge**, debug khi T2 bế tắc, và **code security-critical** (auth/session/crypto — dùng tiết chế vì chung quota với chat) |
| **T2 — tay** | **Codex trên ChatGPT Plus \$20** (GPT-5.6; mua 07/2026) | thi công agent-tasks theo spec. Bậc trong Codex: **Sol** (cao) = việc khó đã có spec — auth/DDL/Docker/bug khó · **Terra** = workhorse mặc định — wiring/CRUD/UI/viết test · **Luna** (nhẹ, quota ~3–4×) = vòng lặp máy móc (test-fix-test, lint, rename). **Luật quota: Sol chỉ nhận việc đã có spec, không bao giờ nhận việc "thử xem sao"** — thứ giết limit là vòng lặp và test-spam, không phải task khó |
| **T3 — máy chạy test** | **2× Google AI Pro** (sẵn có) | **duy nhất một vai: CHẠY TEST** (unit/smoke/Postman/Chrome-DevTools-MCP UI/Playwright) theo hướng dẫn của T1/T2 — *chạy và report, không thiết kế test* (test case do T1 viết trong spec, T2 cài đặt). Kinh nghiệm chính chủ: Gemini 3.1 Pro / 3.5 Flash không đủ tin cho việc khác — nhưng test-loop đốt quota khủng và là việc khối-lượng-lớn/phán-đoán-thấp, khớp đúng quota-nhiều của Google. ⚠️ 2026-06-18: **Gemini CLI ngừng phục vụ gói AI Pro** — đường dùng còn lại là Jules / Antigravity / web |

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

## 7.1 📝 2026-07-21 — bằng chứng thực nghiệm cho vai T3: ba lỗi chỉ trình duyệt mới thấy

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

## 7.2 ✅ ĐÓNG 2026-07-22 — "cho agent lái Chrome profile thật của chủ" (mục MỞ từ 007)

Kiểm chứng thật bằng Codex: **chạy tốt**, chuyển được giữa nhiều profile, đi trọn luồng OAuth trên `microsched.fly.dev` (tài khoản trong allowlist vào được; tài khoản ngoài allowlist bị chặn đúng, sang `/auth/denied`), và **không** chạm trực tiếp cookie/mật khẩu/profile store.

⇒ **Hệ quả cho việc phân vai: trục "ai lái được trình duyệt" không còn trùng với trục tier.** §7.1 rút ra luật *"việc cần trình duyệt thì giao cho thứ lái được trình duyệt, bất kể tier"* trong bối cảnh chỉ T3 làm được. Nay T2 cũng làm được ⇒ **task browser không còn phải cắt đôi giữa hai tầng** — người viết code và người nhìn nó chạy có thể là một, đúng thứ [[feedback-verification-loop-over-model]] gọi là vòng lặp kiểm chứng. T3 vẫn giữ vai chạy test diện rộng.

⚠️ **Nhưng ranh giới dữ liệu siết lại, không nới ra.** Profile đó **không phải môi trường test** — nó là máy của chủ, đang đăng nhập sẵn mọi thứ. Luật đầy đủ ghi ở **`AGENTS.md`** mục *"Lái trình duyệt"* (chỉ dùng tài khoản được nêu tên; không rời phạm vi app; không đọc cookie/history/autofill; soi ảnh chụp trước khi dán; không đổi setting). Hai điểm đáng nhắc lại ở đây vì chúng thuộc threat model §1 chứ không thuộc kỹ thuật:

- **Có một tài khoản chính chủ cấm đụng.** Tên tài khoản **không ghi vào repo** — chỉ nêu trong prompt giao việc.
- **Không dán địa chỉ email thật vào PR/commit/docs.** Repo public + threat model = social engineering ⇒ danh sách tài khoản là vật liệu dựng pretext. Viết theo vai (*"tài khoản trong allowlist"*), không viết địa chỉ.

## 7.3 ✅ CHỐT 2026-07-22 (muộn) — Claude **điều phối** Codex trực tiếp, thay cho chuyển tay

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

**⚠️ Bất đối xứng chi phí lọc:** lọc PR của Codex-do-Claude-brief thì **rẻ** (Claude có sẵn mô hình "đáng lẽ thế nào"); lọc PR Jules chạy tự do thì **đắt** — phải dựng lại ý định từ diff, gần bằng tự viết. Một bộ lọc chỉ tiết kiệm băng thông khi nó **từ chối được rẻ**.

⇒ **Mở bằng số, không bằng niềm tin:** thử **5 task** loại *"đúng/sai do CI quyết"* (viết test theo danh sách T1 đã đặc tả — bulk, phán đoán thấp, blast radius ≈ 0). Đo **tỉ lệ PR được nhận** + **thời gian Claude tốn mỗi PR để lọc**. Nhận <50% hoặc lọc tốn gần bằng tự viết ⇒ **đóng lane**. Chuỗi lọc mong muốn về sau `T2 → T1 → chủ`; **lần đầu chạy thẳng `Claude → chủ`** cho chắc, thêm tầng sau khi có lòng tin.

### g) Nơi để việc + báo cáo

- **`agent-tasks/harness-audit/`** — spec đối soát harness, đánh số riêng `01`/`02` (không thuộc hàng đợi 001–012).
- **`harness-reports/`** — output. `.gitignore` giữ `README.md` trong git, **chặn nội dung**: repo public + threat model social engineering, mà báo cáo mô tả thói quen làm việc và bộ nhớ cá nhân — **không phải secret nên gitleaks không chặn**, dòng `.gitignore` là cơ chế duy nhất. Kiểm chứng bằng `git add -n`: chỉ `README.md` vào được index.
- **Vòng đời:** `harness-reports/` là **chỗ tạm ứng, không phải kho** — phát hiện nhập vào `AGENTS.md`/`~/.codex/AGENTS.md`/`docs/` xong thì dọn. Mục tiêu là **giảm** số nơi chứa sự thật.

*Nguồn (tra live 2026-07-22):* [codex-plugin-cc](https://github.com/openai/codex-plugin-cc) · [Codex Memories (OpenAI)](https://learn.chatgpt.com/docs/customization/memories) · [Neon free plan limits](https://neon.com/faqs/free-plan-limits-and-quotas) · [Jules pricing 2026](https://hackup.ai/ai-plans/jules/) · [Gemini 3.6 Flash in Antigravity](https://antigravity.google/blog/gemini-3-6-flash-in-google-antigravity)

---

## 8. Chạy nhiều agent song song — ⚠️ GHI NHẬN 2026-07-21, chưa nghiên cứu đủ

Bối cảnh: Codex lẫn Claude Code đều mở được nhiều session cùng lúc, và máy chủ **thừa sức về phần cứng** — nên câu hỏi không phải "máy chịu nổi không" mà là **"cái gì hỏng khi hai agent cùng chạy"**. Ghi lại để nghiên cứu tiếp trước khi mở song song thật (dự kiến từ 009).

**Giới hạn cứng — không thương lượng được:**
1. **Một Neon DB dùng chung.** Hai agent chạy Alembic/pytest cùng lúc = schema đá nhau, test chập chờn không tái hiện được. Hướng gỡ: mỗi agent một **Neon branch**. ⚠️ *Chưa tra:* giới hạn số branch + chi phí ở gói hiện tại.
2. **`http://localhost:8000/auth/callback` là redirect URI duy nhất cho local.** ⇒ đúng **một** agent chạy được luồng OAuth local tại một thời điểm. Ảnh hưởng trực tiếp mọi task đụng auth.
3. **Chuỗi Alembic có một head.** Hai agent mỗi người tạo một migration = hai head, phải merge tay. Luật: **một agent sở hữu chuỗi migration tại một thời điểm**.
4. **Chung working dir = hỏng.** Mỗi agent phải có **git worktree riêng**. ⚠️ *Chưa tra:* Codex xử lý worktree thế nào (Claude Code có sẵn `isolation: worktree`).

**Rủi ro:**
- **File dùng chung** bị đụng ở mọi slice: `main.py` (đăng ký router), `models.py`, `settings.py`. Conflict nhỏ nhưng liên tục.
- **Xung đột ngữ nghĩa — nguy hơn conflict git, vì git không báo gì.** Hai agent tự chế hai hình dạng error response, hai kiểu phân trang, hai lối đặt tên route → merge sạch sẽ, codebase mất mạch. Đây là lý do task **đặt khuôn** (008) phải chạy một mình *trước*.

**Chất lượng — nút cổ chai thật:**
Không phải quota (đo thật 003→006: chỉ ~20% quota tuần). Là **băng thông review của chính chủ**. N agent → N PR → vẫn chui qua một người. **Song song phía trên một nút thắt tuần tự chỉ tạo hàng đợi, không tạo thông lượng.** Và review 3 PR không liên quan cùng lúc thì chất lượng review tụt — với task security-critical (007) đó là mất mát thật, không phải lý thuyết.

**Luật tạm cho phase C (chốt 2026-07-21, xem lại sau 009):**
- **007 chạy một mình.** **008 chạy một mình** (đặt khuôn).
- **Từ 009** mở tối đa **2 luồng**, đủ cả 4 điều kiện: worktree riêng · Neon branch riêng · một chủ sở hữu chuỗi migration · convention đã đóng băng từ 008.
- Nguyên tắc: **chất lượng > thông lượng.** Không đổi review kỹ lấy song song.

### 📝 2026-07-22 (muộn) — mục này được MỞ LẠI: 4 giới hạn cứng rút còn 2, và kết luận "song song vô ích" hết hiệu lực

Hai thứ mới xuất hiện sau khi §8 được viết (21/07), cả hai đều ở `§7.3`:

**① Danh sách giới hạn cứng rút còn hai.**

| Giới hạn 21/07 | Trạng thái 22/07 |
|---|---|
| 1. Một Neon DB chung → schema đá nhau | ✅ **BIẾN MẤT** — dev + test chạy **Postgres trong Docker, mỗi lane một container/port** (§7.3e). Free hơn, nhanh hơn Neon branch, và **không cần Neon branch nữa**. |
| 2. Một redirect URI `localhost:8000` | ⚠️ **gỡ được, chờ chủ** — Google OAuth đăng ký được nhiều redirect URI; thêm `:8001`/`:8002`. **Không cần sửa code** (đã tra `auth.py`). |
| 3. Một Alembic head | ⚠️ Còn — nhưng đây là vấn đề *git*, không phải DB. **📌 biến quy ước thành cổng máy**: `Migration QA` bắt `alembic heads` trả đúng 1 dòng. |
| 4. Chung working dir | ⚠️ Còn — **lane slot** (§7.3e) gộp luôn #2 và #4 thành một bó cấu hình cố định, khai báo một lần. |

**⚠️ Ghi lại một khe hở loại [[feedback-gap-between-correct-decisions]] mà bản 21/07 đã tạo ra:** §8 kê thuốc *"mỗi agent một Neon branch"* — **đúng**, nó chữa va chạm schema. `cost-brief.md` §7 (22/07) ghi *"Neon mong manh, soi hằng ngày"* — cũng **đúng**. Hai file **không tham chiếu nhau**, và khoảng trống giữa chúng là: **branch chữa tính-đúng-đắn nhưng làm TỆ HƠN hạn mức**. Tra live 22/07: Neon free = **10 branch/project, branch dùng chung storage nên gần như miễn phí để tạo — nhưng 100 CU-hours là hạn mức của cả PROJECT, mọi branch xài chung một túi**; cộng autosuspend 5 phút ⇒ **mỗi lần đánh thức tính tối thiểu ~5 phút compute dù test chạy 10 giây** ⇒ 100 CU-h ≈ ~1.200 lần đánh thức/tháng, ba luồng chạy vòng lặp *test-fix-test* đốt hết trong **một buổi chiều**. Đây là biến thể thứ tư của lớp lỗi đó: **không phải hai quyết định để hở, mà là LỜI GIẢI của ràng buộc A làm tệ hơn ràng buộc B.**

**② Kết luận "song song không tạo thông lượng" phải xét lại.** §8 kết luận vậy vì nút cổ chai là **băng thông review của chính chủ** — đúng **với các cơ chế có lúc đó**. **Thang triage L1/L2/L3** (§7.3c) là cơ chế §8 chưa có, và nó **tấn công thẳng nút cổ chai**: Claude nuốt L3, nén L2 xuống một dòng PR ⇒ lượng-đọc-mỗi-luồng tụt hẳn. ⇒ Phần lớn "hiệu suất cộng thêm" nằm ở **thang**, không nằm ở số luồng — thang có tác dụng **ngay ở một luồng**, không cần chờ song song.

**Luật cập nhật cho phase C (thay luật 21/07):**
- **008 vẫn chạy một mình** — nhưng là **một luồng Codex do Claude điều phối + bật thang**, không phải Claude tự code. Đây là lần hiệu chuẩn thang.
- **Hai luồng từ 009/010**, sau khi đủ: thang đã có số hiệu chuẩn · lane slot đã dựng (worktree + trust + port + Postgres container) · redirect URI đã đăng ký · cổng `alembic heads` đã có · convention đóng băng từ 008.
- **Ba luồng: chưa.** Không phải "không bao giờ" — mà chưa giới hạn nào trong bốn cái trên được kiểm với ba.
- Nguyên tắc cũ **giữ nguyên**: chất lượng > thông lượng.

**Cần nghiên cứu thêm:** giới hạn/chi phí Neon branch · worktree ở Codex · có nên dùng Postgres ephemeral (container) cho *test* thay vì Neon branch — lưu ý luật "một store duy nhất" là về **nguồn sự thật của dữ liệu**, không phải về fixture test, nên đây có thể không vi phạm; nhưng 006 đã cho CI chạy trên Neon (`prepare_ci_database.py`) nên phải cân nhắc cùng chỗ.

## 9. ✅ CHỐT 2026-07-22 — CD: dựng ở **008b**, ngay sau 008a và **trước** 008

Tới 22/07 deploy vẫn là `fly deploy` gõ tay. Câu hỏi không phải "có nên tự động hoá không" mà là **bao giờ**, và câu trả lời không đến từ sự tiện lợi.

**Lý do chọn đúng khe này — CD là thứ làm cho luật nghiệm thu đủ rẻ để được tuân thủ.** §7.1 đã chốt: *task đụng bản build production thì Acceptance **bắt buộc** có bước nhìn bằng mắt trên deploy thật*. Từ 008 trở đi **mỗi slice đều đụng** (API + UI + cookie + service worker). Nếu deploy còn là việc thủ công thì mỗi lần nghiệm thu phải trả một khoản ma sát — và ma sát đặt đúng chỗ đó sẽ khiến người ta bỏ qua **đúng bước đã để lọt 4 lỗi ở 007**. CD ở đây không phải tiện nghi, nó là **hạ tầng của kỷ luật kiểm chứng**.

**Vì sao không sớm hơn (ngay bây giờ):** trước 008 chưa có gì để deploy ngoài trang đăng nhập; CD sẽ được chạy gần như 0 lần trước khi thực sự cần. **Vì sao không muộn hơn (sau 008):** 008 là task **đặt khuôn** — mọi slice sau bắt chước nó, kể cả bắt chước *quy trình nghiệm thu* của nó. Muốn khuôn đúng thì lúc đúc khuôn phải đã có CD.

**Nội dung 008b (spec viết sau, đây là ranh giới):**
- GH Actions: merge vào **`main`** → build + `fly deploy` → **smoke test bắt buộc**, đỏ thì fail. Smoke test gọi `/api/readyz` (không phải `healthz` — xem `health.py`), kiểm `status == "ok"`. Đây đúng là thứ đã bắt được lỗi crash-loop B1 của 007 nếu nó tồn tại lúc đó.
- Deploy **chỉ từ `main`** — nhất quán với §2.1, và khiến định nghĩa "`main` = bản đang chạy" tự cưỡng chế thay vì trông vào kỷ luật.
- Nuốt luôn 2 món polish tồn từ 007 (`auth-brief.md` §6.2): cảnh báo lúc khởi động khi thiếu `OAUTH_STATE_SECRET`, và `except Exception` trần ở callback. Cả hai là guardrail lúc khởi động/deploy — mà **CD làm deploy nhanh hơn ⇒ deploy sai cũng nhanh hơn**, nên đây đúng lúc chúng đáng giá nhất.
- Dựng luôn `CRON_TOKEN` + khung cron endpoint (backup/embed/nhắc thuốc) vì cùng chạm hạ tầng GH Actions.

**Bất biến bắt buộc mang theo (rút từ sự cố Neon 22/07, xem `cost-brief.md` §7):** **không job nền nào được poll DB với chu kỳ ngắn hơn cửa sổ idle 5 phút của Neon, trừ khi đã tính lại ngân sách CU-hr.** Cron backup/embed/nhắc thuốc sắp dựng ở chính 008b sẽ đâm thẳng vào bức tường này nếu không ghi trước.

**📝 2026-07-22 (muộn trong ngày) — spec đã viết: `agent-tasks/008b-cd-fly-deploy.md`. Ba điểm lệch so với ranh giới ở trên:**

1. **Trigger deploy = `develop`, không phải `main`; `main` không deploy nữa** — xem note ở §2.1, đó là chỗ giải vòng tròn.
2. **Smoke test kiểm thêm git SHA**, không chỉ `status == "ok"`. Lý do: nếu deploy hỏng một phần và Fly giữ machine cũ đang chạy tốt, smoke test chỉ kiểm `status` sẽ **xanh trên bản cũ** — báo thành công cho một lần deploy thất bại. Cùng họ với "test cho hành vi vắng mặt".
3. **Thu hẹp phạm vi — hai món đẩy ra:**
   - **Nhắc thuốc → 011.** Cách ngây thơ là cron 5 phút/lần hỏi DB "tới giờ chưa"; nhịp tối thiểu của GitHub Actions cron **đúng bằng 5 phút**, bằng luôn cửa sổ idle Neon, và lịch GH Actions còn hay trễ ⇒ **sự cố 22/07 mặc áo khác**. Lời giải là một quyết định thiết kế chưa chốt (lịch tính trước vs PWA notification), không thuộc một task hạ tầng.
   - **Script soi hoá đơn Fly/Neon → 008c.** `cost-brief.md` §7.4 gộp nó vào 008b vì *"đúng lúc hạ tầng GH Actions cron ra đời"* — nhưng hạ tầng đó **vẫn còn nguyên sau 008b**, nên gộp chỉ làm PR phình gấp đôi và cần thêm 2 secret mới.

**✅ §9 ĐÓNG 2026-07-22 — 008b đã chạy và đã nghiệm thu.** PR [#13](https://github.com/NguyenHaiHung0510/microSched/pull/13) merged; **deploy tự động đầu tiên** chạy 1m41s, mọi step xanh. Bằng chứng: `readyz.commit` = `c569878…` **khớp đúng merge commit** (không phải chỉ `status: ok`), `healthz` không đổi, bảng độ tụt in `main đang tụt 7 commit · tag gần nhất: v0.2`.

**Một mục còn treo, đã kiểm chứ không phải đoán:** `gh workflow run` trả `HTTP 404: workflow not found on the default branch` — GitHub chỉ mở `workflow_dispatch` khi file workflow **đã có trên default branch** (`main`), mà `main` chưa nhận 008b. ⇒ ⓐ cron production chưa gọi lần nào, bằng chứng đầu tiên là lần chạy theo lịch **10:17 giờ VN 23/07**; ⓑ **`workflow_dispatch` của `deploy.yml` — đường lùi phụ — cũng chưa tồn tại**, nên roll-forward hiện là đường lùi *duy nhất đang sống*. Cả hai tự sống lại ở lần merge `develop` → `main` kế tiếp. Chi tiết: `agent-tasks/008b-cd-fly-deploy.md` mục "⚠️ Sót lại".

---
*Cập nhật khi: bật auto-review, dựng CI, đổi repo visibility, hoặc đổi công cụ harness. Soi lại §4 + §7 sau ~3 tháng (~10/2026 — chính sách/giá vendor đổi nhanh). §8 xem lại sau khi chạy 009 (lần song song thật đầu tiên). **§9 đã đóng 2026-07-22**; mở lại nếu đổi hạ tầng deploy. §7.2 xem lại nếu đổi cách agent truy cập trình duyệt. Thêm note có ngày — không xóa kết luận cũ.*
