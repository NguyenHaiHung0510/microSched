# Session, error and logout shell

Source: `frontend/src/App.tsx:44` (`fetchSession`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Checking/guest/error states, retry, allowlisted login link and logout.

## How to get to it (user POV)

Fresh guest /home; synthetic /auth/dev-session only on task runtime; authenticated header → Đăng xuất.

Real prerequisites: Synthetic local auth enabled by Main setup only; no real account/profile, OAuth or new consent scope.

## Driving it with H14 isolated browser/CLI

App.tsx fetchSession; app logo; button Đăng xuất; public login link inspect-only.

Observable oracle: No protected data during guest/error; session failure stays explicit; logout removes authenticated shell and selected Mimi conversation.

## Gotchas

Never record session response email/cookie. Source-mapped error cases require a separate frozen fault scenario.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
