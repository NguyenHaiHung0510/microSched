# Calendar navigation and event sources

Source: `frontend/src/App.tsx:108` (`currentTab === 'calendar'`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Day scroll/detail, task projection, manual event and imported ICS source.

## How to get to it (user POV)

Synthetic login → Lịch → fixture day → day detail/task/event.

Real prerequisites: Freeze Vietnam timezone, dates, ICS input/source and expected projection; separately approved import/event writes.

## Driving it with H14 isolated browser/CLI

calendar-day-cell[data-day=FROZEN_DAY], calendar-day-task; frontend/src/CalendarScreen.tsx and DayDetailDialog.tsx.

Observable oracle: Day detail agrees with fixture task/event date boundaries; projection is consistent; write proof includes durable source/event receipts.

## Gotchas

Import is distinct from task export. No subscription to real external calendar or live OAuth grant.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.

## 093 interval feedback — affected recipe

The historical NOT_RUN above remains historical. Independent before-repro on919 established valid
same-day/cross-midnight200 and a confusing generic422 for an equal interval.093 changes only shared
EventForm feedback; the Owner's exact valid-edit rejection is NOT_REPRODUCED.

Granted isolated093 cell: API8003, production preview4176, PG55493; source/build/config/fixture
binding is required from the current writer handback. Runtime owner launches API using
`python -B -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8003 --no-access-log`
and preview with **process-only `VITE_BACKEND_ORIGIN=http://127.0.0.1:8003`**. Do not rely on Vite's
default8000 or edit a frozen env file. Record full commands, env names (no secret values), hidden
PIDs/actual listeners, logs, finite exits and proxied readyz exacthead/dbup before cases.

Selectors: `calendar-view-toggle-list`, `calendar-view-toggle-grid`,
`calendar-day-cell[data-day=FROZEN_VN_DAY]`, `calendar-day-event[data-event-id=OWN_ID]`,
`calendar-event-form`, its two `input[type=datetime-local]` fields,
`calendar-event-interval-error`, save/create buttons. Dialog and inline list wrapper share the form.
Invalid end <= start must show the exact Vietnamese message under end, focus that editable input,
connect `aria-describedby`, set `aria-invalid`, send0HTTP and preserve all draft values. Correction
clears the message and saves; compare offset-aware intended VN instants to canonical API + own-ID PG.
Direct invalid API writes must still return422 and leave the row unchanged. Server validation,
source ownership, public calendar boundary and relative/absolute reminder freshness remain intact.

Bounded direct cached Playwright driver: `scripts/calendar_time.mjs --origin http://127.0.0.1:4176
--output ABSOLUTE_UNIQUE_OWN_OUTPUT --python EXISTING_READONLY_PYTHON --oracle
ABSOLUTE_093_LOCAL_ORACLE`. It checks its owned output/origin/PG oracle scope, uses a fresh isolated
synthetic-owner context, creates only manifest-owned public source/event, writes IDs immediately,
logs out and closes that context. Existing ignored093 `.local/r8-093/oracle.py` reads only those IDs
via own local transport. No provider/push/real profile. Retain failed attempts; inspect unknown
effects before a fresh attempt. New author output is not independent acceptance. Builder receipts
and immutable full freeze are in the current grant's `techlead/o8-093-dev328` output.

## 094 — move Task and day annotation

Month-grid desktop drag and day-detail **Chuyển ngày** use the same move action. Mobile uses the
visible tap button; keyboard can open the day and submit the date form. Tasks retain date precision
or their Vietnam clock, including seconds/milliseconds. A range annotation shifts from the grabbed
day, including a middle day, and retains its inclusive length. Undo restores the full prior schedule.
Calendar-source sessions have no movement handle. Existing desktop-only quick creation stays intact.

The action requires an online, verified session and an unlocked private display where applicable.
Task moves use the existing typed outbox and same-object barrier. Local admission remains pending
until queue/reconciliation settlement and a matching canonical GET; unknown/held/rejected commands
are retained. Annotation errors restore the local date projection and retain an editable retry draft.
Private lock purges the move dialog; no private pixels or payloads belong in reports.

Owned094 recovery: API8004, preview4177, PG55494/database `microsched_r4_094`, labelled container/volume
`r4-094-20261024-microsched` / `r4-094-20261024-microsched-db`. Use the current frozen handback and
ignored `.local/r4-094/runtime.py` for exact owned launch commands and env **names**. Preview requires
process-only `VITE_BACKEND_ORIGIN=http://127.0.0.1:8004`; the default8000 is not this cell. Inspect actual
PID/command/listener and proxied readyz before lifecycle actions; preserve fixtures and failed attempts.

Selectors: `calendar-day-cell[data-day]`, `calendar-day-chip-task[data-task-id]`,
`calendar-day-annotation[data-annotation-id]`, `calendar-day-task[data-task-id]`,
`calendar-annotation-detail[data-annotation-id]`, `calendar-task-move`, `calendar-annotation-move`,
`calendar-move-dialog`, `calendar-move-preview`, `calendar-move-error`, `calendar-move-pending`.
Cancel restores focus to the grabbed day. New form input/action controls are at least44px high.

Bounded direct driver: `scripts/calendar_move.mjs --origin http://127.0.0.1:4177 --case
desktop|mobile|touch|diagnostic|private --output ABSOLUTE_UNIQUE_OWN_OUTPUT --python
EXISTING_READONLY_PYTHON --oracle ABSOLUTE_094_LOCAL_ORACLE`. Desktop/mobile create additive synthetic
fixtures, recording returned IDs immediately. Touch and diagnostic accept `--resume OWN_PRIOR_RECEIPT`
to reuse settled public IDs. Desktop drag uses native pointer delivery; the retained failed locator
attempts are driver evidence, not a product PASS. The own-ID read-only PG oracle corroborates API
schedule/reminder snapshots. Private mode captures neither pixels nor raw error details. Each mode
logs out and closes its isolated context. Its `nativeDrag` uses Playwright `page.mouse` down/move/up
and browser-native dragstart/dragover/drop, with durable PATCH200/undo proof. This differs from
JavaScript `dispatchEvent` and the mocked API regression layer. Final mocked browser result is
5PASS/1SKIP; the SKIP is desktop HTML drag on mobile, whose native-touch alternative has its own
real API/PG receipt. No real profile, provider, reseed/reset or baseline cleanup.

Current author receipts and full freeze: granted `techlead/r4-094-dev328`. These are builder confidence;
independent QA, required CI, physical-device and production acceptance remain separate gates.
