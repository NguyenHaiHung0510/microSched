# B15 — Execution modes: NORMAL và scoped AUTO

Date: 2026-09-22
Status: **OWNER-APPROVED D8 — NOT IMPLEMENTED**

Scope: whether Mimi should always require confirmation of a frozen preview or also
support an automatic-write mode. This report does not authorize a runtime mode,
provider call, migration or live experiment.

## 1. Answer first

Research was necessary because “AUTO” crosses the authorization, privacy, recovery
and product-control boundary; it is not a prompt-only setting.

T1 recommends:

1. Keep **NORMAL as the only write mode in the next package**: Mimi may read,
   reason, produce a draft and prepare a frozen preview autonomously, but every
   write requires confirmation of that exact preview.
2. Do **not** expose `AUTO-READ` or `AUTO-PREPARE` as extra modes. Those are normal
   agent behavior under bounded read tools and do not write data.
3. Design a future **scoped automatic-execution grant**, not one global AUTO
   switch. A grant authorizes one typed operation family under field, selection,
   sensitivity, row/group, risk, time and route limits. It is revocable and
   receipt-backed.
4. Do not pilot automatic writes until the chosen operation has proven CAS,
   idempotency, atomic receipt, reconciliation and a real tested inverse/undo.

This preserves the approved `draft → direction approval → frozen preview → exact
confirmation → execute` contract now, while leaving a principled path to reduce
friction later.

## 2. Important naming boundary

Provider `tool_choice=auto` means the model may choose between returning text and
requesting a function. It does **not** authorize the application to perform a
write. The application still executes and validates the function. Google likewise
describes consequential function calls as actions the application should validate
with the user: [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling).

For Mimi:

```text
provider automatic tool choice != Mimi automatic execution authority
```

The word `AUTO` in the UI must therefore mean an application-owned grant, never a
provider parameter or model self-assessed confidence.

## 3. Evidence

### 3.1 Repository facts (`OBSERVED`)

- Current Mimi server already owns auth, privacy, source versions, lease, preview
  digest/nonce/expiry, idempotency, transaction and receipt. Model output is not
  authority. See [`backend/app/agent/models.py`](../../backend/app/agent/models.py)
  and [`backend/app/agent/service.py`](../../backend/app/agent/service.py).
- Current change-set states and confirmation flow assume an exact frozen preview;
  there is no automatic-execution grant model, grant generation, revocation fence
  or domain-wide inverse contract.
- Current provider-visible write is the narrow `task.create.v1`; bulk update,
  grouped CAS and verified undo are not implemented. See B13.
- PRIVATE unlock controls data capability. It does not currently grant permission
  to skip confirmation.

### 3.2 External engineering evidence (`OBSERVED`)

- OpenAI recommends risk-rating tools using reversibility, permissions and
  financial impact, and retaining human oversight for sensitive, irreversible or
  high-stakes actions until reliability grows:
  [A practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/).
