# 017-QA — execution spec cho offline outbox + public read cache

> **Executor-agnostic · Bậc L2 · Trạng thái: DRAFT chờ adversarial review.**
>
> Đây là spec chạy QA độc lập cho `agent-tasks/017-offline-outbox.md`; nó không thay implementation
> spec và không mở lại product/architecture decision. Nguồn bắt buộc: `CLAUDE.md`, `AGENTS.md`,
> `agent-tasks/017-offline-outbox.md`, `docs/qa-framework.md`, `docs/frontend-brief.md`,
> `docs/ui-brief.md`, `docs/auth-brief.md` §4 R6 và `docs/tracking-brief.md` §8.1.
>
> Tài liệu này định nghĩa đúng **20 nhóm acceptance** ở §4. Một nhóm chỉ đạt khi có raw receipt từ
> đúng lane. Source review, local mock, CI, production và iPhone là các loại bằng chứng khác nhau;
> không loại nào tự thay được loại còn lại.

## 0. Mục tiêu, phạm vi và hard boundaries

QA phải chứng minh hai nửa cùng sống:

1. **Nửa đọc:** production PWA mở lại khi mất mạng vẫn render public shell + public cache, nhưng
   private plaintext không tồn tại trong persisted read cache và private gate luôn locked.
2. **Nửa ghi:** mọi write domain được 017 phủ đi qua typed outbox, retry đúng postcondition,
   idempotent khi mất response, không bị tab khác gửi trùng, rồi về queue `0` sau reconnect.

### 0.1 Không được làm trong lượt QA

- Không tạo migration, đổi schema hoặc tự sửa product contract. Thấy cần migration thì `BLOCKED` và
  dừng; 017 chốt **không migration**.
- Không đổi sang sync-engine, mirror entity vào Dexie, thêm Background Sync, hoặc coi cờ module là
  cross-tab lock.
- Không queue auth login/logout, private lock/unlock, web-push registration hoặc cron.
- `POST /api/push/subscribe` và `DELETE /api/push/subscribe` vẫn bypass; nhưng
  `POST /api/reminder-dispatch/{dispatch_id}/confirm` là write domain phải queue. Với `app_setting`,
  chỉ `show_list_price` và `subscription_expiry_lead_days` thuộc seam; `private_pin`,
  `private_unlock_throttle`, `private_unlock_ttl_minutes` phải bypass và **không bao giờ** được seam
  generic read/queue/write.
- Không sửa backend thành `204` khi DELETE không tìm thấy; classifier phải hiểu DELETE-vs-restore.
- Không lấy lane Playwright mặc định đang `serviceWorkers: 'block'` làm proof PWA.
- Không dùng `page.route(... route.fulfill())` cho request write ở khoảnh khắc đang chứng minh mạng
  thật đã bị cắt; route mock chỉ được dùng ở lane deterministic riêng.
- Không đọc cookie, password store, profile files, history hoặc secret. Không ghi email, PIN, token,
  connection string, dữ liệu cá nhân thật vào stdout, screenshot, report, commit hoặc PR.
- Không sửa/xoá dữ liệu production không do chính lượt QA tạo. Dữ liệu QA phải là synthetic và có
  prefix `QA017_`; cleanup chỉ nhắm đúng ID đã ghi trong manifest của lượt đó.

### 0.2 Quyền quyết định và điểm dừng kiến trúc

Chạm một trong các điều sau thì dừng toàn bộ implementation-related QA, giữ raw log và báo T1/chủ:

- core generic outbox vượt ngưỡng 400 dòng của implementation spec;
- xuất hiện merge/conflict resolution giữa hai phiên bản client/server;
- dependency một-cha không đủ, cần nhiều cha/đồ thị topo;
- optimistic layer bắt đầu mirror entity store thay vì overlay command lên Query cache;
- brief/spec mâu thuẫn về một postcondition cần test;
- acceptance chỉ có thể đạt bằng secret, personal data hoặc tài khoản không được giao.

Một lane bị lỗi môi trường hai vòng liên tiếp thì dừng **lane đó**, không đoán tiếp và không hạ chuẩn.
Ghi `[CHƯA VERIFY]` kèm nguyên lệnh, exit code, stderr/stdout và trạng thái thật trên đĩa/process.

## 1. Môi trường, dữ liệu và loại biên lai

### 1.1 Năm lane không được đánh tráo

| Lane | Dùng để chứng minh | Không chứng minh được |
|---|---|---|
| L0 — unit/static | typed classifier, sanitizer, queue state machine, lint/build | IndexedDB/SW/browser/PG thật |
| L1 — throwaway Postgres + API thật | idempotency, atomic reorder, row count/postcondition | production deploy, iPhone, real SW |
| L2 — production-build browser local | IndexedDB, real SW, Web Locks, offline transport, two-page race | Fly SHA, Neon, iPhone Safari/PWA |
| L3 — production HTTPS | revision thật, secure context, Fly/Neon/session/SW thật | bàn phím/safe-area và Safari iPhone nếu chạy desktop |
| L4 — iPhone của chủ | PWA Home Screen, airplane mode, reload, touch/safe area, reconnect | unit classifier coverage hoặc PG row-count inventory |

L0–L2 chạy trên worktree/branch code 017 đã implement. L3–L4 chỉ chạy sau khi T1 xác nhận revision
đã merge/deploy và `/api/readyz.commit` đúng SHA cần nghiệm thu, `db=up`. Executor QA không tự merge.

### 1.2 Fixture synthetic bắt buộc

Mỗi lượt tạo một `run_id` không chứa danh tính, ví dụ `QA017_20260815_A`. Manifest giữ các ID do
lượt đó tạo; không giữ cookie hoặc credential. Tập tối thiểu:

- một task/note/tracker public và một task/note/tracker private;
- public canary `QA017_PUBLIC_<run_id>`;
- private read-cache canary `QA017_PRIVATE_CACHE_<run_id>`;
- private pending-outbox canary `QA017_PRIVATE_OUTBOX_<run_id>`;
- chuỗi 70 ký tự không khoảng trắng, tiếng Việt khoảng 150 ký tự dấu dày, CHỮ HOA CÓ DẤU, emoji,
  một ký tự, thừa khoảng trắng hai đầu và toàn khoảng trắng;
- ít nhất 30 outbox-panel/domain rows hỗn hợp trạng thái để kiểm scroll/layout.

Canary private chỉ là dữ liệu giả. Report được ghi literal canary giả để chứng minh phép tìm kiếm,
nhưng không được chụp/ghi bất kỳ private data thật nào đã có sẵn trong tài khoản.

Mỗi case phá huỷ state (`lock`, TTL, logout, `401`, blocked/quota) phải dùng **BrowserContext/profile
và `run_id` riêng**. Setup ghi manifest before-state; cleanup chỉ xoá đúng server fixture/read-cache
do case đó tạo. Helper reset được phép reset RAM/read-cache/bootstrap nhưng **không được xoá hoặc
recreate outbox để làm xanh test**. Ngay sau setup/reset phải assert outbox canary vẫn còn trước khi
trigger destructive chạy.

### 1.3 State oracle bắt buộc

Test phải quan sát state bằng API/test helper typed hoặc browser-side IndexedDB trong chính origin;
không parse URL để suy ra `operation_kind`. Tối thiểu phải lấy được:

```text
queue: operation_id, operation_kind, resource, entity_id,
       dependency_operation_id, requires_private, state,
       attempts, next_attempt_at, last_error_code
read cache: query key, sanitizer type, serialized bytes/value
bootstrap: email-role marker, signed_in_at, expires_at, last_verified flag
transport: request method/path, client UUID, start/end/error category
clock: injected now, private_until boundary, session expires_at boundary,
       query maxAge boundary, build-SHA buster
```

Không log body chứa dữ liệu người dùng thật. Với production, chỉ log synthetic QA IDs, counter,
state/error code và timestamps đã làm tròn đủ để chứng minh thứ tự.

Với private outbox payload, oracle log **SHA-256 digest của canonical serialized payload + byte
length**, không log plaintext. Digest/length phải đủ để chứng minh payload không bị reset/purge làm
đổi trước khi flush; sau success thì chứng minh row đã biến mất thay vì dump nội dung.

**Canonical payload contract:** dùng RFC 8785 JSON Canonicalization Scheme (JCS), implement local
không thêm dependency. Adapter chỉ nhận JSON values; reject `undefined`, `BigInt`, `NaN`, `Infinity`
và object `Date`. Datetime phải được adapter đổi trước thành UTC ISO-8601 có milliseconds + `Z`;
date-only giữ `YYYY-MM-DD`. JCS sort object key theo UTF-16 code units, giữ array order, dùng JSON
number/string escaping chuẩn ECMAScript, không whitespace. Unicode code points giữ nguyên, **không**
tự NFC/NFD; bytes cuối là UTF-8 (`TextEncoder`). SHA-256 ghi lowercase hex.

`payload_sha256`/`payload_byte_length` được tính đúng một lần khi enqueue và là field immutable của
row. Trước mọi destructive reset, test tự tính cùng digest từ fixture input và giữ baseline trong
run manifest của Playwright/test process **ngoài IndexedDB/outbox row**. Mỗi checkpoint so ba phía:
external baseline = immutable row fields = digest recompute từ row payload; không được tính baseline
lại sau purge/reset. Golden tests bắt buộc có object đảo key order (digest bằng nhau), array đổi thứ
tự (digest khác), Unicode composed/decomposed (digest khác vì không normalize), datetime UTC exact,
và reject bốn non-JSON values trên. Không log canonical bytes/plaintext.

