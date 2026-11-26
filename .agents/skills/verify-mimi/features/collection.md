# Task collection review and revision

Current source at the [indexed baseline](README.md): `frontend/src/MimiCollectionReview.tsx:24` and `:38`, `backend/app/web/routers/mimi.py:809`. Runtime **NOT_RUN**.

## Sub-features

Selection coverage/counts, search/filter/paging, revision and atomic whole-selection confirmation.

## How to get to it (user POV)

From a genuine owned collection preview choose **Xem và duyệt** or **Inspector B**. Inspect whole-selection counts and exact affected fields before any decision.

## Driving it in a current synthetic candidate

Use `mimi-collection-review`, `mimi-global-counts`, `mimi-review-row` and `mimi-confirmation-preflight` when shown. **Sửa phương án này** binds revision to the composer. **Xác nhận toàn bộ … Task** applies the frozen set; table filtering changes what is visible. Bind selection `GET /api/mimi/conversations/{id}/selections/{selection_id}`, the current preview version and owned Task fixture.

Oracle: Included/excluded/uncertain/affected totals and the exact allowed target set agree. Commit is atomic and repeat-safe under the frozen decision key. The [case oracle](../../../../docs/qa-specs/mimi-task-collection-cases.json) retains 34 A0 and 20 A1 cases. The [backend selector manifest](../../../../docs/qa-specs/mimi-task-collection-execution.json) covers A0. The A1 [app execution record](../../../../docs/qa-specs/mimi-task-collection-app-execution.json) has its original runtime binding. The [collection contract](../../../../docs/mimi/task-collection.md) defines the applicable gates.

## Gotchas

A0-22 and A0-32 use the successor feature-off/tool-boundary test after the collection revision gained its bounded read phase. The uptime and disposable migration assertions are separate selectors and retain their case oracles. The collection runner’s non-collect database tuples belong to earlier batches. Prepare a reviewed binding and owned database for a new runtime batch. Review and revision do not grant actual Task mutation. Use an exact permit and fixture/oracle for the confirm case. No current execution verdict follows from the historical selector manifest.
