# Run observations, context and recovery

Browser E2E/conversation statistics là observational records, khác provider
latency/server duration/billing. Current source đã bỏ timing line dưới từng
Mimi reply/system notice; không dùng `mimi-answer-timing` như visible control.
Preview/Confirm/Resume vẫn có phase/source riêng; failed/cancelled/unknown không
vào success averages. Missing/hidden/offscreen/reload phải giữ unknown đúng nghĩa.
Xem [current metrics/feedback contract](../../../../docs/reference/ui-behavior.md).
Không có model call/DDL/per-token polling mới từ measurement hoặc recipe này.

Current source at the [indexed baseline](README.md): `frontend/src/MimiScreen.tsx:853`, `:973` and `:1068`, `frontend/src/MimiRunObservations.tsx:13`. Runtime **NOT_RUN**.

## Sub-features

Pause/cancel, Resume, unknown outcome reconciliation, typed overflow and truthful run/usage state.

## How to get to it (user POV)

Open an owned run in Workspace or dock. Inspect the progress/status surface. Attempt Pause, then Resume only for a frozen resumable text run. Use the typed unknown recovery path before deciding on any retry.

## Driving it in a current synthetic candidate

Scope **Tạm dừng** and **Huỷ run ngay** to `mimi-progress`. Read `mimi-unknown-recovery`, `mimi-context-limit-notice` and `mimi-run-outcome` when present. **Tiếp tục** may make a successor run. Observe `GET /api/mimi/runs/{id}/events` and its `/stream` variant, the scoped `POST` actions `pause`, `cancel`, `resume` and `reconcile`, and the attributed `mimi-run-observations`.

Oracle: No duplicate user message, exact parent/successor linkage and at most the allowed recovery for a definite typed overflow. UNKNOWN preserves liability until reconciled. Bind deterministic SDK outcomes, retained user source/history and call/usage oracles. See `backend/tests/test_mimi_owner192_resume_pg.py`, `backend/tests/test_mimi_recovery_pg.py` and the [operating contract](../../../../docs/mimi/operating-contract.md).

## Gotchas

Inspect durable effects and run identity before retry. Provider outcomes and physical timing stay separate from synthetic response statistics.
