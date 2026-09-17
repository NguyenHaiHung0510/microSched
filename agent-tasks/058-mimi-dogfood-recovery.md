# 058 — Mimi P1R dogfood recovery and interaction shell

Status: **OWNER UI PREVIEW READY — 058A IMPLEMENTED; 058B–058D NOT STARTED (2026-09-17)**

> Executor/integrator: T1 GPT-5.6 Sol · Profile: Balanced · Owner grant: continue the approved Mimi delivery flow, correct the failed P1 local dogfood, build the local UI/UX continuously for Owner review, then implement and verify the bounded package. No Astra delegation.

## 1. Outcome

Close the 2026-09-16 Owner dogfood failure before expanding P2:

1. Mimi chat is a persistent side surface beside Task, Notes, Calendar and Tracker; desktop content reflows while it is open, and mobile uses a full-height sheet.
2. The top-level Mimi tab is a management **Control Center** whose default landing is Overview/dashboard, not a transcript.
3. Owner can create, switch, rename, archive and restore STANDARD conversations.
4. Ordinary chat may return assistant text or a clarifying question; action intent may propose at most one typed `task.create.v1`, which still requires frozen preview and Owner confirmation.
5. Long live-model turns stay visibly alive through streamed application/provider events, elapsed time, cancel/recovery controls and exact terminal state. A short generic API timeout must not kill a valid Mimi run.
6. A full local live route completes representative journeys through the actual Mimi app, not only direct provider probes or mocked UI.

P1's ledger, encryption, server-issued authority, frozen confirmation, idempotent execution and receipts remain the substrate. This correction changes product shape and runtime transport; it does not weaken write safety.

## 2. Owner decisions and source reconciliation

Owner decisions approved 2026-09-17:

- side-chat is the primary ubiquitous conversational surface;
- Mimi tab is dashboard/general information/configuration/management; chat inside it is secondary deep-work capability;
- Control Center MVP contains real `Overview`, `Activity`, `Conversations` and `Settings`; Orbit, Memory and Skills appear only when corresponding capability is real;
- use streaming; a several-minute turn is acceptable when progress/tool activity is honest and visually clear;
- remove the accidental 20-second Mimi cutoff. P1R uses a configurable seven-minute interactive safety ceiling, not a latency acceptance target; actual elapsed/TTFT/tool/terminal time is recorded;
- no P2 domain expansion until this correction passes Owner local dogfood.

This interpretation is independently supported by the pre-P1 product records:

- unified spec: Mimi UI maps to `Overview / Orbit / Memory / Skills / Settings`;
- execution spec: Owner requires one common Mimi management area, explicit editable-limit requested/effective state and Orbit as a sub-area;
- master delivery plan: current dogfood gate forbids propagating the P1 tab-chat product shape.

## 3. Scope and non-goals

### In scope

- shared thread core rendered as desktop/mobile side-chat and as the Conversations area inside Control Center;
- Overview, Activity, Conversations and existing-setting presentation;
- STANDARD conversation list/new/switch/rename/archive/restore;
- streamed assistant text plus application-visible run/tool/preview events;
- long-run cancellation, disconnect reconciliation and truthful error recovery;
- provider routing policy split between exact-pin evaluation and bounded adaptive dogfood;
- local synthetic preview, focused frontend/API work, throwaway PostgreSQL if schema changes, and Owner manual local acceptance.

### Out of scope

- PRIVATE conversation enablement, private tools or production real-personal chat;
- permanent conversation deletion before the approved retention/deletion manifest is implemented;
- Orbit jobs, long-term Memory, Skills publication or fake settings for absent capabilities;
- Notes/Calendar/Tracker/Subscription writes, documents, web search or multi-model automatic routing;
- Neon migration/Restore/Sync, production enablement, cleanup of retained Task 056/057 artifacts;
- MIDEX heavy benchmark or production default model adoption.

## 4. UI information architecture

### 4.1 Global side-chat

- One persistent launcher in the authenticated shell, separate from the domain tab row.
- Desktop grid: `minmax(0, 1fr)` main surface plus a docked Mimi panel. Initial panel width is bounded and owner-resizable without horizontal page overflow; reopening restores only presentation state, never transcript content in browser persistence.
- At narrower widths use an accessible full-height sheet. No hover-only action; close, conversation switch and primary actions meet touch targets.
- The same selected conversation remains open while Owner moves through Task/Notes/Calendar/Tracker.
- Header distinguishes browser connectivity, API health, route availability and current run state. Never label `navigator.onLine` as provider health or hard-code a route name.
- Transcript, frozen preview, receipt and errors are separate semantic items. Composer remains reachable; diagnostics/raw event names are behind an explicit inspector.

### 4.2 Mimi Control Center

Default landing is **Overview**:

- effective model/provider/routing mode and checked-at time;
- enabled/disabled capabilities and their gates;
- health/error summary;
- pending approvals and recent activity;
- concise usage/cache/cost fields with `OBSERVED / ESTIMATED / UNAVAILABLE` provenance.

Other real areas:

- **Activity:** runs, receipts, terminal state, timing, route, usage and bounded diagnostics;
- **Conversations:** list/manage conversations and open the shared deep-work thread workspace;
- **Settings:** only configuration that exists in P1R, with requested/effective/applied/failed state. No secret or fake provider parity.

Orbit, Memory and Skills remain capability-gated; their absence is not represented as working empty tabs.

## 5. Streaming and long-run contract

