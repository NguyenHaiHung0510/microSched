# B14 — Loop engine và harness cho Mimi

**Trạng thái:** RESEARCH / PROPOSAL — không phải runtime design hay approval triển khai
**Ngày research:** 2026-09-22
**Vai trò:** T3 read-only researcher
**Phạm vi ghi:** chỉ file này; không runtime/API/key/eval/browser, không commit

## 1. Câu hỏi

Mimi cần một vòng lặp server nào để:

1. thực hiện nhiều lượt đọc bounded mà không biến “đọc 100 Task” thành 100 tool call;
2. tách model turn, tool call, Owner input, draft, preview và execute;
3. sống sót qua disconnect, crash, deadline, cancel/halt/resume và kết quả provider không rõ;
4. cung cấp event/progress trung thực cho side-chat gọn và workspace minh bạch;
5. giữ deterministic authority ở server, còn model đảm nhiệm việc suy luận và chọn bước tiếp theo;
6. vừa đủ cho modular monolith, single-user microSched mà không dựng workflow platform quá sớm.

Nghiên cứu này nối các quyết định đã duyệt trong `00-owner-decisions.md`: D1 (server envelope + bounded iterative reads, giữ fixed prefetch/one-call fast path), D2 (adaptive interaction), D3 (microSched là canonical transcript/context; provider state/cache chỉ là tối ưu), D4 (progressive UX/checkpoint), và D5 (cache không bị cấm blanket; eval phải phản ánh STANDARD topology thực tế cùng lane chẩn đoán có kiểm soát).

## 2. Phương pháp và nguồn

Đã đọc `AGENTS.md`, `docs/harness-policy.md`, `docs/qa-agent-framework.md`, `docs/mimi-p0-contracts.md`, `docs/qa-specs/qa-mimi-p1-live-dogfood.md`, các file B00–B14 trong thư mục research, và các contract Mimi hiện hành trong `C:\Users\os\Desktop\cur_docs\PTHTTM\btl\04-spec-hop-nhat-mimi.md` và `02-spec-thuc-thi-mimi.md`.

Primary/official sources được đọc ngày 2026-09-22:

