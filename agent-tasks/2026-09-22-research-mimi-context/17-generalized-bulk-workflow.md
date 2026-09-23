# B16 — Generalized bulk workflow: query, classify, plan, materialize

Date: 2026-09-22
Status: **OWNER-APPROVED revised D6 — NOT IMPLEMENTED**

Scope: generalize beyond the example “rename 100 Tasks” to the real need: inspect
many records, filter/facet/cluster/rank/classify them, compare strategies, obtain
Owner direction, and only then build an explicit multi-change preview.

## 1. Answer first

The previous `typed transform OR bounded ID → patch mapping` proposal is necessary
but too narrow. Those are good **mutation leaves**; they are not a complete
workflow abstraction.

T1 recommends a dual path:

1. **Explicit fast path:** small, fully specified operation or a homogeneous
   deterministic transform.
2. **General workflow path:** bounded query/aggregate → selection snapshot →
   evidence-backed grouping/strategy candidate → conversational draft → Owner
   direction → server materialization → grouped frozen preview → exact confirm →
   atomic execute/reconcile.

The generalized internal representation is a hierarchical `WorkflowPlan`, but it
must remain small, typed and server-validated. It is not a new programming language
and does not authorize arbitrary code.

## 2. Generalization discipline

A hard case is used as a **probe**:

```text
example symptom → underlying jobs → competing abstractions → smallest extensible
design → counterexample/adversarial cases → bounded first vertical slice
```

For “rename 100 Tasks”, the underlying jobs are not just batch update:

- discover the exact population and know whether coverage is complete;
- summarize/facet it without stuffing every row into one prompt;
- detect meaningful classes and exceptions;
- compare a strategy for each class;
- explain the strategic proposal to the Owner;
- turn only the approved direction into exact before→after operations;
- review, confirm, execute and recover at group/batch level.

This rule is recorded in B00 so future T1 work does not overfit one difficult
example. It is a reasoning/research constraint, not a new harness authority rule.

## 3. Evidence

### 3.1 Current repository (`OBSERVED`)

- Provider-visible Mimi exposes only `task.create.v1`; the current Task read name is
  server prefetch, not a model-callable read tool. Current lease is one model turn
  and one tool call. See B13.
- Direct Task API can page up to 100 Tasks, but update remains one `PATCH` per Task;
  no multi-row CAS/bulk rename exists. See
  [`backend/app/web/routers/tasks.py`](../../backend/app/web/routers/tasks.py) and
  [`backend/app/domain/tasks.py`](../../backend/app/domain/tasks.py).
- Mimi already has encrypted change-set, digest/nonce/expiry, idempotency and
  receipt seams, but current service materializes one Task-create operation, not a
  generalized operation graph. See
  [`backend/app/agent/models.py`](../../backend/app/agent/models.py) and B12/B13.

### 3.2 External design evidence (`OBSERVED`)

