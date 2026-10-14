# Preview, revision and frozen confirmation

Source: `frontend/src/MimiScreen.tsx:112` (`mimi-change-set`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Preview/reject/confirm, revision, receipt/undo and unknown recovery.

## How to get to it (user POV)

Selected deterministic synthetic run → preview → inspect changes → permitted decision.

Real prerequisites: Frozen deterministic provider, authenticated synthetic role, source versions, change-set expiry/idempotency and domain baseline; separately approved confirmation writes.

## Driving it with H14 isolated browser/CLI

mimi-change-set, mimi-preview-actions, mimi-receipt, mimi-unknown-recovery; source backend/app/web/routers/mimi.py.

Observable oracle: No write before confirmation; server-frozen preview matches authorized durable delta and idempotent receipt; rejection/expiry preserve data.

## Gotchas

First metadata driver denies these routes. Stand-in lifecycle evidence does not prove natural conversation quality.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
