# Run observations, context and recovery

Source: `frontend/src/MimiScreen.tsx:744` (`mimi-run-context-inspector`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Pending/running/terminal, cancel/pause/resume/reconcile, context checkpoint and runtime usage.

## How to get to it (user POV)

Fixture conversation → Run rail or context chip/Chi tiết kỹ thuật; only authorized deterministic controls.

Real prerequisites: Frozen run/call/event/checkpoint/oracle with exact terminal/recovery states; deterministic local lane separately prepared.

## Driving it with H14 isolated browser/CLI

mimi-run-context-inspector, mimi-run-observations, mimi-progress, MimiRunObservations.tsx and MimiContextRail.tsx.

Observable oracle: UI/wire/durable run identity converge; pending control ack is not terminal; requested vs actual route/cost preserves UNKNOWN where unreported.

## Gotchas

Closing browser/SSE does not mean run unsent/cancelled. Do not silently substitute model or activate paid routes.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