- Pagination tokens should preserve the original request semantics and remain
  opaque rather than becoming editable query state:
  [Google AIP-158](https://google.aip.dev/158).
- Synchronous batch update is normally atomic; a partial-success design needs an
  explicit long-running operation/error mapping contract:
  [Google AIP-234](https://google.aip.dev/234).
- An outer batch success does not prove every inner action succeeded; individual
  correlation and outcomes remain necessary:
  [Microsoft Graph JSON batching](https://learn.microsoft.com/en-us/graph/json-batching).
- PostgreSQL Read Committed can see a new snapshot per statement. A reviewable
  preview that was created earlier therefore still needs application-level source
  versions/CAS at confirmation and commit:
  [PostgreSQL transaction isolation](https://www.postgresql.org/docs/17/transaction-iso.html).
- Parallel function calls are useful for independent reads, not permission to run
  dependent writes concurrently:
  [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling).

No external pattern proves exact page, group, token or row limits for Mimi. Those
remain workload measurements.

## 4. Minimal generalized architecture (`PROPOSAL`)

### 4.1 Bounded evidence tools

Model-callable reads:

- `task.query.v1`: filter, range, projection, stable sort and opaque cursor;
- `task.aggregate.v1`: count, facet, group and bounded summary;
- `task.inspect_batch.v1`: targeted detail for bounded IDs/selection subsets.

All results include source/version frontier, query hash, `data_as_of`, completeness
(`COMPLETE|PARTIAL|STALE|FAILED`), omissions/reasons and next cursor. An auth/private
filter or byte cap must not masquerade as an empty complete result.

Use aggregate/facet first, projection pages second and detail only for relevant or
uncertain groups. The server may fan out independent C0 reads with a finite cap;
dependent reads and all write transitions remain ordered.

### 4.2 Selection snapshot

For multi-record work the server freezes:

- canonical query/filter/sort/projection hash;
- exact visible IDs and source versions (or a bounded immutable reference);
- completeness/omission and sensitivity scope;
- tool/policy version, evidence frontier, expiry and digest.

`selection_ref` proves which evidence a candidate used. It is not a bearer token for
write authority. Preview/confirm still revalidate access and versions.

### 4.3 Candidate grouping and strategic draft

The model can return a typed **plan candidate** as part of its terminal output:

```json
{
  "selection_ref": "...",
  "coverage": "COMPLETE|PARTIAL",
  "groups": [
    {
      "group_id": "exam-near",
      "members_ref": "...",
      "evidence_refs": ["..."],
      "strategy_options": [
        {"strategy_id": "a", "kind": "task.title_template.v1", "params": {}},
        {"strategy_id": "b", "kind": "no_change", "params": {}}
      ],
      "recommended_strategy": "a"
    }
  ],
  "uncertainties": []
}
```

This is **not a model-callable mutation tool and not authority**. It is validated
structured output supporting the ordinary conversational draft. The user-facing
draft remains prose that explains understanding, groups, options, consequences,
coverage and questions. Owner approval chooses a direction; it does not confirm
writes.

The server rejects overlapping membership when the contract requires a partition,
unknown/unclassified IDs when completeness is claimed, strategy kinds outside the
allowlist, forged privacy flags and a `COMPLETE` claim over partial evidence.

### 4.4 Internal WorkflowPlan and mutation leaves

After Owner direction, the server reopens the approved checkpoint, re-reads stale
sources as necessary and constructs a typed internal tree/DAG:

```text
WorkflowPlan
├─ selection/evidence frontier
├─ group A → selected strategy → mutation leaves
├─ group B → selected strategy → mutation leaves
└─ dependencies/invariants/completeness
```

Mutation leaves are:

1. **Deterministic transform:** prefix, suffix, whitespace/case normalization or
   an approved template. Server calculates every before/after.
2. **Bounded semantic mapping:** exact ID → typed patch + evidence reference +
   reason code for cases that cannot be expressed deterministically.

No Python, JavaScript, SQL, arbitrary regex, URL or model-controlled executable
code. Mapping pages do not execute while being generated.

### 4.5 Server materialization

`workflow.materialize` is a server transition, not an unrestricted provider tool:

```text
approved direction + current selection/source versions
→ validate plan and invariants
→ materialize exact operations
→ capture before/after, expected versions and inverse metadata
→ calculate group/top-level digests
→ freeze preview
```

Each operation has stable ID, entity ID, group path, before/after, expected version,
dependency, reason/evidence references, reversibility and sensitivity. Conflicts,
no-ops, forbidden rows and omissions are explicit preview groups, not silently
dropped records.

## 5. Execution semantics (`PROPOSAL`)

- `WHOLE_BATCH_ATOMIC`: one measured-safe transaction; any invalid/stale member
  makes zero writes.
- `GROUP_ATOMIC`: each explicit deterministic group is all-or-nothing; dependency
  order is declared. Owner confirmation binds exact group digests/scope.
- `PER_ITEM`: disabled initially; if introduced, it requires explicit Owner choice,
  per-item durable outcomes and a partial-success UX.

Never silently downgrade whole-batch to groups/items after a timeout. An unknown
group outcome is reconciled by operation/group/idempotency identity before retry.
Batch transport, selection authority and transaction atomicity are three separate
properties.

## 6. Preview UX

There is one canonical `preview_id/change_set_id`.

Side-chat stays compact:

- groups/changed/no-op/conflict/omitted counts and completeness;
- current phase, expiry and blocking attention;
- one CTA to view draft/preview/reconcile;
- confirm only when every material change fits with no hidden row/conflict.

Workspace provides:

- group/strategy tree and the Owner-selected direction;
- compare strategy consequences before materialization when applicable;
- frozen search/filter/sort and paged before→after rows;
- stale/forbidden/invalid/omitted exception groups;
- confirmation at exact all/group digest scope;
- source frontier, tool and execution receipts under progressive disclosure.

A sample or collapsed rows can never be labelled as the whole reviewed set. There
is no raw hidden chain-of-thought.

## 7. Avoiding premature complexity

The generalized model should not force every narrow request through a plan DAG.

First implementation slice should prove:

1. Task query + aggregate/facet + targeted inspect with truthful completeness;
2. selection snapshot;
3. one strategic grouping/draft path over synthetic 100-Task data;
4. deterministic title-normalization/template leaves;
5. grouped frozen preview and whole/group-atomic execution;
6. bounded semantic mappings only after size/context measurements.

Cross-domain plans, arbitrary ranking functions, schedule/status/private bulk
changes and asynchronous partial execution are later capability packages. A simple
`batch_update(requests[])` remains a useful fast path when exact IDs/patches are
already known; it is not the general architecture.

## 8. QA and evaluation

Deterministic tests:

- cursor preserves original query; aggregate/facet agrees with 100/1,000-row
  synthetic fixtures;
- complete/partial/stale/failed and omission counts cannot be forged;
- exact partition coverage, no duplicate/unknown/unclassified selected IDs;
- plan dependency graph is acyclic and all strategies/leaves are allowlisted;
- same snapshot + deterministic plan produces the same digest;
- no write during query, candidate, draft, direction approval or materialization;
- CAS conflict/preview expiry/selection expiry fail at the right boundary;
- whole-batch failure writes zero rows; group atomicity and dependencies are exact;
- idempotent retry, crash before/after commit and unknown reconciliation;
- side-chat/workspace converge on one preview/digest and disclose omissions;
- private/secret/hidden-reasoning bytes do not leak through tools/events/logs.

Probabilistic evaluation compares per-item, batch-array, query/snapshot/materialize
and aggregate/targeted-drill-down topologies on coverage, classification/strategy
quality, Owner review error/time, provider/tool calls, tokens/serialized bytes,
latency, stale/conflict/unknown rates and cost. The production-faithful route is the
acceptance lane; exact-pin/no-fallback is diagnostic. No thresholds or budget are
approved here.

## 9. Owner decision D6 (revised)

**OWNER-APPROVED 2026-09-22:**

- **D6-A:** dual path: explicit operation fast path plus generalized bounded
  query/aggregate → selection → plan candidate/draft → approved direction →
  server-materialized frozen preview.
- **D6-B:** typed transforms and bounded ID→patch mappings are mutation leaves
  inside a hierarchical WorkflowPlan, not the whole architecture; no arbitrary
  executable DSL.
- **D6-C:** whole-batch atomic when measured-safe, explicit group atomic otherwise,
  no silent per-item partial execution initially.
- **D6-D:** first vertical slice is Task analysis/grouping plus safe title
  normalization/templates; broader semantic mappings and other domains follow
  evidence rather than being bundled into the foundation.

## 10. Limitations

No implementation, DB transaction/load test, provider call, context-size
measurement, browser preview or live data was used. WorkflowPlan shape is a T1
proposal built from repository evidence, independent critique and cited primary
engineering guidance; exact schemas and budgets remain implementation/eval work.
