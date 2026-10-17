# Mimi collection and context priority release

Owner approval 2026-10-17 prioritizes collection/Confirm and context/Resume for
production. The release preset enables collection and explicitly leaves
notifications disabled for their separate acceptance lane. Native OpenRouter
routing, model, effort, privacy and saved operating policy retain their values.

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
tokens. Tokenizers remain optional. Reconnect observes the same durable run;
unknown outcomes require reconciliation before redispatch. Existing finite
overflow recovery remains in place.

The opt-in local QA budget can carry separate historical settled cost, full
unresolved holds, dispatch count and MAX count. This preserves cumulative limits
without labeling an old unknown charge as settled. New unknown calls still stop
subsequent dispatch. Production does not use this private QA ledger.

Acceptance requires related deterministic/Postgres checks, independent review,
synthetic full-app Chrome and actual-provider Mimi journeys, then current CI and
the exact deployed readiness commit, database status and flags. Tests with
provider doubles establish lifecycle/safety, not model quality or cache hits.
Physical notification-device acceptance is outside this priority release.

Rollback of activation sets `MIMI_COLLECTION_ENABLED=false` through the normal
release flow. Retain conversations, execution receipts and schema; no database
rollback or data deletion is involved. Configuration in source is preparation,
not proof that a deploy or acceptance run has succeeded.
