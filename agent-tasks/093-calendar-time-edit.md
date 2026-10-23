# 093 — Giải thích khoảng giờ không hợp lệ trong form lịch

Scope approved by Owner326 under the continuing batch and activated by PM under Owner328;
PM selected the inline-error design under Owner322. Base: accepted develop
`6d6f0788d88094c6694144d1c54c20d5912b974d`. One writer, isolated093 resources.

## Observed problem and outcome

Independent before-repro on immutable919: valid same-day and cross-midnight edits both returned200,
with matching API/PostgreSQL timestamps. Equal start/end correctly returned422, kept the row and
editable draft, but showed only “API request failed with status 422”. The Owner's exact valid-edit
failure remains **NOT_REPRODUCED**; this task does not claim a backend valid-save fix.

Shared EventForm now rejects end <= start before HTTP, shows
“Thời gian kết thúc phải sau thời gian bắt đầu.” directly below the end field, associates the help
with that field and focuses it after invalid submit. Fields stay editable; correcting the interval
clears the message and saves the retained draft. Calendar list, month-day dialog and creation reuse
the form. There is no automatic time adjustment, schema/API/ownership/privacy change or redesign.

## Evidence and remaining gates

- New browser regression fails against baseline at the missing inline message, then passes4/4
  desktop/mobile list/day checks: invalid HTTP0, focus/aria, retained fields and corrected retry.
- Focused calendar/reminder backend18PASS + existing reminder freshness3PASS; calendar unit10PASS.
  Real API/PG assertions preserve aware datetimes, interval422 and unchanged rejected canonical rows.
- Real synthetic app author journey: creation, start-only/end-only/both list edits, cross-midnight
  day edit, invalid feedback/corrected retry in both entrypoints, all-day, direct API422 and reload.
  Own public source/event retained with manifest; cropped form screenshots self-reviewed.
- Author confidence is separate from independent093 QA, required CI, physical iPhone/Safari and
  production acceptance. Those layers remain pending/NOT_RUN at author handoff. No merge/deploy.

Local canonical receipt/freeze and resource handback live in the current grant's
`techlead/o8-093-dev328` report directory; see [calendar verification map](../.agents/skills/verify-microsched/features/calendar.md).
