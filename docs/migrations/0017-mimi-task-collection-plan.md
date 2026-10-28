# 0017 — minimal additive Full A migration impact

A1 proposes this package; executable DDL/hash will be frozen after A2 authoring.
Source baseline6ed330d4, Alembic head0016. Live schema/catalog NOT_RUN. Local/CI
throwaway author/test is granted; live Neon upgrade/Restore/Sync is not granted.
Existing Task/TaskItem/OneShotReminder, MimiChangeSet/Receipt/RefreshMarker,
MimiEvidence/Feedback and PushSubscription were inspected. Do not recreate them.

| Table/delta | FK/index/invariant | Data and old-app impact |
|---|---|---|
| task.collection_version BIGINT NOT NULL DEFAULT1 CHECK>=1 | BEFORE UPDATE increments, aggregate child writes bump parent under parent lock | Existing rows1, additive default. Existing timestamp read API stays compatible; new collection CAS binds integer too. |
| task_item.deleted_at nullable timestamptz | Active(parent,position,id) partial index; parent→child lock then parent version trigger | Existing children live. New read/count/FTS paths exclude tombstones. Old app reads them and hard-deletes: after activation old app is READ-ONLY rollback, not recovery-safe writer. |
| mimi_execution_receipt.result_ciphertext nullable TEXT | CHECK null or mimi:v1 prefix; resource AAD | Encrypted full before/after/inverse, v1 receipts unchanged. task_id stays historical first target anchor, ordered IDs in v2 result. |
| mimi_evidence.content_ciphertext nullable TEXT | CHECK prefix; existing conversation/run FK and1MiB limit reused | No new evidence table/blob store; old references stay readable. Server validates causal ownership. |
| mimi_device_preference | UUID/timestamps; owner UUID; subscription FK CASCADE unique; opt-in defaultfalse; revision>=1 | No legacy subscriptions auto-opted-in. Explicit authenticated device binding within approved D7 only. |
| mimi_notification_intent | conversation/run/event FKs CASCADE; owner UUID, kind completed/approval_ready, encrypted copy, opaque locator/hash, expires/read_at; unique(event,kind); unread owner index | In-app durable attention, same completion TX. No copied private or credential content. |
| mimi_notification_delivery | intent/preference FKs CASCADE; unique pair, states pending/sending/accepted/unknown/retryable/expired/suppressed; attempts0..4, next_at; pending index | Restart-safe finite device fanout. Ambiguous sending→unknown, never auto-retry. No exactly-once guarantee. |

All new tables follow UUIDv7/timestamps/set_updated_at, TEXT+CHECK and application
schema/default grants. Trigger parent→child→reminder lock behavior is tested with
old app/raw writers; do not create child→parent deadlock. Updates may conservatively
bump parent more than once, but never miss or reuse a committed version.
No rewrite of prose/real data, no auto-purge, no destructive live downgrade.
Down migration is throwaway-only and refuses any recovery/notification/tombstone
data that would be lost. Preserve old DDL as read-only fallback reference.

Local tests:0016→0017 on populated synthetic baseline, constraints/FKs/indexes/
triggers and app grants catalog audit; old app behavior before activation; new
feature-off fallback on0017; targeted concurrent raw-child/parent CAS; rollback of
failed batch leaves no domain/receipt/intent; restart retains unknown delivery.
Fresh empty disposable upgrade/downgrade/re-upgrade only after refusal test;
old app after tombstones is deliberately read-only, no false write compatibility.

Owner execution card at A2 freeze must bind exact migration file+DDL SHA256,
0016 live baseline/catalog/grants evidence, target revision, row/count impact,
Owner backup identifier/time+restore plan, maintenance/no-old-writers boundary,
forward upgrade command, activation flags/schema-ready check, verification SQL,
feature/dispatcher-off rollforward fallback and retained unknown receipts.
Actual backup/live DDL/activation/production readyz NOT_RUN. A1 plan hash is not
an executable migration approval. No Owner question blocks local A2.
