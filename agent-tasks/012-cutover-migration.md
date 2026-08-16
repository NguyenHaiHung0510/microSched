# 012 — Cutover: đưa dữ liệu thật từ Postgres v2 sang Neon, rồi ngừng dùng app cũ

> **Executor: T2 (route chọn từ Runtime Catalog lúc giao) · Bậc L1 · effort đề xuất high.**
> **Trạng thái: DRAFT — refresh 2026-08-16.** Các quyết định ở §3 đã được chủ duyệt; bản chi tiết này
> còn chờ exact-head adversarial review và strategic sign-off của chủ. DRAFT **không** cho phép thi công
> script, chạy rehearsal, chạm Neon hay cutover thật.
>
> Cutover thật là nghi thức local do chủ giám sát. Executor không nhận secret, dữ liệu cá nhân, URL DB
> thật, PIN, cookie hay dump; không in plaintext task/note/event, endpoint Push hoặc token/session.

## 0. Phạm vi và hard boundary

Lô implementation sau khi spec được duyệt sẽ làm một script one-shot, test fixture giả đã sanitize và
runbook. Nó đọc Postgres local `microschedule_v2` **read-only**, transform tập được map, rồi thay toàn
bộ **domain content mock/trash đã được chủ cho phép purge** ở Neon bằng tập đó.

Không làm:

- không sửa schema/migration; target phải đang ở exact migration head trước khi chạy;
- không sửa hay xoá `microschedule_v2`, SQLite `todo.db`, hay archive nguồn;
- không import lịch học/thi từ v2. Chỉ mang event thêm tay; lịch gốc vẫn import `.ics` qua 010a;
- không đụng `app_setting`, `session`, `push_subscription` hoặc `alembic_version` ở target;
- không coi `/api/readyz` một mình là bằng chứng dữ liệu đã đúng.

`message` là hội thoại AI tương lai đã mã hoá; `audit_log` là metadata trace AI/tool. Nếu hiện có ở
target, cả hai cùng task/note/calendar/day annotation/tracker/subscription/reminder đều là mock theo
quyết định chủ 2026-08-16 và được purge trong transaction. Đây không suy ra rằng hai bảng luôn là rác
ở tương lai.

## 1. Cổng vào — thiếu một dòng là dừng

1. **Task 022 đã merge, deploy và được verify viewability thật.** Không chỉ có spec: Task screen phải
   xem/reach được toàn bộ lịch sử theo timeline bounded, không còn giới hạn 100/offset. Đây là hard
   prerequisite để không đổ dữ liệu thật vào UI không xem hết được.
2. Target schema khớp exact Alembic head và app role có đúng quyền DML. Script kiểm catalog/column/
   constraint cần dùng, không chấp nhận `alembic current` làm bằng chứng duy nhất.
3. Chủ xác nhận app mới dùng hằng ngày được, 010a/010b và 011 đã production-accepted, giá/backup được
   re-check theo `docs/cost-brief.md` tại ngày chạy.
4. Chủ làm source identity gate: đúng máy/database `microschedule_v2`/source read-role và schema
   `public`; target gate chạy `current_user` và bắt buộc đúng `microsched_app`, không migrator/owner.
   Script in hostname/database/user đã redaction và xác nhận fingerprint DDL/source identity
   expected. Lệch bất cứ thành phần nào là abort trước read/target connection.
5. Chủ đồng ý maintenance window: old app đóng/freeze và sole Fly Machine dừng trước transaction target.

Không hardcode snapshot 163/191 hay bất kỳ count lịch sử nào. Count, set ID, transformation formula và
digest được đo lại **sau source freeze, ngay tại cut-off** (§6).

## 2. Mapping nguồn → target

| Source `public` | Target `microsched` | Quy tắc |
|---|---|---|
| `tasks` | `task` | giữ UUID cũ; status `open/completed`; priority map 6→3; source `archived` là fail-closed (§3) |
| `task_items` | `task_item` | giữ ID/FK/position; chỉ cha được map |
| `notes` | `note` | giữ UUID, title/body/timestamps, pinned/priority |
| `note_items` | `note_item` | `is_done` → `is_completed`; giữ position; chỉ cha được map |
| manual legacy calendar events | one target `calendar_source` + `calendar_event` | manual predicate bằng `external_uid LIKE 'manual\\_%' ESCAPE '\\'`; `v1-schedule-*` bỏ để import lại `.ics` |
| `priorities` | `task.priority`, `note.priority` | map theo **tên** trong §3; không tạo bảng |
| `app_settings`, `agent_action_log`, source version/history/backup tables | — | không map |

Không có `--skip-calendar`: lịch manual là một mapped component, nên bỏ nó là một run khác không cùng
hợp đồng. Dry-run luôn in hai bucket `manual_*` và `v1-schedule-*`; `manual_* = 0` là kết quả hợp lệ,
nhưng vẫn có digest/count rỗng trong manifest.

## 3. Quyết định chủ duyệt 2026-08-16

### 3.1 Data và preserve boundary

