# Mimi attention and device notifications

Current source at the [indexed baseline](README.md): `frontend/src/MimiNotifications.tsx:33`, `frontend/src/App.tsx:88`, `backend/app/web/routers/mimi.py:687`. Runtime **NOT_RUN**.

## Sub-features

In-app attention, owner locator, explicit read ACK, device opt-in/revision and dedup.

## How to get to it (user POV)

In Workspace open the data rail and **Thông báo Mimi** when enabled. **Mở hội thoại** selects the owned row’s conversation. The same-origin deep link `/mimi?attention=OWN_LOCATOR` resolves in the app. Acknowledging read or opting in is a separate action.

## Driving it in a current synthetic candidate

Bind `notifications_enabled`, the owned STANDARD conversation/intent, and valid/expired/foreign locator fixtures. Use `mimi-attention`, **Đánh dấu đã đọc** or **Bật trên thiết bị này** only for separately granted writes. Verify `GET /api/mimi/attention`, `GET /api/mimi/attention/resolve/{locator}`, and bound read/preference endpoints. The preference read uses device proof. See `backend/tests/test_mimi_notifications_pg.py`.

Oracle: Locator opens the intended conversation, expiry is visible, invalid locators reveal no protected state, and read ACK is distinct from delivery and Reminder History handled status.

## Gotchas

The tracked release preset has notifications off. An enabled synthetic fixture and device proof are required for opt-in. Opening the rail alone does not request permission. Historical qualifications below retain their exact scope.


Owner196: physical notification delivery NOT_RUN_OWNER_WAIVED only. Notifications ON and permission/privacy/dedup/stale/deep-link/runtime acceptance remain required.

Shared091 auth boundary (Owner322): authoritative domain401 returns the shell to guest and holds outbox; existing PIN401 is not logout. This is not live Mimi/attention/device acceptance or new permissions. Current native/provider/device statuses above remain qualified; use the separately frozen focused QA grant.

## Historical R3A history backend (092)

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

## Historical R3 night history UI and handled successor

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
