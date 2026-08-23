# Task 025 QA — independent review cho local production-image QA cell

> **Trạng thái: ✅ QA SPEC APPROVED 2026-08-24.**
> Reviewer độc lập với implementer; chạy trên worktree riêng của candidate PR, không production
> access, không secret thật, không merge. Physical iPhone là receipt riêng và được phép `NOT RUN`.

## 0. Verdict đang được kiểm

QA này chỉ trả lời: **cell có dùng production image candidate trong một biên local disposable
fail-closed hay không**. Nó không chứng minh production deployment, real Google OAuth, Safari,
physical iPhone hoặc outbox 017.

Ba nhãn phải tách:

- `CELL = PASS | FAIL | BLOCKED`;
- `PHYSICAL_IPHONE = PASS | FAIL | NOT RUN`;
- `RELEASE_V1 = ELIGIBLE | ELIGIBLE_WITH_DEVICE_GAP | BLOCKED`.

Owner đã duyệt: `CELL=PASS` + `PHYSICAL_IPHONE=NOT RUN` cho phép
`RELEASE_V1=ELIGIBLE_WITH_DEVICE_GAP`. Không được viết `iPhone PASS`. Nếu physical run ra `FAIL`,
release là `BLOCKED` cho tới khi xử lý/owner quyết định khác.

## 1. Boundary của reviewer

- Chỉ dùng local Docker daemon + candidate worktree. Không mở `microsched.fly.dev`, Fly dashboard,
  Neon, host Postgres, `.env`, Google OAuth, Chrome profile thật hoặc dữ liệu thật.
- Không export/read giá trị các biến bị cấm. Nếu chúng đã tồn tại trong shell, reviewer dùng một
  shell sạch hoặc chỉ chạy negative guard test; report tên biến, không report giá trị.
- Không bật Docker Desktop thay owner; nếu daemon tắt, trả `BLOCKED_PREREQUISITE` với raw error.
- Không tự sửa candidate để “làm xanh”. Mutation proof chỉ là thay đổi tạm, restore ngay, rồi xác
  nhận `git diff` trở lại đúng candidate.
- Không chạy task 017, không copy WIP branch 017, không đổi acceptance A01–A20.

## 2. Prerequisite receipts

Chạy từ repo root, lưu raw stdout/stderr + exit code:

```text
git rev-parse HEAD
git status --short
docker version
docker compose version
python --version
```

`docker --version` một mình không đủ; `docker version` phải thấy daemon. Candidate worktree phải
clean trước full run, trừ artifact ignored trong `frontend/test-results/`.

## 3. Acceptance độc lập

### Q025-A01 — scope và candidate identity

- Diff Phase A chỉ chạm allowlist §3 của implementation spec; diff Phase B chỉ thêm CI placement đã
  nêu. Không app source, root `Dockerfile`, `fly.toml`, deploy workflow, Alembic revision hoặc 017.
- Production app image dùng root `Dockerfile` không sửa và full candidate SHA. Receipt `image_id`
  tồn tại; `/api/readyz` có `status=ok`, `db=up`, `commit=<HEAD>`.

### Q025-A02 — guard từ chối trước side effect

- Với từng biến/target forbidden, CLI trả exit 40 + `GUARD_DENIED`.
- Chụp inventory trước/sau bằng exact project label; cả hai là 0 container/network/volume.
- Không tồn tại `--force`, `--allow-production`, `--remote`, `--base-url` hoặc fallback prompt.

### Q025-A03 — không ambient config/secret

- Unit test dùng temp directory chứa `.env` với canary vô hại; rendered config không chứa canary.
- `COMPOSE_DISABLE_ENV_FILE=1`, không `env_file`, secret không nằm trong argv/log/receipt.
- Chạy receipt-schema negative test với token/PIN/DB URL canary: validator phải từ chối.
- `gitleaks`/pre-commit pass trên candidate; không dán literal runtime secret vào PR.

### Q025-A04 — network và resource isolation

- DB và app `Ports` rỗng; Compose network `Internal=true`; browser-runner cũng chỉ nối network đó.
- Reverse proxy trong browser container chỉ bind `127.0.0.1:<ephemeral>` và chỉ có upstream tĩnh
  `app:8000`. Không host/LAN bind, host network, privileged, Docker socket hoặc unrelated resource.
- Browser request ledger chỉ có exact runner-loopback origin; attempted other origin bị abort + fail.
- Sau pass, fail, SIGINT và timeout: inventory exact project về 0.

### Q025-A05 — app/migrator split

- `current_user` app là `microsched_app`; schema/table owner là `microsched_migrator`.
- App role DML pass nhưng DDL và `alembic_version` write bị permission denied.
- App container không nhận owner/migrator secret; migrate container exit trước app.
- App startup command không gọi Alembic; migration chỉ chạy one-shot trên throwaway PG.

