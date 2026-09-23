# B13 — Current Mimi tool surface và bulk gap

Evidence date: 2026-09-22
Scope: read-only audit của origin/develop hiện tại (`HEAD=a4c7e81`, `origin/develop=a4c7e8152bc83a07451eedbf8c1ec8f9de0b3ddf`) và các Mimi contract/spec authoritative đã được research package dẫn chiếu. Không runtime/API/key/test/browser.

## 1. Kết luận ngắn

**FACT:** Provider-visible tool hiện tại chỉ có đúng một function `task.create.v1`; request gửi `tools: [TASK_CREATE_TOOL]`, parser cũng chỉ chấp nhận đúng một call tên đó. [`backend/app/agent/openrouter.py:52-90`](../../backend/app/agent/openrouter.py#L52-L90), [`backend/app/agent/openrouter.py:157-169`](../../backend/app/agent/openrouter.py#L157-L169), [`backend/app/agent/openrouter.py:194-220`](../../backend/app/agent/openrouter.py#L194-L220)

**FACT:** `ExecutionLease` lại cấp capability tuple gồm `task.create.v1` và `task.read.standard.v1`, `max_turns=1`, `max_tool_calls=1`, cost cap 0. [`backend/app/agent/contracts.py:37-53`](../../backend/app/agent/contracts.py#L37-L53), [`backend/app/agent/service.py:699-720`](../../backend/app/agent/service.py#L699-L720)

**FACT:** `task.read.standard.v1` không được đăng ký vào provider schema. Nó được hiện thực như server-side prefetch `list_standard_tasks(..., limit=10)` trước provider dispatch; prefetch này chỉ lấy task chưa xoá, `is_private=false`, sắp xếp `updated_at DESC, id DESC`, và trả các field id/title/status/priority/due/source_version/provenance. [`backend/app/agent/service.py:581-607`](../../backend/app/agent/service.py#L581-L607), [`backend/app/agent/service.py:695-720`](../../backend/app/agent/service.py#L695-L720), [`backend/app/agent/service.py:791-812`](../../backend/app/agent/service.py#L791-L812)

**INFERENCE:** Với yêu cầu “inspect 100 tasks”, Mimi hiện không thể model-call/tool-call đọc đủ 100 qua tool loop: mỗi provider turn chỉ nhận tối đa 10 task inline, và lease chỉ cho một turn/một tool-call. Muốn có toàn bộ 100 phải có đường ngoài provider-visible tool (nhiều request server/prefetch hoặc một capability mới). Đây là suy luận từ các bound nêu trên, chưa đo runtime.

**FACT:** Với yêu cầu “rename 100 tasks”, không có Mimi tool hoặc bulk endpoint cho task rename. HTTP task surface chỉ có `GET /tasks`, `GET /tasks/{id}`, `POST /tasks`, `PATCH /tasks/{id}`, delete/restore và item endpoints; `PATCH /tasks/{id}` nhận `TaskUpdate`, trong đó title là field đơn. [`backend/app/web/routers/tasks.py:54-81`](../../backend/app/web/routers/tasks.py#L54-L81), [`backend/app/web/routers/tasks.py:139-191`](../../backend/app/web/routers/tasks.py#L139-L191), [`backend/app/domain/tasks.py:182-217`](../../backend/app/domain/tasks.py#L182-L217)

## 2. Call-count map cho 100 task

Các con số sau là **INFERENCE từ static contract**, không phải runtime measurement.

| Scenario | Model/provider calls | Model-visible tool calls | App/network calls implied by current surface | Evidence / caveat |
|---|---:|---:|---:|---|
| Inspect 100 tasks through current Mimi turn | 1 provider call, but only 10 preloaded rows | 0 read-tool calls (read is not provider-visible) | 1 Mimi message request; no supported continuation for remaining 90 in same lease | `max_turns=1`, `max_tool_calls=1`; prefetch limit 10. [`service.py:699-720`](../../backend/app/agent/service.py#L699-L720) |
| Inspect 100 through existing `/api/mimi/context/tasks` | 0 provider calls if UI/client reads directly | 0 | At least 4 HTTP GETs at `limit=25` (or 10 at `limit=10`); endpoint has no cursor/filter/projection | [`backend/app/web/routers/mimi.py:379-385`](../../backend/app/web/routers/mimi.py#L379-L385) |
| Inspect 100 through general `/api/tasks` | 0 provider calls if client reads directly | 0 | At least 1 page at `limit=100` for a suitable status/range, but results are full `TaskRead` rows and not Mimi tool calls; cursor may require more pages | [`backend/app/web/routers/tasks.py:54-81`](../../backend/app/web/routers/tasks.py#L54-L81), [`backend/app/domain/tasks.py:756-775`](../../backend/app/domain/tasks.py#L756-L775) |
| Rename 100 tasks with existing task API | 0 provider calls | 0 | 100 `PATCH /api/tasks/{id}` requests; no bulk rename route or bulk body | [`backend/app/web/routers/tasks.py:163-175`](../../backend/app/web/routers/tasks.py#L163-L175) |
| Hypothetical one-row model read/write tools | Depends on orchestration | 100 read calls and/or 100 write calls | This is not current implementation; stated only as the user’s cost concern | No current provider schema supports it |

The phrase “100 tool calls” therefore describes the **missing design shape**, not an observed current Mimi execution. Current Mimi would either under-read (10 rows) or require an unimplemented multi-call continuation/bulk surface.

## 3. Existing reusable domain seams

### 3.1 Read/list/query seams

**FACT:** `TaskStore` already has a privacy-aware list path and a bounded keyset path. `list()` loads parent rows with `readable(...)`, applies status, limit/offset, and fetches all child items in one `IN (task_ids)` query; `list_cursor()` supports status, `from_instant`, `to_instant`, bucket, signed cursor, and `limit <= 100`. [`backend/app/domain/tasks.py:672-754`](../../backend/app/domain/tasks.py#L672-L754), [`backend/app/domain/tasks.py:756-812`](../../backend/app/domain/tasks.py#L756-L812)

**FACT:** The normal task API exposes `status`, `limit`, `cursor`, `from`, `to`, and `bucket`; its response is a `TaskPage` containing full `TaskRead` items plus cursor/count metadata. [`backend/app/web/routers/tasks.py:54-81`](../../backend/app/web/routers/tasks.py#L54-L81), [`backend/app/domain/tasks.py:240-247`](../../backend/app/domain/tasks.py#L240-L247)

**FACT:** Single-row `TaskStore.get()` is privacy-gated and loads checklist children; this is reusable for exact entity reads but is not exposed to Mimi as a provider tool. [`backend/app/domain/tasks.py:968-973`](../../backend/app/domain/tasks.py#L968-L973)

**FACT:** Mimi-specific `list_standard_tasks()` is a separate narrow projection, filters private/deleted rows before assembly, and has only a numeric limit argument. It has no cursor, date/status/search filter, field projection, or `data_as_of` parameter. [`backend/app/agent/service.py:581-607`](../../backend/app/agent/service.py#L581-L607)

### 3.2 Write/CAS/idempotency seams

**FACT:** Existing direct Task update is single-entity `PATCH`; `TaskStore.update()` loads one parent, optionally locks for privacy/status changes, updates fields, flushes, and returns one `TaskRead`. There is no expected entity version argument in `TaskUpdate`, no bulk update method, and no CAS predicate visible in this method. [`backend/app/domain/tasks.py:1037-1106`](../../backend/app/domain/tasks.py#L1037-L1106)

**FACT:** Task creation has an explicit UUID path with `ON CONFLICT DO NOTHING`, making an explicit-ID retry idempotent at create time; this is not a bulk rename/update contract. [`backend/app/domain/tasks.py:975-1015`](../../backend/app/domain/tasks.py#L975-L1015)

**FACT:** Mimi’s frozen change-set/confirm layer does have typed operation IDs, expected entity version field, digest, nonce and idempotency key in the contract; confirm uses an `Idempotency-Key` header and server-side change-set service. [`backend/app/agent/contracts.py:62-87`](../../backend/app/agent/contracts.py#L62-L87), [`backend/app/web/routers/mimi.py:388-399`](../../backend/app/web/routers/mimi.py#L388-L399)

**INFERENCE:** Those Mimi change-set primitives are reusable orchestration seams, but current provider parsing creates at most one `TaskCreate` proposal, and current Task update path does not prove a multi-row CAS/bulk mutation capability. Do not treat the existence of the generic contract as evidence that bulk rename is implemented.

### 3.3 Existing batch/bulk elsewhere

**FACT:** The repository contains reminder delivery batching (`tracker_reminder_batch` / `tracker_reminder_batch_item`) and other domain-specific grouped queries, but these are scheduler/domain internals, not Mimi Task list/rename tools. Search evidence includes [`backend/app/domain/reminder.py:480-580`](../../backend/app/domain/reminder.py#L480-L580) and [`backend/app/alembic/versions/0012_tracker_reminder_batch.py:41-173`](../../backend/app/alembic/versions/0012_tracker_reminder_batch.py#L41-L173).

**OPEN:** No authoritative code/spec evidence located in this audit defines a generic Mimi `batch`, `bulk`, projection, or multi-entity operation schema that could be safely reused for 100 Task renames.

## 4. Authoritative spec comparison

**FACT (spec):** The merged Mimi spec requires typed read tools with `filter/range/cursor/detail`; C0 reads are bounded, C2 includes bulk writes, and operations above 20 are split into related sets. [`C:\Users\os\Desktop\cur_docs\PTHTTM\btl\04-spec-hop-nhat-mimi.md:106-123`](file:///C:/Users/os/Desktop/cur_docs/PTHTTM/btl/04-spec-hop-nhat-mimi.md#L106-L123)

**FACT (spec):** The same spec requires server-side capability allowlist, typed validation, bounded tool results with stable IDs/cursors, and an initial registry including task, calendar, note, tracker, subscription and Mimi conversation/run context buffers. [`C:\Users\os\Desktop\cur_docs\PTHTTM\btl\02-spec-thuc-thi-mimi.md:724-768`](file:///C:/Users/os/Desktop/cur_docs/PTHTTM/btl/02-spec-thuc-thi-mimi.md#L724-L768)

**FACT (spec):** The spec says a related same-Neon change set is atomic, uses CAS at mutation, has scoped idempotency, and rejects stale zero-row mutations rather than silently retrying. [`C:\Users\os\Desktop\cur_docs\PTHTTM\btl\04-spec-hop-nhat-mimi.md:116-125`](file:///C:/Users/os/Desktop/cur_docs/PTHTTM/btl/04-spec-hop-nhat-mimi.md#L116-L125)

**FACT (code):** Current implementation has only the narrow Task P1 slice: server prefetch + one create proposal. The broader spec’s typed domain registry, read filter/range/cursor/detail surface, and bulk/CAS rename capability are not provider-visible in this code snapshot.

## 5. ExecutionLease/provider schema mismatch

| Layer | Declared/observed capability | Status |
|---|---|---|
| Lease | `task.create.v1`, `task.read.standard.v1` | **FACT:** server-issued tuple at [`service.py:709-720`](../../backend/app/agent/service.py#L709-L720) |
| Provider request | `tools: [TASK_CREATE_TOOL]` only | **FACT:** [`openrouter.py:157-169`](../../backend/app/agent/openrouter.py#L157-L169) |
| Provider parser | text XOR exactly one `task.create.v1` call | **FACT:** [`openrouter.py:194-220`](../../backend/app/agent/openrouter.py#L194-L220) |
| Server prefetch | `list_standard_tasks(limit=10)` | **FACT:** [`service.py:695-704`](../../backend/app/agent/service.py#L695-L704) |
| HTTP context endpoint | `/api/mimi/context/tasks?limit=1..25`, list only | **FACT:** [`mimi.py:379-385`](../../backend/app/web/routers/mimi.py#L379-L385) |

**INFERENCE:** `task.read.standard.v1` is currently a lease/audit label for server context assembly, not a provider-invocable schema. The names therefore overstate the provider-visible tool surface unless “capability” is intentionally defined to include server-only prefetch.

**OPEN:** Whether the intended contract should expose read capability as provider tool(s), preserve it as mandatory server prefetch, or support both is an Owner/T1 product/architecture decision. This report does not choose among them.

## 6. Gaps and NOT_RUN boundaries

- **GAP (FACT):** No provider-visible `task.list`, `task.get`, `task.query`, `task.rename`, `task.update_many`, or generic domain registry was found in current code.
- **GAP (FACT):** Mimi prefetch has fixed limit 10; context endpoint caps at 25 and has no cursor/filter/projection.
- **GAP (FACT):** Task update is one ID per HTTP route; no bulk rename route, typed multi-row expected-version list, transaction receipt for a 100-row set, or per-row failure/reconciliation contract was found.
- **GAP (INFERENCE):** A 100-task workflow cannot be completed by today’s single Mimi turn without either truncating inspection to 10, making repeated app requests outside the model, or adding a new bounded bulk/read capability.
- **OPEN:** Exact desired batch size, operation grouping, partial-failure policy, receipt granularity, and whether rename is C1/C2 remain unapproved here. The research package explicitly keeps exact thresholds and final implementation detail open. [`agent-tasks/2026-09-22-research-mimi-context/00-owner-decisions.md:53-59`](00-owner-decisions.md#L53-L59)

**NOT_RUN:** No provider dispatch, live API request, database query, browser journey, benchmark, token/cost measurement, or mutation was run. `git diff --check` was run after writing this artifact and is the only verification command recorded for this file.
