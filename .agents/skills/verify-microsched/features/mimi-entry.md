# Mimi workspace and dock entrypoints

Source: `frontend/src/App.tsx:137` (`<MimiDock`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Mimi tab if available, dock open/close and workspace conversation surface.

## How to get to it (user POV)

Synthetic login with mimi_available → Mimi tab or mimi-dock-toggle from another tab.

Real prerequisites: Feature flags/candidate differ between aa9d7251 and exact Mimi680b7f9b; use Mimi map with its binding for expanded controls.

## Driving it with H14 isolated browser/CLI

role tab Mimi, mimi-dock-toggle, mimi-side-chat; follow separate verify-mimi map.

Observable oracle: Available surface opens, shared selected conversation and domain navigation stay consistent; disabled capability is reported accurately.

## Gotchas

aa9d7251 UI is older than Mimi QA snapshot. Do not imply later Mimi controls exist on the main QA candidate.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
