# B12 — Tool granularity và bulk operations cho Mimi

Trạng thái: **RESEARCH DRAFT — OWNER REVIEW PENDING — IMPLEMENTATION/EVAL NOT AUTHORIZED**
Ngày đọc: 2026-09-22
Phạm vi: tool contract, bulk read/write, preview UX/data contract; không sửa runtime, không gọi
API/provider, không dùng key, không chạy eval/browser.

## 1. Câu hỏi và kết luận ngắn

### Câu hỏi

Nếu Mimi chỉ có tool đọc/ghi một record mỗi lần, yêu cầu như “đổi tên/reformat 100 Tasks” có
buộc phải tạo 100 sequential model tool calls không? Có thể giảm round-trip và context cost mà vẫn
giữ authorization, privacy, provenance, version/CAS, idempotency, draft/preview/confirm,
reviewability, atomicity và partial-failure semantics như thế nào?

### Kết luận (INFERENCE/PROPOSAL, chưa Owner-approved)

- **FACT từ các API chính thức:** nhiều provider có thể trả nhiều function calls trong một model
  turn khi chúng độc lập; đó là tối ưu execution/round-trip, không phải quyền để server tự thực
  thi. OpenAI còn cảnh báo arguments do model sinh ra vẫn phải validate trong code.
- **INFERENCE:** một tool per item là granularity quá thấp cho 100 record nếu model phải tự lặp
  100 lần. Không nhất thiết phải có 100 model turns: có thể dùng một read query trả page hoặc
  snapshot, hoặc một batch call chứa nhiều independent subcalls. Tuy vậy, 100 database mutations
  vẫn phải được server kiểm tra/ghi nhận theo semantics rõ ràng; gom JSON không biến chúng thành
  một transaction tự động.
- **PROPOSAL:** dùng hybrid “bounded query/list → selection snapshot handle → server-side typed
  transformation → frozen bulk preview → explicit confirm → atomic batch/group execution”. Mimi
  chỉ đề xuất filter và typed transformation; server tự xác định các row được phép thấy, before/after,
  versions, exceptions, groups và digest.
- **OPEN:** page-size/result-byte/tool-call/deadline/concurrency caps, điều kiện chia group, whole-
  batch atomicity hay group atomicity, và ngưỡng chuyển draft trước preview đều phải đo trên route,
  DB và workload được Owner duyệt; không đặt số đo minh họa thành default.

Điểm cốt lõi: **batch transport ≠ batch authority ≠ batch atomicity**. Batching giảm số lần đi qua
model/provider/network; authority, stale check, per-record privacy và commit semantics vẫn là trách
nhiệm server.

## 2. Phương pháp và nguồn

### 2.1 Internal evidence (FACT; snapshot hiện tại)

Đã đọc README.md, 00-owner-decisions.md, 05-context-builder-and-manifest.md,
06-tools-and-deterministic-gates.md, 11-owner-workshop-and-t1-synthesis.md,
12-independent-evidence-critique.md, AGENTS.md, docs/project-guide.md,
docs/qa-agent-framework.md, cùng các module hiện hành. Các dòng dưới đây là implementation
facts của worktree, không phải target design.

