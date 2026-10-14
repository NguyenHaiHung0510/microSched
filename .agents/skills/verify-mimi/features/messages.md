# Messages, provenance and composer

Source: `frontend/src/MimiScreen.tsx:1077` (`mimi-input`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Composer/history, response content/provenance, streaming, copy and send.

## How to get to it (user POV)

Selected synthetic conversation → composer/history → actual assistant message action.

Real prerequisites: Deterministic provider/history/system-policy/language/provenance fixture and separate write/call grant; none installed for first metadata proof.

## Driving it with H14 isolated browser/CLI

mimi-input, message action labels in MimiScreen.tsx; inspect mimi-message-provenance.ts.

Observable oracle: Literal authorized input/output and provenance agree with wire/durable history; no duplicate dispatch; UI stream converges with terminal state.

## Gotchas

Composer visibility does not prove model conversation. No paid provider, real PRIVATE prompt or clipboard action in initial recipe.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
