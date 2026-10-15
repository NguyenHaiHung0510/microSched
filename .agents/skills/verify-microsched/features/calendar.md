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
