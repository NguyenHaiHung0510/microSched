# Task 025 QA — independent review cho local production-image QA cell

> **Trạng thái: ✅ QA SPEC APPROVED 2026-08-24.**
> Reviewer độc lập với implementer; chạy trên worktree riêng của candidate PR, không production
> access, không secret thật, không merge. Physical iPhone là receipt riêng; machine token được phép
> `NOT_RUN` (báo cáo cho người có thể hiển thị “NOT RUN”).

## 0. Verdict đang được kiểm

QA này chỉ trả lời: **cell có dùng production image candidate trong một biên local disposable
fail-closed hay không**. Nó không chứng minh production deployment, real Google OAuth, Safari,
physical iPhone hoặc outbox 017.

Ba nhãn phải tách:

- `CELL = PASS | FAIL | BLOCKED`;
- `PHYSICAL_IPHONE = PASS | FAIL | NOT_RUN`;
- `RELEASE_V1 = ELIGIBLE | ELIGIBLE_WITH_DEVICE_GAP | BLOCKED`.

Owner đã duyệt: `CELL=PASS` + `PHYSICAL_IPHONE=NOT_RUN` cho phép
`RELEASE_V1=ELIGIBLE_WITH_DEVICE_GAP`. Không được viết `iPhone PASS`. Nếu physical run ra `FAIL`,
release là `BLOCKED` cho tới khi xử lý/owner quyết định khác.

## 1. Boundary của reviewer

- Chỉ dùng local Docker daemon + candidate worktree. Không mở `microsched.fly.dev`, Fly dashboard,
  Neon, host Postgres, `.env`, Google OAuth, Chrome profile thật hoặc dữ liệu thật.
- Không export/read giá trị các biến bị cấm. Nếu chúng đã tồn tại trong shell, full run phải đi qua
  runner tự sanitize bằng allowlist đóng; negative guard test chỉ report tên biến, không report giá
  trị. Reviewer không tự `unset` rồi gọi Docker ngoài runner để né guard.
- Không bật Docker Desktop thay owner; nếu daemon tắt, trả `BLOCKED_PREREQUISITE` với raw error.
- Không tự sửa candidate để “làm xanh”. Mutation proof chỉ là thay đổi tạm, restore ngay, rồi xác
  nhận `git diff` trở lại đúng candidate.
- Không chạy task 017, không copy WIP branch 017, không đổi acceptance A01–A20.

## 2. Prerequisite receipts

Các lệnh Git/Docker dưới đây phải do runner cung cấp ở preflight và đi qua exact command envelope
§2.3 của implementation spec; reviewer không gọi ambient `docker` trực tiếp. Lưu raw stdout/stderr +
exit code đã redact:

```text
python qa/production-cell/run.py --preflight-only
python --version
```

Preflight receipt phải chứa candidate SHA/clean status, absolute trusted executable hashes,
sanitized environment key-set hash, explicit local context/endpoint/daemon identity, Compose
version và resource count 0. `docker --version` một mình không đủ. Candidate worktree phải clean
trước full run, trừ artifact ignored trong `frontend/test-results/`.

## 3. Acceptance độc lập

### Q025-A01 — scope và candidate identity

- Diff Phase A chỉ chạm allowlist §3 của implementation spec; diff Phase B chỉ thêm CI placement đã
  nêu. Không app source, root `Dockerfile`, `fly.toml`, deploy workflow, Alembic revision hoặc 017.
- Production app image dùng root `Dockerfile` không sửa và full candidate SHA. Receipt `image_id`
  tồn tại; `/api/readyz` có `status=ok`, `db=up`, `commit=<HEAD>`.

### Q025-A02 — guard từ chối trước side effect

- Với từng biến/target forbidden, CLI trả exit 40 + `GUARD_DENIED`.
- Guard test bao phủ ít nhất `DOCKER_HOST`, `DOCKER_CONTEXT`, `BUILDKIT_HOST`, `COMPOSE_FILE`,
  `COMPOSE_PROJECT_NAME`, `COMPOSE_PROFILES`, remote endpoint/context và ambient Git/path
  indirection. Mọi Docker/Compose call dùng allowlist child env, trusted absolute executable,
  explicit attested local context, absolute owned Compose files + exact generated project.
- Trước/sau guard-denied không có Docker mutable command và resource count là 0.
- Không tồn tại `--force`, `--allow-production`, `--remote`, `--base-url` hoặc fallback prompt.

### Q025-A03 — không ambient config/secret

