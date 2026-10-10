# 086 — Mimi Task Collection, approved Full A

Executor: coherent delegated T1 GPT-6.1 Sol/xhigh, sole writer. Branch
`feat/086-mimi-task-collection`; baseline `6ed330d4c2be9cd272794d10766cee59bf93db4f`.
Full A START and overnight autonomy are explicit Owner grants. Older WAITING
headers in the inquiry packet are historical. Expiry09Oct2026 11:00 Asia/Saigon;
checkpoint10:30; no new long work after10:45 without a safe finish basis.

Contract: [Task Collection](../docs/mimi-task-collection-contract.md).
QA: [finite spec](../docs/qa-specs/qa-mimi-task-collection.md),
[case manifest](../docs/qa-specs/mimi-task-collection-cases.json).
Migration: [0017 impact](../docs/migrations/0017-mimi-task-collection-plan.md).
These documents are the A1 freeze; implementation and independent acceptance are
separate. This task is PR-ready only; parent owns acceptance and eventual merge.

## Implementation packages and allowed file families

1. A2 command/schema core: `backend/app/domain/models.py`, `domain/tasks.py`,
   `domain/one_shot.py` only affected helpers, `agent/task_collection.py`,
   `agent/selection.py`, `agent/models.py`, `agent/crypto.py`,
   `alembic/versions/0017_mimi_task_collection.py`, affected Task/read tests.
2. A2 agent integration: `agent/service.py`, `context.py`, `context_builder.py`,
   `loop.py`, `langgraph_runner.py`, `graph_support.py`, `openrouter.py`,
   `openai_sdk.py`, `tools/registry.py`, `tools/task_reads.py`,
   `tools/task_content.py`, `policy/mimi-standard-v2.md`, `policy.py`,
   `observations.py`; targeted affected tests and synthetic fixtures.
3. A2 route/evidence: `agent/route_config.py`, bounded metadata seam in
   `openrouter.py`, `agent/evidence.py`, `core/settings.py`,
   `web/routers/mimi.py`, relevant tests; no new model admission.
4. A2 notification: `agent/notifications.py`, `domain/push.py` additive detailed
   result seam, `web/routers/mimi.py`, `main.py` startup/shutdown wake,
   existing `core/cron_timer.py` only if needed for owned wake integration;
   notification tests. Existing reminder consent/result behavior remains compatible.
5. A4 after backend-ready and Q-P0 closure: existing Mimi screen/dock/control
   center/context/configuration/run components and `frontend/src/lib/mimi-*`,
   narrow `App.tsx`, `sw.ts`, `sw-notification.ts`, tests. No wholesale adoption
   of rejected dirty previews. Read UI brief before UI writes.

No root source writes, production/Neon/schema execution, auth/session/PIN policy,
private/Finance/Health/ICS expansion, arbitrary SQL tool, permanent deletion,
recurrence, deployment or new model family. A material boundary conflict stops
that lane with evidence; routine choices inside this contract are autonomous.

Work packages are dependency estimates, not elapsed ETA: command/schema first;
agent/route/evidence and N2 next; immutable A2 candidate; independent Luna/max
and Gemini/high; grouped reconciliation; prototype amendment/dual closure; A4;
Chrome Luna/xhigh; final technical signoff/PR. Actual cost NOT_CAPTURED.
