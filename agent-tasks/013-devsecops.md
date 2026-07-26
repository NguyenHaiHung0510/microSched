# 013 — DevSecOps: đưa kiểm tra bảo mật vào CI

> Executor: T2 Codex (`gpt-5.6-sol`, `--write`) hoặc Agent-Opus · Bậc: L2 · Effort: medium · **Skill gợi ý:** không cần · **MCP cần:** không cần

**Trạng thái:** ✅ CHỐT v2 — chủ duyệt 2026-07-26. Viết 2026-07-26, fold hai lượt phản biện + đo tay cùng ngày.

---

## 📝 2026-07-26 — v2: cái gì đổi và VÌ SAO

Bản v1 đúng ở giả thuyết trung tâm nhưng **nghi thức nghiệm thu của nó không chạy được**. Hai lượt phản biện khác câu hỏi (T3: *"spec sai ở đâu"*, T2: *"spec không làm được ở đâu"*) + T1 đo tay đã đổi 5 chỗ:

1. **Giả thuyết Việc 1 = ĐÚNG, đã đo, không còn là giả thuyết.** Hook là `gitleaks git --pre-commit --redact --staged --verbose` (`pass_filenames: false`). Đo: khoá giả **chưa staged** ⇒ `Passed`, `0 commits scanned`; **đã staged** ⇒ `Failed` exit 1. CI không stage gì ⇒ **lớp gitleaks trong CI đang quét 0 file rồi báo xanh**.
2. 🔒 **Spec v1 bỏ sót `.gitleaks.toml`.** Repo có 2 rule riêng do 008d thêm (`microsched-db-connection-string`, `microsched-db-env-var-value` — che `NEON_OWNER_URL`/`NEON_MIGRATOR_URL`/`ENCRYPTION_MASTER_KEY`/`CRON_TOKEN`/`OAUTH_STATE_SECRET`). **Hai rule đó cũng chưa từng chạy trong CI.** Ta tưởng 008d đã bịt lỗ; thực tế nó chỉ bịt ở hook máy local.
3. **Acceptance v1 tự mâu thuẫn** (T2 bắt): dòng cũ *"xoá file secret giả trước khi commit"* chọi trực tiếp yêu cầu *"dán output CI đỏ"* — lỗi xoá trước khi commit thì không bao giờ tới CI. Và **Dependabot không sinh CI status check nào**, nên nghi thức đỏ/xanh **không áp được** cho Việc 2. Acceptance nay tách theo từng việc.
4. **Push protection ĐANG BẬT** (T3 bắt; T1 xác minh bằng `gh api`: `secret_scanning_push_protection: enabled`, repo public). Dùng khoá `AKIA…` giả sẽ **bị chặn lúc push** và để lại alert vĩnh viễn trong Security dashboard. **Đường vòng đã đo:** `secret_scanning_non_provider_patterns` đang **tắt** ⇒ dùng **connection string giả** thì GitHub im lặng, còn rule riêng của dự án vẫn nổ (thử thật: cả 2 rule 008d đều bắt). Fixture đổi sang dạng đó — vừa hợp lệ, vừa chứng minh luôn phần 008d.
5. **CodeQL `schedule:` weekly sẽ KHÔNG BAO GIỜ chạy** (T1 bắt). Default branch là `main`; `git ls-tree origin/main .github/workflows/` chỉ có `ci.yml`. **Đây đúng bug đã giết `cron.yml` hồi 23/07** — spec v1 đang dựng lại nó. ⇒ **chủ quyết 26/07: bỏ hẳn `schedule:`**, chỉ `pull_request` + push `develop`.

**Sửa nhỏ, đều đã tra nguồn sống:** `package-ecosystem` phải là **`uv`** (Dependabot có ecosystem riêng cho `uv.lock`; `pip` không đọc `uv.lock`) ⇒ **nhánh dự phòng `pip-audit` của v1 bị bỏ, không cần nữa** · `gitleaks detect` **deprecated từ v8.19.0** → dùng `gitleaks dir` · CodeQL cần `permissions: security-events: write` nếu không SARIF upload ra 403.

