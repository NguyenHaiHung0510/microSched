# Task 082 — Notes usability batch

Status: IMPLEMENTED CANDIDATE; required QA/reviews pending. Owner resumed 03/10/2026 until08:00 Asia/Saigon. Prior notes merge/deploy authority remains after gates. Task017 is frozen and excluded.

## Outcome

- Checklist text click/select must neither toggle nor open details; 44CSSpx area around checkbox toggles exactly once, keyboard Space and focus preserved. Existing card whitespace/title opens details.
- Add/edit subnote supports multiline Vietnamese, wraps long words, Enter inserts newline. Explicit add/save persists item independently from parent-note save; failures retain input and show error. Parent save/cancel does not undo acknowledged subnote writes; audit this existing semantic independently.
- Finance composition positive bars represent share of all expense groups, never normalize largest group to100%; signed/zero semantics unchanged.
- Tracker rhythm opens week containing today's date in Asia/Ho_Chi_Minh for current month; historical months start week1, navigation works.
- Existing tracker rename with unchanged reminder must not require push registration. Actual reminder change retains existing push prerequisites/error handling. No multi-profile push-dedup redesign.
- Future-note reflection uses light golden token pair, readable contrast.

## Scope/non-goals

Frontend changes plus backend tracker-name persistence bug fix; no new dependency/schema/private boundary/outbox. Groups2–5 remain separate future batches (calendar, record explorer, income association, heatmap/day reminder/cost/background, logging reuse/spec). Push duplicate manual mute approved, no browser settings change claimed.

## Required evidence

Targeted regression: notes-checklist-045 six cases (mock transport, no backend claim); finance/rhythm/reminder unit regressions; lint/build/current CI. Preserve earlier RED and failures.
Real production Docker candidate full-app with synthetic disposable Postgres/context per docs/qa-framework2.1: checkbox text/Space/pending failure, multiline explicit save/edit/reload/cancel, rename/reminder preserved, currentVN-week navigation, finance share/zero/signed, golden and long content. Capture 390x844 and1280x695 screenshots, observe real innerWidth/height, no overflow/identity. No real OAuth/Chrome profiles/production data in disposable cell.
Two independent frozen reviews exact GPT6Luna/high and Gemini3.8Flash/high; include independent autosave audit. T1 reconciles findings and directly checks Git status/diff/head/base/CI. NOT_RUN is not PASS.
Production only after gates: CAS merge into develop, exact deploy/readyz commit+db=up, narrow read-only dedicated ChromeWorkPlace tab smoke; no production seed/fault. Physical iPhone remainsNOT_RUN separate per QA release exception. No DB upgrade needed.
At07:45 only checkpointable work,08:00 STOP new work and pause automation; don't waive gates to meet deadline.
