# AGENTS.md — microSched

Canonical entry point for every actor, including T1. Owner-approved migration: 2026-09-06. CLAUDE.md is compatibility-only.

## Read what applies

- [docs/harness-policy.md](docs/harness-policy.md): read for authority, delegation, review, merge/release or harness changes. T1 has bounded inherited authority to work/delegate/merge; no routine coordination-record prerequisite. Elevation needs a holder-issued grant; Owner-only boundaries remain.
- [docs/project-guide.md](docs/project-guide.md): project discovery and domain reading map. Read the relevant brief and task contract, not every linked file/history.
- [agent-tasks/README.md](agent-tasks/README.md): navigation/status, not approval. Re-query GitHub/runtime and task headers before current-state decisions.
- Approved specs/briefs control product meaning. Material requirement gaps or conflicting decisions: present both sides to Owner. Explicit approved migration supersedes the named old rules; history does not reactivate them.

## Hard boundaries

- Owner/task scope is the authority ceiling. T1 chooses proportional evidence and risk-based ad-review, including for its own work. Required/committed checks, reviews and acceptance cannot be dropped to make failure pass. Reviewers stay read-only absent a separate grant.
- No secrets, credentials, real account identifiers or production personal payloads in prompts/logs/fixtures/commits/PRs. Use .env.example; never bypass secret scanning.
- Changes including docs: separate branch → PR into develop; develop deploys, main is release-label only. Code task branches feat/NNN-slug; other work follows the host branch convention.
- Fresh exact head/base/diff/gates and `--match-head-commit` before merge; no blind auto-merge. Merge does not authorize cleanup. Retain dirty/active/unique work.
- No auto-migration on deploy. Never downgrade/round-trip live Neon; destructive migration tests use throwaway local/CI Postgres. Old app/stores are read-only rollback references; see project-guide.
- Neon branch create/delete/Restore/Sync remains Owner-operated. High-fidelity QA: ask Owner to sync develop from main, await confirmation, then approved scrub. Canonical procedure is [qa-framework](docs/qa-framework.md) §2.1. No production seed/fault/migration-rehearsal/repeated automation.
- Before UI writes, read [ui-brief](docs/ui-brief.md) and relevant QA contract. Existing shadcn components, no raw button/input/select; CSS tokens, no hardcoded colors; self-hosted Nunito; light-only; no hard card heights; text ≥12px; no hover-only interactions. Skills do not replace these decisions.
- Significant UI work: prefer full local app preview using existing QA setup. Owner preview ≠ CI/device/production acceptance.

## Browser/data safety

The Owner's real browser profile is not disposable. Read the applicable QA contract first.

- Only explicitly allowed accounts; confirm the selected role on the post-selection screen, not list position. Report role, never real address.
- Stay in microSched/localhost and necessary Google OAuth pages. No unrelated tabs/apps/account settings/new consent scopes.
- Never read cookie/password/autofill/history/profile stores directly. No real email, even partly redacted, in public artifacts.
- Inspect/crop screenshots for unrelated tabs, bookmarks and identity before publication.
- Synthetic disposable QA uses isolated contexts, not real profiles/copied storage. Physical iPhone is separate from viewport emulation.
- Log out of the app and close task tabs after use; preserve sanitized receipts.

## Execution/evidence

- Observed output versus inference must stay distinct; retain relevant raw output/receipt links. Local ≠ committed ≠ CI ≠ runtime/device ≠ production. Unrun is NOT_RUN/UNVERIFIED, not PASS.
- Timeout ≠ no side effects: inspect disk/process/package/image state before retrying. Split long installs; after ~2 unproductive attempts at one blocker, stop and report logs.
- After staging, verify `git status --short` and `git ls-files`; use `git check-ignore -v` if files vanish. One writer per worktree, exact scope.
- Moves require checking ignore/CI filters/CODEOWNERS/hooks/imports/scripts and exercising affected mechanisms. New safety guards need fail-for-intended-violation → restore → PASS proof.
- Live commands: backend/pyproject.toml, frontend/package.json, workflows. Python/tests in backend, npm in frontend, hooks at root. Ask Owner to start Docker when needed; CLI presence does not prove daemon.
- Preserve required-check names: Backend checks, Frontend checks, Repository hooks, Migration QA, Production dependency check; honor other configured required gates too.
- When changing .github configuration, verify which branch each consumer reads and writes (including scheduled workflows, community files and Dependabot target-branch). Default-branch delivery requires the authorized release flow; do not assume merging develop activates every consumer.
- Vietnamese commit/PR text uses UTF-8 files (`git commit -F`, `gh pr create --body-file`), not inline shell arguments. Commits explain why and include executor Co-Authored-By.
- Interval/cron/poll/retry changes: inspect finite-resource quotas and configs. Verify fallback/rollback before relying on it. Production proof: exact /api/readyz.commit + db=up, not merely /api/healthz.
