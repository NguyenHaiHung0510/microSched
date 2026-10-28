# Mimi attention and device notifications

Dated source map for Owner192 G2 binding (exact HEAD and reviewed candidate hashes); inherited base aa79a94. Source `frontend/src/MimiNotifications.tsx:33`. Current runtime status **NOT_RUN** until a canonical candidate-matching receipt is accepted; dated H14 proof is not rebound.

## Sub-features

Owned locator, expiry, preference/opt-in, dedup/stale delivery.

## How to get to it (user POV)

Open owned attention locator; read current preference; no automatic permission request.

## Historical driver binding (current grant required)

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

## R3 night history UI and handled successor

ReminderCenter → Lịch sử now includes this same qualified intent once, grouped by
its recorded creation day/clock. Online-only desired handled=true and exact confirmed
bulk add a separate owner/occurrence association; `read_at`, device receipt status,
attempts, preferences and conversation/run state stay unchanged. Current disclosure
gates are revalidated at commit; applied replay after visibility loss is coarse and
does not return prior counts or scope. No new provider, push permission or offline
adapter follows from this ACK.

Author actual local PG covers all four typed origins, idempotency, current privacy,
exact >50 manifest, concurrent same-batch commit and unchanged Mimi read/delivery.
The synthetic UI has zero push devices/deliveries and live provider disabled; the
intent fixture's initial owner-derivation error and corrected exact IDs are retained
in the R3 night receipt/manifest. Actual own UI shows all origins, not physical
delivery. Reuse `verify-microsched/scripts/r3_history.mjs` and its shared freeze;
independent runtime/provider/device/production statuses are not promoted by author QA.

DEV328 affected correction:shared synthetic history test key/cache is test-scoped;
new0019 association app rights are SELECT/INSERT,manifest SELECT/INSERT/UPDATE after
table-specific default-grant reset. Mimi eligibility/read/delivery logic is unchanged.
Private/draft driver failures now retain constant metadata and omit failure pixels;
use the shared repaired M1 history helper and current freeze. No new Mimi/provider
runtime acceptance follows from these author role/helper checks.
