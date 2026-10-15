# Reminder confirmation deep link

Source: `frontend/src/App.tsx:131` (`location.startsWith('/reminder-confirm')`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

dispatch lookup, stale/error/retry, private unlock and confirmation.

## How to get to it (user POV)

Synthetic same-origin /reminder-confirm?dispatch=ACTUAL_FIXTURE_DISPATCH.

Real prerequisites: Fixture dispatch belongs to synthetic role; freeze pending/expired/private states and confirmation delta; private PIN setup already authorized.

## Driving it with H14 isolated browser/CLI

ReminderConfirmScreen.tsx; reminder-confirm-retry and private-unlock-submit where actual state exposes them.

Observable oracle: Correct dispatch target/state displayed; no premature write; separately approved confirmation is idempotent and reflected durably.

## Gotchas

Dispatch tokens stay private. Do not generate production notification, traverse OAuth or alter real PIN.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
