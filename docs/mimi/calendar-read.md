# Mimi Calendar reads (Task 101)

Calendar reads return the same **saved STANDARD day membership** as Month/DayDetail under the same
source visibility. Consider both open and completed dated Tasks. A Task's `due_on` is a civil
deadline and `due_at` belongs to its Vietnam day. An annotation covers both endpoints. An event
occupies each Vietnam day intersecting `[starts_at, ends_at)`, including intermediate days; an
event ending exactly at 00:00 does not occupy the new day.

`calendar.read.v1` additionally returns computed `calendar_facts`: the
`Asia/Ho_Chi_Minh` timezone, `observed_today` from `data_as_of`, and `requested`
facts for exactly the requested civil dates (at most 31). Each fact contains
`date`, `iso_weekday` (Monday=1, Sunday=7) and `weekday_vi`. Chat and Voice use the
same typed result; for example, 2026-11-18 is Wednesday/ISO 3. These facts do not
claim saved records, full coverage or multi-day membership; `matched_dates`,
exclusive event ends and the existing source/version checks still govern reads.
Invalid cursor/unavailable results do not fabricate date facts. Inspection has
no requested date scope and does not invent a range of dates for a long event.

`MIMI_CALENDAR_READ_ENABLED` defaults to false. The text route offers these tools only on the
existing context-enabled Mimi tool loop when this flag is on. Use explicit opt-in on a synthetic
QA instance after checking its isolation. Existing text transport, Task tools, and provider
routing policy remain in place. Turning the flag off withdraws the tools without a schema change.
The production preset in `fly.toml` enables Calendar reads for the existing STANDARD text chat.
This release does not enable Voice or change conversation ownership. Roll back by setting
`MIMI_CALENDAR_READ_ENABLED=false` and deploying the reviewed configuration; encrypted chat
history and stored calendar data remain intact.

| Tool | Arguments | Evidence |
|---|---|---|
| `calendar.read.v1` | Exactly one of `{"date":"2040-09-01"}`, `{"dates":["2040-08-30","2040-09-02"]}`, or `{"from_date":"2040-08-30","through_date":"2040-09-02"}`. Optional `kinds` subset of `task,event,annotation`; optional `cursor`. Up to 31 unique requested days, using YYYY-MM-DD; the range is inclusive. | Up to 40 distinct records, each with `kind`, `id`, `matched_dates`, a version, and typed date fields. Event rows include the visible source ID, name, kind (manual/ICS or a legacy Excel source), and version. |
| `calendar.inspect.v1` | `{"kind":"event","id":"<row UUID>"}` or `{"kind":"annotation","id":"<row UUID>"}`. | One currently eligible record, or an indistinguishable unavailable result for missing or ineligible IDs. Event location/description and annotation note are detail-only. Use existing Task inspect/content tools for Tasks. |

Pages are ordered by kind (Task → Event → Annotation), then UUID. `has_more=true` and
`next_cursor` mean more matches remain after this page; use the returned cursor with the
same dates and kinds. These are live reads, not snapshots. `has_more=false` means only page/suffix
exhaustion. Every `continued=true` page has `coverage=partial`, including an empty final page:
records inserted or newly visible before the cursor can be skipped. Combining continuation
pages cannot establish a complete range total or full absence. `coverage=complete` is reserved
for an uncontinued, exhausted read of the requested STANDARD/visible scope as observed during
that read; it does not freeze later membership. Row/source-version rechecks validate only
emitted rows, not completeness. An invalid cursor yields no rows or absence evidence.
One page uses at most three bounded statements and transfers at most 41 projected rows.
Summary text/title/label/source name and detail location cap at 240 characters; detail note or
description caps at 2,000. `truncated_fields` identifies an omitted tail. Results remain
untrusted text and never grant permission or open a link.

