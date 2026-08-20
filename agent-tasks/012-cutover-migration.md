# 012 — Cutover: đưa dữ liệu thật từ Postgres v2 sang Neon, rồi ngừng dùng app cũ

> **Executor:** T2 (route chọn từ Runtime Catalog lúc giao) · **Bậc:** L1 · **effort đề xuất:** high.
> **Trạng thái: DRAFT — refresh 2026-08-20.** Exact head `d5e7956` đã bị T3 BLOCK; các finding xác nhận
> đúng đã fold trong bản này. Vẫn cần exact-head adversarial re-review và strategic sign-off của chủ.
> DRAFT **không** cho phép viết/rà rehearsal, chạm Neon, dump hay cutover thật.
>
> Cutover thật chỉ do chủ giám sát tại workstation. Executor không nhận secret, URL DB thật, dump, PIN,
> cookie, endpoint Push, token hoặc plaintext task/note/event/message.

## 0. Phạm vi và hard boundary

Lô implementation sau approval tạo `backend/scripts/cutover_v2.py`, fixture DDL/data hoàn toàn sanitize và
runbook. Nó đọc `microschedule_v2` local **read-only**, transform một snapshot frozen, atomically purge
toàn bộ domain mock/trash đã được chủ approve ở Neon, rồi import chính snapshot đó.

Không làm:

- không đổi schema/grant/migration, không cấp `SELECT` cho `microsched_app` trên `alembic_version`;
- không sửa/xoá/vacuum source `microschedule_v2` hay SQLite `todo.db`;
- không import lịch học/thi từ v2; chỉ map manual legacy events. Lịch gốc re-import từ file `.ics` qua 010a;
- không sửa `app_setting`, `session`, `push_subscription` hay `alembic_version`;
- không coi `/api/readyz` đơn lẻ là proof dữ liệu.

`message` là encrypted future AI conversation; `audit_log` là AI/tool trace metadata. Theo owner decision
2026-08-16, **mọi row hiện hữu** trong hai bảng này, cũng như mọi domain row khác trong §2, là mock/trash
purge-approved. Điều này không gán nhãn các row tương lai là rác.

## 1. Cổng vào — thiếu một dòng là dừng

1. **022 đã merge, deploy và production-verify viewability.** Màn Task phải reach toàn bộ lịch sử theo
   bounded timeline/cursor, không fixed 100/offset.
2. 020 đã production-accepted; app mới daily-usable; 010a/010b/011 production gates, pricing và backup
   được re-check vào ngày chạy.
3. Source gate: chủ xác nhận máy/database `microschedule_v2`/read-role/schema `public` đúng; script
   fingerprint identity/DDL không secret. Lệch bất kỳ thành phần nào abort trước target connection.
4. Chủ đã chọn maintenance window, old app đóng/freeze, và sole Fly Machine có thể dừng.
5. Target attestation (§4.2) khẳng định revision/catalog exact head trước DML. `alembic current` hay
   `readyz` đơn lẻ không thay thế catalog receipt.

Không hardcode 163/191 hay count lịch sử nào. Công thức, count, ID set và digest chỉ có giá trị khi đo
sau source freeze tại exact cut-off (§4.1).

## 2. Phân loại target — phải exhaustive

### 2.1 Preserve set (không purge/không copy)

| Table | Identity key | Bằng chứng bắt buộc |
|---|---|---|
| `app_setting` | `id` | count + sorted-ID + full-row canonical digest |
| `session` | `id` | như trên |
| `push_subscription` | `id` | như trên; không in endpoint/key |
| `alembic_version` | `version_num` | revision + sorted-key + full-row canonical digest, chỉ qua attestation connection |

### 2.2 Purge set và expected end state

| Nhóm | Tables |
|---|---|
| **Mapped rồi nhập lại** | `task`, `task_item`, `note`, `note_item`, `calendar_source`, `calendar_event` |
| **Purge-only, không có source mapping** | `day_annotation`, `tracker_group`, `tracker`, `entry`, `subscription`, `reminder_dispatch`, `message`, `audit_log` |

