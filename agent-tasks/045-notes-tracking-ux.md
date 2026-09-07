# 045 — Notes checklist, tracker reports and freshness

Status: IN PROGRESS. Owner delegated implementation in this task on 2026-09-07 after accepting Task043. T1 may implement, delegate, verify and deliver via the established PR into develop flow. Parallel Task044 homepage/profile work is out of scope and retained.

## Outcome

- Notes: separate unfinished/completed checklist items, reversible completed disclosure; checkbox and text plus modest buffer toggle, trailing whitespace does not toggle; retain detail access, keyboard and pending/error feedback.
- Trackers: compact, readable finance comparison and composition with exact amounts and period labels; inspect previous months through the existing month API. Improve recent entries and reduce repetition in reports without changing financial meaning.
- One header freshness indicator for the active polling tab (Tasks, Notes, Trackers), using its real query state. Loading, error, offline and stale must not claim live. Calendar and nonpolling routes excluded. No extra network polling.

## Boundaries and evidence

Existing shadcn components, warm CSS tokens, light Nunito. No dependency upgrades, migration, credential/privacy changes, real-data writes, Neon operations or cleanup. Synthetic isolated browser contexts only. Task044 owns homepage and GitHub profile; no changes there.

One writer per isolated worktree: T1 integration/global indicator/recent entries; delegated notes and dashboard lanes commit to separate branches. Skills ui-ux-pro-max and web-design-guidelines advise within ui-brief authority. Financial comparison remains same-period; historical month navigation provides full past months without inventing figures or adding queries per tick.

Validation: meaningful pure tests plus browser regressions for hit regions, disclosure, query status, finance labels/zero/error/long content, mobile390/desktop1280 geometry. Existing frontend unit/lint/build and applicable full browser gates, independent frozen review, required CI before guarded merge. Preserve raw output under output/task-045 and scoped browser output; screenshot hashes plus actual image taste observations. Real iPhone, real-account dogfooding and production-image local cell remain NOT_RUN unless separately executed. Deployment claim requires exact readyz commit/db state.
