# Project B verification candidate

Status: H14-N1-G1 approved preparation; generated skills DRAFT pending independent runner review and real end-to-end receipts. This private Owner harness revision changes only project instructions, maps and verification helpers. No product UI/feature implementation, merge/deploy, real data, Neon or paid model calls.

## Routing and map

Use ordinary requests: explain→how/why/teach, compare→read-only inquiry, diagnose→reproduction, design→approved requirements/examples/interfaces, implement→actual batch grant, verify→project driver. Global Owner B supplies conditional leaves; project skills below provide concrete commands/selectors. They do not grant writes or replace product specs.

- [microSched driver](../.agents/skills/verify-microsched/SKILL.md), [map](../.agents/skills/verify-microsched/features/README.md).
- [Mimi driver](../.agents/skills/verify-mimi/SKILL.md), [map](../.agents/skills/verify-mimi/features/README.md).

## Resource and runner contract

Task namespace H14-N1, 20261015. Main alone starts/stops the actual runtime. Two lanes run sequentially because Vite's inspected proxy uses backend8000 and frontend5173. Both use Postgres55456 with unique container/volume/database/state per lane: `h14-n1-20261015-microsched[-db]` / `microsched_h14_microsched` / `.local/h14-night/microsched`; `h14-n1-20261015-mimi[-db]` / `microsched_h14_mimi` / `.local/h14-night/mimi`. Volume label `harness.task` must equal exact lane identity; container retains existing synthetic-label/image/mount/loopback/PID validation.

Never reuse/reset/delete the legacy `microsched-mimi-p0-055-db` or unlabelled resources. Fresh task volume is explicitly created with its label; cached pgvector/pgvector:pg18 is required, no implicit pull. Helper imports the actual sandbox driver from the explicit source after manifest/head checks; changes task identity constants and isolated paths, retains existing scrubbed env allowlist and bootstrap/migration/seed/ownership code. Synthetic STANDARD metadata enables real-chat shell but live-provider/context/collection/notifications/pilot remain false; provider routes/keys not changed. No generated credentials printed. Wrapper has no reset/delete action.

microSched source is this sole harness branch from aa9d7251; Mimi QA source is a clean exact680b7f9b snapshot, not latest Owner product acceptance. Shared source/build/config manifest freezes before launch/batch and after/relevant changes. Main confirms capabilities/listeners/Docker image/volume identity/fixture before T3 driving. Any ownership mismatch holds that lane; independent approved work continues. `.local` is ignored and not evidence storage; private receipts survive stop. Cleanup stops exact owned PIDs/container and retains task data for auditable separately scoped disposal.

## First finite QA batch

1. microSched public homepage: open /home?lang=vi, observe login link/hero, switch English→Tiếng Việt, verify actual hero changes and relative link; no OAuth/external navigation/provider call.
2. Stop owned microSched runtime. Start exact Mimi snapshot under separate namespace, synthetic login; create STANDARD conversation, rename H14 synthetic conversation, reload and reopen; assert persistence and no send/run/turn/provider call.
3. Stop owned runtime, retain canonical action/assertion/screenshot/call receipts and verify they remain. Report source map other features NOT_RUN. Physical device/CI/production/live conversation quality are separate and NOT_RUN.

Independent T3 receives frozen runner/source/profile/oracles/capabilities and writes only its private receipts. T1 accepts consolidated results, groups justified helper/map corrections and retests affected/unproved assertions. No product repairs to make this harness batch pass. Required checks/branches/PR delivery remain the project policy.

## R3 runner and map corrections

Explicit approved source/lane pairs are checked before importing the sandbox. The browser uses only HTTP 127.0.0.1:5173, read-only Vite modules/assets and per-lane app routes. Mimi permits only synthetic session entry/logout, conversation creation and title PATCH as writes; no send/run/decision/configuration/feedback/notification writes. WebSockets are closed before connection; Vite HMR is unnecessary for this finite proof. Every invocation needs a fresh private run directory and preserves preflight BLOCKED receipts. Use a new attempt directory after inspecting the prior result. Both maps now enumerate 12 observed top-level entrypoints each, including required but unavailable fixtures, all NOT_RUN until receipts exist. Map breadth does not expand the initial two-case runtime batch.