### Q025-A06 — auth/PIN không bypass

- Không cookie ⇒ 401; cookie synthetic với digest row thật ⇒ `/api/me` 200 đúng email
  `example.invalid`; logout ⇒ lại 401.
- PIN được đặt/unlock/lock qua protected API thật. Không route/header/query param `qa`, `test-auth`,
  impersonation hoặc fake OAuth callback trong app/OpenAPI.
- Google env vắng; request ledger không có Google host; không browser/account/profile thật.

### Q025-A07 — synthetic data qua real stack

- Đúng 2 task (1 public, 1 private), task items và 1 note mang prefix run; không mock route.
- Private create khi lock trả 403 không lộ title; unlock thì private hiện; lock lại thì private mất,
  public task/note còn.
- Toàn DB bị huỷ; không giữ shared QA user/PIN/data giữa hai run.

### Q025-A08 — browser + Service Worker boundary

- Browser-runner image dùng Node 24 + Playwright version khóa trong `frontend/package-lock.json`,
  bundled Chromium, `browser.newContext`, `serviceWorkers: 'allow'` và close cuối run.
- Không `channel: chrome`, persistent context, `userDataDir`, real `storageState`/cookie export.
- Service Worker controller pass sau reload trên loopback. Receipt chỉ ghi PWA shell; không ghi
  “offline outbox pass”.

### Q025-A09 — recurring/outbound/deploy bị chặn

- Effective app config có `APP_ENV=local`, `ENABLE_INPROCESS_CRON=false`; Google/VAPID/Fly env vắng.
- No outbound requests, không `fly` command, không deploy workflow invocation, không production
  migration. Static diff không sửa production configuration để phục vụ QA.

### Q025-A10 — timeout/cleanup taxonomy

- Fake/subprocess seams sinh đúng `SETUP_TIMEOUT`, `TEST_TIMEOUT`, `CLEANUP_TIMEOUT`.
- Timeout sau partial setup vẫn inventory rồi cleanup; timeout không được báo “chưa tạo gì”.
- Browser pass + cleanup fail ⇒ final nonzero/`CLEANUP_TIMEOUT`.
- Receipt PASS chỉ khi containers/networks/volumes/helper-processes đều 0.

### Q025-A11 — receipt integrity

- Receipt validate `microsched.qa025.receipt.v1`, đủ SHA/image/phases/durations/safety/roles/fixture/
  acceptance/cleanup/device fields.
- Receipt không secret, DB URL, real email, production host, env/container dump. Timestamps UTC và
  `ended_at >= started_at`.
- Raw command log phân biệt rõ `RUN`, `PASS`, `FAIL`, `NOT RUN`; không suy pass từ exit 0 đơn lẻ.

### Q025-A12 — RED→GREEN mutation proof

- Chạy toàn bộ persistent negative tests.
- Chạy ít nhất các mutation **M01, M03, M05, M07, M09, M10, M12** dưới đây; mỗi mutation phải làm
  đúng named test đỏ vì guard bị phá, restore rồi cùng test xanh.
- Không commit mutant; sau restore, `git diff --exit-code` so với candidate patch/snapshot pass.

### Q025-A13 — CI placement/named checks (chỉ Phase B)

- Workflow vẫn tên `CI`, trigger mọi PR/push `develop`, không path-filter làm check biến mất.
- Existing job names vẫn chứa nguyên văn:
  `Backend checks`, `Production dependency check`, `Repository hooks`, `Secret scan`,
  `Frontend checks`, `Frontend e2e`, `Migration QA`.
- Job mới đúng `Local production-image QA cell`, `permissions: contents: read`, timeout ≤25 phút,
  không secret/environment/deploy. Nó informational/non-required; không ruleset mutation trong PR.
- CI receipt phải đến từ commit của PR; local pass không thay thế CI.

### Q025-A14 — ranh giới 017 và iPhone

- Không file/diff/claim từ task 017. Foundation receipt ghi 017 `NOT APPLICABLE` khi code chưa có.
- Nếu adapter 017 được review ở Phase C sau này, vẫn dùng toàn bộ QA spec 017; 025 không pass A01–A20.
- Physical iPhone sub-receipt hiện diện với `PASS`, `FAIL` hoặc `NOT RUN`; Chromium 390×844 không
  được dùng làm device receipt.

## 4. Mutation matrix bắt buộc

Mutation chỉ diễn ra trong reviewer worktree. Không thêm runtime bypass flag để hỗ trợ mutation.

