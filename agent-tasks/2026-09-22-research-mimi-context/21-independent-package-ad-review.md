# B20 — Independent ad-review and T1 reconciliation

Status: **COMPLETE — DOCUMENT REVIEW ONLY — NO RUNTIME/EVAL AUTHORITY**

Date: 2026-09-22

Target freeze:

- `19-final-context-system-policy-package.md` initial draft;
- `20-d10-eval-approval-packet.md` initial draft;
- branch `feat/061-mimi-context-research`;
- reviewer: T3 GPT-5.6 Luna, high effort, read-only;
- no file writes, provider/API call, `.env` access or runtime execution by reviewer.

Worker output is evidence. T1 independently inspected the final files and made every disposition
below.

## 1. Consolidated ledger

| Severity | Finding | T1 disposition | Final correction |
|---|---|---|---|
| P1 | B19 called itself P1C-A but included 100-Task grouping/materialization from P1C-B | ACCEPT | Removed bulk cases from D10 P1C-A; P1C-B now requires a separate eval amendment. |
| P1 | Lane P claimed production fidelity while unconditionally disabling response cache | ACCEPT | Lane P now mirrors an explicit P1C-A daily cache policy: prompt-prefix cache eligible/measured; provider conversation state and response cache disabled for the first canonical-replay release; future change creates a new route-policy/eval version. |
| P1 | Endpoint selection lacked a frozen route-card identity/expiry/binding | ACCEPT | Added two-phase preflight, endpoint-inventory digest, route-card ID/hash, <=24h expiry, exact provider/quantization/privacy/cache/fallback fields and per-call binding. |
| P1 | Token/price ceilings did not satisfy harness monetary failsafe | ACCEPT WITH CLARIFICATION | Tokens remain the primary bench envelope; added derived $0.03/$0.10 per-run and $1.75 aggregate emergency caps covering cache/fallback/retries/fees. |
| P1 | Provider-call arithmetic left no capability/retry reserve | ACCEPT | 192 is now explicitly 168 scenario-turn reserve + 6 lane capability calls + 18 reconciled transport retries; numeric token reserves are also bound for capability/retry calls. |
| P1 | 90% aggregate semantic PASS could hide a required-case FAIL | ACCEPT | All 42 required scenario runs must complete and pass; no aggregate percentage can mask FAIL/BLOCKED/NOT_RUN. |
| P2 | Manifest omitted QA/environment/isolation/route details | ACCEPT | Added QA hash, `APP_ENV`, database class, stable fixture IDs, route/tool/privacy/cache modes, context reserve and cleanup/isolation plans. |
| P2 | Direction approval lacked durable draft identity/revision | ACCEPT | Added `draft_id`, revision/content hash and explicit `approve_direction` actor/time/expected-revision event; it cannot confirm/write. |
| P2 | Canonical storage was not explicitly Neon | ACCEPT | B18 now states Neon is canonical; RAM/rootfs/provider state are discardable; schema work requires throwaway-Postgres upgrade/recovery proof. |

## 2. Additional T1 corrections

T1 found and corrected two related ambiguities during reconciliation:

1. **Preflight ordering:** a route card cannot exist before the endpoint metadata call that creates
   it. B19 now has a base manifest before Stage 0 and a frozen inference manifest afterward.
2. **Provider price ordering:** “combined price” was undefined. Endpoint ranking now uses the
   declared 4:1 input/output envelope (`4 × prompt + completion`) and intentionally does not assume
   a cache-hit rate.

T1 also retained a compatibility boundary for current `task.create.v1` callers while making
`task.create_candidate.v2` the proposed candidate contract; the compatibility adapter cannot own
a second preview/execution path.

The focused reviewer recheck initially marked the call/token reserve finding `PARTIAL`: call math
was correct but capability/retry token reserve was unnamed. T1 then bound those 24 calls to
0.24M input and 0.06M output/reasoning total and left 0.40M/0.10M unallocated safety headroom.

## 3. Final review result

No P0 finding remains. All P1/P2 findings above are reconciled in the final B18/B19 drafts.

This means only **document-review ready for Owner**. It does not mean:

- B18 or B19 is Owner-approved;
- P1C is implemented;
- deterministic QA or live eval passed;
- `MIMI_DEMO_1` may be read;
- a provider/model/route may be adopted;
- local dogfood, deployment or production acceptance is authorized.

## 4. Remaining Owner gates

1. Review/approve or amend B18 scope and exact static system-policy candidate.
2. Review/approve or amend every D10 checklist item in B19.
3. Give a separate implementation order before P1C runtime work begins.
4. Live provider execution remains blocked until implementation plus deterministic gates satisfy
   B19 prerequisites.
