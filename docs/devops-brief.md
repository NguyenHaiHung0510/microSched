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
- **Đánh đổi đã biết khi giữ public:** secret scanning + push protection **free** (private repo cần GitHub Advanced Security trả phí) + giữ được giá trị portfolio.

  📝 **2026-07-23 — soi lại phần "đổi lại", và ghi đúng cỡ của nó.** Bản trước mô tả khoản đánh đổi là *"§12 có một ví dụ noti nêu tên một loại thuốc thật"*. Đó là **mô tả nhỏ hơn hiện thực**, nên nó không còn làm được việc của một biên bản: đọc lại sẽ tưởng phạm vi đã cân nhắc chỉ là một chuỗi, rồi không soi lại nữa. Cùng cơ chế đã giết định nghĩa `main` ở §2.1 — câu chữ đứng yên trong khi hiện thực đi tiếp.

  **Hiện thực (rà toàn repo 2026-07-23):** tên thuốc ở **ba** file (`tracking-brief.md` §12, `forward-spec.md` §11, `learnings-applied.md`) · giờ uống hằng ngày (§12) · hồ sơ hành vi hút thuốc/bia/bi-a (§1, §10) · họ tên + email thật trong mọi commit (git metadata). Ghép lại là một người **định danh được** kèm bệnh mạn tính, thuốc, nhịp sinh hoạt và hai yếu tố nguy cơ đi thẳng với chính bệnh đó.

  **Đường rủi ro thật không phải đường đã ghi ở gạch đầu dòng trên.** Pretext-attacker là chuyện xác suất thấp (không ai bỏ công dựng hồ sơ một sinh viên). Đường có thật là **người đọc được mời tới**: repo public một phần vì *"biết đâu lại là nhà tuyển dụng"* — và docs đang khai đúng với họ. Không cần kẻ tấn công, không cần động cơ.

  **Chủ tái khẳng định GIỮ (2026-07-23), có lý do:** *một công ty phân tích thông tin cá nhân ứng viên qua repo, rồi quyết định tuyển dựa vào đó, thì đã tự loại mình — và nếu điều kiện làm việc ở đó nguy hiểm cho sức khoẻ thì càng không.* Đây là **lọc ngược có chủ ý**, không phải bỏ qua rủi ro.

  **Đã sửa duy nhất một chỗ:** §10 Q2 bỏ cụm *"bộ lấy từ đời thật của chủ"* → *"bộ mẫu khởi đầu"* — sáu chữ không mang thông tin thiết kế nào, chỉ **xác nhận** danh sách là có thật. Giữ nguyên: tên thuốc, giờ giấc, và danh sách tracker hành vi (chúng là ràng buộc schema thật — §1 chốt thuốc lá không ghi số điếu, bia/bi-a phải ghi tiền; xoá đi là mất lý do).

  **KHÔNG rewrite git history — quyết định, không phải bỏ sót.** Repo public đã lâu, giả định đã bị clone/index; `filter-repo` đổi mọi hash và phá mọi bản clone để đổi lấy lợi ích một phần. Người đọc thật đọc HEAD, không đọc history.

## 2. Git workflow — ✅ CHỐT

- **Nhánh:** mọi thay đổi, kể cả docs, làm việc trên branch riêng → PR vào `develop`. Merge `develop` deploy production; sau production acceptance mới mở release-label PR vào `main`. `main` không deploy.
- **Ruleset `protect-main`** (đã bật trên GitHub): chặn xóa nhánh, chặn force-push, **bắt buộc PR** để vào `main`.
  - **`required_approving_review_count: 0` là CỐ Ý** — dự án một người; đòi 1 approval sẽ tự khóa chính mình (không ai tự duyệt PR của mình được). Rule vẫn có giá trị: ép mọi thay đổi đi qua PR (có chỗ để đọc lại diff) + chặn tai nạn force-push.
