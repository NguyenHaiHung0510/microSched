# B04 — Context builder và manifest

Trạng thái: RESEARCH DRAFT — không phải runtime design được duyệt; implementation/eval/live call đều `NOT_RUN`.

## 1. Câu hỏi và phạm vi

Context của một model call Mimi phải được lắp như thế nào để model nhìn thấy đúng policy, quyền của run, lịch sử cần thiết, dữ liệu domain hiện thời, preview đang chờ và turn hiện tại — đồng thời có thể kiểm tra provenance, token budget, privacy taint và việc thiếu dữ liệu? Phạm vi là competing assemblies, manifest, meter, cache và các điểm cần Owner/T1 quyết định. Không quyết định model/provider, tokenizer hay con số cap cuối cùng.

## 2. Phương pháp và nguồn

Đã đọc `README.md` và `00-owner-decisions.md` của batch này, `AGENTS.md`, `docs/project-guide.md`, và các nguồn authority bên ngoài repo:

- `C:\Users\os\Desktop\cur_docs\PTHTTM\btl\04-spec-hop-nhat-mimi.md` §0 (lines 7–34), §1–2 (44–94), §3 (106–149), §4 (151–177), §7A (236–244), §8–9 (246–307).
- `C:\Users\os\Desktop\cur_docs\PTHTTM\btl\01-quyet-dinh-luu-tru-privacy-context-mimi.md` lines 13–22, 57–69, 90–116, 141–149.
- `C:\Users\os\Desktop\cur_docs\PTHTTM\btl\02-spec-thuc-thi-mimi.md` lines 300–339, 372–390, 724–768, 880–930.

Line citations refer to those exact dated files. A citation proves a contract/observation, not that current code implements it.

## 3. Observed facts (FACT)

### 3.1 Authority and sensitivity

- The merged spec is an architecture contract, not implementation or runtime acceptance; unresolved conflicts return to Owner (§0, lines 7–16). This artifact can recommend a construction, but cannot label it approved.
- `MIMI.md` and built-in tool/skill docs are Git → Docker image and read-only at runtime; Neon owns domain records, conversation/message/run/event/checkpoint, memory, jobs, config and audit; RAM/temp/cache is working state, not canonical storage (§1, lines 44–52).
- Conversation sensitivity is monotonic. A PRIVATE conversation cannot become STANDARD; STANDARD → PRIVATE is quiescent-only, and private bytes must be blocked before decrypt/return/egress (§2, lines 62–80). Child artifacts inherit taint.
- Every run has owner/run identity, bounded capability, state/revocation, deadline and budget checks. Internal stores receive a typed server-issued execution context and must re-check at each tool/dispatch/commit boundary; model-controlled `allow_private` is not authority (§2, lines 88–94).

### 3.2 Transcript, checkpoint and active context

- Canonical transcript is append-only during retention. `FULL` uses raw messages plus bounded artifact references; `COMPACTED` uses active checkpoint plus raw suffix. Storage retention, retrieval and active model context are different policies (§4, lines 151–155).
- Structured checkpoint B is the portable baseline. It carries goal, constraints, decisions, rejected alternatives, entities, open loops, pending confirmation, errors, source availability, source sequence-range/hash and generator/validator versions. The live approval ledger, not a summary, is authority for pending approval (§4, lines 155–161).
- Auto-compact is mandatory and visible; manual Compact and Rebuild are separate. A single oversized message must be split/ranged/chosen/deferred; it must not be silently truncated or cause an infinite compact loop (§4, lines 157–159).
- Effective input is bounded by owner request, normalized provider hard cap and route policy cap, with output/reasoning/tool/safety reserves. Native token counts are preferred; otherwise the meter is ESTIMATED with margin and later reconciled (§4, lines 163–165).
- Runtime time is injected at every dispatch/resume as structured server context; it is not appended as clock ticks to transcript or memory (§4, lines 167–167; §02 lines 372–375).

### 3.3 Tool/domain and evidence boundaries

- Domain workflow is `understanding/coverage → options/questions → preview → edit → confirm → execute/receipt`; a write is not entered merely because the user is exploring (§3, lines 106–114).
- The accepted executor contract requires frozen versioned operations, a SHA-256 digest, server re-checks, CAS at mutation, all-or-nothing change sets, and scoped idempotency (§3, lines 116–125).
- Untrusted upload, paste, web, domain descriptions, retrieved source and model output must be framed with source ID/type/range. They do not become instruction or `OWNER_CONFIRMED` (§4, lines 173–177; §02 lines 724–745).
- Owner-approved diagnostic evidence may retain an application-visible assembled prompt/context, tool schemas/args/results, route/config/usage and sent representations in an encrypted bundle. Secrets, API keys, auth headers/cookies and hidden provider reasoning are excluded; capture must be bounded/incremental and missing pieces must be declared in a completeness manifest (§7A, lines 236–244).