Mọi purge-only component **bắt buộc** xuất hiện trong final manifest với `expected_count=0`,
`empty_sorted_id_digest` và `empty_full_row_digest` canonical. Transaction assert cả ba sau purge/import
và `--verify` assert lại post-commit. Không có bảng purge-only nào được coi là “tự nhiên rỗng”.

Attestation catalog phải classify mọi table trong schema `microsched` vào preserve/mapped/purge-only.
Một app/domain table mới không nằm trong ba set là **abort** đến khi chủ phân loại rõ; không được tự coi
nó là mock hay operational state.

## 3. Source validation và mapping

### 3.1 Validation chung

Nguồn phải có source status hợp lệ, child có parent, `task_item.position`/`note_item.position >= 0`,
manual event `ends_at > starts_at` và tất cả timestamp required offset-aware. `tasks.status='archived'`
hoặc `notes.archived_at IS NOT NULL` có count >0 là **fail-closed**: in count + ID digest, không import
một phần, hỏi chủ. Target không có archived status; không tự drop hay thêm schema.

Priority map cố định:

```python
PRIORITY_MAP = {
    "Quan trọng hơn TN": "p1", "Nguy hiểm": "p1",
    "Bỏ là nhót": "p2", "Phải làm": "p2",
    "Nên làm": "p3", "Optional": "p3",
}
```

`priority_id IS NULL -> target priority NULL` là hợp lệ. Với **mỗi priority_id được tham chiếu** bởi
một row được map, require đúng một source priority row, không có duplicate referenced `name`, và name
nằm trong `PRIORITY_MAP`. Chỉ referenced unknown/duplicate name abort; priority không tham chiếu không
tự làm abort.

### 3.2 Calendar taxonomy — exact predicate, không silent skip

Chỉ candidate calendar rows có source `display_name = 'v1_sqlite_schedule'`. Classification phải thực
hiện bằng query này (literal escape là **một** ký tự backslash):

```sql
SELECT
  ce.id,
  CASE
    WHEN ce.external_uid LIKE 'manual\_%' ESCAPE '\' THEN 'manual'
    WHEN ce.external_uid LIKE 'v1-schedule-%' THEN 'ics_reimport'
    ELSE 'unclassified'
  END AS cutover_bucket
FROM public.calendar_events AS ce
JOIN public.calendar_sources AS cs ON cs.id = ce.source_id
WHERE cs.display_name = 'v1_sqlite_schedule';
```

Dry-run/manifest in count + ID digest riêng cho `manual` và `ics_reimport`; không tạo manual source nếu
manual count bằng 0. `external_uid` khác pattern hoặc `NULL` là `unclassified` và abort. Event có source
khác `v1_sqlite_schedule`, source missing, hoặc source display name NULL cũng là unclassified inventory
và abort. Nhờ vậy không có event cũ nào lặng lẽ ngoài taxonomy.

### 3.3 Công thức cột — source `public.*` → target `microsched.*`

Script dùng SQLAlchemy/SQLModel **table models** và explicit values, không DTO/store `require_uuidv7`:
UUID historical source có thể v4. Không dùng `ON CONFLICT DO NOTHING`; overlap/drift là error.

**`tasks -> task`**

| Target field | Formula |
|---|---|
| `id` | `tasks.id`, giữ nguyên UUID |
| `title` | `tasks.title` |
| `body_md` | `tasks.note` |
| `status` | `tasks.status`, chỉ `open -> open` hoặc `completed -> completed` |
| `priority` | `NULL` nếu `priority_id` NULL; nếu khác NULL, lookup `priorities.name` theo §3.1 rồi `PRIORITY_MAP[name]` |
| `due_at` / `completed_at` | `tasks.due_at` / `tasks.completed_at`, giữ instant hoặc NULL |
| `created_at` / `updated_at` | giữ exact source timestamp |
| `is_private` / `pinned` / `deleted_at` | constants `false` / `false` / `NULL` |

