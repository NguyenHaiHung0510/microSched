# Mimi routing and context contract — 2026-10-11

This source candidate uses dynamic metadata eligibility intersected with trusted
endpoint qualification receipts. OpenRouter balances/falls back within the resulting
`only` list. There is no provider-name roster, local ranker, permanent pin, paid warming
or automatic application resend after UNKNOWN. Default deployment remains exact;
adaptive activation requires independent route qualification and release gates.

## Fixed eligibility criteria

- Model: `deepseek/deepseek-v4.1-flash`; selected effort exactly low/high/max.
  Production default remains HIGH. QA MAX remains separately conditional/budgeted.
- Capacity: endpoint context at least the configured1,048,576 tokens and completion capacity at least8192. Missing/noninteger/lower metadata excludes it;272000 is the compaction trigger, not the model window.
- Precision: fp8 only. Tools, tool_choice and reasoning parameters required;
  named function, main conversation and strict summary response contracts qualified.
- Uptime strictly greater than95% in the selected rolling1d window (30m supported).
  Missing/nonfinite uptime fails closed. Threshold cannot be lowered below95.
- Prompt price at mostUSD0.20/M and completion at mostUSD0.60/M tokens.
  `max_price` is a unit-price bound, never a total-spend budget.
- Native `zdr=true`, `data_collection=deny`, `require_parameters=true` and
  `quantizations=[fp8]`. Contradictory privacy/capability metadata excludes endpoints.
  Missing positive metadata is not certification; receipts must prove applicable axes.

## Qualification lifecycle

`MIMI_ROUTE_QUALIFICATIONS_JSON` defaults to`[]`. It contains trusted deployment
receipts, not model/UI-supplied assertions. Each record binds `catalog_tag`, a verified
full-variant `routing_slug` (not inferred from the tag), actual `provider_name`, model,
effort, precision, source/config `scope_sha256`, material `endpoint_sha256`, privacy,
named-function proof and all three request families: main/summary/forced_function.
`evidence_sha256` binds the reviewed routing_slug/privacy/effort/main/summary/
forced_function receipts. `expires_at` is an epoch timestamp, valid for at most24h.
These hashes do not themselves prove that a live qualification passed; release
review must verify the actual referenced evidence before supplying the manifest.

Catalog refresh is on-demand: TTL300s, timeout10s, response bound2MiB and manual
refresh cooldown30s. Qualification expiry and material source/variant drift invalidate
admission. New metadata-eligible endpoints remain pending qualification, not active.
The run freezes its allowed set; request construction rejects expired qualification
or catalog older than300s. It does not silently broaden/renew a run or spend on
recertification. Empty intersection stops. Long runs can halt at this freshness fence;
a future refresh design would need separate review. Sticky never bypasses the fence.

Adaptive requests omit `order`/`sort`, allowing OpenRouter's native selection/sticky
behavior; exact rollback retains one provider with fallback disabled. Existing opaque
HMAC conversation `session_id` is preserved for main/helper. Native session stickiness
does not transfer provider KV cache, certify cache support or guarantee a cache hit.
No new retention option or direct-provider cache key is forwarded.

## Context and app receipts

New runs bind the deployment compaction trigger272000; rollback100000 remains an
explicit preset. Model window1048576, output reserve8192, payload2MiB and transcript
suffix1000 are independent bounds. Only bound successful main provider prompt usage
triggers compaction; serialized bytes do not measure tokens. Stable policy/schema
prefixes precede mutable reference/history/authority data. Known original policy
checkpoint digests remain compatible only with intact encrypted content/frontier/
source proofs; arbitrary hashes fail closed. New checkpoints use the current digest.

Provider cached-token counts come from actual usage; absence remains UNKNOWN.
App continuation reuse is limited to versioned public Task inspect receipts with
consume-time version/private/deletion checks. Query/aggregate/content/reminder results
are read again; no cached answer proves fresh corpus coverage or grants authority.

Notifications retain existing opt-in/device/private/dedup/stale-suppression gates.
No physical delivery or deployment flag is proved by offline/native tests.

Primary references: [provider selection](https://openrouter.ai/docs/guides/routing/provider-selection),
[prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching),
[ZDR](https://openrouter.ai/docs/guides/features/zdr),
[DeepInfra caching](https://docs.deepinfra.com/chat/prompt-caching).
General provider documentation is not measured Mimi endpoint qualification.
