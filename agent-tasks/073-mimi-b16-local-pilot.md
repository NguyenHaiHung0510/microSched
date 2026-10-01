# 073 — B16 full local Mimi pilot

Owner grant: direct approval 2026-10-01 of T1's full local LangGraph B16 pilot; latest annotation requires implementation, QA and reconciled review before Owner dogfood. One writer per checkout. T1 backend/integration in 073; Luna/high frontend in 074. No merge, deploy, production, Neon, default migration or architecture adoption. Existing morning horizon 08:00 Asia/Saigon remains; checkpoint unfinished work then. Preserve 066 preview and lanes 069–072.

## Outcome and scope

Local-only, default-off pilot inside full Mimi workspace. Select 1–16 existing standard/public Tasks, query → group → draft → owner direction → immutable preview → exact confirmation → atomic Task mutation plus receipt. Prefix operation is deliberately bounded: `[planned] ` plus original title. The UI displays every before/after value. Real Task source fingerprints, expiry, owner, generation and digest must gate execution. Both actual LangGraph and control use identical domain handlers and PostgreSQL authority. Graph checkpoint contains references only. Pending runs resume after reload. Unknown dispatch must stop for reconciliation, never retry automatically.

Actual app Tasks live in a dedicated synthetic local database; no existing QA database is mutated. Private/deleted Tasks must not enter selection, preview or model context. No browser-profile stores, real personal payloads or credentials in artifacts. HTTPX remains provider transport. Deterministic provider evidence must be labeled; it does not prove conversation quality.

## Frozen frontend API

All routes below use existing authenticated session and state-changing Mimi same-origin/JSON/CSRF guards. Path `/api/mimi/workflow-pilot`. Disabled routes return 404. Errors use HTTP 409 with `detail` a stable reason string (invalid payload is 422). Every POST uses `X-Mimi-CSRF: 1`, JSON; no auto retries.

- GET `/tasks` → `{items: [{id: string, title: string}]}` (public, not deleted; at most 100 choices).
- GET `/runs` → `{items: Status[]}` (owned, at most 24 recent runs).
- POST `/runs` body `{run_id: UUID, task_ids: UUID[], engine: "graph" | "control"}` → Status. Generate run_id once per user action, retain it on timeout; recovery uses GET, never new automatic dispatch.
- GET `/runs/{run_id}` → Status (owner-bound).
- POST `/runs/{run_id}/advance` body `{generation: number, direction?: "apply_prefix", preview_digest?: string, cancel?: boolean}` → Status. Exactly one action; confirmation digest only, owner is server-derived. No client-authored operation/title.

Status = `{run_id, generation, engine, phase, draft, preview_digest: string|null, preview: {sources: [{id,version,title}], operations: [{id,title}], groups: string[][]}|null, receipt: {digest,changed}|null, stop_reason: string|null, provider_calls, events: string[]}`. Additional server preview authority fields may be ignored by UI. Phases query/group/draft/direction/materialize/confirmation/execute/succeeded/expired/cancelled/reconcile/repreview. Only direction enables direction button; only confirmation enables exact confirm; terminal and reconcile/repreview explain next step without silent retry. Cancel permitted for paused pre-execute runs. GET must not advance workflow. Capabilities adds `workflow_pilot_enabled: boolean`; mount only when true in workspace Mimi, no change to default dock/chat.

UI uses existing shadcn components, CSS tokens, Nunito, Vietnamese text, readable >=12px, touch >=44px, no hard card heights/hover-only affordances. Show selected count, loading and error, truthful phase, group/draft, every before/after, confirmation button, receipt and resume selection. Label synthetic/deterministic mode transparently; model-backed draft only after real provider QA is implemented and accepted.

## Acceptance gates

Targeted tests must cover disabled/local guard, unauthenticated/CSRF, owner isolation, private/deleted exclusion, forged digest, stale Task fingerprint, idempotent receipt and transaction rollback of actual Tasks. Safety guards need intended RED then restored GREEN. Existing relevant workflow tests must pass; backend/frontend checks, normal hooks and frozen independent review with finding reconciliation. T1 first bounded full-app browser smoke then freeze scenarios before delegating repetitive desktop/mobile/reload/error journeys. Chrome MCP eligibility must be demonstrated; no assumed worker access. Preserve raw receipts, explicit NOT_RUN boundaries, changed-file list and final Git state.

Paid QA: T1 alone may read exact MIMI_DEMO_1 from root backend/.env in process. Total authorized spending <=USD1.00, excluding USD0.50 key reserve. Existing confirmed USD0.00129543925 and unresolved USD0.046175 reservation count against this total. No worker may read/use key. Each new distinct call requires reservation, exact priced provider route/no fallback, finite tokens/deadline, usage before/after and ledger. Never redispatch the previous unknown DeepSeek attempt or release its reservation without evidence. No paid calls before domain/auth/atomicity safety gates pass.

## Status

IMPLEMENTING; full-app runtime/browser/provider acceptance NOT_RUN. Dogfood release is gated on implementation plus QA and reconciled review, not a completion date.
