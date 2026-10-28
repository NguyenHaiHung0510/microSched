# Kiến trúc hiện hành

microSched là ứng dụng cá nhân một Owner, với FastAPI modular monolith và React PWA cùng origin. Source roots: [backend entry](../../backend/app/main.py), [frontend entry](../../frontend/src/App.tsx), [Dockerfile](../../Dockerfile), [Fly config](../../fly.toml).

```text
Browser / PWA
  React + TanStack Query + Dexie + service worker
       | same-origin JSON / SSE
  FastAPI web routers -> domain services -> SQLModel / PostgreSQL
       |                    |                 |
  OAuth/session/private   Task/Note/etc.    Neon + pgvector
       |
  Mimi supervisor -> context / tools / frozen Confirm -> domain transaction
       |
  configured model gateway (optional per runtime)
```

## Module boundaries

| Layer | Ownership/source |
|---|---|
| HTTP/auth/validation | [web](../../backend/app/web), routers under authenticated API; health and login have explicit public paths |
| Domain/state | [domain](../../backend/app/domain): models, read gates, Task/Note/Calendar/Tracker/Entry/Subscription/reminders |
| Infrastructure | [core](../../backend/app/core): settings, crypto, sessions, DB lifecycle, in-process cron timer |
| Agent | [agent](../../backend/app/agent): conversation/run/event/call accounting, context, tool proposals and atomic confirmation |
| UI | [frontend/src](../../frontend/src): shared shell, screens, component library, query/cache/offline boundaries |

Production builds frontend once and serves its static output from FastAPI; Node is not a production server. One PostgreSQL database is the durable source of truth. There is no parallel SQLite truth, Redis broker or microservice deployment. pgvector is present as a schema capability; its presence does not establish an all-domain retrieval feature.

## Write and refresh flow

Online domain requests pass session and visibility checks, validate typed inputs and use domain transactions. The response/ACK must reflect a durable outcome. Shared query invalidation refreshes readers after a mutation; an uncertain response is not proof of no commit. Existing client IDs, version checks and receipts make retries safe within their specified contracts.

The current outbox admits supported Task/checklist and existing-tracker Entry commands into IndexedDB before projecting an immediate UI result. A worker sends ordered typed commands, reconciles canonical responses and retains unknown/error/authorization/version holds for visible resolution. It has no generic URL queue or direct HTTP fallback when durable admission fails. Its full contract is [offline outbox](../reference/offline-outbox.md).

Service-worker precache, public query persistence and mutation outbox serve different purposes. Private response caches remain volatile under [R6](../auth-brief.md); existing admitted private pending work has the separately approved payload boundary described in the outbox contract. Safe updates preserve active drafts/queued work and require compatible protocol state.

## Background and AI work

The optional in-process cron timer restores reminder schedules from durable rows and signals reload after relevant commits. Fly stays always-on for that timer; DB-free `/api/healthz` probes avoid waking the database. Changing cadence/retry/hosting requires checking finite infrastructure quotas and fallback behavior.

Mimi runs inside the same backend, with encrypted persisted conversation/evidence and explicit server-side authority. Native routing selects providers within configured privacy/precision/price requirements. Model text and retrieved/imported content remain untrusted data. Proposals do not write domain rows; Confirm validates frozen operations and commits effects with receipt/refresh metadata atomically. See [Mimi](../mimi/README.md).

Migration is a separate operation, never an automatic deploy step. Runtime DB access is CRUD-only; schema ownership and recovery are covered in [data model](data-model.md) and [operations](../operations/runbook.md).
