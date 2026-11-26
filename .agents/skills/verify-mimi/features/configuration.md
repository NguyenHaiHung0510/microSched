# Model/effort and durable operating policy

Current source at the [indexed baseline](README.md): `frontend/src/MimiConfiguration.tsx:139` and `:258`, `frontend/src/MimiOperatingPolicyPanel.tsx:29`. Runtime **NOT_RUN**.

## Sub-features

Per-conversation model, effort and input selection, global input/price policy, CAS and draft retention.

## How to get to it (user POV)

In Workspace use `mimi-configuration-hub-toggle` (**Cấu hình Mimi**) on an owned conversation. The composer model control opens quick settings. The dock menu can open the Workspace hub. Operating policy and Voice preferences are hub-only.

## Driving it in a current synthetic candidate

Use `mimi-route-settings`, **Mức suy luận**, **Lưu lựa chọn**, and `mimi-operating-policy-panel`. Check `/api/mimi/capabilities` and its `model_selection_enabled` flag. Use frozen supported profiles, no-egress setup and the bound `GET/PUT` conversation configuration and operating-policy routes. The default input cap is 50,000 Unicode codepoints. Read the effective saved policy for the case. Use `frontend/src/mimi-configuration.test.ts` and `backend/tests/test_mimi_operating_policy_pg.py` for deterministic oracles.

Oracle: Readback version/CAS, limit/price revision and next-unsent request match. Conflict keeps draft. The already dispatched snapshot and prior measured-usage anchor stay fixed. `mimi-provider-pool` is diagnostic information under native gateway policy.

## Gotchas

Any test needing an actual next-unsent request needs the approved SDK double or a separately authorized exact route. The configuration surface does not grant model/key/catalog use.


A price/future-input policy save preserves the past measured-usage anchor; next unsent wire still uses the latest admitted caps. Owner192 author proof covers this cheap R1 correction; native/browser acceptance remains separate.
