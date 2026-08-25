# Task 025 — local production-image QA cell

> **Trạng thái: ✅ SPEC APPROVED 2026-08-24; chỉ được thi công theo các phase dưới đây.**
> Executor: T2 Codex · Bậc: high · Effort: high · Skill gợi ý: Playwright · MCP: không cần.
> Target: PR nhỏ vào `develop`; không merge, deploy, migration production hoặc đổi ruleset.

> **Amendment 2026-08-24 — ✅ CHỐT · pre-activation receipt v1 erratum:** canonical `run_id`
> khớp chính xác `^msqa025-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}$`; `t`/`z` là separator
> lowercase literal. Semantic validator phải parse ID chính xác trong `fixtures.prefix` và fixture
> label ledger, rồi so byte-for-byte với root/Compose/cleanup; regex schema đơn lẻ không là proof
> cross-field. `project_name` phải bằng `run_id` byte-for-byte trên Compose, manifest, labels,
> receipt và cleanup; không sinh derived Compose ID. Không có compatibility alias cho `T`/`Z`
> uppercase: ID dạng cũ phải bị từ chối trước subprocess/resource creation. Amendment giữ nguyên
> `microsched.qa025.receipt.v1`; artifact lịch sử dạng uppercase, nếu có, không được rewrite và chỉ
> được đối chiếu bằng schema tại commit lịch sử của artifact đó.

> **📝 Cập nhật 2026-08-25:** Task 025 cung cấp hạ tầng disposable cell chạy local container. Đối với các đợt QA sau cut-over cần snapshot dữ liệu thật hoặc Migration Rehearsal, sử dụng thêm lane Ephemeral Neon Branch kết hợp `scripts.prepare_qa_branch` theo `AGENTS.md` §9.

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
- Hành vi Safari/installed PWA trên iPhone thật. Mục này giữ receipt riêng; machine token mặc định
  `NOT_RUN` (báo cáo cho người có thể hiển thị “NOT RUN”).

## 2. Safety boundary tuyệt đối

### 2.1 Đích duy nhất được phép

- App origin nhìn từ Chromium: reverse proxy **bên trong browser-runner container** chỉ nghe
  `http://127.0.0.1:<ephemeral-port>` và chỉ forward tới service cố định `app:8000`; không có option
  `--base-url` và không publish app ra host.
- DB: service DNS cố định `db:5432` bên trong run-scoped Compose network; **không publish DB port**.
- Docker resources: runner sinh một `run_id`/project name duy nhất dạng
  `msqa025-20260824t000000z-00000000`, khớp chính xác canonical regex ở amendment; mọi thao tác dọn
  chỉ dùng exact resource IDs trong hash-bound manifest ở §5.3, không discover-xoá theo prefix.
- Image: build từ root `Dockerfile` của exact `git rev-parse HEAD`, với
  `--build-arg GIT_SHA=<full SHA>`. Không bind-mount source vào app container.

Mọi service — `db`, `bootstrap`, `migrate`, `seed`, `app`, `browser` — phải publish **0 host port**,
chỉ nối **đúng một** Compose network `cell` có `internal: true`; không được tự sinh network
`default`, nối network ngoài, `network_mode: host|service:*|container:*`, privileged mode hay Docker
socket. Reverse proxy chỉ bind loopback **bên trong browser container**. Browser chỉ được request
đúng origin loopback vừa sinh; proxy không nhận upstream tùy ý và request khác phải bị abort, ghi
host đã redact rồi làm test fail. Image build/pull có thể dùng mạng trước khi secret được sinh;
runtime có secret thì chỉ tồn tại trên internal network.

### 2.2 Forbidden targets và input

Runner phải từ chối **trước lệnh Docker đầu tiên** nếu caller đưa bất kỳ option/biến cấu hình target
nào ngoài contract ở §2.1. Chỉ báo **tên biến**, không đọc/in giá trị.

Nhóm app/data bị cấm:

