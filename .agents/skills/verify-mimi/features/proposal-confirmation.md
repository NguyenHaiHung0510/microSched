# Preview, revision and frozen confirmation

Current source at the [indexed baseline](README.md): `frontend/src/MimiScreen.tsx:142` and `:1106`, `backend/app/web/routers/mimi.py:625` and `:765`. Runtime **NOT_RUN**.

## Sub-features

Review, revision, rejection and explicit text Confirm. Stale/unknown recovery, durable readback and receipt-bound Undo preview.

## How to get to it (user POV)

From an owned proposal, inspect the summary then the detailed change list before taking the permitted action. Read an applied receipt under the transcript and use **Hoàn tác** only when the scoped undo-preview case is granted.

## Driving it in a current synthetic candidate

Use `mimi-change-set` for the simple preview or [collection review](collection.md) for collection. Scope the guarded decision buttons to `mimi-preview-actions`. Decision uses `POST /api/mimi/change-sets/{id}/decision` with the exact digest/nonce/request identity. An unknown result requires receipt reconciliation. `mimi-receipt` or the applied transcript receipt can reconcile after reload. **Hoàn tác** resolves the applied receipt and prepares an inverse preview through `POST /api/mimi/receipts/{id}/undo-preview`.

Oracle: Read/review/revision alone causes zero domain writes. Exact-authorized Confirm/Undo Confirm applies the frozen target set once with a matching receipt and readback. Stale, expired, conflicting and blocked-new cases preserve the documented authority/state. See `frontend/e2e/mimi-night-ui.spec.ts` and `backend/tests/test_mimi_confirmation_preflight_pg.py`.

## Gotchas

Keep the actual run’s Confirm0 or explicit exact one-use mutation permit. Preserve the original decision identity through unknown outcomes. Voice fast-apply has its own [capability and oracle](voice.md).
