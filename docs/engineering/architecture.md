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

  miGarden UI -> app adapter -> config / commands / evidence in PostgreSQL
                      ^
  Zone A ESP32 -------+ device exchange (wire v1)
```

## Module boundaries

| Layer | Ownership/source |
|---|---|
| HTTP/auth/validation | [web](../../backend/app/web), routers under authenticated API; health and login have explicit public paths |
| Domain/state | [domain](../../backend/app/domain): models, read gates, Task/Note/Calendar/Tracker/Entry/Subscription/reminders |
| Infrastructure | [core](../../backend/app/core): settings, crypto, sessions, DB lifecycle, in-process cron timer |
| Agent | [agent](../../backend/app/agent): conversation/run/event/call accounting, context, tool proposals and atomic confirmation |
| miGarden | [Adapter](../../backend/app/domain/migarden) owns Zone A config, requests, projections and evidence. The ESP32 owns its clock, safety, budget, local schedule, journal and physical output |
| UI | [frontend/src](../../frontend/src): shared shell, screens, component library, query/cache/offline boundaries |

Production builds frontend once and serves its static output from FastAPI; Node is not a production server. One PostgreSQL database is the durable source of truth. There is no parallel SQLite truth, Redis broker or microservice deployment. pgvector is present as a schema capability; its presence does not establish an all-domain retrieval feature.

## Write and refresh flow

Online domain requests pass session and visibility checks, validate typed inputs and use domain transactions. The response/ACK must reflect a durable outcome. Shared query invalidation refreshes readers after a mutation; an uncertain response is not proof of no commit. Existing client IDs, version checks and receipts make retries safe within their specified contracts.

The current outbox admits supported Task/checklist and existing-tracker Entry commands into IndexedDB before projecting an immediate UI result. A worker sends ordered typed commands, reconciles canonical responses and retains unknown/error/authorization/version holds for visible resolution. It has no generic URL queue or direct HTTP fallback when durable admission fails. Its full contract is [offline outbox](../reference/offline-outbox.md).

Service-worker precache, public query persistence and mutation outbox serve different purposes. Private response caches remain volatile under [R6](../auth-brief.md); existing admitted private pending work has the separately approved payload boundary described in the outbox contract. Safe updates preserve active drafts/queued work and require compatible protocol state.

## Background and AI work

The optional in-process cron timer restores reminder schedules from durable rows and signals reload after relevant commits. Fly stays always-on for that timer; DB-free `/api/healthz` probes avoid waking the database. Changing cadence/retry/hosting requires checking finite infrastructure quotas and fallback behavior.

Mimi runs inside the same backend, with encrypted persisted conversation/evidence and explicit server-side authority. Native routing selects providers within configured privacy/precision/price requirements. Model text and retrieved/imported content remain untrusted data. Calendar in STANDARD uses typed read-only tools against saved data. Owner workspace resolves shared STANDARD history and legacy aliases while preserving conversation rows. Voice v1 adds duplex audio and Calendar reads in the same conversation. Voice v2 can prepare a frozen group of Task changes and use the same execution and undo contracts. Confirm validates source, authority and CAS before committing effects with receipt and refresh metadata in one transaction. With Auto enabled, only eligible reversible Voice v2 groups may commit without the user clicking Confirm. Reconnect and undo use durable receipts. [Mimi](../mimi/README.md) · [Owner workspace](../mimi/owner-workspace.md) · [Voice](../mimi/voice.md)

## miGarden adapter

The app saves versioned desired config and projects the last applied config from verified Controller evidence. START is a preview/confirm request with a bounded grant, and STOP has its own correlated receipt. The ESP32 makes the final local decision. The history and forecast expose their evidence coverage, and web state derives freshness from the accepted snapshot. A failed background read leaves that snapshot in view until its freshness expires. Loss of web connectivity freezes the displayed elapsed time at the last reported value and disables remote START.

The device can negotiate `quiet-health-v1` while retaining the `migarden.zone-a.v1` envelope. Idle waits reduce DB access. Authoritative exchanges retain boot and report checks, and only committed exchanges can acknowledge reports. Optional hourly health stays outside control decisions. See the [adapter contract](../migarden/n01-api.md) and [recovery and sync notes](../migarden/recovery-latency.vi.md).

Migration is a separate operation, never an automatic deploy step. Runtime DB access is CRUD-only; schema ownership and recovery are covered in [data model](data-model.md) and [operations](../operations/runbook.md).