**Một mục T3 nêu đã BÁC:** nó cảnh báo Python 3.14 phá CodeQL extractor và gắn nhãn OBSERVED — sai, CodeQL 2.24.0 (01/2026) đã hỗ trợ tính năng 3.14, 2.25.3 hỗ trợ cú pháp 3.15. Giữ nguyên luật cũ: **agy là cố vấn, T1 kiểm tay từng mục.**

**Quan sát phụ, không thuộc phạm vi task nhưng phải ghi:** ruleset `protect-develop` có **0 required status check** — đường merge thật (PR vào `develop`, và merge `develop` = deploy production) hiện không bị check nào chặn cứng; 5 check kia gác `main`, nhánh không deploy. **Chủ quyết 26/07:** job `secret-scan` mới **sẽ thành required check trên CẢ `protect-develop` và `protect-main`** — nhưng **chỉ siết SAU khi job đã tồn tại trên `develop` và chạy xanh ít nhất 1 lần**, vì thêm required check trỏ vào một job chưa tồn tại sẽ **kẹt vĩnh viễn mọi PR**.

---

## Bối cảnh (đọc trước khi làm bất cứ gì)

microSched là **dự án một người**, repo **public by deliberate choice**, threat model ghi ở `docs/devops-brief.md` §1 là **social engineering** — không phải tấn công diện rộng, không phải bot quét lỗ hổng.

⚠️ **Đây là ràng buộc quan trọng nhất của task này: đừng dựng stack DevSecOps doanh nghiệp.** Mỗi job thêm vào CI là thời gian chờ trên mọi PR, và một job không ai đọc kết quả thì tệ hơn không có — nó dạy người ta bỏ qua bảng CI. Chọn theo tỷ lệ công/lợi, và **nói không** với những thứ ở mục "Cố ý KHÔNG làm" bên dưới.

Deploy tự động: merge vào `develop` ⇒ build ⇒ Fly.io. `main` **không** deploy (chỉ là nhãn release). Xem `docs/devops-brief.md` §2.1.

## Hiện trạng — đã đo bằng file, không phải suy đoán

`.github/workflows/ci.yml` có 5 job, chạy trên mọi `pull_request` và mọi push vào `develop`:

| Job | Làm gì |
|---|---|
| `backend` | `ruff check` + `ruff format --check` + `pytest -m "not pg"` |
| `runtime-deps` | `uv sync --no-dev` rồi `create_app()` — chặn lỗi "test xanh nhưng image production không boot" |
| `hooks` | `pre-commit run --all-files` |
| `frontend` | `npm run lint` + `npm test` + `npm run build` |
| `migration-qa` | Postgres `pgvector:pg18` thật → upgrade → kiểm drift → downgrade base → upgrade → `pytest -m pg` |

`.pre-commit-config.yaml` có: `check-added-large-files`, `end-of-file-fixer`, `trailing-whitespace`, `check-merge-conflict`, `check-yaml`, `detect-private-key`, và **gitleaks v8.30.1**.

**`.gitleaks.toml` (gốc repo) — v1 bỏ sót file này, nó quan trọng:** `extend.useDefault = true` + **2 rule riêng** thêm bởi 008d — `microsched-db-connection-string` (URI DB có credential trông thật) và `microsched-db-env-var-value` (che `DATABASE_URL`, `PGPASSWORD`, `NEON_OWNER_URL`, `NEON_MIGRATOR_URL`, `ENCRYPTION_MASTER_KEY`, `CRON_TOKEN`, `OAUTH_STATE_SECRET`). Mọi lệnh gitleaks trong CI **phải nạp file này**.

`.github/workflows/deploy.yml` có smoke test khẳng định **SHA đã deploy khớp SHA vừa build** — không dừng ở `status: ok`.

**Thiếu (đã kiểm, file không tồn tại):**
- `.github/dependabot.yml` — không có
- workflow CodeQL / SAST nào — không có
- `pip-audit` / `npm audit` / OSV — không có
- quét container image — không có

---

## Việc 1 — Dựng lớp secret-scan THẬT trong CI *(làm trước tiên, ưu tiên cao nhất)*

**Không còn là giả thuyết — T1 đã đo 2026-07-26, kết quả ở §v2 mục 1.** Lớp gitleaks trong CI hiện quét 0 file và báo xanh. Đây đúng lớp lỗi đã gặp 4 lần với `shadcn add` (`docs/ui-brief.md` §8) và 1 lần với `resize_window`: **công cụ báo thành công khi không làm gì cả.** Executor **không cần đo lại** bước này.

