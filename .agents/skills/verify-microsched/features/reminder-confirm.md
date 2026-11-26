# Reminder confirmation deep link

Current source at the [indexed baseline](README.md): `frontend/src/App.tsx:184`, `frontend/src/ReminderConfirmScreen.tsx:65` and `:131`, `backend/app/web/routers/push.py:118`.

## Sub-features

Automatic Entry confirmation on opening a dispatch link, stable retry, missing/stale dispatch and private unlock.

## How to get to it (user POV)

Inspect the same-origin `/reminder-confirm?dispatch=OWN_ID` URL without visiting it in a read-only case. Open an owned dispatch only with a synthetic confirm-write grant. A guest sees public auth with a relative return target before the protected screen mounts.

Freeze a pending owned dispatch and expected Entry delta, plus separate stale/missing, lost-ACK and private locked/unlocked inputs. PIN unlock requires its approved synthetic fixture.

## Driving it in a current synthetic candidate

The authenticated screen sends `POST /api/reminder-dispatch/{id}/confirm` on mount. Retry via `reminder-confirm-retry`, or `private-unlock-submit` after `PRIVATE_UNLOCK_REQUIRED`, repeats the same in-mount Entry ID and occurrence timestamp. See `frontend/e2e/reminder-confirm.spec.ts`.

Oracle: Exactly one Entry for the authorized dispatch after retry/reload, corroborated by canonical/durable state. An invalid or unavailable dispatch creates none. A network failure keeps the retry surface.

## Gotchas

Dispatch tokens stay private. Do not generate production notification, traverse OAuth or alter real PIN.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