`DATABASE_URL`, `NEON_OWNER_URL`, `NEON_MIGRATOR_URL`, `CUTOVER_MIGRATOR_URL`,
`ALLOW_REMOTE_PG_TESTS`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_EMAILS`,
`PRIVATE_PIN_BOOTSTRAP`, `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CLAIMS_SUB`,
`FLY_API_TOKEN`, `FLY_APP`, `PLAYWRIGHT_BASE_URL`.

Nhóm có thể đổi Docker daemon/build/Compose target bị cấm toàn bộ ở parent environment:

`DOCKER_HOST`, `DOCKER_CONTEXT`, `DOCKER_CONFIG`, `DOCKER_CERT_PATH`, `DOCKER_TLS_VERIFY`,
`DOCKER_API_VERSION`, `DOCKER_DEFAULT_PLATFORM`, `BUILDKIT_HOST`, mọi `BUILDX_*`/`BUILDKIT_*`,
`COMPOSE_FILE`, `COMPOSE_PROJECT_NAME`, `COMPOSE_PROFILES`, `COMPOSE_ENV_FILES`,
`COMPOSE_PATH_SEPARATOR`, `COMPOSE_CONVERT_WINDOWS_PATHS`, và mọi `HTTP_PROXY`, `HTTPS_PROXY`,
`ALL_PROXY`/biến proxy không do runner sinh.

Nhóm có thể đổi repo/config/executable resolution bị cấm: mọi `GIT_*` từ parent (đặc biệt
`GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`,
`GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_COMMON_DIR`, `GIT_CONFIG*`, `GIT_EXEC_PATH`), cộng
`CDPATH`, `PYTHONPATH`, `PYTHONHOME`, `XDG_CONFIG_HOME`. `HOME`/`USERPROFILE` và
`XDG_RUNTIME_DIR` chỉ được giữ sau khi chứng minh là absolute local path của account hiện tại, không
UNC/network path, symlink/reparse vào worktree/temp khác.

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

### 2.3 Docker/Git command envelope — áp cho **mọi** lần gọi

Implementation phải có đúng một seam `run_docker(args)` và một seam read-only `run_git(args)`;
không module nào gọi `docker`, `docker compose`, `git` hoặc shell trực tiếp.

Trước **mỗi** Docker/Compose call, `run_docker` phải:

1. dựng mới child environment từ allowlist đóng, không clone `os.environ`: validated
   `SystemRoot`/`WINDIR`/`ComSpec`/`PATHEXT` trên Windows, validated `HOME`/`USERPROFILE`/
   `XDG_RUNTIME_DIR` khi platform cần, locale, và các giá trị **runner tự đặt** `PATH`, `TEMP`,
   `TMP`, `COMPOSE_DISABLE_ENV_FILE=1`, `COMPOSE_ANSI=never`; allowlist phải được so theo tên key
   case-insensitive trên Windows. Mọi key Docker/Compose/BuildKit/proxy khác vắng mặt, đặc biệt
   `DOCKER_HOST`, `DOCKER_CONTEXT`, `COMPOSE_FILE`, `COMPOSE_PROJECT_NAME`, `COMPOSE_PROFILES` và
   `BUILDKIT_HOST`;
2. gọi bằng argv list + `shell=False` + owned absolute `cwd`; không command string, alias, `.bat`
   shim từ worktree hoặc current-directory search;
3. dùng absolute `docker` executable đã resolve một lần, từ trusted local install root
   (Windows Docker Desktop; Linux `/usr/bin`/`/usr/local/bin`), không nằm trong repo/temp/UNC; ghi
   SHA-256 executable vào manifest. `PATH` child được dựng từ trusted executable/system dirs, không
   copy parent `PATH`;
4. với mọi engine/Compose command sau context discovery, chèn `--context <attested-name>` tường
   minh. Không dựa current context;
5. với mọi Compose command, chèn nguyên văn:
   `--project-directory <ABS_OWNED_QA_DIR> -f <ABS_BASE_COMPOSE> -f <ABS_GENERATED_OVERRIDE>
   --project-name <EXACT_RUN_ID>`. Hai file phải regular, không symlink/reparse, nằm trong repo hoặc
   run-temp do runner sở hữu; hash phải khớp manifest **trước mỗi call**. Không nhận compose path,
   profile hoặc project từ CLI/env;
6. ghi receipt argv đã redact + SHA-256 của sanitized environment key-set; không ghi env values.

`run_git` dùng absolute trusted `git` executable, sanitized environment không có parent `GIT_*`,
absolute `-C <EXPECTED_WORKTREE>`, và đối chiếu root do `Path(__file__).resolve()` suy ra với
`git rev-parse --show-toplevel`. `.git` worktree indirection phải trỏ vào đúng shared repo metadata;
alternate object/config/index/worktree path bị từ chối. Candidate SHA phải là 40 lowercase hex và
worktree clean trước build.

### 2.4 Local daemon/context attestation

Context discovery cũng chạy qua `run_docker` với sanitized env và chỉ đọc metadata. Không dùng
ambient current context: enumerate contexts rồi chọn đúng một pair trong allowlist đóng:

| Platform | Context | Endpoint bắt buộc |
|---|---|---|
| GitHub/Linux local daemon | `default` | `unix:///var/run/docker.sock` |
| Windows Docker Desktop Linux engine | `desktop-linux` | `npipe:////./pipe/dockerDesktopLinuxEngine` |
| Windows local engine fallback | `default` | `npipe:////./pipe/docker_engine` |

