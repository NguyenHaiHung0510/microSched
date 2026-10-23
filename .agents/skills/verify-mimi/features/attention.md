# Mimi attention and device notifications

Source-mapped for Owner192 G2 current binding (exact HEAD and reviewed candidate hashes); inherited base aa79a94. Source `frontend/src/MimiNotifications.tsx:33`. Current runtime status **NOT_RUN** until a canonical candidate-matching receipt is accepted; dated H14 proof is not rebound.

## Sub-features

Owned locator, expiry, preference/opt-in, dedup/stale delivery.

## How to get to it (user POV)

Open owned attention locator; read current preference; no automatic permission request.

## Driving it with the current scoped harness

Journey `EXISTING_DEVICE_GATE`; use `python -B .agents/skills/verify-mimi/scripts/driver.py doctor --binding CURRENT_BINDING` before the first drive. Selector source: `mimi-attention` (observed in current source). Notification flag, exact synthetic locator and separate opt-in/physical device proof or Owner disposition. Core actions share native/live/device QA receipts, not a second matrix.

Oracle: Correct owned thread and truthful expiry; in-app evidence does not imply physical delivery or permission.

## Gotchas

Missing prerequisite stays BLOCKED/NOT_RUN. No source fixes while frozen QA runs; no implicit grant from this map. Provider doubles prove lifecycle, not live quality. Source/config/helper drift invalidates affected proof. No post-QA source change inherits acceptance.

Owner196: physical notification delivery NOT_RUN_OWNER_WAIVED only. Notifications ON and permission/privacy/dedup/stale/deep-link/runtime acceptance remain required.

Shared091 auth boundary (Owner322): authoritative domain401 returns the shell to guest and holds outbox; existing PIN401 is not logout. This is not live Mimi/attention/device acceptance or new permissions. Current native/provider/device statuses above remain qualified; use the separately frozen focused QA grant.

## R3A history backend (092)

`GET /api/reminder-history?origin=mimi_intent` is a read-only projection of existing
intents, gated by current owner + nonprivate STANDARD conversation + the existing
notification/production availability flags before pagination/decryption. It does not
replace `/api/mimi/attention`, opt-in, locator resolution or read_at acknowledgement.
One intent remains one occurrence across multiple device receipts. Provider acceptance
means at least one target accepted; other targets may differ, not OS display/read.
Attempt count is the maximum per-device receipt, not a push-call count. No endpoint,
key or preference metadata is returned. Intent-created clock and encrypted intent
copy retain their explicit basis; current conversation prose is not reconstructed.

Author deterministic API/local-PG tests exercise synthetic intent/device rows only,
with no live Mimi/provider/dispatch. Independent History UI, physical delivery and
production remain NOT_RUN; retain the historical qualifications above.