| ID | Thay đổi tạm cần làm | Named test phải ĐỎ | Guard/acceptance |
|---|---|---|---|
| M01 | Bỏ `DATABASE_URL` khỏi deny-set | remote env không bị chặn trước Docker | A02 / 025-SAFE-01 |
| M02 | Cho parser nhận base URL khác loopback | production/remote URL được nhận | A02 / 025-SAFE-01 |
| M03 | Publish app ra host hoặc đổi proxy bind thành `0.0.0.0` | rendered config/network test | A04 / 025-SAFE-03 |
| M04 | Publish `db:5432` ra host | zero-DB-port assertion | A04 / 025-SAFE-03 |
| M05 | Đưa migrator URL/secret vào app service | effective-env role separation test | A05 / 025-SAFE-04 |
| M06 | Grant CREATE schema cho app | negative DDL assertion | A05 / 025-SAFE-04 |
| M07 | Đặt `ENABLE_INPROCESS_CRON=true` | effective-config/outbound guard | A09 / 025-SAFE-06 |
| M08 | Cho synthetic OpenAPI fixture có `/api/qa/session` | no-auth-bypass contract | A06 / 025-SAFE-05 |
| M09 | Dùng `launchPersistentContext`/`channel: chrome` trong fixture | browser isolation static test | A08 / 025-CELL-03 |
| M10 | Giả lập `docker compose down` xong còn 1 network | final PASS/cleanup test | A10 / 025-CELL-04 |
| M11 | Build/ready receipt với SHA khác HEAD | candidate identity assertion | A01 / 025-CELL-01 |
| M12 | Nhét canary token/DB URL vào receipt fixture | receipt schema redaction test | A03/A11 / 025-CELL-05 |

Với mỗi row đã chạy, PR receipt cần raw block theo khuôn:

```text
MUTATION=M01
RED_COMMAND=<exact command>
RED_EXIT=<nonzero>
RED_OUTPUT=<raw failing assertion, đã redact>
RESTORE=<exact file restored>
GREEN_COMMAND=<same command>
GREEN_EXIT=0
GREEN_OUTPUT=<raw pass output>
```

Không chấp nhận “test vẫn xanh khi code hỏng”, “đã review bằng mắt” hoặc hai command khác nhau không
đo cùng assertion.

## 5. Trình tự chạy và raw receipts

Tên CLI là contract của implementation:

```text
python -m unittest discover -s qa/production-cell/tests -p "test_*.py"
python qa/production-cell/run.py
```

Reviewer lưu nguyên output; không tóm tắt thay output. Sau full run:

```text
git status --short
docker ps -a --filter label=com.docker.compose.project=<exact-run-id>
docker network ls --filter label=com.docker.compose.project=<exact-run-id>
docker volume ls --filter label=com.docker.compose.project=<exact-run-id>
```

Nếu command timeout: ghi timeout + kiểm trạng thái thật trên disk/Docker trước khi kết luận; tiếp tục
cleanup theo exact project manifest. Không dùng `docker system prune`, wildcard hoặc xoá project khác.

Docs/code-safe checks cuối:

```text
git diff --check
pre-commit run --all-files
```

Phase B còn phải chờ `gh pr checks <PR> --watch` và dán output check-name/status/commit. Reviewer
không merge.

## 6. Physical iPhone receipt — distinct, mặc định NOT RUN

Local cell **không** bind LAN để iPhone truy cập; làm thế sẽ phá A04. Physical iPhone acceptance là
một lượt riêng do owner cho phép, trên candidate đã deploy, theo đúng account/privacy rule hiện hành.
Không dùng cell token/PIN và không đưa account/email thật vào artifact.

Khi chưa chạy, receipt bắt buộc:

```json
{
  "acceptance_id": "Q025-DEVICE-IPHONE-01",
  "status": "NOT RUN",
  "reason": "Physical iPhone acceptance is separate from the disposable local cell",
  "production_commit": null,
  "executed_at": null,
  "evidence": []
}
```

Nếu 017 dùng policy này mà chưa chạy physical A18, báo nguyên văn:

```text
017_QA=PARTIAL
017_A18=NOT RUN
RELEASE_V1=ELIGIBLE_WITH_DEVICE_GAP   # chỉ khi mọi release gate khác pass
```

Không sửa `017-qa-offline-outbox.md` hoặc gọi `017=PASS`.

## 7. Verdict table

| Điều kiện | CELL | DEVICE | Release v1 |
|---|---|---|---|
| A01–A14 applicable pass, cleanup sạch | PASS | PASS | ELIGIBLE |
| Cell pass, iPhone chưa chạy | PASS | NOT RUN | ELIGIBLE_WITH_DEVICE_GAP |
| Cell pass, iPhone chạy và fail | PASS | FAIL | BLOCKED |
| Guard/role/cleanup/receipt fail | FAIL | bất kỳ | BLOCKED |
| Docker/browser prerequisite thiếu, chưa có full receipt | BLOCKED | NOT RUN | BLOCKED |

Mọi mục không chạy ghi `NOT RUN`; mọi điều suy từ code ghi `[SUY LUẬN]`; chỉ output vừa chạy được
ghi `[QUAN SÁT]`. Không dùng CI/local/browser emulation để suy ra production hoặc physical device.
