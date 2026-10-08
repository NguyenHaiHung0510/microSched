# Round 0 — local baseline (T1, 2026-09-26)

Scope: code and dated receipts in `feat/065-mimi-p1c-context-loop` at `1a10eb4`. This is a repository observation, **not** a live/provider/production test. No key or API was used.

| Seam | Observed implementation | Decision-sensitive gap |
| --- | --- | --- |
| Transport | `backend/app/agent/openrouter.py` builds OpenRouter requests with `store=false`, provider ZDR/data-collection/price controls, usage, optional streaming; parses a terminal union and classifies dispatch errors. `httpx` is already a declared runtime dependency. | Compare official SDK with these exact fields and **number of upstream dispatches**, not just a hello-world completion. Unknown outcome must not silently retry. |
| Loop and authority | `backend/app/agent/loop.py` is a finite read-only loop; `backend/app/agent/context.py` has typed envelope/terminal outcomes; `backend/app/agent/tools/registry.py` exposes query, aggregate, inspect-batch and one create-candidate proposal. Domain write remains outside the loop. | A generic agent runner cannot inherit write or privacy authority. Assess whether it can replace loop mechanics while preserving the frozen preview/confirmation, ledger, bounded reads and source freshness. |
| Durability | `backend/app/agent/runtime.py` supervises coroutines with a PostgreSQL advisory guard; `service.py` persists runs, events and provider-call states. `compaction.py` creates validated extractive checkpoints. | Compare mature checkpoint orchestration to current design; do not treat ephemeral process tasks as durable truth. Receipt B24 states crash after a succeeded provider terminal can halt truthfully without reconstructing the frozen preview: this is an explicit limitation, not a complete recovery claim. |
| Feedback and visibility | Backend supports `turn/run/call/operation/receipt` feedback targets (`contracts.py`, `service.py`), but `frontend/src/MimiScreen.tsx` currently presents a feedback form only when there is a Task receipt. It maps SSE stages to a short status, elapsed time and streamed text. | Wrong chat answer, failed run or misleading read-only response lacks the same easy feedback affordance. Current browser acknowledgment/INP and stage timing are **not measured** here. |
| Dashboard | `frontend/src/MimiControlCenter.tsx` still uses synthetic usage and a local Settings value for 30 minutes. | Do not present these as buyer-backed operational metrics or a wired lease setting. |

Prior B24 receipt (`agent-tasks/2026-09-22-research-mimi-context/24-p1ca-implementation-status.md`) records offline green suites and a limited no-key SDK spike, but no live model proof. Its conclusion to retain `httpx` is a **prior dated hypothesis** to challenge with the current research, not an immutable architecture choice.

The Owner asks for research/advice. No package install, model/API egress, D10, test mutation, runtime change or library migration is part of this round.
