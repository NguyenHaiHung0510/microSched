# B17 — Mimi storage tiering and recovery

Date: 2026-09-22
Status: **T1 SYNTHESIS — OWNER DECISION REQUIRED — NOT IMPLEMENTED**

Scope: how Mimi should use Fly RAM, the Machine root filesystem, browser memory
and Neon without assuming that faster/closer storage is durable or authoritative.

## 1. Answer first

Mimi already has a concrete storage architecture, but it is effectively **RAM +
Neon** today:

- Neon contains the canonical encrypted conversation/run/change-set/receipt state;
- RAM supervises active coroutines and ordinary application/query state;
- Fly rootfs is not used as a Mimi runtime cache/checkpoint tier;
- browser persistent storage is not canonical Mimi content;
- `MimiEvidence.content_ref` is a schema seam, not an implemented object store.

T1 recommends keeping Neon canonical and adding a narrow **disposable scratch/cache
tier** on rootfs only when measurement shows it helps. The sequence is not a write-
through hierarchy where every byte moves RAM → disk → DB. Classify data first:

```text
live working set → RAM
rebuildable bounded local bytes → ephemeral rootfs (optional)
authority/recovery/audit → Neon
large durable artifacts later → encrypted object storage + Neon pointer
```

The Owner's “about 8GB Docker” should not be treated as confirmed capacity. The
current repo defines 512MB RAM and 512MB swap, but not rootfs size, persistence or a
mounted volume. Exact production space/free bytes remain runtime evidence.

## 2. Current inventory (`OBSERVED`)

| Data | Current location | Evidence |
|---|---|---|
| Conversation metadata, DEK wrapper, generation/frontier | Neon | [`backend/app/agent/models.py`](../../backend/app/agent/models.py) |
| Messages and title | Neon; encrypted conversation-bound ciphertext | same |
| Run state, lease, source versions, deadline | Neon | same |
| Event sequence | Neon JSONB | same |
| Provider-call intent/state/route/result summary/usage | Neon | same |
| Frozen change-set operation | Neon; encrypted | same |
| Receipt, idempotency and refresh marker | Neon | same |
| Feedback | Neon; sensitive text encrypted | same |
| Evidence | Neon metadata + nullable `content_ref`; no runtime object adapter found | same |
| Active run coroutine lifetime | process RAM | [`backend/app/agent/runtime.py`](../../backend/app/agent/runtime.py) |
| Browser Mimi queries/composer | React/TanStack process memory | [`frontend/src/MimiScreen.tsx`](../../frontend/src/MimiScreen.tsx) |
| Browser persistence | pinned conversation UI preference uses `localStorage`; canonical transcript/run does not | [`frontend/src/MimiControlCenter.tsx`](../../frontend/src/MimiControlCenter.tsx) |
| Local encrypted feedback store | P0 synthetic review helper, not production runtime | [`backend/app/agent/feedback_store.py`](../../backend/app/agent/feedback_store.py) |
| Fly rootfs/Mimi cache | no rootfs Mimi adapter or `[mounts]` in current topology | [`fly.toml`](../../fly.toml) |

Current Fly configuration is one 512MB shared-CPU Machine in `sin`, 512MB swap,
`auto_stop_machines=false`, `min_machines_running=1`, no volume mount and no
`persist_rootfs` entry. Therefore the Owner's older intention that Neon automatically
idles while Mimi is inactive is not established by current Fly topology; an always-
running app may still allow Neon compute to suspend only if no DB activity wakes it.

## 3. Platform facts (`OBSERVED`)

