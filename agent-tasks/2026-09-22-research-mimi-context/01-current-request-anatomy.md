# B00 — Anatomy of the current Mimi model request

Status: **RESEARCH ONLY — no runtime change, API call, provider call, or eval**

Evidence date: 2026-09-22. Inspected worktree is
`C:\Users\os\.codex\worktrees\mimi-context-research-2026-09-22\microsched`,
`HEAD=a4c7e81`, with local `origin/develop` at the same SHA. Only the assigned
research folder is untracked. This is source/spec inspection, not a runtime or
production receipt.

Labels: **FACT** = observed source/document; **INFERENCE** = conclusion from it;
**PROPOSAL** = discussion direction, not a decision; **OPEN** = unresolved or
not evidenced.

## 1. Entry point and run envelope

- **FACT** — `POST /api/mimi/conversations/{conversation_id}/messages` validates
  `MessageCreate` and calls `send_message`; the streaming sibling creates a
  server-owned worker and observes durable SSE events
  (`backend/app/web/routers/mimi.py:194-266`). Both state-changing endpoints
  require Mimi availability and CSRF dependencies.
- **FACT** — `MessageCreate` bounds client ID to 160 chars and content to 12,000
  chars, rejects blank input, and accepts `auto` or `revise_pending_preview`.
  Revision requires both pending change-set UUID and 64-hex digest
  (`backend/app/agent/service.py:58-80`). Same client ID/same content is
  idempotent; changed content and stale expected generation conflict
  (`service.py:622-641`).
- **FACT** — each accepted run receives server run/task UUIDs, current generation,
  deadline and an `ExecutionLease` with `task.create.v1` and
  `task.read.standard.v1`, `max_turns=1`, `max_tool_calls=1`, cost cap zero,
  STANDARD sensitivity and Task source versions
  (`service.py:695-730`; `contracts.py:37-59`).
- **FACT** — defaults are real chat/live provider disabled, preview TTL 15 minutes,
  deadline 1,800 seconds, exact route, low reasoning, context setting 131,072,
  output setting 4,096 and ZDR required (`backend/app/core/settings.py:85-106`).
  Live settings require key/model/price and exact provider/quantization (or
  adaptive allowlists), and bound context/output/TTL/deadline
  (`settings.py:213-260`).
- **FACT** — owner identity and provider session ID are server-side keyed opaque
  digests (`service.py:126-141`); no credential value was read or recorded.
- **INFERENCE** — the lease is backend authority, not a typed authority block in
  the provider message. Model-visible authority is prose/data; backend checks are
  the actual security boundary.

## 2. Exact current request assembly

At the live-provider branch `send_message` builds one system message, bounded
provider history, and the current user turn (`backend/app/agent/service.py:767-799`):

```text
[
 {role: system, content: inline_policy + owner_now + reserved_task_id
     + json(current_standard_tasks) + json(previous_pending_operations)},
 ...provider_history,
 {role: user, content: current_user_text}
]
```

### Policy/system text

- **FACT** — policy is an inline Python string, not a `MIMI.md` loader. It says
  Mimi is a microSched assistant, defaults user-facing language to Vietnamese,
  uses text for greetings/questions/insufficient data, forbids a tool call for
  greetings or unclear Task intent, requires only a Task title, permits at most
  one STANDARD proposal, forbids self-execution, and describes revision of a
  pending preview (`service.py:769-786`).
- **FACT** — it injects Asia/Ho_Chi_Minh current timestamp, relative-date rule,
  server-reserved Task UUID, current Task JSON and prior-preview operation JSON
  (`service.py:787-795`).
- **FACT** — current contract 04 puts core personality/security policy in
  read-only `MIMI.md` in the Git/Docker image (`04-spec-hop-nhat-mimi.md:1-16,
  44-52`).
- **INFERENCE** — current inline policy is a narrow P1 Task policy, not complete
  product policy for private taint, context manifest/meter/compaction, source
  trust, attachments, memory, skills, jobs or multi-domain tools.
- **OPEN** — Owner's research note says no final system prompt/context
  architecture is approved (`agent-tasks/2026-09-22-research-mimi-context/00-owner-decisions.md`).

### History

