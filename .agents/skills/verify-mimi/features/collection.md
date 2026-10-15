# Task collection review and revision

Source: `frontend/src/MimiCollectionReview.tsx:39` (`mimi-collection-review`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Full plan entries/checklists/reminders, drawer/inspector/paging, revision/confirm/reject/undo.

## How to get to it (user POV)

A separately prepared synthetic collection proposal → Xem và duyệt or Inspector B → Xem đủ entries.

Real prerequisites: Collection flag, deterministic plan/entry/source versions and complete oracle from docs/mimi-task-collection-contract.md; separately authorized domain writes.

## Driving it with H14 isolated browser/CLI

mimi-change-set, mimi-collection-review, mimi-review-row, mimi-entry-details, mimi-preview-actions.

Observable oracle: Every planned entry is inspectable; frozen before/after/version matches authorized transaction and receipt, no partial silent apply.

## Gotchas

Collection disabled in first namespace. Broad map documents prerequisite; it does not install provider doubles or run a three-feature pilot.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
