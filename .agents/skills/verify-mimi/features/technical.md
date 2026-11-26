# Technical detail dialog

Current source at the [indexed baseline](README.md): `frontend/src/MimiScreen.tsx:1341`, `frontend/src/MimiDock.tsx:61`, `frontend/src/MimiCheckpointViewer.tsx:49`. Runtime **NOT_RUN**.

## Sub-features

Technical detail dialog, run/manifest and checkpoint inspection, model identity/usage uncertainty and evidence readback.

## How to get to it (user POV)

In side-chat open **Tùy chọn side-chat** → **Chi tiết kỹ thuật** for the owned conversation. Workspace inspection also uses the [data rail](context-rail.md).

## Driving it in a current synthetic candidate

Use `mimi-technical-dialog`, `mimi-run-observations` and `mimi-checkpoint-viewer` when corresponding data exists. Use an owned run with synthetic call, manifest and optional checkpoint/evidence bundle. Compare the authorized evidence bundle/owned conversation response and actual observed call receipt.

Oracle: The shown source, phase, units and requested/effective model identity match attributed data. Missing usage/cost/route stays unknown. No hidden reasoning or raw sensitive diagnostics in evidence.

## Gotchas

The separate technical dialog and Workspace run rail expose related views. Use the selector scoped to the surface reached.


### Historical Task091 shared shell readiness
R2 Task/Entry outbox uses separate canonical snapshots/pending projection and current private/principal epochs. Mimi remains online, no queued arbitrary URL/provider/confirmation. Verify a deterministic canonical invalidation does not erase pending Task/Entry state through the current R2 synthetic shell. Actual Mimi activation/provider acceptance NOT_RUN. The dated commands remain in the [Task091 recipe](../../verify-microsched/features/offline-outbox.md).

### Task095 funding compatibility
Funding is a native Tracker/Entry lane, not a Mimi tool capability. Existing agent/default Entry reads do not opt into nested funding metadata; ordinary agent updates omit the optional FK and preserve it. No new source-ID write or provider activation is granted. Shared lock/cache and protocol1 semantics use the current [funding recipe](../../verify-microsched/features/funding-entry.md); do not rerun a provider matrix or archived Owner192 doctor. Actual Mimi/provider acceptance remains NOT_RUN.
