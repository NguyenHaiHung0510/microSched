# Public homepage language and login link

Source: `frontend/src/HomePage.tsx:144` (`login-link`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

English/Vietnamese, hero, relative login link, signed-in/guest/unknown presentation.

## How to get to it (user POV)

Fresh isolated context → /home?lang=vi → English → Tiếng Việt; inspect login destination without following it.

Real prerequisites: First approved case: exact microSched binding, Main-owned ready runtime, no authenticated profile.

## Driving it with H14 isolated browser/CLI

getByTestId("login-link"), #public-title, buttons English/Tiếng Việt. At 1280×800, the exact ten vi/en desktop showcase paths decode as five complete images at each VI→EN→VI stage; receipt.showcase_assets records actual dimensions. Read admission remains fixed-origin GET/HEAD and an explicit microSched-only asset set.

Observable oracle: Hero visibly changes and restores; relative login link reachable; no application tabs or external request.

## Gotchas

Only this homepage case has an observed initial recipe. Vite bootstrap requires its concrete local env.mjs module; the homepage also loads ten existing localized desktop showcase PNGs. Original failures are retained: missing-module admission, then an attempt with 6/6 UI assertions but 20 blocked image GETs. Final independent attempt4 passed 6/6 UI,15/15 decoded image observations and zero blocked requests. Full-page pixels were inspected for this scope; this is not a general visual/scroll/responsive audit. Viewport emulation is not a physical device.

Status: OBSERVED_ACCEPTED for this public-home recipe only, exact aa9d7251, H14-N1/R9 attempt4. Evidence locator: microsched-attempt4/receipt.json and before/after pixels, final-grouped-retest-handback, final-runtime-cleanup and R6 final-technical-signoff in the private task record. Main stopped the exact runtime; evidence survived. Other eleven mapped features remain NOT_RUN; no full-product/CI/device/production claim.
