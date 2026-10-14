# Technical detail dialog

Source: `frontend/src/MimiScreen.tsx:1121` (`mimi-technical-dialog`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Technical menu/dialog, source/context/provider/run evidence and close focus.

## How to get to it (user POV)

Side-chat menu → Chi tiết kỹ thuật; workspace chat uses its actual technical trigger.

Real prerequisites: Synthetic selected conversation; optional frozen run/provider receipts for deeper panes.

## Driving it with H14 isolated browser/CLI

mimi-technical-dialog; Tùy chọn side-chat; inspect source-provided details and onTechnicalCloseFocus.

Observable oracle: Dialog opens correct selected run/conversation, states unknown honestly, and restores trigger focus on close.

## Gotchas

No secret/provider headers/runtime credentials in receipts; run evidence stays NOT_RUN without a fixture.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