Nếu có nhiều pair hợp lệ, caller phải chọn bằng runner-owned platform policy (CI=`default`, Docker
Desktop Windows=`desktop-linux`), không bằng env/CLI. Context khác hoặc endpoint `tcp://`,
`http(s)://`, `ssh://`, TLS/cert path, UNC/network socket ⇒
`GUARD_DENIED`; không “thử xem có connect được không”. Qua explicit context, chạy `docker info`
read-only và bắt buộc server `OSType=linux`, non-empty daemon ID/name/version. Canonical object
`{context_name, endpoint, daemon_id, daemon_name, server_version, os_type}` được SHA-256 thành
`daemon_identity_sha256`; manifest/receipt chỉ lưu endpoint kind + endpoint hash, không credential.
Mọi mutable call và cleanup đều phải dùng cùng explicit context; trước cleanup re-attest identity
khớp byte-for-byte. Context/daemon đổi giữa run ⇒ `CLEANUP_GUARD_DENIED`, không xoá gì.

### 2.5 Secrets chỉ sống trong một run

- Dùng CSPRNG để sinh Postgres owner/app/migrator passwords, AES key, opaque session token và PIN 6
  chữ số cho từng run. Email fixture luôn thuộc `example.invalid`.
- Không đọc root/backend `.env`; `COMPOSE_DISABLE_ENV_FILE=1` chỉ được runner tự đặt; Compose files
  không có `env_file` và không interpolate biến deny-set. Chạy absolute/attested
  `docker ... compose ... config -q` trước `up` bằng envelope §2.3.
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
  browser-runner Dockerfile/proxy, executable receipt validator, QA-only locked dependencies và
  unit tests;
- `frontend/e2e/production-cell/**`: Playwright full-stack tests, không dùng mock routes;
- `frontend/package.json` chỉ nếu cần một script gọi lane; `.gitignore` chỉ nếu artifact path chưa
  được phủ. Ưu tiên `frontend/test-results/production-cell/<run_id>/`, vốn đã bị ignore.

Receipt schema source-of-truth đã commit tại `agent-tasks/025-qa-receipt.schema.json`; Phase A chỉ
được sửa schema đó bằng một dated spec amendment/review riêng, không tạo schema song song trong
`qa/`.

Không sửa `Dockerfile`. App service build thẳng file đó. QA helper có thể có Dockerfile riêng nhưng
không được thay thế image đang được test.

### 3.1 Thứ tự dịch vụ

1. **Preflight:** exact owned worktree/SHA, executable hashes, sanitized environment, local context/
   daemon identity, absolute Compose file hashes/project và config/network/port policy. Guard fail
   trước mutation có resource count 0.
