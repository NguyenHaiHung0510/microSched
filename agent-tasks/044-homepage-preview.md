# 044 — homepage + denied, Owner preview

Status: IMPLEMENTATION / RELEASE AUTHORIZED (2026-09-07). Owner accepted preview v2 and instructed “okay triển khai”. T1 may finalize verification, create/merge the homepage PR into develop, verify deployment, publish the requested live links, and use the normal release-label path for default-branch README delivery. Executor/writer: T1; reviewers remain read-only. No cleanup, real-data operations, auth-policy change or unrelated PR merge is included.

## Scope

- Bilingual public homepage at explicit `/home`; `/` remains app entry for valid sessions and shows homepage for guests. VI default in this draft, EN toggle affects public pages only.
- Preserve internal app deep links, OAuth return_to validation, server-side allowlist/session, private gate and SW `/api/` + `/auth/` navigation denylist. No auth classification changes, extra polling or new privileges.
- App has a visible homepage link; explicit homepage never forces a signed-in visitor back into app.
- Denied retains HTTP 403, neutral error copy, repository/home/creator links. Reuse frontend design tokens/components via a separate Vite-built document; retain a neutral static fallback if build is absent. No account/identity reflection or auto-retry OAuth.
- No app-wide redesign, logo change, analytics, external auto-loading, new dependencies, fabricated product screenshot, production data, Neon/host DB or migration on production.

## Legacy reconciliation

This newly approved task replaces 008h's old chosen layout, fixed section order and logged-out-only home assumption. Owner requests add creator profile and denied, superseding that old task's outbound-link whitelist and no-backend scope for these specific presentation changes. Identity stays at the already approved public creator name/profile; no other personal payloads. Existing project logo reused unchanged. Do not mark historical 008h DONE or drop other projects' acceptance debt.

## Local preview

Isolated worktree on base `03bdfe9005b4bd2290f9470e9358f718a1c0a313` from freshly fetched develop. Main checkout and parallel branches untouched. Node dependencies installed from lockfile. Synthetic PostgreSQL on loopback55444, native backend8044, Vite5144; exact runtime credentials/resources/receipts stay in private runtime package, never this public task. Owner explicitly started Docker. Existing local-only QA session entry is used; no real Google login.

This is a real-source interactive preview, NOT QA025 production-image acceptance. Screenshots show genuine UI rendered with authored synthetic data; no generative replacement of text/layout in product images. Optional AI art would be labeled illustration, not a demo/evidence asset.

Use backend-serving-built-app at http://127.0.0.1:8044/home for Owner acceptance (EN: ?lang=en), /auth/dev-session for the synthetic session, and /auth/denied for the real403 page. Vite5144 is authoring-only; its direct proxy of built denied needs asset handling before being used as an acceptance origin. No real Google login is configured in the synthetic preview.

## Preview acceptance

1. Typecheck/lint/build and relevant existing tests; focused homepage/return-to/denied regression checks. Guard changes (if any) need red→green intended-violation proof; no required check renamed.
2. Observe guest `/`, explicit `/home` signed/guest, enter app, app→home→app, deep-link login destination, 401 vs network unknown, real backend403 denied and no private queries on public page.
3. VI/EN desktop1280 + mobile390 and narrow320; no horizontal overflow, legible text ≥12px, primary targets≥44px, keyboard focus/anchors, no external resource loads. Reduced-motion/200% text checks scoped to new public pages.
4. Independent code/accuracy and actual screenshot taste review. No finding quota, consolidate actionable issues. Owner decides visual direction.
5. Leave preview safely accessible for Owner with exact local links and scoped stop instructions; no cleanup/deletion or public publication. iPhone/production/CI and real OAuth remain NOT_RUN.

Next gate: Owner feedback on local preview, then final implementation/QA/PR scope. Not automatically ready to merge because preview builds.

Superseding release decision, 2026-09-07: the Owner's “okay triển khai” accepts the v2 direction and authorizes delivery, replacing the preview-only publication hold above. Prior preview evidence remains distinct from CI/deployment/device evidence. Before merge require a frozen release review, fresh exact head/base/diff and all configured checks. Production smoke is bounded to deployed commit/db readiness plus unauthenticated homepage/denied/static assets; no production login, seed, mutation or fault injection. The existing preview remains available; do not stop/delete resources as part of merge.

Owner follow-up: another UI/UX agent is active; preserve that lane and re-query/reconcile develop before any eventual PR. Add a website link to the GitHub profile's microSched section only AFTER the public homepage is deployed and verified. The separate profile availability copy is updated now: busy through late November2026, schedule expected to gradually open from early December; no guaranteed job-start date.

Owner follow-up, 2026-09-07 (preview revision): PR #207 UI lane has completed. T1 must verify and integrate its develop changes into this isolated preview before refreshing the screenshots. Rewrite VI naturally using first-person mình–bạn, use I–you in EN, and mention learning to build software AND work with AI agents. Showcase all four current tabs using real app captures and synthetic data; optional deeper features must remain truthful to the app.

