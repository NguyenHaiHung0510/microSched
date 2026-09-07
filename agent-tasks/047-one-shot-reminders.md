# 047 — One-shot reminders

Status: IMPLEMENTED; production migration 0013 APPLIED; current delivery/CI receipts at [PR 213](https://github.com/NguyenHaiHung0510/microSched/pull/213). Owner approved 2026-09-07 in task `01a07c4f-aa74-7ef2-888b-a1b3abf87b17`, including 45-minute late delivery and autonomous continuation after the UI lane, then explicitly approved migration and continued delivery on 2026-09-08. T1 is the writer. Base: develop `0db779a5bd8457a588c59aa3fac6e3ec8bf8de62`; PR211/212 independently verified MERGED, UI task completed. Existing worktrees and untracked files retained.

## Accepted behavior

- One pending one-shot reminder per task/calendar event/tracker, alongside existing recurring tracker reminders. Absolute date/time works without a source deadline. Relative reminders support before/after minutes/hours/days; task date-only and all-day event require an explicit anchor clock time. Preview the resolved Vietnam date/time.
- Absolute reminders retain their time on source changes. Pending relative reminders follow the source. If the new target is in the past or the anchor disappears, save the source and mark the reminder needs-reschedule; never silently send immediately.
- Sent reminders never rearm on source edits. An explicit new reminder is a new occurrence. Complete/delete source cancels pending reminders; restore/reopen never rearms them. Do not add new calendar cancellation semantics.
- At most four provider attempts with existing 30/120/600-second backoff. Server catch-up allowed through 45 minutes inclusive. Beyond that, mark missed; no stale replay flood. Provider TTL must not extend beyond this validity window. Provider handoff is not device receipt or reading; retries may duplicate after uncertain outcomes.
- Source → reminder lock order, durable revision checks before provider handoff. Already handed-off network calls cannot be recalled. Editing during an uncertain send requires explicit rescheduling rather than automatically creating another send.
- Private push is generic; APIs, listing, history, cache and open-source actions inherit current source visibility. No copied private titles in reminder storage.
- Global bell opens a side panel on desktop/fullscreen mobile with upcoming, attention and collapsed history; source-local creation/edit remains available. Recurring entries link to their existing source editor.

## Implementation and finite resources

Use existing PostgreSQL, in-process owned scheduler, event-driven reload and Web Push. No extra service, timer poll, Redis/Celery, infrastructure or costs. New rows use typed nullable foreign keys with exactly one source, partial uniqueness for active reminders, bounded list/page queries and four attempts. No source prose in reminder table. Privacy remains source-derived.

Migration is additive; old application can run on expanded schema. The initial production deployment hold was satisfied by the separately Owner-approved migration recorded below. Never auto-migrate on deploy or expose credentials/personal records. Local disposable PostgreSQL only for destructive migration/QA.

## Acceptance

Targeted pure and real PostgreSQL tests: absolute/relative/date-only; future/past/missing anchors; completion/delete/restore; duplicate create and stale revision; private lock list/detail/write and cache purge; 45-minute boundary; retries/exhaustion/no device; recovery from sending; provider handoff race/version; old recurring grace unchanged; schema migration/drift. Safety guards require intended RED then restored GREEN receipts.

Frontend lint/typecheck/unit/build; backend Ruff/non-PG/PG; existing required CI checks and repository hooks. Browser synthetic tests at 390×844 and 1280×800 for editing, preview, errors, management and privacy; full local app preview. Independent review if available through an authorized transport, otherwise do not call self-review independent. Real iPhone/Safari and production acceptance remain NOT_RUN until actually observed.

## Adjacent agreed follow-up

Homepage: measure payload/cache and bounded synthetic load, then propose controls/costs; no new CDN/security policy/autoscale/CAPTCHA without concrete Owner decision. Backup keys: quarterly/post-change check principle accepted; agent must not inspect key stores or real backups or publish personal storage details. Do not mix these into reminder migration.

## Checkpoint

2026-09-08: implementation complete in `feat/047-one-shot-reminders`; application/test code frozen at `4aa26ed2938f5d4bb65cb3bdeb0a9fce9407c327`. New migration 0013, parent-gated API, durable dispatcher, after-commit timer reload, source editors and global management are implemented. No new dependency/service/polling. Local preview uses only disposable synthetic PostgreSQL. Production and physical-device acceptance NOT_RUN. Check [PR 213 checks](https://github.com/NguyenHaiHung0510/microSched/pull/213/checks) for current exact-head CI; initial published head passed Backend, Frontend, Production dependency, Repository hooks and Secret scan while longer jobs were running. Hourly continuation `microsched-reminders-hourly-continuation` is to pause when CI and independent work finish and only the Owner migration gate remains.

## Local evidence — 2026-09-08

These are observed local runs on the pre-commit candidate; CI will bind committed code independently. Commands run in their backend/frontend directories. Raw local logs are ignored artifacts, not public CI receipts.

| Layer | Command / observation | Result |
|---|---|---|
| Backend | `pytest -m 'not pg' -q -p no:cacheprovider` | 426 PASS; 211 PG deselected |
| Database | `pytest -m pg -q -p no:cacheprovider`, throwaway pgvector18, canonical CI roles | 211 PASS; before final after-commit dependency refinement, which has focused and full non-PG coverage |
| Pure + PG feature | `pytest tests/test_one_shot.py tests/test_one_shot_pg.py` | 26 PASS |
| Frontend unit | `npm test` | 145 PASS |
| Full browser | `npm run e2e` | 266 PASS, 34 conditional production-cell cases SKIPPED; before device controls and nonblocking refetch refinement |
| Feature browser | `npm run e2e -- e2e/reminders-047.spec.ts` | 8 PASS after final device/nonblocking-refetch refinements; mobile and desktop |
| Native local app | `node scripts/qa-reminders-047.mjs` | PASS 390×844 and 1280×800: actual save, preset, center, completion, ≥44px buttons |
| Docker runtime | `REMINDER_QA_LOGIN_URL=http://127.0.0.1:8047 node scripts/qa-reminders-runtime-047.mjs` | PASS all source editors, actual private list/detail/cancel guards, no-store, long unbroken/Vietnamese mobile text, HTTP source reschedule, real timer wake → no_device |
| Image | Production Dockerfile, local synthetic config, 1 CPU/256MB | Build/start PASS; real scheduler ownership acquired; idle memory observed 96.79 MiB |
| Migration | Upgrade/drift/drop guard; downgrade with nonempty synthetic table | `migration_drift=empty`; unsafe-drop scan PASS; downgrade refused with expected message, revision 0013 and 11 synthetic rows retained |
| Safety RED/GREEN | Remove source read gate, then restore | RED caught forbidden reminder in locked list; restored GREEN PASS |
| Safety RED/GREEN | Remove source-write reload marker, then restore | RED caught missing post-commit reload; restored 2 PASS, commit failure produces no reload |

Review is T1 self-review, not independent review. It found and corrected the pre-commit source-reload race and mutation pending-on-refetch issue. Frozen legacy cutover remains pinned to schema 0012: tests rehearse 0012 then restore head, while the actual script refuses 0013. No broader purge inventory/authority was added.

Repository hooks and secret scanning passed before commit. Only the sanitized commit was published; public documentation contains no personal key-storage locations. This docs-only follow-up preserves the frozen application/test code above. No merge/deploy occurred.

## Owner-approved production migration — 2026-09-08

Authority: after T1 explicitly requested permission to apply 0013, verify schema and continue merge/deploy, the Owner replied “duyệt, tiếp tục đến khi hết việc” in the current task. This grants T1 that bounded delivery action; it does not authorize unrelated infrastructure, backup/key access, production fixture writes or destructive cleanup.

Preflight found production at 0011, not 0012. The configured local runtime/migrator targets matched; a runtime-side normalized target fingerprint also matched without exposing credentials or endpoint names (SSH returned the fingerprint but a nonzero transport exit, so this is partial transport evidence). Missing batch tables and all 0012 data preconditions were verified with boolean-only queries. Standard Alembic applied the required checked-in chain `0011 → 0012 → 0013`, exit 0, transactional DDL with 5-second lock and 60-second statement timeouts. No downgrade, manual stamping, record rewrite or deletion was used.

Post-migration: revision0013, correct table owner, three cascading FKs, three valid active unique indexes and three enabled source triggers. Six CHECKs, three FKs, one PK and eight PostgreSQL18 NOT NULL constraints are all validated. App-role SELECT/INSERT/UPDATE/DELETE were checked individually, schema CREATE remains denied, and an actual app-role `SELECT ... LIMIT 0` succeeded without loading records. Canonical `scripts.check_migration_drift` returned `migration_drift=empty`. The previous deployed app remained at `0db779a5bd8457a588c59aa3fac6e3ec8bf8de62`, `db=up`, immediately after expansion.

The first custom verification used a PostgreSQL-pre18 assumption of ten total constraints and failed; catalog types showed eight additional NOT NULL entries, all valid. Two elevated read-command approval reviews timed out. The unchanged drift checker and typed catalog query then completed successfully with ordinary execution permissions. These were verification/tooling issues, not migration rollback or data repair. Final exact-head merge/deploy receipts belong in PR213 so this historical checkpoint does not masquerade as live state.

### Delivery checkpoint: tool recovery

After successful migration verification, elevated local git commit/push commands and GitHub browser access failed at automatic approval review before execution. Bounded retries and heartbeat resumption also timed out. The Owner subsequently re-enabled the hourly heartbeat and instructed T1 to continue. On resumption, the saved heartbeat was verified ACTIVE at one hour, GitHub commands succeeded, and PR213 remained OPEN/ready/CLEAN with all ten checks successful.

Application code remains frozen at the previously checked head; this receipt is documentation only. Owner authority is sufficient to publish it, refresh exact head/base/checks, CAS merge and verify deployment. Do not reapply 0012/0013 or request a second business approval for this bounded delivery. Final merge/deployment evidence is maintained in PR213; physical device and actual Web Push remain NOT_RUN.

Screenshots remain local under `frontend/output/playwright/reminders-047/`; scripts reproduce them with synthetic data. The Docker image is a local production-build smoke with local auth/config, not full production-cell/device/provider acceptance. The guarded native localhost login issues the synthetic session; no auth gate was weakened for Docker port forwarding. No actual Web Push sent.

## Migration and delivery handoff

The Owner-approved migration gate is satisfied by the receipt above. Finish repository hooks and all configured exact-head CI gates before merge into develop; then verify deployment. Migration remains a separately authorized maintenance action, not a deploy hook. Do not copy credentials into chat or receipts.

Rollback is the previous app on expanded schema. Keep 0013 and reminder rows; never use downgrade as production rollback. Empty-schema downgrade/upgrade is only a disposable QA lane. After schema verification and fresh exact head/base/checks, normal authorized merge/deploy may proceed; verify exact readyz commit and `db=up`. Physical iPhone/Safari and Web Push delivery require separate observation.

## Homepage and key assessment

See [bounded assessment](047-homepage-backup-assessment.md). Measurement-only scope is complete; no infrastructure, cache policy, rate limits, crypto or key-store changes were made.
