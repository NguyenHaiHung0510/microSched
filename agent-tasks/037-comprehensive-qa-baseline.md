# 037 — Comprehensive QA baseline sau cut-over

> Trạng thái: **DRAFT 2026-08-28 — Owner đã duyệt strategy/scope/order; technical spec còn chờ independent ad-review; Tầng 2 vẫn BLOCKED bởi conflict policy + Owner gate.**
>
> T3 executor: Gemini 3.7/high hoặc Luna/xhigh theo lane; backend/data lane Terra/xhigh.
> T1 chỉ viết matrix, đọc receipt và reconcile; không làm thao tác QA lặp.

## 0. Có cần “QA toàn bộ hệ thống” không?

**Có, nhưng dưới dạng baseline release assurance theo risk, không phải test mọi permutation.**

Lý do:

- cut-over + migration đã thay data/runtime boundary;
- receipt cũ theo từng slice không chứng minh current post-cutover whole app;
- nhiều QA debt còn tách rời (iPhone, Web Push, offline, private, calendar);
- baseline lần này phải sinh regression pack để tái chạy định kỳ, không phải giấy chứng nhận vĩnh viễn.

Phương pháp: 15 flow xuyên domain + targeted P0/P1 invariants; không nhân Cartesian product của mọi
surface × state × viewport.

## 1. Dependency và điểm dừng

Hard start:

1. T1 trình bày strategy/run boundary của baseline này ở tầng product/assurance; Owner duyệt scope và
   thứ tự chạy. Source receipt đã được capture tại
   `agent-tasks/037-owner-strategy-approval.json`; nó **chỉ** duyệt các `scope_ids` ghi trong receipt,
   không cấp Neon/production/device/push/git/merge/deploy authority. Đây là audit evidence, không phải
   chữ ký hay platform identity proof. Tầng 1 chỉ mở khi T1 đã trực tiếp kiểm explicit Owner approval
   trong T1 thread và ghi manual process gate vào manifest; thiếu bước người kiểm ⇒ **không chạy**.
   Frozen current receipt SHA-256 là
   `b800bc1a713b914f20f0128ecc5d3296ed649064dc4d5609a4e229346c3329b5`; bytes đổi ⇒ re-review spec,
   không tự cập nhật manifest để bỏ qua.
2. Task 035/036 exact candidate đã qua local tests + independent ad-review; spec hash và candidate commit
   phải bất biến trong suốt run. Spec còn `DRAFT`, diff còn dirty/uncommitted hoặc verdict còn
   `BLOCK_*` ⇒ chưa được mở baseline.
3. Docker Desktop chỉ là prerequisite của **local disposable candidate-cell** và local PG commands có
   `capability=docker`; không phải production lane và không áp cho CI service container. Static host
   commands được phép chạy trước khi Docker bật, nhưng baseline không thể PASS nếu required Docker cell
   chưa chạy. Validator preflight phải BLOCK command `capability=docker` trước khi có daemon receipt.
4. Không dùng production làm general test environment.

Sau strategy approval nhưng trước Tầng 2, T1 dừng tại Owner gate; Owner tự Restore/Sync Neon `develop`
từ production branch qua Neon Console và xác nhận xong. Approval strategy không thay thế confirmation
sync, và confirmation sync không tự mở production/device/push authority.

Mỗi run tạo `run-manifest.json` **trước lệnh test đầu tiên** với `schema_version`, `run_id`, exact
`candidate_sha = git rev-parse --verify HEAD^{commit}`, SHA-256 của spec 035/036/037,
`expected_production_sha` (nullable trước Tầng 3), thời gian UTC, executor lane, `commands_sha256`,
`candidate_provenance_sha256` và object `strategy_approval_binding`. Binding này bắt buộc chứa
`source_receipt_path=agent-tasks/037-owner-strategy-approval.json`, SHA-256 của source receipt,
`source_message_id`, exact `run_id`, `candidate_sha`, exact SHA-256 spec 037 và đúng sáu `scope_ids` trong
receipt. Validator load frozen `qa/contracts/037/strategy-approval-source.schema.json`, re-hash
receipt, tự hash UTF-8 `source.exact_text`, kiểm
message/thread/turn/timestamp, `qa_execution_status=NOT_RUN`, denied-authority superset, rồi từ chối mọi
command capability ngoài scope. Binding chỉ gắn approval strategy vào run; nó không biến receipt thành
Neon/production/device/push/merge/deploy authority. Thiếu/mismatch/unknown field ⇒ preflight exit khác 0
và **không lệnh test nào được chạy**.
`structured_consent.decision`, exact sáu scope IDs, `execution_authority=false` và runtime run/candidate/
spec binding phải semantic-equal. Tuy nhiên validator **không được claim** đã chứng minh người gửi hay
tính xác thực của actor: receipt/envelope/hash chỉ là audit trail. Authority thực tế ở đây là manual
Owner+T1 process gate đã được T1 kiểm; receipt một mình không mở lane.