- Anthropic describes user-configurable `always allow / needs approval / block`
  permissions and warns that prompt injection becomes more consequential as the
  tool set and autonomy grow:
  [Trustworthy agents in practice](https://www.anthropic.com/research/trustworthy-agents).
- OWASP frames excessive agency as excessive functionality, permission or
  autonomy; mitigations include least privilege, granular tools and approval for
  high-impact actions:
  [LLM06:2025 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/).
- Agents benefit from checkpoints, bounded iterations and environmental evidence;
  autonomy also compounds cost and error:
  [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents).

These sources support risk-scoped human control. They do not provide a numeric
threshold suitable for Mimi, so no number is promoted into policy.

## 4. Options and trade-offs

| Option | Benefit | Material problem | T1 disposition |
|---|---|---|---|
| Global `NORMAL / AUTO` toggle | Simple mental model and low friction | “AUTO” silently spans domains, fields and risk; hard to understand, revoke or audit | Reject |
| Per-domain AUTO (`Tasks auto`) | Narrower than global | Still too broad: rename, delete, schedule and private change have different risk | Reject |
| Confirm every write | Clear control, matches current contract | Review friction for frequent low-risk operations | Use now |
| Per-operation scoped grant | Least privilege; reusable for repeated safe operations | Needs policy schema, lifecycle, receipts, recovery and clear UX | Future target |
| Cancellable countdown before auto-write | Feels reversible | Closing the tab, disconnect or race makes countdown unreliable; does not replace authorization | Optional UX only, not a safety primitive |

The strongest case **for** AUTO is repeated, local, reversible normalization where
one confirmation per run adds little information. The strongest case **against**
AUTO now is that Mimi has not yet proven the persistence/reconciliation/undo and
bulk-CAS substrate that makes automatic failure bounded.

The nearest safe alternative is one confirmation for a complete grouped frozen
preview—not per row—and automatic preparation of that preview.

## 5. Proposed future grant contract (`PROPOSAL`)

A grant is created by the Owner through a reviewable policy, never by model text:

```json
{
  "grant_id": "opaque",
  "generation": 1,
  "mode": "scoped_auto_execute",
  "domain": "task",
  "operation": "title.normalize.v1",
  "allowed_fields": ["title"],
  "selection_constraint": {"is_private": false},
  "max_rows_per_run": "MEASURED_LATER",
  "max_groups_per_run": "MEASURED_LATER",
  "cumulative_budget": "MEASURED_LATER",
  "requires_reversible": true,
  "external_side_effect": false,
  "expires_at": "...",
  "policy_version": "...",
  "route_privacy_class": "standard",
  "revoked_at": null
}
```

The server, not the model, calculates eligibility from:

- operation/field allowlist and sensitivity;
- exact selection and completeness;
- source freshness/CAS and conflict state;
- reversibility/inverse proof;
- local versus external effect;
- row/group/cumulative budget;
- deadline, route policy, grant generation and revocation;
- prior failure, unknown outcome or recovery status.

Model confidence is not an authorization signal. `allow_private`, `skip_confirm`,
risk score or grant generation supplied by the model are ignored/rejected.

## 6. Initial action classes (`PROPOSAL`)

| Action | Next package | Future scoped AUTO |
|---|---|---|
| Bounded read/list/aggregate | automatic under C0 lease | Yes; this is normal agent work, not a write mode |
| Direct answer, draft, frozen preview preparation | automatic | Yes; no data mutation |
| Single local reversible Task write | explicit confirmation | Candidate only after inverse/CAS/recovery proof |
| Bulk/multi-record write | exact group/batch confirmation | Later candidate only for a proven typed operation |
| Delete, send/publish, permission/auth, financial/external action | explicit confirmation | Excluded by default |
| PRIVATE write | unlock plus explicit confirmation | Separate Owner-approved grant and stricter route/taint policy required |

Undo is not a button alone. A valid inverse must retain before/after, expected
version and idempotency; revalidate concurrent changes; distinguish unknown from
failed; and produce a new conflict/preview when an inverse is no longer safe.

## 7. UX consequences (`PROPOSAL`)

Until automatic writes exist, do not add a decorative NORMAL/AUTO selector.

When scoped AUTO exists:

- side-chat shows the effective grant in one compact line, current scope and a
  visible `Pause/Revoke` action;
- workspace exposes grant version, operation/fields, selection limits, expiry,
  consumed budget, automatic action log, conflicts, receipts and undo/reconcile;
- automatic run, waiting review, revoke requested and revoked are distinct states;
- PRIVATE expiry or grant revocation fences unstarted work and reconciles in-flight
  unknown outcomes before any retry;
- a route fallback that no longer satisfies the grant downgrades to NORMAL/preview,
  never silently keeps AUTO.

Both surfaces project the same durable run/grant/change-set state.

## 8. QA before any AUTO-write pilot

Deterministic RED → GREEN cases must cover:

- forged/missing/wrong-generation/revoked/expired grant;
- operation, field, sensitivity, selection or cumulative-budget escape;
- prompt injection in Task/tool data attempting to widen authority;
- stale source, partial selection, CAS conflict and privacy lock expiry;
- cancel/revoke races before dispatch, during provider read and during commit;
- crash before/after commit, late result and outcome-unknown reconciliation;
- duplicate requests/confirmation/retry with exactly one mutation receipt;
- inverse after no concurrent edit and inverse conflict after a concurrent edit;
- route fallback/privacy mismatch causing deterministic downgrade;
- side-chat/workspace convergence and no false “done” claim.

Probabilistic evaluation then measures false action, missed clarification,
unnecessary confirmation, review time, rollback success, stale/unknown rates,
latency, tokens and cost under the production-faithful route. No pilot threshold or
budget is approved here.

## 9. Owner decision D8

**OWNER-APPROVED 2026-09-22:**

- **D8-A:** NORMAL remains the only write mode in the next package; automatic
  bounded reads/reasoning/preview preparation continue without a fake mode toggle.
- **D8-B:** future AUTO means a scoped, expiring, revocable per-operation grant—not
  a global/per-domain switch and not provider automatic tool choice.
- **D8-C:** no AUTO-write pilot until one allowlisted reversible operation passes
  CAS/idempotency/atomic receipt/reconciliation/inverse QA; PRIVATE and external or
  irreversible actions remain confirmation-required by default.

## 10. Limitations

No runtime, API/provider call, route probe, browser, live data, threshold, rollback
test, migration or AUTO policy implementation was run. Current conclusions are
architecture/product recommendations grounded in repository evidence and cited
engineering sources, not acceptance evidence.