**Thi công — thêm một job MỚI tên `secret-scan` vào `.github/workflows/ci.yml`.**

🔒 Đây là chỗ v1 tự mâu thuẫn (dòng cũ đề xuất sửa job `hooks`, trong khi §"Cố ý KHÔNG làm" cấm sửa 5 job hiện tại). **Phán quyết: job MỚI, không đụng job `hooks`.** Lý do thực chất, không phải hình thức: hook `pre-commit` và quét CI có **ngữ nghĩa khác nhau** (hook đọc staged index, CI đọc cây làm việc) — nhét chung một job thì lần sau sẽ có người tưởng chúng là một thứ, đúng cái nhầm đã tạo ra lỗ này.

```yaml
  secret-scan:
    name: Secret scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITLEAKS_CONFIG: .gitleaks.toml
```
Hoặc, nếu action đòi license/telemetry ngoài ý muốn, dùng thẳng binary — **executor chọn một, ghi rõ đã chọn cái nào và vì sao**:
```
gitleaks dir . --config .gitleaks.toml --redact --exit-code 1
```

**Ba điểm bắt buộc đúng, mỗi điểm là một cách hỏng im lặng:**
- **`dir`, KHÔNG phải `detect`.** `detect` deprecated từ v8.19.0. `dir` quét **cây làm việc** — đúng thứ ta cần, và **không phụ thuộc `fetch-depth`**. (Nếu ai đó đổi sang `gitleaks git` thì `actions/checkout@v4` mặc định `fetch-depth: 1` sẽ chỉ soi đúng 1 commit — quét lịch sử hụt mà vẫn xanh.)
- **Phải nạp `.gitleaks.toml`.** Không nạp = mất 2 rule 008d = mất đúng phần che `NEON_OWNER_URL` / `ENCRYPTION_MASTER_KEY` / `CRON_TOKEN`. Nghiệm thu phải chứng minh rule **riêng** nổ, không chỉ rule mặc định.
- **Giữ nguyên hook pre-commit.** Hai lớp, hai mục đích: hook chặn trước khi commit; CI chặn thứ đã lọt qua `--no-verify` hoặc từ máy chưa chạy `pre-commit install`.

**Sau khi job xanh trên `develop`:** báo T1 để thêm `Secret scan` vào required checks của **cả** `protect-develop` và `protect-main` (chủ đã duyệt; thứ tự bắt buộc — xem §v2 cuối).

## Việc 2 — Bật Dependabot

Bắt được thứ review tay **không bao giờ** bắt được: CVE trong dependency. Đây là loại lỗ hổng không nằm trong code ta viết.

Hai phần **tách biệt, đừng nhầm**:
- **Alerts** (cảnh báo CVE) = bật trong repo Settings → Code security. **Không cần file nào.** → việc của chủ. T1 đã kiểm 26/07: `gh api repos/:owner/:repo/vulnerability-alerts` trả **404** và `dependabot_security_updates: disabled` ⇒ **đang TẮT thật**, không phải phỏng đoán.
- **Version updates** (tự mở PR nâng version) = cần `.github/dependabot.yml`:
  - 2 ecosystem: **`uv`** cho `/backend`, `npm` cho `/frontend`
  - `schedule: weekly` (không phải `daily` — dự án một người, PR hằng ngày là nhiễu)
  - `open-pull-requests-limit: 3` mỗi ecosystem

✅ **Đã tra nguồn sống 2026-07-26 (T1), không cần executor tra lại:** Dependabot **có ecosystem riêng `uv`** cho `uv.lock`. Dùng `pip` cho `/backend` là **SAI và im lặng** — `pip` chỉ đọc `requirements.txt`/`setup.py`/`Pipfile`, gặp `uv.lock` thì bỏ qua, để lại một file config nằm đó không làm gì. ⇒ **Nhánh dự phòng `pip-audit` của v1 đã BỎ**, không cần nữa.

Cả `backend/uv.lock` và `frontend/package-lock.json` đều đã xác nhận tồn tại.

## Việc 3 — CodeQL

