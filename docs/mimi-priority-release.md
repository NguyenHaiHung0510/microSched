# Mimi collection and context priority release

Owner247 approval 2026-10-18 prioritizes collection/Confirm and context/Resume for
production. The release preset enables collection and explicitly leaves
notifications disabled for their separate acceptance lane. The model is
`deepseek/deepseek-v4.1-flash-1017`, HIGH by default with NONE/LOW/HIGH/MAX
selectable. Native OpenRouter keeps ZDR, deny data collection, fp8, manual price
caps and gateway fallback, without a local provider roster/catalog gate. Saved
old-model price caps carry forward (including USD0.36/1.44 per million); historical
run receipts remain unchanged.

Collection reads and freezes current Task selections, then presents a validated
preview. Questions and unrelated chat do not expire a preview. Replacement,
expiry, lost permissions and changed relevant sources still prevent stale
confirmation. Confirm validates all targets before one transaction; an identical
repeated decision returns the existing receipt.

Query cursors remain bound to their exact filter, projection, sort and limit.
An invalid cursor returns a bounded read-error result so the model can correct
its query within the existing run limits. It supplies no Task data, membership
or completeness evidence; other validation and access failures still halt.

Context uses a soft 272,000-token compact trigger and a 400,000-token operating
target. Provider usage is authoritative for total tokens, cache and cost;
composition measures serialized UTF-8 bytes rather than invented per-bucket
tokens. Native main and helper requests omit `max_tokens` and
`max_completion_tokens`, using provider output defaults. The 8,192-token context
planning reserve is neither a generation cap nor the monetary reserve. Local paid
QA reserves the shared configured context window at the greater input/output
manual price cap, including reasoning, without a model-MAX lookup service. Tokenizers remain
optional. Reconnect observes the same durable run;
unknown outcomes require reconciliation before redispatch. Existing finite
overflow recovery remains in place.

The opt-in local QA successor ledger uses `budget_mode="money_only"`: money,
expiry, ticket state and unresolved liability remain admission gates. Call/MAX
counts are observations; absent/null count caps do not gate this mode. The old
ledger remains read-only, with its historical known costs and full unresolved
holds carried forward without invented settlements. Legacy capped ledgers retain
their original count semantics. New unknown calls stop subsequent dispatch pending
inspection/reconciliation. Production does not use this private QA ledger.

Acceptance requires related deterministic/Postgres checks, two independent
premerge challenges (Luna and Gemini), synthetic full-app Chrome and actual-provider Mimi journeys, then current CI and
the exact deployed readiness commit, database status and flags. Tests with
provider doubles establish lifecycle/safety, not model quality or cache hits.
Connect, read-idle and total-run deadlines are distinct: SDK120s is not a total
run cutoff. Finite run/no-progress/recovery bounds and ambiguous-dispatch safety
remain. Manual Stop/Resume is rare secondary coverage, without an exhaustive
release matrix; network retry/recovery is a separate resilience path. Model
reasoning mistakes, slow but bounded MAX or safely failed/poor compaction are
reported as quality limitations without blocking unrelated delivery. Incorrect
previews are never confirmed; genuine privacy, authority, data loss, duplicate
write or uncontrolled-spend defects still need disposition. Product prompt or
context-selection/assembly semantic changes require concrete Owner presentation
before editing. Physical notification-device acceptance is outside this release.

After conditional develop merge/deploy and exact production verification, Main
prepares a separate release proposal for Owner approval before any main release.
Source preparation, develop approval and silence do not authorize main release.

Rollback of activation sets `MIMI_COLLECTION_ENABLED=false` through the normal
release flow. Retain conversations, execution receipts and schema; no database
rollback or data deletion is involved. Configuration in source is preparation,
not proof that a deploy or acceptance run has succeeded.
