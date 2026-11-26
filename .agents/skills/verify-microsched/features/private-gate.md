# Private visibility gate

Current source at the [indexed baseline](README.md): `frontend/src/PrivateGate.tsx:273`, `frontend/src/AppNavigation.tsx:56`, `backend/app/web/routers/private.py:59`.

## Sub-features

Locked/unlocked badge, unlock/expiry/lock and PIN-change entrypoint.

## How to get to it (user POV)

Synthetic header → `private-unlock-open`. **Ứng dụng** → `private-pin-change-open` is the separate PIN form entry. Inspect locked views before any supplied synthetic PIN.

Real prerequisites: Frozen private rows, server session/expiry and an already approved synthetic PIN; changing real auth/PIN remains out of scope.

## Driving it in a current synthetic candidate

Use `private-badge`, `private-unlock-open`, `private-pin-input`, `private-unlock-submit` and `private-lock-now`. Observe `POST /api/private/unlock` and `POST /api/private/lock` on the explicitly granted synthetic paths. See `frontend/e2e/private.spec.ts` and `backend/tests/test_private_api.py`.

Oracle: Private rows/controls disappear at lock/expiry, including on a late response or another tab. Owned public draft stays available. API/session gate and visible state agree. Retain content-free evidence for sensitive cases.

## Gotchas

Screenshots cannot expose real account identifiers; no settings/security boundary changes. Initial smoke does not exercise unlock.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
