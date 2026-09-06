# Task 043 — UI/UX readability

Status: VALIDATING, 2026-09-06. Owner delegated autonomous T1 delivery in current task, then explicitly allowed starting immediately and requested UI/UX harness skills and Gemini 3.8 delegation. Grant ends on completion; Owner-only boundaries remain. Source: current Codex task 01a0773f-7cc9-7d93-8d2f-25a6c8e55041.

## Outcome and decisions

Improve six observed daily-use problems: logo returns to default Task view; distinguish private objects while unlocked; readable laptop month calendar; useful optional phone month view; tracker upcoming reminders with actual next date/time under existing recurrence semantics; coherent Task day grouping without stacked empty cards. Keep established tokens, Nunito, light theme, domain behavior, data gates and calendar list/detail paths. No migration, new scheduler/polling, auth/privacy boundary changes or production data QA.

Owner has delegated routine design decisions while sleeping. Use full application synthetic browser preview and regression tests; preview is not Owner aesthetic approval nor physical iPhone acceptance.

## Execution

Base: origin/develop ac35b75db73a0c4e78aebea536bc7a026f594a98. T1 integration worktree: worktrees/043-ui-ux-readability on feat/043-ui-ux-readability. Gemini UI worktree: worktrees/043-ui-calendar-task on feat/043-ui-calendar-task. One writer per worktree; Gemini scope calendar/Task/logo only, T1 scope reminder and shared private presentation until integration. No cleanup grant. Preserve unrelated worktrees/untracked files.

Read AGENTS.md, docs/harness-policy.md, project-guide.md, ui-brief.md, qa-framework.md and applicable domain specs. Skills: ui-ux-pro-max and web-design-guidelines; latter fetched 2026-09-06. Verified UX search: essential text truncation requires wrap/stack or a visible full-detail path, not ellipsis-only meaning.

## Acceptance and evidence

Each fixed behavior has a data-testid based Playwright regression. Test 390x844 and 1280x800, extra wide calendar and small phone where helpful. Include long Vietnamese/unbroken titles, mixed standard/private, dense lists, empty/error/loading, reminder recurrence/date boundaries. New safety guards require intended RED then GREEN. Preserve current frontend/backend CI and required checks; select independent frozen-target review for recurrence correctness/private regressions and UI accessibility. Use synthetic fixtures only. Local/committed/CI/production/device are separate verdicts; physical iPhone NOT_RUN. No Neon access or assumed Docker daemon. Local build/API-mocked full app QA is distinct from disposable production-image cell.

## Resume

Heartbeat id microsched-uiux-07-sep-0205, displayed name microSched UIUX - overnight recovery. Configured every 20 minutes until 2026-09-07 12:00 Asia/Ho_Chi_Minh, plus 02:05 and 02:15 wake dates. Inspect actual worktree/process/worker state before resuming. Stop this heartbeat on completion or exclusive Owner blocker after independent work is exhausted. Raw working receipts and worker handoffs live in frontend/test-results/task-043 (ignored); final dated receipt belongs beside this contract before PR. Never publish attached personal screenshots or their payloads.

## Checkpoint 2026-09-06 22:36 VN

Backend worker handed off 016bf36; T1 inspected recurrence extraction/query scope and cherry-picked as c8841c3. Worker observed 394 non-PG PASS + Ruff; independent frozen backend review in progress. T1 reminder/private frontend initial unit 116 PASS/build PASS; focused Playwright 6/6 PASS at 390x844 and 1280x800. Full suite/integrated calendar still NOT_RUN. Gemini 3.8 Flash/high CLI remains active in separate worktree on calendar/Task/logo.

Output lesson: first Playwright invocation without --output tried cleaning the default test-results root and stalled on open worker log files, removing earlier generated unit/build logs and prompt files. T1 stopped only the verified task test process 28308, then reran with a nested browser output path; 6/6 PASS. No user/repo source/data deleted. All future runs MUST use --output=frontend/test-results/task-043/<run> from root (or equivalent relative path from frontend). Durable receipts now at root output/task-043 (gitignored), outside Playwright cleanup; source contract stays here. Earlier unit/build counts observed in tool output need renewed final raw receipts after integration. Worker CLI event/stderr still open under frontend/test-results/task-043; do not delete/move these while worker runs.

### Independent backend review 2026-09-06

Reviewer /root/review_projection reviewed frozen worker 016bf36ea8522e85e641d73c2f9fba17131bb1eb versus ac35b75, independently compared AST of all three extracted helpers and executed a stdlib synthetic +5-day calculation. Verdict PASS on recurrence parity, readable/deleted scope, bounded query count, compatibility and null/error behavior; no required finding. It inspected final worker raw 394 PASS and intended RED failures but did not rerun the whole suite. PG/query performance/HTTP runtime remain NOT_RUN in this lane. T1 subsequently committed the worker files and integrated as c8841c3; the worker's older 'commit blocked' note is historical.

### UI integration 2026-09-06 22:50 VN

Gemini first UI commit 6ec6c44 integrated as 8b6157e. T1 found incomplete agenda month/error/draft handling and delegated a bounded CalendarScrollView-only follow-up, current exec session 31057, logs output/task-043/gemini-agenda-events.jsonl. T1 owns candidate edits to logo/layout, Task empty-date row grouping, shared private markers and calendar day details. Initial integrated focused suite: 19 PASS, 1 desktop-only skip, 2 failures caused by the new test selecting all groups containing the reschedule word 'Hôm nay'. Replaced ambiguous text selector with task-today-label; rerun pending. Added further private Task/calendar regression cases after that run. Final full suite and screenshots still pending.

### Integrated review checkpoint 2026-09-06 23:30 VN

Gemini follow-up 4e9f415 integrated as b1a272b; both workers finished. T1 completed shared presentation, semantic logo navigation, mobile tabs, calendar focus/targets, loading/errors and measured sticky-header centering. Frozen candidate f97c6b9: frontend lint and 116 unit tests PASS, backend Ruff and 394 non-PG tests PASS (197 PG cases deselected), repository hooks PASS. Full synthetic browser suite: 213 PASS, 29 pre-existing/conditional skips, 4 FAIL caused by the new display test ID colliding with the existing tracker editor. Raw receipts: output/task-043/e2e-full.log and associated scoped traces. No required gate was dropped.

Independent read-only UI reviewer /root/review_ui inspected the frozen source and verified all 19 screenshot MD5/SHA256 against f97c6b9. Two P2 findings: grid-to-agenda retained a large scroll offset and hid the picker; new agenda task toggle lacked pending/error feedback. T1 accepted both plus the test-ID collision. New regression tests failed for intended causes (scrollTop 183 versus 0; checkbox enabled during pending request), raw output/task-043/review-red.log. Corrections reset agenda scroll after mount, preserve the grid position, disable duplicate toggles with visible pending/error/retry guidance, and rename only the reminder display test ID. Physical device, production-image local QA, production data QA remain NOT_RUN; no Neon or real-profile operations.
