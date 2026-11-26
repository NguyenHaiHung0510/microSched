# Response feedback and target binding

Task099 M2 candidate: detail **and expected** each8,000 Unicode codepoints for
Mimi/system ×positive/negative; no native truncation. Use `mimi-positive-detail`,
`mimi-positive-expected`, `mimi-feedback`, `mimi-feedback-expected` and their
visible counters. Test7999/8000/8001, emoji/IME/paste/middle edits, original
key/body/target on unknown retry, and late ACK preserving new edits. Existing
encrypted API envelope10,000 and causal evidence remain. See
[Task099](../../../../docs/reference/ui-behavior.md).
Independent current-candidate browser/device acceptance remains **NOT_RUN**.

Current source at the [indexed baseline](README.md): `frontend/src/MimiScreen.tsx:1109` and `:1156`, `frontend/src/MimiPositiveSupplement.tsx:71`. Runtime **NOT_RUN**.

## Sub-features

Response/notice-targeted feedback, positive supplement, draft/counts and unknown outcomes.

## How to get to it (user POV)

From a bound synthetic Mimi reply or verified system notice, scope the thumbs controls to that target. Open the corresponding positive or negative editor. Submit only under the exact permitted feedback write.

## Driving it in a current synthetic candidate

Use `mimi-positive-feedback` and `mimi-positive-supplement`, or the negative feedback dialog with `#mimi-feedback`, `#mimi-feedback-expected` and `mimi-feedback-target-snippet`. Observe `POST /api/mimi/conversations/{id}/feedback` with owned target/cause/ID and the durable acknowledgement. Bind the expected network fault before testing UNKNOWN. See `frontend/e2e/mimi-night-ui.spec.ts` and `backend/tests/test_mimi_feedback_target_binding.py`.

Oracle: The exact target/idempotency and 8,000-codepoint limit apply to both editor fields. On retry the original payload and key stay bound. A later typed edit survives late ACK.

## Gotchas

Separate genuine target-bearing notice from an arbitrary toast or error. Feedback evidence establishes the binding and state of that feedback.
