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