| Hiện trạng | Bằng chứng | Ý nghĩa cho B12 |
|---|---|---|
| Mimi prefetch tối đa 10 Task STANDARD và gắn source_version từ updated_at | backend/app/agent/service.py:581-604, 699-703 | Đã có bounded read và provenance tối thiểu, nhưng chưa có query/filter/page/snapshot tool cho model. |
| Lease hiện chỉ cấp task.create.v1, task.read.standard.v1, một turn và một tool call | backend/app/agent/service.py:713-718 | Chưa thể suy ra iterative loop/batch đã chạy; đây là walking skeleton. |
| Model proposal hiện materializes một ChangeOperation; frozen change set được tạo từ một operation | backend/app/agent/service.py:1234-1254; backend/app/agent/contracts.py:62-79 | Schema tuple có thể chứa nhiều operation về mặt kiểu, nhưng service/confirm hiện chưa phải bulk executor. |
| Confirm đọc lại frozen payload, bind digest/nonce/expiry/idempotency rồi gọi TaskStore.create | backend/app/agent/service.py:1284-1477 | Boundary tốt để mở rộng, nhưng không chứng minh update 100 row, CAS per row, inverse hay partial receipt đã có. |
| Direct Task API có list bằng signed keyset cursor, limit HTTP 1..100, và timeline gom ba bucket | backend/app/domain/tasks.py:756-896; backend/app/web/routers/tasks.py:54-135 | Có primitive server-side paging/aggregate để tái sử dụng; cursor hiện không phải selection snapshot cho bulk. |
| Direct update/delete vẫn là per-task endpoint; TaskStore.update/soft_delete không nhận expected version trong payload | backend/app/web/routers/tasks.py:163-182; backend/app/domain/tasks.py:1037-1114 | Mimi không được giả định direct CRUD đã có bulk CAS; cần contract mới hoặc adapter riêng. |
| Task read áp dụng readable(...), private visibility và child query sau parent selection | backend/app/domain/tasks.py:672-755, 800-895 | Privacy filter phải xảy ra trước model-result assembly; không cho model tự suy ra private rows từ count/IDs. |
| Owner đã duyệt D1 hybrid envelope + bounded iterative reads, giữ fixed prefetch fast path; D2 adaptive draft/preview; D3 canonical replay + optional compatible cache; D4 progressive UX | 00-owner-decisions.md; 11-owner-workshop-and-t1-synthesis.md | B12 phải là bounded proposal, không tạo ngưỡng “2/3 records”, không cấm blanket cache, không coi draft là executable. |
| Owner bổ sung: side-chat là quick chat tinh gọn; Mimi workspace là nơi inspect tường minh nhất | Owner instruction in current handoff, 2026-09-22 | Hai surface chỉ là hai projection của cùng frozen preview; không tạo state/digest/selection thứ hai. |

### 2.2 Primary external sources (FACT; URLs và ngày truy cập)

1. **OpenAI Chat API reference**, truy cập 2026-09-22, mục parallel_tool_calls, tool-call ID và
   cảnh báo validate arguments:
   https://developers.openai.com/api/reference/resources/chat
2. **Google AI for Developers — Function calling with the Gemini API**, truy cập 2026-09-22:
   function calling có thể nhiều function trong một turn (parallel) hoặc tuần tự/compositional;
   parallel chỉ phù hợp khi độc lập:
   https://ai.google.dev/gemini-api/docs/function-calling
3. **Anthropic — Define/use tools**, truy cập 2026-09-22: disable_parallel_tool_use để giới hạn
   một tool, kết quả phải map bằng tool_use_id, và batch tool là một workaround khi cần gom
   nhiều tool calls:
   https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools
4. **Google AIP-158 Pagination**, truy cập 2026-09-22: collection nên pagination ngay từ đầu;
   page_size, opaque page_token, giữ các request args khác nhất quán và result cap là một phần
   contract:
   https://google.aip.dev/158
5. **Microsoft Graph JSON batching**, truy cập 2026-09-22: một HTTP batch có correlation ID;
   response có thể out-of-order; outer 200 không chứng minh inner request thành công; dependency
   failure là 424; batch nên rõ là sequential hoặc parallel:
   https://learn.microsoft.com/en-us/graph/json-batching
6. **Google AIP-234 Batch Update**, truy cập 2026-09-22: synchronous OK khó diễn đạt partial
   failure; khi cần partial errors nên bind lỗi với index/request ID:
   https://google.aip.dev/234
7. **PostgreSQL 17 Transaction Isolation**, truy cập 2026-09-22: Read Committed query thấy
   snapshot committed tại thời điểm query bắt đầu; serializable vẫn có thể cần retry do conflict:
   https://www.postgresql.org/docs/17/transaction-iso.html
8. **OpenAI Chat API reference — prompt cache/usage fields**, truy cập 2026-09-22: API expose
   prompt-cache key và cached-token details; cached input không thay thế việc ghi usage/route/cache
   provenance:
   https://developers.openai.com/api/reference/resources/chat
9. **OpenAI Realtime API reference — truncation**, truy cập 2026-09-22: input vượt limit có thể bị
   truncate; có thể disable truncation để nhận error hoặc giữ retention ratio:
   https://platform.openai.com/docs/api-reference/realtime