Candidate provenance là tracked-schema artifact `candidate-provenance.json` trong run, không được suy từ
working tree hiện tại. Nó bắt buộc có canonical GitHub `repo`, remote URL, `candidate_ref`,
`candidate_sha`, `candidate_tree_sha`, UTC query và ba dependency records `035A|035B|036`. Mỗi record có
spec path/hash; exact local command IDs + stdout/stderr digests; independent review envelope validated
by `qa/contracts/037/review-envelope.schema.json`; PR number/URL; `headRefName/headRefOid`;
`baseRefName=develop/baseRefOid`; state, `isDraft=false`, required-check list và query UTC lấy live bằng
`gh pr view --json`. Review envelope bắt buộc `reviewed_head_oid`, `base_oid`, reviewer identity/model/
reasoning effort, verdict/time, raw review digest và raw GitHub/API receipt digest; cả head/base
phải equal PR receipt và dependency record. Candidate PR riêng
phải có `headRefOid=candidate_sha`; `git merge-base --is-ancestor` phải trả 0 cho từng dependency head
trong candidate. Exact dependency IDs/argv nằm trong immutable
`qa/contracts/037/command-contract.v1.json`: 035A dùng
`dep.035A.ruff-check|ruff-format|pytest-non-pg|pytest-pg|precommit`; 035B dùng cùng năm backend/root IDs,
`dep.035B.active-endpoints-unit` cho exact unit selector chỉ row `push_subscription` hiện hành (endpoint
đã unsubscribe/dead-delete và batch terminal `exhausted` đều zero provider call), cộng
`dep.035B.frontend-lint|frontend-unit|frontend-build|frontend-e2e`; 036 dùng
`dep.036.backend-whitespace|frontend-lint|frontend-unit|frontend-build|frontend-e2e|precommit`.
`dep.035B.frontend-e2e` và `dep.036.frontend-e2e` canonical duy nhất là cwd `frontend`, argv
`["npm","run","e2e"]` vì đó là script sống trong `frontend/package.json`; `npm run test:e2e` và
`npx playwright test` **không tương đương receipt** và không thỏa dependency gate. 035B
active-endpoints unit chỉ PASS khi assert endpoint đã unsubscribe/dead-delete và batch terminal
`exhausted` đều zero provider call; 035B frontend unit chỉ PASS khi test assert opaque notification
`tag` đi tới `showNotification`. Exit 0 thiếu assertion tương ứng không thỏa oracle; 035B phải cung cấp
cả hai exact receipts này. Task 036 vẫn chỉ reconcile/rerun exact command riêng của 036 trước 037.
Command thiếu, review không bind đúng head, PR/check không terminal-success, base không phải `develop`,
hoặc lineage fail ⇒ BLOCKED trước baseline.

Review envelope/raw digest là audit evidence. T1 phải thủ công kiểm reviewer thực sự khác executor và
review bind đúng head/spec, rồi ghi `t1_process_check`; validator chỉ kiểm record nhất quán và exact string
`reviewer.identity != executor_identity`, không claim xác thực actor. Thiếu manual check, cùng identity,
review/head mismatch hoặc chỉ có executor self-claim ⇒ BLOCKED.

Dirty contract: tracked/index diff phải rỗng; untracked chỉ được nằm dưới exact
`output/qa-runs/<run_id>/` sau khi preflight tạo manifest. Validator lưu SHA-256 của raw
`git status --porcelain=v1 -z`, reject symlink/junction/path traversal và mọi path khác. SHA/tree đầu-cuối
run lệch, một acceptance mang SHA khác hoặc spec hash đổi ⇒ FAIL. Equality Tầng 3 là
contract conditional exact: `expected_production_sha=NULL` ⇒ mọi cell Tầng 3 `NOT_RUN`; khi non-null thì
bắt buộc `readyz.commit == expected_production_sha == candidate_sha` bằng exact 40-hex commit, khác ⇒
`FAIL_P0`. Receipt từ run/candidate khác không được copy sang baseline này.

### Conflict policy Tầng 2 — bắt buộc Owner quyết

Hai phía hiện mâu thuẫn:

- `CLAUDE.md`, `docs/devops-brief.md` §8.3, `agent-tasks/README.md` và spec 031 nói agent tự tạo/xoá
  ephemeral Neon branch bằng `neonctl`.
- `AGENTS.md` §9 và `docs/qa-framework.md` §2.1 (update 2026-08-26) cấm agent chạy `neonctl`; Owner
  phải Restore/Sync persistent `develop` từ `main`, xác nhận, rồi agent scrub.

T1 không tự chọn. Cho tới khi Owner chốt canonical policy:

```text
Tầng 1 local/CI synthetic: ALLOWED
Tầng 2 Neon high-fidelity: BLOCKED
Tầng 3 production: NOT RUN
```

Ngay cả khi Owner chốt persistent `develop`, agent vẫn phải dừng và hỏi nguyên văn trước QA data:

> Vui lòng lên Neon Console đồng bộ (Restore/Sync) nhánh `develop` từ `main` (Production) và xác nhận sau khi hoàn tất để tiếp tục.

## 2. Severity và nhãn bằng chứng

- P0: privacy/auth bypass, plaintext/ciphertext leak, data loss/schema mismatch/500, duplicate or
  missing entry/outbox/reminder flood, backup không restore, wrong production revision.
- P1: flow chính không hoàn thành; mọi hard threshold trong `docs/qa-framework.md`/`docs/ui-brief.md`
  trượt (dialog cắt, horizontal scroll, touch/input/font/contrast/focus/spacing/gap dưới ngưỡng);
  notification batching/sort/subtask sai.
- P2: microcopy/taste/spacing chỉ mang tính polish **sau khi** mọi threshold cứng đã PASS.

Machine status chỉ thuộc enum:

```text
PASS | FAIL | NOT_RUN | BLOCKED | SKIPPED_OPTIONAL
```

Mapping narrative: `PASS` = `[ĐÃ CHẠY — PASS]`; `FAIL` = `[ĐÃ CHẠY — FAIL]`; `NOT_RUN` =
`[CHƯA VERIFY]`; hai status còn lại giữ nguyên. `[SUY LUẬN]` chỉ được nằm trong commentary, không phải
status acceptance. Chỉ optional cell khai `required=false` mới được `SKIPPED_OPTIONAL`; thiếu authority/
prerequisite là `BLOCKED`, chưa chạy hoặc mất receipt là `NOT_RUN`, không đổi qua lại để làm báo cáo đẹp.

Final aggregation theo precedence: P0 FAIL ⇒ `FAIL_P0`; required BLOCKED ⇒ `BLOCKED`; required
FAIL ⇒ `FAIL`; required NOT_RUN ⇒ `PARTIAL_NOT_ACCEPTED`; chỉ khi mọi required cell PASS, không P0/P1
mở và cleanup PASS mới là `PASS_BASELINE`. Optional `FAIL|BLOCKED|NOT_RUN` không đổi final status nhưng
phải xuất hiện trong `optional_findings`; chỉ `SKIPPED_OPTIONAL` hợp lệ khi command/oracle không chạy vì
đúng allowlist optional. Taste không tham gia gate.