2. **Build:** production app image với full SHA; lấy immutable image ID.
3. **DB:** `pgvector/pgvector:pg18`, data directory trên tmpfs, healthcheck bounded, không host port.
4. **Bootstrap:** one-shot owner helper tạo `microsched_migrator` và `microsched_app`, revoke public,
   schema `microsched` do migrator sở hữu, app chỉ có usage + DML. Không gọi
   `bootstrap_neon.py` vì script đó đọc `backend/.env`.
5. **Migrate:** one-shot production image chạy Alembic head bằng **migrator URL của cell**, rồi
   migrator revoke mọi DML của app trên `microsched.alembic_version`. Compose bắt buộc khai báo
   `app.depends_on.migrate.condition: service_completed_successfully` (cả `seed`/browser dependency
   chain cũng không được vòng qua gate). Orchestrator chỉ `up` target `migrate` trước; **chỉ sau exit
   0** mới được phát lệnh có target `app`. Nếu migrate exit non-zero, không app-create command nào
   được gọi và `docker inspect`/Compose inventory phải chứng minh app container không tồn tại, không
   running. Đây là migration rehearsal trên throwaway PG, không phải deploy migration.
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
9. **Cleanup:** đóng context/browser rồi re-attest daemon + hash-bound manifest; dọn exact resource
   IDs, temp secrets và helper process theo §5.3. Không dùng project/prefix discovery làm delete set.

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

### 3.3 Runtime network/port attestation

Static `compose config --format json` và runtime `docker inspect` phải cùng chứng minh:

- top-level chỉ có network `cell`, `internal=true`; không có `default`, external network hoặc
  service-level `network_mode`;
- **từng service** `db/bootstrap/migrate/seed/app/browser` có `ports=[]`, runtime
  `HostConfig.PortBindings` rỗng/null và `NetworkSettings.Ports` rỗng/null;
- từng container nối đúng một network ID, cùng exact ID của `<project>_cell`; network inspect có
  `Internal=true`;
- `total_ports_published=0`, `network_count=1`. One-shot containers phải được giữ tới lúc inspect,
  không `--rm` trước khi lấy receipt.

Thêm một port cho browser/one-shot hoặc bỏ explicit `networks: [cell]` để Compose sinh default phải
làm named guard test đỏ.

## 4. Synthetic fixture và smoke contract

Mọi label có prefix `[QA025:<run_id>]`; email là `qa025-<suffix>@example.invalid`. Trước subprocess
hay acceptance/resource mutation đầu tiên, runner phải lập fixture label ledger và parse chính xác ID
trong `fixtures.prefix` (literal form `[QA025:<run_id>]`) cùng mọi label ledger entry. Nó phải so raw
UTF-8 bytes với root `run_id`, `compose.project_name`, `cleanup.run_id` và `cleanup.project_name`;
không `.lower()`, Unicode normalization, replace hay derived Compose ID. Một ID lowercase vẫn hợp lệ
về grammar nhưng khác byte, ví dụ đổi duy nhất suffix `00000000` thành `00000001`, phải trả exit 40
`GUARD_DENIED` trước subprocess/resource creation và trước mutation acceptance. Receipt chỉ giữ
`fixtures.prefix` compact; ledger runtime có thể không ghi vào receipt. Không dùng tên/email/ngày thật.
Browser/API phải đi qua real app, **không `page.route` mock response**.

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

Timeout **không** có nghĩa phase chưa tạo gì. Khi timeout/cancel, runner chỉ inspect exact resource
IDs đã ghi trong verified manifest, rồi cleanup trong `finally`; label chỉ dùng xác thực ownership,
không dùng discovery/delete set. Cấm wildcard hoặc xoá resource ngoài manifest.

### 5.2 Taxonomy + exit code

Các token trong cột Status là **canonical machine tokens** duy nhất trong JSON/CLI. UI/Markdown có
thể hiển thị `NOT RUN`, nhưng phải map về `NOT_RUN` trước validate.

