# 094 — Chuyển ngày Task và dấu ngày trên lịch

Owner-approved O4; PM conditional R4 activation after the093 candidate handback. Sole T1 writer on
`feat/094-calendar-move`, isolated094 resources. Base fast-forwarded without discarding WIP to accepted
develop `3119906c5bdc16d7a1c2e663fc352841c6aafd21`, preserving093 EventForm interval feedback.

Existing desktop Task drag flattened datetime Tasks to date-only values and its undo retained only
the prior date. Task/annotation movement now shares one online action with visible day-detail
**Chuyển ngày** controls for touch/keyboard. Datetime moves preserve Vietnam clock and precision;
date-only stays date-only. Annotation ranges move relative to the grabbed day and keep their length.
Undo restores the entire previous schedule. Calendar-source sessions stay outside movement.

Task writes retain the existing typed outbox/order barrier. A pending projection is distinguished
from canonical acknowledgement; uncertain commands are preserved. Annotation failures restore the
projection, keep the date draft and allow a corrected retry. Offline/unverified/private-locked new
actions are refused; cross-page private lock clears the move dialog. No schema/backend/auth-policy
change, full-offline promise or automatic time adjustment is introduced.

## Author evidence and remaining gates

- Temporal/admission/order/ACK tests and the complete frontend unit suite; TypeScript, lint and build.
  Existing unrelated NoteChecklist dependency warning is qualified in the author handback.
- Affected browser regressions cover shared Task/annotation actions, desktop drag, cancellation,
  invalid input, rejected write/retry and full-schedule undo on desktop/mobile viewports.
- Actual synthetic app + own-ID PostgreSQL/API receipts cover Task date/datetime and undo,
  relative/absolute reminders, middle-grab range across month, single-day annotation and undo,
  native touch, honest pending before ACK, injected own422 rollback/draft/retry and private guard.
  Earlier interrupted/failed driver attempts remain preserved with their effects receipts.
- Public screenshots are indexed in the current granted `techlead/r4-094-dev328` report; private
  mode has no pixels/raw payload output. Fixtures are additive and retained with manifest.

These observations establish author confidence only. Independent094 QA, required exact-head CI,
physical iPhone/Safari and production remain pending at handoff. Parent owns acceptance/release;
the writer stops at clean commit, normal push, draft PR, full freeze and consolidated handback/HOLD.
See the [calendar verification recipe](../.agents/skills/verify-microsched/features/calendar.md).
