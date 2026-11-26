# Task tab and task lifecycle

Task098 (2026-10-26): shared `TaskForm` uses `task-title-input`, a wrapping,
autogrowing textarea retaining text-input CR/LF, Enter and IME semantics. It never
rewrites an unchanged stored title. Focused cases cover Task-tab edit, calendar
month/day and agenda edit, plus a forced `field-sizing:fixed` fallback. WebKit and
physical iPhone require separate evidence; Chromium viewports do not prove them.

Current source at the [indexed baseline](README.md): `frontend/src/TasksScreen.tsx:573` and `:909`, `frontend/src/App.tsx:134`, `frontend/src/TaskTitleInput.tsx:32`.

## Sub-features

Task list/timeline, filters, create/edit/checklist/complete/delete and navigation to default Task.

## How to get to it (user POV)

Synthetic login → **Task** tab or menu, or explicit `/tasks`. A miGarden-enabled mobile shell puts Task in **Ứng dụng**. Choose the fixture-owned date/task.

Real prerequisites: Fixture tasks with frozen ID/status/date/timezone; a separately authorized domain-write case for any save/delete.

## Driving it in a current synthetic candidate

Use role `tab` **Task** when it is in the nav. Use `quick-add-input` / `quick-add-submit` for quick creation, `task-create-dialog` for full creation, and `task-card[data-task-id]` for the owned row. Its `task-title` opens `task-detail-dialog`. `task-edit` uses the shared `task-title-input`. Child removal in an existing Task shows `task-child-delete-confirm` before `task-child-delete-commit`.

Oracle: Match day/filter/status and actual Task/checklist IDs against `/api/tasks` or `/api/tasks/timeline` as applicable. Approved writes match canonical and durable state after acknowledgement and reload. Cancel produces zero domain writes. See `frontend/e2e/tasks.spec.ts` and `frontend/e2e/task-title-suggestions.spec.ts` for existing cases.

## Gotchas

Metadata-only Mimi smoke reads initial Task data; it does not verify task lifecycle. No destructive/real-data operations in initial batch.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