Các invariant gốc:

- persisted Query namespace và Dexie outbox là **hai namespace/DB riêng**;
- read cache chỉ public; private detail có `0` occurrence plaintext;
- outbox được phép giữ private pending vì đó có thể là bản duy nhất;
- rehydrate không mang quyền private và không persist `private_until`;
- một request tại một thời điểm trong lock; row hold/failed và descendants của nó không chặn row
  public độc lập;
- success duplicate chỉ từ contract replay `200`, không suy từ `409`.

## 2. Raw commands nền và quy tắc chạy

### 2.1 Kiểm baseline trước khi test

Chạy ở root worktree, dán raw output:

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse origin/develop
rg -n "serviceWorkers|webServer|baseURL" frontend -g "playwright*.config.ts"
rg -n "@router\.(post|patch|delete)" backend/app
rg -n "apiRequest<|apiRequest\(|fetch\(|XMLHttpRequest|sendBeacon|axios|ky" frontend/src -g "*.ts" -g "*.tsx"
rg --files frontend/tests frontend/e2e backend/tests
```

Nếu worktree có thay đổi không thuộc lượt QA, dừng trước RED proof. Không reset/xoá thay đổi của
người khác. Nếu frontend mới chưa có dependencies, chạy `npm ci` ở `frontend`, rồi kiểm
`npm ls --depth=0` trước khi kết luận install thất bại/timeout.

### 2.2 L0 — static, unit và build

```powershell
Set-Location frontend
npm run lint
npm run build
npm test
npm test -- outbox-write-manifest
npm run e2e -- --list
Set-Location ..\backend
uv run ruff check
uv run pytest
uv run pytest -vv tests/test_offline_outbox_manifest.py
Set-Location ..
```

Receipt phải có command, exit code và raw pass/fail summary. `--list` chỉ chứng minh discovery;
không được đổi nó thành execution receipt. Nếu test 017 nằm ở file riêng, report ghi thêm chính xác
lệnh targeted thực tế; placeholder hoặc `0 tests collected` không phải receipt.

### 2.3 L1 — Postgres/API thật

Docker Desktop là prerequisite do người chạy bật. Lane này dựng đúng một container throwaway
localhost; không được trỏ tới Neon/staging, không bật `ALLOW_REMOTE_PG_TESTS=1`, không downgrade hoặc
round-trip. Connection string được dựng từ biến local synthetic và không được echo.

Chạy ở root worktree; tên container/port cố định giúp kiểm target trước cleanup:

```powershell
docker info
$qaStartLocation = Get-Location
$qaPgName = 'microsched-017-qa-pg'
$qaPgPort = 55432
$qaPgOwnerUser = 'postgres'
$qaPgPassword = [guid]::NewGuid().ToString('N')
$qaPgDatabase = 'microsched_ci'
$qaMigratorUser = 'microsched_migrator'
$qaMigratorPassword = [guid]::NewGuid().ToString('N')
$qaAppUser = 'microsched_app'
$qaAppPassword = [guid]::NewGuid().ToString('N')
$qaPgCreated = $false
$qaPgSucceeded = $false
$qaProxy = $null
$qaProxyPid = $null
$qaEnvNames = @(
  'NEON_MIGRATOR_URL', 'DATABASE_URL', 'APP_ENV', 'OAUTH_STATE_SECRET',
  'ENCRYPTION_MASTER_KEY', 'SESSION_COOKIE_SECURE', 'ENABLE_INPROCESS_CRON',
  'ALLOW_REMOTE_PG_TESTS'
)
$qaEnvSnapshot = @{}
foreach ($qaEnvName in $qaEnvNames) {
  $qaExists = Test-Path "Env:$qaEnvName"
  $qaEnvSnapshot[$qaEnvName] = @{
    Exists = $qaExists
    Value = if ($qaExists) { (Get-Item "Env:$qaEnvName").Value } else { $null }
  }
}
$qaOldNativePreference = $PSNativeCommandUseErrorActionPreference
$qaOldErrorPreference = $ErrorActionPreference
$PSNativeCommandUseErrorActionPreference = $true
$ErrorActionPreference = 'Stop'

