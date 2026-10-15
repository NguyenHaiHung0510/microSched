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
