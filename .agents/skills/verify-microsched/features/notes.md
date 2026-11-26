# Notes and reflections

Current source at the [indexed baseline](README.md): `frontend/src/NotesScreen.tsx:477` and `:972`, `backend/app/web/routers/notes.py:159`.

## Sub-features

Quick/detail creation, title/detail, pin/sort, reflections and edits.

## How to get to it (user POV)

Synthetic login → **Ghi chú** → owned note title or `note-open-full`. Read via the full-region reader. Quick-add, the separate full-create dialog, checklist operations and reflections need the corresponding synthetic write case.

Real prerequisites: Synthetic note/content/expiry fixtures; current note limits; separate grant/oracle for reflection/save/delete.

## Driving it in a current synthetic candidate

Start in `note-list`. Use `note-find`, `note-sort`, `note-card`, `note-expand` and `note-detail-dialog` / `note-reader-back`. Quick/full creation uses `quick-add-note-input` or `note-create-dialog`. The reflection form uses `note-future-reflection-dialog`. Use the checklist controls and exact order oracle below.

Oracle: Correct fixture content and sort/pin state, back-to-opener position and loaded search scope. Canonical `/api/notes/{id}` and its checklist reflect only approved writes after reload. Cancellation produces zero writes.

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