- **FACT** — `_provider_history` selects only encrypted `user`/`assistant` rows,
  newest first, at most 24 messages and 65,536 stored bytes; it stops before a
  whole message would exceed the byte bound and returns chronological order
  (`service.py:404-446`). System/tool/event/provider/change-set rows are not
  included; current user text is appended separately. Canonical ordered messages
  remain in the ledger (`backend/app/agent/models.py:96-135`).
- **INFERENCE** — whole-message cutoff avoids partial text, but there is no
  context frontier, omission reason, manifest, meter, checkpoint or compaction.
  This does not by itself satisfy 04's no-silent-truncation/B-first contract
  (`04-spec-hop-nhat-mimi.md:27-30, 250-257, 276-293`).
- **OPEN** — no tokenizer/count-method receipt is present. History uses UTF-8
  bytes; provider preflight later compares UTF-8 bytes with a token setting.

### Domain context

- **FACT** — `list_standard_tasks` reads non-deleted `is_private=false` Tasks,
  ordered by updated time/ID, and returns ID/title/status/priority/due fields,
  source version and `microsched.task.standard.v1` provenance
  (`service.py:581-607`). The direct context endpoint permits 1–25/default 10,
  but model path always asks for 10 (`routers/mimi.py:379-385`; `service.py:699`).
- **FACT** — run stores `task:<id> → updated_at` source versions and emits
  `context.tasks_read` with count and `private_allowed=false`
  (`service.py:699-743`). No Notes, Calendar, Tracker, Subscription, reminder,
  attachment, memory, skill, report or job context is assembled. There is no
  provider-visible read tool despite the lease capability.
- **INFERENCE** — this is a deliberate P1 boundary, not proof the wider typed-tool
  contract exists. 04 forbids registering capabilities without receipts
  (`04-spec-hop-nhat-mimi.md:38-42`).

### Pending preview

- **FACT** — service locks pending change sets, rejects multiple rows, checks a
  revision's supplied ID/digest, and decrypts operation ciphertext server-side
  (`service.py:652-693`). Model context receives operation JSON only: no ID,
  digest, nonce, expiry, policy version or expected-version envelope
  (`service.py:681-695, 793-795`).
- **FACT** — ordinary turns with pending preview halt with
  `pending_preview_requires_decision`; only an explicit revision can supersede
  after a validated typed replacement. Revision forces the Task tool and rejects
  text (`service.py:691, 1138-1227`; `openrouter.py:182-191`).
- **INFERENCE** — server authority is preserved, but operation-only context is
  less reproducible than a typed preview envelope; this is context fidelity, not
  a confirmation bypass.

## 3. Tool, provider and checks

- **FACT** — request exposes exactly one strict `task.create.v1` function: one
  STANDARD proposal requiring server confirmation, preallocated UUID, title/body/
  status/priority/due fields, `is_private=false`, and max 20 checklist items;
  extra properties are forbidden (`backend/app/agent/openrouter.py:52-93`).
- **FACT** — ordinary tool choice is `auto`; revision uses configured `required`
  or named-function choice; unqualified forced choice is rejected. Parallel tool
  calls are omitted; parser accepts one known call (`openrouter.py:157-219`).
- **FACT** — terminal result is text or exactly one validated Task call. Narration
  beside a valid call is discarded; status/schedule are normalized and private,
  missing/mismatched IDs and size violations are rejected
  (`openrouter.py:194-283`). One run has one turn/tool, then a frozen change set
  awaits Owner confirmation (`service.py:709-720, 1234-1281`).
- **FACT** — body has model, messages, one tool, tool choice, stream, `store=false`,
  max tokens, excluded hidden reasoning, usage include, provider policy and opaque
  session ID (`openrouter.py:142-179`). Exact mode pins provider/quantization and
  disallows fallback; adaptive mode bounds allowlists and allows fallback within
  them (`openrouter.py:111-139`). Both send `require_parameters`,
  `data_collection=deny`, ZDR setting and price caps.
- **FACT** — preflight serializes only `messages` as compact UTF-8 JSON and rejects
  byte length + max output > configured context; it never truncates
  (`openrouter.py:151-156`). After dispatch, service checks terminal schema,
  reserved Task ID, revision kind, generation frontier, pending preview locks and
  source state; failures/unknown are durable and unknown is not blindly retried
  (`service.py:904-926, 927-997, 1138-1227`).
