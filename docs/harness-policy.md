# Harness policy — bounded authority v1

**ACTIVE — Owner-approved 2026-09-06.** Canonical operating policy for every actor, including T1. Replaces blanket coordination-record authorization and fixed T1/T2/T3 execution bans, not domain briefs or task-specific safety gates.

## 1. Separate authorization, evidence and coordination

Authorization answers “is this actor allowed?”; evidence answers “is the result good enough?”; coordination records who does what, dependencies, state and history. None substitutes for the others. Coordination metadata is useful but not a routine authorization prerequisite.

## 2. Authority classes

### Inherited authority

After the Owner delegates an objective/role and boundaries, T1 may plan, work directly or delegate, create branches/worktrees/PRs, select model + reasoning effort, choose verification/review, accept work and merge within that grant. No new authorization record per routine action.

The actual Owner request/project rules bound the grant, not the title “T1”. It ends at completion, expiry if specified, revocation or scope change. An advisory/review request does not authorize implementation/publication. Missing requirements that materially change the outcome return to the Owner; routine implementation details do not.

T2/T3 inherit only their assigned work and role rights. A read-only reviewer cannot write/merge. The handoff must specify whether merge is included; the parent's full rights are a ceiling, not an automatic child grant.

### Scoped authorization — elevation

An executor needing rights outside its assigned role/scope obtains a grant from the holder. T1 may grant only rights T1 actually holds; Owner-only rights require the Owner.

Record **issuer, executor, action/scope, constraints, expiry/completion condition** and a traceable source of the issuer's actual instruction in existing task/handoff/coordination metadata. A standalone file is optional. The executor may transcribe a grant, but cannot self-issue it, extend scope/expiry or establish authenticity merely by typing an issuer name. Unverifiable issuer/source/scope means stop the elevated action.

Routine actions do not require a Git JSON envelope, RFC-8785 binding or independent validator. Existing task-specific machine-readable safety contracts remain mandatory unless explicitly changed by the Owner.

### Owner-only boundaries

Stop without explicit Owner authorization of the relevant boundary/action for:

- destructive production operations, real-data deletion or irreversible migration;
- security, credential, authentication, privacy or permission-boundary changes;
- major product/requirement changes or Owner-reserved architecture;
- material external commitments, exceptional costs or new public publication outside the task;
- changes to the harness authority model itself;
- anything explicitly Owner-only in the project/task contract.

Neon create/delete/Restore/Sync remains Owner-operated. Browser identity/private-data and QA gates remain intact. Sandbox/full-access capability is not business authorization. This policy is model-mediated; no universal mechanical authorization validator is claimed.

## 3. Outcome contract and review

Use the existing task artifact/prompt: outcome, scope/non-goals, dependencies, decision rights, relevant quality axes, evidence layer and stop/re-plan triggers. Do not require a second spec or approval of each procedural detail when boundaries are clear.

T1 chooses direct work/delegation by quality, speed, cost, uncertainty and blast radius. A “subagent” is any worker outside the main Owner–T1 chat, regardless of native/OpenCodex/other-task transport. Use supported, authorized mechanisms; one writer per worktree; parallel lanes read-only or isolated. Do not assume skill/memory propagation.

Ad-review is **risk-based, not automatically mandatory for routine changes**. T1 may request independent challenge of its own work. Give the reviewer the contract, raw evidence and immutable commit/artifact digest without steering it to confirm T1. Complete declared axes and return one consolidated ledger.

Findings distinguish acceptance violations, material regressions, optional improvements and evidence-only gaps. No finding quota. T1 reconciles and may reject findings with evidence. Re-review closes prior findings and checks relevant delta/regressions rather than expanding the backlog.

Committed task acceptance/review gates remain binding. T1 must not lower an Owner-approved outcome or drop a required failing check to declare success. Replanning may change methods without weakening the outcome; requirement/Owner-only changes return to the Owner.

Model upgrades and low-risk trials are Owner choices, not mandatory eval/canary programs. Use active capabilities, not historical model tables. Route probes prove callability only; do not silently substitute a specifically required route/model.

## 4. Merge and release