| Status | Exit | Nghĩa |
|---|---:|---|
| `PASS` | 0 | Mọi assertion cell pass và cleanup sạch |
| `FAIL_ASSERTION` | 20 | App/role/browser assertion sai |
| `BLOCKED_PREREQUISITE` | 30 | Docker/Compose/Node/browser chưa có; chưa chạy mutation |
| `GUARD_DENIED` | 40 | Input/target/env vi phạm; chưa tạo Docker resource |
| `CLEANUP_GUARD_DENIED` | 41 | Daemon/manifest/context đổi; không được xoá resource |
| `SETUP_TIMEOUT` | 50 | build/DB/migrate/ready quá hạn |
| `TEST_TIMEOUT` | 51 | browser phase quá hạn |
| `CLEANUP_TIMEOUT` | 52 | dọn quá hạn hoặc còn resource; luôn non-pass |
| `INFRA_ERROR` | 60 | lỗi công cụ không thuộc assertion |
| `NOT_RUN` | — | Token machine cho acceptance/sub-receipt chưa chạy |

Nếu test pass nhưng cleanup fail, final status là `CLEANUP_TIMEOUT`, không phải `PASS`.

### 5.3 Hash-bound run manifest + exact cleanup

Ngay sau preflight, trước mutation, ghi atomically `run-manifest.json` trong run directory. Object
canonical JSON (UTF-8, sorted keys, separators `,`/`:`, không field `manifest_sha256`) phải được
SHA-256; wrapper JSON ngoài chứa `payload` + `manifest_sha256`. Trước **mọi mutable command**, sau
mỗi resource create và trước cleanup, đọc lại và verify hash. Update resource IDs bằng atomic replace
rồi tính hash mới; không mutate file in-place.

Payload bắt buộc:

```json
{
  "schema": "microsched.qa025.run-manifest.v1",
  "run_id": "msqa025-...",
  "project_name": "msqa025-...",
  "git_sha": "<40 hex>",
  "docker_executable_sha256": "<64 hex>",
  "daemon_identity_sha256": "<64 hex>",
  "daemon": {"context_name": "desktop-linux", "endpoint_kind": "npipe", "endpoint_sha256": "<64 hex>", "daemon_id": "<non-empty>", "server_version": "<non-empty>", "os_type": "linux"},
  "compose": {"project_directory": "<absolute>", "files": [{"path": "<absolute>", "sha256": "<64 hex>"}]},
  "resources": {"containers": ["<full id>"], "networks": ["<full id>"], "volumes": ["<full name/id>"], "images": ["sha256:<digest>", "..."]}
}
```

Cleanup algorithm cố định:

1. lock run directory; verify manifest hash, run/project equality và Compose-file hashes;
2. re-attest exact daemon identity qua envelope §2.3; mismatch ⇒ `CLEANUP_GUARD_DENIED`, **0 delete**;
3. inspect từng exact ID, bắt buộc label `com.docker.compose.project=<project_name>` +
   `com.microsched.qa025.run_id=<run_id>`; missing label/foreign ID/tamper ⇒ guard denied, 0 delete;
4. stop/remove exact container IDs, exact network/volume IDs và chỉ image IDs ghi trong manifest;
   không `compose down`, `--remove-orphans`, prune, prefix/glob hoặc label-query dùng làm delete set;
5. verify từng exact ID absent. Project/resource lạ nằm ngoài manifest **không được chạm**.

Integration test bắt buộc tạo foreign sentinel project/resource với distinct run label trước cell;
sau cleanup, exact sentinel ID phải vẫn tồn tại/running và config hash không đổi, rồi test fixture tự
dọn sentinel trong một `finally` riêng. Manifest/project/resource ID bị sửa một byte phải làm cleanup
fail-closed `CLEANUP_GUARD_DENIED`, sentinel và cell resources đều chưa bị delete.

Nếu manifest/daemon guard từ chối cleanup, runner không được tự bypass để “cố dọn”: receipt giữ
`CLEANUP_GUARD_DENIED` + exact IDs đỏ hoá, in hướng dẫn recovery thủ công nhưng không chạy lệnh xoá.
Đây là khả năng còn resource có chủ đích để tránh xoá nhầm remote/foreign target; reviewer/owner chỉ
dọn sau khi đối chiếu daemon + manifest gốc bằng một thao tác riêng ngoài verdict của run.

### 5.4 Receipt JSON v1 — executable contract