Các nguồn xác lập capability/pattern của API, không xác lập route Mimi có cùng capability, latency,
token price, cache retention, hoặc schema success. Các con số trong ví dụ dưới đây là illustrative
only và phải giữ nhãn OPEN.

## 3. Vì sao per-item sequential tool calls là vấn đề

### 3.1 Bản chất chi phí (INFERENCE)

Với read_task(id) một phần tử, 100 record có thể tạo:

1. nhiều model→tool decision turns nếu model cần chờ từng result;
2. nhiều network/provider/tool boundary và durable event/receipt entries;
3. 100 lần schema/auth/lookup overhead ở phía adapter;
4. 100 result blobs được đưa lại vào context, sau đó còn phải giữ history/tool exchanges cho
   final answer/preview;
5. race window dài hơn giữa read đầu và preview/confirm cuối.

Nếu provider trả 100 independent calls trong một turn, application vẫn phải execute/validate từng
call và phải giới hạn concurrency/result size. Nếu server có thể phục vụ một SQL query theo
filter/projection/page thì query đó thường biểu đạt ý định tốt hơn việc cho model enumerate 100
IDs. Đây là suy luận kiến trúc, không phải benchmark; latency/token/cost chưa được đo.

### 3.2 Parallel calls không phải default cho writes (FACT + PROPOSAL)

Google mô tả parallel function calling cho các function độc lập; Anthropic cung cấp switch để
disable parallel; OpenAI reference có parallel_tool_calls và ID per call. Điều này hữu ích cho
đọc các nguồn độc lập, nhưng bulk rename/reformat có shared selection, shared snapshot và shared
confirm semantics. **PROPOSAL:** cho phép parallel execution ở read-only subqueries sau khi server
đã canonicalize/authorize; không cho model dùng parallel per-item writes để bypass frozen preview,
CAS, idempotency hoặc partial-failure policy.

## 4. So sánh các granularity/options

| Option | Model-facing shape | Điểm mạnh | Điểm yếu/rủi ro | Kết luận cho Mimi |
|---|---|---|---|---|
| A. Per-item tool | task.read(id) / task.update(id, patch) lặp N lần | Dễ hiểu, lỗi từng item, dễ map receipt | N tool calls/round-trip; model phải enumerate; context/history phình; bulk preview khó review; writes dễ thành partial side effects | Giữ cho single-item hoặc exception drill-down; không dùng làm bulk default. |
| B. Batch array tool | task.read_many(ids[]), task.update_many(ops[]) | Ít model/provider turns; correlation ID/index dễ; phù hợp independent reads | Array do model sinh có thể thiếu/duplicate/wrong IDs; payload/result quá lớn; batch request không tự atomic; partial failure cần explicit contract | Dùng cho bounded read và có thể execute group nhỏ sau frozen preview; server vẫn validate từng entry. |
| C. Query + selection snapshot + declarative transform | task.search/list(filter, projection, page) → opaque handle; server materializes rename/reformat preview | Model nêu intent/selection một lần; server có complete visible set, before/after, versions, grouping và digest; dễ paginated review | Cần selection lifecycle, query semantics, snapshot/versioning, transform DSL và conflict policy; broad selection tăng sensitivity/blast radius | **PROPOSAL khuyến nghị** cho 100 Tasks; boundary rõ nhất giữa model intent và server authority. |
| D. Server composite query/aggregation | task.aggregate/query trả summary/counts/groups/exceptions | Rất tiết kiệm result tokens; tốt cho read-only summary | Summary không đủ cho mutation; dễ mất row-level provenance; query language có thể thành arbitrary SQL nếu mở rộng quá mức | Dùng cho read-only summary và preflight; không làm write authority. |

### 4.1 Batching transport vs declarative bulk operation (INFERENCE)

B là transport-level aggregation: nhiều requests đặt trong một envelope. C là intent-level
aggregation: server tự materialize target set và typed transformation từ query + snapshot. Với ví dụ
“đổi format tiêu đề 100 Tasks”, C tránh cho model phải tạo 100 patch objects và giúp preview chứng
minh tất cả before→after. D hỗ trợ C bằng count/group/exception summary nhưng không được thay thế
row-level preview.

