# 044 — homepage + denied, Owner preview

Status: OWNER PREVIEW READY (2026-09-07), local draft only; not release-ready/Owner-accepted. Owner approved 2026-09-07: A product-first + B journey + C planned extensions; requested a full real local app to see and try. Executor/writer: T1; independent agents research/review only except the separate synthetic runtime grant. No publication, PR merge or production deployment until Owner has reviewed this draft.

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

Owner follow-up: another UI/UX agent is active; preserve that lane and re-query/reconcile develop before any eventual PR. Add a website link to the GitHub profile's microSched section only AFTER the public homepage is deployed and verified. The separate profile availability copy is updated now: busy through late November2026, schedule expected to gradually open from early December; no guaranteed job-start date.

## Preview receipts, 2026-09-07

- Frontend lint/build PASS (including apple icon and PWA surface guards); 122 tests /16files PASS.
- Backend 398 non-PG tests PASS; 197 PG tests deselected/NOT_RUN. Focused auth/denied 33PASS; Ruff check/format PASS on changed Python files.
- Real local Chromium: 11 case groups PASS, including VI/EN at1280/390/320, no overflow or <12px text, primary targets≥44px, assets loaded, skip/anchor, locale reload, deep-link href, app↔home/logout, public page only queries /api/me, controlled503 distinct from401, denied403, landscape and CSS200% text. No JS page errors or unexpected outbound requests in routed browser lane.
- Measured text pairs: 64VI +64EN +9denied, no normal/large-text contrast failure in visible opaque pairs. This is not a full non-text/all-state accessibility audit.
- Separate fresh service-worker-enabled context: controller active, /auth/denied still403 and rendered correctly, Home returns to /home. Built manifest start_url remains /.
- Independent code/auth review: no P1/P2 on frozen source; independent actual-screenshot/copy review: one EN/VI miGarden P2 fixed and exact-hash delta closed. Optional hero forced-break removed and visually rechecked. Screenshot framing and EN logo returning to VI are optional Owner-feedback items, not claimed fixed.
- Final HomePage source SHA256 F683A8466DC3E9B816F22451C645770365AE43BC310D9798B2CEDFE6C2DFB771. Evidence/scripts/screenshots and resource/stop handoff retained privately in the session's homepage-preview-v1 and homepage-runtime-v1 packages.
- CI, real OAuth, physical iPhone/Safari, production-image QA and production deployment: NOT_RUN. No microSched commit/PR/merge/push, no cleanup/deletion. Preview remains in isolated worktree for Owner feedback.
