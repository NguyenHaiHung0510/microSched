# Task 058A local interaction-shell preview receipt

Date: 2026-09-17 12:27 +07:00
Branch: `feat/058-mimi-dogfood-recovery`
Base: `origin/develop@563b0badae0dc7ba3fb8c0e9b6852a8bc4e8dc90`
Result: **READY FOR OWNER UI PREVIEW — not runtime/live-provider acceptance**

## Observed implementation

- Mimi top-level tab lands on `Mimi Control Center` Overview, with real preview sections for Overview, Activity, Conversations and Settings.
- Orbit, Memory and Skills are described only as capability-gated roadmap items; they are not presented as active empty modules.
- Authenticated shell has a separate `Chat với Mimi` launcher.
- Desktop uses a sticky bounded right-side panel while the microSched screen reflows; mobile uses a full-height dialog sheet.
- The shared conversation view retains frozen preview, confirm/reject, receipt and feedback UI. Browser connectivity is not labelled as provider health.
- A loopback-only in-memory synthetic API makes the UI hot-reload preview independently testable without Task 056/057 runtime, real data or provider keys.

## Observed checks

| Check | Result |
|---|---|
| `npm run lint` | PASS, exit 0 |
| `npm test` | PASS, 21 files / 148 tests |
| `npm run build` | PASS, including apple-icon and PWA surface guards |
| `npx playwright test e2e/mimi-p1.spec.ts` | PASS, 4/4: Control Center + preview/receipt and side-chat/no-overflow on desktop 1280 and mobile 390 |
| Live local preview | PASS: `http://127.0.0.1:5158/` returned 200; synthetic API reported `mimi_available=true` |
| Browser interaction | PASS: Task → Mimi Control Center → global side-chat → create STANDARD conversation → send synthetic Task request → frozen `task.create.v1` preview appeared |

Windows sandbox initially blocked Vite/Vitest native child-process loading with `spawn EPERM`; the same exact checks passed outside the restricted sandbox. This is recorded as an execution-environment distinction, not a product failure.

## Preview endpoints

- UI with hot reload: `http://127.0.0.1:5158/`
- Synthetic API: `http://127.0.0.1:8058/`
- Both bind to loopback only. State is in memory and disappears when the preview process stops.

## Evidence boundaries

- UI preview and focused frontend regression: **PASS**.
- Conversation management API/schema, provider streaming, seven-minute deadline/cancel/reconcile, adaptive route policy and live-model path: **NOT RUN / not implemented in 058A**.
- Full backend suite, migration QA, physical device, production and Owner dogfood: **NOT RUN**.
- Owner approval of the product shape remains the gate before 058B/058C.
