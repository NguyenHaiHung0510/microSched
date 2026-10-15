# Model/effort configuration entrypoints

Source: `frontend/src/MimiConfiguration.tsx:145` (`mimi-route-settings`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Quick model chip, workspace hub, profile/details and next-run notice.

## How to get to it (user POV)

Selected synthetic conversation → mimi-route-settings or workspace mimi-configuration-hub-toggle; side-chat menu Cấu hình Mimi.

Real prerequisites: Capabilities/configuration fixture and exact candidate model settings; config writes/provider-pool network not authorized by first metadata proof.

## Driving it with H14 isolated browser/CLI

mimi-route-settings, mimi-profile-details, mimi-next-run-notice; read-only opening in separately frozen fixture.

Observable oracle: Displayed requested model/effort and supported capability are accurate; active run remains fixed and changes apply only to next run under a separate grant.

## Gotchas

Harness T1 model is not Mimi app configuration authority. No credential/auth/provider changes or live pool refresh.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
