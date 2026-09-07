# Homepage and backup assessment — 2026-09-08

Owner scope: public homepage only; app stays single-user/allowlisted. Balance visitor experience with realistic nuisance abuse, keep the current cost cap, no autoscaling/machine increase or blanket challenge. This is measurement/advice, not authority to change hosting or security policy.

## Observed local baseline

Production Dockerfile candidate for Task 047, one CPU and 256 MB memory limit, same FastAPI static/API process. `frontend/scripts/measure-homepage-047.mjs` permits loopback only and issues a fixed 64-request burst, concurrency four, five-second request timeout. Chromium cold context blocks service workers; no network/CPU throttling. No production load/fault test.

- First public view fetched app JavaScript 460,960 bytes, shared HomePage JavaScript 249,340 bytes, CSS 71,358 bytes, plus the first showcase image 49,300 bytes. Observed resource transfer total about 834 KB, excluding HTML; this is local uncompressed traffic, not a mobile Internet timing estimate. FCP was not reported by this browser run; do not claim it passed a performance budget.
- GET `/` and a hashed `/assets/*.js` returned 200 with ETag but no explicit Cache-Control or Content-Encoding. GET `/api/me` without a session returned 401. Code rejects a missing session cookie before a DB lookup; a forged nonempty cookie still invokes session lookup.
- The burst mixed homepage, app asset and anonymous `/api/me`: 64/64 expected statuses; p50 15.6 ms, p95 42.3 ms, max 47.7 ms on this local run. This does not establish safe production concurrency or resistance to a distributed attack. Idle image memory observed 96.79 MiB/256 MiB before the burst.
- `fly.toml` specifies one shared CPU/256 MB, always-on, no HTTP concurrency stanza. This is repository configuration, not a fresh inventory of deployed machines. No general incoming request limiter is implemented by this assessment.

## What is worth doing next

1. **Worth a small performance change first:** separate/lazy-load the authenticated app so a visitor only loads the public surface, explicitly cache content-hashed assets (`public, max-age=31536000, immutable`), and revalidate HTML/service-worker manifests. Measure actual gzip/Brotli delivery before choosing precompression/proxy settings. Keep all authenticated/API/OAuth/private responses outside shared-cache rules. Verify old/new asset compatibility and PWA update behavior before delivery. This is a concrete proposal, not an applied configuration.
2. **CDN is useful if a custom domain is already desired:** edge static caching/compression and managed DDoS filtering protect before traffic reaches the small origin. Cloudflare proxying on Fly also changes certificate considerations; HTML/JSON are not cached by Cloudflare by default. Start with static assets, preserve API/OAuth bypass, test callback/PWA behavior. Do not assume “enable CDN” caches the entire app or closes direct origin access. [Fly integration](https://fly.io/docs/networking/understanding-cloudflare/), [Cloudflare defaults](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/).
3. **Origin resource limits still matter:** an attacker can request API routes even if the UI exposes only a homepage. Invalid-session lookups, OAuth starts, body sizes and expensive imports have different costs. Apply measured per-route bounds and overload behavior before an arbitrary blanket low per-IP rate that penalizes visitors sharing mobile/NAT addresses. A local reverse proxy can bound bodies/connections and serve cached files, but shares the origin's network/machine and cannot absorb a volumetric attack upstream. No new proxy/limit was installed.

Keep the current machine/cost policy. No evidence from this bounded run justifies upgrading RAM, autoscaling or challenging every visitor. A more exact CDN/domain proposal depends on the Owner's domain/hosting preference; no service purchase or pricing promise is made here.

## PIN and backup threat model

Current code verified: `backend/app/core/private_pin.py` hashes the six-digit display PIN with Argon2id; it does not import crypto or derive an encryption key. `backend/app/core/crypto.py` decrypts private columns using a separately configured 32-byte AES-GCM master key. The following conclusions concern those encrypted columns, not every field in a database dump.

| Attacker has | Consequence |
|---|---|
| App code and a decrypted database dump, no master key | They can remove cooldown and attack the PIN hash offline. Recovering that PIN does not provide the independent AES key. |
| Dump plus encryption master key | They can decrypt encrypted columns directly and bypass the display gate; trying one million PINs is unnecessary. |
| Only an age-encrypted backup file | They first need the matching age identity to open that outer archive; afterward the separate inner-encryption key still matters. This describes the intended layers, not verification of a particular backup. |

Do not strengthen cooldown as a solution to offline code modification. Keep the master key outside database backups, and avoid giving one storage/account compromise access to both backup and decryption identities. Changing to PIN-derived encryption would weaken the present independent-key design. No key material, backup archive or production secrets were read.

Actual recovery readiness is UNVERIFIED. A quarterly check and another after key/device changes is proportionate: privately confirm which backup maps to which age identity/master key version, independent recovery copies, and restore a small isolated sample through both layers. The agent can provide a checklist and record PASS/FAIL without collecting secrets or storage locations. Actual key/backup access and restore rehearsal remain Owner-operated; no background access or new quarterly automation was created.
