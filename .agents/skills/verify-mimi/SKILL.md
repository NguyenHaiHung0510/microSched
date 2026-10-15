---
name: verify-mimi
description: "Verify Mimi conversation UI metadata on the exact H14 clean 680b7f9b synthetic candidate without paid live-provider calls; map other flows honestly."
---
# Mimi verification

Status: ACTIVE for the observed H14 STANDARD conversation-metadata flow, T1 technical acceptance 2026-10-15: independent attempt2 PASS 4/4, zero blocked, logout/context close observed. Runtime source exact 680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37 in Main-owned harness-b-mimi-qa; NOT latest Owner product acceptance. This map proves 1/12 entrypoints,11/12 NOT_RUN; combined maps 2/24 proved, 22/24 NOT_RUN. Skill/helper delivery source is separate. Closed-rail handling is source-supported; actual case observed it already open. No conversation/provider-quality/full-product claim.

Evidence locator: private H14-N1/R9 final-grouped-retest-handback, mimi-attempt2/receipt.json, original before/after pixels, final-runtime-cleanup and R6 final-technical-signoff. This status update does not rewrite the executed freeze.

## Launch

H14 isolated runtime only, Main process owner. Read [resource/runner contract](../../../docs/harness-b-verification.md) and reserve shared ports8000/5173/55456 sequentially. No legacy P0 volume/profile/Neon/.env. Run from the exact source root with its prepared backend Python:

```powershell
& backend/.venv/Scripts/python.exe .local/h14-night/runner/h14_sandbox.py --source . --binding .local/h14-night/binding.json --lane mimi start
```

Main first copies the two frozen helpers to `.local/h14-night/runner` and this lane's reviewed binding to `.local/h14-night/binding.json` in the exact QA checkout. Verify copied helper hashes against the review manifest. This ignored scaffolding is setup, not a product source change. Run the concrete commands from that exact root. The live Mimi snapshot need not receive project source writes. It reuses the inspected `scripts.mimi_sandbox` with isolated H14 identity, labeled volume and new .local/h14-night state; refused ownership never triggers reset/delete. Bootstrap migrations/seeds touch only the newly owned DB. Live provider false; no app paid calls. Wait for exact readyz.commit + db=up, frontend usable, fixture verification and owned PID/container status. No automatic startup in this skill; the named historical flow is observed, while a changed/new candidate needs its own reviewed binding and lifecycle proof. Health/readiness waits inside the established driver are technical operation bounds, not a task termination deadline.

## Doctor

Run `& backend/.venv/Scripts/python.exe .local/h14-night/runner/h14_sandbox.py --source . --binding .local/h14-night/binding.json --lane mimi status` and the same command ending `verify` before the first drive and after a surprise. Require exact source manifest/head, task identity, container/image/mount/loopback bindings, all backend/frontend readiness booleans and fixture verification. Status alone is not a grant to reuse a listener. Frozen source/build/config is checked at startup and before/after the batch; cases refer to it. Doctor is read-only; verify queries only the task-owned synthetic DB. Never read/log runtime.json generated credentials.

## Drive

First approved end-to-end feature: new conversation, rename, reload and reopen to prove metadata persistence; no send/confirm/provider call. Use the same absolute helper path, source Mimi snapshot and lane mimi. Other mapped flows remain NOT_RUN.

## Evidence

One canonical receipt per case: frozen source/binding/lane, ordered real user actions, actual viewport, complete assertion outputs, required sanitized screenshots, visible and durable result, request/call counts, cost/timing and unknowns. T3 claim and T1 acceptance remain separate; the named final R9 flow is T1-accepted, unrun mapped flows are not. Source-map NOT_RUN for other features; no whole-app/device/live-provider claim. Main cleanup is observed for this run and evidence survived; recheck survival in each new run. No private identities/profile screenshots or .env/runtime secrets.

## Cleanup

Main uses `& backend/.venv/Scripts/python.exe .local/h14-night/runner/h14_sandbox.py --source . --binding .local/h14-night/binding.json --lane mimi stop`; inherited driver checks exact recorded PID ownership and labeled container. No process-name kills, no deleting volumes/user work. This first H14 runtime closeout retains the task-owned labeled volume/container/data for audit; Main handles separately authorized disposal after confirming receipts survive. Required evidence stays in the private task receipt folder outside .local. Log out of app where login was used, close only owned tab/context. Stop after failed attempts too, with exact ownership; failure does not authorize killing another listener.

## Helpers

`scripts/h14_sandbox.py` is a task-owned namespace/ownership adapter over existing code; executable with the prepared backend Python, invocation above. `scripts/drive_feature.mjs` runs only the chosen mapped proof with an isolated bundled Chromium; invocation:

```powershell
node .local/h14-night/runner/drive_feature.mjs --source . --binding .local/h14-night/binding.json --lane mimi --receipts FRESH_PRIVATE_RUN_DIRECTORY
```

Do not run before the runtime-plan freeze/independent runner review and Main startup. Each call reserves a new, nonexistent private receipt directory; retry uses a new directory and references the preceding attempt. Preflight failure writes a canonical BLOCKED receipt before exit. The script requires an already-ready exact owned runtime and allows only HTTP 127.0.0.1:5173 and the documented per-lane methods/routes; all other ports/protocols/routes and WebSocket connections are denied. Existing browser CLI can drive other mapped features manually by actual role/testid selectors under the same ownership/freeze. No NPX network required; Main has observed cached CLI0.1.22 and Chromium151 capability. Capability handshake is not project proof.

For a new authorized candidate follow owner-pstack maintenance: select current source/head/files, new binding/task namespace/allowlisted wrapper and affected recipes; never weaken the dated H14 guards. Read [feature map](features/README.md); generation/maintenance never grants product repairs or paid live-provider calls. Preserve independent QA and project approval/data boundaries.
