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
