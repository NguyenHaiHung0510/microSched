# 067 — Mimi feedback and offline decision replay

Status: **OWNER-APPROVED 2026-09-30 — IMPLEMENTATION / NO PROVIDER EGRESS**.

Closeout 2026-09-30: integrated into066 frozen code945b324, with [scoped PG/browser feedback and replay evidence](2026-09-30-mimi-research/prototype-result.md). Actual call-label ambiguity repaired. Scripted local feedback acceptance is separate from full visual/device/live-model evidence and runner adoption.

Scope inside the 066 prototype grant: narrow existing full-app feedback for answer/turn/run/call in addition to receipt; validate target membership/ownership and preserve encrypted comments/expected outcome/idempotency. Associated labels, existing shadcn controls/tokens/light Nunito; draft retained on error, truthful saved/pending/error states. No separate design system/provider SDK/schema migration.

Prepare a synthetic-only manual replay contract and optional fake DecisionFacade outside ordinary runtime: bounded enum, probabilities/abstention, explicit source/policy/fixture versions, expected classification, no model-created authority/action payload. No automatic API call on normal turns, no real transcript export. Fake decisions prove protocol/error behavior, not Jev/Vietnamese quality. Real Jev/Kev semantic cohort requires its own exact endpoint/data eligibility and call/token/billed cap approval.

Acceptance: text-only answer without receipt can receive feedback; stopped run and call targets bind the correct conversation; wrong/malformed target rejects before insert; duplicate client_id with same content is idempotent and changed content conflicts; UI target changes cannot silently attach a draft to another object. Replay rejects forged authority/invalid enum/unbounded input, fake timeout abstains, classifications don't invoke tools/write. Intended negative -> GREEN proof for new safety checks. Focused frontend/backend tests plus synthetic full-app integration after T1 freeze. Preserve receipt feedback and logged-out/private-data boundaries.

Single writer in this slice's worktree; integrate into066 after local commits and T1 inspection. T1 owns final state/diff/findings. See 066 for final Luna+Gemini review pair and no live/deploy scope. User-visible feedback is product functionality; prototype/replay internals remain off ordinary user flows.
