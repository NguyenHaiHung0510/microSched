# Mimi side-chat, progress, feedback and telemetry review

Date: 2026-09-26
Scope: read-only inspection of `worktrees/065-mimi-p1c-context-loop` plus current primary UX, browser-performance, accessibility and observability sources. This report makes recommendations only; it does not authorize implementation, provider egress, a telemetry service, deployment or merge.

## Executive assessment

Mimi already has a strong app-owned evidence base: durable run states, sequenced events, provider-call route and reported-usage receipts, execution receipts, and reconnect/replay. The dock has an active spinner, stage text, elapsed time, cancellation, and recovery actions. The workspace expands route/context/usage details. These are product-specific foundations worth retaining.

Three issues keep the current UX from being fully trustworthy for Owner dogfood:

1. The dock labels a synthetic `run.reserved` stream event “Đã nhận yêu cầu” before the durable run acceptance event is observed.
2. It looks animated, but final answer text is buffered and only delivered after the provider response reaches a terminal classification. One idle heartbeat is mapped to “Đang khởi tạo run,” which can contradict the last known stage.
3. Visible feedback is available only after a Task receipt, although the data model supports feedback for turns, runs and calls. Wrong answers and errors have no nearby report affordance.

Recommendation: improve the current native interaction and ledger loop first. Measure browser acknowledgment separately from provider time; keep truthful stage progress and elapsed time, never invent an ETA or completion percentage, and capture privacy-safe, structured feedback against the correct turn/run/call. OpenTelemetry can be a later export format. Langfuse or Phoenix would add another store and operational/privacy boundary without currently filling a demonstrated gap.

## Evidence inspected

Local code and project artifacts were read from:

- `backend/app/agent/models.py:137-237,269-378` — run, event, provider-call, execution-receipt and feedback record shapes.
- `backend/app/agent/service.py:943-1107,1424-1449,1571-1615,2371-2520,2524-2565` — admission, event creation, bounded reads, conversation serialization, usage and event replay.
- `backend/app/agent/openrouter.py:487-647` — provider streaming, first-output timing, buffering and adapter timing receipt.
- `backend/app/web/routers/mimi.py:89-134,248-350,392-453` — SSE reservation, 750ms event polling, heartbeat and run observation/resume.
- `frontend/src/MimiScreen.tsx:57-69,166-186,219-247,293-368,315-351,437-495,497-517,546-647` — elapsed timer, stage mapping, send/reconnect, status UI, errors, receipt feedback and dock event disclosure.
- `frontend/src/mimi-api.ts:13-95,261-324,376-390` — browser run/event/call types, SSE consumption and receipt-only feedback submission.
- `frontend/src/MimiContextRail.tsx:66-95` — workspace run/context/route/usage inspector.
- `docs/qa-specs/qa-mimi-p1-live-dogfood.md:196-226` and `agent-tasks/2026-09-22-research-mimi-context/24-p1ca-implementation-status.md:118-184` — current acceptance boundaries and recorded local evidence.

The status ledger reports local offline suites and a deterministic fake-provider browser lane as passing, while live Chrome/route acceptance and Owner dogfood remain NOT RUN; transaction-pooler behavior on Neon remains UNVERIFIED. Those distinctions are retained here. This review does not re-run tests or claim current CI/runtime/production acceptance.

## Observed behavior

### Side-chat and workspace

`MimiScreen` is shared across `dock` and `workspace` variants. The compact dock projects current conversation state, status, elapsed time, cancel/recovery controls, previews and receipts. It also has a collapsed “Chi tiết kỹ thuật” disclosure that lists event-kind names, which is not yet a user-oriented progress timeline. The workspace context rail is already the richer disclosure surface: it shows run state/start/deadline, then expands route, requested/effective model and provider, context byte upper bound/limit, checkpoint frontier, provider-reported token/cache/cost, and source coverage/omissions.

### Acknowledgment and progress

`send.onMutate` immediately renders “Đang gửi yêu cầu,” which is a useful local acknowledgment. The SSE generator then emits `run.reserved` before polling persisted state; the UI maps it to “Đã nhận yêu cầu.” The service persists `run.accepted` separately. Thus the UI can currently imply server acceptance before that durable event is observed. The event stream polls the ledger at 750ms intervals; it emits a heartbeat after 15 seconds without a new event.

The provider adapter records the first received content chunk internally, but retains text until terminal classification so early prose is not shown if the provider ultimately returns a tool call. It then invokes the assistant-delta callback over buffered pieces. Consequently, the dock’s activity animation and stage transitions are useful, but visible assistant text is not true token-by-token streaming. The UI maps heartbeat to “Đang khởi tạo run,” even if a known stage had already been reached. The provider timing receipt already contains duration, connect time and TTFT (`usage.mimi_timing`); UI-visible answer delivery time would be a different measurement.

Elapsed time is shown without a fabricated ETA. On the sending component it starts from local click time; after reattachment it falls back to persisted `run.created_at`. The active status container is `role="status" aria-atomic="true"` while the elapsed label changes every second; that could repeatedly announce the timer to assistive technology and should be checked.

### Feedback and persisted evidence

