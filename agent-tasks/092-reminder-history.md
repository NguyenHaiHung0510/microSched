# 092 — Lịch sử nhắc và xác nhận đã xử lý

History B groups existing durable occurrences by Vietnamese calendar day, latest
first. It combines one-shot Task/Event/Tracker/DayAnnotation, tracker dispatch,
subscription dispatch and owner-visible nonprivate STANDARD Mimi intent. No Note
origin, reconstructed legacy clock or OS-delivery claim. The reviewed read projection
and current source content/visibility rules remain the basis.

`GET /api/reminder-history` filters source/origin/send status/handled/date with keyset
paging. `PUT /api/reminder-history/{origin}/{id}/handled` accepts only boolean
`handled: true`; replay keeps the first timestamp. This ACK never completes a Task,
confirms an Entry, changes a schedule or marks Mimi read/delivered.

`POST /api/reminder-history/handled-batches/prepare` accepts a UUIDv7 batch ID,
normalized filter and optional typed `selected_refs`. Omitted refs mean all matching
unhandled occurrences, including unloaded pages. The server freezes exact typed IDs,
count, filter fingerprint and cutoff; the UI confirms the visible count/scope.
`POST /api/reminder-history/handled-batches/{id}/commit` locks and rechecks current
authorization/parents/receipts, then commits all ACKs and stable replay result in one
request transaction. A stale hidden/deleted member aborts the whole set. New arrivals
are excluded; already handled members count separately. Same-ID different scope is
409; unapplied manifests expire after15minutes and need renewed confirmation. Applied
replay remains stable, returning only coarse success if current disclosure is lost.

Migration0019 adds only `reminder_occurrence_handled` and `reminder_handled_batch`.
The app role has SELECT/INSERT on occurrence associations and SELECT/INSERT/UPDATE
on manifests; table-specific resets remove broader inherited default grants.
The migrator owns DDL. Empty disposable downgrade is supported;
nonempty downgrade refuses, preserving records. Production requires explicit migration
and backup/rehearsal/release gates; deploy never auto-migrates. Immutable919 old backend
was exercised against0019 using the app role and rolled-back synthetic CRUD.

Owner322 permits online-only ACK/bulk with immediate truthful pending/failure and
existing pending-source barriers; no new outbox family or full offline matrix.
History/selection/confirmation are RAM-only and cleared on private lock/logout;
connected public source drafts retain their baseline. Existing approved UI tokens,
components, light Nunito, touch/keyboard controls and responsive A layout apply.

Evidence: focused real-PG/API/schema/concurrency tests, backend/frontend regression,
existing-stack focused own preview driver and versioned R3 night freeze/handback.
Author evidence is separate from independent QA, CI, physical devices and production.
Base919 is the locally frozen R2 dependency; release base must be refreshed after
PM accepts/merges R2. No release acceptance is asserted by this source branch.

DEV328 F01/F02/F03 repairs keep history product behavior unchanged:shared test fixture
provides synthetic key/cache,unreleased0019 grants only the rights above,and sensitive
M1 failures omit raw errors/pixels before verified purge. Focused caller-key-absent
PG/crypto tests and actual app-role positive/refusal checks run on a separate owned
rehearsal; existing60occurrences/59handled/2manifests are retained. Production backup
remains blocked by automatic review; no productionDDL/deploy follows from this repair.