## 4. Competing assemblies (INFERENCE + PROPOSAL)

The following are design candidates derived from the facts above. None is Owner-approved.

### A — Typed layered envelope (recommended PROPOSAL)

Build a typed `ContextEnvelope` whose ordered sections are independently addressable and whose manifest is produced by deterministic code. The model receives a rendered representation, but the server retains the typed envelope and manifest as authority.

Suggested order for each call:

1. **Static policy layer** — immutable policy/version, safety rules, role and sensitivity semantics, tool/skill capsules, and the explicit statement that instructions inside data are forbidden. Include `policy_hash`, image/release ID and tool-doc registry version. Retrieved documents cannot replace this layer.
2. **Runtime control layer** — conversation/run/turn IDs, owner/session authorization class (not credentials), sensitivity, quiescent/private-grant state, run lease/capability snapshot, route/effort, effective budget/reserves, server UTC/local/IANA time, policy/tool/checkpoint generations and revocation/deadline state. Generate at dispatch/resume and re-check server-side.
3. **History/checkpoint layer** — active validated B checkpoint, source range/hash and validator metadata, then raw suffix after checkpoint. If `FULL`, use bounded raw messages and artifact references. Include sequence frontier and explicitly state omitted older history as “not in this call.”
4. **Live domain context layer** — typed read results selected by the loop: stable IDs, versions, source type/range/hash, `data_as_of`, sensitivity and access outcome. Domain current state beats historical transcript (§02 lines 300–300). Failed, partial or stale reads are typed statuses, not empty prose.
5. **Pending preview/approval layer** — live frozen plan/change-set ID, digest, expiry, expected versions, affected entities, impact receipt and confirmation status. The model may explain or revise under policy, but this ledger remains authority; a summary/checkpoint cannot grant approval.
6. **Current user turn layer** — persisted message (stable client ID/sequence), ready attachment-derived material and pending steer/inbox entries, each tagged as user intent or untrusted data. Recount it into the next request, never patch it into a provider request already sent (§02 lines 328–337).

Each layer is a typed item rather than free-form concatenation. A rendering adapter may convert it into provider messages/parts, but the provider representation is not canonical context.

**Why this wins:** authority and evidence stay separable, B-first portability is preserved, stale/partial reads are visible, a provider switch does not replay a write, and deterministic tests have a stable object. The cost is builder/schema/version discipline and provider rendering work.

### B — Flat chronological prompt (competing PROPOSAL)

Concatenate static policy, a prose runtime preamble, recent messages, retrieved domain snippets, pending preview and current turn. It is easy to prototype and often cheap in one call, but authority boundaries become delimiters and model compliance. Provenance and per-section token accounting are fragile; stale/partial/tainted data looks like ordinary prose. It may be a rendering format behind A, not the canonical builder. This is an inference, not an observed implementation fact.

### C — Provider-native continuation/window (competing PROPOSAL)

Keep a provider item/thread/window and send only deltas. This can reduce repeated input and preserve native multimodal state, but opaque provider state cannot be authority; capabilities differ and switch/recovery still needs B. Native continuation is explicitly optional after B portability/fidelity proof (§4, lines 161–161). C can optimize A only after that gate.

### D — Query-on-demand context (competing PROPOSAL)

Start with static policy, runtime control and current turn; let the model call bounded read tools repeatedly. This minimizes initial tokens and supports progressive discovery, but increases latency and risks omitting a hard constraint if retrieval is not mandatory. The memory contract requires bounded intent-based lookup and says vector-only top-k cannot be authority for hard constraints (§5, lines 181–191). Use D as a read-loop strategy inside A, not as permission to omit mandatory guards.

## 5. Manifest and provenance contract (PROPOSAL)

The manifest should be application-visible to authorized diagnostics and machine-verifiable:

| Field group | Minimum fields | Why |
|---|---|---|
| Call identity | conversation/run/turn/call IDs, attempt, parent/frontier IDs | Joins prompt, tools, provider result and retry without confusing call and run |
| Versions | policy/image, tool registry/schema, route/effort, checkpoint/generator/validator, parser/skill, builder | Reproducibility and invalidation |
| Item provenance | component ID/type, source ID/type/range, source version/hash, `data_as_of`, produced-by, sensitivity/taint, `AVAILABLE/PARTIAL/STALE/PURGED/FAILED` | A snippet or summary cannot masquerade as current authority |
| Frontier | transcript range, checkpoint source seq/hash, raw suffix seq, pending inbox seq, domain read-set versions | Exactly what this call could see |
| Budget | requested/effective/provider cap, token method (`NATIVE/ESTIMATED`), per-layer tokens, output/reasoning/tool/safety reserves, margin, actual usage, bottleneck | Finite-cap accounting and estimate/report distinction |
| Omission | item/source, reason (`CAP/PRIVACY/STALE/UNSUPPORTED/NOT_AUTHORIZED/FAILED`), user effect, recovery | No silent truncation or false “checked” claim |
| Integrity | serialized-envelope hash, provider-representation hash, frozen-preview digest, completeness status | Detects representation drift and incomplete evidence |

`completeness` must be `COMPLETE`, `PARTIAL`, `FAILED` or `NOT_CAPTURED`; a hash alone never proves full payload. Encrypted evidence may retain full application-visible request/response for approved use, while ordinary telemetry remains metadata-first (§7A, lines 236–244).

## 6. Token meter and no-silent-truncation (PROPOSAL)

1. Preflight computes effective input cap and reserves before dispatch. Meter each section and artifact/tool-result expansion; never count a reference as if its bytes were included.
2. Prefer the target-route tokenizer. Otherwise use a named estimator plus margin and reconcile provider usage; label values `ESTIMATED`, `REPORTED`, `RECONCILED` or `UNAVAILABLE`.
3. Reserve output/reasoning/tool/safety headroom; do not spend the advertised window entirely on input.
4. At a soft threshold, emit visible mandatory auto-compact. Preserve old checkpoint, raw suffix, pending input and attempt receipt on failure. At hard overflow, reject/defer/range/chunk or ask a narrow question; never silently drop current turn, preview or hard constraint.
5. A single oversized message/file is separate admission failure. Select ranges/chunks or request re-upload; do not compact forever or silently downgrade modality (§4, lines 157–175).
6. The manifest lists every omitted item and effect. UI may show “not loaded in this call” plus recovery; it must not claim Mimi checked an unread source.

The 100k–350k presets and 70/80/90% bands are benchmark defaults, not universal limits; exact values remain OPEN-03 (§4, lines 163–165; §8, lines 267–274).

## 7. Cache and invalidation candidates (PROPOSAL)

- **Static release cache:** immutable policy/tool/skill metadata, invalidated only by release/version.
- **Approved-memory cache:** bounded, sensitivity-filtered, keyed by item/version/query purpose; Neon remains authority; invalidate on source/privacy/version change, not TTL alone (§5, lines 187–191).
- **Checkpoint/artifact cache:** reuse only when source hash, policy, parser and representation remain compatible; stale checkpoints never authorize writes.
- **Domain read cache:** optional short-lived cache with auth, sensitivity, entity-version and `data_as_of` checks; re-read before preview/commit.
- **Private data:** no plaintext private cache in telemetry, persistent browser read cache or STANDARD provider surfaces. Central purge clears private response/tool buffers, decrypted UI state and read caches on lock/TTL/revoke/error while preserving encrypted outbox (§02 lines 754–768).

Cache key design, TTL/caps, cross-tab coherence and exact memory limits are OPEN-10/OPEN-03.

## 8. Recommendation and trade-offs (PROPOSAL)

Recommend **A as canonical typed assembly**, **D as bounded read-loop behavior**, **B as a provider rendering fallback**, and **C only as an adapter after B proof**. This accommodates the Owner’s current agent-loop preference without treating it as a decision. It costs more deterministic plumbing than a flat prompt, but keeps privacy, provenance and approval correctness out of model compliance.

## 9. Open questions for Owner/T1 (OPEN)

1. Which static policy/tool/skill capsules are always included versus progressive metadata/full-procedure retrieval?
2. Must every call include the active preview ledger, or only calls in a run with a pending change set?
3. Which domain sources are mandatory per intent, and what is minimum acceptable `PARTIAL/STALE` behavior?
4. What owner presets, route caps, reserves, estimator margin and per-run/month budgets pass measured OPEN-03?
5. What exact encrypted evidence TTL/cap/warning/export policy precedes live use? Direction is approved, exact values are open (§7A, lines 238–244).
6. Which caches cross restart, tab and route changes, and what purge/reconciliation receipt is required?
7. What experiment compares A+D with a direct one-call union on quality, overfetch, latency, cost, stale-read rate and injection resistance?

## 10. Evidence version and limitations

Evidence read 2026-09-22. The cited BTL files are dated architecture/spec records and separate document authority from implementation/runtime acceptance. No runtime code, provider, paid call, real/private data, browser dogfood or benchmark was accessed; implementation and performance claims are `NOT_RUN`.