try {
  try { $qaExisting = docker container inspect --format '{{.Id}}' $qaPgName 2>$null }
  catch { $qaExisting = $null }
  if ($qaExisting) { throw "Container $qaPgName đã tồn tại; dừng để xác định chủ sở hữu" }

  docker run --name $qaPgName --rm -d `
    --health-cmd "pg_isready -U $qaPgOwnerUser -d $qaPgDatabase" `
    --health-interval 5s --health-timeout 5s --health-retries 10 `
    -e "POSTGRES_USER=$qaPgOwnerUser" `
    -e "POSTGRES_PASSWORD=$qaPgPassword" `
    -e "POSTGRES_DB=$qaPgDatabase" `
    -p "127.0.0.1:${qaPgPort}:5432" `
    pgvector/pgvector:pg18
  $qaPgCreated = $true

  $qaPgHealthy = $false
  foreach ($attempt in 1..20) {
    $qaPgState = docker inspect --format '{{.State.Health.Status}}' $qaPgName
    if ($qaPgState -eq 'healthy') { $qaPgHealthy = $true; break }
    Start-Sleep -Seconds 1
  }
  if (-not $qaPgHealthy) { throw 'QA017 Postgres unhealthy' }

  $qaRoleSql = @'
\set ON_ERROR_STOP on
\getenv migrator_password QA_MIGRATOR_PASSWORD
\getenv app_password QA_APP_PASSWORD
SELECT format(
  'CREATE ROLE microsched_migrator WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'migrator_password'
) \gexec
SELECT format(
  'CREATE ROLE microsched_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'app_password'
) \gexec
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
CREATE SCHEMA microsched AUTHORIZATION microsched_migrator;
REVOKE ALL ON SCHEMA microsched FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA microsched TO microsched_app;
ALTER DEFAULT PRIVILEGES FOR ROLE microsched_migrator IN SCHEMA microsched
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO microsched_app;
ALTER ROLE microsched_app SET search_path = microsched, public;
ALTER ROLE microsched_migrator SET search_path = public;
'@
  $qaRoleSql | docker exec -i `
    -e "PGPASSWORD=$qaPgPassword" `
    -e "QA_MIGRATOR_PASSWORD=$qaMigratorPassword" `
    -e "QA_APP_PASSWORD=$qaAppPassword" `
    $qaPgName psql -v ON_ERROR_STOP=1 -U $qaPgOwnerUser -d $qaPgDatabase

  $qaPrerequisites = docker exec -e "PGPASSWORD=$qaPgPassword" $qaPgName psql -At `
    -U $qaPgOwnerUser -d $qaPgDatabase -c @"
SELECT
  EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')
  AND EXISTS (
    SELECT 1
    FROM pg_namespace n
    JOIN pg_roles r ON r.oid = n.nspowner
    WHERE n.nspname = 'microsched' AND r.rolname = 'microsched_migrator'
  )
  AND has_schema_privilege('microsched_app', 'microsched', 'USAGE')
  AND NOT has_schema_privilege('microsched_app', 'microsched', 'CREATE');
"@
  if ($qaPrerequisites.Trim() -ne 't') { throw 'QA017 migration prerequisites invalid' }
  Write-Output 'migration_prerequisites=ok'

  $env:NEON_MIGRATOR_URL = "postgresql://${qaMigratorUser}:${qaMigratorPassword}@127.0.0.1:${qaPgPort}/${qaPgDatabase}"
  $env:DATABASE_URL = "postgresql://${qaAppUser}:${qaAppPassword}@127.0.0.1:${qaPgPort}/${qaPgDatabase}"
  $env:APP_ENV = 'local'
  $env:OAUTH_STATE_SECRET = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
  $qaEncryptionKeyBytes = [byte[]]::new(32)
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($qaEncryptionKeyBytes)
  $env:ENCRYPTION_MASTER_KEY = [Convert]::ToBase64String($qaEncryptionKeyBytes).Replace('+', '-').Replace('/', '_')
  $env:SESSION_COOKIE_SECURE = 'false'
  $env:ENABLE_INPROCESS_CRON = 'false'
  Remove-Item Env:ALLOW_REMOTE_PG_TESTS -ErrorAction SilentlyContinue

  Set-Location backend
  uv run python -m scripts.check_migration_drops
  uv run alembic upgrade head
  uv run alembic current

  docker exec -e "PGPASSWORD=$qaMigratorPassword" $qaPgName psql -At `
    -U $qaMigratorUser -d $qaPgDatabase -c "SELECT 'migrator_identity=' || current_user"
  $qaAppPrivilegeSql = @'
\set ON_ERROR_STOP on
SELECT 'app_identity=' || current_user;
SELECT 'app_crud_all_tables=' || COALESCE(bool_and(
  has_table_privilege(current_user, schemaname || '.' || tablename,
                      'SELECT,INSERT,UPDATE,DELETE')
), false)
FROM pg_tables
WHERE schemaname = 'microsched' AND tablename <> 'alembic_version';
DO $qa$
BEGIN
  BEGIN
    EXECUTE 'CREATE TABLE microsched.qa017_should_not_exist(id integer)';
    RAISE EXCEPTION 'app_ddl_unexpectedly_allowed';
  EXCEPTION
    WHEN insufficient_privilege THEN RAISE NOTICE 'app_ddl=blocked';
  END;
END
$qa$;
'@
  $qaAppPrivilegeSql | docker exec -i -e "PGPASSWORD=$qaAppPassword" `
    $qaPgName psql -At -U $qaAppUser -d $qaPgDatabase
  $qa017PgNodes = @(
    'tests/test_offline_outbox_pg.py::test_operation_matrix_covers_registry_exactly'
    'tests/test_offline_outbox_pg.py::test_operation_matrix'
    'tests/test_offline_outbox_pg.py::test_response_lost_entity_create_matrix'
    'tests/test_offline_outbox_pg.py::test_response_lost_calendar_import_atomic_replace'
    'tests/test_offline_outbox_pg.py::test_response_lost_subscription_renew'
    'tests/test_offline_outbox_pg.py::test_response_lost_reminder_confirm'
    'tests/test_tasks_api.py::test_task_crud_and_nested_items_through_http'
    'tests/test_notes_api.py::test_note_crud_nullable_title_checklist_restore_and_dto_boundary'
    'tests/test_settings_api.py::test_settings_allowlist_never_leaks_or_touches_secret_keys'
    'tests/test_settings_api.py::test_settings_valid_keys_validate_values'
    'tests/test_push_api.py::test_two_devices_confirm_same_dispatch_create_one_entry'
    'tests/test_push_api.py::test_private_dispatch_requires_unlock_then_accepts_same_body'
  )
  uv run pytest -m pg --collect-only -q $qa017PgNodes
  uv run pytest -m pg -vv $qa017PgNodes

  Set-Location $qaStartLocation
  Set-Location frontend
  npm run build
  Set-Location $qaStartLocation

  $qaExistingListener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 4180 `
    -State Listen -ErrorAction SilentlyContinue
  if ($qaExistingListener) { throw 'Port 4180 đã bị chiếm; dừng để xác định chủ sở hữu' }

  $qaProxy = Start-Process uv `
    -ArgumentList @('run','python','-m','tests.support.response_lost_proxy',
                    '--host','127.0.0.1','--port','4180','--static','../frontend/dist') `
    -WorkingDirectory (Resolve-Path 'backend') -WindowStyle Hidden -PassThru
  $qaProxyPid = $qaProxy.Id
  $qaProxyReady = $false
  foreach ($attempt in 1..20) {
    try {
      $health = Invoke-RestMethod 'http://127.0.0.1:4180/__qa__/health' -TimeoutSec 2
      if ($health.status -eq 'ok') { $qaProxyReady = $true; break }
    }
    catch { Start-Sleep -Seconds 1 }
  }
  if (-not $qaProxyReady) { throw 'response-lost proxy unhealthy' }

  Set-Location frontend
  npx playwright test --config=playwright.response-lost.config.ts e2e/offline-outbox-response-lost.spec.ts
  $qaPgSucceeded = $true
}
finally {
  try {
    Set-Location $qaStartLocation
    $qaTaskkillError = $null
    try {
      if ($qaProxyPid -and (Get-Process -Id $qaProxyPid -ErrorAction SilentlyContinue)) {
        taskkill /PID $qaProxyPid /T /F
      }
    }
    catch { $qaTaskkillError = $_ }
    finally {
      if ($qaProxyPid) {
        Wait-Process -Id $qaProxyPid -Timeout 10 -ErrorAction SilentlyContinue
      }
      $qaProxyParentRemaining = if ($qaProxyPid) {
        Get-Process -Id $qaProxyPid -ErrorAction SilentlyContinue
      } else { $null }
      $qaRemainingListener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 4180 `
        -State Listen -ErrorAction SilentlyContinue
    }
    if ($qaProxyParentRemaining -or $qaRemainingListener) {
      if ($qaTaskkillError) {
        throw 'taskkill lỗi và response-lost proxy parent/port 4180 vẫn còn'
      }
      throw 'response-lost proxy parent/port 4180 vẫn còn'
    }
    if ($qaTaskkillError) { Write-Output 'proxy_cleanup=taskkill_race_but_pid_and_port_gone' }
    else { Write-Output 'proxy_cleanup=stopped_and_port_free' }
  }
  finally {
    try {
      if ($qaPgCreated) {
        if (-not $qaPgSucceeded) { docker logs --tail 100 $qaPgName }
        $qaActualName = docker inspect --format '{{.Name}}' $qaPgName
        if ($qaActualName -ne "/$qaPgName") { throw "Refuse cleanup: unexpected container $qaActualName" }
        docker stop $qaPgName
      }
    }
    finally {
      foreach ($qaEnvName in $qaEnvNames) {
        if ($qaEnvSnapshot[$qaEnvName].Exists) {
          Set-Item "Env:$qaEnvName" $qaEnvSnapshot[$qaEnvName].Value
        }
        else { Remove-Item "Env:$qaEnvName" -ErrorAction SilentlyContinue }
      }
      $PSNativeCommandUseErrorActionPreference = $qaOldNativePreference
      $ErrorActionPreference = $qaOldErrorPreference
    }
  }
}
```

Receipt L1 phải có `docker info`, health=`healthy`, hai identity
`migrator=microsched_migrator`/`app=microsched_app` và app bị chặn DDL nhưng CRUD được,
`migration_prerequisites=ok`, Alembic head, raw
collect list và run summary; thêm API status/client UUID/SQL count đã redacted thành
`resource + qa_id + count`, không dán payload/DB URL. **Bất kỳ skip, deselected-all, `0 collected`,
exit 5 hoặc targeted cases còn thiếu đều là `[CHƯA VERIFY]`**, dù `pytest` thường xanh. Nếu command
timeout, kiểm `docker inspect/logs` và migration state trước khi kết luận. Cleanup chỉ stop đúng
`microsched-017-qa-pg` sau khi đã kiểm tên; tuyệt đối không dùng Neon để tái hiện lane này.

L1 cố ý **không** gọi `scripts.prepare_ci_database`: script CI hiện hành tự `CREATE SCHEMA` và do đó
cần identity bootstrap cao hơn migrator. Trong lane này, owner của đúng container throwaway chỉ tạo
extension/roles/schema rồi query bốn prerequisite; mọi Alembic DDL sau đó chạy bằng
`microsched_migrator`, còn app/proxy chỉ nhận `microsched_app`. Không được gán URL owner/superuser vào
`NEON_MIGRATOR_URL` để làm command “chạy được”.

#### OpenAPI route manifest → adapter registry → exact PG node

Set-equality giữa registry và PG matrix chưa đủ: một route bị bỏ khỏi **cả hai** vẫn làm meta-test
xanh. Implementation phải có một manifest language-neutral (chuẩn là
`frontend/src/lib/outbox-write-manifest.json`) chứa mọi route mutating do FastAPI OpenAPI runtime
trả về, theo khoá `METHOD + path template`. Mỗi row phải thuộc đúng một loại:

- `outbox`: có exact `operation_kind` và adapter typed;
- `bypass`: có lý do hard-boundary, chỉ gồm auth logout, private unlock/lock/PIN và push
  subscribe/unsubscribe;
- `key-gated`: riêng `PATCH /api/settings/{key}`, outbox chỉ cho `show_list_price` và
  `subscription_expiry_lead_days`; `private_pin`, `private_unlock_throttle`,
  `private_unlock_ttl_minutes` là bypass và không được đi qua generic seam.

`tests/test_offline_outbox_manifest.py` phải có fixture tự chứa, không đọc environment/secret thật:

```python
import secrets

monkeypatch.setenv("APP_ENV", "local")
monkeypatch.setenv("OAUTH_STATE_SECRET", secrets.token_urlsafe(32))
get_settings.cache_clear()
try:
    schema = create_app().openapi()
finally:
    get_settings.cache_clear()
