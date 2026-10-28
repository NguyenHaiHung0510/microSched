# Subscription management route

Source: `frontend/src/App.tsx:131` (`location.startsWith('/subscription')`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

List, create/edit, renewal/cancellation and price/expiry settings.

## How to get to it (user POV)

Synthetic login → /subscription; Back returns to app; use fixture-owned subscription only.

Real prerequisites: Known subscription dates, prices, auto-renew/private state; separate approved writes and frozen date clock.

## Driving it with H14 isolated browser/CLI

subscription-screen, subscription-card, subscription-dialog, subscription-renew-dialog.

Observable oracle: Correct status/renew summary follows frozen dates; cancellation/renewal only under authorized fixture oracle and durable receipt; Back remains usable.

## Gotchas

No purchase or external commitment. Browser permission/price settings must not be changed just to reach a smoke.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
