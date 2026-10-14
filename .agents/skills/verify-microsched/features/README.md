# Feature map — verify-microsched

Broad observed top-level source map for exact candidate `aa9d7251cdb506e968a6ffddfbae6767b6987327` at `harness-b-verification/microsched`. This is verification navigation, not product authority or whole-product acceptance. Every row is source-mapped and **NOT_RUN**; no runtime receipt exists in R3. The initial runtime batch still proves only public-home and conversation-metadata respectively. Read each feature for real prerequisites/oracle/gotchas before extending QA.

| Entrypoint / feature | Exact source navigation | Status |
|---|---|---|
| [Public homepage language and login link](public-home.md) | `frontend/src/HomePage.tsx:144` | NOT_RUN |
| [Task tab and task lifecycle](task-calendar.md) | `frontend/src/App.tsx:168` | NOT_RUN |
| [Calendar navigation and event sources](calendar.md) | `frontend/src/App.tsx:108` | NOT_RUN |
| [Notes and reflections](notes.md) | `frontend/src/App.tsx:178` | NOT_RUN |
| [Tracker editors and records](tracker-form.md) | `frontend/src/App.tsx:198` | NOT_RUN |
| [Subscription management route](subscription.md) | `frontend/src/App.tsx:131` | NOT_RUN |
| [Reminder confirmation deep link](reminder-confirm.md) | `frontend/src/App.tsx:131` | NOT_RUN |
| [Reminder center](reminder-center.md) | `frontend/src/App.tsx:139` | NOT_RUN |
| [Private visibility gate](private-gate.md) | `frontend/src/App.tsx:140` | NOT_RUN |
| [Mimi workspace and dock entrypoints](mimi-entry.md) | `frontend/src/App.tsx:137` | NOT_RUN |
| [Session, error and logout shell](session.md) | `frontend/src/App.tsx:44` | NOT_RUN |
| [PWA and visible data freshness](pwa-freshness.md) | `frontend/src/LiveStatus.tsx:43` | NOT_RUN |

Enumeration boundary: observed top-level app routes/tabs/global controls and reachable Mimi workspace/dock entrypoints in the named source. This is a broad inventory, not exhaustive per-field/state QA. Later or hidden/provider-dependent behaviors remain described by prerequisite, not silently accepted. On source changes re-inventory entrypoints and affected recipes; do not treat this old snapshot as current production truth.
