# Public homepage language and login link

Source: `frontend/src/HomePage.tsx:144` (`login-link`) in exact `aa9d7251cdb506e968a6ffddfbae6767b6987327`; source root `harness-b-verification/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

English/Vietnamese, hero, relative login link, signed-in/guest/unknown presentation.

## How to get to it (user POV)

Fresh isolated context → /home?lang=vi → English → Tiếng Việt; inspect login destination without following it.

Real prerequisites: First approved case: exact microSched binding, Main-owned ready runtime, no authenticated profile.

## Driving it with H14 isolated browser/CLI

getByTestId("login-link"), #public-title, buttons English/Tiếng Việt.

Observable oracle: Hero visibly changes and restores; relative login link reachable; no application tabs or external request.

## Gotchas

Only this case has an automated initial recipe. Vite bootstrap requires read access to `/node_modules/vite/dist/client/env.mjs` at the bound local frontend origin; blocking this module can leave the page blank before `login-link` renders. The first actual attempt failed at that harness boundary; preserve its private receipt and replay after the reviewed policy correction. Viewport ≠ physical device.

Status: source-mapped; first runtime case FAIL (harness module admission), affected replay NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