Local ≠ CI ≠ Neon ≠ production ≠ physical iPhone. `/api/healthz` ≠ `/api/readyz`.

## 3. Tầng 1 — local/CI synthetic

### 3.1 Static/unit/API/PG

- Ruff/format/pytest non-PG + PG.
- Frontend lint/unit/build/full Playwright.
- Postgres `pgvector:pg18`: upgrade head, drift check, downgrade base → upgrade head, final drift.
- Auth/private gates with synthetic identities; no `.env`/real account.
- Reminder batch payload/membership/retry/restart/confirmation.
- Task/note/calendar/tracker/subscription CRUD invariants.
- PWA/outbox only theo behavior actually implemented; missing 017 acceptance remains `CHƯA VERIFY`,
  không giả PASS từ package visibility.
- Synthetic backup dump → decrypt/`pg_restore -l`/restore into throwaway PG; không dùng Neon owner URL.

Real-PG lane phải dựng ephemeral `microsched_migrator` + `microsched_app` như 035 §2.1: bootstrap bằng
service superuser chỉ để tạo extension/schema/roles; Alembic chạy qua migrator URL; catalog assert exact
table/sequence owner, explicit + default app CRUD grants, app DDL denied và `PUBLIC` zero privileges.
Không được chạy migration bằng `postgres` rồi tick owner/grant PASS.

Tầng 1 dùng candidate Docker image build từ exact `candidate_sha` và lockfiles hiện tại, database/
roles/schema/container tên theo `run_id`, browser context mới không storage/cookie/profile thật. Receipt
ghi image digest, Node/Python/uv/npm/Playwright/Postgres versions và lockfile hashes. Kết thúc phải stop +
remove đúng container/network/database/roles/context của run, xác nhận resource count zero; không reuse
container hoặc browser context từ run trước.

### 3.2 Browser geometry/accessibility

Viewports 390×844 + 1280×800, plus coarse pointer where relevant:

- no horizontal scroll;
- target 44px/24px, gap, input 16px, focus return/trap;
- text/non-text contrast, aria-label/live, keyboard path;
- empty/loading/load-error/submitting/submit-error/offline;
- long/70-char-no-space/Vietnamese/emoji/whitespace-only;
- 30+ records, pinned/private/completed/deleted+undo, reload/focus/background/second-use.

Guardrail mới phải có RED → GREEN receipt.

### 3.3 Command manifest và oracle bắt buộc

Expected authority đã được materialize trong spec branch tại `qa/contracts/037/`; executor không được sửa
để làm implementation PASS:

```text
authority-receipts.schema.json
review-envelope.schema.json
expected-authority-review.schema.json
strategy-approval-source.schema.json
command-contract.v1.json
matrix-inventory.v1.json
expected-catalog-fixtures.v1.json
catalog-queries.v1.sql
```

Task 037 implementation phải thêm các runtime schema/tooling sau cùng directory, không thay expected
authority ở trên:

```text
run-manifest.schema.json
strategy-approval-binding.schema.json
candidate-provenance.schema.json
commands.schema.json
acceptance.schema.json
redaction-rules.v1.json
screenshot-record.schema.json
screenshot-checkpoints.v1.json
catalog-receipt.schema.json
backup-receipt.schema.json
migration-receipt.schema.json
```

Frozen SHA-256 (lowercase) của expected authority hiện tại được tính trên UTF-8 sau khi chuẩn hóa mọi
line ending về LF (`\n`), để checkout Windows CRLF không làm drift authority:

```text
authority-receipts.schema.json          b69adfadd267667f7da8a81d786f9738500a89b29a4826bf1a244aa2e93dc52d
review-envelope.schema.json             3b01043108c6908edf67004c97a9a3e54bea547ea63b67515ac644ff9e4ad74d
expected-authority-review.schema.json   c810e8f79fa9758b68b0090e241d84706cf168f1d956817369b59d551fc51266
strategy-approval-source.schema.json    81ebdb861839cbb66c7c62e64a5251ca0806f0e8265aa462444c73966916f7e4
command-contract.v1.json                6fea8c93d69ee946e860ff606eeec19ce2ceeb374ada213118f06c38aadff510
matrix-inventory.v1.json                605b8a51e97af23031424110f660e8087113c5d91fab6dda45858aa409b2ffd1
expected-catalog-fixtures.v1.json       19b3f49a3cbee094754123d6d380502a6c37d56a933ddd750575fd829603e92d
catalog-queries.v1.sql                  9d497dfcc5d2123876d44b6618d8b9504ae0871a52a296c175a7193d449c6d0a
```

Manifest/preflight phải re-hash đủ tám file và equal bảng này; đổi một byte ⇒ spec phải re-review, không
được cập nhật hash trong implementation PR để “hợp thức hóa” drift.

Các JSON Schema dùng `additionalProperties=false`. Validator tracked
`backend/scripts/validate_qa_run.py` phải load đúng path/version; thiếu hoặc unknown version fail-closed.
`matrix-inventory.v1.json` là authority duy nhất cho surface/state/viewport/device combination và
`required|conditional` policy. Nó materialize đủ 15 scenario, full framework state profile, exact local/
CI viewport-device pairs và exact production/iPhone acceptance IDs. Validator expand deterministic ID
format rồi yêu cầu set equality; một row/scenario, trailing shorthand hoặc executor-authored N/A đều fail.