Source-of-truth: `agent-tasks/025-qa-receipt.schema.json` (JSON Schema Draft 2020-12). Phase A phải
pin runtime-only `jsonschema` trong `qa/production-cell/requirements.lock` và cung cấp validator
`qa/production-cell/validate_receipt.py`. Exact command:

```text
python qa/production-cell/validate_receipt.py \
  --schema agent-tasks/025-qa-receipt.schema.json \
  --receipt frontend/test-results/production-cell/<run_id>/receipt.json
```

Validator phải dùng `Draft202012Validator.check_schema()` + `FormatChecker`, rồi validate instance.
Draft 2020-12 ở schema v1 chỉ chứng minh grammar cục bộ của từng field; `description` trong schema
phải nói rõ nó không chứng minh cross-field equality. Schema và semantic validator checklist phải
cùng enforce allowlisted pair ở §2.4; cụ thể `context_name=desktop-linux` ⇒
`endpoint_kind=npipe`, và fixture `desktop-linux+unix` phải fail. Sau schema, semantic pass bắt buộc
parse exact embedded ID từ `fixtures.prefix` và từng fixture label ledger entry, rồi so raw UTF-8
bytes (không case-fold/coerce/derive) để assert bằng root `run_id`, `compose.project_name`,
`cleanup.run_id` và `cleanup.project_name`; `fixtures.prefix` không chỉ pass regex. Semantic pass còn
bắt buộc kiểm: `ended_at >= started_at`; phase name không lặp và PASS có đủ chín phase; Compose file
roles đúng một `base` + một `generated_override`; daemon identity ở target/cleanup bằng nhau;
foreign-sentinel before/after config hash bằng nhau. Test negative bắt buộc copy receipt hợp lệ rồi
đổi duy nhất embedded fixture ID sang canonical lowercase khác (`...-00000001` khi root là
`...-00000000`): schema grammar có thể pass, nhưng semantic validator phải nonzero. Test preflight
label-ledger tương tự phải exit 40 `GUARD_DENIED`, không subprocess/resource/acceptance mutation.
Recursive redaction scan phải reject key (case-insensitive)
`database_url|owner_url|migrator_url|password|session_token|pin|aes_key|cookie|authorization|`
`container_env|env_dump` và string chứa `postgres://|postgresql://|*.neon.tech|*.fly.dev` hoặc email
ngoài `example.invalid`. Khi hợp lệ, in đúng
`receipt_schema=microsched.qa025.receipt.v1 status=<final_status>`. Không được chỉ parse JSON.

Lưu redacted receipt tại `frontend/test-results/production-cell/<run_id>/receipt.json`. Schema là
contract field/enum/required/conditional chính xác; PASS-shaped receipt có đủ các field sau:

