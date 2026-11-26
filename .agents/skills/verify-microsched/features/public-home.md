# Public homepage language and login link

Current source at the [indexed baseline](README.md): `frontend/src/HomePage.tsx:244`, `frontend/src/public-home.ts:8`, `frontend/src/PublicShowcase.tsx:86`.

## Sub-features

English/Vietnamese navigation, public microSched gallery, public Mimi, miGarden and About pages, and checking/guest/signed-in/unknown access states.

## How to get to it (user POV)

Open `/home?lang=vi&view=microsched`. Follow the public header links to `view=mimi`, `view=migarden` and `view=about`. Change language on a non-default view and use Back/deep-link reload. Use an isolated guest context and separately bound synthetic session or session fault for the other access states. Inspect login and external links in place.

## Driving it in a current synthetic candidate

Use header links inside navigation named **Các mục trên trang chủ** or **Homepage navigation**. Language switches are links **English** and **Tiếng Việt**. Check `#public-main[data-view]`, `aria-current="page"`, `#public-title` and document language. Guest has `login-link` with same-origin `/auth/login` and a relative `return_to`. Signed-in has `public-open-app` targeting `/`. Check gallery `public-gallery` and decoded `showcase-image` when the active slide is in view.

Oracle: View and language survive the appropriate links and reload. Public views render their own content without mounting protected app tabs. Freeze same-origin asset paths from `public-home.ts` and `PublicShowcase.tsx` for the selected view/viewport. External clip playback needs separate authorization.

## Gotchas

H14 evidence below belongs to the original homepage case and its archived asset allowlist. Vite bootstrap requires its concrete local env.mjs module; the homepage also loads ten existing localized desktop showcase PNGs. Original failures are retained: missing-module admission, then an attempt with 6/6 UI assertions but 20 blocked image GETs. Final independent attempt4 passed 6/6 UI,15/15 decoded image observations and zero blocked requests. Full-page pixels were inspected for this scope; this is not a general visual/scroll/responsive audit. Viewport emulation is not a physical device.

Status: OBSERVED_ACCEPTED for this public-home recipe only, exact aa9d7251, H14-N1/R9 attempt4. Evidence locator: microsched-attempt4/receipt.json and before/after pixels, final-grouped-retest-handback, final-runtime-cleanup and R6 final-technical-signoff in the private task record. Main stopped the exact runtime; evidence survived. The other eleven features in that H14 snapshot remain NOT_RUN; no full-product/CI/device/production claim.
