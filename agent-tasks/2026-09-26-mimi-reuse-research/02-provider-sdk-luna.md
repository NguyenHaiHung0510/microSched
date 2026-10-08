# Round 1A — provider transport and SDK parity

Research by GPT-6 Luna; T1 transcribed and checked the local exception path. Snapshot 2026-09-26. Read-only, no install, provider egress or key.

## Findings

The incumbent `backend/app/agent/openrouter.py` sends a bounded one-dispatch OpenRouter request using `httpx` (already a runtime dependency), performs route/provider and terminal parsing, and gives `service.py` a truthful `retryable/unknown/failed` outcome for the persisted call ledger. It is not merely boilerplate HTTP. An SDK would still leave Mimi's domain authority, transcript, source checks and preview/confirm seam in application code.

| Option | Potential gain | Unproven or conflicting seam |
| --- | --- | --- |
| OpenRouter Python SDK | Thin typed client, native routing, streaming and generation endpoints. | Current public chat signature lacks visible `store` and top-level `usage` arguments or a proven arbitrary body passthrough. Source shows per-call `retries`; the old B24 phrase about default retries alone is insufficient to reject it. Agent found current SDK metadata pins `pydantic<2.13`, while this worktree's `backend/uv.lock` has 2.13.4. Confirm versions/lock at any future spike. |
| OpenAI Python SDK with OpenRouter `base_url` | Existing `extra_body` can carry router-specific fields; `max_retries=0` is documented. This is the most compact alternative fixture spike. | Default retry is nonzero; raw response/provider/usage and streamed partial tool-call fidelity need proof. Sending a field is not evidence the gateway honors it. |
| LiteLLM | Multi-provider normalization, routing, fallback, usage convenience. | Adds another retry/fallback authority and a larger dependency/configuration surface. LiteLLM docs distinguish router `num_retries` from provider-SDK `max_retries`; hidden dispatches would violate Mimi's ledger. Stronger fit only if genuinely operating multiple direct first-party routes. |
| PydanticAI provider layer | Typed tools/output and OpenRouter settings, building on existing Pydantic use. | Framework-level model/message and loop semantics may change terminal and telemetry fields; evaluate as orchestration candidate, not a drop-in HTTP client. |

Primary sources: [OpenRouter client SDK](https://openrouter.ai/docs/client-sdks/overview), [Python chat API](https://openrouter.ai/docs/client-sdks/python/api-reference/chat), [Python SDK source](https://github.com/OpenRouterTeam/python-sdk/blob/main/src/openrouter/chat.py), [SDK metadata](https://github.com/OpenRouterTeam/python-sdk/blob/main/pyproject.toml), [OpenAI Python retries](https://github.com/openai/openai-python#retries), [OpenAI Chat source](https://github.com/openai/openai-python/blob/main/src/openai/resources/chat/completions/completions.py), [LiteLLM Router retries](https://docs.litellm.ai/docs/routing).

`store:false` is present in Mimi's request builder. The agent found it explicit on OpenRouter's [Responses API schema](https://openrouter.ai/docs/api/api-reference/responses/create-responses) but not in the current public [Chat Completions schema](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request). **Inference, not a verified leak:** for the Chat route, the field's retention effect is not established by these docs. The already-configured provider ZDR and `data_collection=deny` remain separate routing controls, not application-log controls. Do not report `store:false` as a proven Chat privacy guarantee until the buyer/gateway confirms it.

The agent spotted a narrow recovery-path defect candidate: `get_generation()` catches `httpx.ConnectError` and `TimeoutException` but not all `TransportError` variants; `service.reconcile_unknown_run()` only catches `ProviderDispatchError`/`RouteContractError`. T1 verified these paths in `openrouter.py` around `get_generation` and `service.py` around `reconcile_unknown_run`. A `ReadError` or `RemoteProtocolError` may therefore become a generic server error instead of a recoverable reconciliation-unavailable response. This is **code-inferred, not test-proven**; it does not itself redispatch the original generation.

## Decision gate

Do not migrate by reputation. First run a synthetic, no-key `httpx.MockTransport` comparison against the OpenAI SDK (and OpenRouter SDK only if lock/signature issues can be resolved) for exact/adaptive JSON fields, SSE partial tool calls, usage-only terminal, provider identity, cancellation and client closing, and a counted **single POST** under 429/5xx/connect/read/timeout faults. Retain incumbent if parity or maintenance/footprint gain is not demonstrated. Separately clarify Chat `store` semantics from authoritative gateway documentation or an approved synthetic probe. No live route test is authorized by this research.

Confidence: high on local code and documented signatures, medium on package compatibility across future versions, unknown on live Chat `store` semantics and observed upstream retention.
