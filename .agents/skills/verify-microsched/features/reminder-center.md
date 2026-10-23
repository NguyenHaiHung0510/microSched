# Reminder center

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
