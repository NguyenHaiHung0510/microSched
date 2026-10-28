# Private visibility gate

Source: `frontend/src/App.tsx:140` (`<PrivateGate`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Locked/unlocked badge, unlock/expiry/lock and PIN-change entrypoint.

## How to get to it (user POV)

Synthetic app header → private-unlock-open; inspect locked views before any supplied synthetic PIN.

Real prerequisites: Frozen private rows, server session/expiry and an already approved synthetic PIN; changing real auth/PIN remains out of scope.

## Driving it with H14 isolated browser/CLI

private-badge, private-unlock-open, private-pin-input, private-lock-now.

Observable oracle: Private rows absent when locked; authorized unlock/expiry/lock updates visibility and cache/dialog state consistently.

## Gotchas

Screenshots cannot expose real account identifiers; no settings/security boundary changes. Initial smoke does not exercise unlock.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