`command-contract.v1.json` enumerate exact ID/cwd/argv/expected exit/oracle/capability cho dependency,
Tier 1, Docker lifecycle, Tier 2 authority+scrub, production/device activation và cleanup. Executor
materialize `commands.json` từ contract này. Static `id` map 1:1 sang runtime `command_id`; mỗi ID xuất hiện đúng
một object; không được alias hai ID vào một result hay dùng một ID cho hai argv. Mỗi object bắt buộc có
`command_id`, `contract_command_version`, `cwd` thuộc enum `.|backend|frontend`, canonical
`resolved_cwd`, `argv` array, `argv_sha256`, env-name allowlist (không value), timeout, capability,
`required`, `expected_exit_codes`, `oracle_ids`, `failure_status`, `failure_severity` và artifact-relative
stdout/stderr paths. `resolved_cwd` phải bằng `Resolve-Path(<candidate_worktree>/<cwd>)`, nằm trong exact
candidate worktree sau canonicalization và không qua symlink/junction. Shell string, `..`, absolute cwd,
duplicate ID/result, argv drift hoặc command không có oracle ⇒ preflight fail-closed. `frontend.e2e`,
dependency 035B và dependency 036 đều dùng exact `npm run e2e`; không còn hai Playwright argv. Task 037 đồng thời sửa
`backend/scripts/prepare_ci_database.py` cùng CI/local harness để bootstrap exact migrator/app roles ở
§3.1 trước Alembic.

Ngoài object command, `command_bindings` materialize cho **mọi** command ID năm field
`phase|required|conditional|activation|depends_on`; key set phải exact-bijection với `commands[]` và mọi
dependency phải PASS trước start. Runtime `commands.json` không được tự hạ `required`, đổi condition,
activation hay dependency. Tất cả PG/Alembic command bind `pg.synthetic-dsn-provenance`; wrapper phải
re-read receipt ngay trước process start và thay toàn bộ DB env bằng synthetic allowlist. Bất kỳ
`DATABASE_URL`/migrator/app URL từ process env, repo/user `.env`, host ngoài exact run container/network,
Neon hostname/project/branch marker, production target hoặc provenance không bắt nguồn từ
`docker.synthetic-env-create` ⇒ `FAIL_P0` **trước Alembic/pytest/SQL**. Không được coi việc một validator
đã PASS từ đầu run là đủ nếu env đổi sau đó.

`verify_qa_catalog.py`, `verify_synthetic_backup_roundtrip.py`, `validate_qa_run.py` và browser suite nếu
chưa tồn tại là deliverable của Task 037; không được silently bỏ command. `scheduler_ownership_receipt`
phải assert `holder_count=1` ở lane applicable, không chỉ exit 0. Nếu runner tương ứng chưa tồn tại,
QA task phải thêm script/test deterministic rồi
gọi bằng exact argv; không thay bằng prose. Backup round-trip dùng DB synthetic: `pg_dump` → encrypt →
decrypt → `pg_restore -l` → restore sang database throwaway mới → compare schema/row/invariant inventory;
raw artifact không chứa DSN/key/plaintext dump. Browser oracle lưu selector + computed geometry/contrast/
focus/touch metrics, không lấy screenshot làm oracle duy nhất.

Mỗi execution sinh đúng một command-result bind `command_id`, `cwd`, `argv_sha256`, start/end UTC,
actual exit, raw digests và `oracle_results[]`. Mỗi acceptance copy `command_id`, expected/actual exit,
expected/actual oracle ID + result. Wrapper `pg.0012-neg-*` expected exit 0 chỉ khi nested Alembic
downgrade trả nonzero exact SQLSTATE `23514` và catalog/row digest không đổi; nested exit 0 là
`FAIL_P0`. Mọi top-level required command trong contract expected `[0]`. Prerequisite/authority/daemon vắng **trước start** và có exact
allowlisted blocker ⇒ `BLOCKED`; command đã start mà timeout, exit mismatch hoặc oracle mismatch ⇒
`FAIL_P0` nếu oracle thuộc privacy/data/schema/backup/production-revision, còn lại `FAIL`; nested negative
fixture exit 0 hoặc sai SQLSTATE luôn `FAIL_P0`. Không được để report tự chọn mapping. Final validator đối chiếu
bijection giữa contract command IDs, `commands.json`,
command results và required acceptance coverage; command thừa/thiếu/chạy hai lần không có explicit
`attempt` sequence, raw digest thiếu, oracle chưa chạy hay acceptance không khớp đều fail-closed.

### 3.4 Deterministic PG/catalog/backup/migration contract

`expected-catalog-fixtures.v1.json` literalize exact table→column list, constraint/index/trigger list,
role/grant set, deterministic UUID/row cho bốn negative fixture và empty round-trip; file còn lưu RFC8785
SHA-256 riêng của `catalog_expected` và `fixtures`. `catalog-queries.v1.sql` là exact read-only SQL target
cho role/object/column/constraint/index/trigger/grant/default-ACL/revision. Hai file là expected authority,
không sinh từ DB/ORM/migration đang test.

Trước implementation/run, một **independent reviewer và Owner** phải ký
`agent-tasks/037-expected-authority-review.json` theo
`qa/contracts/037/expected-authority-review.schema.json`, bind exact hash của command/matrix/catalog/query
files, exact candidate/spec/run và SHA-256 của sorted exact approved command-ID set. Owner section phải
có exact `APPROVE_EXPECTED_AUTHORITY_ONLY` structured consent. T1 thủ công kiểm Owner message, reviewer
thực sự khác executor và review đúng bytes/head, rồi ghi `t1_process_check`; validator kiểm binding/hash/
identity-string nhất quán nhưng không claim platform identity hay actor authenticity. Local envelope chỉ
là audit evidence và không tự cấp execution authority. Approval strategy hiện tại
không thay approval kỹ thuật này. Executor identity phải khác reviewer;
executor không được sửa expected files hoặc tự ký cả expected lẫn implementation. Thiếu envelope,
manual Owner+T1 review gate chưa recorded, hash/version drift hay một bên chưa PASS ⇒ `qa.preflight`
BLOCKED. `catalog-receipt.schema.json` ghi raw-query digest và normalized rows với exact fields, sort ổn định:

- `roles[]`: `rolname,rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls`;
  `microsched_migrator` và `microsched_app` đều login trong disposable cell và năm privilege flag đều
  false; bootstrap service superuser không được là owner/grantee sau bootstrap.