- Fly documents the normal Machine root filesystem as ephemeral and suitable only
  for temporary data/application/runtime files that can be rebuilt. It also warns
  that ephemeral disk performance is capped (about 2,000 IOPS and 8 MiB/s):
  [Fly Volumes overview](https://fly.io/docs/volumes/overview/).
- Restart/deploy/Machine update can wipe the ephemeral filesystem:
  [Restart apps or Machines](https://fly.io/docs/apps/restart/).
- Fly now exposes `persist_rootfs = never|restart|always`, but the repository does
  not enable it. Persisting rootfs would be a deployment/infrastructure decision,
  not an assumption:
  [Fly app configuration](https://fly.io/docs/reference/configuration/).
- A Fly Volume is local persistent storage attached to a Machine/host rather than a
  replicated application database. It introduces attachment, deploy and recovery
  constraints:
  [Fly Volumes overview](https://fly.io/docs/volumes/overview/).
- Neon separates durable storage from compute and can suspend idle compute; clients
  must tolerate wake/reconnect behavior:
  [Neon compute endpoints](https://neon.com/docs/manage/endpoints/).

These facts mean rootfs is not automatically a “fast second copy of DB”. It can
reduce repeated serialization/decompression or hold spill/temp bytes, but it cannot
be required for correctness and may be slower than expected for many tiny random
operations.

## 4. Recommended tiers (`PROPOSAL`)

### Tier 0 — RAM: bounded live execution

Use for:

- current request/context assembly and streamed deltas not yet at a durable event
  boundary;
- active coroutine/task registry, semaphore and short-lived locks;
- parsed tool/result objects, hot read-through cache and DB connections;
- UI composer draft and in-memory query cache.

Limits:

- budget per run plus global concurrency/admission based on measured peak RSS;
- never depend on a RAM lock/task for authority after restart;
- persist provider intent/checkpoint/change-set/receipt before claiming the
  corresponding durable transition;
- 512MB RAM and swap make unbounded context/result caches unsafe.

### Tier 1 — Fly rootfs: optional rebuildable scratch/cache

Eligible examples:

- temp upload/decompression/serialization files;
- bounded encrypted tool-result spill for an active run;
- content-addressed copies of non-sensitive static policy/tool schemas;
- rebuildable derived preview pages whose canonical operation data/digest is in
  Neon;
- temporary eval/browser artifacts in non-production disposable environments.

Every rootfs class needs a directory allowlist, content hash, sensitivity rule,
per-run/global byte cap, TTL/LRU, startup orphan cleanup, `finally` cleanup and
fallback to direct DB/object fetch. A cache miss or total loss must preserve
correctness. Atomic temp-write + fsync/rename may protect a local cache file from
partial reads, but does not make it durable across replacement.

Do **not** put on rootfs:

- canonical transcript/run/checkpoint/change-set/receipt/idempotency/grant state;
- secrets, API keys, session tokens, master/DEK material or DB dumps;
- the only copy of attachments/evidence/provider outcomes;
- retry intents, outstanding confirmations or AUTO authority;
- PRIVATE plaintext or raw prompts/responses merely for convenience.

Because the expected workload is currently small, rootfs tier implementation should
wait for measurements of DB payload size, repeated reads, serialization CPU, RSS and
latency. A tier with no measured hit/rebuild value is unnecessary complexity.

### Tier 2 — Neon: canonical state and bounded small evidence

Keep canonical:

- conversations/messages/title/frontier and compaction checkpoint metadata;
- runs, loop/tool intents and results needed for replay/recovery;
- provider-call identity/outcome/usage/route receipts;
- selection/workflow plan references, source versions and grants;
- frozen changes, confirmation, receipt/idempotency/reconciliation;
- bounded encrypted feedback/evidence metadata under approved retention.

Large model/tool payloads should not be dumped into unconstrained event JSONB.
Define typed/redacted event/provider schemas, encryption and row/byte/retention caps.
Missing usage/cache/cost data remains `UNAVAILABLE`, not zero.

### Tier 3 — future encrypted object storage

Use only when attachments, exports, full evidence or large immutable tool artifacts
outgrow measured Neon caps. Store encrypted objects under random/content IDs with
hash, size, sensitivity, retention/deletion state and object version in Neon.

Do not add object storage or a Fly Volume pre-emptively. Current nearest alternative
is bounded encrypted Neon content. A Fly Volume is not a substitute for replicated
durable artifacts and complicates single-Machine replacement/recovery.

### Provider cache/state — separate plane

Provider prompt cache/conversation state/response cache follow D3/D5. They can save
cost/latency but are neither local storage tiers nor recovery truth. Every provider
state reference has a stateless rehydrate path and privacy/retention receipt.

## 5. Recovery behavior (`PROPOSAL`)

Cold boot is the invariant:

1. start with empty RAM/rootfs cache;
2. initialize DB/provider adapters;
3. inspect durable nonterminal runs/provider intents/receipts;
4. acquire generation/lease fences;
5. classify each as resume, wait, reconcile or terminal—not blind retry;
6. rebuild context/preview projections from Neon and optional provider state;
7. clean orphan scratch only after no live lease references it.

Current code usefully commits provider intent before network I/O and receipts with
domain mutation seams, but the existing `MimiRunSupervisor` only owns process-local
tasks. This does not prove a startup sweep for every stale `intent/dispatched/running`
state. D7 implementation must close that recovery plane.

Neon idle/wake is compatible with this design if background timers, health checks
and monitoring do not query it unnecessarily. Current `/api/healthz` avoids DB, but
`ENABLE_INPROCESS_CRON=true` and always-on Fly topology require measurement of real
DB wake behavior. Do not keep Neon awake to preserve Mimi runs; durable checkpoints
allow the worker to reconnect/resume when required.

## 6. Strongest counterargument and nearest alternative

**Counterargument:** RAM → disk → DB appears efficient and uses paid resources, but
three mutable copies create invalidation, encryption, cleanup and crash-consistency
work. The rootfs performance limit and replacement semantics mean it can make a
small one-user app slower and less reliable, not faster.

**Nearest viable alternative:** keep Neon-first canonical storage plus bounded RAM,
measure actual payload/latency/RSS, and add only one content-addressed disposable
scratch class when evidence shows value. This is T1's recommendation.

If later large durable artifacts become real, add encrypted object storage. Do not
add a Fly Volume merely to fill a conceptual middle tier.

## 7. QA and measurement before a rootfs tier

- read actual live Machine rootfs size/free bytes, `persist_rootfs`, Machine count
  and replacement behavior; exact 8GB remains `UNVERIFIED`;
- measure cold/warm context assembly, repeated tool-result serialization, Neon
  round-trip and rootfs read/write under realistic payload sizes;
- measure 512MB RAM + swap at maximum admitted context, evidence and concurrency;
- restart/deploy at provider intent, provider-dispatched/no-result, checkpoint,
  waiting confirmation and post-domain-commit/pre-event seams;
- prove startup recovery, late-result fencing, idempotent mutation and no lost
  preview/confirmation;
- test rootfs full, permission error, corruption, stale entry, orphan cleanup and
  total deletion; behavior must fall back or fail truthfully;
- test private/secret/plaintext scanners over rootfs, events, provider JSONB and
  stdout logs;
- measure Neon cold wake/reconnect and verify health/cron behavior does not defeat
  desired autosuspend;
- test multiple workers/Machines in a disposable topology even if production is
  currently one Machine; local files and RAM locks must not imply global ownership.

No exact byte/TTL/RSS/latency threshold is approved here. Set limits from the first
synthetic/load pilot and resource headroom, then version them.

## 8. Owner decision D9

T1 recommends Owner approve:

- **D9-A:** Neon remains canonical for all conversation/run/authority/recovery and
  bounded evidence state; RAM/rootfs/provider caches are discardable optimizations.
- **D9-B:** do not add a Fly Volume or generic disk cache now. First measure; then
  introduce only typed, encrypted where necessary, content-addressed disposable
  scratch classes with quota/TTL/cleanup/fallback.
- **D9-C:** future large durable artifacts use encrypted object storage plus Neon
  metadata; rootfs is never the only durable copy.
- **D9-D:** cold-start recovery/startup sweep and Neon idle/wake measurements are
  mandatory acceptance gates for D7, independent of whether rootfs caching ships.

## 9. Limitations

Static repo evidence and current official platform documentation were inspected.
No production Fly/Neon configuration, disk capacity/free space, RSS, latency,
restart fault injection, object storage or provider call was run. Current plan,
backup/PITR retention, actual autosuspend and effective Machine rootfs settings are
`UNVERIFIED` until an authorized live inspection.
