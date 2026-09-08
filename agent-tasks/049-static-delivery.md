# Task 049 — minimal static delivery

Status: IMPLEMENTED LOCALLY; CI/production pending.

Owner grant 2026-09-08: T1 may decide and deliver small, low-risk homepage improvements without technical micromanagement. Keep costs/topology, UI and existing application behavior. No CDN/proxy, scaling, load-to-failure test or routing rewrite. The approved cache boundary excludes API/OAuth/private responses from shared caches.

Implementation: Vite build automatically produces gzip alternatives for JS/CSS after PWA precache generation. The existing FastAPI static server serves these only when accepted, retaining original URL, MIME, conditional response and plaintext fallback. Hashed assets cache for one year immutable; HTML/worker/unhashed files revalidate. Missing assets return 404 rather than a cacheable HTML fallback. All API/auth responses use no-store. No new package or service; runtime does not compress data or cache private responses.

Verification: RED tests observed missing compression/cache headers and missing API no-store; GREEN after correction. Coverage includes gzip rejection, conditional 304, HEAD, Range using original bytes, missing gzip fallback, missing asset, shell/worker revalidation and anonymous API/auth boundaries. Native local FastAPI + actual Chromium: three initial JS/CSS resources transfer 211970 bytes including measured response overhead, versus 780012 decoded bytes; warm reload reports zero transfer for those assets, no page errors. Build precompresses four JS/CSS files from 780214 to 211254 bytes. These are local compression/cache measurements, not network timing or production capacity promises.

Actual service-worker registration/activation and offline shell reload PASS. Initial QA script incorrectly expected the existing worker to claim its first page; corrected QA to use normal navigation after activation, with a bounded deadline. Application worker lifecycle unchanged. Frontend build/lint and 145 unit tests PASS. Final backend 439 PASS (211 PG deselected), Ruff PASS; nine static-delivery cases are included. CI receipts pending. Physical device and production load testing NOT_RUN. Self-review only.

Rollback: prior server ignores gzip alternatives and serves original assets. Deploy the prior image to revert headers/serving behavior; no schema/data changes. Existing immutable assets are safe only while filenames remain content-hashed. Original files remain in every build. Old missing chunks return 404 rather than being retained indefinitely; PWA precaches the existing URL set, not duplicate gzip URLs.

Next: full final backend and required CI, exact-head CAS merge, exact deployed SHA/db plus bounded public asset/header smoke; no production load or private-account fixture.
