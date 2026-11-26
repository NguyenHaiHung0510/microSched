# Calendar navigation and event sources

Current source at the [indexed baseline](README.md): `frontend/src/CalendarScreen.tsx:376`, `frontend/src/CalendarScrollView.tsx:664`, `frontend/src/DayDetailDialog.tsx:559`.

## Sub-features

Month grid, day agenda and Mini navigation, Task/annotation projection and movement, event/source list, manual events and local ICS imports.

## How to get to it (user POV)

Synthetic login → **Lịch**. In the scroll view choose month Grid or Agenda and open a fixture day. The top-level list view opens event ranges and source controls.

Real prerequisites: Freeze Vietnam timezone, dates, ICS input/source and expected projection; separately approved import/event writes.

## Driving it in a current synthetic candidate

Use `calendar-view-toggle-grid` / `calendar-view-toggle-list` for the top-level switch. In the scroll view, use `calendar-mode-toggle-grid` / `calendar-mode-toggle-agenda`, `calendar-today-button` and `calendar-toggle-sidebar`. The day targets are `calendar-day-cell[data-day]` or `calendar-agenda-day-button` then `calendar-agenda-open-detail`. Scope the result to `calendar-day-dialog`. In list view use `calendar-manual-source-button` and `calendar-source-row[data-source-id]` for owned sources. **Thêm nguồn lịch** opens the ICS file dialog. Scope `calendar-import-button` (**Nhập lại**) to the existing ICS source and compare `calendar-import-report` with the owned import fixture.

Oracle: The VN date and Task/Event/annotation membership agree with the frozen fixture and canonical responses. Read `/api/calendar/events` and `/api/calendar/sources` for event/source state. Import, move/undo and invalid interval assertions require distinct scoped write and durable oracles. See the dated recipes below for selectors and evidence of those seams.

## Gotchas

Import is distinct from task export. No subscription to real external calendar or live OAuth grant.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.

## Historical 093 interval feedback

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

## Historical 094 — move Task and day annotation

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
