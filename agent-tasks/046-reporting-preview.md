# Task 046 — reporting preview and interface polish

Status: IMPLEMENTED — local acceptance and independent review passed; delivery tracked in PR #211 (2026-09-07).

Authority: Owner requested note-reflection color, calendar scrollbar containment,
report-month label spacing, absolute calendar-month reporting with 1/3/6/12-month
views, and visual per-tracker recording rhythm. Owner subsequently clarified that
visual examples are suggestions, skills should inform the design, and items 4–5
require a quick draft and Owner approval before implementation.

Owner approval: "Mình duyệt"; exception: reflection styling must differ from private
notes, T1 chooses the correction without another preview gate. Owner requests
implementation through merge and another release on main. T1 may implement,
delegate, review, create/merge the feature PR into develop, verify its automatic
deploy, then release-label develop into main and tag the next minor version.
One-shot reminders, offline backup/PIN and DoS are assigned to a separate chat and
are not implementation scope here. No auth, cryptography, scheduler, real-data,
infrastructure, migration or cost changes. No broad Git cleanup grant is inferred.

Design direction: horizontal monthly bars with exact values and an explicit
partial-current-month label; one consistent accent for selected/current month and
a distinct token for past months. Color identifies series rather than claiming
that more spending is good. Composition uses labeled bars. Rhythm uses a week
matrix with one row per tracker, direct counts and a legend, accessible day detail,
and an alternative focused monthly calendar for dense tracker collections.
No missed-dose/adherence inference from a missing record.

Additional Owner feedback (mobile screenshots, 2026-09-07): quick-capture titles
overflow and overlap the backdate icon; management headings/group metadata overlap
edit/delete actions. Included in this delivery. Use responsive minimum-width grid
tracks, separate capture/menu hit targets, wrapped titles and separated management
actions. Verify hostile names and actual hit-target geometry plus capture/backdate
regression; preserve capture ordering and private semantics.

Skills: ui-ux-pro-max, targeted chart/heatmap guidance under docs/ui-brief.md.
Preview approval accepts presentation and interactions, not API/runtime/device QA.
Post-approval implementation must test absolute period boundaries, capped current
month, privacy/archive/deletion filtering, empty/error/signed values and responsive
layout. Preserve A2–A4/F6 current-time semantics unless explicitly redesigned.

Baseline: fb294eb07b5954994268ea23af550cc070dc0714 (origin/develop observed 2026-09-07).
Worktree: worktrees/046-tracker-periods-polish. Parallel backend exploration was
stopped during draft-first review and resumed only after explicit Owner approval.

Acceptance: backend period/domain/HTTP tests (including guarded privacy RED/GREEN),
frontend unit/lint/build, real-app synthetic browser regression and responsive
visual evidence, independent frozen-target review of report meaning/privacy/UI,
all configured CI gates. Immediately before both merges recheck exact head/base,
diff and gates; use match-head CAS. Production acceptance: deploy success plus
one read-only /api/readyz check with exact commit and db=up; no real-data testing.
Physical iPhone remains explicitly NOT_RUN under qa-framework §2.1.

Physical iPhone/Safari and real-account acceptance: NOT_RUN. Production/release acceptance is recorded separately after the exact deployed commit is verified.

## Implementation acceptance — 2026-09-07

- Final code review target: 09f5fb454edb27fa2768512dce9eaf702229fadf,
  baseline fb294eb07b5954994268ea23af550cc070dc0714. Independent read-only review
  closed numeric HTTP parsing, midnight fixture and rhythm target-spacing findings;
  no remaining actionable P0/P1/P2 within the declared scope.
- Backend: 410 non-Postgres tests passed in the backend worker. Intended removal of
  the locked-private SQL predicate failed RED, restoration passed GREEN. This is
  query-contract evidence, not a substitute for database execution. Migration QA
  run 34137152374 passed all 199 Postgres tests on the previous PR head; exact final
  head CI remains a merge gate.
- Frontend: lint and 138 unit tests passed. Full synthetic Chromium regression:
  258 passed, 34 conditional skips at b6aaa58. The final spacing delta additionally
  passed six report tests with measured 8px gaps, minimum 24x44px secondary day
  targets, locally scrollable weekly matrix and reachable rightmost cells.
  Capture/backdate and management primary controls retain 44px targets.
- Real app builds ran through Playwright's configured build/preview command.
  Mobile viewport is Chromium 390x844 with touch; desktop is 1280x800. Management
  test intentionally fixes 390px under both projects, so it is mobile evidence.
- Eighteen synthetic screenshot/hash manifests are retained locally in
  output/task-046/screenshots. Final finance/rhythm captures use 09f5fb4; unchanged
  reflection/calendar/capture/management captures use b6aaa58. Both T1 and reviewer
  inspected evidence. Observed visuals: long names wrap and actions remain separate;
  reflection blue differs from the pink private edge; financial labels and daily
  counts are readable. DOM measurements are asserted in tests, not inferred from
  screenshots.
- Local raw receipts: output/task-046/full-browser.log,
  reporting-integration.log, capture-regression.log, rhythm-spacing-green.log;
  backend worker output/task-046-data/activity-private-sql-red.log,
  activity-private-sql-green.log, activity-private-full-non-pg-green.log.
- Preview source remains a local untracked artifact, excluded from the PR.
  No security/scheduler/migration changes or unrelated Git cleanup.
- Owner requested a 45-minute continuation heartbeat on 2026-09-07. Existing
  task heartbeat microsched-uiux-07-sep-0205 was updated and verified ACTIVE at
  45-minute intervals. Pause it after merge/deploy/main release complete.

Delivery checkpoint: PR https://github.com/NguyenHaiHung0510/microSched/pull/211.
Recheck final CI, exact head/base/diff and merge with CAS; verify develop deploy
and readyz commit/db; then main release-label PR and next minor annotated tag.
The local output/task-046/delivery-receipt.md records subsequent exact receipts.