Publication follow-up, Owner-approved 2026-09-07: after public homepage release and verification, add its live public introduction URL to BOTH the GitHub profile repository and the microSched repository README, in both EN and VI. Keep repository/source links alongside it. Never publish localhost or claim the homepage is live before deployment. This is pending release, not permission to skip Owner preview acceptance.

## Preview v1 receipts, 2026-09-07 (historical)

- Frontend lint/build PASS (including apple icon and PWA surface guards); 122 tests /16files PASS.
- Backend 398 non-PG tests PASS; 197 PG tests deselected/NOT_RUN. Focused auth/denied 33PASS; Ruff check/format PASS on changed Python files.
- Real local Chromium: 11 case groups PASS, including VI/EN at1280/390/320, no overflow or <12px text, primary targets≥44px, assets loaded, skip/anchor, locale reload, deep-link href, app↔home/logout, public page only queries /api/me, controlled503 distinct from401, denied403, landscape and CSS200% text. No JS page errors or unexpected outbound requests in routed browser lane.
- Measured text pairs: 64VI +64EN +9denied, no normal/large-text contrast failure in visible opaque pairs. This is not a full non-text/all-state accessibility audit.
- Separate fresh service-worker-enabled context: controller active, /auth/denied still403 and rendered correctly, Home returns to /home. Built manifest start_url remains /.
- Independent code/auth review: no P1/P2 on frozen source; independent actual-screenshot/copy review: one EN/VI miGarden P2 fixed and exact-hash delta closed. Optional hero forced-break removed and visually rechecked. Screenshot framing and EN logo returning to VI are optional Owner-feedback items, not claimed fixed.
- Final HomePage source SHA256 F683A8466DC3E9B816F22451C645770365AE43BC310D9798B2CEDFE6C2DFB771. Evidence/scripts/screenshots and resource/stop handoff retained privately in the session's homepage-preview-v1 and homepage-runtime-v1 packages.
- CI, real OAuth, physical iPhone/Safari, production-image QA and production deployment: NOT_RUN. No microSched commit/PR/merge/push, no cleanup/deletion. Preview remains in isolated worktree for Owner feedback.

## Preview v2 receipts, 2026-09-07

- PR207 MERGED verified from GitHub; develop fetched at647d1049a00457d6fcb5d2a94fa4b4317b2c1eba. Saved a local v1 checkpoint, rebased this unpublished branch onto207, and preserved both LiveStatus and homepage imports at the only conflict. Integrated checkpoint751aa833c5fb7af8a979e3acbf75f55a00864aea; no remote push, other-worktree change or cleanup.
- VI rewritten as personal narration; EN first-person and software/agent-learning additions. Independent bilingual review's one P2 terminology ambiguity fixed and delta closed. Final HomePage SHA256 C3343514A226BF8EE112B5CFDE97169546D30C4E9D1E41A0D7714C0FB9FFEE14.
- Added a manual four-screen screenshot selector with local full-image links, native keyboard controls, selected-state semantics, responsive images and no autoplay. VI labels match actual app tabs. Scoped CSS retains approved components/tokens/font.
- Eight real app PNGs (1280x800 and390x844), all from integrated207 UI. Task mobile shows today's checklists; Notes shows a synthetic six-item checklist (four open/two done); Calendar mobile uses the real day view; Tracker shows the new finance report. T1 visually inspected all images and verified copy hashes. One additional synthetic note was created through the real local API; no existing data deleted/changed and no real data used.
- Frontend lint/build PASS, final135 tests/19files PASS; focused auth/denied33PASS. Full backend non-PG suite was not repeated for this frontend-only delta; v1 evidence remains separate. Build precache24entries/1395.41KiB; all eight public PNGs total491826bytes. Existing PWA inlineDynamicImports deprecation warning remains.
- Local Chromium: original11 public/auth/navigation/layout case groups PASS; new24 gallery cases (VI/EN x1280/390/320 x4screens) PASS, including all responsive image assets, native Tab/Space/Enter selection, locale-switch selection retention and no overflow. Selected border min4.80:1 and focus token3.90:1; actual keyboard outline visible. Opaque visible text checks70VI+70EN+9denied have0failures. Service worker controlled, denied403, Home recovery PASS. Not a full accessibility/device certification.
- Private ignored receipts and Owner handoff: output/playwright/homepage-v2/. Initial capture loading/session-race and browser lazy-load timing failures retained there; these are not hidden or claimed as application fixes. Final capture sessions logged out and contexts closed; runtime retained for Owner preview.
- Physical iPhone/Safari, real OAuth, full PG suite, CI, production-image QA and homepage publication: NOT_RUN. Owner preview approval remains pending; live links for profile AND repo READMEs remain pending verified release.
- Final independent gallery/code/screenshot review found no P1/P2 at the frozen source hashes. T1-image-hashes.json records15distinct MD5/SHA256 values across app and homepage/gallery captures. This is evidence-backed preview handoff, not Owner aesthetic approval or full runtime/device acceptance.
