# Notes and reflections

Source: `frontend/src/App.tsx:178` (`currentTab === 'notes'`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Quick/detail creation, title/detail, pin/sort, reflections and edits.

## How to get to it (user POV)

Synthetic login → Ghi chú → selected note; quick-add or detail dialog only in approved write case.

Real prerequisites: Synthetic note/content/expiry fixtures; current note limits; separate grant/oracle for reflection/save/delete.

## Driving it with H14 isolated browser/CLI

note-list, note-card, note-title, quick-add-note-input, note-create-dialog; inspect NotesScreen.tsx actual controls.

Observable oracle: Correct fixture note and sort/pin state are visible; cancel preserves data; approved save/reflection persists exactly once after reload.

## Gotchas

No real personal note payloads in screenshots. Notes are not covered by task or homepage smoke.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.

## Task098 successor — 2026-10-26

The approved B reader reuses `note-detail-dialog` as a full-region reading surface,
without a new route. `note-reader-back` restores the opener's visual position and
filter context. Section buttons navigate body → checklist → reflections within the
actual reader scroller. Item controls are exactly `note-item-edit`, `note-item-top`,
`note-item-delete` (Pencil/ArrowUpToLine/Trash). Adjacent up/down is removed.

`POST /api/notes/{note_id}/items/{item_id}/move-to-top` compares the complete
content-free `{id, position, is_completed}` snapshot under the parent lock, then
moves within the current completion group in one transaction. Stale snapshots are
409 without writes; an exact unchanged postcondition permits lost-response replay.
Tick does not reorder. No pin field or DDL. Existing private visibility and child
delete confirmation remain required.

Preview is body6 / first reflection4 / first3 unfinished items×4 rendered lines;
completed items are also clamped when explicitly disclosed. Full-card collapse
resets both checklist disclosures. Stored content is never truncated.

Focused author oracles: `frontend/e2e/note-reader-history-task-098.spec.ts`,
`frontend/e2e/notes-checklist-045.spec.ts`, `backend/tests/test_note_order.py` and
`backend/tests/test_notes_api.py`. Author evidence is separate from independent QA,
CI, device and production. See `docs/reference/ui-behavior.md`.