```json
{
  "schema": "microsched.qa025.receipt.v1",
  "run_id": "msqa025-20260824t000000z-00000000",
  "target_class": "local_disposable",
  "git_sha": "0000000000000000000000000000000000000000",
  "image_id": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "started_at": "2026-08-24T00:00:00Z",
  "ended_at": "2026-08-24T00:01:00Z",
  "final_status": "PASS",
  "phases": [
    {"name": "preflight", "status": "PASS", "duration_ms": 1, "exit_code": 0},
    {"name": "build", "status": "PASS", "duration_ms": 1, "exit_code": 0},
    {"name": "database", "status": "PASS", "duration_ms": 1, "exit_code": 0},
    {"name": "bootstrap", "status": "PASS", "duration_ms": 1, "exit_code": 0},
    {"name": "migrate", "status": "PASS", "duration_ms": 1, "exit_code": 0},
    {"name": "seed", "status": "PASS", "duration_ms": 1, "exit_code": 0},
    {"name": "app_ready", "status": "PASS", "duration_ms": 1, "exit_code": 0},
    {"name": "browser", "status": "PASS", "duration_ms": 1, "exit_code": 0},
    {"name": "cleanup", "status": "PASS", "duration_ms": 1, "exit_code": 0}
  ],
  "docker_target": {
    "context_name": "default", "endpoint_kind": "unix",
    "endpoint_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "daemon_id_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "daemon_name_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "server_version": "28.0.0", "os_type": "linux",
    "daemon_identity_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "command_envelope": {
    "status": "PASS",
    "docker_executable_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "git_executable_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "sanitized_env_keys_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "rejected_parent_variable_names": [], "docker_call_count": 20, "compose_call_count": 10,
    "all_calls_used_sanitized_env": true, "all_calls_used_explicit_context": true,
    "all_calls_used_absolute_executable": true,
    "all_compose_calls_used_absolute_owned_files": true,
    "all_compose_calls_used_exact_project": true, "all_calls_used_shell_false": true
  },
  "compose": {
    "project_name": "msqa025-20260824t000000z-00000000",
    "project_directory_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "files": [
      {"role": "base", "sha256": "0000000000000000000000000000000000000000000000000000000000000000"},
      {"role": "generated_override", "sha256": "0000000000000000000000000000000000000000000000000000000000000000"}
    ],
    "config_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "network_name": "cell"
  },
  "safety": {
    "browser_origin": "runner-loopback:<redacted-ephemeral-port>",
    "ports_by_service": {"db": 0, "bootstrap": 0, "migrate": 0, "seed": 0, "app": 0, "browser": 0},
    "total_ports_published": 0,
    "networks_by_service": {"db": 1, "bootstrap": 1, "migrate": 1, "seed": 1, "app": 1, "browser": 1},
    "network_count": 1, "network_internal": true,
    "network_id_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "unexpected_networks": 0, "env_file_disabled": true, "outbound_requests": 0
  },
  "roles": {
    "status": "PASS", "app": "microsched_app", "migrator": "microsched_migrator",
    "ddl_denied": true, "alembic_write_denied": true, "app_role_only": true
  },
  "fixtures": {
    "status": "PASS", "prefix": "[QA025:msqa025-20260824t000000z-00000000]",
    "task_count": 2, "note_count": 1, "synthetic_domain": "example.invalid"
  },
  "migration_gate": {
    "status": "PASS", "fault_case": "none", "exit_code": 0,
    "service_completed_successfully": true, "app_create_command_issued": true,
    "app_created_before_success": false, "app_container_created": true,
    "app_container_running": true
  },
  "acceptance": {
    "025-SAFE-01": "PASS", "025-SAFE-02": "PASS", "025-SAFE-03": "PASS",
    "025-SAFE-04": "PASS", "025-SAFE-05": "PASS", "025-SAFE-06": "PASS",
    "025-SAFE-07": "PASS", "025-CELL-01": "PASS", "025-CELL-02": "PASS",
    "025-CELL-03": "PASS", "025-CELL-04": "PASS", "025-CELL-05": "PASS",
    "025-CELL-06": "PASS", "025-RED-01": "PASS", "025-CI-01": "NOT_APPLICABLE",
    "025-DEP-017": "NOT_APPLICABLE"
  },
  "cleanup": {
    "status": "PASS", "manifest_verified": true,
    "manifest_schema": "microsched.qa025.run-manifest.v1",
    "manifest_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "manifest_resource_ids_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "run_id": "msqa025-20260824t000000z-00000000",
    "project_name": "msqa025-20260824t000000z-00000000",
    "daemon_identity_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "delete_selection": "exact_manifest_resource_ids", "delete_command_count": 6,
    "tamper_detected": false,
    "residual_counts": {"containers": 0, "networks": 0, "volumes": 0, "images": 0, "helper_processes": 0},
    "foreign_sentinel": {
      "project_name_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "resource_ids_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "config_sha256_before": "0000000000000000000000000000000000000000000000000000000000000000",
      "config_sha256_after": "0000000000000000000000000000000000000000000000000000000000000000",
      "survived_cell_cleanup": true, "separate_cleanup_status": "PASS"
    }
  },
  "physical_iphone": {
    "acceptance_id": "Q025-DEVICE-IPHONE-01", "status": "NOT_RUN",
    "reason": "Physical iPhone acceptance is separate", "production_commit": null,
    "executed_at": null, "evidence": []
  }
}
```