- `objects[]`: `schema,kind,name,owner`; schema `microsched`, mọi table/sequence trong canonical inventory
  owner exact `microsched_migrator`; riêng batch objects phải có
  `tracker_reminder_batch`, `tracker_reminder_batch_item` và mọi owned sequence tương ứng.
- `explicit_grants[]`: `grantee,object_kind,schema,name,privilege,is_grantable`; app có đúng
  `SELECT|INSERT|UPDATE|DELETE` trên application tables và `USAGE|SELECT` trên application sequences,
  không DDL/TRUNCATE/REFERENCES/TRIGGER; PUBLIC có zero row trong schema.
- `schema_grants[]`: query trực tiếp `pg_namespace.nspacl` (effective `acldefault` nếu null), exact set
  migrator `CREATE|USAGE`, app `USAGE`, PUBLIC empty.
- `default_grants[]`: effective ACL cho cả trường hợp có/không row `pg_default_acl`; owner là migrator,
  app nhận đúng table CRUD và sequence `USAGE|SELECT`, owner privilege set đúng PG18, PUBLIC empty.
- Object/schema/default ACL query **không filter grantee**; normalized receipt chứa mọi grantee. Validator
  compare exact set với authority, yêu cầu bootstrap service role có zero owner/grant/default-ACL residue
  và reject mọi grantee/privilege ngoài inventory, không chỉ kiểm app/PUBLIC.
- `pg_default_acl` authority/query enumerate mọi relevant owner `microsched_migrator|microsched_app|postgres`
  cho table/sequence effective ACL. Trước `aclexplode`, raw query luôn trả
  `{raw_row_count,raw_tuples[]}` cho bootstrap `postgres`; tuple gồm owner/schema/object-kind/cardinality/
  raw ACL text nên row có ACL `{}` vẫn nhìn thấy. Exact expected là count `0`, tuples `[]`; sau đó mới
  compare expanded privileges `bootstrap_default_acl_residue=[]`. Static RED fixture inject một raw tuple
  `postgres/GLOBAL/r/{}` và bắt validator trả `FAIL_P0_EXTRA_BOOTSTRAP_DEFAULT_ACL_TUPLE`. Một row ở schema
  khác hoặc empty ACL array vẫn FAIL.
- `ddl_denials[]`: app chạy riêng `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` trong transaction rollback;
  mỗi statement phải fail SQLSTATE `42501`. Migrator fixture upgrade phải PASS và `alembic_version=0012`.
- `columns/constraints/indexes/triggers[]` có name/type/expression normalized; compare exact canonical
  inventory file, không chỉ compare count hay Alembic metadata.

`backup-receipt.schema.json` dùng fixture `backup-v1`: seed public/private synthetic rows cho mọi domain
table, tối thiểu một batch có hai item + linked dispatch và một row mỗi trạng thái miền; lưu
`seed_manifest_sha256`, ordered `{table,row_count,pk_set_sha256,invariant_sha256}` và canonical catalog
SHA-256. `pg_dump` của source disposable DB phải stream thẳng qua approved encryption command thành
encrypted artifact; plaintext dump path là forbidden. Sau decrypt stream, `pg_restore -l` phải exit 0;
restore vào **database mới** `<run_id>_restore`, rồi inventory/canonical catalog phải byte-equal digest với
source expectation. Receipt lưu encrypted artifact SHA-256, dump-list SHA-256, restore database opaque ID,
exit/oracle và cleanup link; DSN/key/private plaintext không được xuất hiện trong argv/raw/artifact.

Migration fixtures là database/schema mới, command ID và transaction riêng; không share mutation:

1. `empty-roundtrip`: upgrade `0011→0012`, downgrade `0012→0011`, catalog oracle ở `0011`, rồi upgrade
   `0011→0012` và drift empty.
2. `batch-nonempty`: seed một batch; downgrade phải nonzero với SQLSTATE `23514`, revision vẫn `0012`,
   batch/item table + full pre-command catalog digest không đổi.
3. `item-nonempty`: seed batch + linked dispatch + item; cùng negative oracle như trên.
4. `dispatch-cancelled` và `dispatch-exhausted`: mỗi fixture seed đúng một unlinked dispatch status;
   downgrade phải nonzero `23514`, revision/catalog/row giữ nguyên.

Oracle tại revision `0011` bắt buộc absent cả hai batch tables, owned sequences, toàn bộ constraint/index/
trigger có prefix tương ứng, `ck_tracker_reminder_time_whole_second`, và không còn `cancelled|exhausted`
trong normalized `ck_reminder_dispatch_status`; đồng thời các table/constraint/index/trigger của `0011`
canonical inventory vẫn present. `migration-receipt.schema.json` lưu fixture ID, before/after revision,
expected/actual SQLSTATE+exit, before/after catalog digest, row digest, rollback/cleanup. Một happy-path
`downgrade base` không thay các fixture này.

Mọi guard mới có `mutant_id`, exact temporary mutation, expected failing test/assertion, RED stdout/stderr +
exit khác 0, restore receipt, rồi GREEN stdout/stderr + exit 0. Mutant tối thiểu tham chiếu 035 ownership/
batch privacy/locking và 036 pagination/private-cache/subtask/geometry guards; mutation không được commit.

Migration oracle bắt buộc thêm downgrade có non-empty batch/item hoặc dispatch
`cancelled|exhausted` phải fail trước DDL; downgrade-empty tới revision `0011` phải chứng minh catalog
không còn table/trigger/index/whole-second CHECK của `0012`, rồi upgrade lại + drift empty. Không thay
bằng riêng `downgrade base` happy path.

### 3.5 Docker disposable-cell lifecycle — exact command gate

Order required trong `command-contract.v1.json`:

1. `docker.daemon` xác nhận Server object, rồi `docker.build-candidate` build production Dockerfile với
   exact `GIT_SHA=<candidate-sha>`; `docker.inspect-candidate` lưu image ID, label run/candidate và digest
   của build context/lockfiles. Tag bắt buộc `microsched-qa:<candidate-sha>-<run-id>`; mọi container,
   network và image đều có `microsched.qa.run_id=<run-id>`. Mismatch tag/label/readyz commit ⇒ `FAIL_P0`.
