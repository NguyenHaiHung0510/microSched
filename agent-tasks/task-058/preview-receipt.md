# Task 058A local interaction-shell preview receipt

Date: 2026-09-17 17:45 +07:00
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
- 058A.1 provides four switchable states: healthy, long-running, provider/cache
  degradation/recovery and Owner queue. They exercise elapsed time, tool stages,
  optional public reasoning, health, pending work and adversarial conversation
  list states instead of merely filling cards.
- The usage panel visibly marks synthetic data and exercises today, 7/30 days,
  3/6 months and 1 year. Live integration will expose only ranges supported by
  the direct purchasing-provider API; it will not invent older billing data.
- Runtime settings preview an adjustable 30-minute lease, four accumulating
  activity-detail levels and one confirmed reset action for the group.
- Three Owner-selected visual boards are preserved in the main checkout's
  ignored `agent-tasks/temp/mimi-design-references/` directory with SHA-256
  receipts. Japanese board copy is explicitly excluded from product approval.

## Observed checks

| Check | Result |
|---|---|
| `npm run lint` | PASS, exit 0 |
| `npm test` | PASS, 21 files / 148 tests |
| `npm run build` | PASS, including apple-icon and PWA surface guards |
| `npx playwright test e2e/mimi-p1.spec.ts` | PASS, 4/4: Control Center + preview/receipt and side-chat/no-overflow on desktop 1280 and mobile 390 |
| Live local preview | PASS: `http://127.0.0.1:5158/` returned 200; synthetic API reported `mimi_available=true` |
| Browser interaction | PASS: healthy → long-running scenario, elapsed timer/tool stages/reasoning, 1-year usage range, Settings and reset confirmation were observed in a real headed Chromium session |

The first focused E2E rerun after adding `GET /api/mimi/preview` produced 2 PASS
and 2 FAIL because the old route fixture treated every Mimi request other than
`GET .../conversations/current` as a write and required CSRF. The fixture was
corrected to return 404 for the optional preview GET in non-synthetic tests; the
immediate rerun passed 4/4. This RED → GREEN receipt is retained rather than
rewriting the first run as PASS.

Windows sandbox initially blocked Vite/Vitest native child-process loading with `spawn EPERM`; the same exact checks passed outside the restricted sandbox. This is recorded as an execution-environment distinction, not a product failure.

## Preview endpoints

- UI with hot reload: `http://127.0.0.1:5158/`
- Synthetic API: `http://127.0.0.1:8058/`
- Both bind to loopback only. State is in memory and disappears when the preview process stops.

## Evidence boundaries

- UI preview and focused frontend regression: **PASS**.
- Conversation management API/schema, provider streaming, server-owned
  background execution, adjustable lease/cancel/resume/reconcile, OpenRouter
  analytics integration, adaptive route policy and live-model path:
  **NOT RUN / not implemented in 058A.1**.
- Full backend suite, migration QA, physical device, production and Owner dogfood: **NOT RUN**.
- Owner approval of the product shape remains the gate before 058B/058C.
