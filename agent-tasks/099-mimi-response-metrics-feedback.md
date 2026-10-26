# 099 — Mimi response E2E and feedback capacity

Status: implementation candidate; HOLD for PM integration and independent QA.
Base: develop `1a2c739af5512f86e037ba4086b210fbc35c80d2`.
Scope: M1/M2, approved 2026-10-26. No migration, provider activation, shared
dependencies, global navigation or domain CRUD changes. Release belongs to PM.

## User behavior and measurement

Each response shows browser E2E beside the existing run cost. Conversation stats
show arithmetic min/average/max and measured/eligible successful response
segments, with missing, pending, failed, cancelled and unknown counts separately.
Cost remains per run and is never added again for a second message/segment.

Start is the accepted UI action before fetch: Send, explicit Resume, or a preview
decision. A canonical response must be committed to DOM and have a visible paint
opportunity. Browser `performance.now()` measures the whole interval, including
network, queue, tools, retries/backoff, compaction, persistence, optional billing
enrichment and rendering. Provider TTFT/duration and server run elapsed are
separate; neither substitutes for E2E. The measurement is client-observed, not
trusted billing, server authority, a physical display receipt or a benchmark.

Preview ends the initial response. Confirmation begins a separate segment and
excludes the human decision wait. Resume binds its successor to the original
run. Failed/cancelled/unknown segments may retain their own elapsed duration but
do not enter successful averages. Hidden/offscreen observations store no duration.
Closing/switching chat conservatively invalidates an unobserved visible interval.
Reload/history never reconstruct a monotonic start or remeasure an old response.

One bounded observational POST per response/phase is made after the render
boundary, outside the answer mutation. No per-token updates or additional
polling. ACK failure cannot fail an answer, restart a model or loop retries;
coverage remains missing until a durable receipt exists. A single post-ACK read
refreshes the existing cache. Existing authenticated/CSRF gates, conversation/run
membership, exact source binding, finite 0..86,400,000ms validation, conflicting
replay rejection and the existing append fence protect the receipt. Existing
`MimiEvent` JSONB stores version1; all-retained aggregation ignores the public
last-event window. No DDL or backfill of invented metrics.

## Feedback

Positive/negative detail and optional expected outcome each allow 8,000 Unicode
code points on Mimi and verified system notices. The comment envelope remains
10,000 including polarity/reasons; expected retains its separate 10,000 API
envelope. Encryption and causal evidence are unchanged; no new raw export.
Over-limit text stays editable, IME is not sliced, counters use code points,
submission waits until composition ends and text fits. Unknown-result retries
retain the original key/body/target; ACKs do not clear a newer draft. Drafts
remain memory-only, with existing target and conversation binding.

## Reproduce focused evidence

Run in the respective backend/frontend directory, using existing dependencies.
Do not read real `.env`, auth/profile stores or connect to a real database.

```text
python -B -m pytest -q -p no:cacheprovider tests/test_mimi_response_timing.py tests/test_mimi_p2_metrics.py tests/test_mimi_feedback_target_binding.py tests/test_mimi_billing_prices.py tests/test_mimi_billing_repair.py
python -B -m pytest -q -p no:cacheprovider tests/test_mimi_response_timing_pg.py tests/test_mimi_message_provenance_pg.py tests/test_mimi_p1_api.py
node node_modules/vitest/vitest.mjs run src/mimi-response-timing.test.ts src/MimiPositiveSupplement.test.tsx src/mimi-owner-feedback.test.ts src/MimiConversationMetrics.test.tsx src/MimiSystemNotice.test.tsx
npm run build
```

PG fixture requires a freshly bootstrapped disposable pgvector/Postgres18 with
existing migrations0020, using `scripts.prepare_ci_database` then Alembic upgrade.
Set only explicit synthetic local URLs in the test process; `pg_dsn` rejects
non-local databases. The new PG case creates its own conversations and removes
only those IDs. It verifies concurrent identical replay, source/target/owner
refusal, conflict, unique event sequences, old receipt beyond MAX_EVENTS,
2s/8s/missing →2/5/8 and2/3 coverage, unchangedUSD0.03 and encrypted8000/8000.