2. `docker.network-create`; `docker.pg-pull` + `docker.pg-inspect` resolve
   `pgvector/pgvector:pg18` sang immutable image ID/RepoDigest `<pgvector-pg18-ref>` trong manifest;
   `docker.pg-create` dùng exact ref, tmpfs, healthcheck bounded và **không host port**.
3. `docker.synthetic-env-create` tạo env mới từ exact container/network của run (không load process env
   hay `.env`), rồi `pg.synthetic-dsn-provenance` bind host/network/database/role/run và reject mọi Neon/
   production target. Chỉ sau receipt đó `pg.bootstrap-roles` mới tạo database/schema/
   `microsched_migrator`/`microsched_app` tên bind `run_id`, rồi catalog oracle. Mọi PG/Alembic command
   revalidate same receipt immediately before start. `docker.app-create` chỉ nhận synthetic env file nằm
   trong run artifact; redaction scan cấm production/Neon DSN. `docker.app-readyz` phải trả status ok,
   db up, exact candidate SHA.
4. Trước xóa, `docker.cleanup-scope` enumerate exact candidate tag, names và labels; nếu một target thiếu
   exact `run_id`, có label run khác hoặc selector có thể match nhiều run thì BLOCK và retain để Owner
   xử lý. `pg.cleanup-db-roles` phụ thuộc cả `docker.cleanup-scope` và
   `pg.synthetic-dsn-provenance`, nhận exact `--synthetic-dsn-receipt`, container/network/run ID và re-read
   receipt ngay trước first destructive SQL; wrong database/container/network/run, env/`.env` override,
   Neon/production target hoặc stale receipt ⇒ BLOCK, **không DROP gì**. Cleanup reverse order bằng
   `docker.cleanup-app` → `pg.cleanup-db-roles` → `docker.cleanup-pg` →
   `docker.cleanup-network` → `docker.cleanup-image` → `docker.cleanup-zero`. Final oracle đếm resource
   có run label/identifier: containers=0, networks=0, candidate images=0, databases=0, schemas=0, roles=0,
   processes/browser-contexts/tabs/temp plaintext=0. Missing cleanup receipt luôn chặn `PASS_BASELINE`.

Docker timeout không có nghĩa resource chưa tạo: trước retry/cleanup phải inspect exact run labels/names và
ghi trạng thái thật. Không được xoá resource không mang exact `run_id`; không dùng prefix/glob/filter có
thể chạm resource run khác.

## 4. Tầng 2 — owner-gated scrubbed Neon develop

Chỉ sau canonical policy + **explicit manual Owner confirmation được T1 trực tiếp kiểm**. Audit path:
`output/qa-runs/<run-id>/authority/owner-sync-receipt.json`, validated bằng exact
`qa/contracts/037/authority-receipts.schema.json#/$defs/owner_sync_receipt`. Receipt không tự mở gate và
không chứng minh actor; nó ghi lại manual process check cùng technical binding. Receipt phải bind source
message identity/timestamp/hash của confirmation mới; structured consent
phải exact `CONFIRM_NEON_MAIN_TO_DEVELOP_SYNC_COMPLETED`, same run/candidate/spec và chỉ allow
`tier2.prepare-qa-branch`; exact Neon project/branch ID hashes;
source=`main`, target=`develop`; immutable `production_parent_git_sha`; Console operation hash + sync UTC;
immutable parent-source receipt hash; exact run/candidate/spec/manifest-core. Strategy receipt hiện tại
deny Neon operation và **không thể** satisfy receipt này; lời hứa “sẽ sync” cũng không phải receipt đã
sync.

1. `authority.validate-owner-sync` phải PASS **ngay trước** `tier2.prepare-qa-branch`; raw receipt hash và
   validation output vào manifest. `prepare_qa_branch` bắt buộc nhận `--authority-receipt` +
   `--manifest-core-sha256` đúng command contract và tự revalidate trước first DB statement; core digest
   tính trên immutable manifest fields, không gồm receipt object để tránh self-hash. Gọi script cũ không
   args phải fail-closed. Không echo env/DSN/key/PIN/cookie/email.
2. Verify scrub: text format preserved; private re-encrypted/synthesized; push_subscription,
   reminder_dispatch, batch delivery data **và `audit_log`** đều zero; QA session seeded.
3. Migration rehearsal + exact `microsched` catalog/constraints/drift, gồm trigger, table/sequence owner,
   explicit/default grants, application DDL denial và `PUBLIC` zero privileges theo 035.
4. Backend `APP_ENV=local` trước, Vite sau, localhost only; `/auth/dev-session` fail-closed conditions.
5. High-fidelity data shape: ≥51 notes, ≥223 tasks, large calendar/tracker mix, không private text thật.
6. Fake/local push adapter; không gửi điện thoại thật.
7. Logout, protected API 401, close tabs/processes, cookie-redacted cleanup receipt.

Manual Owner+T1 process gate thiếu, receipt thiếu/expired/mismatch, production parent/candidate/spec/run drift, validator chưa chạy hoặc thứ tự
command sai ⇒ `BLOCKED` **trước scrub**; không chuyển production. Sync receipt chỉ là input cho
technical target/command guard của `tier2.prepare-qa-branch`, không tự cấp authority và không cấp
production/device/push/merge/deploy.

## 5. Tầng 3 — production smoke + physical iPhone riêng

Current strategy approval explicitly denies production/device/push, nên mọi cell ở đây hiện `BLOCKED`/
`NOT_RUN`. Mở lane cần **một future activation receipt riêng** tại
`output/qa-runs/<run-id>/authority/production-device-activation.json`, validate theo
`authority-receipts.schema.json#/$defs/production_device_activation`, hoặc valid tracked
`coordination_record` có `authority_binding` tương đương, **sau** manual explicit Owner approval được T1
trực tiếp kiểm. Receipt/record là audit evidence và technical scope input, không tự mở gate hay chứng minh
actor. Nó bind exact candidate/spec/run/
manifest-core, target origin/Fly app/region/database branch/device token, read-only scope, exact allowed command
IDs, executor lane/identity/model/effort, issue/expiry và single-use; `read_only` luôn literal `true`, đủ
exact tám denied mutations và structured scope record tương ứng. Thiếu/mismatch/
expired/executor khác ⇒
`authority.validate-production-device` fail và mọi target command `BLOCKED`; strategy/sync receipt không
được dùng thay.