```

Không có fixture này, default fail-closed `APP_ENV=production` làm bare `create_app()` dừng vì thiếu
`OAUTH_STATE_SECRET`; không được chữa bằng đọc `.env` hoặc in secret. Từ schema, test lấy toàn bộ
`POST/PATCH/DELETE` rồi assert set-equality exact `(METHOD, path template)` với manifest. Route mới
chưa phân loại phải làm test đỏ, kể cả khi nó chưa có trong adapter registry/matrix.

Set route thôi chưa đủ. Mỗi row `outbox` phải machine-assert exact tuple
`(METHOD, path template, operation_kind)` bằng metadata của typed adapter **và** param row PG matrix;
không cho `/api/tasks` bị map sang một adapter hiện hữu khác mà ba set vẫn xanh. Bypass test phải
assert exact method/path set chỉ gồm `POST /auth/logout`, ba private routes và push
subscribe/unsubscribe. Với `PATCH /api/settings/{key}`, manifest bắt buộc có hai field:

```text
allowed_keys = keys(PUBLIC_SETTING_SPECS)
bypass_keys = {PIN_SETTING_KEY, THROTTLE_SETTING_KEY, TTL_SETTING_KEY}
```

Python test import các constant thật để assert exact hai set; Vitest assert hai allowed key map đúng
hai `setting.*.update` adapter và ba bypass key không có adapter. Cuối cùng meta-test PG consume exact
route→operation rows từ manifest, không chỉ compare operation-name set. Receipt phải dán route count,
exact tuple diff và allowed/bypass-key diff khi lệch.

Ngoài manifest, static guard phải quét mọi transport (`apiRequest`, direct `fetch`,
`XMLHttpRequest`, `sendBeacon`, `axios`, `ky`) và fail nếu một write domain đi vòng seam. Direct
transport chỉ được tồn tại ở boundary đã allowlist có lý do; grep review bằng mắt đơn lẻ không thay
test manifest runtime.

#### Matrix route → `operation_kind` → exact PG node

`tests/test_offline_outbox_pg.py::test_operation_matrix` phải dùng param `ids=` đúng tên dưới đây;
meta-test `test_operation_matrix_covers_registry_exactly` assert **set-equality** giữa typed adapter
registry và toàn bộ ID trong matrix: không thiếu, không dư, không trùng. Nếu implementation thêm một
`operation_kind`, phải thêm exact row/node trước khi QA; không quay lại `-k`, regex hoặc “chạy cả file
chắc là có”.

| Route | Exact `operation_kind` → exact node suffix của `test_operation_matrix[...]` |
|---|---|
| `/api/tasks` · `/api/tasks/{id}` · `/restore` | `task.create` · `task.update` · `task.delete` · `task.restore` |
| `/api/tasks/{id}/items` · `/{item_id}` | `task_item.create` · `task_item.update` · `task_item.delete` |
| `/api/notes` · `/api/notes/{id}` · `/restore` | `note.create` · `note.update` · `note.delete` · `note.restore` |
| `/api/notes/{id}/items` · `/{item_id}` · `/positions` | `note_item.create` · `note_item.update` · `note_item.delete` · `note_item.reorder` |
| `/api/calendar/sources` · `/{id}` · `/import` | `calendar_source.create` · `calendar_source.update` · `calendar_source.delete` · `calendar.import` |
| `/api/calendar/events` · `/{id}` | `calendar_event.create` · `calendar_event.update` · `calendar_event.delete` |
| `/api/calendar/annotations` · `/{id}` | `day_annotation.create` · `day_annotation.update` · `day_annotation.delete` |
| `/api/tracker/groups` · `/{id}` | `tracker_group.create` · `tracker_group.update` · `tracker_group.delete` |
| `/api/tracker/trackers` · `/{id}` · `/restore` | `tracker.create` · `tracker.update` · `tracker.archive` · `tracker.restore`; node `tracker.update` phải có payload reminder config riêng |
| `/api/tracker/entries` · `/{id}` · `/restore` | `entry.create` · `entry.update` · `entry.delete` · `entry.restore` |
| `/api/subscriptions` · `/{id}` + actions | `subscription.create` · `subscription.update` · `subscription.cancel` · `subscription.uncancel` · `subscription.renew` · `subscription.delete` · `subscription.restore` |
| `PATCH /api/settings/show_list_price` | `setting.show_list_price.update` |
| `PATCH /api/settings/subscription_expiry_lead_days` | `setting.subscription_expiry_lead_days.update` |
| `POST /api/reminder-dispatch/{dispatch_id}/confirm` | `reminder.confirm` |

Mỗi value `kind` trong cột phải xuất hiện raw dưới node đầy đủ
`tests/test_offline_outbox_pg.py::test_operation_matrix[kind]` ở collect **và** execution output.
Hai test settings hiện hữu chứng minh ba key private không bị đọc/chạm; hai test task/note hiện hữu
neo task-item/note-item; hai test push hiện hữu neo same-dispatch và private hold. Một node skip,
missing, duplicate hoặc không execute ⇒ lane `[CHƯA VERIFY]`.

`test_response_lost_entity_create_matrix` cũng phải dùng exact param IDs và collect/run đủ:
`task.create`, `task_item.create`, `note.create`, `note_item.create`, `calendar_source.create`,
`calendar_event.create`, `day_annotation.create`, `tracker_group.create`, `tracker.create`,
`entry.create`, `subscription.create`. Task-item/note-item không được coi đã phủ chỉ vì parent create
xanh.

#### Harness response-lost chạy API/PG thật

`tests/support/response_lost.py` phải cung cấp core harness dùng được bởi bốn test
`test_response_lost_*` ở trên. L1 Python được dùng `httpx.ASGITransport`; lane đó chỉ chứng minh
server/PG, không được dùng làm browser/outbox receipt:

1. forward nguyên method/path/body vào **real FastAPI app** qua `httpx.ASGITransport`, với dependency
   DB trỏ container PG thật;
2. chờ upstream endpoint trả về và `await response.aread()`; bằng connection PG độc lập, poll có
   hạn tới khi commit probe thấy đúng row/dispatch/postcondition;
3. đóng upstream response rồi ném `httpx.ReadError`/abort downstream để client **không nhận status
   hay body**, nhưng server commit vẫn còn;
4. retry bằng transport bình thường, **cùng path + UUID/body bytes**; query PG lại.

Receipt bắt buộc: request digest/UUID, upstream-completed marker, commit probe + row count, client
abort exception, retry status/body contract và final row count. Cấm `route.fulfill()`, fake service,
mock DB hoặc “ném network error” trước khi real API commit; các cách đó không chứng minh response-lost.

Browser không gọi được `ASGITransport`. Vì vậy A10 bắt buộc thêm test-only HTTP/TCP reverse proxy
`backend/tests/support/response_lost_proxy.py` (tên khác phải ghi path thật) làm **chính browser
origin**: serve `frontend/dist`, forward `/api/*` vào real FastAPI + throwaway PG, và có control route
`/__qa__/response-lost/arm` chỉ trong test process. Control row arm đúng một
`METHOD + path + client UUID/payload digest`; proxy chờ upstream response + independent commit probe,
rồi đóng downstream socket không gửi status/body. Browser phải quan sát fetch abort thật
(`net::ERR_EMPTY_RESPONSE`/`TypeError` tương đương), không `route.abort()` hoặc fulfillment.

Lifecycle chuẩn nằm trong **cùng outer `try/finally` của L1 ở trên**: PG còn sống, cả
`NEON_MIGRATOR_URL` và app `DATABASE_URL` cùng trỏ PG local nhưng dùng **hai login role khác nhau**,
`APP_ENV=local`, OAuth secret và AES-256 `ENCRYPTION_MASTER_KEY` đều synthetic, cookie local và cron
tắt trước khi spawn proxy. Browser chạy xong mới `taskkill /T` exact proxy PID; dù `taskkill` race/non-zero,
`finally` vẫn chờ và assert parent + port 4180 đã biến mất. Chỉ sau đó mới stop PG và restore toàn bộ
env/location/preferences. Không được tách proxy/Playwright thành command chạy sau cleanup L1, không
được để proxy đọc key hay DB URL thật từ `.env`.

Dedicated Playwright config phải `baseURL=http://127.0.0.1:4180`, không reuse server/port, và fail
nếu port đã bị chiếm. Proxy chỉ nhận synthetic fixture; DB URL qua env local không được truyền trong
argument/stdout. Receipt gồm PID/origin/health, arm tuple đã redacted thành digest, upstream+commit
markers, browser abort category và process/port đã dừng. ASGI-only ⇒ L1 có thể pass nhưng A10 vẫn
`[CHƯA VERIFY]`.

### 2.4 L2 — hai browser config riêng

Lane UI deterministic hiện hữu có thể tiếp tục chặn SW:

```powershell
Set-Location frontend
npm run e2e -- --project=mobile e2e/offline-outbox.spec.ts
npm run e2e -- --project=desktop e2e/offline-outbox.spec.ts
```

Lane PWA phải dùng production build và dedicated config có `serviceWorkers: 'allow'`. Tên file có
thể khác, nhưng report phải ghi path/lệnh thật; ví dụ chuẩn:

```powershell
Set-Location frontend
npx playwright test --config=playwright.pwa.config.ts e2e/offline-outbox.pwa.spec.ts
Set-Location ..
```

Dedicated config phải tự build production, serve `dist` cùng một deterministic API origin/proxy,
`reuseExistingServer: false`, và fail nếu port đã bị process khác chiếm. Online seed/flush có thể đi
qua deterministic test server; **offline write proof không được dùng `route.fulfill()`**. Nếu không
có dedicated real-SW config, nhóm 12 và 13 là `[CHƯA VERIFY]` dù lane mock xanh.

Mỗi test storage/SW destructive mặc định tạo fresh `BrowserContext` + fixture server namespace theo
`run_id`. Nếu vì chi phí phải reuse context, `beforeEach` bắt buộc cleanup theo manifest rồi assert
baseline queue/server counts; mọi assertion dùng delta so với baseline, không hardcode `0/3` khi
fixture còn canary hợp lệ.

### 2.5 L3 — production revision gate

T1 cung cấp expected merged SHA; không lấy SHA từ một status board cũ.

```powershell
$ready = Invoke-RestMethod -Uri 'https://microsched.fly.dev/api/readyz' -TimeoutSec 15
$ready | ConvertTo-Json -Depth 5
```

Chỉ đi tiếp khi raw JSON có `commit` đúng expected SHA và `db` = `up`. Endpoint này tốn DB query;
chỉ gọi ở checkpoint, không poll dày và không đổi Fly health check sang `/api/readyz`.

## 3. Quy ước report và kết quả

Spec này không bị ghi đè bởi kết quả. Khi thực thi, append từng lô vào
`agent-tasks/017-qa-results.md` hoặc artifact append-only được T1 chỉ định. Mỗi lô có:

1. **Đã soi:** acceptance ID, lane, environment, SHA, viewport, fixture `run_id`, start/end.
2. **Raw receipts:** nguyên command/output cần thiết; payload riêng tư/secret được loại từ nguồn chứ
   không chụp rồi bôi đen sau.
3. **Finding:** `file:line` hoặc selector/state transition, số đo, mức, correction nhỏ nhất.
4. **Ảnh + taste nếu có:** path, hash, một câu mô tả banner/chữ đầu trang, 2–4 câu nhận xét.
5. **Kết luận từng ID:** đúng một trong `[ĐÃ CHẠY — PASS]`, `[ĐÃ CHẠY — FAIL]`,
   `[CHƯA VERIFY]`, `[BLOCKED]`.

`SUY LUẬN` chỉ giải thích; nó không tick acceptance. Local/CI/production/iPhone phải ghi nhãn đúng.

## 4. Hai mươi nhóm acceptance bắt buộc

### A01 — Happy path online và inventory mọi write domain

**Setup/steps:** online, ghi baseline queue; inventory mọi route create/patch/soft-delete/restore,
`*_item` và write đặc thù của **task, note, calendar, tracker, subscription, `app_setting` và cấu
hình reminder** (`reminder_time`/`reminder_text`). Calendar inventory gồm source/event/annotation/
import; tracker gồm group/tracker/entry/subscription/settings. Thêm đích danh
`POST /api/reminder-dispatch/{dispatch_id}/confirm` với metadata giữ `dispatch_id`, `entry_id`,
`occurred_at`. Thực hiện ít nhất một write mỗi `operation_kind`; auth, private unlock/lock,
push subscribe/unsubscribe và cron bypass có chủ đích. Settings seam chỉ inventory/queue hai key
allowlist; ba key private không được generic seam đọc/queue/write. Test atomic note-item reorder bằng
một request.

**PASS state:** API success được reconcile vào Query cache; queue trở lại baseline; không direct domain
write nào bypass typed seam; reorder hoặc thành công toàn bộ hoặc thất bại toàn bộ, không nửa-vời.
Online happy paths 008–011 vẫn xanh.

**Raw receipt:** route inventory trước/sau, request/status counter theo operation kind, queue
`baseline -> delta -> baseline`, test name/pass count. **FAIL/stop:** route domain chưa inventory,
subscription/setting/reminder config/reminder-confirm bị bỏ sót, private setting key lọt registry,
một direct
`apiRequest` không có comment bypass, placeholder không được thay bằng server response, hoặc reorder
gửi hai PATCH rời.

### A02 — Offline reload thấy public shell + public cache

**Setup/steps:** online một lần để có bootstrap và public snapshot; đợi persist hoàn tất; xác nhận SW
đã controller; cắt mạng bằng browser context, reload cứng.

**PASS state:** đúng một public shell render, public task/note/tracker canary hiện, banner
`Đang ngoại tuyến · dữ liệu lúc HH:mm` hiện; không card “Không kết nối được API” đè đồng thời lên
shell; không request mock giả thành công.

**Raw receipt:** `ready/controller` state, offline transition, reload URL, visible public IDs/banner,
query timestamp. **FAIL/stop:** chỉ client-side toggle `navigator.onLine`, không reload, shell đến từ
RAM chưa persist, hoặc route fulfillment che request thật.

#### Manifest Query persisted bắt buộc cho A03/A04

QA không được chọn tuỳ ý “một list đại diện”. `PERSISTED_QUERY_MANIFEST` phải phân loại exact mọi
query family thực sự mount trong fixture đi qua Tasks, Notes, Calendar, Tracker, Subscription và
Reminder Confirm. Baseline hiện tại phải có tối thiểu:

| Query key/family | Chính sách persisted bắt buộc |
|---|---|
| `['tasks', *]`, `['notes']` | lọc item `is_private=true`; sanitizer typed giữ nested public items |
| `['calendar','tasks',*]` | dùng cùng task sanitizer, không tạo bản sao logic khác |
| `['calendar','annotations',*]` | lọc annotation `is_private=true` |
| `['calendar','sources']`, `['calendar','events',*]` | public-only; persist và chứng minh canary còn |
| `['tracker','trackers']` | lọc tracker private; đây là tập public tracker ID nguồn cho các row VIA_PARENT |
| `['tracker','groups']` | giữ group public nhưng tính lại `tracker_count` chỉ từ tập public tracker ID |
| `['tracker','entries']` | chỉ giữ entry có `tracker_id` thuộc tập public tracker ID |
| `['subscription','subscriptions']` | chỉ giữ subscription có `tracker_id` thuộc tập public tracker ID |
| `['subscription','settings']` | chỉ giữ hai key public `show_list_price`, `subscription_expiry_lead_days` |
| `['tracker','dashboard',*]` | `never_persist`: aggregate hiện không đủ provenance để trừ phần private an toàn |
| `['session']` | không dehydrate như domain query; chỉ đi bootstrap tối thiểu riêng, không `private_until` |

Browser test phải harvest raw QueryCache keys sau khi đã mở đủ các màn, assert mỗi key khớp đúng
một row manifest và không có family ngoài manifest. Query mới mặc định `never_persist`, nhưng nếu nó
là public surface cần sống offline thì acceptance phải thêm sanitizer/row rõ ràng thay vì âm thầm
mất dữ liệu. Reminder Confirm hiện chỉ dùng `['session']`; nếu implementation thêm read query riêng,
harvest sẽ làm test đỏ tới khi phân loại.

### A03 — Mixed query persist thành public-only

**Setup/steps:** lúc unlocked, chạy từng row của manifest trên. Với mọi family private-bearing, seed
mixed public/private synthetic items; với row VIA_PARENT seed public + private tracker và child của
cả hai. Force persistence; đọc đúng Query persister namespace; reload offline/locked. Với row
public-only, seed public canary và chứng minh nó thật sự được persist. Với `never_persist`, seed một
canary rồi chứng minh query hash/value không nằm trên đĩa.

**PASS state:** mỗi serialized family được phép chứa public canary đúng một lần, private cache
canary `0` lần; group count khớp public trackers; entry/subscription chỉ còn parent public;
dashboard/session không lọt Query snapshot; rehydrated UI chỉ có public. Sanitizer phải typed theo
query key/item, query mới mặc định không persist; không dùng recursive generic blocklist.

**Raw receipt:** toàn bộ harvested key + manifest policy, before/after item counts, public-parent ID
set, persisted/never-persist result và UI locator counts. **FAIL:** thiếu một key đang mount, chỉ
chứng minh private row bị CSS ẩn, sanitizer VIA_PARENT không neo public tracker set, hoặc quét nhầm
outbox namespace.

### A04 — IndexedDB private plaintext = 0 occurrence/0 byte match

**Setup/steps:** persist private detail và từng private-bearing family trong manifest (task, note,
annotation, calendar-task, tracker, entry, subscription, group count/dashboard aggregate); quét
byte/string toàn bộ **read-cache namespace** bằng unique private canary sau flush-to-disk. Quét tên
store/key/value, không chỉ một object đã biết.

**PASS state:** `TextEncoder`/string scan trả `occurrences=0`, `matching_bytes=0` trong read cache;
private detail không dehydrate. Outbox namespace được báo riêng, không cộng nó vào invariant này.

**Raw receipt:** DB/store names, bytes scanned, occurrence/matching-byte count; không dump toàn bộ
record. **FAIL/stop:** scanner chỉ đọc RAM, chỉ tìm field `is_private`, hoặc canary xuất hiện ở read
cache dù UI locked.

**Negative trước boot:** trong fresh context, (a) chặn `indexedDB.open` và (b) cho write đầu tiên ném
`QuotaExceededError`. Cả hai case phải chạy trước khi module app boot. App online vẫn render và write
thẳng server được; hiện cảnh báo người-đọc-được “Không thể lưu ngoại tuyến”,
không crash bundle và không giả rằng write đã queue. Receipt gồm console/page-error count, warning,
online request/status và queue unavailable state. Nếu chỉ monkeypatch sau khi DB đã mở thì chưa đạt.

### A05 — Purge lock/TTL/logout/401 giữ private outbox canary

Chạy các case độc lập, mỗi case có fresh BrowserContext/profile, `run_id` và reset manifest riêng.
Trước boot cài Playwright fake clock (`page.clock.install`) hoặc injected `now()` seam; không dùng
sleep 36 phút. Với case TTL, mốc là **`private_until` 36 phút** của private gate, không phải
`session.expires_at` của login session. Setup tạo private outbox row rồi ghi
`payload_sha256 + payload_byte_length`; reset read surface phải giữ đúng digest/length đó.

| Trigger | Read cache/RAM/bootstrap sau trigger | Outbox private canary |
|---|---|---|
| lock tay | private bị purge, public snapshot còn | còn đúng 1 |
| `private_until` 36 phút hết | private bị purge, public snapshot còn | còn đúng 1 |
| logout | toàn bộ Query namespace + bootstrap bị purge | còn đúng 1 |
| **canary flush request** nhận `401` | classifier không tự xoá payload | đúng row đó `auth_hold`, digest/length nguyên |
| session query/global auth handler nhận `401` | purge RAM + toàn bộ Query namespace + bootstrap | outbox vẫn còn; auth-held rows không đổi payload |

Privacy response exact cũng phải đi qua central `purgePrivateSurface()`, không rải logic theo màn.

Hai case `401` là hai oracle riêng: việc row chuyển `auth_hold` thuộc flusher/classifier; purge
session/query thuộc central unauthenticated handler. Có thể cùng một response kích cả hai, nhưng test
phải assert riêng và không suy “purge thành công” từ mỗi state row. Sau login/unlock lại, flush chính
canary đó: digest/byte length ở request canonical phải bằng before;
server có đúng một row; outbox row mới được remove sau success. Không log plaintext payload.

**Raw receipt:** injected clock/timeline, context/run manifest, before/after counts cho RAM, read DB,
bootstrap và outbox; digest/byte length before reset, after purge/hold và at flush. **FAIL:**
`Dexie.delete()`/database delete chạm outbox; lock xoá public offline cache; logout/401 xoá private
pending payload; reset helper xoá/reseed outbox; digest đổi; hoặc chỉ reload UI mà bytes vẫn nằm trên
disk.

### A06 — Offline bootstrap luôn locked và không có `private_until`

**Setup/steps:** cài fake clock/injected `now()` **trước app boot**, online tạo bootstrap + public
Query snapshot tại `t0`, inspect serialized keys/bytes. Tách hai loại test, vì `private_until` chỉ
sống trong RAM còn ba boundary kia kiểm persisted snapshot:

- **Private TTL:** dùng **cùng một online BrowserContext/page/RAM state**, không reload/new context.
  Nhận `/api/me` unlocked tại `t0`, advance cùng fake clock tới `t0+35:59`, rồi `t0+36:01`; lần sau
  phải purge/relock. Fresh context ở đây chỉ chứng minh bootstrap locked sẵn, không chứng minh timer
  TTL đã chạy.
- **Persisted boundaries:** `session.expires_at`, Query `maxAge` và build-SHA buster mỗi case dùng
  fresh context nhận một bản persisted fixture snapshot riêng; không chạy nối tiếp bằng wall-clock.

| Clock/boundary | Expected |
|---|---|
| `private_until`: `t0+35:59` / `t0+36:01` trong cùng online context | trước còn grant RAM; sau purge/relock; key này không có trên disk |
| `session.expires_at`: `-1ms` / `+1ms` | trước public shell eligible; sau “Cần kết nối để xác thực lại” |
| Query `maxAge`: `7d-1ms` / `7d+1ms` | trước public snapshot hydrate; sau snapshot bị loại, không tự kéo dài session |
| build-SHA buster đổi trong `maxAge` | Query snapshot cũ bị loại deterministic; session validity vẫn chỉ theo `expires_at` |

**PASS state:** bootstrap chỉ có identity marker tối thiểu, `signed_in_at`, `expires_at`, last-verified
flag; không có key/value `private_until`, PIN hay unlock grant; trước expiry render public shell ở
state locked, không có unlock action; sau expiry hiện “Cần kết nối để xác thực lại” và không render
domain shell. Query cache `maxAge=7 ngày`, build-SHA buster và session expiry là ba oracle riêng;
không lấy cache còn hạn làm bằng chứng session còn hạn, và buster không kéo dài expiry.

**Raw receipt:** fake-clock install time + injected times, key list, `private_until occurrences=0`,
gate state, query hydrate/evict counts, buster before/after và từng render assertion. **FAIL:** dùng
sleep/wall-clock flake, dùng fresh context để claim TTL timer, nhầm `private_until` với
`session.expires_at`, cached session rehydrate thành unlocked, hoặc expiry/maxAge được tính lại từ
reload/build time.

### A07 — Route-aware classifier, retry và `outcome_unknown`

Unit table phải truyền typed metadata (`operation_kind`, `resource`, `requires_private`,
`idempotency_mode`, `dependency_operation_id`), không chỉ status:

| Input | Expected transition/postcondition |
|---|---|
| network/timeout/408/425/5xx | retry 1→2→4→8→16→30s, không park vì attempts |
| `429` | retry theo `Retry-After` hợp lệ; test cả seconds và HTTP-date hoặc ghi rõ parser contract |
| `401` | `auth_hold`, attempts không tăng, giữ queue/outbox, dừng tới login |
| exact `PRIVATE_UNLOCK_REQUIRED` 403 | `private_hold`, không retry tới unlock |
| private 404/409 khi client biết locked | `private_hold`; unlock rồi còn 404/409 thì `failed` |
| public/unlocked DELETE 404 | postcondition đạt, remove row |
| restore 404 | `failed` (hoặc private hold nếu gate giải thích), không coi success |
| business 400/409/422 | `failed`, giữ lỗi gốc, không auto-retry |
| create 409 | không bao giờ tự coi duplicate success; replay đúng phải là server `200` |
| `outcome_unknown` sau dispatch | giữ cùng operation/client UUID/payload; retry idempotent, không sinh command mới |

`not_attempted` và `outcome_unknown` phải phân biệt được trong receipt/telemetry; cả hai không được
nuốt payload. **Raw receipt:** mỗi row có input metadata, prior state, next state, attempts,
`next_attempt_at`, error code và test PASS. **FAIL:** một global `status -> action` table, so chuỗi
message, `Retry-After` bị bỏ, hoặc >50 attempts tự park.

Trước classifier phải có **một central HTTP error normalizer**. Test API/fixture thật phải thu raw
`status + JSON envelope/detail` synthetic từ ít nhất task, note, tracker, calendar, subscription và
`POST /api/reminder-dispatch/{dispatch_id}/confirm`,
sau đó ghi normalized machine code/kind mà typed classifier nhận. Bao phủ privacy response khác
status (`403/404/409`) và business/validation (`400/409/422`); riêng confirm phải có raw 403
`detail.code=PRIVATE_UNLOCK_REQUIRED`, dispatch 404 và business/config 409. Không cho từng screen tự
parse text. Raw receipt được phép giữ error code/detail synthetic nhưng không private payload. Nếu
classifier được gọi trực tiếp bằng object tự chế mà không chứng minh envelope→normalizer, subcase
này là `[CHƯA VERIFY]`.

### A08 — `dependency_operation_id` trỏ operation row

**Setup/steps:** offline tạo chain group G → tracker T → entry E trong một Dexie transaction; parent
đã có server có dependency `null`; parent queued thì child trỏ đúng primary key outbox của create
parent, không trỏ entity UUID. Chạy thêm response-lost case: G đã dispatch/commit nhưng row G đang
`outcome_unknown`, T/E còn `pending`; đặt một public row P độc lập phía sau.

**PASS state:** flush G→T→E đúng order; child không gửi vượt parent hold; parent failed làm
descendants `suppressed` và UI chỉ hiện một lỗi gốc; discard parent discard descendants; independent
row vẫn runnable. Khi G=`outcome_unknown`, request count T/E bằng `0` nhưng P vẫn gửi; replay **G
trước** cùng UUID/payload. G replay `200` mới release T rồi E; nếu replay G thành failure thật thì
T/E mới `suppressed`.

**Raw receipt:** operation IDs/entity IDs/dependency IDs, transaction boundary, request order và
state cascade gồm `outcome_unknown → replay → release/suppress`. **FAIL:** dependency suy từ URL/
parent UUID, descendant gửi khi parent outcome chưa biết, outcome-unknown chặn public độc lập, hoặc
discard để orphan row.

### A09 — Private-held không chặn public độc lập

**Setup/steps:** chạy ba case tách biệt với fresh context: (a) gate locked, enqueue private parent +
descendant rồi public row độc lập; (b) session hết hạn tạo `auth_hold` + descendant rồi public row;
(c) business 422 làm parent `failed`. Kích flush, sau đó unlock/login/discard theo đúng case.

**PASS state:** (a) parent và descendants đều exact `private_hold`, public row vẫn gửi/remove; unlock
đưa cùng chain về runnable và gửi theo dependency; (b) parent + descendants exact `auth_hold`, login
đưa chúng về runnable; (c) chỉ parent exact `failed`, descendants exact `suppressed`. Discard parent
xoá toàn bộ descendants trong cả ba case, nhưng không xoá public độc lập. Sau unlock, nếu server còn
404/409 thì parent thành `failed` và descendants thành `suppressed`, không coi success.

**Raw receipt:** insertion order, exact state từng operation ID trước/sau điều kiện được giải,
request order và cascade sau fail/discard. **FAIL:** dùng chung chữ “hold/suppressed”, descendant
private/auth bị suppress vĩnh viễn, descendant failed còn runnable, FIFO toàn cục đứng vô hạn, hoặc
flusher gửi private khi locked.

### A10 — Response-lost idempotency trên mọi POST create được phủ

Mọi case dùng harness response-lost §2.3 và có **hai receipt nối nhau**: L1 chứng minh real API + PG
commit/replay contract; browser/outbox lane gọi HTTP/TCP proxy cùng section để chứng minh state
client. Ngay trước dispatch ghi `operation_id`, `attempts=A`, client UUID/path và payload digest.
Proxy chỉ abort sau upstream-completed + commit-probe. Ngay sau client nhận network abort phải assert
cùng row:

```text
state = outcome_unknown
operation_id/client UUID/path/payload digest = không đổi
attempts = A + 1
next_attempt_at = mốc backoff hữu hạn đã inject clock
```

Chỉ sau assertion này mới tiến clock và retry cùng bytes; server `200` replay mới được remove row.
Case đối chứng cắt mạng/Web Lock trước dispatch phải ghi `not_attempted`, attempts vẫn `A`, không có
upstream marker và không được đổi thành `outcome_unknown`. Route fulfillment, fake DB hoặc unit
classifier object không thay hai receipt trên. Tách bốn contract, không ép mọi POST vào cùng khuôn:

1. **Entity UUID create:** inventory toàn bộ create sau 010/011; gửi cùng client UUIDv7/payload,
   mô phỏng commit rồi response mất, retry đúng command. Tối thiểu task-item, note-item,
   calendar-event và mọi entity create còn lại: first `201`, replay `200`, SQL count `1`; replay
   không update payload cũ. UUID khác nhưng business name trùng chỉ `409` cho
   `calendar_source`, `tracker_group`, `tracker`, `subscription` theo contract hiện hữu. Task,
   note, calendar-event, day-annotation, entry và item phải chứng minh cùng title/label/content vẫn
   được phép tạo row khác; 409 ở các resource đó là lỗi test hoặc conflict UUID thật, không phải
   duplicate-name success.
2. **Calendar import:** queue đúng một normalized `ImportRequest`, không một row/event. Mất response
   rồi replay **cùng normalized request**; replace-all chạy atomic, response theo contract, final
   normalized event set/count giống hệt và không duplicate/partial old+new set.
3. **Subscription renew:** mất response sau renew, retry cùng `entry_id`; cả hai response theo
   contract `200`, lượt replay `created=false`, subscription `expires_on` và `status` không tiến
   thêm/đổi sai (fixture active phải vẫn `active`), SQL chỉ một entry và post-commit side effect
   không phát lại.
4. **Reminder confirm:** queue giữ nguyên path `dispatch_id` và body `entry_id + occurred_at`. Sau
   commit-response-lost, retry đúng path/body trả `200`, `created=false`,
   `confirmed_entry_id` bằng Entry đã commit và SQL có đúng một Entry. Private dispatch lúc locked
   trả 403 exact code, không tạo Entry, row `private_hold`; unlock rồi retry cùng body tạo đúng một.
   Cùng `dispatch_id` nhưng retry/body cạnh tranh dùng `entry_id` khác vẫn là occurrence-level
   idempotency: first committed Entry thắng, response sau `created=false` + ID của winner; không tạo
   Entry thứ hai và `occurred_at` của loser không được ghi đè.

**Raw receipt:** route inventory, operation state timeline trước dispatch → `outcome_unknown` →
remove, QA UUID/normalized-request digest/dispatch_id/entry_id/occurred_at, upstream-completed +
commit-probe + client-abort, retry status + `created`, per-table/event-set count,
expiry/status before/after và side-effect counter. **FAIL/stop:** row ở `pending`/`not_attempted` sau
abort đã dispatch, attempts/digest/UUID không khớp timeline, route
entity create chưa nhận client UUID, retry sinh UUID mới, import tạo per-event commands hoặc partial
replace, renew tăng hai kỳ/`created=true` lần hai, confirm làm rơi/đổi ba field hoặc tạo Entry thứ
hai, duplicate count >1, hoặc test dùng route fulfillment/mock DB/abort trước commit.
Không sửa schema để cứu lane.

### A11 — Web Locks với hai tab thật

**Setup/steps:** dùng hai `Page` trong cùng `BrowserContext`/origin/IndexedDB; cả hai cùng thấy một
pending command và cùng nhận `online`; quan sát lock `microsched-outbox-flush` và server request
counter. Không thay bằng hai Promise trong một module.

**PASS state:** đúng một tab sở hữu lock ở một thời điểm, đúng một request cho command, tab còn lại
chờ rồi reload queue, cả hai cuối cùng thấy queue `0`. Khi `navigator.locks` bị thiếu trong test
negative, không tab nào flush cạnh tranh; UI cảnh báo và queue giữ nguyên.

**Raw receipt:** page IDs, lock acquisition/release timestamps, request count `1`, final counts ở cả
hai page. **FAIL:** module flag là proof chính, hai page dùng storage khác context, hoặc count >1.

### A12 — Lane production-build có real SW và offline transport thật

**Setup/steps:** dùng dedicated config `serviceWorkers: 'allow'`; mỗi test dùng fresh context/profile
và fixture namespace, hoặc cleanup theo manifest rồi assert baseline queue/server counts. Build
production; load một lần; chờ `navigator.serviceWorker.ready`, reload nếu cần tới khi
`navigator.serviceWorker.controller` có giá trị; chỉ sau đó gọi `context.setOffline(true)`. Trigger
write qua UI và assert delta so với baseline.

**PASS state:** receipt lần lượt là `ready=true`, `controller=true`, `offline=true`; shell/font/assets
từ real precache; write API abort/fail transport thật và command vào outbox. Không `route.fulfill()`
cho write này; test fail nếu SW blocked hoặc controller null.

**Raw receipt:** config path/excerpt, production build summary, registration scope/controller script
URL, context/run ID + baseline, Playwright offline state, request failure/abort category, queue delta.
**FAIL/stop:** vite dev,
`serviceWorkers:'block'`, chỉ `ready` không controller, hoặc synthetic thrown error không qua fetch.

### A13 — End-to-end offline write rồi reconnect về queue 0

Chạy hai flow trong fresh contexts/fixture namespaces; gọi baseline queue là `B`, không mặc định `0`:

1. **Public:** sau A12, offline reload, tạo representative public task, note và entry; kiểm
   optimistic UI; reload offline lần nữa; bật online. Expected queue
   `B -> B+3 -> B+3 after reload -> B`; coordinator cancel refetch liên quan, flush, reconcile rồi
   mới invalidate.
2. **Private reminder-confirm synthetic E2E:** fixture tạo private tracker + dispatch; online unlock,
   mở confirm route, chuyển offline rồi submit. Outbox row giữ `operation_kind=reminder.confirm`,
   path `dispatch_id`, body `entry_id + occurred_at` và canonical `payload_sha256 + byte_length`
   nhưng không log plaintext. Reload fresh page trong cùng storage khi offline ⇒ bootstrap/gate
   locked, private Entry không overlay/không lộ trong read cache/UI, outbox digest vẫn nguyên.
   Expected queue `B -> B+1`; reload giữ `B+1`. Reconnect khi còn locked ⇒ raw confirm 403 được
   normalize thành `private_hold`, server Entry count vẫn 0 và queue còn `B+1`; unlock online ⇒ gửi
   cùng `dispatch_id + entry_id + occurred_at`, server đúng một Entry, response created đúng contract
   và queue về `B`.

**PASS state:** optimistic public entities không bị refetch ghi đè; server response thay placeholder;
server có đúng một row mỗi QA UUID; public cache sau invalidate khớp server. Chuỗi unsent
create→absolute-patch→delete coalesce về baseline; side-effect operations không coalesce. Private
flow chứng minh đồng thời “outbox giữ” và “locked UI/read cache không lộ”.

**Raw receipt:** context/run manifest, baseline/delta queue timeline, payload digest/byte length,
request order/status, dispatch/entry/occurred identity, gate/hold states, private locator/read-cache
occurrence `0`, UI entity state trước/sau reload, server/API count và final invalidate. **FAIL:**
hardcode queue `0/3` khi fixture có
canary, queue indicator ẩn trong khi rows còn, reset xoá outbox, private overlay khi locked, digest
đổi/confirm fields đổi, UI hiện synced trước server success, polling/refetch xoá optimistic row,
duplicate server row,
hoặc online+unlock nhưng queue không về baseline.

### A14 — UI state, microcopy và khả năng thoát lỗi

Kiểm đúng các state: `chờ mạng`, `cần đăng nhập`, `cần mở khoá riêng tư`, `gửi thất bại`, pending `0`
và nhiều mục. Bắt buộc selector: `outbox-indicator`, `outbox-panel`, `outbox-item`,
`outbox-item-discard`, `offline-banner`.

**PASS state:** indicator “N đang chờ gửi” ẩn ở `0`, mở được panel; failed item có lý do người đọc
được + `Xoá bỏ`; discard rollback và kéo descendants; optimistic failed entity có badge
“Chưa gửi được”; validation/business failure không có nút retry giả; auth/private hold tự chạy lại
khi điều kiện đạt. Toast Hoàn tác 10 giây giữ contract. Không lọt từ kỹ thuật `payload`, `entity`,
`sync engine`, `outcome_unknown`; error nói chuyện gì + làm gì tiếp, vẫn visible khi panel/dialog đóng.

**Raw receipt:** state→visible copy/selector table, action/result, aria-live/focus return. **FAIL:**
trạng thái chỉ phân biệt bằng màu, hành động chỉ hover, private entity name lọt vào copy locked, hoặc
discard không rollback.

### A15 — Viewport chính 390 × 844 và touch metrics

**Setup/steps:** Chromium mobile project đúng 390×844 + touch và ít nhất một pass trên iPhone ở A18;
đọc `window.innerWidth/innerHeight`, không tin resize receipt. Dùng dữ liệu dài + 30 rows, panel mở ở
cuối màn.

**PASS state:** `innerWidth=390`; scroll ngang `0`; action chính ≥44×44 CSS px, tuyệt đối không dưới
24×24, gap ≥8px, input font ≥16px; panel/popover portal không bị `overflow-hidden` cắt; focus ring/
status icon non-text contrast ≥3:1; text contrast đúng WCAG; keyboard order không trap.

**Raw receipt:** JSON selector + rect + gap + font + computed colors/ratio + scrollWidth; kèm ảnh
390×844 của panel ≥30 rows theo checkpoint bắt buộc bên dưới. **FAIL:** dùng screenshot thay số đo,
target dưới 24px, text/action tràn, hoặc input bị Safari zoom do <16px.

### A16 — Desktop 1280 × 800 và đường thay thế không-hover

**Setup/steps:** chạy cùng state/data ở desktop project; keyboard-only mở indicator/panel, discard,
lock/login hold affordance; kiểm hover chỉ là shortcut.

**PASS state:** mọi thông tin/hành động vẫn tới được bằng click/tap/keyboard; focus visible, không
trap; panel/dialog không cắt và trả focus về opener; layout không giãn vô lý hoặc ẩn trạng thái.

**Raw receipt:** `innerWidth=1280`, tab order/focused selector sequence, rect/overflow và ảnh
1280×800 của cùng panel ≥30 rows. **FAIL:** hover là đường duy nhất, thiếu ảnh checkpoint, hoặc mobile
pass được dùng thay desktop.

#### Ảnh + taste bắt buộc, không phải proof số đo

Theo `docs/qa-framework.md` §3.E, lane L2 phải lưu ảnh synthetic vào
`output/playwright/017-taste/` ở tối thiểu năm checkpoint **phân biệt**:

1. outbox panel ≥30 rows ở 390×844, có banner/trạng thái đầu trang;
2. cùng dataset/state ở 1280×800;
3. `note-detail-dialog` với checklist dài để bắt regression UI chung;
4. private gate locked, private row ở hold nhưng không lộ entity name;
5. private gate vừa unlock, cùng chain đang/rồi flush.

Mỗi ảnh phải có viewport/state/run ID, 2–4 câu taste, và một câu literal mô tả heading/banner đang
hiện. Chạy `Get-FileHash -Algorithm MD5 output/playwright/017-taste/*` trước khi đọc nhận xét; hash
phải khác nhau cho năm checkpoint. Ảnh chỉ chứa fixture synthetic, đã crop vào app; không avatar,
bookmark, email, PIN hoặc tab khác. Thiếu ảnh/hash/banner description ⇒ A15/A16/A20
`[CHƯA VERIFY]`; ảnh không thay computed geometry/contrast.

### A17 — Production HTTPS, revision và secure-context capability

**Setup/steps:** sau revision gate L3, mở đúng `https://microsched.fly.dev`; xác nhận
`location.protocol`, `window.isSecureContext`, `navigator.serviceWorker`, `navigator.locks`, SW
ready/controller và `/api/readyz` một lần.

**PASS state:** HTTPS + secure context true; expected commit và `db=up`; real SW controls page; Web
Locks tồn tại. Chạy một synthetic public queue round-trip và xác nhận queue `0`, không dùng
`http://192.168...`.

**Raw receipt:** readyz JSON, capability JSON, controller scope/script URL, QA request/state counter.
**FAIL/stop:** commit mismatch, db down, controller là revision cũ, Web Locks missing nhưng app vẫn
âm thầm flush cạnh tranh, hoặc production test đụng dữ liệu không thuộc manifest.

### A18 — iPhone thật của chủ qua PWA Home Screen

Lane này do chủ trực tiếp chạy hoặc giám sát; executor không tự chọn account/PIN. Dùng đúng PWA đã
cài Home Screen trên production HTTPS:

1. online mở app, ghi manifest các pending IDs đã tồn tại và baseline queue `B`; không xoá/chỉnh các
   row đó; xác nhận public canaries đã cache và gate locked;
2. bật airplane mode, đóng/mở lại PWA rồi reload;
3. thấy public cache, không thấy private; tạo đúng ba synthetic IDs mới: task + note + entry;
4. kiểm queue `B -> B+3`, indicator tăng, bàn phím/safe area/touch không che action;
5. tắt airplane mode, giữ app mở, chờ ba synthetic rows gửi xong và queue trở lại đúng `B`; đọc lại
   server state theo ba IDs, không dùng bulk delete/reset để ép baseline;
6. cleanup chỉ ba synthetic server IDs nếu chủ cho phép; không xoá row/payload đã tồn tại trước;
   logout khỏi app/đóng bề mặt QA theo hướng dẫn của chủ.

**PASS state:** offline reload sống, private plaintext/UI không lộ, ba writes queue, reconnect đúng
một bản ghi mỗi synthetic ID và queue `B -> B+3 -> B`; before/after set của pre-existing outbox IDs
không đổi. **Raw receipt:** owner-visible checklist theo vai, manifest synthetic/pre-existing ID
counts, thời điểm/trạng thái/count, iOS/PWA version đủ để tái lập; không ghi email/PIN/cookie/
screenshot có avatar/bookmark.
**CHƯA VERIFY:** simulator/desktop emulation không thay lane này.

### A19 — RED → GREEN cho guardrail an toàn

Trên clean throwaway QA worktree/temporary uncommitted patch, cố ý phá từng guardrail dưới đây,
chạy targeted test thấy **đỏ đúng assertion**, hoàn nguyên đúng patch rồi thấy **xanh**. Không commit,
push hoặc merge code phá.

| RG | Phá tạm thời | RED đúng | GREEN sau restore |
|---|---|---|---|
| 01 sanitizer | cho mixed list persist nguyên | private canary occurrence >0 | occurrence=0, public còn |
| 02 purge boundary | cho purge xoá outbox | private outbox canary mất | canary còn đúng 1 |
| 03 classifier | coi mọi 404 là success | restore/private case sai state | DELETE/restore/private đúng bảng A07 |
| 04 skip/dependency | buộc strict global FIFO | public row không gửi | public đi qua private hold |
| 05 idempotency | sinh UUID mới khi retry | SQL count=2 hoặc test ID mismatch | same UUID, count=1 |
| 06 Web Lock | bypass lock ở một tab | request count=2 | count=1 với hai page |
| 07 real SW | block SW/bỏ controller wait | PWA guard fail trước offline | allow + ready + controller xanh |
| 08 refetch/private E2E | invalidate trước flush hoặc overlay private khi locked | optimistic/private assertion đỏ | queue về baseline, state server đúng, locked không lộ |
| 09 clock/cache | trộn `private_until`, session expiry hoặc bỏ SHA buster | boundary/maxAge/buster assertion đỏ | 36m/expiry/7d/buster độc lập xanh |
| 10 IndexedDB fallback | bỏ lazy-open/catch quota | app crash hoặc báo queue giả | online sống + warning, không queue giả |

**Raw receipt:** diff mô tả một dòng, exact targeted command, red assertion/exit code, restore method,
green output, cuối cùng `git status --short`. Nếu không có RED log thì guardrail đó là
`[CHƯA VERIFY]`, dù GREEN suite xanh.

### A20 — Evidence taxonomy, completeness và stop receipt

Report cuối phải có đúng 20 dòng A01–A20, mỗi dòng gắn lane và một trạng thái chuẩn. Bắt buộc tách:

- **ĐÃ CHẠY:** nguyên command + output/state/selector/số đo quan sát được;
- **CHƯA VERIFY:** lane chưa chạy, lý do và prerequisite còn thiếu;
- **SUY LUẬN:** nhận định từ code/doc, không tick PASS;
- **BLOCKED:** conflict/stop condition, hai vòng thử raw nếu là block môi trường.

**PASS state:** không acceptance nào bị đổi từ unverified thành pass; local/CI không được viết thành
production/iPhone; đủ năm screenshot checkpoint phân biệt có raw MD5 + heading/banner description +
taste; CI của PR code xanh đúng các check hiện hành và diff được đọc. **FAIL:** “all tests pass”
không kèm raw summary, output bị tóm tắt, test skip không nói, thiếu/trùng ảnh checkpoint,
production commit không khớp, hoặc personal data/secret lọt artifact.

## 5. CI, PR và Definition of Done

### 5.1 Required local/CI receipts

Trước khi gọi QA implementation hoàn thành:

- `npm run lint`, `npm run build`, `npm test`, mobile/desktop e2e và dedicated PWA lane đều execute;
- `uv run ruff check`, `uv run pytest`, targeted PG/idempotency lane đều execute;
- RED→GREEN có raw output cho mười guardrail A19;
- `gh pr checks <PR> --watch` kết thúc xanh; giữ nguyên tên required checks hiện hành:
  `Backend checks`, `Frontend checks`, `Repository hooks`, `Migration QA`,
  `Production dependency check`; các check khác như `Secret scan`/`Frontend e2e` cũng phải được báo
  đúng trạng thái, không gọi skip là pass;
- diff test/harness được đọc để bác `.skip`, mock thay real-SW, route fallback và assertion rỗng.

### 5.2 Mức kết luận

- **QA PASS:** A01–A20 đều `[ĐÃ CHẠY — PASS]`, gồm L3 production HTTPS và L4 iPhone thật.
- **PARTIAL / CHƯA VERIFY:** L0–L2 xanh nhưng thiếu production/iPhone, hoặc thiếu một RED proof.
- **FAIL:** một invariant dữ liệu/quyền/idempotency/race sai khi đã chạy.
- **BLOCKED:** stop condition kiến trúc/conflict hoặc cùng block môi trường sau hai vòng có raw log.

Không được đóng 017 bằng source review, build local, mocked Playwright, `serviceWorkers:'block'`,
`npm run e2e -- --list`, CI xanh đơn lẻ, liveness `/api/healthz`, hoặc lời khai không có receipt.

## 6. Checklist handoff ngắn

Trước khi giao người chạy QA, T1 điền nhưng không tự hạ chuẩn:

```text
[ ] implementation PR + expected merged/deployed SHA
[ ] clean QA worktree; exact branch/SHA
[ ] Docker/throwaway PG prerequisite
[ ] dedicated PWA config path + exact command
[ ] synthetic fixture run_id + cleanup manifest
[ ] production account role authorized; không ghi email/PIN
[ ] owner/iPhone slot cho A18
[ ] append-only result artifact path
[ ] đủ A01–A20 và RG-01–RG-10
```
