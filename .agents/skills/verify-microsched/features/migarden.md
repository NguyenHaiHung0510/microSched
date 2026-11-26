# miGarden Khu A

Current source at the [indexed baseline](README.md): `frontend/src/App.tsx:75`, `frontend/src/features/migarden/MiGardenScreen.tsx:212` and `backend/app/web/routers/migarden_human.py:38`. [Current product contract](../../../../docs/migarden/n01-status.md).

## Sub-features

Overview, freshness and last-confirmed state, history and version drill-down, health, configuration and Start/Stop request surfaces.

## How to get to it (user POV)

With `migarden_available` enabled for the owned session, open **miGarden** in the domain nav or via `migarden-open` in **Ứng dụng**. Fresh signed-in `/` routes to `/migarden`. The in-page buttons are **Tổng quan**, **Lịch sử** (`?tab=history`) and **Cấu hình** (`?tab=config`). Version detail is in History via `version`. With the gate off, the menu has disabled `migarden-placeholder` and the direct route reports that miGarden is disabled.

## Driving it in a current synthetic candidate

Use `migarden-screen`, `garden-output`, `garden-last-confirmed`, `garden-history`, `garden-health` and `garden-versions`. Bind an isolated Owner session, desired/applied config versions, known current/stale/unknown report clocks, history rows and no connected Controller. Use owned `GET /api/migarden/state`, `/history`, `/daily`, `/config`, `/config/versions` and `/health` under the same prefix. The visible state query can update local presence bookkeeping. The browser and PG oracles are `frontend/e2e/migarden-n02-shell.spec.ts`, `frontend/e2e/migarden-live-status.spec.ts` and `backend/tests/test_migarden_pg.py`.

Oracle: Displayed source/time and desired/applied config match the frozen report/version/history fixtures. Fresh app transport alone does not certify fresh Controller contact or output. Use the [54-case N01 matrix](../../../../docs/migarden/n01-qa-matrix.md) for retained requirements and evidence layers.

## Gotchas

**Tưới ngay** then **Xem trước** calls `POST /api/migarden/start/preview`. Confirm, **Dừng tưới** and **Lưu cấu hình** are also effectful. These need a separate scoped synthetic command/config grant and durable oracle. Physical Controller, water/output, production and current synthetic browser acceptance are **NOT_RUN**.