- Unit test dùng temp directory chứa `.env` với canary vô hại; rendered config không chứa canary.
- `COMPOSE_DISABLE_ENV_FILE=1`, không `env_file`, secret không nằm trong argv/log/receipt.
- Chạy receipt-schema negative test với token/PIN/DB URL canary: validator phải từ chối.
- `gitleaks`/pre-commit pass trên candidate; không dán literal runtime secret vào PR.

### Q025-A04 — network và resource isolation

- Mỗi service `db/bootstrap/migrate/seed/app/browser` có 0 published host port trong rendered config
  lẫn runtime inspect; receipt `ports_by_service` đủ sáu key và `total_ports_published=0`.
- Top-level và runtime có đúng một network `cell`, `Internal=true`; không `default`, external/host/
  service/container network mode. Từng container chỉ nối exact network ID đó.
- Reverse proxy trong browser container chỉ bind `127.0.0.1:<ephemeral>` và chỉ có upstream tĩnh
  `app:8000`. Không host/LAN bind, host network, privileged, Docker socket hoặc unrelated resource.
- Browser request ledger chỉ có exact runner-loopback origin; attempted other origin bị abort + fail.
- Sau pass, fail, SIGINT và timeout: exact IDs trong verified manifest đều absent; foreign sentinel
  project/resource vẫn sống và không đổi config hash.

### Q025-A05 — app/migrator split

- `current_user` app là `microsched_app`; schema/table owner là `microsched_migrator`.
- App role DML pass nhưng DDL và `alembic_version` write bị permission denied.
- App container không nhận owner/migrator secret; Compose có
  `app.depends_on.migrate.condition=service_completed_successfully` và migrate exit trước app.
- App startup command không gọi Alembic; migration chỉ chạy one-shot trên throwaway PG.
- Fault-inject migration exit non-zero: command ledger không có app-create/start, app container
  absent và không running.

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
- Manifest canonical hash bind exact `run_id`, `project_name`, daemon identity, Compose hashes và mọi
  resource ID. Cleanup chỉ stop/remove exact verified IDs; không Compose down, wildcard/prefix,
  prune hoặc label-discovery delete set.
- Manifest/project/resource tamper trả `CLEANUP_GUARD_DENIED`, không delete cell hay sentinel.
- Receipt PASS chỉ khi cell containers/networks/volumes/helper-processes đều 0 và sentinel sống.

### Q025-A11 — receipt integrity

- `agent-tasks/025-qa-receipt.schema.json` pass Draft 2020-12 meta-schema check; exact validator
  command trong implementation spec pass receipt và reject unknown/missing field hoặc enum sai.
- Receipt validate `microsched.qa025.receipt.v1`, đủ SHA/image/phases/durations/safety/roles/fixture/
  acceptance/migration/network/cleanup/device fields.
- Receipt không secret, DB URL, real email, production host, env/container dump. Timestamps UTC và
  `ended_at >= started_at`.
- Raw command log phân biệt rõ `RUN`, `PASS`, `FAIL`, `NOT_RUN`; báo cáo hiển thị có thể viết “NOT
  RUN”. Không suy pass từ exit 0 đơn lẻ.

### Q025-A12 — RED→GREEN mutation proof

- Chạy toàn bộ persistent negative tests.
- Chạy các mutation bắt buộc **M01, M03, M05, M07, M09, M10, M12 và M13–M24** dưới đây; mỗi
  mutation phải làm đúng named test đỏ vì guard bị phá, restore rồi cùng test xanh.
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

- Không file/diff/claim từ task 017. Foundation receipt ghi `025-DEP-017=NOT_APPLICABLE` khi code
  chưa có.