Receipt cấm URL DB, env values, token, PIN, AES key, real email, container env dump và literal host
production. Root required fields/enums/conditionals nằm trong committed schema. Enum machine status
chỉ gồm
`PASS|FAIL_ASSERTION|BLOCKED_PREREQUISITE|GUARD_DENIED|CLEANUP_GUARD_DENIED|SETUP_TIMEOUT|TEST_TIMEOUT|CLEANUP_TIMEOUT|INFRA_ERROR|NOT_RUN`;
`final_status` cấm `NOT_RUN`. Acceptance value thêm `NOT_APPLICABLE`. Schema validator phải fail nếu
unknown field, required field thiếu, status viết `NOT RUN`, key cấm hoặc string forbidden target.
Riêng physical-iPhone sub-receipt có enum `PASS|FAIL|NOT_RUN` theo dated policy; `FAIL` ở đây không
được dùng làm `final_status` của cell.

## 6. Acceptance IDs cho implementer

- **025-SAFE-01 — Default deny:** mọi app/data target injection ở §2.2 trả `GUARD_DENIED` trước
  Docker; không có production URL option hoặc escape hatch.
- **025-SAFE-07 — Local Docker only:** remote/ambient daemon, context, BuildKit, proxy và Compose
  project/file/profile injection bị từ chối trước resource creation; mọi call dùng sanitized
  allowlist, trusted absolute executable, explicit attested local context, owned absolute files +
  exact canonical lowercase `run_id` làm project. `T`/`Z` uppercase bị từ chối trước subprocess/
  resource creation. Git/path indirection bị loại theo §2.3.
- **025-SAFE-02 — No ambient secret:** `.env` bị vô hiệu; secrets mỗi run không vào argv/log/git/
  receipt; gitleaks + receipt validator pass.
- **025-SAFE-03 — Network boundary:** mọi service có 0 published port, đúng một internal network và
  không default/external/host network; proxy chỉ bind loopback; browser có 0 outbound request.
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
  inventory exact-ID về 0; hash-bound manifest/daemon/resource labels khớp; foreign sentinel sống nguyên;
  tamper trả `CLEANUP_GUARD_DENIED` với 0 delete.
- **025-CELL-05 — Receipt:** committed schema + executable validator pass, đủ required fields/enums,
  canonical lowercase `run_id`; semantic parser bind byte-for-byte root/Compose/cleanup với exact ID
  trong `fixtures.prefix`/fixture label ledger (một lowercase ID khác phải đỏ); canonical `NOT_RUN`,
  phase/duration/daemon/migration/network/acceptance/cleanup, không secret/PII.
- **025-CELL-06 — Migration gate:** Compose khai báo `service_completed_successfully`; orchestrator
  không issue app-create trước migrate exit 0; injected exit non-zero chứng minh app absent/not running.
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

Nếu 017 chưa có, receipt ghi `025-DEP-017 = NOT_APPLICABLE`, không dựng fake outbox và không copy
file từ `feat/017-offline-outbox`.

## 9. 🚫 Không được làm

1. Không Neon/host DB/production URL, `.env`, real Google OAuth, real email/data, Chrome profile.
2. Không auth/PIN bypass route, test-only branch trong app, shared long-lived QA account hoặc PIN.
3. Không bật cron/push, không gửi outbound, không deploy, không `fly`, không production migration.
4. Không sửa `Dockerfile`, `fly.toml`, deploy workflow, app source, Alembic revision hoặc task 017.
5. Không publish port của bất kỳ service nào; không Docker socket/privileged/default/external/host
   network.
6. Không gọi Docker/Git ngoài command envelope; không dùng ambient daemon/context/BuildKit/Compose/
   proxy/Git/path config, remote endpoint, caller-supplied Compose file/profile/project hoặc relative
   executable/path.
7. Không gọi cleanup bằng Compose down, wildcard/project prefix, prune hoặc label-discovery delete
   set; chỉ exact IDs trong verified manifest trên re-attested daemon.
8. Không issue app-create/start trước migrator exit 0; migration non-zero không được để app container
   tồn tại hay running.
9. Không gọi local Chromium/iPhone/viewport là bằng chứng physical iPhone.
10. Không merge và không đổi required checks. Reviewers quyết định gate.

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