Feedback rows allow target types `turn`, `run`, `call`, `operation`, and `receipt`, with encrypted comment and optional expected-result text, evidence IDs, an idempotency client ID, unresolved state and workflow state. But the only current UI form is rendered under the latest execution receipt, and `saveMimiFeedback` hardcodes `target_type: 'receipt'`. There is no inline “wrong answer” or error-report action.

The native records already let Mimi correlate runs, event sequences, provider calls, usage and domain-write receipts. Provider usage is selectively exposed only when reported; cache/cost absence is not treated as zero. The ContextRail is a suitable detail view for route/timing/context provenance. Avoid confusing its synthetic Control Center usage preview with real usage; it is explicitly labeled `SYNTHETIC`.

## Current primary references and limits

1. **NN/g, “Less Chat, More Answer,” 2026-04-17.** In a usability study, 9 participants with different digital/AI literacy used 8 site-specific chatbots, 2–3 per participant, on realistic tasks. Participants approached chat like search, typed short or imperfect requests, wanted direct/scannable answers, and benefited from essential answer first with detail on demand. This supports a concise side-chat and progressive workspace disclosure. Limits: small sample, site-specific bots, task sessions rather than longitudinal productivity-assistant use; it does not supply a response-latency threshold for Mimi. [Source](https://www.nngroup.com/articles/less-chat-more-answer/)

2. **Chrome/web.dev, INP article updated 2025-09-02.** INP measures interaction start to next paint across click/tap/keyboard input; the metric is about browser responsiveness, not eventual network/model completion. The current field “good” threshold is at or below 200ms at the page-view 75th percentile. This is a useful independent responsiveness reference, not a promise that a full request/model call completes within that time. [Source](https://web.dev/articles/inp)

3. **Microsoft Fluent 2 Wait UX.** Recommends immediate AI-chat response feedback, accurate descriptive labels, no confusing loader flash for waits under one second, spinner for short indeterminate waits, and content/status messaging for longer waits when progress cannot be measured. Use this to favor local echo/status immediately and restrained motion; do not represent unknown work with a determinate bar. [Source](https://fluent2.microsoft.design/wait-ux)

4. **Carbon Design System progress-bar guidance.** Determinate percentage is for measurable progress against a known goal; indeterminate progress represents active work with unknown completion. Carbon advises short labels and helper text that do not imply a quantitative estimate when none exists. [Source](https://carbondesignsystem.com/components/progress-bar/usage/)

5. **W3C WAI, WCAG 4.1.3 Status Messages.** Dynamic status should be exposed programmatically without moving focus. Mimi’s role/status usage needs a screen-reader check, particularly the atomic region containing a per-second timer. [Source](https://www.w3.org/WAI/WCAG21/Understanding/status-messages)

6. **OpenTelemetry GenAI semantic conventions.** The GenAI convention repository documents operation duration and other client/workflow/agent/tool metrics, but labels the metric document `Status: Development`; the convention surface is actively evolving. It is useful as an interoperability mapping, not as Mimi’s correctness or recovery ledger. [Metric conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md), [repository](https://github.com/open-telemetry/semantic-conventions-genai).

7. **Langfuse self-hosting and retention.** Current architecture calls for web and worker containers plus PostgreSQL, Redis/Valkey, ClickHouse and blob storage; documented minimum sizing is 4 GiB each for web and worker, before the data services. Self-hosted data is kept indefinitely unless retention is configured; retention feature details vary by edition. This substantially exceeds the app’s 512 MB Fly Machine footprint and adds separate data governance/retention operations. [Self-host overview](https://langfuse.com/self-hosting), [sizing](https://langfuse.com/self-hosting/configuration/scaling), [retention](https://langfuse.com/docs/administration/data-retention).

8. **Arize Phoenix self-hosting.** Official docs describe SQLite as the default storage and PostgreSQL as an option for production. Phoenix could support an isolated local trace-view experiment, but remains an additional trace store and access/retention boundary. The cited page does not define a minimum memory footprint, so no claim is made that Phoenix itself cannot fit in 512 MB. [Source](https://arize.com/docs/phoenix/self-hosting/deploying-phoenix).

## Inferences and recommendations

### Surface behavior

Keep the side-chat short: preserve the user’s message immediately, show “Đang gửi…” as a local state, then change to “Đã nhận” only after durable acceptance is known. During work, show one truthful current stage, elapsed time and only the action relevant to that stage (e.g. cancel, confirm, reconcile). Avoid showing a log of raw event names in the compact surface. Keep Context/Preview/Run provenance, source detail, route, timing and usage in workspace progressive disclosure.

The visible stage vocabulary should follow app evidence, not hidden model thoughts: for example, “Đang chuẩn bị ngữ cảnh,” “Đang chờ mô hình,” “Đang đọc dữ liệu,” “Đang kiểm tra kết quả,” and terminal states such as completed, waiting for confirmation, retryable, unknown, cancelled or deadline exceeded. Preserve the last known stage on heartbeat and distinguish “connection active, no new event” from “initializing.” Never imply provider TTFT is when the user first sees text while the current buffering contract delays text until terminal classification.

### Metrics: separate the paint from the model

Measure separate boundaries, preferably using monotonic clocks within one process/session and persisted timestamps for reattachment:

- **Browser acknowledgment:** send/click to the first painted local echo/status. Measure Event Timing/INP and a dedicated click-to-visible-ack user-timing metric. Report p50/p75/p95 segmented by device/browser/viewport. The owner’s ~400ms goal is an app-specific target; it is not an external standard. INP ≤200ms at p75 is a separate general browser reference.
- **Durable acceptance:** request arrival to committed `run.accepted`; do not substitute the synthetic `run.reserved` event.
- **Server/provider boundaries:** run queued/accepted, provider dispatch, provider connect, first provider output/TTFT, last provider output/terminal and total run duration. Preserve reported values and nulls; separate provider TTFT from event polling/replay delay and from first answer paint.
- **User-visible completion:** first visible answer text, preview available, or terminal failure state. Since text is currently buffered, present it as “answer delivered,” not streamed TTFT.

No percentage or ETA should be rendered unless the operation has a reliable denominator and measurable progress. Elapsed time is useful, but says how long the run has taken, not how much remains.

### Feedback and privacy-safe telemetry

Make feedback contextual to the artifact: a compact Good / Report issue affordance on assistant answers and errors/unknowns, in addition to receipt feedback. Offer short reason codes such as inaccurate, missed intent, wrong context, unsafe boundary, tool/result issue, slow, or disconnected. Keep narrative and expected-result optional. Bind each submission to an explicit turn/run/call/event sequence (or receipt), include an idempotent client ID, and show “saved” separately from later triage/resolution. Reuse the encrypted per-conversation content boundary for all free text; do not copy prompt/response/arguments into routine telemetry.

Keep the app-native ledger authoritative. For aggregate metrics, record schema/app/policy versions, event/stage and terminal class, timing values, provider-reported usage, and bounded route category; use low-cardinality dimensions. Do not use conversation/run IDs as metric labels. If trace correlation is needed, keep identifiers in access-controlled traces, and do not export raw prompt, completion, tool arguments/results, task titles, credentials, or full source IDs. Apply an explicit retention/TTL and export opt-in before any external sink; retain provider usage/cost as null when missing.

**OpenTelemetry:** adopt as a thin optional instrumentation/export mapping when the application needs cross-layer trace interoperability or repeated multi-provider diagnosis. Keep custom run/event semantics and durable recovery in the existing app ledger, since GenAI conventions are currently marked Development and conventions alone do not express Mimi’s owner-confirmation, source-freshness or unknown-outcome invariants.

**Langfuse/Phoenix:** do not self-host either as a prerequisite for this dogfood loop. Langfuse’s documented minimum service footprint and indefinite default retention make it a poor fit next to a 512 MB service without a real shared-observability need. Phoenix can be considered for a disposable, redacted local experiment if an interactive trace UI proves valuable; it still must not become canonical state or silently receive private content.

## Counterargument

The strongest case for adopting an external observability system now is faster inspection across browser, server, provider and tool spans, plus standardized dashboards and less bespoke metric code. That could expose timing distributions and recurring failures that an Owner-only conversation log will not. The nearest simpler alternative is to improve existing event/usage records, add a small bounded aggregate metric view, and map to OpenTelemetry names at an export seam later. Given an already durable ledger, one-owner dogfood scale, active-development GenAI conventions, privacy boundaries and 512 MB deployment, the simpler alternative currently has the better fit.

## Suggested QA and implementation gates

These are advisory acceptance probes, not executed checks:

1. In the Owner’s normal non-F11 browser workflow, measure click-to-visible acknowledgment separately from server acceptance. Include normal desktop width, narrower desktop/tablet where the dock becomes a sheet/dialog, and mobile. A single Owner session can establish usability but cannot support population-level percentile claims; accumulate enough repeated runs before interpreting p75/p95.
2. Exercise fast answer, delayed provider, iterative read/tool, long run, pre-dispatch failure, post-dispatch unknown, cancellation, deadline, Resume and Reconcile. Verify state and labels match durable event order and no hidden retry occurs.
3. Close/reopen the dock, switch domain tabs/conversations and reload the browser during an active run. Confirm same run is reattached, elapsed time is continuous, replay is sequence-stable, and no duplicate provider call or user message occurs.
4. Confirm no fake percent/ETA, no “accepted” before durable acceptance, no “initializing” heartbeat regression, and no label implying live answer tokens while text is buffered.
5. Submit a wrong-answer report and an error-state report. Verify target linkage, encryption, idempotent retry, visible save acknowledgment and unresolved/triage lifecycle; verify no prompt/answer payload appears in routine diagnostics/export.
6. Check keyboard, reduced motion and screen-reader behavior. Ensure the status is announced when it changes without announcing a ticking elapsed timer every second.

Before calling this Owner-dogfood-ready, reconcile the exact frozen worktree/commit against the project’s existing review and CI gates; prove corrected acceptance and heartbeat labeling with deterministic cases; review the bounded telemetry schema and retention/privacy boundary; then perform the already gated live Chrome and route acceptance before Owner dogfood. This report authorizes none of those external or product-changing actions.
