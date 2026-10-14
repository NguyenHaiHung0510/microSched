# Workspace Context / Preview / Run tabs

Source: `frontend/src/MimiContextRail.tsx:16` (`type RailTab`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Context domain summaries, Preview plan, Run state/context/usage, Mở đầy đủ navigation.

## How to get to it (user POV)

Workspace rail → Context / Preview / Run; choose Mở đầy đủ for synthetic task/note/calendar/tracker.

Real prerequisites: Synthetic domain rows and explicit private visibility; selected conversation with frozen preview/run if those panes are to be proven.

## Driving it with H14 isolated browser/CLI

mimi-context-rail buttons Context/Preview/Run, mimi-context-inspector; refs in proposal-confirmation and run-context.

Observable oracle: Context shows only available authorized fixture data; opening panes sends no data to model; empty run/preview explains state rather than claiming execution.

## Gotchas

Context UI reads are distinct from context-v1 provider injection. Provider/context flags stay false in initial namespace.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
