# B05 — Tools và deterministic gates

Trạng thái: RESEARCH DRAFT — không phải executable design; runtime/eval/paid call đều `NOT_RUN`.

## 1. Câu hỏi và phạm vi

Làm sao tách “model được đề xuất gì” khỏi “server cho phép gì”, và đặt read loop, draft, frozen preview, confirm, idempotency, CAS và pre/post-call checks ở đâu? So sánh direct terminal union với iterative agent loop; Owner hiện nghiêng agent loop nhưng đó là preference để nghiên cứu, không phải quyết định.

## 2. Phương pháp và nguồn

Đã đọc research README/owner decisions, repo `AGENTS.md`/`docs/project-guide.md`, và:

- `C:\Users\os\Desktop\cur_docs\PTHTTM\btl\04-spec-hop-nhat-mimi.md` §3 lines 106–149, §4 lines 151–177, §6 lines 201–220, §7 lines 222–244, §8–9 lines 246–307.
- `C:\Users\os\Desktop\cur_docs\PTHTTM\btl\02-spec-thuc-thi-mimi.md` lines 310–339, 357–371, 724–768, 880–950.

The sources are dated contract records; they do not prove implementation.

## 3. Facts (FACT)

- Workflow is understand/coverage → options/questions → preview → edit → confirm → execute/receipt; model output is proposal, not authority (§04 §3, lines 106–114).
- Tool classes are bounded: C0 read; C1 narrow reversible; C2 sensitive/private/finance/health/subscription/memory/bulk; C3 is not registered for secrets/PIN/auth/schema, hard deletes, arbitrary SQL/URL/shell/code/macro or self-policy/tools (§04 §3, lines 110–114).
- Executor needs typed versioned operations, before/after, expected versions, sensitivity/tier, reversibility, expiry, SHA-256 digest, server re-check at confirm, CAS during mutation, atomic related change set, audit receipt and scoped idempotency (§04 §3, lines 116–125).
- Read tools are allowed in a loop; write tools create an operation/change set and do not touch domain DB. A run waits for confirmation; reject does not silently repair and execute (§02 lines 320–324).
- Direct UI CRUD retains its own contract; it is not a reason to make model-facing tools broad (§04 lines 110–114).
- Run state and provider-call outcome are separate. `OUTCOME_UNKNOWN` requires reconciliation and `auto_retry=false`; committed durable results materialize once, late results are fenced (§04 lines 131–149).
- Typed tools use filter/range/cursor/detail and stable IDs; live domain state wins old transcript; stale/partial reads are meaningful states (§04 lines 110, 153–159; §02 line 300).
- Injection detectors are signals only. The real boundary is server allowlist/capability, typed validation, confirmation and transaction (§02 lines 724–745).

## 4. Authority split (PROPOSAL)

Model-facing interface should be intentionally weaker than server authority:

| Surface | Model may propose/request | Server alone decides |
|---|---|---|
| Read tool | tool name, typed args, bounded filter/range/cursor/detail | registry membership, auth/sensitivity, row limits, query plan, timeout, redaction, `data_as_of`, source versions |
| Draft/plan | goals, options, operation candidates, questions, uncertainty | whether intent is sufficiently clear, allowed domain/tool set, grouping, tier, required confirmation |
| Preview | typed change-set candidate and explanation | current state, before-image, expected versions, policy, scope, digest, expiry, reversibility and side effects |
| Confirm | change-set ID + digest + nonce + decision | owner/session auth, private grant, lease, exact digest, expiry, current versions, pending-input impact, single-use nonce |
| Execute | no new payload; receives receipt/result | capability snapshot, CAS transaction, idempotency, revocation/revoke race, result fence, audit and refresh marker |

Never accept model-controlled `allow_private`, `skip_confirm`, arbitrary destination, raw SQL, URL, shell/code or altered operation payload. The confirmation request binds an existing frozen digest, not a second model payload (§04 lines 118–123).

## 5. Gate pipeline (PROPOSAL)

### 5.1 Preflight before each model call

1. Load server run identity, sensitivity/taint, lease, route/profile, deadline, turn/tool/cost bounds and revocation state.
2. Check conversation generation, pending steer/inbox and active preview. A material change, privacy/destination change or uncertain impact must pause for revision; a no-impact supplement may retain preview only after a recorded impact assessment (§04 lines 147–149; §02 lines 328–337).
3. Build typed context and manifest; verify source hashes/versions, auth and privacy before decrypting/returning any bytes. Read failure is `PARTIAL/STALE/FAILED`, not an empty success.
4. Apply model route capability, input meter, reserves and budget. If it does not fit, compact/range/defer or ask; do not silently trim or auto-switch a pinned route (§04 lines 157–165).
5. Register only exact tools whose receipts/capabilities are current. Enforce call count, argument schema, bounds and per-tool sensitivity.

### 5.2 Before each tool call

