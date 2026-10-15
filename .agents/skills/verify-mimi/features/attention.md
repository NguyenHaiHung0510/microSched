# Mimi attention and device notifications

Source: `frontend/src/MimiNotifications.tsx:33` (`mimi-attention`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

In-app attention, read/open locator, expiry, device preference and permission-mediated push.

## How to get to it (user POV)

Workspace notification surface or /mimi?attention=ACTUAL_SYNTHETIC_LOCATOR → correct thread.

Real prerequisites: notifications flag, synthetic locator ownership/expiry/device proof and explicit permission-action grant; flag false and service workers blocked in initial namespace.

## Driving it with H14 isolated browser/CLI

mimi-attention; App.tsx attention route; buttons Đọc lại trạng thái; no enable gesture in initial recipe.

Observable oracle: Owned locator opens correct conversation; expired locator truthfully labels status; read/preference version checks follow frozen fixture.

## Gotchas

No automatic browser permission request, real push device or new scope. Attention binding ≠ notification delivery.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
