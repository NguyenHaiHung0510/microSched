# Tracker editors and records

Source: `frontend/src/App.tsx:198` (`currentTab === 'tracker'`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Tracker list/types, creation/edit, entry/records and deep link /trackers.

## How to get to it (user POV)

Synthetic login → Theo dõi or /trackers → fixture tracker → create/edit dialog.

Real prerequisites: Synthetic tracker type/schema/records; private gate state explicit; tracking-brief governs oracle.

## Driving it with H14 isolated browser/CLI

tracker-create, tracker-edit scoped by actual tracker-id, tracker-dialog; inspect TrackerScreen.tsx for record navigation.

Observable oracle: Chosen form has actual fixture values, validation and cancellation preserve records; approved writes match durable schema/data.

## Gotchas

Health/money/general types have different oracles. Source mapping is not records/heatmap QA.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
