# Task 025 — local production-image QA cell

> **Trạng thái: ✅ SPEC APPROVED 2026-08-24; chỉ được thi công theo các phase dưới đây.**
> Executor: T2 Codex · Bậc: high · Effort: high · Skill gợi ý: Playwright · MCP: không cần.
> Target: PR nhỏ vào `develop`; không merge, deploy, migration production hoặc đổi ruleset.

## 0. Kết quả cần có

Dựng một QA cell dùng **đúng production Docker image build từ candidate SHA**, nhưng chạy hoàn toàn
local với Postgres throwaway, session/PIN/data synthetic và Playwright Chromium context không
persistent. Cell phải fail-closed trước mọi production/host target, không đọc `.env`, không dùng
Google OAuth thật, không dùng Chrome profile thật, không phát outbound, và luôn để lại receipt dọn
dẹp máy-đọc-được.

Đây là **hạ tầng QA**, không phải thay đổi hành vi app. `Dockerfile`, app source, `fly.toml`, deploy
workflow và Alembic revisions là read-only trong task này.

## 1. Evidence đầu vào — không được nâng nhãn

### [QUAN SÁT 2026-08-24 trên `origin/develop`]

- `Dockerfile` là multi-stage production build, cài backend bằng `uv sync --frozen --no-dev`, copy
  frontend build, chạy non-root và nhận `GIT_SHA` qua build arg.
- `.github/workflows/ci.yml` đang có các check mang đúng tên:
  `Backend checks`, `Production dependency check`, `Repository hooks`, `Secret scan`,
  `Frontend checks`, `Frontend e2e`, `Migration QA`.
- `.github/workflows/deploy.yml` deploy khi push `develop`; nó không chạy Alembic. `fly.toml` đặt
  `ENABLE_INPROCESS_CRON = "true"` cho production. Cell không được copy runtime env đó.
- `frontend/playwright.config.ts` hiện chạy suite mock với `serviceWorkers: 'block'`. Nó không phải
  full-stack production-image receipt.
- `backend/app/core/settings.py` có default `APP_ENV=production`, đọc `.env` nếu caller không chặn,
  và default cron là false. `backend/tests/conftest.py` có escape hatch
  `ALLOW_REMOTE_PG_TESTS=1`; cell phải loại biến này, không dùng nó.
- Session thật dùng cookie `ms_session`; DB chỉ lưu SHA-256 digest của opaque token. Protected API
  vẫn đi qua `require_session`. PIN có thể được đặt qua protected API khi DB chưa có PIN.
- Spec `017` yêu cầu real Service Worker, outbox, idempotent writes, private-cache exclusion và A18
  trên iPhone. Code 017 chưa có trong `origin/develop` tại thời điểm viết spec này.

### [SUY LUẬN từ evidence trên]

- Chạy image với `fly.toml`/production secrets là sai boundary: nó có thể bật recurring outbound.
  Cell phải dùng local runtime config tường minh, trong khi image artifact vẫn là production image.
- Mock Playwright hiện tại không chứng minh app image, database, role grants, session store hoặc real
  Service Worker. Cần lane riêng thay vì sửa nghĩa suite đó.

### [KHÔNG BIẾT cho tới khi có receipt]

- Docker daemon/Compose/Playwright browser có sẵn trên máy executor hay không.
- Candidate image có build và chạy được, cell có dọn sạch sau timeout hay không.
- Hành vi Safari/installed PWA trên iPhone thật. Mục này giữ receipt riêng, mặc định `NOT RUN`.

## 2. Safety boundary tuyệt đối

### 2.1 Đích duy nhất được phép

- App origin nhìn từ Chromium: reverse proxy **bên trong browser-runner container** chỉ nghe
  `http://127.0.0.1:<ephemeral-port>` và chỉ forward tới service cố định `app:8000`; không có option
  `--base-url` và không publish app ra host.
- DB: service DNS cố định `db:5432` bên trong run-scoped Compose network; **không publish DB port**.
- Docker resources: project name `msqa025-<UTC timestamp>-<8 hex>` do runner sinh; mọi thao tác dọn
  chỉ dùng đúng project name đã ghi trong manifest.
- Image: build từ root `Dockerfile` của exact `git rev-parse HEAD`, với
  `--build-arg GIT_SHA=<full SHA>`. Không bind-mount source vào app container.