- Browser sends an authenticated unsafe request and consumes a `text/event-stream` response through fetch streaming, preserving Mimi CSRF checks; do not use a state-changing GET.
- Provider request uses streaming where the exact endpoint supports required tool behavior. Provider chunks are normalized into application events before reaching UI.
- Persist run/provider intent before dispatch. Terminal provider result and usage are persisted before materializing canonical assistant message/change set.
- Allowed public event types are bounded and versioned, for example: `run.accepted`, `context.reading`, `provider.connected`, `assistant.delta`, `tool.proposed`, `tool.validating`, `preview.ready`, `run.recovering`, `run.terminal`, `heartbeat`.
- Never stream raw hidden chain-of-thought. UI may show truthful stage animation and an approved application-visible reasoning summary only; partial tool JSON stays server-side until complete and validated.
- Heartbeat is liveness, not fake progress. One active stream per run; seven-minute default ceiling; Owner cancel closes dispatch and records a distinct terminal state. No unbounded background loop or dense polling.
- Disconnect is ambiguous until reconciliation. On reconnect, query the durable run/client ID; never create a second turn merely because the transport ended.
- The generic 20-second API helper remains for ordinary requests. Mimi streaming has an explicit longer deadline and its own reconciliation path.

## 6. Provider routing and cache policy

Do not answer the provider question with one universal pin:

### Exact-pin evaluation lane

- Benchmark and route-card units pin exact `(model, provider endpoint, quantization, reasoning effort, route-policy version)` with fallback disabled.
- This is required for attributable MIDEX quality, cache, latency, uptime, tool-error and cost evidence.

### Adaptive local dogfood lane

- Do not hard-pin one provider and do not route completely unrestricted.
- Use an allowlist of endpoints that individually passed the route contract, plus `require_parameters=true`, `data_collection=deny`, ZDR policy, quantization/capability filters and `max_price`.
- Leave manual `order` unset so OpenRouter can use price/availability load balancing and provider sticky routing; allow bounded provider fallback inside the eligible pool.
- Send a non-identifying opaque `session_id` derived from the conversation so multi-turn prompt cache can remain warm. Persist the actual provider endpoint on every call.
- Record uncached input, cached input, cache writes, output/reasoning, cache discount, cost, TTFT, throughput, terminal status and route change.

Cache hit rate is important but not sufficient. It reduces only eligible repeated input; base input price, cache-read price, output/reasoning volume, prefix stability, TTL, tool reliability, latency and uptime remain separate. Owner's 2026-09-17 provider snapshot is accepted as dated discovery evidence, not a production guarantee.

## 7. Delivery order

### 058A — Local interaction-shell preview

1. Build the Control Center Overview and persistent side-chat against synthetic, adversarial fixture states using existing tokens/components.
2. Keep a real local app reachable with hot reload for Owner review.
3. Review desktop 1280/1440/1920 and mobile 390; iterate until Owner accepts the product shape.

Preview approval is not backend/full QA acceptance. Do not implement broad runtime/migration work before this gate.

### 058B — Conversation and truthful status foundation

- Add only schema/API fields needed for conversation management and status/route metadata.
- Reuse per-conversation DEK; title/content-bearing metadata remains encrypted as required.
- Add list/new/get/rename/archive/restore with ownership, idempotency, pagination and lock-safe presentation.

### 058C — Streamed run and provider-policy correction

- Implement normalized stream, long-run deadline/cancel/reconcile and text-or-one-tool terminal union.
- Port the Task 057 unsupported-parameter correction with focused regression coverage.
- Implement exact-pin route card and adaptive eligible-pool policy as separate versioned configurations.

### 058D — Full local acceptance

- focused and full frontend/backend suites;
- throwaway PostgreSQL migration/drift/full lane when schema changes;
- Playwright real shell/state matrix plus full local server journeys;
- at least five consecutive valid full-app route terminals and three complete journeys, including ordinary `hello`, clarification, Task preview/revision/confirm, reject and disconnect reconciliation;
- Owner manual local dogfood receipt.

Only after 058D may T1 propose PR/merge. Production remains default-off; migration/real enablement is separate.

## 8. Acceptance matrix

| Gate | Required proof |
|---|---|
| P1R-IA-01 | Mimi tab lands on Overview; Activity/Conversations/Settings are subordinate real modules, not the page identity. |
| P1R-SIDE-01 | Side-chat stays usable beside all four domain screens; desktop reflows and mobile sheet preserves draft/conversation. |
| P1R-CONV-01 | New/switch/rename/archive/restore and reload continuity; no cross-conversation message/run leakage. |
| P1R-STREAM-01 | Truthful staged events, elapsed time, heartbeat, cancel and terminal state; no raw CoT or partial tool JSON exposure. |
| P1R-RECOVER-01 | Transport timeout/disconnect reconciles same client/run without duplicate provider call or write. |
| P1R-ROUTE-01 | Exact-pin lane is attributable; adaptive lane stays inside eligible allowlist and records actual provider/cache/cost/timing. |
| P1R-CHAT-01 | Zero-tool assistant response and exactly-one-tool preview both validate; writes still require confirmation. |
| P1R-UX-01 | Keyboard/touch/focus/reduced-motion/adversarial content and viewport matrix pass; raw internal enums are not primary copy. |
| P1R-OWNER-01 | Owner directly approves local preview, then directly completes local dogfood journey. |

## 9. Stop and re-plan

Stop for Owner if a proposed fix weakens confirmation/idempotency/privacy, requires PRIVATE or production-data authority, needs a real Neon action, adds a new paid commitment, or conflicts with the approved Control Center identity. Preserve logs after roughly two unproductive attempts at the same route/runtime blocker.

## 10. Evidence paths

- Canonical task: this file.
- Receipts: `agent-tasks/task-058/`.
- UI preview artifacts: local ignored evidence until inspected/sanitized; only approved screenshots may enter the repository.
- Task 057 remains historical evidence for the direct-pass/full-app-fail route and is not rewritten as PASS.