Chỉ khi exact deployed SHA đã được phép. `expected_production_sha` lấy từ immutable merged PR commit
queried lại qua GitHub API/`git rev-parse` ngay trước run, kèm URL/ref + query UTC trong manifest; không
nhập tay từ report cũ. Production activation phải allow **cả** exact command IDs:

```text
prod.readyz       | . | curl.exe --fail --silent --show-error --proto =https --tlsv1.2 https://microsched.fly.dev/api/readyz
prod.fly-topology | . | flyctl machine list --app microsched --json
```

Production command lưu exact argv/exit/raw output digest. Oracle:

```text
/api/readyz.status = ok
/api/readyz.commit = expected_production_sha = candidate_sha
db = up
exactly one healthy Fly Machine trong allowed region/topology
```

Task 037 v1 chỉ materialize hai production command read-only ở trên; **không có production browser
smoke**. Login/logout/deep-link/public/private browser trên production vẫn `NOT_RUN` và cần future spec +
exact activation/commands/matrix trước khi chạy. Không seed, migration rehearsal, fault injection hay push
thật trên production.

Physical iPhone acceptance là lane riêng: PWA Home Screen, actual viewport/safe-area, keyboard, dialog
scroll, notification title/body/group/click, offline reload/reconnect nếu feature đã implemented.
Chromium 390px không được nâng thành iPhone PASS.

Exact device acceptance IDs/commands nằm trong materialized matrix:
`037-device-iphone-layout→device.iphone-acceptance`,
`037-device-ios-pwa→device.ios-pwa-acceptance`,
`037-device-real-push-single|037-device-real-push-grouped→device.real-web-push`. Authority tách riêng
`production_read_only_smoke|physical_iphone_layout_acceptance|ios_pwa_acceptance|
real_web_push_acceptance`; mỗi type chỉ mở IDs của chính nó. Physical iPhone layout receipt không mở iOS
PWA, production read-only không mở device/real push.

Mỗi matrix/device cell mang exact `device_token` trong
`LOCAL_CHROMIUM|CI_CHROMIUM|IPHONE_PHYSICAL|IOS_PWA|REAL_WEB_PUSH`; `NONE` chỉ cho
non-browser cell. Mỗi token dùng machine status enum ở §2. Production command lưu
raw output cho readyz/topology. Mutation production luôn deny; real push cần exact activation type riêng.
Không có authority ⇒ `BLOCKED`, không prompt để tự mở rộng. Chromium không thể điền PASS thay
`IPHONE_PHYSICAL`/`IOS_PWA`.

## 6. Fifteen baseline flows

1. Login → return_to → logout → session expiry.
2. Private locked → public use → unlock → lock-now; no name/count/body/cache leak.
3. Create long task + draft checklist → edit/tick/delete/reopen → visible error path.
4. Calendar adjacent months → task open/edit/subtask/tick/move → inert placeholders.
5. Note sort alphabet/created/updated + pinned + null title + long reflection.
6. Tracker event/money/quantity, 0/large/Vietnamese/emoji, long dialog.
7. Single public tracker reminder payload + click.
8. Private or multi same-time batch ⇒ one generic notification with correct N.
9. Stale dispatch/retry/restart/partial devices; no duplicate entry.
10. Subscription renew/cancel/restore/highlight/settings invariants.
11. Offline public read/write → reconnect/idempotency nếu outbox 017 thực sự implemented; nếu chưa thì
    outbox cell `NOT_RUN` và nêu gap, không suy từ dependency visibility.
12. Private Notes/Tracker read-cache purge khi lock là **mandatory** theo 036; pending private outbox
    preservation chỉ conditional theo 017. Sentinel plaintext/name/count không được flash trước refetch.
13. Migration + schema drift + synthetic backup restore + row/invariant inventory.
14. ≥30 records at 390/1280, last card/dialog/popover, hostile strings.
15. Reload/focus/background and second-use session; polling/timer bounded, empty heap no hot loop.

### 6.1 Minimum coverage groups — machine authority phải materialize đủ

Exact inventory đã materialize tại `qa/contracts/037/matrix-inventory.v1.json`, không còn ký pháp rút gọn.
Nó khai literal cho từng scenario: surface group, full framework states
`empty|loading|load_error|submitting|submit_error|offline|long_content|many_30plus`, domain states, exact
viewport/device pairs, required/conditional policy và deterministic acceptance ID format. Validator
expand **ORTHOGONAL_UNION**: (a) surface × framework-state-profile × viewport/device với
`domain_state=NONE`; (b) surface × required-domain-states × viewport/device với
`framework_state=loaded` cho UI hoặc `NONE` cho non-UI. Không nhân framework×domain, không gộp về một
cột `state`. Compare exact set với `matrix.csv`; missing/extra/duplicate đều fail. Scenario 11 conditional
false vẫn sinh đủ cells `NOT_RUN`, không xoá; private-cache scenario 12 luôn
required. Production/iPhone/real-push dùng sáu exact acceptance IDs ở §5/materialized inventory và không
được backfill bằng local Chromium.

## 7. Screenshot/taste protocol

Required app-only crops: task/note/tracker ≥30 at both viewports; long tracker dialog; note reflection;
calendar/day dialog; private locked/unlocked; single and grouped reminder synthetic state.

Mỗi ảnh có **cả** SHA-256 và receipt `md5sum` theo `docs/qa-framework.md`; T1 tự chạy `md5sum` trước khi
đọc narrative, rồi verify SHA-256 manifest. Mỗi ảnh có một câu mô tả banner/chữ đầu trang và 2–4 câu
taste. Taste không tự PASS/FAIL. Hash trùng ngoài allowlist explicit hoặc mô tả không khớp ảnh ⇒ FAIL.

