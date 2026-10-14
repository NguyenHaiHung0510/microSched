# Response feedback and target binding

Source: `frontend/src/MimiScreen.tsx:929` (`mimi-feedback-target`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Helpful/not-good actions, reasons/draft/expected result, acknowledgment and evidence.

## How to get to it (user POV)

Synthetic assistant message → Hữu ích / Chưa tốt action → Mục cần góp ý; select exact message/run/call/receipt.

Real prerequisites: Existing synthetic assistant message/target receipt and version; approved feedback write/oracle; encryption/ack fixture.

## Driving it with H14 isolated browser/CLI

mimi-feedback-target, mimi-feedback-target-snippet, mimi-feedback, mimi-feedback-expected; MimiFeedbackEvidence.tsx.

Observable oracle: Submitted feedback binds the chosen target, persists acknowledgment and prevents draft/target confusion; unsupported supplement remains an unsent draft.

## Gotchas

No real complaint/chat payloads. Positive click can be a write; first metadata case does not exercise feedback.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
