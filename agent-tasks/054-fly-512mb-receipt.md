# Task 054 — Fly 512MB delivery receipt

**Status:** canonical configuration and guard delivery in progress.
**Owner authority:** explicit 2026-09-09 approval to raise microSched Fly RAM to 512MB, retain 512MB swap, merge the scoped canonical update into `develop`, and use the ordinary deploy route. No migration, volume, new machine, database or cleanup is authorized.

## Live scale receipt — before canonical deploy

| Field | Observed result |
|---|---|
| Time | 2026-09-09 09:42 UTC |
| App / machine | `microsched` / `d8d9564b42e9e8` |
| Topology | Exactly one started, healthy Machine in `sin` |
| Compute | `shared` CPU, 1 CPU, **512MB RAM**, **512MB swap** |
| Restart | Expected short Machine restart; new instance `01M22RR44CM4170VBGN93KWH61` |
| Health | Fly service check passing |

The first `flyctl machine update` received no API response; a read-back confirmed no state change before one retry. The retry completed successfully. This receipt does not claim an OOM-free outcome, p95 behavior, CI, deploy, production readiness, physical-device acceptance or a current invoice amount.

## Canonical guard scope

- `fly.toml`: one `shared`/one-CPU VM at 512MB and top-level 512MB swap.
- `backend/tests/test_fly_config.py`: exact RAM, swap and single-Machine topology guards.
- `docs/architecture-brief.md` and `docs/cost-brief.md`: current 256MB/only-after-OOM statements superseded by the Owner decision; historical cost figures remain labeled as planning estimates.

The final PR/merge, exact-head CI, ordinary deploy and `/api/readyz` (`commit` plus `db=up`) receipts are appended only after observation.