## 5. Bounded read contract (PROPOSAL; exact limits OPEN)

Tên dưới đây là illustrative schema names, chưa phải API approval.

### 5.1 task.search.v1 / task.list.v2

Request model chỉ được phép:

- filter: typed fields/enums/ranges (status, priority, date range, pinned, text search nếu
  được Owner bật); không raw SQL, URL, arbitrary predicate/code/regex;
- projection: allowlist tối thiểu (id, title/status/priority/schedule/version); full body/items
  chỉ khi tool capability, privacy gate và result budget cho phép;
- page_size, opaque cursor, sort; server có default/hard maximum nhưng con số phải measured;
- optional query_id/selection_mode, không nhận allow_private từ model; private visibility đến từ
  server-issued lease/session;
- detail: summary/row/expanded, mỗi mode có byte/row cap.

Response phải có:

- items trong page, next_cursor, has_more, returned_count, omitted_count/reason nếu server
  không thể trả đủ;
- source_id, source_version, data_as_of, sensitivity/access outcome; failed/private/partial/stale
  không được biến thành empty list;
- query_hash, canonical filter/sort/projection hash, page_digest, tool-call ID và run provenance;
- optional snapshot_handle tạo bởi server, opaque/signed/scoped/expiring and non-authorizing by
  itself. Request lại phải re-check owner/session/capability.

Pagination giữ mọi args khác nhất quán, giống AIP-158; đổi query phải tạo query/snapshot mới. Handle
không được chứa plaintext private data hay grant quyền.

### 5.2 Selection snapshot semantics

**PROPOSAL:** server tạo selection_snapshot.v1 khi yêu cầu bulk transformation, lưu:

- owner/conversation/run/lease scope, sensitivity class, canonical filter/sort/projection/query hash;
- selected IDs và current source versions hoặc một server-side immutable snapshot reference;
- creation time, expiry, policy/tool version, snapshot digest, completeness/omission state;
- whether selection is EXACT, PARTIAL, STALE or FAILED.

EXACT nghĩa server đã xác định tập visible tại frontier đã ghi, không có nghĩa dữ liệu sẽ không đổi
sau đó. PARTIAL không được dùng để nói “đã kiểm tra 100%”. Read paging tiếp theo dùng handle +
cursor; không cho model sửa filter giữa chừng mà vẫn giữ digest cũ.

## 6. Declarative bulk transformation và preview (PROPOSAL)

### 6.1 Không cho model gửi executable code

Một transformation nên là typed DSL/enum, ví dụ:

    {
      "kind": "task.rename_or_reformat.v1",
      "selection_handle": "opaque-server-handle",
      "rule": {
        "operation": "prefix|suffix|normalize_whitespace|template",
        "template_id": "owner-approved-template",
        "arguments": {"prefix": "Ôn thi: "}
      },
      "projection": ["id", "title", "status", "updated_at"]
    }

Đây chỉ là minh họa shape; template_id, supported operations, maximum expansion, Unicode/timezone
normalization và private eligibility là OPEN. Không nhận Python/JS/SQL/regex tùy ý, raw destination,
secret hoặc model-controlled policy override. Server canonicalizes rule, evaluates it against the
snapshot và rejects any row for which output is invalid or exceeds field limits.

### 6.2 bulk.preview.v1 output contract

Preview phải là frozen, typed, inspectable result; summary không đủ. Tối thiểu:

- preview_id/change_set_id, schema/policy/tool/generator version, selection handle/hash,
  source frontier/snapshot digest, expires_at, nonce, idempotency scope;
- aggregate: selected/visible/changed/noop/conflict/forbidden/invalid/omitted counts; counts phải
  map tới exact row set and are not permission to execute;
- every changed row (paged/chunked): stable task_id, before fields, after fields, source version,
  operation ID, row digest, sensitivity, reason/status;
- unchanged rows may be collapsed only when server still records them as evaluated/no-op and UI says
  so; they must not disappear into an unqualified “100 checked” claim;
- exception rows: PRIVATE_NOT_ALLOWED, NOT_FOUND, STALE, VALIDATION_ERROR, NOOP,
  TRANSFORM_ERROR, BUDGET_OMITTED (names illustrative); each carries recovery action and no private
  bytes when caller lacks access;
