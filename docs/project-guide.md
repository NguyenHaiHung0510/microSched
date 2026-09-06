# microSched — project reading map

Process authority: [harness-policy.md](harness-policy.md). Entry point: [AGENTS.md](../AGENTS.md). Read the relevant subset, not the whole linked collection.

microSched is a single-user personal task/note/calendar/tracker web app and learning project for harness engineering + AI engineering. Public story and shipped/roadmap distinctions: [README.md](../README.md). Predecessor VC_QuanLyThoiGian is reference/rollback material, not an app to modify.

## Sources by question

| Question | Read |
|---|---|
| Queue/accepted scope | [task index](../agent-tasks/README.md), assigned NNN spec, fresh GitHub/runtime receipts |
| Backlog/AI sequencing | [forward spec](forward-spec.md), [owner idea inbox](upgrade-notes-inbox.md) |
| Architecture/hosting/modules/MCP timing | [architecture](architecture-brief.md) |
| Schema/DB/privacy indexes | [concept schema](schema-v1-brief.md), [physical schema](schema-physical-brief.md), [DB decisions](db-and-data-model-brief.md) |
| Trackers/subscriptions/health/money | [tracking](tracking-brief.md) |
| Frontend/PWA/offline | [frontend](frontend-brief.md) |
| UI/interaction/components/QA | [UI](ui-brief.md), [QA](qa-framework.md) |
| Auth/private/AI R1–R7 | [authentication](auth-brief.md) |
| Threat model/repo/CI/release/costs | [DevOps](devops-brief.md), [costs](cost-brief.md) |
| Predecessor data/domain behavior | [migration mapping](migration-mapping-brief.md), [v1 reference](v1-reference.md) |
| Historical rationale/receipts | [session log](session-log.md), [learnings](learnings-applied.md); not current authority |

## Architecture invariants

- One PostgreSQL + pgvector store on Neon; no parallel SQLite/Postgres truths. Python/FastAPI modular monolith, SQLModel/Alembic, UUIDv7, TEXT+CHECK enums; exact rules in schema/architecture briefs.
- React/TypeScript/Vite static SPA/PWA; one production Python process serves API and frontend. Node build-time only. No speculative microservices/Redis/Celery or premature MCP server.
- Established Fly topology is one continuously running machine in sin; re-query fly.toml/live system for exact current state. Old cost/model tables are not current evidence.
- Markdown for prose, structured columns for queryable meaning. Store full values, truncate only for display; entities/timestamps stay in schema briefs.
- Google OAuth allowlist, server-side opaque sessions and private PIN display gate; encryption master key stays app-held. Read auth R1–R7 before AI/private work; encrypted columns never enter pgvector/FTS.
- AI sequences foundation → read-only retrieval → narrow writes with confirmation/audit → finance. Existing offline seams do not mean full outbox shipped. Consult current specs/code, not old counts.
- No automatic Alembic on deploy. Migration has a separately approved lane and real schema evidence beyond alembic current.

## Legacy-data boundaries

Old app `C:/Users/os/Desktop/old_prj/VC_QuanLyThoiGian`, its main branch and SQLite `C:/Users/os/Desktop/Tools/VC_microSchedule_home/todo.db` stay read-only rollback references. Legacy migration source was local Postgres `microschedule_v2`; after cutover, old migration-era prose is neither current production truth nor permission to access data. Reconcile the assigned migration contract before touching stores. Host Postgres superuser serves other projects: never reuse it for this app; use limited roles.

The parent strategy workspace is `../../hoc_he_2026` relative to repository root; consult only for broader learning/strategy work, not routine implementation. Old-store inventory scripts do not grant real-data access.

## Knowledge hygiene

Status belongs in task index/receipts, domain decisions in briefs, history in session logs. Do not copy everything into AGENTS/CLAUDE. Memory locates sources; verify drifting facts from current code/config/runtime. Locked meaning changes need Owner approval; dated observations should not coexist as contradictory current truths.

Public contributors do not need private harness-core: mandatory project rules are available in this repository.
