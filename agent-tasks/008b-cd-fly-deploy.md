# 008b — CD: merge `develop` là deploy, kèm smoke test chứng minh bản mới thật sự đang chạy

> **Trạng thái:** ✅ **DONE + NGHIỆM THU 2026-07-22.** PR [#13](https://github.com/NguyenHaiHung0510/microSched/pull/13) merged; deploy tự động **đầu tiên** chạy thật (1m41s, mọi step xanh). Khối B đạt: `readyz.commit` = `c569878…` **khớp merge commit**, `healthz` không đổi, bảng độ tụt in `main đang tụt 7 commit · tag gần nhất: v0.2`. **Còn treo một mục**, xem "⚠️ Sót lại" cuối file.
> **Executor dự kiến:** T2 — Codex · **Bậc model: Sol (bậc cao)** · **Effort:** high · **Skill gợi ý:** (không) · **MCP cần:** (không)
> *Lý do bậc: cùng họ với 005 — CI/CD là chỗ "sai âm thầm thành nợ". Thêm nữa task này cầm `MICROSCHED_DEPLOY_TOKEN`, tức sai một dòng YAML là lộ quyền deploy lên chính app đang chạy.*
> *Quota **không** phải ràng buộc (đo thật 003→006: cả chuỗi tốn ~20% quota tuần; Codex còn reset dày). **Đừng hạ bậc để tiết kiệm** — task này có cả browser lẫn CI, hạ bậc là mua rủi ro bằng thứ đang dư.*
> *Executor lái được Chrome bằng **profile thật của chủ** ⇒ đọc `AGENTS.md` mục "Lái trình duyệt" trước khi mở tab đầu tiên.*

## Bối cảnh (đọc trước, đừng bỏ qua)

Đọc `CLAUDE.md` + `docs/devops-brief.md` §2.1 và §9 + `docs/cost-brief.md` §7 + `backend/app/web/routers/health.py` (đọc **cả docstring**, nó giải thích một sự cố thật).

Tới 2026-07-22 deploy vẫn là `fly deploy` gõ tay. **Vì sao tự động hoá đúng lúc này, không sớm không muộn:** sớm hơn thì chưa có gì để deploy ngoài trang đăng nhập; muộn hơn thì 008 — task **đặt khuôn** mà mọi slice sau bắt chước, kể cả bắt chước *quy trình nghiệm thu* — bị đúc lúc chưa có CD.

**Và vì sao nó không phải tiện nghi:** từ 008 trở đi mỗi lát cắt đều đụng bản build production (API + UI + cookie + service worker), nên Acceptance **bắt buộc** có bước nhìn bằng mắt trên deploy thật (`devops-brief.md` §7.1). Nếu deploy còn thủ công thì mỗi lần nghiệm thu phải trả một khoản ma sát — đặt đúng ở bước **đã để lọt 4 lỗi ở 007**. CD ở đây là hạ tầng của kỷ luật kiểm chứng.

### 📝 Đổi so với `devops-brief.md` §9 — trigger deploy là `develop`, không phải `main` (chốt 2026-07-22, muộn trong ngày)

§9 viết *"deploy chỉ từ `main`"*. Đọc cùng §2.1 (điều kiện merge vào `main` = *"CI xanh **+ đã nghiệm thu bằng mắt trên fly.dev**"*) thì thành vòng tròn: muốn lên `main` phải đã thấy nó chạy trên fly.dev, mà thứ duy nhất đưa code lên fly.dev là merge vào `main`.

**Chủ giải bằng cách đảo trigger — và bỏ hẳn deploy ở `main`:**

| | `develop` | `main` |
|---|---|---|
| Trigger deploy | **merge = deploy production ngay** | **không deploy gì cả, không bao giờ** |
| Ý nghĩa | "đang chạy production" | "nhãn release ổn định" |
| Kiểm chứng | **chủ + T3 test ngay tại đây** — đây chính là bản đang chạy | có thể test + review lại kỹ lúc cân nhắc đẩy ra |
| Cổng vào | 5 required checks | chủ thấy lát cắt đủ ổn định để đánh dấu |
| Nhịp | mỗi task | mỗi lát cắt, kèm tag `v0.x` |

**Nói thẳng cái đã đổi:** §2.1 gốc coi `main` là *"con trỏ tới trạng thái đã được chứng minh bằng tay"* — hàm ý việc chứng minh diễn ra **ở cổng vào `main`**. Trong mô hình này việc chứng minh diễn ra **liên tục trên `develop`** (vì `develop` chính là production), nên `main` không còn thêm một lớp kiểm chứng riêng nào. Giá trị còn lại của nó — vẫn thật, chỉ khác loại — là **điểm lùi được chọn có chủ ý**: một mốc mà chủ đã nhìn lại toàn bộ lát cắt và nói "đây là chỗ đáng quay về". Ghi rõ vì nếu cứ để nguyên câu chữ cũ, sáu tháng nữa sẽ có người đọc `main` như một cổng chất lượng mà nó không còn là.

**Hai hệ quả phải xử trong chính task này:**

1. **`main` mất tính tự-cưỡng-chế.** §9 chọn deploy-từ-`main` chính là để việc lên `main` không phụ thuộc kỷ luật con người — thứ đã làm `main` tụt 33 commit thành con trỏ chết (§2.1). ⇒ **Bắt buộc mục 1.5 dưới đây** (in độ tụt sau mỗi deploy). Biến kỷ luật thành thứ nhìn thấy, không phải thứ phải nhớ.
2. **Production giờ chạy `develop`.** Chấp nhận được vì chỉ có một người dùng và người đó chính là người đang sửa. Nhưng nghĩa là PR `feat/NNN → develop` nay là **cổng chất lượng cuối cùng trước production** — không còn nhánh nào để hỏng an toàn.

**Đường lùi (ghi rõ để không ai đi dựng thứ phức tạp hơn):** đường chính là **roll-forward** — `git revert` trên `develop`, CD chạy, xong. Nó đi đúng con đường được chạy mỗi ngày nên luôn ở trạng thái hoạt động. `workflow_dispatch` ở mục 1.4 là đường phụ, giữ vì rẻ, **không** cần chứng minh trong Acceptance.

## Việc của CHỦ trước khi chạy task

- [x] **Token deploy Fly đã tạo 2026-07-22** — deploy token phạm vi **chỉ app `microsched`**, không phải personal token, không phải org token. Không có trong `backend/.env`, không có trong Fly secrets (kiểm bằng `flyctl secrets list` — đúng là không thấy).
- [x] **Secret trên GitHub tên `MICROSCHED_DEPLOY_TOKEN`** — đổi tên xong 2026-07-22, bản tên cũ đã xoá (kiểm bằng `gh secret list`, chỉ còn đúng một dòng).
  *Vì sao không dùng tên mặc định `FLY_API_TOKEN`:* tên phải phản ánh **phạm vi quyền**, mà token này chỉ có quyền trên app `microsched` — tên mặc định ngụ ý "token API của Fly", rộng hơn hẳn. Giá phải trả là đúng một dòng map trong workflow (mục 1.3).
  ⛔ Token này **không bao giờ** lên Fly secrets: app không gọi `flyctl`, nên đưa vào chỉ tạo đường leo thang *"đọc được env" ⇒ "deploy được code tuỳ ý"*. Cùng lý do với `NEON_OWNER_URL`/`NEON_MIGRATOR_URL`.
- [x] **`CRON_TOKEN` — `backend/.env` (giá trị A) + Fly secrets (giá trị B, đã `Deployed`)**, hai giá trị khác nhau.
- [x] **`CRON_TOKEN` đã vào GitHub repo secrets**, giá trị **bằng bản trên Fly** (không phải bản local) — kiểm bằng `gh secret list` 2026-07-22. Workflow cron gọi endpoint **production** nên nó xác thực với bản Fly.
  *Quên bước này thì workflow cron trả 401 — trông y hệt lỗi "dependency bearer sai" ở mục 3.2, dễ đi sửa nhầm code thay vì sửa cấu hình.*
- [x] Docker Desktop đã bật (không bắt buộc — build chạy trên remote builder của Fly — nhưng có thì `docker build` thử local được).

## Phải làm

### 1. Workflow CD — `.github/workflows/deploy.yml`

**1.1 Trigger.** `on: push: branches: [develop]` + `workflow_dispatch` (mục 1.4).
**KHÔNG có trigger nào trên `main`** — `main` không deploy gì cả, nó chỉ là nhãn release (xem note ở đầu spec).
**Tuyệt đối KHÔNG** dùng `pull_request_target`. Repo này **public** ([devops-brief.md](../docs/devops-brief.md) §1) ⇒ `pull_request_target` sẽ trao token deploy cho PR từ fork bất kỳ. `ci.yml` hiện dùng `pull_request` đúng vì lý do này (đã được security-review PR #9 xác nhận) — giữ nguyên nguyên tắc đó.

**1.2 Chống chạy chồng.** `concurrency: { group: deploy-production, cancel-in-progress: false }`. Hai merge sát nhau mà deploy song song thì thứ tự bản lên production trở nên ngẫu nhiên. **Không** `cancel-in-progress` — huỷ giữa chừng một `fly deploy` là để lại trạng thái không ai biết.

**1.3 Các bước.**
1. `flyctl deploy --remote-only --build-arg GIT_SHA=${{ github.sha }}`, với
   `env: FLY_API_TOKEN: ${{ secrets.MICROSCHED_DEPLOY_TOKEN }}` — **map một dòng**, vì secret đặt tên theo phạm vi quyền còn `flyctl` đọc biến `FLY_API_TOKEN`. Đây là chỗ duy nhất hai tên gặp nhau; ghi comment ngay tại dòng đó.
2. Smoke test (mục 2) — **đỏ thì job fail**.
3. In bảng độ tụt `main` (mục 1.5).

Không chạy lại bộ test ở đây: ruleset đã bắt 5 check qua ở PR, và bản thân `Dockerfile` cài `uv sync --frozen --no-dev` ⇒ **chính lần build này là job `Production dependency check`** — đúng thứ bắt được lỗi `httpx` (B1) của 007.

**1.4 `workflow_dispatch`** nhận input `ref` (mặc định `develop`) để deploy lại một tag/commit bất kỳ. Vài dòng YAML, giữ làm đường phụ.

**1.5 Bảng độ tụt.** Cuối job, in vào `$GITHUB_STEP_SUMMARY`:
`develop @ <sha ngắn> đang chạy production · main đang tụt N commit · tag gần nhất: vX.Y`
(`git rev-list --count origin/main..origin/develop`). Đây là cái phanh cho hệ quả (1) ở trên — **không phải trang trí, đừng bỏ**.

### 2. Smoke test — phải chứng minh **bản mới** đang chạy, không chỉ "có thứ gì đó sống"

**2.1 Gọi `https://microsched.fly.dev/api/readyz`** (public URL, không phải internal), kiểm `status == "ok"` **và** `commit` khớp `${{ github.sha }}`.

**Vì sao `readyz` chứ không `healthz`:** health check của Fly nay trỏ `/api/healthz`, endpoint **cố ý không chạm DB**. Nên một machine khởi động được nhưng sai cấu hình DB **vẫn pass health check và `fly deploy` vẫn báo xanh**. `readyz` là thứ duy nhất chứng minh app với lấy được Neon.

**Vì sao phải kiểm `commit`, không chỉ `status`:** nếu deploy hỏng một phần và Fly giữ machine cũ đang chạy tốt, smoke test chỉ kiểm `status` sẽ **xanh trên bản cũ** — báo thành công cho một lần deploy thất bại. Đây là test cho *hành vi vắng mặt*, đúng loại đã bỏ sót ở sự cố Neon.

**2.2 Bơm SHA qua đường build.**
- `Dockerfile`: `ARG GIT_SHA=unknown` ở runtime stage → `ENV GIT_SHA=${GIT_SHA}`.
- `app/core/settings.py`: thêm `git_sha: str = "unknown"`.
- `health.py`: `/api/readyz` trả thêm `"commit": settings.git_sha`.
- **`/api/healthz` giữ nguyên** — không thêm field, không thêm gì. Nó là bề mặt bị ping 2.880 lần/ngày.

Lộ git SHA ra endpoint không auth **không rò gì**: repo public theo quyết định có chủ ý (`devops-brief.md` §1). Ghi lại để lần security-review sau không mất thời gian tra.

**2.3 Retry.** Thử lại có backoff, trần ~90 giây rồi fail. `fly deploy` trả về khi machine đã healthy, nhưng healthy ≠ đã nhận traffic.

**2.4 Ghi rõ vào comment của workflow:** smoke test **không** vi phạm bất biến Neon (mục "Bất biến" dưới). Deploy là sự kiện thưa, một lần đánh thức ≈ 0,02 CU-hr. Không có dòng ghi chú này, người sau sẽ thấy "readyz tốn query" rồi đổi sang `healthz` cho lành — và xoá đúng thứ khiến smoke test có ý nghĩa.

### 3. Hai món polish 007 + khung cron

**3.1 Hai món tồn từ `auth-brief.md` §6.2** (cố ý hoãn ở 007 để không đổi diff đã review):
- **`OAUTH_STATE_SECRET` thiếu thì phải kêu lên.** Hiện `app/main.py:44` lặng lẽ `secrets.token_urlsafe(32)` khi thiếu ⇒ mọi phiên OAuth chết sau mỗi lần restart machine mà không dấu vết nào. Cho fail-fast lúc khởi động khi ở production; local dev vẫn được chạy không cần nó (chỉ log cảnh báo).
- **`except Exception` trần ở `app/web/routers/auth.py:104`** — hiện "Google chết" và "có người đang dò" nhìn giống hệt nhau trong log. Bắt hẹp lại + log phân biệt. **Không đổi hành vi trả về:** mọi nhánh hỏng vẫn fail-closed và vẫn 303 sang `/auth/denied` (B3 của 007 — nhánh từ chối không được để `?code=` nằm lại URL).

*Vì sao gộp vào đây:* cả hai là guardrail lúc khởi động/deploy, mà **CD làm deploy nhanh hơn ⇒ deploy sai cũng nhanh hơn**. Đây đúng lúc chúng đáng giá nhất.

**📝 2026-07-22 (T1 review PR #13) — sinh ra biến `APP_ENV`. Mọi slice sau bắt chước chỗ này.**
Bản đầu suy ra "có phải production không" từ `SESSION_COOKIE_SECURE`. Chạy đúng, nhưng dựng một **sợi dây vô hình**: một ngày nào đó tắt `SESSION_COOKIE_SECURE` vì lý do riêng của nó sẽ tắt luôn một guard chẳng liên quan — đúng hình dạng sự cố Neon. Chốt: **`APP_ENV` là câu trả lời duy nhất cho "app đang chạy ở đâu"**, hỏi qua `settings.is_production`. **Guard nào phụ thuộc môi trường về sau — gửi mail thật, gọi LLM ở Bước 1, job backup — đều phải hỏi biến này, cấm suy ra từ setting hàng xóm.**

Hai tính chất cố ý, đừng "dọn dẹp" mất:
- **Mặc định trong code = `production`, VÀ `fly.toml [env]` vẫn ghi tường minh `APP_ENV = 'production'`.** Trùng lặp là cố ý, được cả hai mặt: đọc `fly.toml` là biết production đang chạy chế độ nào (không phải nhớ mặc định trong code), mà nếu dòng đó lỡ mất thì app **rơi về bản nghiêm hơn**. Không phải secret ⇒ để trong `fly.toml`, không dùng `flyctl secrets`. **Không tồn tại đường nào để *mất* một dòng mà production dễ dãi đi** — chỉ có đường *gõ thêm* `local` lên server, và đó là việc nhìn thấy được. *(📝 sửa cùng ngày: bản đầu cố ý bỏ trống trên Fly; chủ chỉ ra rằng ghi tường minh vẫn tốt hơn, và đúng — bỏ trống chỉ đổi lấy tính an toàn mà mặc định trong code đã cho sẵn.)*
- **Kiểu `Literal`, không phải `str`.** `APP_ENV=prod` là lỗi gõ mà nếu so chuỗi thường sẽ *âm thầm* thành "không phải production" rồi tắt guard. Pydantic chặn ngay lúc khởi động — chính là lý do có một câu trả lời tường minh.

Cả hai tính chất đều có test, và **cả hai test đã được chứng minh biết đỏ** (đổi mặc định sang `local` + nới `Literal` ⇒ 2 failed).

**3.2 `CRON_TOKEN` + khung cron.**
- Dependency FastAPI kiểm `Authorization: Bearer <CRON_TOKEN>`, so sánh bằng `secrets.compare_digest`. **Không** đi qua session user (`auth-brief.md` §5).
- Thiếu `CRON_TOKEN` lúc khởi động ⇒ endpoint cron trả **503**, không phải 401 và tuyệt đối không phải "cho qua". Một cổng không cấu hình phải **đóng và ồn ào**.
- **Đúng một** endpoint mẫu nhịp thưa + workflow cron gọi nó, để chứng minh đường dây chạy. Chọn cái rẻ nhất (vd `POST /api/cron/heartbeat` ghi 1 dòng log). **Chưa** viết backup/embed thật.
- Workflow cron lấy bearer từ `${{ secrets.CRON_TOKEN }}` — **bản GitHub phải khớp bản Fly**, vì nó gọi production. Bản trong `backend/.env` cố ý khác và chỉ dùng khi chạy local: `.env` nằm trên laptop (dễ `cat` nhầm, lọt thư mục sync, dán nhầm vào session agent) nên rò nó **không được** kéo theo quyền gọi cron production.

### 4. Cập nhật docs

- `docs/devops-brief.md`: **đã cập nhật sẵn 2026-07-22** (note có ngày ở §2.1 + §9) — **executor không sửa file này**, chỉ đọc.
- `backend/.env.example`: đánh dấu `CRON_TOKEN` ✅ trong bảng cấp phát; **thêm một dòng ⬜ cho khoá `age`** (private key mã hoá dump, `db-and-data-model-brief.md` §6). Bảng hiện không biết khoá đó tồn tại — hai file đúng, không tham chiếu nhau, đúng cái khe đã sinh ra sự cố Neon.
- `agent-tasks/README.md`: 008b → DONE; ghi rõ **nhắc thuốc đẩy sang 011** và **script soi hoá đơn đẩy sang 008c** (lý do ở mục "KHÔNG được làm").

## Bất biến bắt buộc mang theo

**Không job nền nào được poll DB với chu kỳ ngắn hơn cửa sổ idle 5 phút của Neon, trừ khi đã tính lại ngân sách CU-hr.** (`cost-brief.md` §7 — sự cố 22/07: một health check 30 giây chạy `SELECT 1` đã giữ Neon thức 24/7, 6 CU-hrs/ngày trên hạn mức 100/tháng, suýt mất DB 13 ngày giữa tháng.) Cron dựng ở chính task này đâm thẳng vào bức tường đó nếu quên.

## KHÔNG được làm

- **Không** đụng `/api/healthz`, **không** đổi `path` health check trong `fly.toml`. Đọc docstring `health.py` trước khi có ý tưởng nào ở khu vực này.
- **Không** làm nhắc thuốc. Cách ngây thơ là cron 5 phút/lần hỏi DB "tới giờ chưa" — nhịp tối thiểu của GitHub Actions cron **đúng bằng 5 phút**, bằng luôn cửa sổ idle Neon, và lịch GH Actions còn hay trễ ⇒ DB thức gần 24/7. Đó là **sự cố 22/07 mặc áo khác**. Lời giải (lịch tính trước thay vì poll / đẩy sang PWA notification, vướng caveat iOS ở `frontend-brief.md`) là **quyết định thiết kế chưa chốt** ⇒ thuộc **011**, không phải task hạ tầng.
- **Không** làm script soi hoá đơn Fly/Neon (`cost-brief.md` §7.4) — tách thành **008c**. Hạ tầng cron vẫn còn nguyên sau task này nên gộp vào chẳng lợi gì, chỉ làm PR phình gấp đôi và cần thêm 2 secret mới.
- **Không** dựng staging app / Neon branch. Đã cân và loại: +\$2,50/tháng và một branch ăn vào **storage — hạn mức liên tục không reset** (`cost-brief.md` §7.2).
- **Không** để `MICROSCHED_DEPLOY_TOKEN`, `CRON_TOKEN` (hay bất kỳ secret nào) đi qua `pull_request_target`, echo ra log, hay xuất hiện trong step summary.
- **Không** sửa `docs/*.md` ngoài mục 4. Kẹt/bí >2 vòng → DỪNG, escalate T1 kèm log lỗi.

## Acceptance (kiểm chứng được)

> **✅ Kết quả 2026-07-22 — cố ý KHÔNG tick hàng loạt, vì tick là xoá mất ranh giới "ai đã chạy cái gì":**
> **khối A + A′** = executor chạy và báo cáo, bằng chứng nằm trong PR [#13](https://github.com/NguyenHaiHung0510/microSched/pull/13) (docker build với SHA thật, curl cron 401/401/200/503, ba kịch bản OAuth trên Chrome thật, 43 test, actionlint, 5/5 check).
> **khối B** = T1 kiểm trực tiếp sau merge, số liệu ở dòng Trạng thái đầu file — **trừ cron production, chưa chạy được**, xem mục "⚠️ Sót lại" cuối file.

**Chia làm hai khối có chủ ý.** Workflow CD **chưa tồn tại trên `develop`** cho tới khi PR này được merge, nên executor **không thể** chứng minh nó chạy. Đó là giới hạn thật của task, không phải cớ — điều bắt buộc là **nói đúng mình đứng ở khối nào**, đừng để một mục ở khối B được viết như thể đã chạy.

### A. Executor PHẢI chạy trước khi mở PR

- [ ] **Docker local, chứng minh đường SHA thông suốt:** `docker build --build-arg GIT_SHA=<sha thật>` → `docker run` → `curl /api/readyz` trả đúng `commit` = SHA đó. Đây là mảnh mới rủi ro nhất của task, và nó **kiểm được trọn vẹn ở local** — không có lý do gì để nó nằm ở khối B.
- [ ] `curl /api/healthz` trên chính container đó: vẫn đúng `{"status":"ok","version":"..."}`, **không** có key `db`, **không** có key `commit`.
- [ ] `POST /api/cron/heartbeat` không bearer → **401**; sai bearer → **401**; đúng `CRON_TOKEN` → **200**. Chạy thật bằng `curl`, không chỉ bằng unit test.
- [ ] Thiếu `CRON_TOKEN` lúc khởi động → endpoint cron trả **503**, không phải 401 và tuyệt đối không phải cho qua.
- [ ] Thiếu `OAUTH_STATE_SECRET` ở production-mode → app **từ chối khởi động**, log nói rõ biến nào thiếu. Ở dev-mode vẫn chạy được.
- [ ] YAML hợp lệ (`actionlint` hoặc tương đương); `pytest`, `ruff`, `pre-commit run --all-files` sạch; 5 required check xanh trên PR.

### A′. Cần TRÌNH DUYỆT — vẫn là việc của executor, nhưng đọc luật profile trước

Executor lái được Chrome (kiểm chứng 2026-07-22). **Đọc `AGENTS.md` mục "Lái trình duyệt" trước khi mở tab đầu tiên** — đó là profile thật của chủ, không phải môi trường test. Tài khoản được phép dùng nêu trong prompt giao việc; **không tự chọn tài khoản.**

Mục 3.1 sửa đúng đoạn xử lý lỗi ở callback OAuth, tức chạm vào chỗ đã sinh ra lỗi B3 của 007 ⇒ phải kiểm lại bằng mắt, không giả định:

- [ ] **Nhánh hợp lệ** (tài khoản trong allowlist): đăng nhập vào được, dashboard hiện phiên.
- [ ] **Nhánh bị chặn bởi allowlist** (tài khoản là Google test-user nhưng ngoài allowlist): 303 sang `/auth/denied`, **`?code=` KHÔNG nằm lại trên thanh địa chỉ, cũng không nằm lại trong history**.
- [ ] **Nhánh ngoài cả hai** (không test-user, không allowlist): cũng dừng sạch, không lộ gì trên URL.
- [ ] Đăng xuất sạch, đóng tab.

### B. Chỉ chứng minh được SAU merge — ghi vào PR là "chưa chạy", chủ + T1 nghiệm thu

- [ ] Workflow chạy thật → `https://microsched.fly.dev/api/readyz` trả `status: "ok"` **và** `commit` khớp SHA vừa merge. Dán JSON thật.
- [ ] **Smoke test biết fail:** sửa tạm cho so SHA với giá trị sai → job **đỏ**. Hoàn lại. *(Một smoke test chưa từng đỏ là một smoke test chưa từng được kiểm.)*
- [ ] Step summary in đúng dòng độ tụt `main`.
- [ ] Workflow cron gọi được endpoint production ít nhất một lần thật (bearer = bản GitHub, phải khớp bản Fly).
- [ ] *(trình duyệt)* Đăng nhập Google thật trên `microsched.fly.dev` vẫn chạy sau khi deploy.
- [ ] **Chưa cần chứng minh:** deploy từ tag qua `workflow_dispatch` (đường phụ, roll-forward là đường chính).

## Báo cáo

Theo quy ước `agent-tasks/README.md` §"Quy ước BÁO CÁO": tách rõ **Đã chạy** / **CHƯA chạy** / **Vì sao vẫn tin là đúng (lập luận, không phải bằng chứng)**. Task này đụng bản build production và đường auth ⇒ phần "đã chạy" **phải** có thao tác trên trình duyệt thật, không chỉ CI xanh.

## Bàn giao

Branch **`feat/008b-cd-fly-deploy`** → PR nhỏ vào `develop`, kèm output verify. Người merge = chủ sau khi T1 review diff. Commit message tiếng Việt *tại sao*, kèm `Co-Authored-By:` của agent thực thi.

⚠️ **Lưu ý riêng của task này:** merge PR này vào `develop` **chính là** lần deploy tự động đầu tiên. Đọc lại mục 1.1–1.2 trước khi bấm merge.

---

## ⚠️ Sót lại sau nghiệm thu (2026-07-22) — `workflow_dispatch` chưa tồn tại

`gh workflow run cron.yml --ref develop` trả **`HTTP 404: workflow not found on the default branch`**. GitHub chỉ mở `workflow_dispatch` khi file workflow **đã có mặt trên default branch** (`main`) — mà `main` chưa nhận 008b. Không ai biết luật này trước khi va vào.

Hai hệ quả, cả hai đều là *chưa chạy*, không phải *hỏng*:

1. **Cron production chưa được gọi lần nào.** Bằng chứng đầu tiên sẽ là lần chạy theo lịch: **03:17 UTC = 10:17 giờ VN**. Kiểm bằng `gh run list --workflow=cron.yml`; endpoint phải trả 200 và **không** đánh thức Neon (heartbeat cố ý không chạm DB).
2. **`workflow_dispatch` của `deploy.yml` — đường lùi phụ — cũng chưa tồn tại.** Không phá gì: đường lùi chính vẫn là **roll-forward** (`git revert` trên `develop` → CD chạy), và đó là đường được đi mỗi ngày nên luôn hoạt động. Nhưng giờ nó là *đường lùi duy nhất đang sống*, và đó là sự thật đã kiểm chứ không phải giả định. Cả hai `workflow_dispatch` tự sống lại ở lần merge `develop` → `main` kế tiếp.

**Bài học đáng mang đi:** một cơ chế **có mặt trong code** vẫn có thể **chưa hoạt động** vì một luật nằm ở hệ thống khác (ở đây là quy tắc default-branch của GitHub). Cùng họ với sự cố Neon — chỗ hỏng nằm giữa hai thứ đều đúng, ở hai nơi không tham chiếu nhau. ⇒ Với mọi "đường thoát hiểm" dựng thêm: **hỏi ngay nó đã dùng được chưa, đừng chờ tới lúc cần**.