- Verify tool registry version, server-issued capability, run generation, lease/deadline, current sensitivity and route budget.
- Validate args with typed schema; normalize UTC/timezone/Decimal and reject omitted-vs-null ambiguity.
- Re-check source auth/privacy and read-set version. Never pass private bytes from a STANDARD run; never let a source label grant authority.
- Assign call ID/idempotency identity and persist intent/fingerprint before external/provider dispatch where needed. A model retry is not automatically a safe server retry.

### 5.3 Draft and preview boundary

Draft is conversational understanding/options/plan and may contain no executable authority. Preview is a frozen typed change set: preallocated operation IDs, args, before→after, expected versions, sensitivity/tier, side effects, expiry and digest. C1 is ≤5 operations; C2 is 6–20 or sensitive; larger sets split into related groups rather than one blind apply (§04 lines 112–114). A preview may be edited into a new version; only the latest valid digest can be confirmed.

### 5.4 Confirm boundary

Confirm accepts only change-set ID, exact digest, explicit decision and single-use nonce. Server atomically checks owner/session authority, private grant (if applicable), run lease, policy/route, expiry, current versions and pending-input impact. No new natural-language payload is merged into the frozen plan. If any check fails, return stale/expired/needs-review and keep the domain unchanged.

### 5.5 Execute/post-call

Related same-Neon operations execute in one transaction with CAS; zero-row CAS is `STALE`, not silent latest-read retry. Unique `(server scope, idempotency key)` gives same-digest receipt replay and different-digest `409`; nonce replay is a separate rejection. Audit and durable refresh-needed marker share the commit boundary; after-commit signals accelerate but do not establish correctness (§04 lines 121–125). Provider outcomes are reconciled before retry; no blind retry after unknown outcome.

## 6. Direct terminal union vs iterative agent loop (INFERENCE/PROPOSAL)

| Dimension | Direct terminal union | Iterative bounded agent loop |
|---|---|---|
| Shape | Server pre-reads a fixed union, one model call, then draft/preview | Model receives bounded tools and performs several read calls before answer/preview |
| Latency/cost | Predictable and usually lower for known task; overfetches unrelated data | More round trips and token/tool cost; can stop once sufficient evidence exists |
| Completeness | Strong if required union is known; brittle for ambiguous intent/new domain | Progressive discovery handles ambiguity, but can fail to retrieve a hard constraint unless mandatory reads are server-enforced |
| Provenance | Easy to manifest a fixed read set | Must record each call, source version and omission; stronger causal trace if done correctly |
| Attack surface | Smaller tool loop; a poisoned result still contaminates the single call | More tool/result boundaries and opportunities for indirect injection or data exfiltration |
| Freshness/races | One coherent read snapshot is simpler; long pre-read may stale before commit | Re-check each call and mandatory final preflight; more churn/race handling |
| Recovery | Simple retry of one call, but context overflow can be opaque | Checkpoints between calls support halt/resume/unknown-result recovery (§04 lines 131–149) |
| Best use | Small, explicit read with known fields and low ambiguity | Bounded planning, multi-domain discovery and document-grounded work |

**Recommendation (PROPOSAL): hybrid gate:** server prefetches mandatory safety/identity/current-version reads; an iterative loop may perform bounded C0 reads and source-range reads; it cannot choose away mandatory reads or escalate its own capability. Direct union remains a baseline and fast path for small explicit requests. Owner’s agent-loop preference is therefore testable without making the loop security authority.

## 7. Deterministic cases and gates (PROPOSAL)

Minimum fake-provider/disposable-DB matrix: duplicate confirm same digest; different digest same key; nonce replay; expired preview; stale entity version; zero-row CAS; partial related transaction; revoke vs commit; lock vs confirm; cancel vs durable result; unknown provider result then late result; crash after domain commit before refresh signal; read source changes between preview and execute; private source requested by STANDARD; malformed/oversized args; tool result poisoning; and pending steer that is harmless, material or uncertain. Each new guard must show deliberate violation RED → restoration GREEN (§04 §7 lines 224–230; §8 lines 276–293).

Read-only quality cases should compare fixed union and loop on the same synthetic fixtures, required constraints, source citations, stale-read handling, tool count, latency, tokens/cost and injection resistance. Provider mocks prove lifecycle/transport only, not conversation quality. This research did not run those cases.

## 8. Open questions (OPEN)

1. Which mandatory prefetch set applies to each intent/domain, and what are hard per-run/tool/latency caps after measurement?
2. Is draft required for every ambiguous request, or can the server classify a narrow explicit request directly to preview?
3. Exact policy for read results with `PARTIAL`, `STALE`, `FAILED` and source deletion is still to be operationalized.
4. Which sensitive operations are C2 in practice, and which remain disabled until a dedicated adapter receipt?
5. What provider call identity/idempotency guarantees are available per selected route? Do not infer from model labels.
6. How much loop trace belongs in encrypted evidence versus metadata-only telemetry, and what exact retention/cap precedes live use?

## 9. Evidence version and limitations

Read 2026-09-22. No runtime edit, API call, browser dogfood, provider call, paid eval or implementation test was performed. Recommendations are proposals; Owner approval and later deterministic receipts are required.