| Nguồn | Điều quan sát được dùng trong báo cáo |
|---|---|
| Anthropic, [How tool use works](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works) | Client loop dựa trên `stop_reason == tool_use`; app thực thi tool rồi gửi `tool_result`; loop kết thúc với terminal stop reason. Server tools có loop nội bộ và `pause_turn` cần continuation. |
| Anthropic, [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents) | Phân biệt workflows có control-flow định trước với agents tự chọn quy trình; nên bắt đầu bằng kiến trúc đơn giản và chỉ thêm evaluator/optimizer khi có tiêu chí đo được; tool interface cần được thiết kế/test kỹ. |
| Anthropic, [Streaming messages](https://platform.claude.com/docs/en/build-with-claude/streaming) | Stream có các event block start/delta/stop; stream có thể có error; SDK xử lý accumulation/reconnection nhưng app vẫn cần lifecycle contract riêng. |
| Anthropic, [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) | Cache bao phủ tools/system/messages tới cache breakpoint; TTL và cache hit là provider semantics, không phải canonical conversation state. |
| OpenAI, [Function calling](https://developers.openai.com/api/docs/guides/function-calling) và [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | Tool call là multi-step exchange giữa app và model; `strict` giúp args theo schema khi route/schema tương thích; đó không phải auth/commit authority. |
| OpenAI Agents SDK, [running agents](https://openai.github.io/openai-agents-python/running_agents/) | Runner quản lý turn/tool; có `max_function_tool_concurrency`; `RunState` có thể pause/resume và giữ pending approval/context. |
| OpenAI Agents SDK, [RunState](https://openai.github.io/openai-agents-python/ref/run_state/) | Run state là serializable pause/resume boundary; có model responses, generated items, pending input và `_max_turns`; history append lỗi cần reconcile thay vì chạy lại mù. |
| OpenAI Agents SDK, [guardrails](https://openai.github.io/openai-agents-python/guardrails/) | Tool guardrails chạy trước/sau từng function tool; blocking và parallel guardrail có trade-off về latency/cost/side effect. |
| OpenAI API, [webhooks/background responses](https://developers.openai.com/api/docs/guides/webhooks) | Background response có completion webhook; đây là provider-specific async primitive, không thay canonical app run state. |
| Google, [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling) | Model có thể gọi nhiều function trong một turn (parallel) hoặc gọi nối tiếp (compositional); app chịu trách nhiệm chạy function và gửi kết quả lại. |
| Google Cloud, [Vertex AI function calling](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling) | Có `AUTO`, `VALIDATED`, `ANY`, `NONE`; function schema/forced choice là capability route-specific. |
| Google, [parallel/compositional function calling](https://ai.google.dev/gemini-api/docs/generate-content/function-calling) | Calls độc lập có thể chạy song song; calls phụ thuộc phải tuần tự; response được ghép theo call id. |
| Google, [context caching](https://ai.google.dev/gemini-api/docs/caching) | Có implicit/explicit caching; cached tokens, TTL và cost là số liệu riêng; cache không nên là nguồn state duy nhất. |
| MCP, [server overview/tools](https://modelcontextprotocol.io/specification/draft/server/index), [pagination](https://ts.sdk.modelcontextprotocol.io/v2/api/%40modelcontextprotocol/client/client/client.html) | Tools là model-controlled; list operations có opaque cursor; client convenience có thể tự đi hết pages nhưng phải có page cap; deterministic ordering hỗ trợ cache. |
| MCP, [tasks/cancel](https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks) | Cancel là cooperative/eventually consistent; ack không chứng minh công việc đã dừng và terminal state có thể khác `cancelled`. |
| Temporal, [platform docs](https://docs.temporal.io/), Inngest, [durable execution](https://www.inngest.com/docs/learn/how-functions-are-executed) | Durable workflow lưu state/checkpoint, retry từng step và resume sau crash/network failure; đây là các tham chiếu so sánh, không phải đề xuất thêm dependency ngay. |

### Giới hạn nguồn

Các provider docs mô tả protocol/capability của từng API, không chứng minh route/model tương lai của Mimi, chất lượng suy luận, latency, memory hay cost thực tế. Các con số loop/tool/context/budget ở đây nếu không có raw receipt đều là `PROPOSAL`/`OPEN`, không phải benchmark. Không có provider call, runtime test hoặc paid eval trong batch này (`NOT_RUN`).

## 3. Kết luận ngắn

**PROPOSAL:** Mimi nên dùng **DB-backed bounded run state machine trong modular monolith**, với một worker/lease loop nhỏ, thay vì chỉ `while` trong HTTP request và cũng chưa cần Temporal/Celery/Redis. Giữ fixed server prefetch + one model call làm fast path; các request cần khám phá dùng cùng envelope nhưng cho model phát ra một hoặc một nhóm C0 read calls trong nhiều turn. Mỗi turn, tool intent/result, Owner interruption, checkpoint, budget và terminal outcome được ghi durable trước khi phát event.

Điểm quan trọng nhất cho câu hỏi “100 Task có thành 100 call không?” là **tool contract**, không phải sức mạnh model: một tool server-side phải đọc theo filter/cursor/projection và trả batch bounded hoặc summary + continuation; model không được phải gọi từng row. Các read calls độc lập có thể được server chạy song song trong một tool round, nhưng mọi giới hạn/concurrency/budget do server quyết định.

Đây là một **durable application run state machine**, không phải “provider conversation state có thêm vài UI event”. Provider continuation/cache có thể được dùng để giảm token/latency sau khi compatibility được kiểm, nhưng canonical transcript, tool receipts, checkpoints, owner decisions và recovery thuộc microSched.

## 4. FACT: loop/provider/workflow primitives

### 4.1 Model turn và tool call là hai loại bước khác nhau

- `FACT`: Anthropic mô tả chu trình: app gửi messages + tools → model trả `tool_use` → app chạy tool → gửi `tool_result` → gọi model tiếp. `stop_reason` khác `tool_use` là terminal/exception cần app xử lý.
- `FACT`: Gemini mô tả cùng một khái niệm nhưng cho phép cả parallel function calls và compositional/sequential calls. Model không tự chạy function.
- `FACT`: OpenAI function calling/Agents SDK cũng tách model generation khỏi local function execution; Structured Outputs/strict schema có thể kiểm tra hình dạng args nhưng không quyết định quyền đọc/ghi, freshness, owner confirmation, CAS hay idempotency.
- `INFERENCE`: adapter của Mimi cần chuẩn hóa provider response thành `model_turn`, `tool_intent`, `tool_result`, `provider_terminal`, `provider_error`, `provider_unknown`; không để provider-specific `stop_reason` trở thành domain state.

### 4.2 Parallel không đồng nghĩa với “mọi tool đều chạy cùng lúc”

- `FACT`: Google nêu calls không phụ thuộc nhau có thể chạy song song; calls có dependency phải tuần tự. OpenAI SDK có một giới hạn concurrency riêng cho local function execution, tách khỏi việc model có được phép emit parallel calls hay không.
- `FACT`: Anthropic cũng mô tả parallel tool use và cách tiếp tục khi có server/client tools trong cùng group.
- `PROPOSAL`: server phân loại tool bằng metadata `read_only`, `depends_on`, `side_effect`, `sensitivity`, `max_rows`, `max_bytes`, `timeout`, `concurrency_class`. Chỉ C0 read calls cùng round, không dependency và cùng privacy scope mới được fan-out; write/preview/confirm luôn qua sequential server gates.
- `OPEN`: exact concurrency và page/byte caps phải đo theo Fly memory/latency/provider receipt; không lấy ví dụ của provider làm số microSched.

### 4.3 Provider-native state và durable workflow là tối ưu/đối chiếu, không phải authority

- `FACT`: OpenAI Agents SDK có serializable `RunState`, max-turn bound, interruption/approval và resume. OpenAI background/webhook có provider-side asynchronous response. Gemini có stateful/cached modes; Anthropic có server-executed tool loop và prompt cache.
- `FACT`: Temporal/Inngest cho thấy durable execution lưu step/checkpoint bên ngoài process và retry/resume từ step đã thành công.
- `INFERENCE`: Mimi phải giữ application-owned ledger ngay cả khi dùng các primitive đó, vì chỉ microSched mới biết canonical conversation generation, privacy taint, preview digest, Owner approval, domain versions và late-result fence.
- `PROPOSAL`: provider state/cache được ghi thành `native_context_artifact`/optimization receipt với exact compatibility hash, frontier và expiry. Mất hoặc mismatch artifact chỉ làm chậm/rehydrate từ canonical state; không làm mất run hay đổi meaning.

### 4.4 Cancel/halt không phải một terminal result đáng tin

- `FACT`: MCP task cancellation là cooperative; acknowledgement không chứng minh execution đã dừng. Provider/network disconnect sau dispatch cũng không chứng minh provider chưa làm gì.
- `FACT`: Repo `docs/qa-agent-framework.md` yêu cầu `succeeded | failed | unknown` cho provider outcome; `unknown` phải reconcile trước redispatch.
- `PROPOSAL`: `cancel_requested`, `halt_requested`, `deadline_paused`, `resume_requested` là commands/events; state machine chỉ chuyển terminal khi đã có durable evidence. Cancel thắng trước bước chưa bắt đầu; in-flight provider call có thể vẫn `unknown`; late result phải bị fence theo generation/cancel/deletion policy.

## 5. So sánh kiến trúc

| Mẫu | Ưu điểm | Rủi ro/thiếu | Đánh giá Mimi |
|---|---|---|---|
| `while` trong request | Dễ viết; fast path thấp latency; ít bảng | Request timeout/crash làm mất loop; khó Owner wait; retry duplicate; không có durable frontier | Chỉ dùng cho adapter-level pure call hoặc fixed fast path có run record; **không đủ** cho long/bounded loop |
| DB-backed durable run state machine | Vừa đủ cho one-user; replay event/checkpoint; halt/resume/approval; dùng Postgres hiện có; provider-agnostic | T1 phải thiết kế state/event/idempotency/worker cẩn thận; không tự có distributed scheduling hoàn chỉnh | **PROPOSAL phù hợp nhất hiện tại** |
| Workflow/job engine ngoài (Temporal/Inngest/Celery/Redis) | Retry/lease/cron/fan-out đã trưởng thành; scale nhiều run | Dependency/ops/cost; duplicate authority; khó map preview/privacy semantics; overengineering cho single-user modular monolith | Giữ làm migration path khi có workload/availability evidence, chưa thêm ngay |
| Provider-native agent/session | Ít code loop; có continuation/cache/server tools | Vendor lock-in; semantics/retention/privacy/unknown outcome không đồng nhất; không chứa domain authority | Dùng optional optimization qua adapter, không làm canonical state |

**PROPOSAL:** mức tối thiểu không phải “chỉ một vòng while”, mà là **durable envelope + bounded loop**. Durable không đồng nghĩa dựng workflow platform; nó có thể là các row `ai_run`, `ai_turn`, `ai_tool_call`, `run_event`, `context_checkpoint`, `provider_result`, `change_set` và một worker lease trong monolith, nếu các invariants được kiểm bằng deterministic tests.

## 6. State machine tối thiểu

### 6.1 State và terminal union

Tên dưới đây là `PROPOSAL` để mô tả shape, không phải migration đã được duyệt.

```text
ACCEPTED
  → PREFLIGHTING
  → MODEL_TURN
  → TOOL_GATE → TOOL_RUNNING → TOOL_RESULT_DURABLE → MODEL_TURN
  → OWNER_INPUT_PENDING
  → CHECKPOINTED / COMPACTING / RECONCILING
  → TERMINAL
```

Các terminal result typed, không gom mọi thứ thành text:

```text
final_text | clarification | draft_text | preview_ready |
cancelled | halted | deadline_paused | budget_stopped |
failed | blocked | unknown_requires_reconcile
```

`preview_ready` vẫn chưa phải domain write. `draft_text` là reply chiến lược/thấu hiểu/option để Owner duyệt hướng; sau khi hướng được duyệt, một turn khác mới materialize implementation-detailed frozen preview. `preview_ready` chứa change-set ID/digest/expiry/expected versions; confirm không gửi lại payload tự do.

### 6.2 Envelope trước mỗi model turn

`FACT/PROPOSAL` từ repo contract: server phải re-check identity, sensitivity/taint, capability, lease, route, source versions, deadline, budget, pending steering và active preview trước mỗi egress/tool boundary.

Envelope tối thiểu:

- `run_id`, conversation generation, turn number, parent checkpoint/frontier;
- requested/effective route receipt, policy/tool-schema hash, provider-call identity;
- privacy/sensitivity + capability snapshot + revocation/lease status;
- bounded context manifest: source IDs/version/hash, omissions, stale/partial status, token/cost reserve;
- allowed tool registry snapshot, per-tool limits, remaining turn/tool/byte/time/cost budget;
- pending Owner input/steering and active draft/preview references;
- idempotency key/fingerprint for the next model/provider dispatch.

Model chỉ được suy luận trên envelope/context đã cấp. Nó không được tự tạo authority envelope, `allow_private`, `skip_confirm`, policy override hay raw SQL/URL/shell.

### 6.3 Checkpoint và compaction

- `FACT`: B04/D4 và `qa-agent-framework` yêu cầu canonical transcript/context có thể rehydrate, checkpoint nhìn thấy được, không silent truncation, và compaction không làm mất pending preview/steering.
- `PROPOSAL`: checkpoint lưu portable frontier, source range/hash, structured claims + epistemic status + source refs, token before/after, generation/validator version, status `PROPOSED → VALIDATED → ACTIVE/REJECTED`. Provider-native window/cache chỉ là optional artifact.
- `PROPOSAL`: auto-compaction là một server state transition với event `context.compaction_started`, `checkpoint.ready`, `context.compacted`; manual/rebuild/recovery tạo checkpoint mới, không rewrite message/event canonical.
- `OPEN`: route-specific token counter, compaction trigger, summary validator và encrypted/metadata-only retention phải được Owner chốt sau đo; các con số B08/B09 chưa phải evidence.

## 7. Tool harness: đọc 100 Task mà không cần 100 calls

### 7.1 Vấn đề

`INFERENCE`: nếu Mimi chỉ có `task.get(id)` và model phải tự enumerate từng ID, latency, provider round trips, prompt/tool-result tokens và failure surface tăng gần tuyến tính. Điều này là failure của tool contract, không phải lý do để ném toàn bộ domain table vào system prompt.

### 7.2 Shape đề xuất

Thay vì tool atom hóa theo row, expose C0 read tools có server-side query/batch semantics:

| Tool shape | Mục đích | Bắt buộc server trả |
|---|---|---|
| `task.list.v1` | filter theo date/status/tag/search, sort, cursor, field projection | stable IDs, bounded page, `next_cursor`, `complete/partial`, `data_as_of`, source/version refs, omitted count/reason |
| `task.inspect_batch.v1` | nhận một list ID hoặc server-issued selection handle, trả nhiều task trong một call | preserve requested order, per-item `found/forbidden/stale`, bounded byte/row count, continuation nếu overflow |
| `task.aggregate.v1` | count/group/facet/summarize deterministic fields trước khi model đọc rows | aggregate + query definition + data frontier + caveat; không tự viết prose authority |
| `task.read_window.v1` | lấy một range bounded cho planner sau khi aggregate chỉ ra vùng cần xem | cursor/range, stable IDs, source versions, omission/partial marker |

Tên chỉ mang tính minh họa; tool registry thật phải theo domain contract và capability receipt. `task.list` không được trả payload vô hạn chỉ vì model xin `limit=100000`; server clamp/reject và ghi omission.

**PROPOSAL — batch result envelope:**

```json
{
  "items": [{"id": "...", "fields": {"...": "..."}, "source_version": "..."}],
  "selection": {"filter_hash": "...", "sort": "...", "cursor": "..."},
  "next_cursor": "...",
  "completeness": "COMPLETE|PARTIAL|STALE|FAILED",
  "omitted": [{"reason": "BYTE_CAP|ROW_CAP|AUTH|STALE", "count": 0}],
  "data_as_of": "...",
  "manifest_ref": "..."
}
```

The model may ask for continuation, but server controls whether the next page fits remaining budget and whether it needs Owner clarification. A continuation is a new tool intent with the previous cursor/fingerprint, not an implicit unbounded loop.

### 7.3 100-Task scenario

Scenario: Owner says “xem toàn bộ 100 Task tuần này, đề xuất sắp xếp lại; chưa sửa gì”.

1. Server accepts run, mandatory preflight reads auth/privacy/current frontier and records `run_id`.
2. Fast path is eligible only if fixed union can answer safely; otherwise model gets `task.aggregate.v1` + `task.list.v1` capability, not `task.get`-100-times.
3. Model requests one filtered list. Server returns one or several bounded pages, possibly executing independent domain reads in one server round; receipt records page count, bytes, cursor, omitted/partial state.
4. If constraints are not covered, model requests one continuation or a narrow `task.inspect_batch` for selected IDs. If budget/coverage is insufficient, it asks a clarification or emits a draft with explicit omissions; it does not claim full inspection.
5. Model returns `draft_text`: strategic understanding, constraints found, conflicts, options and proposed direction. No mutation and no executable operation payload.
6. Owner approves the direction. Server starts a successor turn from the exact checkpoint/frontier; it may re-read changed source rows and then creates a frozen typed preview containing operation IDs, before/after, expected versions, group/tier, digest, expiry and conflict list.
7. Owner sees all grouped changes and confirms the exact digest. Server re-checks versions/lease/privacy/pending steering, then executes related groups atomically/idempotently. A crash after commit before event delivery is recovered from durable receipt; an unknown provider result is reconciled before any redispatch.

This gives “one/few bounded reads + explicit evidence” rather than 100 provider calls, while preserving the ability to inspect only the rows that matter. It does **not** promise that 100 rows fit one model context; server may summarize, page, checkpoint or ask.

### 7.4 Batch vs individual calls trade-off

- `FACT`: batching reduces round trips and enables server-side query plans, but large tool results increase context/serialization cost and can worsen model attention.
- `PROPOSAL`: use deterministic aggregates/projections first, then bounded detail pages; preserve stable IDs/provenance; let model request detail only where uncertainty/decision relevance justifies it.
- `PROPOSAL`: for independent C0 reads, parallelize inside the server tool round with a finite concurrency cap; for dependent reads, keep sequential. Never parallelize domain mutations merely because provider emitted parallel calls.
- `OPEN`: page size, max bytes, field projection defaults, aggregate cardinality and “enough evidence” policy need synthetic 100/1,000-row measurements and Owner approval.

## 8. Draft, preview và Owner steering

### 8.1 Draft/preview boundary

- `FACT` from Owner decision: draft is ordinary conversational strategic understanding/options/plan presented for direction approval; it is not executable or partially executable.
- `FACT` from Mimi contract: preview is frozen typed mutation set, with digest/CAS/expiry/confirmation; writes never happen before explicit confirm.
- `PROPOSAL`: model may emit `draft_text` or a typed `preview_candidate`, but only server creates `change_set` authority and only server can move to `preview_ready` after validation. A draft is not a hidden change set.
- `PROPOSAL`: small, explicit “do it now” may skip draft and go to preview candidate; broad/ambiguous/multi-domain/explicit planning normally stops at draft. Do not encode a hard entity-count threshold before Owner approves evidence.

### 8.2 Steering/inbox

- `FACT`: existing Mimi contract distinguishes harmless supplement from material change and requires impact evaluation; a message during an active run is not automatically a reason to discard a valid preview.
- `PROPOSAL`: server stores a per-run inbox with sequence and classifies pending input as `NO_CHANGE`, `MATERIAL_CHANGE`, `CONFLICT`, `CANCEL`, or `OWNER_APPROVAL`. Before the next model/tool boundary, the harness applies the command atomically with run generation; material change supersedes/rebuilds candidate, harmless supplement may preserve it with a recorded impact check, and conflict pauses for attention.
- `PROPOSAL`: Owner approval of a draft resumes a new implementation phase from checkpoint, never by asking model to “remember” the previous plan only from provider state.

## 9. Two-surface event/progress contract

### 9.1 Canonical state is shared

`PROPOSAL` required by the Owner’s new UI constraint: side-chat and Mimi workspace subscribe to the **same `run_id`, event sequence, checkpoint, preview/change-set and receipt**. Neither surface owns a second progress state or independently infers terminal status. Reconnect uses run ID + sequence cursor and converges to the durable snapshot.

The server emits bounded, versioned application events such as:

```text
run.accepted
run.phase_changed
context.reading
context.page_received
provider.connected
assistant.delta
tool.proposed
tool.validating
tool.completed
owner_input.required
checkpoint.created
preview.ready
conflict.detected
run.reconciling
run.paused
run.cancel_requested
run.terminal
heartbeat
```

Do not emit hidden chain-of-thought, raw private prompt, secret, partial tool JSON or fake token/progress percentages. `assistant.delta` is user-visible assistant prose only; tool events use sanitized names/args summaries and receipt links/IDs. Heartbeat proves observation channel liveness, not model progress.

### 9.2 Side-chat: quick/tinh gọn

`PROPOSAL`: side-chat is a compact observer and action surface. It shows only:

- current high-level phase (`Đang đọc`, `Đang suy luận`, `Đang chờ bạn`, `Preview sẵn sàng`, `Đang khôi phục`, terminal label);
- truthful elapsed time from server acceptance and, where available, coarse phase progress such as “đã đọc 3 trang / còn dữ kiện chưa tải” — never an invented percent;
- one attention sentence for missing facts, conflict, stale data, deadline or unknown outcome;
- the next valid CTA: `Xem draft`, `Xem preview`, `Bổ sung`, `Xác nhận`, `Xem kết quả`, `Reconcile`, `Resume`, `Hủy`;
- compact link/open action to workspace detail.

Side-chat must not maintain a separate abbreviated preview or silently hide a conflict that changes execution meaning. It may collapse detail visually, but CTA and terminal state are projections of canonical state.

### 9.3 Mimi workspace: full transparency, not overcomplexity

`PROPOSAL`: workspace is the detailed inspection surface, not a second agent. It can disclose:

- ordered phase/turn timeline and durable event sequence;
- context sources, pages/cursors, omissions, stale/partial markers and checkpoint frontier;
- sanitized tool reads: tool name, filter/range/projection, row/page counts, elapsed, outcome and provenance;
- provider route/effort requested/effective, cache/cost/token fields only when receipt-backed (`REPORTED`, `ESTIMATED`, or `UNAVAILABLE`);
- draft text and Owner direction decision;
- frozen preview grouped by change set/operation, before→after, expected version, conflict/stale reason, digest/expiry and exact CTA;
- recovery/unknown/cancel/deadline state, retry/reconcile count and durable receipt.

It should use progressive disclosure: a compact timeline first, expandable context/tool/receipt panels, and no raw hidden reasoning. Full transparency means “what the harness did, what data was selected/omitted, what is pending and what is authorized”, not exposing internal CoT or every provider wire byte.

### 9.4 UI trade-offs

- More detail improves Owner auditability and preview trust, but increases cognitive load and may expose sensitive metadata. Use disclosure and taint-aware redaction.
- A compact side-chat improves daily flow, but risks hiding stale/partial evidence. Show attention/CTA and provide one-tap workspace access whenever detail affects correctness.
- One canonical event stream avoids divergence, but event schemas must be bounded/versioned and replay-safe. UI-only derived labels are not durable truth.
- `OPEN`: exact presentation levels, mobile fold behavior, event payload redaction and which route/usage fields are safe for STANDARD vs PRIVATE remain UX/Owner decisions; local synthetic preview is required before acceptance.

## 10. What model suy luận vs server harness bảo đảm

| Model may reason/propose | Server must decide/enforce |
|---|---|
| Interpret user intent; identify missing facts; choose a permitted C0 tool and typed args; decide whether additional bounded evidence is useful; summarize evidence; propose options/draft; propose typed operation candidate; explain uncertainty/conflicts | Auth/session/owner identity; STANDARD/PRIVATE taint; capability and tool registry; row/byte/page/deadline/concurrency/cost bounds; route/policy/provider eligibility; schema/normalization; source freshness/version; whether draft or preview is allowed; preview digest/nonce/expiry; Owner approval; CAS/transaction/idempotency; result fence/reconciliation; event ordering/replay; retention/deletion and audit |

Structured outputs help parse/validate model proposals but do not make model text authority. Deterministic pre/post tool gates are mandatory even when provider offers strict schemas or native guardrails. A second LLM may be considered for semantic quality/offline evaluation, but must not be the safety gate or domain authorizer.

## 11. Failure/recovery matrix

| Failure/event | Canonical state/handling (PROPOSAL grounded in existing contract) | UI claim |
|---|---|---|
| HTTP/SSE disconnect before terminal | Keep run server-owned; reconnect by `run_id` + cursor; inspect durable provider call | Side-chat “Mất kết nối quan sát; đang kiểm tra run”, not “failed” |
| Provider response after dispatch but no durable result | `OUTCOME_UNKNOWN`; reconcile provider identity/result before retry | Workspace shows unknown/reconcile CTA; no duplicate dispatch |
| Crash after domain commit before event | Read transaction receipt/change-set/idempotency; append missing event/materialize once | Same preview/receipt after reload; no second mutation |
| Tool result timeout | classify retryable/definitive/unknown; retry only policy-allowed idempotent read; checkpoint otherwise | Honest phase + retry/revise CTA |
| Budget/deadline reached | persist checkpoint and `deadline_paused`/`budget_stopped`; no silent truncation or fallback | “Đã tạm dừng ở checkpoint”; Resume if safe |
| Owner cancel during tool/provider call | record intent; stop unstarted work; reconcile in-flight; fence late result | Cancel requested vs cancelled remain distinct until evidence |
| Source version changed before preview/confirm | stale/conflict; rebuild/read fresh, never silently latest-write | Workspace highlights affected operations; side-chat attention CTA |
| Steering changes plan | classify no-impact/material/conflict; preserve or supersede candidate via generation/CAS | Side-chat says “cần xem lại preview” only when actually superseded |
| Compaction interrupted | keep previous active checkpoint; validate new checkpoint before activation | Workspace shows recoverable checkpoint; no lost transcript claim |
| Model loops same tool/args or no frontier progress | server loop detector stops/pauses with reason; no model self-override | “Không có thêm dữ kiện mới; cần chỉ dẫn” |

## 12. QA/harness requirements

### 12.1 Deterministic contract plane

At minimum, disposable DB/fake provider tests must cover:

- fixed prefetch one-call fast path and iterative loop produce equivalent answer/coverage on same fixture where both are applicable;
- one `task.list`/`inspect_batch` handles 100 synthetic tasks with bounded pages, cursor continuation, byte/row cap, omission and source provenance; no per-row provider call;
- independent reads parallelize only within server cap; dependent reads remain ordered; write tools never execute in parallel accidentally;
- malformed/oversized/unknown tool args, forged `allow_private`, wrong generation, wrong policy/schema hash and partial/STALE/FAILED result fail closed;
- max turns/tool calls/pages/bytes/deadline/cost admission and loop detector stop deterministically;
- event sequence monotonicity, reconnect replay/dedup, side-chat/workspace convergence and no duplicate terminal/preview;
- pending Owner input, steering no-impact/material/conflict, draft approval, preview revision, reject, expiry and confirm race;
- unknown provider outcome, late result, retry identity, idempotent domain commit, crash before/after durable result and crash after domain commit;
- compaction checkpoint validation, recovery, stale source and pending preview preservation;
- no raw hidden reasoning/secret/private bytes in public events, logs, workspace redacted view or provider payload outside allowed sensitivity.

Every new safety guard needs intentional RED (violate the intended invariant) → restore → GREEN, per QA framework.

### 12.2 Probabilistic/route plane

After deterministic plane passes and Owner authorizes a route card, semantic tests should compare:

- ordinary chat/read-only answer vs clarification;
- broad 100-Task request → strategic draft, not auto-preview/write;
- Owner draft approval → implementation preview with all material changes explicit;
- narrow “do it now” → preview only when intent/data are sufficient;
- tool selection, evidence coverage, language, uncertainty and no fabricated completeness;
- side-chat concise event projection vs workspace detailed projection;
- provider cache/fallback behavior, actual route, token/cache/cost/timing receipts.

Production-faithful STANDARD acceptance must exercise the actual approved daily routing/cache/fallback topology (D5). A controlled exact-pin/no-fallback lane remains useful for attribution and diagnosis, but must not be substituted for the daily topology when making daily-behavior claims. No model list, repetition count, judge, budget or score threshold is approved by this research.

### 12.3 Evidence claims

Use the repo ladder A0–A5. `PASS` requires raw evidence for the exact case; route probe is not full-app behavior; provider mock is not conversation quality; local/browser viewport is not physical device/production. Unrun runtime/eval/browser layers remain `NOT_RUN`/`UNVERIFIED`.

## 13. Alternatives and trade-offs

### A — Fixed union only

Best latency/predictability and simple provenance; overfetches fields, handles known intents well, but brittle for broad/ambiguous/multi-domain questions. Keep as baseline/fast path and eval comparator.

### B — Unbounded autonomous loop

Flexible but risks tool explosion, context bloat, cost/latency runaway, repeated reads, stale assumptions and difficult recovery. Reject as harness policy; no unbounded model-controlled loop.

### C — Bounded iterative loop with durable state (recommended proposal)

Supports progressive evidence and Owner handoff while keeping finite resources, replay and no-write boundary. Costs more implementation and potentially more model/tool round trips; batch tools, aggregates, checkpointing and fixed fast path reduce cost.

### D — Full durable workflow engine now

Strong recovery primitives but adds operational surface, dependency and split authority before microSched has measured need. Keep as future migration option if run volume, uptime or scheduling complexity exceeds monolith envelope.

## 14. Owner decisions, proposals and open questions

### Already approved and carried forward (`FACT` / Owner decision)

- D1 hybrid server envelope + bounded iterative read loop; fixed prefetch one-call fast path/baseline.
- D2 adaptive draft/preview interaction; no fixed entity-count threshold.
- D3 canonical microSched transcript/context; provider state/cache optional rehydratable optimization.
- D4 progressive UX, visible checkpoint/compaction, receipt-backed context/model status.
- D5 cache is allowed subject to privacy/security; daily STANDARD eval must reflect actual routing/cache/fallback topology plus controlled diagnostics.
- Draft = strategic conversational plan for direction approval; preview = frozen implementation-detail change set awaiting explicit confirmation.
- New UI constraint: side-chat quick/tinh gọn; Mimi workspace full transparency via progressive disclosure; both project one canonical run/preview state and do not expose hidden CoT.

### Proposals for Owner/T1 review (`PROPOSAL`)

1. Implement a DB-backed bounded run state machine/worker in the monolith; do not add Temporal/Redis/Celery until evidence requires it.
2. Define composite/batch C0 read tools with cursor/projection/aggregate/byte bounds; never require one model tool call per Task.
3. Persist model turns, tool intents/results, owner inbox, checkpoints, provider outcome and event sequence before emitting UI observation.
4. Make provider state/cache attachable and discardable; rehydrate from canonical state on mismatch.
5. Keep side-chat and workspace as projections of one event log/snapshot with different disclosure levels.
6. Use model for interpretation/planning/tool proposal and server for all authority, deterministic safety and commit-time checks.

### Open (`OPEN`)

1. Exact state enum/row schema and worker lease implementation.
2. Per-route input/output/context counting method, page/byte/tool/turn/time/cost caps.
3. Which tools support batch/aggregate semantics across Notes, Calendar, Tracker and Subscription, and their C0/C1/C2 classification.
4. How to represent “complete enough evidence” without a hard entity-count threshold.
5. Exact loop detector (repeated call fingerprint, no-frontier-progress, budget/time policy) and whether any Owner override exists.
6. Compaction trigger/validator, checkpoint payload, retention and provider-native artifact compatibility.
7. Provider adapter guarantees for cancellation, idempotency, reconciliation identity and usage/cache fields.
8. UI event redaction per sensitivity and detailed workspace information architecture/mobile folding.
9. Owner-approved route, model, effort, cache/fallback policy and later eval matrix/budget/repetitions/judge.

## 15. Evidence/limitations receipt

- **Observed:** official docs and repository contracts listed above were read on 2026-09-22; current research package and Owner decisions were consulted.
- **Inferred:** provider-neutral loop/state separation, batch-tool recommendation, monolith durable state-machine fit and two-surface projection model.
- **Proposed:** all design choices explicitly labelled `PROPOSAL`; none is implementation authorization.
- **Not run:** runtime/API/provider call, browser, key use, latency/memory benchmark, 100-task load, paid/live eval, schema migration, deployment and production acceptance.
- **No claim:** no current model/provider label, cache hit rate, cost, latency, token limit or route capability is certified by this report.

### Local verification

`git diff --check`: **PASS** (run after writing this file).
`git status/diff`, commit, PR, merge and acceptance: **NOT RUN / not authorized**.
