# Mimi native OpenRouter routing

Owner225–230, approved 17 October 2026. This supersedes the active local
provider-catalog/certificate admission design. Delivery of this source change
does not establish deployment or live application acceptance.

Mimi supplies its selected model/effort, assembled input, tools, output limit and
stable opaque conversation `session_id`. Routing sends OpenRouter's native
`require_parameters`, `allow_fallbacks`, `data_collection`, ZDR, precision and
Owner-controlled price caps. It does not send `only`, `order`, `sort`, a fallback
model array, or a locally computed eligible-provider set. OpenRouter selects and
fails over providers using its default policy. Unsupported policy yields an
error; Mimi never silently raises prices or relaxes privacy/precision.

New runs normalize saved exact/adaptive preferences to native routing without
rewriting historical runs. Collection is an independent product feature. Local
uptime/capacity/provider certificates and metadata TTL do not admit generation;
the old catalog implementation is retained only for historical tests. Chat-open
warmup is a compatibility no-op. The authenticated legacy pool-refresh endpoint
returns current policy rather than a provider roster and performs no network or
inference request. Provider metadata, when absent, remains unknown. A different
response model is still rejected; domain/tool validation and Confirm remain in
Mimi.

## Gateway recovery

One routing controller allows at most three attempts, approximately 1s then 2s
backoff plus jitter, respecting `Retry-After` and the existing run deadline.
OpenAI SDK internal retries remain disabled. Safe connect failures and explicit
429/typed overload responses can retry. An in-flight-budget 402 can retry only
with the documented metadata and Retry-After. Authentication, spent credits,
invalid requests and unclassified policy/no-provider errors do not retry.

Read/write failures, cancellation, JSON errors inside HTTP200, partial streams
and uncertain terminals do not silently replay. Each observed attempt is kept
in the provider-call route receipt, separately from agent tool-loop turns.
Usage belongs to its attempt; missing cost is never inferred to be zero. The
private paid-QA ledger reserves one dispatch upstream, so routing disables its
extra automatic attempts while that ledger is active rather than multiply an
unapproved reservation. The existing hold/call counters remain authoritative.

The current SDK discards the outer SSE error envelope before exposing APIError.
Mimi preserves identity/usage from earlier observed frames; information present
only on that discarded envelope remains unknown. It does not fabricate an ID or
fee. HTTPX parsing preserves those facts when actually observed.

Mimi's soft compact trigger, operating input target, byte resource limit and
finite overflow recovery are separate application policies. Model profile
capacity may bound a private financial reservation; it is not an endpoint
capacity filter or a guarantee that every provider accepts that input size.

## Verification and operation

Tests use the real request builder and SDK with fake HTTP/SSE responses. They
exercise native policy, legacy preference normalization, retry limits,
Retry-After, unknown/partial failures, terminal accounting frames, model identity
and server-side argument validation. They do not prove OpenRouter's internal
balancing, provider quality or a warm cache. No automatic provider probe is
installed. Normal Mimi live/product acceptance is a separate approved batch.

`fly.toml` prepares native routing without changing model, prices, privacy or
unrelated feature flags. Deployment requires its own covering grant; rollback
uses the prior known application build/config, not an old preference written
into a new conversation. No database migration is required.

Contract sources: [provider selection](https://openrouter.ai/docs/guides/routing/provider-selection),
[errors](https://openrouter.ai/docs/api_reference/errors-and-debugging),
[limits](https://openrouter.ai/docs/api_reference/limits),
[streaming](https://openrouter.ai/docs/api_reference/streaming),
[cache/session affinity](https://openrouter.ai/docs/guides/best-practices/prompt-caching).
