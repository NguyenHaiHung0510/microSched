# Task090 — group heatmap H2

Approved outcome: add All / Group / Tracker modes to existing heatmap. Group uses current membership; preserve year/month layout, grouped tooltip and touch detail. Same scope governs year counts, month cells, day preview and paginated records. Empty/deleted groups never silently expand to All.

API: optional UUID group_id on GET /api/tracker/activity and /api/tracker/entries. Both group and tracker intersect when supplied. Existing parent visibility/soft-delete gates apply before aggregation/pagination. Group names are public under current model; locked private member labels/counts/entries stay excluded. No schema, group privacy, provider, outbox, notification-history or release changes.

## Candidate and evidence

Branch feat/090-group-heatmap; isolated worktrees/090-group-heatmap; base ddba8d367d575c91f8e355bb9a21fa408d6fea0c. Private freeze/handback supplies final HEAD and source/build/config/fixture/oracle resources. Base alone is not the candidate. Author smoke is separate from independent QA. PM owns review/UIQA acceptance/merge/deploy. Physical iPhone and production NOT_RUN.

Checks: backend Ruff/unit and tracker API regression on separate empty local test DB; frontend unit/lint/build; synthetic mock Chromium heatmap regression; actual app synthetic smoke separately. Retain failures/corrected reruns. Required CI names remain Backend checks, Frontend checks, Repository hooks, Migration QA, Production dependency check and any additional configured gates.

## Synthetic lifecycle

Use .agents/skills/verify-microsched/scripts/r1_sandbox.py. Only assigned Task090 checkout and microsched lane allowed. Adapter preserves archived H14 helpers and uses existing sandbox ownership/migration/fixture mechanisms. No paid provider, in-process cron or Mimi chat. Cached pgvector/pgvector:pg18 required, no implicit pull.

| Resource | Exact ownership |
|---|---|
| Task/container | r1-090-20261022-microsched |
| Volume | r1-090-20261022-microsched-db, exact harness.task label |
| Loopback ports | PostgreSQL55490, backend8000, frontend5173 |
| Preview/test DB | microsched_r1_090 / microsched_r1_090_tests |
| State | .local/r1-090/microsched; synthetic credentials never logged/committed |
| Binding | current private freeze, never archived H14 |

From granted checkout and installed backend Python, replace CURRENT_BINDING with inspected private binding:

```powershell
& backend/.venv/Scripts/python.exe -B .agents/skills/verify-microsched/scripts/r1_sandbox.py --source . --binding CURRENT_BINDING --lane microsched start
# Doctor: same command ending status, then verify
# Cleanup: same command ending stop; retain volume/data and evidence
```

Doctor caveat: inherited _load_state may backfill legacy volume metadata in runtime.json during status; verify calls _activate_synthetic_settings, replacing process settings/environment and clearing the settings cache. Doctor is owner-operated and not universally side-effect-free. Strict read-only reviewers use direct read-only resource/PID and /api/readyz probes, or request the actual owner before write-capable Doctor actions. No guard/helper behavior changes.

start-db prepares only owned DB and baseline fixture. Tests use separate empty DB to preserve preview fixture/encryption. On first image initialization, inherited pg_isready can precede final postmaster restart: if connection lost, inspect exact container/log/state and resume same healthy namespace; no reinstall/recreate/reset.

Baseline fixture is not H2 oracle. Private R1 seed manifest supplies groups, two public members, excluded other-group/private members, VN boundary entries, notes/values and paging IDs. Inspect exact source/resources before adoption; new inputs need new binding. Compare shared freeze at batch boundaries. Do not edit source/helpers/fixtures during independent QA.

Rollback: reviewed revert of task commit, no migration/data rollback. Merge/deploy require later PM release grant and independent evidence.

## Author handoff — 2026-oct-23 (Asia/Saigon)

H2 implemented with no migration. Inherited current-source results: backend1216passed/1skipped (480PGtests deselected), trackerAPI22passed, frontend282passed, mockheatmap13passed/9viewport-skipped; lint/build/Ruff receipts retained. Actual synthetic app author smoke covered group57/year, VNdays1+56, lazy detail50→56, records50/6, empty0, tracker30, All58 and390×844 touch drilldown. These are author observations, not independent acceptance.

Known diagnostic: React development console emitted a LiveStatus/HeatmapDayDetail render-update warning on first mobile detail open; interaction/data assertions completed. The shared cache-subscription and detail-query patterns predate this slice, but a separate baseline runtime reproduction was not run. No unrelated LiveStatus change included. Existing mobile month calendar uses its labelled internal horizontal scroll; shell did not overflow.

Private frozen handback supplies final commit, bindings, fixture/oracle, installed build, runtime/PIDs, command receipts and screenshot report. Independent review/UIQA, required CI, physical iPhone/Safari and production remain separate gates.