- group metadata: deterministic grouping key, member IDs/count, group digest, group status and
  whether group is independently confirmable; top-level digest binds every group/exception/frontier;
- completeness: COMPLETE/PARTIAL/FAILED/NOT_CAPTURED, with explicit omissions and source ranges.

### 6.3 Preview UX for 100 Tasks (PROPOSAL; two surfaces, one canonical state)

The Owner's side-chat/workspace split should be presentation only. Both surfaces read the same
server-frozen preview by preview_id/change_set_id and digest; neither computes a new selection, edits
the payload, or maintains a second confirmation state.

**Side-chat = quick chat, compact projection.** Default content:

- one-line action and state: “96/100 eligible changes ready for review”;
- compact counts for changed/no-op/stale/forbidden/invalid and expiry;
- show only key conflicts (for example the most severe or blocking exceptions), never imply that
  collapsed rows were absent;
- one clear CTA to open Mimi workspace for full inspection; confirm/reject controls bind exact
  preview/group digest and may be disabled when full review is required;
- if selection is PARTIAL/STALE/FAILED, say that explicitly and offer refresh/rebuild, not a success
  summary.

Side-chat must stay small enough for quick interaction. It may show a compact sample, but sample rows
are not the authoritative complete preview and “confirm sample” must not silently mean “confirm all”.

**Mimi workspace = explicit inspection projection.** It is the place to review the full frozen data:

- top summary with selected/visible/changed/no-op/conflict/forbidden/omitted and completeness;
- grouping by deterministic result/status/date/exception or an approved user filter;
- search and sort over the frozen preview projection, preserving preview digest;
- paginated/chunked changed rows with before→after values, source version and operation status;
- per-row expand for complete details; exception panel with recovery action;
- receipt/status panel after execution, including group/row outcomes and reconcile state;
- confirm-all / confirm-group actions only when the selected IDs and digest are explicit.

**Disclosure levels, without overdesign:**

1. Minimal: side-chat state/counts/CTA; workspace summary and visible blocking exceptions.
2. Default: workspace groups plus changed rows and before→after; search/filter/sort and row expand.
3. Advanced on demand: source frontier, selection/query hash, tool calls, chunk digests, route/cache/
   token/cost provenance, policy/tool versions, nonce/expiry and raw receipt metadata (secrets and
   hidden reasoning excluded).

The same canonical preview data powers all levels. Summary/group collapse is a view operation, not
an authority operation. Loading a chunk or opening workspace never recomputes the transform or
silently changes what was confirmed.

## 7. Bulk confirm and execute semantics (PROPOSAL; Owner choice required)

### 7.1 Whole-batch atomicity

**Option W — whole batch all-or-nothing:** confirm one top-level digest; server rechecks every selected
row's permission/version/rule and commits one transaction. Any stale/invalid member fails the whole
batch with zero domain writes. Best reviewability and simple truth, but transaction duration/lock
contention and rollback cost grow with selection size.

**Option G — explicit group atomicity:** preview deterministically partitions into groups; each group has
its own digest, expected versions and idempotency scope. Confirm all or selected groups. Each group is
all-or-nothing; result explicitly reports succeeded, stale, failed, unknown, not_confirmed. This
enables bounded review/execution but is not whole-batch atomicity. Top-level receipt must say this.

**Option P — partial per-row:** each row commits independently and receipt maps every row. Most
resilient but has highest semantic surprise and recovery burden; disable for first bulk-write design
unless Owner explicitly wants it.

**PROPOSAL:** start with W for sets that fit measured transaction/preview budgets; offer G only after
an approved contract and deterministic tests. Never silently downgrade W to G because of timeout. If
execution outcome is ambiguous, reconcile by change-set/group/idempotency identity before retrying.

### 7.2 CAS, idempotency, inverse and rollback

For every row operation, frozen data should carry:

- visible before-image or a privacy-safe digest plus server-side stored before-image;
- expected source/entity version and selection frontier;
- canonical after-image/rule output and operation digest;
- inverse/reversible marker; for rename/reformat, inverse can be old title/body only if safely retained
  under selected privacy/retention policy;