**`task_items -> task_item`**

| Target field | Formula |
|---|---|
| `id`, `task_id`, `content`, `is_completed`, `position`, `created_at`, `updated_at` | cùng tên từ `task_items` |
| parent policy | `task_id` phải thuộc task transformed; archived/unmapped parent đã blocked ở §3.1 |

**`notes -> note`**

| Target field | Formula |
|---|---|
| `id` / `title` / `created_at` / `updated_at` | giữ fields cùng tên từ `notes` |
| `body_md` | `notes.body` |
| `pinned` | `notes.pinned` |
| `priority` | `NULL` nếu `priority_id` NULL; lookup/map y như task nếu non-NULL |
| `embedding` / `is_private` / `deleted_at` | constants `NULL` / `false` / `NULL` |
| archived policy | `notes.archived_at IS NOT NULL` blocked fail-closed theo §3.1, không có row transformed |

**`note_items -> note_item`**

| Target field | Formula |
|---|---|
| `id`, `note_id`, `content`, `position`, `created_at`, `updated_at` | giữ fields cùng tên từ `note_items` |
| `is_completed` | `note_items.is_done` |
| parent policy | `note_id` phải thuộc note transformed |

**One generated `calendar_source` for all manual events**

| Target field | Formula |
|---|---|
| `id` | UUIDv7 sinh đúng một lần before manifest, ký/record as expected ID |
| `name` / `kind` | constants `Buổi thủ công (app cũ)` / `manual` |
| `color` / `is_visible` | constants `NULL` / `true` |
| `created_at` / `updated_at` | exact source-freeze `cutoff_at` from manifest |

**`manual calendar_events -> calendar_event`**

| Target field | Formula |
|---|---|
| `id` | source `calendar_events.id` |
| `source_id` | generated manual source ID above |
| `title`, `location`, `starts_at`, `ends_at` | same-named source fields, including NULL location and exact instants |
| `description_md` | source `description` |
| `all_day` | constant `false` |
| `is_hidden` | `COALESCE(user_cancelled, false) OR status = 'cancelled'` |
| `created_at` / `updated_at` | exact source timestamps |

Target-only constants and nullable fields above are part of the transform version and full-row digest, not
implicit server-default behavior.

## 4. Two-phase manifest, role isolation và canonical proof

### 4.1 Phase A — source freeze draft

Sau owner freeze, source read-only connection validates §3 then computes transformed expected rows/counts,
sorted identity-key digest và full-row digest for all mapped components. It creates an encrypted **draft**
manifest with source identity/DDL fingerprint, transform version, exact `cutoff_at` UTC, script git SHA and
source expected section. The full `pg_dump -Fc` source backup is encrypted by `age` outside repo; restore it
to throwaway Postgres and require catalog/count/digest match Phase-A source section.

### 4.2 Phase B — Fly stopped final manifest

Sau khi sole Fly Machine is confirmed stopped, open a **separate, tightly bounded** attestation connection
as `microsched_migrator` (or `neondb_owner` only when migrator cannot attest). It is `READ ONLY` from
connect through close, has short statement timeout, runs only `current_user`, `alembic_version.version_num`
and `information_schema`/catalog queries needed to classify §2 and assert required columns/constraints. It
does not read application rows. This is necessary because migration `0001` explicitly revokes all access to
`microsched.alembic_version` from `microsched_app`.

Close the attestation connection **before** reading application rows or opening target DML. It may never
issue DML, grant, role or schema changes. No grant change is authorized. Record its revision/catalog
fingerprint in draft. A distinct `microsched_app` **read-only preflight** connection runs `current_user`
and must equal exactly `microsched_app`; it collects encrypted pre-state count/identity/full-row digests
for preserve **except `alembic_version`** and for purge sets, then closes. It neither queries
`alembic_version` nor reuses attestation credentials.

