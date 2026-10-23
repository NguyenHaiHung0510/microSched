# Task091 — bounded offline Task/checklist + Entry recipe

Current phase/source/acceptance come from Task091 and private PM grant/freeze. First source base f7c19131cb9b831c1d0697ceef00557da1f5831e; build/runtime freeze must supply actual new candidate. This recipe is M1 navigation, never a runtime PASS or extra actor authority.

Owner namespace r2-091-20261023-microsched, retained same-name-db volume; preview microsched_r2_091/test microsched_r2_091_tests; PG55491/API8001/production4174. Dev5174 reserved, not production SW evidence. Provider/Mimi/cron OFF. Runtime secrets stay ignored in .local/r2-091/microsched/runtime.json; reviewers use bound synthetic auth/navigation recipe and never print credential files.

Owner source guard / lifecycle:
```powershell
backend/.venv/Scripts/python.exe .agents/skills/verify-microsched/scripts/r2_sandbox.py --source <absolute-091> --binding <current-binding> guard
# Separate already-granted owner effects, never reviewer Doctor:
# Retained091: no init-db/reseed/migration. Explicit runtime owner only may start
# the exact retained labelled container after ownership/image/volume/ports checks.
# start-app requires current production build; stop-app retains DB/volume.
```

Owned synthetic browser readiness (requires its own execution grant):
```powershell
node .agents/skills/verify-microsched/scripts/r2_browser.mjs --output-root <absolute-own-granted-output-root>
```

The CLI creates a fresh isolated context, verifies the selected synthetic role, waits for actual controlling SW, captures actual viewport and sanitized queue/SW/readyz state, then logs out/closes only its context. It neither asserts the nine product outcomes nor mutates source/DB fixture/helper. Imports support one same-origin context with two pages, real readonly IDB metadata, scoped PWA controller and bounded native dispatchTouchEvent. Reuse proven direct1.62.1 cached API; do not add a CLI status framework.

Journey imports: waitForQueueCount(page,count,{timeout}), readCanonical(page,path) and captureWire(context). Queue polling requires an existing supported store; a missing store is not ACK. Assert response status before reading DTO fields. Context wire receipts include method/path/status/failure without bodies/cookies/identity; stop the collector before handback. Inspect queue and actual PG postconditions before retry. navigator.onLine alone does not certify the Playwright offline setting after reload.

For physical-row receipts use the frozen container/DB plus schema-qualified microsched tables inside BEGIN READ ONLY/COMMIT; bind validated synthetic case UUIDs from the current manifest. Never infer SQL persistence from an API mock or projected DTO, and never run lifecycle/fixture setup from a reviewer probe. Database URLs/role passwords stay in ignored state and are not output arguments. The owned Docker local socket psql transport uses the declared database without a password-bearing URL.

| Case | Required independent boundary |
|---|---|
|Q1|Durable offline Task+initial children and existing-tracker Entry; public reload; reconnect stable IDs/original time|
|Q2|Actual API/PG commit + lost ACK, predecessor order and shared429/503/network pacing|
|Q3|Two pages/same IDB/WebLocks, crash recovery and one transport|
|Q4|Actual IDB admission abort/open failure, draft retained and no HTTP fallback|
|Q5|Unclaimed create semantic-tree cancel; claimed/unknown/ACK durable compensation|
|Q6|Lock/late ACK/principal/auth and authorized tombstone/private machine codes; no canonical private cache|
|Q7|Pure Task/calendar/count/Entry projections, dedup and honest pending/last-confirmed aggregates|
|Q8|Real SW update with dirty draft/pending V1; unknown format/capability holds; no clearing/unregister|
|Q9|Declared synthetic100 admissions with p50/p95/failure/sample machine/build/method evidence|

Use actual PM fixture/oracles/capabilities; builder self-check is separate. Missing physical iPhone/Safari/provider/production evidence stays NOT_RUN. No runtime or independent outcomes transfer from R1/017/069. Future domains remain whole-batch work.