Free cho public repo. Thêm `.github/workflows/codeql.yml`:
- ngôn ngữ: `python` và `javascript-typescript` (đúng identifier hiện hành)
- trigger: **`pull_request` + push `develop`. KHÔNG có `schedule:`** — chủ quyết 26/07.
- **bắt buộc có khối `permissions`**, thiếu là SARIF upload ra 403:
```yaml
permissions:
  security-events: write
  contents: read
  actions: read
```

🔒 **Vì sao bỏ `schedule:` — đọc kỹ, đây là bug đã xảy ra một lần rồi.** GitHub chỉ đọc `schedule:` từ **default branch**. Default branch của repo này là **`main`**, và trên `main` hiện chỉ có `ci.yml`. Một `codeql.yml` land vào `develop` sẽ có `schedule:` **không bao giờ kích hoạt** — im lặng, không lỗi, không cảnh báo. Đây **đúng** cơ chế đã giết `cron.yml` (`CLAUDE.md`, 23/07). Và kể cả đưa lên `main` cũng chết đường dài: GitHub tắt scheduled workflow sau 60 ngày không commit trên default branch, mà `devops-brief.md` §2.1 **thiết kế `main` để im lặng**.

**Giá trị chính KHÔNG phải bắt lỗi logic** — T1 đã đọc tay toàn bộ `backend/app/**` trong phiên security review 2026-07-23 và không tìm thấy lỗ hổng leo thang quyền hay rò dữ liệu. Giá trị là nó **chạy mọi lần push mà không phụ thuộc vào việc ai đó nhớ làm**. Review thủ công là kỷ luật con người; kỷ luật con người hỏng đúng vào tuần bận nhất.

Đặt CodeQL là **required check** hay không → để chủ quyết sau khi thấy nó chạy 1-2 tuần, đừng tự bật.

---

## Cố ý KHÔNG làm

Ghi rõ để executor không tự nới phạm vi:

- **Container image scan** (Trivy/Grype) — image chạy đúng một process Python, bề mặt nhỏ, không đáng một job trên mọi PR.
- **DAST / OWASP ZAP** — app một người dùng, nằm sau OAuth allowlist. Không có bề mặt công khai để quét.
- **SBOM / artifact signing** — chưa có consumer nào của artifact ngoài chính Fly.
- **Đổi ngưỡng hay tắt bớt job CI đang có** — task này chỉ THÊM, không sửa 5 job hiện tại. *(📝 v2: dòng này từng chọi với đề xuất "thêm step vào job `hooks`" ở Việc 1. Đã xử: Việc 1 dựng **job mới** `secret-scan`, không đụng `hooks`. Luật này giữ nguyên hiệu lực.)*
- **Chạm vào `deploy.yml`** — smoke test ở đó đang đúng, đừng đụng.
- **Tự đổi ruleset / required checks** — executor **không** chạm repo settings. Job xanh rồi thì báo T1, T1 siết (chủ đã duyệt nội dung, nhưng thao tác là của T1).
- **Dùng khoá `AKIA…` hay bất kỳ provider pattern nào làm fixture** — push protection sẽ chặn và để lại alert vĩnh viễn. Xem §Acceptance Việc 1.

## Việc của CHỦ

- [ ] Bật **Dependabot alerts** trong repo Settings → Code security (agent không có quyền đổi repo settings). T1 đã xác nhận đang TẮT.
- [x] ~~Xác nhận có muốn CodeQL không~~ → **chốt 26/07: có, nhưng bỏ `schedule:`**
- [ ] *(sau khi job xanh)* siết `Secret scan` thành required check trên `protect-develop` + `protect-main`

## Acceptance — nguyên tắc giữ nguyên, nghi thức TÁCH THEO TỪNG VIỆC

Nguyên tắc không đổi:

> **Một job bảo mật chưa bao giờ đỏ là một job chưa được chứng minh là đang chạy.**

🔒 **Nhưng v1 áp một nghi thức chung cho cả 3 việc, và điều đó không chạy được** (T2 bắt). Hai lý do, cả hai đều cứng:
- v1 vừa đòi *"dán output CI đỏ"* vừa bảo *"xoá file secret giả **trước khi commit**"*. Lỗi xoá trước khi commit **không bao giờ tới CI** ⇒ không tồn tại run đỏ để dán.
- **Dependabot không sinh CI status check nào.** Alerts và version-update PR không phải job ⇒ không có gì để đỏ.

