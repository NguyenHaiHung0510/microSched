# Task 046 — reporting preview and interface polish

Status: IMPLEMENTING — Owner approved preview and delivery through main release (2026-09-07).

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

Physical iPhone/Safari, real account and production acceptance: NOT_RUN.
