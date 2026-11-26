# Mimi Voice v1 and v2

Current source at the [indexed baseline](README.md): `frontend/src/MimiScreen.tsx:1322`, `frontend/src/MimiVoiceDock.tsx:25`, `frontend/src/MimiVoicePreferences.tsx:29` and `backend/app/web/routers/mimi_voice.py:67`. [Voice contract](../../../../docs/mimi/voice.md).

## Sub-features

Voice in an owned STANDARD conversation, mic/audio lifecycle, read-only Calendar in v1, and the separately gated v2 proposal/fast-apply and receipt-bound undo.

## How to get to it (user POV)

Open an active STANDARD conversation in Workspace or dock. When `voice_enabled` is reported, the composer has **Giọng nói**. The hub exposes the Voice preference only with `voice_v2_enabled`. The button is gated on online, conversation and run/decision state.

## Driving it in a current synthetic candidate

Use `mimi-voice-start`, `mimi-voice-dock`, `mimi-voice-mute`, `mimi-voice-stop`, `mimi-voice-action` and the hub’s switch in `mimi-voice-preferences` where applicable. Bind the approved no-egress socket/transport double, media capability, owned STANDARD session, saved Calendar fixtures and v1/v2 capability gates. Observe `POST /api/mimi/conversations/{id}/voice-ticket`, the same-origin `/api/mimi/conversations/{id}/voice/{run_id}` WebSocket, the scoped Stop POST and the terminal receipt. `GET/PATCH /api/mimi/voice-preferences` reads and saves the explicit fast-apply preference, with CSRF for writes.

Oracle: v1 reads only saved Calendar and preserves the text draft. v1 mute releases and can reacquire the mic. v2 mute ends the call. v2 can prepare a whole preview or apply/undo only a server-eligible exact set under the current grant. A frozen preview and a durable applied receipt have distinct meanings. Check ticket linkage, stop/cleanup, stale/unknown reconciliation and no duplicate commit with `frontend/src/mimi-voice.test.ts` and `backend/tests/test_mimi_voice_v2.py` / `backend/tests/test_mimi_voice_v2_pg.py`.

## Gotchas

Ticket issuance, voice socket/media use, preference edits and synthetic domain writes require a current approved synthetic setup. Keep the voice socket on the no-egress transport double. The Google model route described in the Voice contract is **BLOCKED** for Agent execution under the current Owner model policy across transports, including previously granted pins. Synthetic Voice and physical mic/audio checks remain **NOT_RUN** for this baseline.