T1 may merge directly or assign an authorized executor after judging evidence sufficient within the inherited grant. Routine docs merges need no coordination record or fixed reviewer sequence.

1. Separate branch → PR into develop; do not bypass protection or force-push protected branches.
2. Immediately before merge, re-query OPEN/non-draft, MERGEABLE/CLEAN, exact head/current base, expected diff/scope, required checks/reviews and task gates. Pending/failing CI is not success.
3. Use `gh pr merge --match-head-commit <head>` or equivalent CAS, never auto-merge to skip judgment. Head/base/gate drift requires delta reconciliation and refreshed acceptance before acting.
4. Retain actor, authority source, head/base, evidence, command/exit and resulting merge SHA in existing receipts; no ceremonial record.
5. develop merge triggers the established production deploy. Ordinary non-destructive deployment through that workflow is within an authorized delivery task, not permission for migrations/new infrastructure/data operations. Claiming live delivery requires deploy evidence and exact `/api/readyz.commit` plus `db=up`.
6. main stays release-label after applicable production acceptance. Check the full release diff and its authorization; a policy task does not imply permission for an unrelated release.

Local, committed, CI, runtime, physical device and production are separate evidence layers. Docs-only changes may not need local app/device tests; label unrun layers rather than implying PASS.

## 5. QA, cleanup and stopping

- Read UI brief/QA contract before UI implementation. Significant changes should use full real local app preview with existing components and the established scrubbed/synthetic-data QA setup; no forced tiny mount or default temporary HTML.
- Preview approval accepts direction/interaction, not full QA, device or production. Real-data staging still requires Owner sync before scrub. Production is not a general test environment.
- OBSERVED / INFERRED / UNVERIFIED stay distinct, with relevant raw receipts. Timeout is not proof of no effects: inspect actual state before retrying.
- Merge does not authorize cleanup. Default-retain branches/worktrees; separately authorized exact cleanup targets need dirty/open-PR/reachability/unique-work checks. Dirty/active/unique/mismatching targets remain.
- Around two unproductive attempts at the same blocker, stop guessing and re-plan/escalate with logs. No universal count of review rounds; budget by risk/information gain.
- Deadline, silence, heartbeat, tool permission or metadata never expands scope or permits deletion/cancellation.
- Observation remains event-driven first. If T1 otherwise idles on live lanes, use one supported heartbeat per group (5 minutes ordinary, 8 minutes long visual QA unless Owner overrides), no duplicates/dense polling, retire when terminal. “Active monitor” requires actual schedule/wake evidence.

## 6. Knowledge and closeout

AGENTS.md is the compact entry point; project-guide.md routes domain reading; briefs own domain decisions; this file owns process. CLAUDE.md is compatibility-only. History/memory aid recall, not authority. Retrieve narrowly rather than reading whole archives.

Closeout updates current task status and dated receipts, canonical decisions and exceptions/NOT_RUN. Harness maintenance is one untimeboxed triage for duplication, stale claims, broad retrieval, authority risks and costly loops—not a forced eval, archive purge or framework install.

## 7. Interpretation checks

These cases test policy interpretation, **not a new enforcement engine**:

| Case | Decision |
|---|---|
| Authorized routine T1 docs merge, no coordination record, fresh gates pass | ALLOW |
| Coordination metadata claims rights without actual issuer grant | DENY |
| Read-only reviewer writes/merges or self-extends scope/expiry | DENY; obtain holder-issued grant |
| T1 grants Owner-only data deletion without Owner approval | DENY |
| Task requires two reviewers; only one completed | WAIT |
| Required CI fails or accepted head/base/diff drifts | STOP/reconcile |
| Merge done but cleanup target is dirty/unique | RETAIN |
| Neon QA approved but Owner has not synced | BLOCK before scrub |
| Chromium viewport passes but iPhone not run | Device NOT_RUN |
| Historical authorization schema claims new authority | No grant from history |

The 2026-09-06 Owner instruction explicitly authorizes this migration and application to PR #200 plus necessary migration PRs. It supersedes the old blanket-record model. Preserve old task-specific safety/acceptance requirements when resuming tasks; historical role recipes do not reactivate retired policy.