- group/top-level change-set digest, single-use nonce, expiry, owner scope and idempotency key;
- receipt mapping row ID → outcome, before/after digest, conflict/error code, commit timestamp.

At confirm, server reloads the encrypted frozen payload, rechecks ownership/sensitivity/expiry/current
version and executes CAS. SELECT FOR UPDATE can coordinate concurrent rows, but a lock alone is not
an application-level expected-version check; stale rows must produce explicit conflict. PostgreSQL's
snapshot/serialization behavior is why all rows need a defined frontier and retry/reconcile policy.

Rollback should use a separate inverse change set/explicit Owner decision, not an implicit “undo last
100” lookup. If a group partially fails, only a group with a durable all-or-nothing receipt can claim
rollback safety; an ambiguous provider/DB outcome must stop and reconcile.

### 7.3 Partial failures and receipt shape

A batch HTTP 200 or model “done” text must not imply every row succeeded. The receipt should include:

- execution_mode (WHOLE_BATCH_ATOMIC, GROUP_ATOMIC, or Owner-approved per-row);
- top-level and group digests, confirmation decision scope, actual selected/eligible counts;
- per-row result or a secure paginated result handle, with errors correlated by stable operation ID;
- committed_count, noop_count, stale_count, forbidden_count, validation_count, failed_count,
  unknown_count, and omitted/unchecked count;
- whether the domain transaction committed, rolled back, or requires reconcile; refresh marker and
  audit linkage;
- exact route/model/cache/token/cost provenance only as reported/estimated/unavailable, not inferred.

