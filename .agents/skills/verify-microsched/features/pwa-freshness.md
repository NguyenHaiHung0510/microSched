# PWA and visible data freshness

Source: `frontend/src/LiveStatus.tsx:43` (`app-live-status`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Active-query freshness, offline/paused/error status; install/service worker and push entrypoints governed separately.

## How to get to it (user POV)

Signed-in Task/Notes/Tracker view → app-live-status; inspect isolated worker lifecycle only in an approved platform case.

Real prerequisites: Frozen query timestamps/network state; disposable profile and explicit platform capability; service workers are blocked in initial browser proofs.

## Driving it with H14 isolated browser/CLI

app-live-status data-state; frontend/src/sw.ts and vite.config.ts define worker boundary.

Observable oracle: Status reflects active query freshness and connectivity; independent offline/outbox/push oracle required for each durable capability.

## Gotchas

Emulation ≠ physical iPhone/PWA install. No permission prompt/real device subscription. First proofs do not test workers.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
