# 098 — Note reader, checklist ordering, History position and Task title

Status: implementation complete; author verification recorded below. HOLD for PM integration, independent review and QA under the approved night batch.
Scope: N1–N3, H1, T1 only. Reader B; icon-only item actions; atomic completion-group move-to-top with snapshot CAS; 6/4/3×4 preview; nonpurge History ACK; wrapped single-line Task title.

Base: 1a2c739af5512f86e037ba4086b210fbc35c80d2. No DDL, provider calls, production data or Mimi changes. Independent QA, integration and release remain PM-owned. No push/PR/merge in this lane.

## Behavior

- Preview: body6 lines, first reflection4, first3 unfinished items×4 lines each. Disclosed completed items remain clamped in preview. Full collapse resets disclosure state; stored strings stay intact.
- Reader B reuses the existing detail lifecycle as a full-region surface, with safe-area header/back/edit, body → checklist → reflections and section navigation. Closing restores the actual opener's viewport offset and filter context, including changed preview height.
- Item toolbar: Pencil, ArrowUpToLine, Trash only. Top is disabled for the first item of each completion group. One POST compares the full content-free checklist snapshot under the parent lock, permutes only that group's slots and commits all ranks together. Exact unchanged postcondition replay is a no-op; stale membership/completion/ranks are409 without writes. No DDL or new pin mode.
- History ACK patches only an existing scoped cache using the server timestamp, preserving pages, row DOM/disclosure and current/next/previous anchors through background refetch. Focus waits for pending completion; old refetch settlement cannot clear a newer anchor. Filter changes and private/auth purge discard anchors; private pages/selection/confirmation still purge.
- Shared Task title wraps/autogrows with a measured-height fallback. Enter respects the enabled submit button and IME; CR/LF handling matches the previous text Input. Unedited legacy values and body text are preserved.

## Author verification — 2026-10-26, Asia/Saigon

- Focused pure + PostgreSQL Note/API tests:19/19 PASS, including concurrent winner/conflict, rollback, exact replay, stale append/delete/rank/completion and inaccessible parents.
- CAS refusal guard: intended bypass FAIL → exact source restored → PASS.
- Frontend unit:318/318 PASS across54 files; production build and scoped ESLint/Ruff checks PASS.
- Consolidated production-build Chromium UI:32/32 PASS, desktop1280×800 and mobile390×844. Covers097 density/confirmations,045 checklist regressions and098 reader/ordering/History/title.
- History baseline was reproduced before the fix: ACK at occurrence81 lost its loaded row/pages. All failed traces are retained separately from final passing evidence.
- Reader oracle uses the pointerdown origin after Playwright scrolling. Mobile pre-click800px was obstructed by the96px tab area; trace records interception and actual704px click, then704px return. Desktop738px →738px. Assertion remains same visible opener/anchor within5px, with a deliberate preview-height change.
- WebKit binary absent: NOT_RUN. Forced field-sizing fallback passed in Chromium. Physical iPhone, independent review/QA, full CI and production remain NOT_RUN in this lane.

The local handback supplies exact commit/build/config/fixtures and all author receipts. Existing required CI and PM acceptance are retained; no push/PR/merge or cleanup is authorized by this task's author verification.

Final shared-create smoke additionally found a textarea-label ambiguity: the wrapping label included title value text, so a title containing “giờ” matched the time label. The title now has an explicit useId/htmlFor association. Original unchanged create smoke and affected title/calendar cases:6/6 PASS; final consolidated browser32/32 PASS again. All failure receipts remain retained.

## PM grouped review correction — 2026-10-27, Asia/Saigon

Independent integrated review found that an ambiguous bulk-commit ACK could be dismissed and lose its original snapshot ID. While that commit is pending or explicitly unknown, the confirmation stays open, its cancel/close controls cannot discard the batch, and retry sends the same prepared ID. Auth/private-scope purge still clears it. The intended enabled-cancel failure was reproduced before the guard; the corrected same-ID retry, Escape/outside dismissal and visibility purge passed on desktop and mobile.

CI feedback assertions now follow the existing uncertain-save message and explicit original-intent retry button; the three-attempt identity/target/body checks remain. Both formerly failing viewport journeys passed locally. A Calendar test now counts only open_picker requests, checks its actual first-page limit and exact next cursor, and verifies retained/appended rows; unrelated grid/overdue refreshes no longer pollute the counter. No Calendar product code changed. Picker and adjacent undated case passed twice on mobile. Fresh independent delta/UI QA and final CI remain PM-owned.

## PM consolidated UI correction — 2026-10-27, Asia/Saigon

The frozen888 full-app synthetic batch was operated by PM in visible IAB after subagent IAB surfaces proved unavailable. Independent Luna receipt review graded the same15journeys:5accepted,5partial,4failed,1NOT_RUN;14were operated and the actor distinction is retained. Scoped PostgreSQL readback verified the four8000+8000 feedback supplements, exact Note/Task values and three handled occurrences. Device/nativeIME/PWA-update and unavailable live faults remain qualified.

The accepted UI failures shared intrinsic min-content sizing: long Task titles and unbroken feedback text widened an auto-sized Dialog grid. DialogContent now uses one minmax(0,1fr) track, shrinkable children and anywhere wrapping; inputs retain full values and the existing close/focus lifecycle. No new height cap or visual redesign was introduced.

History bulk commit captures its original batch ID and scope gate. After dispatch, transport timeout/network/server-ACK loss or invalid ACK stays explicitly uncertain and cannot discard the original snapshot; an offline retry preserves that prior uncertainty. Pre-send refusals stay distinct. Matching ACK and scope purge retain their existing semantics; no automatic retry or global API/auth/transaction change was added. A fresh bulk dialog resets prior commit state and renders only its own error, keeping the outside History message and scroll context.

Four intended regressions reproduced before correction, then12targeted browser cases passed on both viewports. A self-review offline-after-lost-ACK regression was also reproduced, corrected and the6affected transport cases passed, including the actual20-second timeout path. These counts overlap; they are not18uniquecases. Full frontend329tests/57files and ESLint passed. The browser web-server build passed TypeScript/Vite and existing Apple/PWA guards. Fresh final CI, independent delta and affected full-app preview/release remain PM-owned.