- **Quy ước commit:** **1 commit = 1 phiên quyết định** → history đọc được như nhật ký thiết kế. Message tiếng Việt, mô tả *tại sao* chứ không chỉ *cái gì*, kèm `Co-Authored-By:`.
- PR đầu tiên: [#1](https://github.com/NguyenHaiHung0510/microSched/pull/1) — gộp 3 phiên thiết kế (kiến trúc, schema vật lý, tracking).

## 2.1 ✅ CHỐT 2026-07-22 — `main` nghĩa là gì, và bao giờ merge vào nó

§2 nói *"`main` = trạng thái đã duyệt"* — quá mơ hồ để hành động, và hậu quả đo được: tới 22/07, **`main` tụt sau `develop` 33 commit**, đứng im ở PR #4 (thời 003/004). Toàn bộ 005 (Docker/Fly), 006 (DDL) và 007 (auth) **không có trên `main`**. Tức `main` không phải bản đang chạy, không phải điểm rollback (nó cũ hơn cả lần deploy thành công đầu tiên), và ruleset `protect-main` đang canh một nhánh không ai dùng. **Một con trỏ chết.**

Nguyên nhân không phải lười: chưa ai định nghĩa *điều kiện* để merge, nên không bao giờ tới lúc "đủ điều kiện".

**Quy tắc hiện hành: `develop` = nhánh production được deploy; `main` = release-label/rollback milestone do chủ chọn sau receipt production acceptance trên `develop`.** `main` không phải deployment trigger và không thêm cổng acceptance độc lập.

| | `develop` | `main` |
|---|---|---|
| Nhận từ | mọi `feat/NNN` qua PR nhỏ | `develop`, khi chủ chọn một lát cắt release |
| Điều kiện | CI xanh; runtime/production acceptance có receipt riêng | receipt production acceptance đã có trên `develop` + quyết định release của chủ; không deploy lại |
| Nhịp | mỗi task | theo quyết định release |
| Ý nghĩa | nhánh production được deploy | release-label và điểm rollback được chọn có chủ ý |

- **Gắn tag `v0.x` mỗi lần merge vào `main`.** Không có tag thì `main` vẫn không phải đường lùi dùng được — muốn quay về "bản chạy tốt tuần trước" phải mò commit hash.
- **RETIRED receipt (2026-07-22, wording cũ):** ~~Từ 008b, `main` là trigger deploy (CD chỉ chạy từ `main`, không từ `develop`).~~ **Current truth:** CD deploy chỉ từ `develop`; merge vào `develop` deploy production, còn `main` không deploy và chỉ nhận release-label PR sau production acceptance.
  - **📝 2026-07-22 (muộn trong ngày) — RETIRED receipt: đảo quyết định trigger deploy sang `develop`.** Gạch đầu dòng trên và điều kiện ở bảng (*"đã nghiệm thu bằng mắt trên fly.dev"*) tạo một **vòng tròn**: muốn merge vào `main` phải đã thấy nó chạy trên fly.dev, mà thứ duy nhất đưa code lên fly.dev lại là merge vào `main`. Hôm nay chưa cắn vì deploy còn gõ tay từ `develop`; sau 008b thì cắn. Nặng hơn: nếu lời giải là *"vẫn deploy tay để nghiệm thu"* thì **008b không gỡ được đúng khoản ma sát nó sinh ra để gỡ**. → **Chốt (chủ): merge vào `develop` = deploy production ngay; `main` không deploy, chỉ đánh dấu release ổn định kèm tag `v0.x`.** Chi tiết: `agent-tasks/008b-cd-fly-deploy.md`.
  - **📝 2026-07-22 — `main` KHÔNG deploy, và việc kiểm chứng dời hẳn sang `develop`.** Không có trigger nào trên `main`, cả trước lẫn sau 008b. **Chủ + T3 test ngay trên `develop`** — hợp lý vì `develop` *chính là* bản đang chạy production. `main` chỉ còn là **nhãn release ổn định**; lúc cân nhắc đẩy ra có thể test + review lại kỹ, nhưng đó là tuỳ nghi, không phải cổng.
    **Nói thẳng cái đã đổi, đừng để câu chữ cũ đánh lừa người đọc sau:** định nghĩa ở dòng 33 hàm ý việc chứng minh diễn ra **tại cổng vào `main`**. Nay nó diễn ra **liên tục trên `develop`**, nên `main` không thêm lớp kiểm chứng riêng nào nữa. Giá trị còn lại — vẫn thật, chỉ khác loại — là **điểm lùi được chọn có chủ ý**: mốc mà chủ đã nhìn lại cả lát cắt và nói "đây là chỗ đáng quay về". Ai đọc `main` như một cổng chất lượng là đọc sai kể từ 2026-07-22.
    **Hệ quả phải canh:** `main` giờ **không có cơ chế tự cưỡng chế nào** — chính thứ đã làm nó tụt 33 commit thành con trỏ chết. Phanh duy nhất là workflow CD in độ tụt `main` sau mỗi lần deploy (`agent-tasks/008b` mục 1.5). Nếu con số đó cứ lớn dần qua vài tuần thì luật này đang chết lần thứ hai, và lần này đã có sẵn đồng hồ đo.
  - **Đường lùi trong mô hình mới:** đường chính là **roll-forward** (`git revert` trên `develop` → CD chạy), vì nó đi đúng con đường được chạy mỗi ngày nên luôn ở trạng thái hoạt động. Deploy-từ-tag chỉ là đường phụ (`workflow_dispatch`). Lưu ý cái *không* mất: code trên `main` **đã từng chạy production** — nó đi qua `develop` trước; thứ chưa từng được kiểm là *cơ chế* deploy-từ-ref, không phải code.
- **Hệ quả cho việc chọn thứ vào `main`:** một bản vá chưa deploy, chưa nhìn bằng mắt thì **chưa được lên `main`** dù CI xanh và diff đã review. Ví dụ đầu tiên áp luật: PR [#10](https://github.com/NguyenHaiHung0510/microSched/pull/10) (đồng bộ 33 commit) **cố ý không mang theo** bản vá healthz của PR [#11](https://github.com/NguyenHaiHung0510/microSched/pull/11) — vá đó vào `develop` trước, lên `main` ở vòng sau, sau khi deploy và nhìn Neon ngủ thật.

**Vì sao không đơn giản cho `main` bám sát `develop`:** thế thì `main` không mang thêm thông tin nào so với `develop`, và ta mất đi thứ duy nhất đáng có ở một dự án một người — **một con trỏ tới trạng thái đã được chứng minh bằng tay**. Giá trị của `main` nằm đúng ở chỗ nó *tụt lại*, và tụt lại có lý do.

## 2.2 Ruleset — cấu hình sống **NGOÀI git**, nên phải chép vào đây

*(Ghi 2026-07-23. Trước đó ba dữ kiện này chỉ tồn tại trong memory của Claude — tức nếu đổi máy hoặc mất memory là mất hẳn. Đây là loại sự thật **không có file nào trong repo phản ánh**, nên brief là nhà đúng của nó.)*

| Ruleset | Id | Nội dung | Vì sao đúng như vậy |
|---|---|---|---|
| **`protect-main`** | `19172264` | chặn `deletion` + `non_fast_forward`, bắt buộc PR, **5 required status check**: `Backend checks` · `Frontend checks` · `Repository hooks` · `Migration QA` · `Production dependency check`. `bypass_actors: []` | approvals = **0 cố ý** (dự án 1 người). `bypass_actors` rỗng nghĩa là **không có cửa thoát nếu CI hỏng** — kẹt thì tạm `PATCH enforcement: disabled`, sửa xong bật lại. |
| **`protect-develop`** | `19198649` | chặn `deletion` + `non_fast_forward`, **1 required status check: `Secret scan`**. | *(xem dòng dưới — hàng này từng nói khác)* |

**📝 Sửa 2026-07-26 (phiên 013).** Hàng `protect-develop` ở trên từng ghi *"chỉ `deletion`+`non_fast_forward`, cố ý KHÔNG đặt required check, để giữ quy ước docs-commit-thẳng"*. **Câu đó hết đúng** khi `Secret scan` được siết thành required check trên `protect-develop` — đo thật: push thẳng một commit docs bị GitHub từ chối với `GH013: Required status check "Secret scan" is expected`. Đây là **đánh đổi có chủ ý** (chủ chốt 26/07): giữ cổng cứng trên `develop` (nơi merge = deploy production) đổi lấy việc **mọi thứ vào `develop`, kể cả docs, đều phải qua PR** — quy ước "docs commit thẳng" ở §5 đã chết, xem `CLAUDE.md` §Repo & workflow. Sửa tại chỗ vì đây là *current state*, không phải log lịch sử — xem luật phân loại D1 ở đầu `CLAUDE.md`.

⚠️ **Required check khớp theo TÊN job.** Thêm job mới thì phải thêm tay vào ruleset (`gh api`); **đổi tên job cũ làm PR kẹt vĩnh viễn** ở trạng thái *"Expected"* — không có lỗi đỏ nào để nhìn, chỉ là chờ mãi một check không bao giờ tới. Luật này đã được chép sang `AGENTS.md` cho executor. **Biến thể đã gặp thật (26/07):** `Secret scan` bị thêm nhầm vào `protect-main` trước khi job đó tồn tại trong `ci.yml` của `main` ⇒ mọi PR vào `main` kẹt; đã gỡ, và trạng thái đúng hiện tại là **`protect-main` KHÔNG có `Secret scan`** (job chỉ sống trong `ci.yml` của `develop`) — chỉ thêm lại sau khi `main` đồng bộ mang theo job đó.

**📝 2026-07-26 (đuôi phiên) — ruleset là trạng thái NGOÀI git, nên hai phiên chạy song song có thể ghi đè nhau mà không ai biết.** Trong một buổi, ruleset `protect-main` bị toggle Secret-scan-on/off **bốn lần** (thêm→gỡ→thêm lại→gỡ lại) bởi các phiên khác nhau không biết về nhau: phiên A thêm (đúng lúc job vừa xanh) → phiên B gỡ (đúng, vì main chưa có job) → phiên A thấy "mất" và thêm lại (SAI — hiểu nhầm một quyết định có chủ ý thành một tai nạn) → phiên khác gỡ lại lần cuối (đúng). Không có git log, không có PR, không có gì để `git status` trước khi sửa — khác hẳn cây làm việc, nơi `git status`/`git log` luôn cho biết ai vừa chạm gì. ⇒ **Trước khi "khôi phục" một cấu hình ngoài-git tưởng như bị mất, hỏi "có ai VỪA CHỦ Ý gỡ nó không" trước khi hỏi "sao nó mất".** Không có cách tự động kiểm — chỉ có thể đọc lại lý do (ở đây: dòng bảng này) trước khi hành động.

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
- ✅ **Lỗ đã bịt 2026-07-24** (`agent-tasks/008d` Mục 2): rule `microsched-db-env-var-value` trước chỉ liệt kê `DATABASE_URL`/`PGPASSWORD` — credential **ít quyền nhất** (CRUD-only). Hai chuỗi **quyền cao nhất** `NEON_OWNER_URL`/`NEON_MIGRATOR_URL` (đổi schema, tạo role — ⛔ không lên Fly, `backend/.env.example`) chỉ còn rule `microsched-db-connection-string` che, mà rule đó đòi mật khẩu chứa **chữ số** đúng vị trí ⇒ một URL Neon có mật khẩu không-chữ-số lọt **cả hai** rule, hook báo xanh. Bất đối xứng đúng chiều nguy hiểm (credential mạnh nhất che yếu nhất). Vá: thêm `NEON_OWNER_URL`, `NEON_MIGRATOR_URL`, `ENCRYPTION_MASTER_KEY`, `CRON_TOKEN`, `OAUTH_STATE_SECRET` vào nhóm tên + `keywords` của rule 2; **giữ nguyên** điều kiện "trông thật" (có chữ số) — nới ra sẽ báo nhầm `.env.example` và dạy người ta bỏ qua hook (§3 gốc). Test **ba trường hợp bằng binary gitleaks v8.30.1 thật** (không tin suông): (1) 5 biến gán giá trị **có** chữ số → chặn (exit 1, RuleID `microsched-db-env-var-value` bắt cả 5 dòng); (2) **lỗ đang vá** — chuỗi Neon gán cho biến owner với mật khẩu **không** chữ số: config **cũ** báo `no leaks found` (exit 0 — lọt), config **mới** chặn (exit 1); (3) **không báo nhầm** — `backend/.env.example` hiện tại, `postgresql+asyncpg://` trơn, và placeholder 5 biến (không chữ số) đều exit 0. `pre-commit run --all-files` sạch toàn repo (7/7 hook, kể cả gitleaks). Không cần `gitleaks:allow` mới — chuỗi test là file tạm ngoài repo, đã xoá.

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

📝 **2026-07-20 — RETIRED receipt:** executor mặc định cho task **code** = **T2 Codex** (§7); code chạy trên branch **`feat/NNN-<slug>`** → **PR nhỏ vào `develop`** để T1 review diff từng task. Phần *"docs vẫn commit thẳng `develop`"* đã bị rule bảo vệ `develop` thay thế; không dùng câu cũ làm hướng dẫn hiện hành.

## 6. Chưa làm (không phải quên)
- **CI nền GitHub Actions** — ✅ dựng 2026-07-20 qua `agent-tasks/003`: job backend khóa theo `uv.lock`, chạy Ruff (lint + format) và pytest; job hooks chạy toàn bộ pre-commit. `agent-tasks/006` sẽ nối thêm hàng rào QA Alembic đã chốt ở `schema-physical-brief.md` §2 (round-trip test, drift-check, chặn drop ngầm) + thử migration trên bản restore (`db-and-data-model-brief.md`).
- **Hàng rào QA Alembic** — ✅ dựng 2026-07-21 qua `agent-tasks/006`: job CI thứ 4 **`Migration QA`** (drift-check phải ra diff rỗng + round-trip `downgrade base`/`upgrade head` trên Postgres container). **Cả 4 job giờ là required status check của ruleset `protect-main`** (đăng ký ngoài git, sửa bằng API — xem cảnh báo về đổi tên job ở `agent-tasks/004`).
- **Dependabot** — **điều kiện chặn đã hết** (2026-07-21: đã có `backend/uv.lock` + `frontend/package-lock.json`). Chưa bật, chưa quyết — ứng viên cho phiên sau.
- **Deploy Fly.io lần đầu** — ✅ hoàn tất 2026-07-20 qua `agent-tasks/005`: `microsched.fly.dev`, đúng 1 Machine `shared-cpu-1x` 256MB always-on tại `sin`; không volume, Fly Postgres hay Tigris.
- **Deploy pipeline** (`fly deploy` qua GitHub Actions) — **chưa làm**; đã ghi hướng ở `architecture-brief.md`, cần chốt cách giữ token an toàn trước.
- 👁 **THEO DÕI (2026-07-21, từ 007) — cảnh báo Fly "app is not listening on 0.0.0.0:8000"** xuất hiện lần đầu ở lần deploy 007, trong khi app **vẫn chạy đúng** và DNS ✓. Giả thuyết: 007 thêm `authlib` + `httpx` → thời gian import tăng → uvicorn bind cổng **muộn hơn** lúc Fly quét socket sau khi máy khởi động. Nhiều khả năng là *race lúc khởi động*, không phải lỗi thật. **Đáng theo dõi vì máy chỉ 256MB** (`fly.toml`): nếu sau này thấy 502 lúc deploy hoặc health-check trượt, đây là chỗ soi đầu tiên; và kiểm mức RAM thật (`architecture-brief.md` cho phép lên 512MB nếu OOM). Chưa sửa — chưa có triệu chứng thật nào ngoài dòng cảnh báo.
- ⏸ **MỞ (2026-07-21) — agent tự lái Chrome profile của chủ để test UI.** Ý tưởng của chủ, đúng hướng theo §7.1 (T3 + MCP Chrome-DevTools là tầng duy nhất thấy lớp lỗi trình duyệt). **Vướng thật:** profile đó chứa 4 tài khoản Google thật đang dùng hằng ngày → chạm luật ranh giới dữ liệu §7 luật 3 (*data thật chỉ tool local do chính chủ giám sát*). Cần quyết riêng: dùng profile Chrome **tách rời chỉ để test** (sạch về ranh giới nhưng phải tự đăng nhập lại), hay cấp quyền theo từng phiên có chủ ngồi cạnh. **Không nhét vào task nào đang chạy** — quyết trước, dùng sau.
  📌 **2026-07-21 — đã va vào hậu quả thật, nâng mức ưu tiên.** Sau khi merge 006, site thật **vẫn chạy image dựng từ 005** nên `/api/healthz` không có trường `db`; `fly secrets set` chỉ restart máy chứ **không build lại image**. Phải `flyctl deploy` tay mới lên sóng. → **Mỗi task merge xong, repo tiến còn site đứng yên** — đúng dạng lệch-trạng-thái mà dự án này sinh ra để tránh, chỉ ở tầng deploy thay vì tầng dữ liệu. Càng nhiều task thì cửa sổ "code đã merge nhưng chưa chạy" càng dễ bị quên. **Ứng viên số 1 cho task ngay sau 007.**

## 7. Harness operating policy — ACTIVE

**✅ Owner-approved 2026-09-06: [harness-policy.md](harness-policy.md) là nguồn chuẩn duy nhất cho authority, coordination, review và merge.**

T1 có inherited authority trong outcome/boundaries đã được giao, có thể trực tiếp làm hoặc delegate và merge khi evidence/gate phù hợp đã đủ. Coordination metadata không tự cấp quyền và không là prerequisite cho mọi PR. Elevation dùng scoped authorization do authority holder cấp; Owner-only boundaries và task-specific safety contracts giữ nguyên. Ad-review theo risk/judgment, không bắt buộc mọi routine change; gate đã cam kết không tự bị bỏ.

Đọc [harness-policy.md](harness-policy.md) cho chi tiết và cases ALLOW/DENY. AGENTS.md là entry point, CLAUDE.md chỉ compatibility; [project-guide.md](project-guide.md) dẫn đến các brief chuyên biệt. Không cần private harness-core để thi công public repo.

**Retired:** blanket coordination_record schema/validator, T1-no-direct/no-merge và fixed role/model recipes của bản trước đã được thay thế, không phải lớp policy thứ hai. Biên lai/bài học cũ chuyển sang [harness history](history/harness-pre-authority-v1.md); nội dung policy cũ còn truy được trong Git trước commit migration. Không sửa gate riêng của một task chỉ vì nó dùng tên record cũ.

## 8. Chạy nhiều agent song song — RETIRED receipt (2026-07-21/23)

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

### 📝 2026-07-23 — giới hạn cứng #4 được ĐO, không còn là phỏng đoán (`agent-tasks/harness-audit/01`)

Chạy cùng một prompt tự-khai trên hai bề mặt — Codex app (A) và qua plugin (B) — rồi **lấy hiệu**. Ba kết quả đóng ba câu hỏi §8/§7.3 đang để ngỏ:

| Câu hỏi để ngỏ | Đo được | Hệ quả cho lane slot |
|---|---|---|
| **#4 chung working dir** — Codex qua plugin có cwd riêng không? | ❌ **TRÙNG y hệt cwd của Claude** (`…\microsched`) | Nhánh "worktree tự nhiên mỗi luồng" **không tồn tại**. Lane slot **phải cấp worktree tường minh**, và luật ***"chạy nền ⇒ Claude không chạm cây làm việc"* chuyển từ khuyến nghị sang BẮT BUỘC** — hai bên đang đứng trên cùng một cây file. |
| **§7.3b** — đường plugin có làm mất memory của Codex? | ✅ **KHÔNG mất** — bản B còn dán ra *nội dung* `MEMORY_SUMMARY` thật (bản A chỉ trích khối *hướng dẫn*) | Giao việc qua plugin **không mất ngữ cảnh tích luỹ**. ⚠️ Đọc đúng phạm vi: memory **của Codex** sống sót qua plugin — **không** nghĩa memory đi được Claude→Codex. Kết luận "không có cầu nối" ở §7.3b **giữ nguyên**. |
| Qua plugin Codex ghi file được không? | ⚠️ **Chưa trả lời được — phép đo bị nhiễu** | Quyền ghi là **cờ `--write`** (`codex-companion.mjs:491` → `workspace-write` / `read-only`), không phải giới hạn cứng. Phiên B ra "không ghi được" vì **chính prompt tự khai là phiên chỉ-đọc**, nên nó đo cái prompt chứ không đo đường plugin. `apply_patch` vẫn nằm trong bản kê tool của B. |

Phụ: bản kê tool qua plugin là **tập con thật sự** (56/78) — mất toàn bộ `codex_app__*` nên **Codex không tự quản lý được thread của chính nó** qua đường này, nhưng **không thiếu thứ nào để thi công** (`shell_command`, `apply_patch`, `update_plan`, `web__run` đủ cả).

**Một lớp lỗi mới cho luật biên lai:** chỉ thị định dạng **tới nơi mà không được thi hành**, và rơi **im lặng**. Prompt bắt mở đầu bằng một dòng cố định; Codex *đọc được* dòng đó (trích lại trong báo cáo) nhưng hiểu thành lời khai của caller nên không in ra. Không lỗi, không cảnh báo. ⇒ **Nghiệm thu phải kiểm dòng chữ thật trong sản phẩm, không suy từ "prompt đã gửi đúng".**

## 9. ✅ CHỐT 2026-07-22 — CD: dựng ở **008b**, ngay sau 008a và **trước** 008

Tới 22/07 deploy vẫn là `fly deploy` gõ tay. Câu hỏi không phải "có nên tự động hoá không" mà là **bao giờ**, và câu trả lời không đến từ sự tiện lợi.

**Lý do chọn đúng khe này — CD là thứ làm cho luật nghiệm thu đủ rẻ để được tuân thủ.** §7.1 đã chốt: *task đụng bản build production thì Acceptance **bắt buộc** có bước nhìn bằng mắt trên deploy thật*. Từ 008 trở đi **mỗi slice đều đụng** (API + UI + cookie + service worker). Nếu deploy còn là việc thủ công thì mỗi lần nghiệm thu phải trả một khoản ma sát — và ma sát đặt đúng chỗ đó sẽ khiến người ta bỏ qua **đúng bước đã để lọt 4 lỗi ở 007**. CD ở đây không phải tiện nghi, nó là **hạ tầng của kỷ luật kiểm chứng**.

**Vì sao không sớm hơn (ngay bây giờ):** trước 008 chưa có gì để deploy ngoài trang đăng nhập; CD sẽ được chạy gần như 0 lần trước khi thực sự cần. **Vì sao không muộn hơn (sau 008):** 008 là task **đặt khuôn** — mọi slice sau bắt chước nó, kể cả bắt chước *quy trình nghiệm thu* của nó. Muốn khuôn đúng thì lúc đúc khuôn phải đã có CD.

**RETIRED pre-spec draft (không phải policy hiện hành) — nội dung 008b từng dự kiến:**
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

## 10. ✅ CHỐT 2026-07-23 — Cron production rời GitHub Actions sang **Google Cloud Scheduler**

**Bằng chứng đóng mục treo ở §9.** §9 để lại câu *"cron production chưa gọi lần nào, bằng chứng đầu tiên là lần chạy theo lịch 10:17 giờ VN 23/07"*. Câu trả lời không phải "chưa tới giờ" mà là **nó sẽ không bao giờ chạy**, và kiểm được bằng một lệnh:

```
git ls-tree --name-only origin/main .github/workflows/   →  chỉ có ci.yml
```

`cron.yml` và `deploy.yml` **chỉ nằm trên `develop`**. GitHub đọc `schedule:` **chỉ từ default branch** — đúng cùng một luật đã làm `gh workflow run` trả 404 ở §9, nhưng §9 mới ghi nhận nó cho `workflow_dispatch` mà chưa suy tiếp sang `schedule`. Một luật, hai hệ quả, chỉ bắt được một.

**Vì sao KHÔNG vá bằng cách đưa `cron.yml` sang `main`.** Ba tầng lý do, tầng sau nặng hơn tầng trước:

1. GitHub **tự tắt scheduled workflow sau 60 ngày không có commit trên default branch** — tag, issue, PR **không** tính, chỉ commit. Tắt xong chỉ gửi **một email** cho người bật gần nhất; tab Actions không hiện lỗi gì.
2. Mà §2.1 chốt `main` **không deploy**, là nhãn release hiếm khi động vào — tức **được thiết kế để im lặng**. ⇒ **Luật git của chính dự án bảo đảm cron sẽ chết.** Vá bằng bot-commit định kỳ lên `main` thì phá luôn ý nghĩa duy nhất còn lại của `main` (điểm rollback chọn có chủ ý): mua scheduler bằng cách để lịch sử `main` nói dối về chính nó.
3. **Tầng nặng nhất, do chủ nêu:** microSched là app cá nhân — *không dev nữa thì app vẫn phải chạy*. GitHub Actions cron gắn lịch chạy vào **hoạt động phát triển**. Đó là **sai phạm trù**, không phải sai cấu hình. Cộng thêm trễ 5–30 phút là thường, >60 phút có ghi nhận lúc cao điểm.

**Cũng đã loại — cron từ trong app ra, vì va scale-to-zero (`architecture-brief.md` §5 note 23/07):** APScheduler in-process (máy ngủ ⇒ scheduler ngủ) · `fly machine run --schedule` (chỉ fuzzy hourly/daily/weekly/monthly, không có cron expression ⇒ không đặt được 20:00, lại không trigger tay được) · Supercronic/process `cron` trong `fly.toml` (là **máy thứ 2 always-on** ⇒ mua lại đúng khoản vừa tiết kiệm).

**✅ Chốt: Google Cloud Scheduler.** Đã cân nhắc cron-job.org / Cloudflare Workers Cron / Upstash QStash; cái quyết định là **chủ đã trả sẵn cái giá duy nhất tôi dùng để loại nó** — project `microSched` (tạo 21/07) đã là **Tier 1 · Prepay** với budget alert 88k VNĐ.

| | cron-job.org | **Cloud Scheduler** |
|---|---|---|
| Timeout mỗi lần gọi | **30s cứng** (cold start 8s ăn 27% ngân sách) | attempt deadline mặc định **180s**, chỉnh tới 30′ |
| Retry khi fail | không | **cấu hình được** (số lần + min/max backoff) |
| Kiểu chết im lặng | tự disable sau **25 fail liên tiếp** | không có |
| Giá | \$0 | **\$0** — 3 job free/billing account, dùng **1** |

**Thiết kế: MỘT job duy nhất, mãi mãi.** Nhắc thuốc 20:00 là job thật; heartbeat chỉ là dây điện — đừng tạo hai.
- **Bây giờ:** 1 job, cron `0 20 * * *`, timezone `Asia/Ho_Chi_Minh`, target `POST https://microsched.fly.dev/api/cron/heartbeat`, header `Authorization: Bearer <CRON_TOKEN>`. Chiếm sẵn slot 20:00 với payload vô hại.
- **Tới slice nhắc thuốc (011):** đổi URL sang endpoint thật. Vẫn 1 job, vẫn free, không migration.
- **Job đó ghi kèm RSS + uptime mỗi lần chạy** — canh rò rỉ bộ nhớ của `suspend` (§5 note 23/07) **không cần job thứ hai**.
- `cron.yml` đã **gỡ `schedule:`**, giữ `workflow_dispatch` làm nút bấm tay. ⚠️ Đừng thêm lại — sẽ thành nguồn cron thứ hai bắn song song vào cùng endpoint.

**✅ Job đã tạo + nghiệm thu 2026-07-24** (`web_check/04`): force run trả **200 OK**. Ba bẫy đã gặp khi tạo, ghi để lần tạo job sau (hoặc job thứ 2) không đạp lại:
- **Target type = HTTP, KHÔNG Pub/Sub.** Hướng dẫn mặc định của Google Cloud Scheduler dẫn sang Pub/Sub (chọn topic, gõ "Hello world"); microSched là endpoint HTTP trần, chọn Pub/Sub thì message rơi vào topic không ai đọc, app không nhận gì.
- **Mục "Auth header" của Scheduler để None.** Đó là OIDC/OAuth token để xác thực *với dịch vụ Google khác*; bật lên nó ghi đè header `Authorization` ⇒ Bearer token của mình mất ⇒ 401. Token của app đi ở dòng **HTTP headers** custom, không phải mục Auth header.
- **Ô URL nhạy khoảng trắng đuôi.** Lần đầu dính tab `%09` ở cuối (`/heartbeat%09`) ⇒ **405**. Copy-paste dễ dính; cắt sạch.
- Retry đặt **3** (miễn phí — Scheduler tính theo job/tháng, không theo lần chạy); attempt deadline để trống (= 3 phút, thừa cho cold start ~9s).

🔒 **Bất biến bắt buộc mang sang 011 (nhắc thuốc) — retry + chưa idempotent = nhắc TRÙNG.** Khi endpoint đổi từ "ghi log" sang "gửi web-push", kịch bản: push gửi xong → response rớt → Scheduler tưởng fail → thử lại → **push lần hai**. ⇒ Endpoint nhắc thuốc **phải đánh dấu "đã nhắc hôm nay" và biến các lần gọi sau thành no-op TRƯỚC KHI** dựa vào retry. Heartbeat lũy đẳng sẵn nên chưa đụng; nhắc thuốc thì bắt buộc.

**📌 Hai free tier khác nhau, đừng gộp** (chủ hỏi đúng chỗ này): free tier **Gemini API** mất khi bật billing trên project — đó là cảnh báo ở `cost-brief.md` §6, và nó **không còn áp** vì project `microSched` bật billing từ đầu. Free tier **Cloud Scheduler** tính theo billing account (3 job), **cần** billing mới dùng được. Không cần email khác, không cần project khác, không phải trả 2k/tháng (đó là giá job thứ 4).

**Lớp biên lai — mỏng, và biết vì sao mỏng.** Ban đầu lập luận *"lời nhắc vắng mặt thì không phát hiện được"*; **chủ bác đúng**: thuốc uống lúc ăn cơm, 20:00 là ngưỡng >97,5% đã uống rồi ⇒ lời nhắc là **backstop**, không phải cơ chế chính, nên rủi ro là **tích của hai xác suất nhỏ độc lập** (quên uống × cron hỏng), không phải một điểm chết. ⇒ Ghi `last_cron_run_at` + cảnh báo khi cũ: **có, nhưng mỏng**, ghép luôn vào job trên. Không dựng hệ giám sát riêng.

**Bất biến §9 vẫn nguyên giá trị, nay cộng thêm một:** ① không job nền nào poll DB dày hơn cửa sổ idle 5 phút của Neon; ② 🔒 **endpoint cron phải làm xong việc bên trong request** — proxy Fly mù với việc sinh ra sau khi response đã trả, và không có cách nào để app nói "tôi đang bận". Với deadline 180s của Cloud Scheduler thì đây gần như không phải hy sinh gì.

### 📝 2026-08-06 — ĐẢO LẠI: Fly always-on đảo luôn quyết định Scheduler (xoá GCS)

Toàn bộ tranh luận phía trên về Google Cloud Scheduler vs GitHub Actions giờ trở thành hồ sơ lưu trữ
lịch sử (legacy evidence) của giai đoạn `008`. Với `011d`, **GCS đã bị loại bỏ hoàn toàn** cùng mọi
cơ chế route `/api/cron/heartbeat` hay `CRON_TOKEN`. App chỉ dùng một **in-process async timer**.

**Đánh đổi đã được chấp nhận:**
1. Mất external retry policy/attempt deadline/independent result reporting; đổi lại được exact-time
   scheduling và xoá hẳn external API.
2. Reliability được dời vào process: 4 lần attempt tối đa (bền qua restart), timeout 20s cho Web Push,
   và observability qua logs.

**Runbook cutover vận hành một chiều (one-way):**
1. 011c/011b merge xong, 011d code sẵn sàng nhưng flag `ENABLE_INPROCESS_CRON=false`.
2. Deploy liveness preflight: app boot nhưng timer no-op.
3. Chủ xoá mọi GCS jobs và lưu biên lai sạch.
4. Đổi flag thành `true` và deploy SHA đã review, xác minh có đúng một Fly Machine chạy.
5. Mọi abort phải giữ flag `false` kèm manual downtime notification; **không** dựng lại GCS hay GitHub
   workflow cho scheduler. Không còn fallback external.

---
*Cập nhật khi: bật auto-review, dựng CI, đổi repo visibility, hoặc đổi công cụ harness. Soi lại §4 + §7 sau ~3 tháng (~10/2026 — chính sách/giá vendor đổi nhanh). §8 xem lại sau khi chạy 009 (lần song song thật đầu tiên). **§9 đã đóng 2026-07-22**; mở lại nếu đổi hạ tầng deploy. **§10 chốt 2026-07-23**; mở lại nếu đổi nhà cung cấp cron hoặc khi 011 cần >3 job. §7.2 xem lại nếu đổi cách agent truy cập trình duyệt. Thêm note có ngày — không xóa kết luận cũ.*

### j) 📝 2026-08-03 — RETIRED route snapshot: chuyển đổi Harness sang Codex Desktop + OpenCodex

Bối cảnh: snapshot này ghi nhận thời điểm dự án chuyển sang **Codex Desktop App** làm harness điều phối chính. Danh sách model/route bên dưới là historical evidence, không phải catalog có hiệu lực; dùng Runtime Catalog ở §7 cho availability hiện tại.

1. **T1 mới:** Môi trường Codex Desktop chính (Main Thread) đảm nhiệm vai T1. Model chính khi quay lại: `gpt-5.6-sol` (effort: `xhigh`/`high`). **Tạm thời từ 2026-08-04:** Terra đang giữ Main Thread; không tự đổi T1 giữa chừng chỉ vì một model khác vừa xuất hiện. Khi cần thêm một lượt reasoning/coding độc lập, dùng `openrouter/openai-gpt-5.6-luna` trước vì bảng tham chiếu hiện hành xếp Luna #1 ở intelligence, coding và agentic.
2. **T2 & T3 mới:** Sử dụng tính năng `spawn_agent` tích hợp sẵn trong Codex Desktop để điều phối sub-agents. Danh sách route tạm đã được chủ lưu ngày 2026-08-04: `google-antigravity/gemini-3.6-flash`, `openrouter/~deepseek-deepseek-v4-flash-latest`, `openrouter/openai-gpt-5.6-luna`.
   - **T2 (Thi công):** Spawn sub-agent với `fork_context: true`. Luna là lane mạnh nhất khi blast radius/lý luận khó đáng chi phí; **Gemini 3.6 Flash là mặc định vận hành trước DeepSeek Flash cho coding + intelligence theo chỉ thị trực tiếp của chủ**, dù bảng tham chiếu riêng lẻ xếp DeepSeek cao hơn Gemini ở cột coding. DeepSeek chỉ là fallback khi Gemini/Luna không gọi được; báo rõ route error, không âm thầm đổi model.
   - **T3 (Phản biện & Test):** Spawn sub-agent độc lập cho lượt review 6 trục (§7.3i) và e2e Playwright. Gemini 3.6 Flash là lane QA/review nhanh mặc định; Luna là lane review sâu khi PR có migration, privacy/auth, hoặc diff lớn. DeepSeek là fallback. Không giả định `gemini-3.1-pro-high` đang callable nếu nó không có trong danh sách route hiện hành.
3. **Giữ nguyên:** Rubric 6 trục (§7.3i), Merge Gate by criticality, Luật biên lai máy kiểm được, và Luật Full-Access git/Docker theo từng lệnh.

**Ranh giới bảo mật & Tín nhiệm Sub-agent / Executor (✅ Cập nhật 2026-08-04):**
- **Free OpenCode Sub-agents / Executors:** Áp dụng chính sách **Zero-Trust** đối với thông tin nhạy cảm. Tuyệt đối không cung cấp, đọc, echo hay chuyển giao file `.env`, API keys, credentials, tokens, hay dữ liệu cá nhân thật (real personal data). Chỉ cung cấp public code/docs và dữ liệu test giả lập/đã che chắn (`synthetic/redacted`).
- **Native OpenAI / Antigravity / OpenAI key / OpenRouter (ZDR enabled):** Được xếp hạng tín nhiệm cao (High Trust) nhờ hạ tầng native/chính chủ hoặc đã kích hoạt Zero Data Retention (ZDR). Tuy nhiên, mức tín nhiệm này **không** đồng nghĩa với việc được phép làm lộ secrets: tuyệt đối không chèn secrets/credentials vào prompt, commit message, pull request, diff, log, hay tài liệu repo.

**Bảng tham chiếu tạm do chủ cung cấp 2026-08-04 (không phải benchmark tự chạy trong repo):**

| Model | Intelligence | Coding | Agentic |
|---|---:|---:|---:|
| GPT-5.6 Luna | #1 | #1 | #1 |
| Gemini 3.6 Flash | #2 | #3 | #2 |
| DeepSeek V4 Flash 0731 | #3 | #2 | #3 |

**Điểm cần xem lại khi Sol quay lại làm T1:** đánh giá lại toàn bộ handoff Codex Desktop/OpenCodex — routing thực tế, skill/plugin có thể tự áp, rubric chất lượng T3, format receipt và độ tin cậy của từng lane. Đây là review mở có chủ ý; không mặc định hoá workflow tạm này thành policy vĩnh viễn.



### 8.3 QA sau cutover — Owner-operated staging

**✅ Reconciled 2026-09-06:** recipe ephemeral create/delete trước đây được thay bằng persistent develop/staging và Owner Restore/Sync, khớp [qa-framework.md §2.1](qa-framework.md). Không agent nào tự tạo/xóa/restore nhánh Neon.

- Local/CI: Postgres throwaway cho fast checks và round-trip migration.
- High-fidelity staging: Owner sync develop từ production main và xác nhận; sau đó chạy approved scrub và backend local/Vite QA. Không truyền secret qua inline CLI; không tự bơm cookie từ recipe cũ.
- Production: chỉ scoped approved smoke/acceptance; migration không tự chạy theo deploy, không destructive QA hoặc automation lặp.

Canonical commands/data/identity gates ở qa-framework và task được giao. Điều này sửa authority/workflow trong docs, không sửa backend scrub behavior hay mở một QA lane trong phiên migration harness.
