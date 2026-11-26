# Messages, provenance and composer

Current source at the [indexed baseline](README.md): `frontend/src/MimiScreen.tsx:1028` and `:1292`, `backend/app/web/routers/mimi.py:370`. Runtime **NOT_RUN**.

## Sub-features

Unicode draft, send/stream, terminal state, provenance and reload. Optional STANDARD Calendar text reads use the same composer.

## How to get to it (user POV)

In Workspace or side-chat select an owned STANDARD conversation. Use **Nhắn Mimi**, then **Gửi** only for the frozen synthetic text and admitted transport.

## Driving it in a current synthetic candidate

Use `mimi-input`, `mimi-messages`, `mimi-pending-answer` and `mimi-run-outcome`. Bind a no-egress SDK double, current language/policy/history, and allowed `POST /api/mimi/conversations/{id}/messages/stream` plus run events. Compare literal input, owned request/event sequence and durable message IDs before/after reload.

For Calendar, bind the opt-in `MIMI_CALENDAR_READ_ENABLED` mode and saved Task/Event/annotation dates, mixed visibility and VN day boundaries. The [Calendar contract](../../../../docs/mimi/calendar-read.md) and `backend/tests/test_mimi_calendar_pg.py` cover coverage, provenance and fresh reads on later turns/Resume. Client-only pending state is outside that saved read.

## Gotchas

Synthetic stream/receipt evidence does not establish live language, reasoning or Calendar grounding. PRIVATE is outside the current STANDARD capability.
