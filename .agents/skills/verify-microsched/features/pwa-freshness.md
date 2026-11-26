# PWA and visible data freshness

Current source at the [indexed baseline](README.md): `frontend/src/LiveStatus.tsx:57`, `frontend/src/App.tsx:180`, `frontend/src/PwaUpdates.tsx:42` and `frontend/src/sw.ts`.

## Sub-features

Active-query freshness, degraded/offline status and safe automatic SW update. Install and push are separate capabilities.

## How to get to it (user POV)

Open a signed-in **Task**, **Ghi chú** or **Theo dõi** screen. Check freshness with frozen network/timestamps. A controlled update needs two generations of the same production build in one disposable origin, and should include a second controlled tab for the dirty case.

## Driving it in a current synthetic candidate

Use `app-live-status[data-state]` and `[data-app-generation]`. Observe actual waiting/controller generations, reload, dirty owner, mutation/queue state and the durable result. `frontend/src/LiveStatus.test.tsx` and `frontend/src/pwa-update.test.ts` cover isolated status/predicate contracts. Production preview and the controlling SW are needed for update proof.

Oracle: Status reflects the selected query’s freshness. An update activates and reloads at a safe boundary. A dirty/uncertain tab retains its input, and compatible pending rows keep identity until a single canonical ACK.

## Gotchas

Use disposable state and a current build/restore plan. Physical install/iPhone, legacy-profile transition, Push and current runtime are **NOT_RUN**. The archived Task096 cell is bound to its own candidate.

## Historical Task096 — safe automatic app update / Owner334

`PwaUpdates.tsx` now renders no recurring update banner. An actual waiting worker activates once at a clean boundary; controllerchange independently rechecks this tab before reload. Another tab may activate while a dirty tab keeps its draft. An update error quietly retains the current app, with no polling/reload loop.

Safety inputs: existing form baselines track edits, not all nonempty fields; detached forms are pruned. Mimi composer/feedback forms declare actual draft ownership rather than treating saved reason/config controls as dirty; matching ACK cleans only sent intent, newer prose stays protected. Actual non-form Note checklist editor and Mimi feedback/run markers, memory-only Mimi composer drafts across conversations and cached unsent positive feedback are guarded. IME composition, TanStack mutations, local admission, unverified/error storage, sending/unknown queue state defer silently. Idle durable pendingV1 is allowed and preserved with unchanged principal/protocol/digest/idempotency/order.

Driving: use own096 preview4179/API8006 and `r6_browser.mjs`. Two controlled generation builds must come from the exact same frozen source with only VITE_APP_GENERATION changed, preserve complete candidate dist manifest/backup and restore all bytes after the proof. Existing Vite preview suffices; do not introduce a server, clear a site/profile, unregister workers or drop queue rows as a workaround.

Required affected outcomes: clean automatic reload/no banner; dirty form and second-tab deferral through external controllerchange; clean-after-save/clear resumes without a click; existing pendingV1 sameID/digest persists and ACKs once. Predicate tests alone do not establish runtime. Record real SW/client generations and wire/IDB/canonical outcome. Provider/legacyOwnerprofile/physical iPhone remain NOT_RUN. Author proof is not independent acceptance.

## Historical H14 visible-freshness map

Source: `frontend/src/LiveStatus.tsx:43` (`app-live-status`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Active-query freshness, offline/paused/error status; install/service worker and push entrypoints governed separately.

## How to get to it (user POV)

Signed-in Task/Notes/Tracker view → app-live-status; inspect isolated worker lifecycle only in an approved platform case.

Real prerequisites: Frozen query timestamps/network state; disposable profile and explicit platform capability; service workers are blocked in initial browser proofs.

## Driving it with H14 isolated browser/CLI

app-live-status data-state; frontend/src/sw.ts and vite.config.ts define worker boundary.

Observable oracle: Status reflects active query freshness and connectivity; independent offline/outbox/push oracle required for each durable capability.

## Gotchas

Emulation ≠ physical iPhone/PWA install. No permission prompt/real device subscription. First proofs do not test workers.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