Only then finalize/hash/sign the manifest with the required owner local signing key; lack of a valid
signature aborts. No dry-run, target mutation or recovery begins from a draft/unsigned/changed manifest.
`--commit`/`--recover` open a fresh `microsched_app` connection for DML/readback after this finalization.

### 4.3 Canonical hashes

A canonical row uses fixed ordered target fields after the formulas in §3: UTF-8 length-prefixed text;
UUID lower-case hyphenated; RFC3339 UTC fixed microseconds; DATE ISO; NULL token; bool `true|false`;
fixed decimal; JSON sorted keys/no whitespace. SHA-256 digests component name + transform version + rows
sorted by identity key. Full-row hashing includes prose, status/priority, foreign keys, completion,
positions, timestamp, privacy/delete flags and every constant/default field listed in §3. Plaintext exists
only transiently in local hash computation; never stdout, PR or artifact.

Mapped components require exact count + sorted-ID set + full-row digest after import. Purge-only components
require the `count=0` and both canonical empty digests in §2.2. Preserve components require exactly their
Phase-B digest; `alembic_version` uses `version_num` as identity.

## 5. CLI, atomic cutover and verify

Argparse has one mutually-exclusive mode group; no flag means `--dry-run`:

```text
cutover_v2 [--dry-run | --commit | --verify | --recover]
```

Every non-dry command requires finalized signed manifest, expected script SHA and
`--confirm-target-host=<production-host>`. URLs live only in environment and logs redact credentials.
No `--skip-calendar`, `--force` or implicit write mode exists.

- `--dry-run`: validates source/attestation/final manifest and prints only host, versions, counts and digests;
  writes zero target bytes.
- `--commit`: only normal initial cutover (§5.1).
- `--verify`: read-only post-commit proof (§5.2).
- `--recover`: narrow post-commit reconstruction (§6), not routine rerun.

### 5.1 `--commit` exactly one transaction

After signature/SHA/host/role/preserve-digest preflight, open one `AsyncSession` under `microsched_app` and
one `db.begin()`. Purge exact child-before-parent order:

`reminder_dispatch -> entry -> subscription -> tracker -> tracker_group -> calendar_event -> calendar_source
-> task_item -> task -> note_item -> note -> day_annotation -> message -> audit_log`.

Then insert parent-before-child mapped rows: `task -> task_item`, `note -> note_item`, generated manual
`calendar_source -> calendar_event`. Inside **that same transaction**, assert:

1. every mapped component exact-matches manifest count, ID set and full-row digest;
2. every purge-only component has count 0 plus the two canonical empty digests;
3. every preserve component still matches Phase-B digest.

Any conflict, unexpected mapped ID, residual purge-only row, FK error, signature/schema/formula/source/preserve
drift is exception and rolls back purge plus import. Commit only after all assertions.

### 5.2 `--verify` and post-ICS distinction

`--verify` opens no DML transaction and repeats the signed-manifest proof post-commit: mapped exact result,
all eight purge-only empty results, and preserve digests unchanged. It must fail if even one residual row
exists in any purge-only table; it is not a subset check.

This verify ends **before** owner imports canonical `.ics` files. After Fly starts, owner explicitly
re-imports the approved canonical files through 010a. Final calendar is therefore:
`migrated manual source/events + separately imported canonical-file sources/events`. Capture exact source/event
counts per imported file and visual calendar receipt separately; do not compare that final aggregate to the
manual-only atomic manifest.

## 6. Constrained `--recover` — only after a failed post-commit state

`--recover` is mutually exclusive with every other mode and may run only when all conditions hold:

1. same immutable final manifest, valid signature and exact script git SHA;
2. `--confirm-target-host` matches; Fly is stopped and a signed local operator receipt names that maintenance
   state (no production API proof substitutes);
3. Phase-B preserve digests still match exactly;
4. recovery source is a fresh restore of the encrypted source dump, verified against the manifest source
   section. It never reads a live/drifted old-app database;
5. source identity, transform version, target attestation and manual source UUIDv7 all match manifest.

