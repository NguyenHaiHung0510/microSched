# Session, error and logout shell

Current source at the [indexed baseline](README.md): `frontend/src/App.tsx:208`, `frontend/src/outbox/core.ts:123`, `frontend/src/AppNavigation.tsx:58`, `backend/app/web/routers/auth.py:244`.

## Sub-features

Checking/guest/error states, retry, allowlisted login link and logout.

## How to get to it (user POV)

Fresh guest → `/home` or a protected deep link. Existing local synthetic auth is `GET /auth/dev-session` with `APP_ENV=local`, loopback and the owned session store. Signed in → `app-menu-open` (**Ứng dụng**) → **Đăng xuất**.

Real prerequisites: Current owned local auth/DB and a separate session fault fixture for network/unknown cases. Use a disposable profile without real OAuth.

## Driving it in a current synthetic candidate

Observe `GET /api/me` and `POST /auth/logout`. On session fault outside `/home`, scope the **Thử lại** button to the error alert. The public link is inspect-only. Use the menu’s **Đăng xuất** button for logout.

Oracle: Guest/error never mounts protected data. Successful logout invalidates the owned session and removes the authenticated shell/selected Mimi conversation. A lost logout response shows unknown server status. An authoritative domain 401 returns to guest and holds pending work. PIN-specific failure stays in the private flow.

## Gotchas

The dev-session path proves synthetic session navigation and logout. For OAuth admission, use the separate mocked callback cases in `backend/tests/test_auth.py` for allowed, unlisted and unverified identities and account-selection policy. On this baseline those tests and the real browser/account chooser are **NOT_RUN**. Do not include email or cookies in evidence. Use a separate frozen scenario for network faults.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