`screenshot-checkpoints.v1.json` phải enumerate exact checkpoint IDs, scenario/acceptance/matrix cell và
expected visible selector/text-role; ít nhất:
`tasks-30-mobile|tasks-30-desktop|notes-30-mobile|notes-30-desktop|trackers-30-mobile|trackers-30-desktop|
tracker-dialog-long-mobile|tracker-dialog-long-desktop|note-reflection-mobile|calendar-day-mobile|
private-locked-mobile|private-unlocked-mobile|reminder-single-synthetic|reminder-grouped-synthetic`.
Thiếu checkpoint không được bù bằng ảnh ngoài inventory.

Mỗi file có đúng một sidecar object trong `screenshot-records.json` theo
`screenshot-record.schema.json`: `screenshot_id`, `checkpoint_id`, `run_id`, `candidate_sha`, spec hashes,
`scenario_id`, `acceptance_id`, `matrix_row_sha256`, lane/device/viewport, pixel width/height, app crop
rectangle, artifact-relative image path, capture UTC, visible selector + normalized accessible-text digest,
`top_banner_or_heading` exact text, `taste_notes` array dài 2–4, lowercase 32-hex MD5, lowercase 64-hex
SHA-256 và capture-command raw receipt digest. `screenshots.md5`/`.sha256` phải được generate từ sidecar,
sort theo relative path và byte-match hash tự tính lại; sidecar/path/checkpoint/acceptance mismatch,
dimension/viewport mismatch, missing narrative, duplicate hash ngoài explicit same-state allowlist hoặc
image không decode được ⇒ FAIL. Screenshot không thay DOM/geometry/contrast oracle; T1 vẫn re-hash MD5
trước khi đọc narrative như framework yêu cầu.

## 8. Artifact layout

Artifacts là local/Git-ignored nếu chứa runtime data:

```text
output/qa-runs/<run-id>/
  run-manifest.json
  candidate-provenance.json
  commands.json
  authority/
    owner-sync-receipt.json                 # future; absent until Owner actually confirms completed sync
    production-device-activation.json       # future; absent until separately activated
  scope.md
  matrix.csv
  acceptance.json
  raw/
    github/
    reviews/
  api-redacted/
  db-inventory.json
  screenshots/
  screenshot-records.json
  screenshots.md5
  screenshots.sha256
  cleanup-receipt.json
  final-report.md
```

`matrix.csv` schema bắt buộc:

```text
scenario_id,coverage_group_id,surface,framework_state,domain_state,viewport,device_token,required,applicable,na_reason_code,acceptance_id
```

Validator load exact `qa/contracts/037/matrix-inventory.v1.json`, expand orthogonal-union contract §6.1 rồi
compare set equality trên `(scenario_id,coverage_group_id,surface,framework_state,domain_state,viewport,device_token,
acceptance_id)`; duplicate, extra hay missing đều fail. Mỗi required combination có đúng một row hoặc
`applicable=false` + exact `na_reason_code` được allowlist cho tuple đó. Narrative 15 flow không thay
completeness matrix.

`acceptance.json` theo JSON Schema tracked trong QA artifact/tooling; mỗi cell bắt buộc có
`run_id`, `manifest_sha256`, `acceptance_id`, `candidate_sha`, `spec_hashes`, `lane`, `status`, `required`,
`command_id`, expected/actual exit, expected/actual oracle ID/result, failure mapping, UTC start/end,
artifact-root-relative raw stdout/stderr paths + SHA-256, oracle/selector/metric/evidence paths + digest,
authority receipt ID/hash, screenshot sidecar IDs nếu applicable, severity và cleanup link.
PASS cần exit/oracle đúng; raw file thiếu hoặc hash mismatch ⇒ FAIL. Redaction validator scan artifact và
fail nếu có secret, literal PIN/cookie/email/DSN/private text/push endpoint. `final-report.md` append-only
được generate từ acceptance, không tự sửa status bằng prose.

`cleanup-receipt.json` bind cùng `run_id`, `candidate_sha`, `manifest_sha256`; liệt kê từng resource
container/network/database/schema/role/process/browser-context/tab/temp plaintext với created identifier,
cleanup command/status và final count. Required cleanup chỉ PASS khi mọi resource count zero, không
process/tab/login còn sống và không plaintext dump/decrypted backup còn trên đĩa.

`validate_qa_run.py --phase final` kiểm toàn bộ contract trên, command coverage (kể cả validator,
catalog, backup, screenshot hashes, authority), strategy source+run binding, expected-authority dual review,
candidate PR/review-envelope lineage, future owner-sync ordering, production/device activation or valid
coordination record, command/result/acceptance bijection, exact matrix set, Docker image/lifecycle/zero
cleanup, screenshot sidecar/checkpoint set, catalog/migration/backup digest, run/spec/SHA binding, raw hashes,
redaction và final aggregation. Validator self-tests phải cố ý đưa approval/sync/activation/expiry/
candidate/review/command/cwd/oracle/matrix/Docker/catalog/screenshot/receipt sai để thấy fail trước gate.

## 9. Stop conditions và periodic triggers

Dừng ngay với P0; policy Neon conflict; Owner chưa sync; scrub/migration/drift fail; wrong readyz SHA;
duplicate screenshot hash; cùng environment failure lặp hai vòng; hoặc cần authority ngoài scope.

Sau baseline, tái chạy targeted suite sau migration/cut-over, auth/private/outbox/reminder/timer change,
shared UI component change; iPhone sau PWA/Web Push hoặc release lớn. Monthly local smoke chỉ được tạo
khi Owner explicit yêu cầu monitor. Monthly staging càng phải owner-triggered và lặp lại canonical policy
resolution + Stop & Request Owner Restore/Sync mỗi run; lịch cũ không phải authority cho lần mới.
