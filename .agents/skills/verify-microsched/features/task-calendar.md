# Task tab and task lifecycle

Source: `frontend/src/App.tsx:168` (`currentTab === 'tasks'`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Task list/timeline, filters, create/edit/checklist/complete/delete and navigation to default Task.

## How to get to it (user POV)

Synthetic login → Task; choose fixture-owned task/day; app logo returns to default Task.

Real prerequisites: Fixture tasks with frozen ID/status/date/timezone; a separately authorized domain-write case for any save/delete.

## Driving it with H14 isolated browser/CLI

role tab Task; task-card scoped by actual fixture task-id; inspect TasksScreen.tsx form/action selectors before writes.

Observable oracle: Correct task opens and expected synthetic contents/status show; an authorized save must match durable row delta and survive reload. Cancel leaves data unchanged.

## Gotchas

Metadata-only Mimi smoke reads initial Task data; it does not verify task lifecycle. No destructive/real-data operations in initial batch.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