- Mọi **domain content hiện hữu trên production** là mock/trash và purge-approved: `task`, `task_item`,
  `note`, `note_item`, `calendar_source`, `calendar_event`, `day_annotation`, `tracker_group`, `tracker`,
  `entry`, `subscription`, `reminder_dispatch`, `message`, `audit_log`.
- Operational state phải nguyên vẹn: `app_setting` (PIN/config), `session`, `push_subscription` (thiết bị
  thật vừa verify), `alembic_version`. Không dump, alter hay copy lại chúng vào target.
- Không có rollback value cho mock target ⇒ **bỏ yêu cầu full Neon target dump**. Trước transaction bắt
  buộc có count + sorted-ID digest + full-row canonical digest cho từng preserve table. Nếu thực tế tiện
  và an toàn, tạo thêm **small encrypted preserve-set export** chỉ cho các table preserve; không phải full
  target dump. Export không vào repo và không được mở trong PR.
- Ngược lại, source phải có full `pg_dump -Fc` mã hoá bằng `age`, timestamped, ngoài repo, và được verify
  restore vào Postgres throwaway: catalog + count + canonical digest trùng manifest trước khi target write.

### 3.2 Source validity và priority

Tập source chỉ hợp lệ nếu tất cả status/position/reference cần map đều hợp lệ. Trước khi mở target
transaction, abort nếu có status khác `open|completed|archived`, `task_item.position`/`note_item.position`
âm, child thiếu cha, priority null/name lạ/duplicate hoặc manual event có `ends_at <= starts_at`. Source
`tasks.status='archived'` **hoặc** `notes.archived_at IS NOT NULL` có count >0 là fail-closed: script in
count/ID digest (không plaintext), không import một phần và hỏi chủ quyết. Target chưa có status archived;
không được tự bỏ hay tự thêm schema.

```python
PRIORITY_MAP = {
    "Quan trọng hơn TN": "p1", "Nguy hiểm": "p1",
    "Bỏ là nhót": "p2", "Phải làm": "p2",
    "Nên làm": "p3", "Optional": "p3",
}
```

Tất cả source rows map với `is_private=false`, `deleted_at=NULL`; target-only defaults được khai rõ trong
canonical formula. Không qua API DTO/Store `require_uuidv7`: historical source UUID có thể v4. Script dùng
table model/SQLAlchemy insert có explicit field, nhưng vẫn tái tạo các invariant liên quan và không dùng
`ON CONFLICT DO NOTHING` để che drift/overlap.

### 3.3 Manifest, identity và canonical proof

Sau cut-off script tạo manifest local encrypted, immutable trong buổi chạy (ký bằng local signing key nếu
runbook đã provision; nếu chưa có key, file digest có permissions owner-only và operator ký receipt tay).
Manifest chứa version script/git SHA, source/target identity fingerprints không secret, schema revision,
transform version, UTC cut-off, và cho **mọi component map** (`task`, `task_item`, `note`, `note_item`,
`calendar_source`, `calendar_event`) cùng preserve table: count, sorted identity-key digest, full-row digest
(`alembic_version` dùng `version_num`, các bảng còn lại dùng `id`).

Canonical row hash dùng exactly ordered fields của **hình target sau transform**, UTF-8 length-prefixed
encoding; UUID lower-case hyphenated; timestamp RFC3339 UTC fixed microseconds; DATE ISO; NULL token;
bool `true|false`; decimal fixed canonical; JSON sorted keys/no whitespace; text raw UTF-8 (không trim).
Digest là SHA-256 của rows sort theo UUID plus component name/version. Hash tất cả field, không chỉ
`id|title`: task/note prose, status/priority/pin/privacy/delete/timestamps; child content/completion/
position/FK/timestamps; source name/kind/color/visibility/timestamps; event source/FK/title/location/
description/all-day/hidden/timestamps. Giá trị plaintext chỉ đi vào hash local, không stdout/PR.

Target manual `calendar_source.id` phải là UUIDv7 sinh **một lần trước manifest**, được record như expected
ID và signed/actual inserted ID; không sinh lại khi retry. Script abort nếu manifest stale, component
formula/version drift, target schema drift, preserve digest drift, hay bất kỳ expected mapped ID overlap
với preserve table/record trái contract. Post-import requires exact count, exact sorted ID set và exact
full-row digest for each mapped component — không phải subset và không chấp nhận "target có nhiều hơn".

## 4. CLI và transaction contract

CLI uses an argparse mutually-exclusive mode group (at most one explicit flag; no flag means dry-run):

```text
cutover_v2 --dry-run | --commit | --verify
```

`--dry-run` và no flag đều ghi 0 byte target; `--commit` require explicit
`--confirm-target-host=<production-host>` và manifest path vừa tạo; `--verify` require manifest committed
và không được sửa target. Không có `--skip-calendar`, cờ "force", hoặc mode ngầm. URL chỉ từ environment;
parser in host/database đã redact, không in credential.

Source engine dùng `default_transaction_read_only=on`; test RED proof phải cho một `UPDATE` source fail
Postgres `25006`. Target dùng app role, nhưng preflight read-only source và target identity/catalog trước.
Sau preflight/manifest, `--commit` mở **một** target `AsyncSession` và **một** `db.begin()`:

1. re-read preserve counts/digests and require equality with manifest;
2. purge theo exact child-before-parent order: `reminder_dispatch`, `entry`, `subscription`, `tracker`,
   `tracker_group`, `calendar_event`, `calendar_source`, `task_item`, `task`, `note_item`, `note`,
   `day_annotation`, `message`, `audit_log`;
3. insert all mapped components in parent-before-child order, with actual IDs exactly manifest expected;
4. run canonical count/ID/full-row verification **inside the same transaction**;
5. commit only if every assertion passes. Any exception rolls back both purge and import atomically.

An `ON CONFLICT`, unexpected existing mapped row, count mismatch, foreign-key mismatch or preserve-table
change is error/rollback, never an idempotent no-op. The run is intentionally not re-run automatically.

If a post-commit check later fails, primary rollback no longer exists. With Fly still stopped, fix-forward
may delete **only manifest-recorded inserted rows** in child-before-parent order and rerun a newly frozen
cut-off; it must never restore a full target dump. The already-purged domain content was approved trash.

## 5. Tests and rehearsal

Fixture DDL/data must be synthetic and sanitized; no copied owner data, dump, title/body, endpoint, email
or PIN. Cover at least:

1. valid mixed source maps every component, all canonical hashes and exact ID sets match;
2. unknown priority/status, invalid position, archived source task/note, invalid manual event and missing
   child parent each abort before target mutation;
3. source UPDATE gets `25006`; URL/host confirmation mismatch aborts;
4. target seeded with all purge-approved domain tables and preserve tables: commit removes only the former,
   keeps app_setting/session/push/alembic byte-for-byte/hash-for-hash;
5. induced failure after purge/before final verify rolls back source target state atomically;
6. manual event plus `v1-schedule-*` proves only manual rows map; generated source ID is UUIDv7 and exact
   manifest ID; no skip-calendar code path exists;
7. manifest formula/schema/preserve-digest/overlap drift each abort; post-insert altered field fails
   full-field digest even when count and IDs match;
8. source encrypted dump restore verifies against manifest; no plaintext enters test log.

Before production, rehearse the complete manifest/transaction on a **disposable Neon branch** with sanitized
fixture (throwaway Postgres may bổ sung CI only, not replace branch rehearsal). Delete branch after receipt.
This is a rehearsal only, not production acceptance.

## 6. Owner-run maintenance ceremony (after approval only)

1. Confirm all §1 gates, exact implementation commit/CI, operator identity and maintenance window.
2. Close old app, inspect `pg_stat_activity` for `microschedule_v2` until no unexpected session remains;
   set default transaction read-only only as backstop, never terminate unknown session blindly.
3. At the exact cut-off compute source formulas/counts/hashes and create the manifest; create the encrypted
   full source dump then verify its throwaway restore against that manifest. Any source drift means return
   to step 2.
4. Stop the **sole** Fly Machine before target mutation, verify it is stopped and no second Machine exists.
   Run cutover from owner workstation directly against Neon; never through a public endpoint or agent tool.
5. Compute preserve pre-state digest/export, then make the last source consistency read against manifest.
   Any source or preserve drift means return to step 2.
6. Dry-run prints only count/IDs digest/host/formula/version; owner reviews. `--commit` performs §4's one
   target transaction, then `--verify` rechecks committed exact canonical result and preserved state.
7. Start exactly one Fly Machine. Verify visually that the intended app is running; then require
   `/api/readyz.commit` equals the exact deployed SHA **and** `db=up`, check Fly reports one machine, and
   perform authenticated user-facing visual checks for imported task/note/item/manual calendar data.
   `/api/readyz` alone is liveness, not data proof.
8. Keep `microschedule_v2` frozen as archive. After seven days without reopening old app, owner may declare
   behavioral cutover complete; never delete the source simply because the import passed.

## 7. Acceptance and authority

- Local/CI proof covers script tests, sanitized DDL fixture, RED→GREEN read-only guard, lint/format and
  exact PR CI. It does **not** prove real data/production.
- Production acceptance requires the owner ceremony receipts: source encrypted-dump restore, manifest,
  atomic verification, preserve digests, one-machine/Fly exact-SHA/db proof and visual UI check.
- PR must separate **ĐÃ CHẠY**, **CHƯA CHẠY**, and **SUY LUẬN**; no raw personal content or connection data.
- This DRAFT records only approved owner decisions above. T1/T2/T3 may review it, but none may self-approve
  implementation, data mutation, actual cutover, or the owner's strategic sign-off.

## 8. Superseded draft hazards retained for review

The 2026-08-01/02 draft was valuable for identifying traps but is superseded where it conflicts here:
stale `191` count, target-subset verification, full target dump, `--skip-calendar`, target-nonempty
assumption and old archive skip behavior are removed. Retain these audit facts: Task 022 viewability,
source/app-role identity, async source read-only driver, full transaction mechanics, manual predicate,
child/parent FK order, source backup, and no plaintext logs. Exact-head adversarial review must verify
these against current code/migration before implementation begins.