- **INFERENCE** — byte-plus-token preflight is not tokenizer accounting: it omits
  tool schema/provider overhead and can reject valid or admit overflowing requests.
- **FACT** — stream adapter accumulates fragments, requires usable terminal signal,
  records timing in usage and emits text only after terminal parsing
  (`openrouter.py:343-510`).

## 4. Provenance, evidence and gaps

- **FACT** — request fingerprint includes route kind, current message hash,
  history hash, pending-operation hash, tool version and Task source versions;
  provider call stores configured route and checkpoint (`service.py:800-844`).
  Success stores response ID, terminal kind/result hash, tool version, actual
  provider/model and usage (`service.py:1011-1044`).
- **FACT** — generic `EvidenceBundle` permits assembled prompt/request/response,
  tool exchanges, route/config/usage and completeness, while rejecting secrets and
  hidden reasoning (`backend/app/agent/contracts.py:98-182, 294-320`), but current
  send path does not instantiate it.
- **INFERENCE** — fingerprint is not a replay receipt: it omits exact prompt bytes,
  tool schema, full route body/provider policy, token method and serialized
  messages. Current contract requires full app-visible encrypted diagnostic
  evidence with truthful COMPLETE/INCOMPLETE/FAILED manifest
  (`04-spec-hop-nhat-mimi.md:236-244`; `07-master-delivery-plan-mimi.md:213-240`).
- **OPEN** — evidence TTL/cap/warning/export/deletion and production policy are
  unresolved Owner gates. No evidence capture/output was run here.

| Axis | Current bound | Gap |
|---|---|---|
| Input | 12,000 chars | no token budget/classification |
| History | 24 messages / 65,536 bytes | no frontier/manifest/meter/compaction |
| Domain | 10 non-private Tasks | no read tools/other domains/freshness manifest |
| Preview | one pending operation; 15-minute default | no digest/expiry/version envelope in context |
| Run | one turn/one tool | no iterative loop/inbox/steering |
| Output | 4,096 default, 256–32,768 bound | no measured reserve/continuation |
| Tool | one strict Task create | no domain registry |
| Route | exact/adaptive allowlists, ZDR/data deny/store false | no live route card/probe |
| Privacy | standard Task filter; private flag false | private taint/processor path absent |
| Evidence | hashes/route/usage/events | no full encrypted payload bundle |

## 5. Proposals and questions

- **PROPOSAL** — add a versioned context manifest per call: policy hash,
  transcript frontier/omissions, source IDs/versions, pending-preview envelope,
  tool schema, route snapshot, token method and sensitivity.
- **PROPOSAL** — use route tokenizer accounting including tool schema/output
  reserve and persist estimated versus provider-reported usage.
- **PROPOSAL** — make encrypted diagnostic capture explicit, bounded and truthful
  on stream failures, excluding headers/secrets/hidden reasoning.
- **PROPOSAL** — if iterative behavior is approved, specify a separate bounded
  loop for repeated reads, draft/frozen preview, pending input, steering,
  compaction, retry and revalidation; do not infer it from `max_turns=1`.

Questions for T1/Owner: Is inline P1 policy sufficient for first smoke? What
context/token/meter/frontier contract is approved? Should preview context include
redacted digest/expiry/version? Provider-visible read tools or server preload?
Which evidence parts/TTL/cap/export policy? Which exact route/model/effort/budget?
What UX follows unknown provider outcome? Must the 2026-09-16 UI/full-app route
correction precede any live call?

## Short summary

**FACT:** current origin/develop is a bounded P1 Task request: inline Vietnamese
policy + owner timestamp + ten safe Tasks with source versions + bounded history +
current user text; one strict Task-create tool and exact/adaptive OpenRouter policy.
Server checks cover generation, preview digest, Task ID, schema, deadline/frontier
and no-blind-retry.

**INFERENCE:** it is not the final Mimi context architecture: policy loader,
context manifest/meter, token-accurate preflight, iterative read/tool loop,
compaction/checkpoint and full payload evidence are absent.

**OPEN:** route adoption, evidence lifecycle, thresholds, preview envelope and
iterative-loop behavior require T1/Owner workshop. No API/provider/browser/DB/
migration/test/runtime/production command was run.