### Việc 1 — CÓ nghi thức đỏ/xanh đầy đủ (bắt buộc)

Trên nhánh `feat/013-devsecops`, làm **đúng** thứ tự này, mỗi bước là một commit được **push thật**:

1. Commit một file `tests/fixtures/fake_leak.txt` chứa **connection string giả** đúng dạng:
   ```
   NEON_OWNER_URL=postgresql://neonuser:<PW>@ep-fake-demo.aws.neon.tech/microsched
   ```
   trong đó `<PW>` = một chuỗi ngẫu nhiên **≥8 ký tự chữ-và-số, phải có ít nhất 1 chữ số** (rule đòi "password trông thật" mới nổ — xem chú thích trong `.gitleaks.toml`). Ví dụ dạng `Ab3xKm9qZ`.

   🔒 **Spec này cố ý KHÔNG chứa chuỗi hoàn chỉnh.** Lý do đo được: bản nháp đầu của spec v2 có nguyên văn chuỗi đầy đủ và **hook gitleaks chặn luôn commit của chính spec** (2 finding, đúng 2 rule 008d). Vui vì nó chứng minh hook sống, nhưng bài học là: **đừng đặt fixture hoàn chỉnh vào tài liệu được commit** — chỗ duy nhất chuỗi đầy đủ được phép tồn tại là file fixture tạm ở bước 1, và nó bị xoá ở bước 3.
   ⚠️ **KHÔNG dùng khoá `AKIA…`.** Push protection đang bật ⇒ khoá AWS giả bị **chặn ngay lúc push** và để lại alert vĩnh viễn trong Security dashboard của một repo public. Chuỗi trên thì `non_provider_patterns` đang tắt nên GitHub im lặng, còn rule riêng của dự án vẫn nổ. **T1 đã thử thật: cả `microsched-db-connection-string` lẫn `microsched-db-env-var-value` đều bắt.**
   ⚠️ Giá trị trên là **giả hoàn toàn** — không phải secret thật, không phải biến thật của bất kỳ môi trường nào.
2. Đợi CI. Lưu link + output job `Secret scan` **ĐỎ**. Phải thấy `RuleID` là rule **riêng** của dự án (chứng minh `.gitleaks.toml` đã được nạp), không chỉ `generic-api-key`.
3. Commit tiếp: **xoá** file fixture.
4. Đợi CI. Lưu link + output **XANH**.
5. Cả hai run đều nằm trong lịch sử PR ⇒ bằng chứng sống sót sau khi fault đã bị gỡ. **Không squash** khi merge, hoặc nếu squash thì dán link run vào PR description trước.

### Việc 2 — KHÔNG có nghi thức đỏ. Bằng chứng sống là thứ khác

Dependabot không tạo CI check. Bằng chứng chấp nhận được, theo thứ tự ưu tiên:
1. **Dependabot thật sự mở được PR** (mạnh nhất), hoặc
2. Insights → Dependency graph → **Dependabot** tab hiển thị **cả hai** ecosystem với "last checked" gần đây và **không có lỗi parse config**.

❌ **Không chấp nhận** "đã thêm `dependabot.yml`, YAML hợp lệ". YAML hợp lệ mà sai `package-ecosystem` thì **im lặng không làm gì** — đó chính là cái bẫy `pip`-vs-`uv` ở Việc 2.

### Việc 3 — nghi thức đỏ ở mức nhẹ

CodeQL chạy được và **báo cáo lên Security tab** là đủ cho lần đầu. Nếu muốn chứng minh nó bắt được: cắm tạm một pattern CodeQL chắc chắn bắt (ví dụ một chuỗi nối thẳng vào câu SQL trong một file test tạm), xem alert hiện ra, rồi gỡ. **Không bắt buộc** — nhưng nếu bỏ qua thì **ghi thẳng vào PR là đã bỏ qua**, đừng để trống.

---

Báo cáo tách rõ **đã chạy** và **chỉ suy luận** theo quy ước ở `agent-tasks/README.md` §"Quy ước BÁO CÁO".

Không chấp nhận: "đã thêm workflow, CI xanh". CI xanh chứng minh workflow chạy được, **không** chứng minh nó phát hiện được gì.
