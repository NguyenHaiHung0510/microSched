# Reminder center

Task098 (2026-10-26) adds an ACK-position oracle in
`frontend/e2e/note-reader-history-task-098.spec.ts`: 125 synthetic occurrences over
three days, three loaded pages, all/unhandled filters, disclosure, failure/retry,
current/next/last-row anchors, and lock with late ACK. ACK patches only an existing
cache row using the server timestamp, retaining query identity and loaded pages
during background refetch. Private/auth purge still removes pages and pending UI.
The task098 browser config targets only its explicitly owned preview15198; do not
reuse legacy driver ports or infer physical-device/independent acceptance.

Source: `frontend/src/App.tsx:139` (`<ReminderCenter`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Reminder sections, paging, linked entity and action entrypoints.

## How to get to it (user POV)

Synthetic app header → Nhắc nhở → section → fixture reminder.

Real prerequisites: Fixture reminder counts/timing/target and private visibility; delivery/push disabled in first namespace.

## Driving it with H14 isolated browser/CLI

reminder-center-open, reminder-center, reminder-row; inspect ReminderCenter.tsx button names.

Observable oracle: Rows/section/paging agree with synthetic fixture; target links open intended entity; action persistence requires distinct approved case.

## Gotchas

An empty drawer is not delivery proof; no real push subscription/permission request.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.

## R3A backend receipt projection (092)

Additive authenticated `GET /api/reminder-history`; existing `/api/reminders`
Upcoming/Attention/configuration routes are unchanged. Backend source:
`backend/app/domain/reminder_history.py` and `backend/app/web/routers/reminder_history.py`.
No History UI or handled/bulk/offline controls in this phase; UI remains NOT_RUN.

Focused oracle: `backend/tests/test_reminder_history_pg.py` on an explicitly owned,
isolated disposable PG. Four real origins: one-shot Task/Event/Tracker/DayAnnotation,
recurring tracker dispatch, subscription dispatch and Mimi intent. There is no Note
origin. Typed occurrence refs dedupe batch members/device retries; current source
content is not a historical snapshot. Only one-shot sent_at proves acceptance time;
legacy dispatches expose day precision, never current schedule clock or fake midnight.

SQL gates/filter precede keyset LIMIT; page default50/max100, no exact total.
Current private gate/owner/filter/Mimi eligibility bind the cursor. Locked private
occurrences are omitted; one constant abstract notice has no identity/time/count and
does not assert private inventory. Unavailable/deleted/orphan sources are omitted.
Mixed batch members never expose a private count. Unlock permits full current private
content; UI RAM/cache purge awaits its separately granted UI phase. All responses
no-store, no new public-cache allowlist. Reads do not acknowledge receipts, confirm
entries, mark handled or mutate sources.

Author API/PG evidence belongs to the versioned R3A handback; independent H1-H4,
History UI H8, R3B/O1, physical device and production acceptance remain NOT_RUN.

## R3 night successor — history B and independent handled state

Supersedes only the R3A phase's "no UI/handled" scope statement above. Open
Nhắc nhở → Lịch sử: latest-first server day groups, source/send-status/handled/date
filters, keyset page50, explicit unknown legacy clock, typed source links. Note is
not a history origin. Handled is an online-only occurrence ACK, never Task completion,
Entry confirmation, schedule change or Mimi read/delivery.

Single desired=true keeps its first timestamp. Selected checkboxes and **all matching
the filter** both prepare an exact server manifest and show count/cutoff/confirmation;
all matching includes unloaded pages. Commit rechecks current disclosure atomically.
Retries retain the same batch ID/result; expired uncommitted selection requires a new
visible preparation. Private lock clears history pages, selection and confirmation
RAM/cursor, while a mounted public source draft remains. No history disk-cache entry.
Relevant pending Task/Tracker aggregate blocks ACK/count until resolved.

Focused existing-stack driver: `scripts/r3_history.mjs --output ABS_OWN_REPORT_ROOT
--case common|private|draft|bulk`. It requires the owned092 loopback8002/4175,
current HEAD in readyz/db=up, ignored `.local/r3-092/runtime.json` and exact
`fixture-manifest.json`; refuses091/remote egress, uses isolated contexts and unique
receipt folders. It intentionally mutates only explicit synthetic occurrence ACKs
and local private session gates. Inspect durable state/earlier receipts before any
retry; its initial common/bulk expectations are not an automatic repeatable seed.

Author actual PG/schema:37 focused checks PASS; backend1216PASS/1SKIP;
frontend293PASS. Actual own UI common/draft/bulk PASS; private01 partial failure
retains its successful cross-page purge assertion and a later driver-label timeout.
The unfinished public-draft step passed separately. Receipts, fixture correction,
schema-role/restore/nonempty rollback proof and exact candidate binding are in the
versioned R3 night handback/freeze. This is author evidence; independent runtime,
required CI, device and production acceptance remain separate/NOT_RUN here.

## DEV328 grouped repair — F01/F02/F03

The shared PG fixture now owns its public synthetic32-byte key and settings/cipher
caches, independent from caller configuration. Unreleased0019 resets only its two
newtable ACLs after inherited defaults:association SELECT/INSERT,manifest
SELECT/INSERT/UPDATE; associationUPDATE/DELETE,manifestDELETE and appDDL are refused.
No existing receipt/source/default-role privileges change.

The focused driver treats both private/draft cases as sensitive:failure stores only
`PRIVATE_CASE_FAILED_DETAILS_SUPPRESSED`,never raw exception or a failure screenshot.
Successful private screenshots require verified purge. Diagnostic
`--case private --prove-private-failure` deliberately fails while private content is
visible,before preparation; expected receipt has no pixels/rawcanary. It is not a
product PASS. Follow with `--case public-preview` to inspect all four origins,paging
and existing handled state without new ACKs or fixtures. Unique output folders and
original failed receipts remain. Guard mutation/restore unit proof uses memory only.

DEV328 author evidence:34affected testsPASS with caller key absent,3helper guard
testsPASS,actual deliberate private safeFAIL + restored public previewPASS. Existing
bf7 business/runtime proof is inherited only where bytes unchanged. Current CI and
independent affected source/runtime closure belong to PM after the new freeze.
