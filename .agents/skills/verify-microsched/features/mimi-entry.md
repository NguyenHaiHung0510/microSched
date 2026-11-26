# Mimi workspace and dock entrypoints

Current source at the [indexed baseline](README.md): `frontend/src/App.tsx:88` and `:195`, `frontend/src/AppNavigation.tsx:54`.

## Sub-features

Workspace, direct `/mimi`, side-chat and capability-off shell.

## How to get to it (user POV)

A synthetic session with `mimi_available` opens **Mimi** from the tab/menu or direct `/mimi`. On another app surface use menu **Chat với Mimi**, the quick-access button, or the guarded **Alt+A** shortcut.

## Driving it in a current synthetic candidate

Use role `tab` **Mimi**, `mimi-dock-open`, `mimi-quick-access` or `mimi-side-chat` as appropriate. Use [Mimi recipes](../../verify-mimi/features/README.md) for workspace, chat and attention cases.

Oracle: The exposed surface opens with the same selected conversation. A capability-off session cannot open the dock or mount the Workspace, and Mimi controls reflect availability. Metadata/navigation needs only an owned synthetic session and owned conversation fixture.

## Gotchas

Freeze the session/capability response per case. Access-priority coverage is in `frontend/e2e/mimi-access-priority.spec.ts`. Sends, decisions, Voice and notification permissions need their own scope.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