PRIVATE Tasks and annotations are excluded before data is selected, independently of PIN state.
Hidden sources and soft-deleted Tasks are excluded before pagination. An explicit date list skips
gaps. Client outbox items do not exist in this server read. No Calendar read can ground a preview
in the same run or be used as Task selection or confirmation evidence. In-run provider dispatch
rechecks the visibility and version of returned rows. Raw Calendar tool pairs stay in encrypted
receipts; future turns and Resume read fresh Calendar data. Resume also drops a prior unfinished
terminal if its run had Calendar reads, including an empty, complete page.

All assistant prose from a run with an allowlisted Calendar `tool.read_result` is replaced by
a structural fresh-read marker in provider history, shared `working_context` projection
(even when working projection or Calendar tools are disabled), and deterministic/semantic
compaction inputs. Classification uses conversation/run identity and `payload.tool`, never
arbitrary receipt decryption. This includes inspect, empty reads and errors. User messages and
general assistant runs retain their normal history; original encrypted UI messages are unchanged.
Checkpoint source hashes still bind original messages, not replacement text, and frontiers retain
their original sequence meaning. New checkpoints record `calendar_history_policy=1`.
An older checkpoint covering a Calendar-derived assistant run without that provenance is refused
before egress with a visible reason to open a new conversation; encrypted chat/checkpoint data is
retained. No automatic migration, snapshot or destructive rewrite is performed.

For an authenticated STANDARD server caller, [calendar_reads.py](../../backend/app/agent/tools/calendar_reads.py)
exports `execute_calendar_read(db, request, settings=settings)` for a typed
`CalendarReadRequest` or `CalendarInspectRequest`, and
`execute_calendar_tool(db, name, arguments, settings=settings)` for allowlisted JSON dispatch.
The caller owns authentication, tool lease, per-turn budget/deadline, and safe provider projection.
The executor fixes STANDARD visibility; it accepts neither a browser session nor model-selected
authority. Voice can use this server seam without calling the text provider or a new HTTP endpoint.

The offline contracts are in [test_mimi_calendar.py](../../backend/tests/test_mimi_calendar.py).
PM/T3 disposable, migrated Postgres qualification uses
[test_mimi_calendar_pg.py](../../backend/tests/test_mimi_calendar_pg.py) and
[test_mimi_calendar_resume_pg.py](../../backend/tests/test_mimi_calendar_resume_pg.py).
The Month/DayDetail grouping and PG reader share the
[event fixture](../../backend/tests/fixtures/mimi_calendar_membership.json). The Resume test doubles
the transport; it does not contact a model. Local source and deterministic checks do not by
themselves qualify synthetic full-app or actual model behavior.

## Builder repair evidence — 2026-nov-15

- Final Calendar, PG parity/pagination, Resume with active filtered checkpoint, 24-case history
  matrix, compaction and shared projection regression: **83/83 PASS**, 6.88s pytest duration.
- Broader affected batch: **127 PASS / 129 attempted**; two extra SDK/LangGraph PG cases failed
  before service because their separate historical `21887/mimi086_qa` prerequisite was unset.
  This batch does not qualify that runner on the supplied database; its allowlist is unchanged.
- Additional current native-route/loop + Calendar history checks: **60/60 PASS**, 6.94s;
  counts overlap the other batches and must not be summed as unique cases.
- Three runtime guard-bypass witnesses independently produced the intended assertion failure
  (direct history, shared projection, compaction), followed by restored passing checks.
- Ruff on all candidate Python sources plus affected tests: PASS. `git diff --check`: PASS.
- Transport doubles only, zero external provider calls. This is builder evidence, not independent
  QA, live provider quality, Voice/UI/device/CI/production acceptance. No commit/push/deploy.

Consolidated receipt and reproducible commands:
[local repair report](C:/Users/os/.codex/visualizations/2026/11/15/01a1de02-a1e3-7ea0-8aee-0d32eb5b6518/mimi-calendar-repair/2026-nov-15/repair-report.md).