With those checks, it opens one `microsched_app` transaction, purges **the complete §2.2 purge set** in the
same child-first order, reimports the exact manifest snapshot, performs §5.1 canonical/purge/preserve
assertions, then commits. Any error rolls back the whole recovery. It is recovery of reconstructible domain
data, **not** a restore of target mock/trash; it never restores full Neon target dump or touches preserve data.

## 7. Tests and branch rehearsal

Fixture DDL/data are synthetic and sanitized: no owner dump, content, endpoint, email, PIN or session token.

1. Field-level mapping test for every §3.3 column, including nullable priority, timestamps, target constants,
   calendar visibility/hidden formula and manual source UUIDv7.
2. Source validation tests: archived task/note, invalid status/position, bad parent, non-NULL unknown or
   duplicate referenced priority name, invalid duration, unclassified/null UID and unknown source all abort
   before DML.
3. Source write attempt raises Postgres `25006`. Role test proves `microsched_app` cannot select
   `alembic_version`; only a short read-only attestation connection obtains revision/catalog and it closes
   before app connection. Test rejects use of migrator/owner for DML and rejects any grant change.
4. Target fixture seeds every purge-set and preserve table. Commit leaves preserve byte/digest-identical,
   mapped exact, and each purge-only table zero/empty. Parameterized residual-row negative cases make
   inside-transaction and `--verify` fail for every purge-only table.
5. Induce failure after purge and before final assertion: transaction rolls target state back exactly.
   Manifest draft/unsigned/signature/SHA/catalog/formula/host/preserve drift and mapped-ID overlap each abort.
6. Calendar fixture covers `manual_*`, `v1-schedule-*`, other and NULL UIDs; only first maps, all other
   categories fail closed. No `--skip-calendar` parser/code path.
7. Recovery denial tests: missing operator receipt/Fly stop/signature, wrong SHA/host, stale preserve digest,
   source dump mismatch, non-frozen source and wrong UUIDv7 all abort before DML. Recovery order and induced
   error prove complete-set transaction rollback; success proves exact reimport.
8. Rehearse full signed-manifest flow on a disposable Neon branch with sanitized fixture; delete branch after
   receipt. Throwaway Postgres supplements CI only, never replaces branch rehearsal.

## 8. Owner maintenance ceremony (after approval only)

1. Confirm §1, implementation SHA/green CI and named operator maintenance window.
2. Close old app; inspect `pg_stat_activity` until no unexpected `microschedule_v2` session. Default
   read-only setting is only backstop; never terminate unknown PID blindly.
3. Freeze source and make Phase-A manifest; encrypt/full-dump source and verify throwaway restore against it.
4. Stop the sole Fly Machine and verify no second machine. Run Phase-B read-only attestation, capture
   preserve/purge state, finalize/sign manifest. Any drift returns to step 2.
5. Owner reviews dry-run. Run `--commit` then `--verify` from owner workstation directly against Neon.
6. Start exactly one Fly Machine. Verify visual app behavior, Fly one-machine state, and
   `/api/readyz.commit` equals intended deployed SHA with `db=up`. This is operational proof, not sole
   data proof.
7. Owner re-imports canonical `.ics` files, captures per-file calendar count receipt and visually checks
   manual and imported calendar rows separately.
8. Keep `microschedule_v2` frozen as archive. Seven days without reopening old app may establish behavioral
   cutover; never delete source solely because import passed.

## 9. Acceptance and authority

- Local/CI proves sanitized tests, red→green source read-only guard, role separation, exact head diff and CI.
  It does **not** prove personal data or production.
- Production acceptance requires source dump restore, signed manifest, atomic/verify receipt, preserve proof,
  Fly exact SHA/`db=up`/one-machine and visual data/calendar receipts.
- PR separates **ĐÃ CHẠY**, **CHƯA CHẠY**, **SUY LUẬN**; no personal content/connection data.
- This remains DRAFT. T1/T2/T3 cannot self-approve implementation, recovery, real cutover or owner sign-off.
