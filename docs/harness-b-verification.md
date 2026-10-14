# Project B verification — scoped observed flows

Status: H14-N1-G1 local installation/discovery and scoped independent runtime proofs technically accepted 2026-10-15. Two cases PASS 2/2, UI assertions 10/10 and homepage decoded images 15/15; only 2/24 mapped entrypoints proved, 22/24 NOT_RUN. Public-home binds exact aa9d7251; STANDARD Mimi metadata binds exact 680b7f9b, NOT latest Owner product acceptance. Main-owned cleanup complete, receipts retained. Harness delivery/new-head CI and final Main report remain separate; no product UI/feature implementation, merge/deploy, real data/Neon or paid-model quality acceptance.

## Routing and map

Use ordinary requests: explain→how/why/teach, compare→read-only inquiry, diagnose→reproduction, design→approved requirements/examples/interfaces, implement→actual batch grant, verify→project driver. Global Owner B supplies conditional leaves; project skills below provide concrete commands/selectors. They do not grant writes or replace product specs.

- [microSched driver](../.agents/skills/verify-microsched/SKILL.md), [map](../.agents/skills/verify-microsched/features/README.md).
- [Mimi driver](../.agents/skills/verify-mimi/SKILL.md), [map](../.agents/skills/verify-mimi/features/README.md).

## Resource and runner contract

Task namespace H14-N1, 20261015. Main alone starts/stops the actual runtime. Two lanes run sequentially because Vite's inspected proxy uses backend8000 and frontend5173. Both use Postgres55456 with unique container/volume/database/state per lane: `h14-n1-20261015-microsched[-db]` / `microsched_h14_microsched` / `.local/h14-night/microsched`; `h14-n1-20261015-mimi[-db]` / `microsched_h14_mimi` / `.local/h14-night/mimi`. Volume label `harness.task` must equal exact lane identity; container retains existing synthetic-label/image/mount/loopback/PID validation.

Never reuse/reset/delete the legacy `microsched-mimi-p0-055-db` or unlabelled resources. Fresh task volume is explicitly created with its label; cached pgvector/pgvector:pg18 is required, no implicit pull. Helper imports the actual sandbox driver from the explicit source after manifest/head checks; changes task identity constants and isolated paths, retains existing scrubbed env allowlist and bootstrap/migration/seed/ownership code. Synthetic STANDARD metadata enables real-chat shell but live-provider/context/collection/notifications/pilot remain false; provider routes/keys not changed. The task-owned wrapper pins MIMI_PUBLIC_ORIGIN=http://127.0.0.1:5173 in its scrubbed synthetic runtime env, matching the browser origin across Vite proxying. Product CSRF enforcement is unchanged; do not fake Origin headers or use wildcard origins. A wrapper/env revision requires Main-owned copy/restart and a fresh source/helper/config freeze before metadata replay; source control checks alone do not prove the restarted backend. No generated credentials printed. Wrapper has no reset/delete action.

microSched source is this sole harness branch from aa9d7251; Mimi QA source is a clean exact 680b7f9b snapshot, not latest Owner product acceptance. Shared source/build/config manifest freezes before launch/batch and after/relevant changes. Main confirms capabilities/listeners/Docker image/volume identity/fixture before T3 driving. Any ownership mismatch holds that lane; independent approved work continues. `.local` is ignored and not evidence storage; private receipts survive stop. Cleanup stops exact owned PIDs/container and retains task data for auditable separately scoped disposal.

## Observed finite QA batch — 2026-10-15

Latest independent results: public-home attempt4 PASS 6/6 plus 15/15 decoded images, zero blocked; Mimi attempt2 PASS 4/4, zero blocked, reused after micro-only repairs because the Mimi body/policy is unchanged. Original micro attempt3 remains FAIL despite 6/6 UI assertions because 20 image GETs were blocked. T1 smoke is separate builder evidence. Main final-runtime-cleanup records owned app/database processes stopped, no reset/delete and all three selected receipts surviving. Evidence locator: private H14-N1/R9 final-grouped-retest-handback, per-case receipts/pixels and R6 final-technical-signoff.

1. microSched public homepage: open /home?lang=vi, observe login link/hero, switch English→Tiếng Việt, verify actual hero changes and relative link; no OAuth/external navigation/provider call.
2. Stop owned microSched runtime. Start exact Mimi snapshot under separate namespace, synthetic login; create STANDARD conversation, rename a run-unique H14 synthetic conversation bound to its synthetic ID, reload and reopen; assert persistence and no send/run/turn/provider call.
3. Stop owned runtime, retain canonical action/assertion/screenshot/call receipts and verify they remain. Report source map other features NOT_RUN. Physical device/CI/production/live conversation quality are separate and NOT_RUN.

Independent T3 receives frozen runner/source/profile/oracles/capabilities and writes only its private receipts. T1 accepts consolidated results, groups justified helper/map corrections and retests affected/unproved assertions. No product repairs to make this harness batch pass. Required checks/branches/PR delivery remain the project policy.

## R3 runner and map corrections

Explicit approved source/lane pairs are checked before importing the sandbox. The browser uses only HTTP 127.0.0.1:5173, read-only Vite modules/assets and per-lane app routes. Mimi permits only synthetic session entry/logout, conversation creation and title PATCH as writes; no send/run/decision/configuration/feedback/notification writes. WebSockets are closed before connection; Vite HMR is unnecessary for this finite proof. Every invocation needs a fresh private run directory and preserves preflight BLOCKED receipts. Use a new attempt directory after inspecting the prior result. At the R3 cutoff both maps enumerated 12 source-observed top-level entrypoints each, including unavailable fixtures; runtime status was NOT_RUN. Final status is one OBSERVED_ACCEPTED row per map, with the other 22 combined entrypoints NOT_RUN. Map breadth does not expand the initial two-case runtime batch.

## New-candidate and delivery boundary

These commands/maps describe the dated H14 freeze. Future sessions use owner-pstack maintenance to select the currently approved checkout/head/file closure, preserve WIP/ownership, prepare a new task namespace/source allowlist/binding and refresh selectors/prerequisites before reviewed launch. Keep H14 evidence immutable; do not remove its guards. Final status-doc edits are separately manifested and do not retroactively alter executed receipt bindings. Delivery HEAD/CI is separate from both runtime heads. One proved flow cannot make all mapped features or the latest product QA-complete.