- Nếu adapter 017 được review ở Phase C sau này, vẫn dùng toàn bộ QA spec 017; 025 không pass A01–A20.
- Physical iPhone sub-receipt hiện diện với `PASS`, `FAIL` hoặc `NOT_RUN`; Chromium 390×844 không
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
| M10 | Giả lập exact-ID cleanup trả còn 1 network | final PASS/cleanup test | A10 / 025-CELL-04 |
| M11 | Build/ready receipt với SHA khác HEAD | candidate identity assertion | A01 / 025-CELL-01 |
| M12 | Nhét canary token/DB URL vào receipt fixture | receipt schema redaction test | A03/A11 / 025-CELL-05 |
| M13 | Set parent `DOCKER_HOST=tcp://198.51.100.1:2375` | remote-daemon env guard trước mutation | A02 / 025-SAFE-07 |
| M14 | Set `DOCKER_CONTEXT=remote` và fixture endpoint `ssh://example.invalid` | remote-context guard trước mutation | A02 / 025-SAFE-07 |
| M15 | Set `COMPOSE_FILE` tới file ngoài owned QA dir | external-Compose-file guard trước mutation | A02 / 025-SAFE-07 |
| M16 | Set `COMPOSE_PROJECT_NAME` khác run ID hoặc `COMPOSE_PROFILES` | project/profile injection guard | A02 / 025-SAFE-07 |
| M17 | Bỏ `service_completed_successfully`, rồi fault-inject migrate exit non-zero | app absent/not-running gate | A05 / 025-CELL-06 |
| M18 | Sửa một byte manifest hash/resource ID | cleanup manifest guard, 0 delete | A10 / 025-CELL-04 |
| M19 | Sửa `project_name` trong manifest sang sentinel project | project mismatch guard; cell + sentinel cùng sống | A10 / 025-CELL-04 |
| M20 | Publish port của browser/one-shot service | every-service zero-port guard | A04 / 025-SAFE-03 |
| M21 | Bỏ explicit `networks: [cell]` để sinh `default` | exactly-one-internal-network guard | A04 / 025-SAFE-03 |
| M22 | Đổi receipt `NOT_RUN` thành `NOT RUN` hoặc xoá required field | schema validator | A11 / 025-CELL-05 |
| M23 | Cho một Docker call clone parent env/không chèn explicit context | command-envelope call-ledger test | A02 / 025-SAFE-07 |
| M24 | Set `GIT_DIR` ngoài repo hoặc prepend fake `docker`/`git` vào parent `PATH` | Git/path/executable indirection guard | A02 / 025-SAFE-07 |

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
python qa/production-cell/validate_receipt.py --schema agent-tasks/025-qa-receipt.schema.json --receipt qa/production-cell/tests/fixtures/valid-receipt.json
python qa/production-cell/run.py
```

Reviewer lưu nguyên output; không tóm tắt thay output. Sau full run, runner phải cung cấp một
`--verify-cleanup <receipt-path>` mode dùng verified manifest + exact IDs và cùng sanitized Docker
envelope; reviewer không gọi ambient Docker hoặc label query:

```text
python qa/production-cell/run.py --verify-cleanup frontend/test-results/production-cell/<run_id>/receipt.json
git status --short
```

Nếu command timeout: ghi timeout + kiểm trạng thái thật trên disk/Docker trước khi kết luận; tiếp tục
cleanup theo verified exact-ID manifest. Không dùng `docker compose down`, label query,
`docker system prune`, wildcard hoặc xoá project khác.

Docs/code-safe checks cuối:

```text
git diff --check
pre-commit run --all-files
```

Phase B còn phải chờ `gh pr checks <PR> --watch` và dán output check-name/status/commit. Reviewer
không merge.

## 6. Physical iPhone receipt — distinct, machine token mặc định `NOT_RUN`

Local cell **không** bind LAN để iPhone truy cập; làm thế sẽ phá A04. Physical iPhone acceptance là
một lượt riêng do owner cho phép, trên candidate đã deploy, theo đúng account/privacy rule hiện hành.
Không dùng cell token/PIN và không đưa account/email thật vào artifact.

Khi chưa chạy, receipt bắt buộc:

```json
{
  "acceptance_id": "Q025-DEVICE-IPHONE-01",
  "status": "NOT_RUN",
  "reason": "Physical iPhone acceptance is separate from the disposable local cell",
  "production_commit": null,
  "executed_at": null,
  "evidence": []
}
```

Nếu 017 dùng policy này mà chưa chạy physical A18, báo nguyên văn:

```text
017_QA=PARTIAL
017_A18=NOT_RUN
RELEASE_V1=ELIGIBLE_WITH_DEVICE_GAP   # chỉ khi mọi release gate khác pass
```

Không sửa `017-qa-offline-outbox.md` hoặc gọi `017=PASS`.

## 7. Verdict table

| Điều kiện | CELL | DEVICE | Release v1 |
|---|---|---|---|
| A01–A14 applicable pass, cleanup sạch | PASS | PASS | ELIGIBLE |
| Cell pass, iPhone chưa chạy | PASS | NOT_RUN | ELIGIBLE_WITH_DEVICE_GAP |
| Cell pass, iPhone chạy và fail | PASS | FAIL | BLOCKED |
| Guard/role/cleanup/receipt fail | FAIL | bất kỳ | BLOCKED |
| Docker/browser prerequisite thiếu, chưa có full receipt | BLOCKED | NOT_RUN | BLOCKED |

Mọi machine field chưa chạy ghi `NOT_RUN` (display có thể viết “NOT RUN”); mọi điều suy từ code ghi
`[SUY LUẬN]`; chỉ output vừa chạy được
ghi `[QUAN SÁT]`. Không dùng CI/local/browser emulation để suy ra production hoặc physical device.
