# Application security baseline — microSched and Mimi

Owner-confirmed scope, 2026-10-15. This brief describes the current risk model; it does not change authentication, permissions or product behavior. Read [auth-brief.md](auth-brief.md) for established controls and [operations runbook](operations/runbook.md) for delivery responsibilities. Use the current source and task grant for what is actually shipped.

## Users and assets

microSched and its Mimi experience currently have one intended user: the Owner. Do not assume a multi-tenant service, organization roles or a hostile second legitimate customer. Protect the Owner's personal content, account/session, private fields, data integrity, service availability and finite provider/infrastructure resources. Public source code is intentional; secrets, real account identifiers and personal production payloads are not test fixtures or public evidence.

The Owner intentionally attacking their own isolated app is not a default threat scenario. A stolen/abused session, an authenticated browser visiting a hostile site, a leaked key, accidental destructive action, crash or data corruption can still harm the Owner. Authentication is an important boundary, not the only boundary.

## External input stays untrusted

| Source / crossing | Relevant failure to assess when the feature exists |
|---|---|
| Anonymous requests, OAuth redirects and browser-origin requests | Access-control/session failures, unintended authenticated actions, credential or personal-data exposure, disproportionate resource use |
| Calendar/ICS imports or feeds | Malformed/oversized input, parser/resource failures, unexpected values or links, unsafe rendered content and data corruption |
| User-selected file, URL or external content for Mimi, including future features | Unsafe parsing/rendering, external requests crossing network boundaries, hidden instructions and unintended data/tool access |
| Model output, retrieved text and tool/provider responses | Content/instructions mistaken for authority, unsupported writes, unsafe rendering, data disclosure or unbounded paid work |

A file the Owner uploads or a URL they choose can contain content written by someone else. Login, import, persistence and inclusion in a model prompt do not make that content trusted. Treat it as data, preserve provenance and validate it at the actual parser/render/network/tool boundary. Future sources in this table are review triggers, not claims that those features already exist or grants to implement them.

## Proportionate assessment and checks

Trace controlled input -> processing -> protected data/action/resource and the actual reachable harm. State existing mitigation, evidence and uncertain preconditions. Prioritize a reproducible personal-data leak, unauthorized access/action, crash/corruption or material resource cost over generic enterprise hardening with no relevant scenario. A dependency advisory is a lead; distinguish build-time/deployed reachability from severity alone. Single-user scope is never a reason to remove a required gate or dismiss externally supplied input.

Reuse targeted auth/import/tool-policy regression tests, existing secret scanning, CodeQL, dependency checks and the project QA contract when applicable. A new hard guard needs an intended failing case, restored passing case and proportional regression evidence. Do not add a new scanner/service, heavy pipeline, broad rate cap or enterprise role system solely to complete a checklist.

Review is read-only unless the actual task grant includes the proposed fixes. Production abuse/load/fault tests, real data, keys, consent scopes, security/permission changes and migrations retain their existing Owner-only boundaries. Synthetic local evidence is not a penetration test, whole-app certification, physical-device acceptance or production proof.

Revisit this baseline if users, public exposure, storage, providers, tools or external input sources change. Put current feature contracts in their existing briefs/tasks; do not copy private discussion or create a second requirement ledger here.