## Acceptance still separate

For integrated A2 use the PM-owned local helper supplied in the private handback
in a fresh Python process. It installs init-only local settings, never reads dotenv,
OS credential config or secret sources, uses microsched_app on the dedicated
099 DB, disables provider/context/notifications/cron, and exposes the ordinary
app routes/session/DB/SSE. No debug route or auth override is added. The fixed
public fixture encryption material is exclusively for disposable synthetic rows.
Its explicit `--candidate-root` / `--smoke` mode exercises the real backend wire
and database for greeting→plain answer, create request→preview, two timing POSTs
and reload. Its2s/8s values are fixtures, never measured performance.
It retains one owned conversation for handoff; IDs go to its sanitized output.
Browser integration uses loopback API18098 and Vite15198 proxying that API;
Mimi public origin is exactly http://127.0.0.1:15198. Existing
`/auth/dev-session` signs in the synthetic local fixture before UI navigation.
The separate source/build/config/fixture handback gives exact launch commands.
No fixture DB/key configuration is included in product source. Repository secret
scanning remains unchanged; the local helper is an independently hashed QA input.

PWA dependency delta: the existing Mimi feedback draft predicate now includes
expected-only text and pending negative intent. This preserves reload safety
after adding expected to the positive editor; no global routing/policy change.

Builder focused tests are not independent QA. PM freezes the integrated source,
build, configuration and synthetic fixtures before the independent batch.
Required browser cases: visible canonical paint vs first chunk; delayed tools,
retry and billing; preview→human wait→Confirm; reconnect vs Resume; cancellation
and failed/unknown outcomes; hidden/offscreen/closed panel/reload/legacy; metric
ACK failure; all-retained coverage beyond public windows; both actors/polarities
and both fields at7999/8000/8001 with emoji, Vietnamese IME, paste/middle edits,
unknown-save retry and stale ACK. No real provider is needed for lifecycle cases.
Full-app visual/physical iPhone/live provider/CI/production evidence is NOT_RUN
by this builder lane until separately observed. No push/PR/merge in this lane.

Builder checks observed2026-10-26 Asia/Saigon:103/103 backend focused tests
(84unit/regression +19PostgreSQL),105/105 frontend Mimi/PWA tests across22files,
targeted Ruff/ESLint, TypeScript/build, apple-icon and PWA surface guards PASS.
Numeric guard mutation produced the intended bool/string rejection failures;
restoration passed6/6. Fresh-process actual FastAPI/session/SSE/DB wire smoke
passed plain/preview/timing POST/reload with0provider calls. Full browser paint,
IME and independent/device/CI/production acceptance remain NOT_RUN.

## Integrated durable ACK correction — 2026-10-27

The independent review found request-yield commit could follow a201ACK. The
integrated candidate opts in exactly six handlers to commit before returning:
Mimi timing/feedback, Note move-to-top, History handled/prepare/commit. Failure
rolls back and returns sanitized503commit_unknown; a commit may already have
succeeded, so no “not saved” claim or automatic model retry is made. Global
get_session, auth, permissions, cron and unrelatedCRUD are unchanged.

Actual route/wire proof:18intendedRED →18GREEN; actualPostgreSQL commit failure
before/after the durable effect and same-key/body replay covered both MimiPOSTs.
Affected backend batch52PASS,14deselected; full frontend329PASS/57files; production
build plus Apple-icon/PWA static guardsPASS. Clients keep original feedback
intent; NoteTop captures its snapshot in mutation variables and exposes exact
replay after uncertainty. Existing History identity/filter/selection remains.
These builder checks are distinct from PM's independent integrated15journeyQA,
physical device/live provider/CI/production gates, all still NOT_RUN here.