AIP-234 and Microsoft Graph are useful API-design analogies: inner item failures must be addressable
by index/ID and outer success must not hide them. Their limits (for example Graph's 20-request batch)
are not Mimi defaults.

## 8. Result size, pagination, context and cache controls (PROPOSAL/OPEN)

### 8.1 Result shaping

- Default to summary/projection for discovery; fetch full fields only after intent requires them.
- Include page_size, opaque cursor and byte/token estimate; enforce row, byte, nesting and wall-time
  caps server-side. A page may contain fewer rows than requested.
- Treat tool result as untrusted domain data with source/version/taint metadata; never concatenate
  raw bodies into instructions without framing.
- If result exceeds cap, return typed PARTIAL/BUDGET_EXCEEDED plus continuation/recovery, not a
  silently truncated success. The model must not claim it saw omitted rows.
- Prefer server aggregation for counts/facets/group summaries, then row pages for review. This reduces
  context cost without reducing auditability.

### 8.2 Model calls and provider parallelism

- max_tool_calls is a lease/resource constraint, not a universal number. For each run record planned,
  attempted, succeeded, failed and unknown tool exchanges.
- Independent read subcalls may be executed concurrently only after server validates each request and
  applies bounded concurrency. Dependent calls (selection→preview, preview→confirm) remain ordered.
- Provider capability (parallel_tool_calls, Anthropic parallel behavior, Gemini parallel support) must
  be route-card evidence; adapter may disable it. Do not infer from model name.
- A batch array can reduce call overhead, but it may increase one response's context size. Measure both
  total serialized bytes/tokens and wall time; optimize for total cost and review correctness, not call
  count alone.

### 8.3 Cache policy (FACT/INFERENCE aligned with D3/D5)

Caching is not categorically forbidden. Canonical microSched transcript/context/run/preview ledger
remains source of truth. A provider prompt/conversation/response cache is an optional optimization
only when route privacy, retention, invalidation and rehydrate semantics are known.

- Cache key must include route/provider, policy/tool schema versions, canonical filter/projection or
  preview digest, source snapshot/version frontier, sensitivity class and relevant user scope.
- A cached read may be reused only while its source/version/expiry/access scope remains valid; on
  stale/private mismatch, miss and rehydrate from canonical DB.
- Do not use response cache to hide model variance in independent semantic eval repetitions or replay
  stale mutation proposals; receipt must record cache kind/hit/miss and actual provider.
- Daily STANDARD acceptance should follow the actual intended routing/cache/fallback topology; a
  controlled diagnostic lane can pin provider and disable response cache. This addresses D5: cache is
  a cost/performance component with privacy trade-offs, not a blanket ban or silent behavior.

Provider references show cached-token/truncation fields exist on some APIs, but values and privacy
contracts are route-specific. cached_tokens = 0 must not be invented when a provider does not report it.

## 9. Thresholds and measurements (OPEN; do not guess)

No numeric threshold below is approved by this report. Candidate variables to measure:

| Variable | Measure before choosing policy | Why it affects choice |
|---|---|---|
| Read page rows/bytes/tokens | p50/p95 serialized result and provider input usage by projection/detail | Determines whether one page or multiple chunks fit context. |
| Tool-call count/parallel width | model turns, tool exchanges, adapter concurrency, failure rate | Distinguishes parallel read benefit from overload/race. |
| Snapshot lifetime | review delay, stale rate, privacy/retention requirement | Determines expiry and stale-preview UX. |
| Preview review burden | time to find one wrong row, expand/search success, omission/conflict comprehension | Determines groups/chunk layout, not an arbitrary row count. |
| Whole-batch transaction | lock duration, DB time, rollback/retry rate, rows affected | Determines W vs G; no “100 is safe” assumption. |
| Partial failure distribution | stale/forbidden/validation/unknown by fixture and concurrency | Determines whether all-or-nothing is usable and how exceptions are grouped. |
| Transform risk | false-positive/false-negative selection and output validation | Determines when draft is required and whether DSL needs narrower operations. |
| Cache economics/privacy | reported cached input, total input/output/reasoning, response-cache hit, storage/retention, fallback cost | A hit alone does not prove lower cost or acceptable privacy. |
| Context truncation/compaction | admission errors, omitted source ranges, rehydrate success, cache hit changes | Prevents silent loss of hard constraints or preview rows. |

The first pilot, if later authorized, should compare: per-item baseline; bounded batch array read;
query+selection handle+server preview; and composite summary followed by row drill-down. It should use
synthetic data only, record exact route/cache topology, and report REPORTED/ESTIMATED/UNAVAILABLE.
This is a future proposal, not an execution request.

## 10. Owner/T1 questions (OPEN)

1. For a first bulk use case, should confirm default be whole-batch atomic (W), explicit group atomic
   (G), or no bulk write until inverse/rollback is implemented?
2. Which Task transformations are acceptable as a declarative allowlist (rename prefix/suffix,
   whitespace normalization, template substitution, schedule/status changes), and which require a
   draft or remain disabled?
3. Does Owner want private Tasks included in bulk selection when a PRIVATE-capable lease exists, and
   what provider/cache promise applies to before-images and inverse data?
4. Should “confirm all eligible” exclude stale/forbidden/invalid rows automatically, or require Owner
   to explicitly choose groups after exceptions are shown?
5. What minimum row-level before→after visibility is required before accepting a grouped preview? Is
   server-side export/download allowed, or must every row be expandable in UI?
6. Which search/filter semantics are product-stable enough to be typed now? Is full-text search needed,
   or are status/date/priority/pinned filters sufficient for first iteration?
7. Which route card/provider capabilities permit parallel read calls, prompt cache, conversation state
   or response cache, and what are the privacy/retention/invalidation promises?
8. How should very large selections be split: deterministic groups, user-selected groups, or a
   long-running operation with resumable checkpoints? What user-visible partial status is acceptable?
9. What is the owner-approved evidence policy for cached input, response cache and provider state in
   production-faithful STANDARD eval versus controlled diagnostic eval?
10. What review/error rate or measured transaction/latency/cost evidence is sufficient to move a
    candidate from research proposal to implementation contract?

## 11. Limitations and receipt

- External documentation was read 2026-09-22; provider behavior, limits, model identifiers, pricing,
  cache retention and SDK details can drift. No claim here proves current Mimi route capability.
- Microsoft Graph and Google AIP are design analogies, not dependencies or approved Mimi APIs.
- No benchmark, tokenization measurement, provider call, DB load test, browser test, eval, key access,
  runtime edit, migration, deployment or acceptance was performed. All limits and execution modes
  are proposals/open questions.
- A tool schema can improve parseability but cannot enforce authorization; deterministic server checks,
  privacy gates, CAS, frozen confirmation, idempotency and receipts remain mandatory.
- git diff --check: **PASS** after writing this artifact.
- Acceptance, commit and merge: **NOT RUN / not authorized**.
