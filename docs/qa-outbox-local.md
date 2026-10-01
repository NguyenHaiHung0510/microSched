# Task 017: dedicated local production PWA QA

This lane runs the real production React build with its service worker enabled, against an authorized synthetic local API/database. The ordinary `npm run e2e` lane continues to run its existing CI tests with service workers blocked. Browser emulation is not a physical iPhone receipt.

Before running, verify the backend process, its source commit, database name/port, and authorized synthetic session. A loopback URL alone does not prove the database is synthetic. Do not point this lane at Neon, Fly production, or a real browser profile. Keep private data locked unless an authorized operator is present to enter the existing synthetic PIN; tests never read or supply that PIN.

Run from `frontend` in PowerShell, after committing product/build inputs:

```powershell
$env:QA017_SYNTHETIC_ACK = '1' # only after verifying the synthetic process/DB/session
$env:QA017_BACKEND_URL = 'http://127.0.0.1:8003'
$env:QA017_BACKEND_SHA = '<verified backend commit>'
$env:QA017_PORT = '4174' # reserve an unused local port; the runner never reuses a server
$env:QA017_HEADLESS = '1' # omit for private cases with the human operator present
npm run e2e:outbox-pwa -- --grep 'J[1-4] |N[1-4] |P1 |P3 '
```

The package command builds once, snapshots `dist` under `output/outbox-pwa/artifacts/builds/<HEAD>/dist`, records every file hash, and starts an isolated preview. It refuses dirty product/build inputs or a different build at an existing immutable destination. Supply a new `QA017_RECEIPT_DIR` if an existing snapshot differs; preserve the old evidence. The preview refuses non-loopback backend URLs, missing synthetic acknowledgment, a mismatched backend commit, or a database that is not ready.

Each case uses a fresh browser context, a unique run tag, one worker, zero retries, and stop on the first failure. The J cases cover offline reload, dependent task/checklist writes, cross-tab Web Locks, and a real server commit with a lost browser response. N cases inject bounded browser storage/lock faults before boot; their API traffic remains real. P1/P3 cover tracker dependency order, a real validation rejection, suppressed children, and independent public progress. P2/P4 require a headed browser and the human operator for the existing private gate. Missing private, physical-device, or production receipts stay `NOT_RUN`; do not count list-only enumeration as executed QA.

Set `QA017_VIEWPORT=390x844` for the mobile viewport pass. Artifacts contain commands/run tags, Playwright JSON, exact API status/ID receipts, queue UUID/state/digest observations and screenshots. Task cleanup is restricted to the exact synthetic IDs created in that run; a 404 cleanup response must be reported, not counted as a successful delete. A pending or outcome-unknown local row is not a server acknowledgment. Preserve unexpected rows rather than clearing storage to make the test pass.

The runner does not start or migrate the database, read `.env`, modify PINs, register real push devices, call model providers, or deploy. Production HTTPS and the Owner's physical iPhone are separate acceptance layers in `agent-tasks/017-qa-offline-outbox.md`.