Network của app + DB + browser-runner phải là Compose `internal: true`; **app và DB đều có 0 host
port**. Reverse proxy chỉ bind loopback trong browser container, cấm `0.0.0.0`, LAN IP,
`network_mode: host`, privileged mode và Docker socket. Browser chỉ được request đúng origin
loopback vừa sinh; proxy không nhận upstream tùy ý và request khác phải bị abort, ghi host đã redact
rồi làm test fail. Image build/pull có thể dùng mạng trước khi secret được sinh; runtime có secret
thì chỉ tồn tại trên internal network.

### 2.2 Forbidden targets và input

Runner phải từ chối **trước lệnh Docker đầu tiên** nếu caller đưa bất kỳ option/biến cấu hình target
nào ngoài contract ở §2.1. Ít nhất các tên sau phải nằm trong deny-set và chỉ được báo **tên**, không
được đọc/in giá trị:

`DATABASE_URL`, `NEON_OWNER_URL`, `NEON_MIGRATOR_URL`, `CUTOVER_MIGRATOR_URL`,
`ALLOW_REMOTE_PG_TESTS`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_EMAILS`,
`PRIVATE_PIN_BOOTSTRAP`, `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CLAIMS_SUB`,
`FLY_API_TOKEN`, `FLY_APP`, `PLAYWRIGHT_BASE_URL`.

Deny-set áp vào **parent environment/caller input** trước khi sinh cell. Sau guard, orchestrator tạo
`DATABASE_URL` nội bộ từ service `db` + password mới và chỉ truyền nó tới đúng child qua secret
mount; tuyệt đối không forward giá trị cùng tên từ parent shell.

Ngoài deny-by-name, config validation phải cấm mọi literal/parsed host thuộc các lớp:

- `*.neon.tech`, Neon pooler/host DB bất kỳ;
- `microsched.fly.dev`, `*.fly.dev`, hoặc HTTP(S) host không phải `127.0.0.1`;
- `localhost`/host gateway/LAN cho DB; DB chỉ được là Compose service `db`;
- đường dẫn Chrome profile, `user-data-dir`, storage state hoặc cookie export của người thật.

Không có `--force`, `--allow-production`, `--remote`, escape hatch hoặc interactive prompt để vượt
guard. Nếu guard từ chối, exit `40`, status `GUARD_DENIED`, resource count phải bằng 0.

### 2.3 Secrets chỉ sống trong một run

- Dùng CSPRNG để sinh Postgres owner/app/migrator passwords, AES key, opaque session token và PIN 6
  chữ số cho từng run. Email fixture luôn thuộc `example.invalid`.
- Không đọc root/backend `.env`; đặt `COMPOSE_DISABLE_ENV_FILE=1`; Compose files không có `env_file`
  và không interpolate biến deny-set. Chạy `docker compose config -q` trước `up`.
- Secret không được đi qua command-line, stdout, log, screenshot, receipt hoặc git. Nếu container
  dài-sống cần secret, dùng file trong temp directory run-scoped (POSIX `0700`/file `0600` khi hệ
  điều hành hỗ trợ) và mount bằng Compose secret; wrapper đọc rồi `exec`. Browser/seed helper nhận
  token/PIN qua stdin hoặc anonymous pipe, không qua argv.
- Temp secret directory bị xoá trong `finally`. Một run dọn lỗi không được giữ receipt `PASS`.
- App **không nhận** owner/migrator URL; migrator/owner helper **không nhận** session/PIN. Receipt chỉ
  ghi fingerprint một chiều tối đa 12 hex nếu thật sự cần đối chiếu, không ghi digest của PIN.

## 3. Kiến trúc cell và file được phép

Phase A chỉ được thêm/sửa trong:

- `qa/production-cell/**`: cross-platform Python orchestrator, Compose base, bootstrap/seed helpers,
  browser-runner Dockerfile/proxy, policy/receipt schema và unit tests;
- `frontend/e2e/production-cell/**`: Playwright full-stack tests, không dùng mock routes;
- `frontend/package.json` chỉ nếu cần một script gọi lane; `.gitignore` chỉ nếu artifact path chưa
  được phủ. Ưu tiên `frontend/test-results/production-cell/<run_id>/`, vốn đã bị ignore.

Không sửa `Dockerfile`. App service build thẳng file đó. QA helper có thể có Dockerfile riêng nhưng
không được thay thế image đang được test.

### 3.1 Thứ tự dịch vụ

1. **Preflight:** working tree policy, exact SHA, Docker/Compose version, port/network/env policy.
2. **Build:** production app image với full SHA; lấy immutable image ID.
3. **DB:** `pgvector/pgvector:pg18`, data directory trên tmpfs, healthcheck bounded, không host port.
4. **Bootstrap:** one-shot owner helper tạo `microsched_migrator` và `microsched_app`, revoke public,
   schema `microsched` do migrator sở hữu, app chỉ có usage + DML. Không gọi
   `bootstrap_neon.py` vì script đó đọc `backend/.env`.
5. **Migrate:** one-shot production image chạy Alembic head bằng **migrator URL của cell**, rồi
   migrator revoke mọi DML của app trên `microsched.alembic_version`; container phải exit trước app.
   Đây là migration rehearsal trên throwaway PG, không phải deploy migration.
6. **Seed auth:** one-shot helper dùng app role, nhận token qua stdin, chỉ insert session synthetic
   với `hash_session_token`; raw token không vào DB/log.
7. **App:** production image, `APP_ENV=local`, `SESSION_COOKIE_SECURE=false`,
   `ENABLE_INPROCESS_CRON=false`, không Google/VAPID/PIN-bootstrap env. Chỉ app-role DB URL + runtime
   AES key. Startup command giữ nguyên image; không tự chạy Alembic.
8. **Browser:** build QA runner image từ Node 24 + exact `frontend/package-lock.json`, chạy
   `playwright install --with-deps chromium` ở build-time; đây là helper image, không thay app image.
   Khi runtime, proxy nội bộ chỉ forward loopback → `app:8000`; Playwright dùng
   `browser.newContext()` không persistent, `serviceWorkers: 'allow'`, cookie synthetic chỉ add vào
   context này. Cấm `channel: 'chrome'`, `launchPersistentContext`, `userDataDir`, real
   `storageState`, browser extension và Google OAuth. Browser runner chỉ nối internal network.
9. **Cleanup:** đóng context/browser rồi dọn đúng Compose project, temp secrets và helper process.

`/api/readyz` chỉ đạt khi body có `status="ok"`, `db="up"`, `commit=<full candidate SHA>`; HTTP 200
một mình không đạt.

### 3.2 Role attestation bắt buộc

Trước browser test, helper chạy và ghi các boolean sau (không ghi URL/password):

- app connection `current_user = microsched_app`;
- schema/table owner là `microsched_migrator` theo migration output;
- app có SELECT/INSERT/UPDATE/DELETE nhưng không có CREATE trên schema;
- `CREATE TABLE microsched.__qa025_forbidden(...)` bằng app role bị permission denied;
- app role không thể update/delete `alembic_version` và app container không có owner/migrator secret;
- migrator container đã exit; app startup không chạy migration.

Negative query phải nằm trong transaction rollback hoặc dùng tên fixture run-scoped; không để lại
object ngay cả trong throwaway DB.

## 4. Synthetic fixture và smoke contract

Mọi label có prefix `[QA025:<run_id>]`; email là `qa025-<suffix>@example.invalid`. ID do fixture sinh
và ghi vào receipt; không dùng tên/email/ngày thật. Browser/API phải đi qua real app, **không
`page.route` mock response**.

Luồng tối thiểu:

1. Không cookie: `GET /api/me` trả 401.
2. Seed digest + add cookie `ms_session` vào isolated context: `/api/me` trả đúng email synthetic.
3. Đặt PIN synthetic bằng protected `POST /api/private/pin`; không có QA auth/PIN bypass route.
4. Khi khoá, create private task bị 403 và response không lộ title fixture.
5. Unlock bằng PIN, tạo một public task + một private task (mỗi task có item) và một note bằng real
   API/UI; reload production page thấy dữ liệu tương ứng.
6. Khoá lại: private task biến mất, public task/note vẫn hiện; `/api/me` vẫn là session synthetic.
7. Service Worker: trên loopback secure context, reload sau registration và ghi
   `navigator.serviceWorker.controller !== null`. Mục này chỉ chứng minh PWA shell hiện tại; không
   chứng minh outbox 017.
8. Logout thật: `/api/me` trở lại 401. Sau đó DB/cell bị huỷ toàn bộ, không “dọn từng row” trên một
   DB sống lâu.

## 5. Timeout, cleanup và receipt

### 5.1 Ngân sách mặc định

| Phase | Timeout |
|---|---:|
| preflight | 30 s |
| build image | 20 min |
| DB/bootstrap/migrate | 5 min tổng |
| app ready | 90 s |
| browser smoke | 10 min |
| cleanup | 2 min |

Timeout **không** có nghĩa phase chưa tạo gì. Khi timeout/cancel, runner phải chụp inventory theo
exact project label, rồi cleanup trong `finally`; cấm wildcard hoặc xoá resource không mang project
name trong manifest.

### 5.2 Taxonomy + exit code

| Status | Exit | Nghĩa |
|---|---:|---|
| `PASS` | 0 | Mọi assertion cell pass và cleanup sạch |
| `FAIL_ASSERTION` | 20 | App/role/browser assertion sai |
| `BLOCKED_PREREQUISITE` | 30 | Docker/Compose/Node/browser chưa có; chưa chạy mutation |
| `GUARD_DENIED` | 40 | Input/target/env vi phạm; chưa tạo Docker resource |
| `SETUP_TIMEOUT` | 50 | build/DB/migrate/ready quá hạn |
| `TEST_TIMEOUT` | 51 | browser phase quá hạn |
| `CLEANUP_TIMEOUT` | 52 | dọn quá hạn hoặc còn resource; luôn non-pass |
| `INFRA_ERROR` | 60 | lỗi công cụ không thuộc assertion |
| `NOT_RUN` | — | Chỉ dùng trong sub-receipt chưa chạy, ví dụ physical iPhone |

Nếu test pass nhưng cleanup fail, final status là `CLEANUP_TIMEOUT`, không phải `PASS`.

### 5.3 Receipt JSON v1

Lưu redacted receipt tại `frontend/test-results/production-cell/<run_id>/receipt.json`, gồm tối thiểu:

```json
{
  "schema": "microsched.qa025.receipt.v1",
  "run_id": "msqa025-...",
  "target_class": "local_disposable",
  "git_sha": "<40 hex>",
  "image_id": "sha256:<digest>",
  "started_at": "<UTC>",
  "ended_at": "<UTC>",
  "final_status": "PASS",
  "phases": [{"name": "preflight", "status": "PASS", "duration_ms": 0}],
  "safety": {
    "browser_origin": "runner-loopback:<redacted-ephemeral-port>",
    "app_ports_published": 0,
    "db_ports_published": 0,
    "network_internal": true,
    "env_file_disabled": true,
    "outbound_requests": 0
  },
  "roles": {"app": "microsched_app", "migrator": "microsched_migrator", "ddl_denied": true},
  "fixtures": {"prefix": "[QA025:<run_id>]", "task_count": 2, "note_count": 1},
  "acceptance": {"025-CELL-01": "PASS"},
  "cleanup": {"status": "PASS", "containers": 0, "networks": 0, "volumes": 0},
  "physical_iphone": {"status": "NOT RUN", "reason": "separate acceptance"}
}
```

Receipt cấm URL DB, env values, token, PIN, AES key, real email, container env dump và literal host
production. Schema validator phải fail nếu xuất hiện key cấm hoặc string thuộc forbidden targets.

## 6. Acceptance IDs cho implementer

- **025-SAFE-01 — Default deny:** mọi target/env injection ở §2.2 trả `GUARD_DENIED` trước Docker;
  không có production URL option hoặc escape hatch.
- **025-SAFE-02 — No ambient secret:** `.env` bị vô hiệu; secrets mỗi run không vào argv/log/git/
  receipt; gitleaks + receipt validator pass.
- **025-SAFE-03 — Network boundary:** app + DB có 0 published port; proxy chỉ bind loopback trong
  browser container; network internal; browser có 0 outbound request.
- **025-SAFE-04 — Role split:** assertions §3.2 pass; app chỉ nhận app URL, migration chỉ nhận
  migrator URL; owner helper chết trước app.
- **025-SAFE-05 — Auth thật, danh tính giả:** session digest + cookie thật, PIN endpoint thật;
  không Google OAuth/real account/QA bypass route.
- **025-SAFE-06 — No recurring/deploy effect:** cron false, VAPID/Google/Fly env absent, không sửa
  deploy/fly/Alembic, không gọi `fly`, Neon hoặc host Postgres.
- **025-CELL-01 — Candidate identity:** image build từ exact clean candidate SHA; readyz commit + db
  khớp, immutable image ID có trong receipt.
- **025-CELL-02 — Real stack:** fixture flow §4 pass không mock; Service Worker controller pass nhưng
  không claim outbox.
- **025-CELL-03 — Browser isolation:** bundled Chromium context mới, đóng cuối run; không Chrome
  profile/persistent state.
- **025-CELL-04 — Timeout/cleanup:** từng failure class sinh đúng status; success chỉ khi resource
  inventory về 0; rerun cùng máy không gặp fixture/resource cũ.
- **025-CELL-05 — Receipt:** JSON schema pass, đủ phase/duration/acceptance/cleanup, không secret/PII.
- **025-RED-01 — Guard biết đỏ:** chạy mutation matrix trong QA spec, lưu raw RED rồi restore GREEN;
  không commit mutant.
- **025-CI-01 — Named-check compatibility:** Phase B giữ nguyên toàn bộ tên check hiện có và thêm
  đúng `Local production-image QA cell` trong workflow `CI`; xem §7.
- **025-DEP-017 — Không hấp thụ 017:** không copy/import branch 017, không sửa spec/code 017, không
  claim A01–A20. Integration outbox chỉ được làm sau precondition §8.

## 7. Phased implementation — không gộp quyền

### Phase A — local cell (PR 025-A)

Thi công §2–§6, unit/policy tests, chạy local receipt và independent QA. **Không sửa CI**. Không được
chạm app behavior, root `Dockerfile`, production config hoặc migrations. Docker Desktop là
prerequisite; `docker --version` không thay receipt daemon hoạt động.

### Phase B — informational CI lane (PR riêng sau khi Phase A được review)

Chỉ sau khi independent QA của Phase A đạt:

- thêm job id `production-qa-cell`, `name: Local production-image QA cell` vào workflow
  `.github/workflows/ci.yml` hiện hữu;
- workflow vẫn trigger mọi PR/push `develop`, **không path-filter** job/workflow này;
- `permissions: contents: read`, không GitHub Environment, không repository secret, không cloud
  credential; timeout job tối đa 25 phút;
- không rename/xoá các job-name hiện hữu; không sửa `.github/workflows/deploy.yml`;
- check mới giữ **informational/non-required**. Thay ruleset là một owner decision + PR/operation riêng,
  tuyệt đối không làm cùng implementation.

Lý do không dùng một required workflow có path filter: PR bị skip có thể để required check ở trạng
thái pending. Một check mới cũng không được “mượn tên” required check cũ.

### Phase C — task-specific adoption

Mỗi feature (đặc biệt 017) thêm scenario riêng ở PR riêng sau khi code feature có trên current
`develop`. Cell foundation pass không tự pass feature acceptance.

## 8. Dependency/precondition với Task 017

025 **không phụ thuộc code 017** để dựng cell; smoke dùng flow task/note/private hiện có. 017 chỉ
được tiêu thụ cell khi đồng thời:

1. implementation 017 đã reconcile lên then-current `develop`, được review và không còn WIP branch
   divergence;
2. prerequisite đã khóa của 017 vẫn giữ nguyên: chạy **sau 011c**, khi bốn family
   task/note/calendar/tracker đã tồn tại; 025 không kéo 011c vào scope của mình;
3. idempotent child POSTs, typed route-aware classifier, Dexie outbox, offline `/api/me` public
   bootstrap không mang quyền private, real Service Worker, item-level private persistence exclusion
   và logout cleanup của spec 017 đã tồn tại;
4. adapter 017 thêm scenario vào Phase C mà không sửa guard/network/auth của foundation;
5. independent QA vẫn chạy A01–A20 của `017-qa-offline-outbox.md`. 025 không đổi A18 thành PASS.

Nếu 017 chưa có, receipt ghi `025-DEP-017 = NOT APPLICABLE`, không dựng fake outbox và không copy
file từ `feat/017-offline-outbox`.

## 9. 🚫 Không được làm

1. Không Neon/host DB/production URL, `.env`, real Google OAuth, real email/data, Chrome profile.
2. Không auth/PIN bypass route, test-only branch trong app, shared long-lived QA account hoặc PIN.
3. Không bật cron/push, không gửi outbound, không deploy, không `fly`, không production migration.
4. Không sửa `Dockerfile`, `fly.toml`, deploy workflow, app source, Alembic revision hoặc task 017.
5. Không publish DB hoặc app ra LAN; không Docker socket/privileged/host network.
6. Không gọi cleanup bằng wildcard/project prefix; chỉ exact manifest target.
7. Không gọi local Chromium/iPhone/viewport là bằng chứng physical iPhone.
8. Không merge và không đổi required checks. Reviewers quyết định gate.

## 10. Nguồn chuẩn để implementer đối chiếu

- Docker Compose networking + project/service discovery:
  <https://docs.docker.com/compose/how-tos/networking/>
- Compose `internal` network và port bind:
  <https://docs.docker.com/reference/compose-file/networks/> và
  <https://docs.docker.com/reference/compose-file/services/>
- Tắt implicit `.env` bằng `COMPOSE_DISABLE_ENV_FILE`:
  <https://docs.docker.com/compose/how-tos/environment-variables/envvars/>
- Playwright `BrowserContext` không persistent:
  <https://playwright.dev/docs/api/class-browsercontext>
- GitHub required check bị pending khi workflow bị skip:
  <https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks>
