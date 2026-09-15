# Future direction — microSched public homepage ecosystem

Status: **OWNER VISION RECORDED / NOT AUTHORIZED FOR TASK 056 IMPLEMENTATION**
Recorded: 2026-09-15

## Product direction

Evolve the public homepage from a single microSched introduction into a compact ecosystem surface rather than one long page. Candidate top-level tabs/routes:

1. **microSched** — current product introduction and public entry points;
2. **Mimi** — only after Mimi reaches an appropriate public-ready state;
3. **miGarden** — only after that product is complete enough to present truthfully;
4. **microLink** — only after that product is complete enough to present truthfully;
5. **MIDEX** — current leaderboard, category champions, methodology, version history and downloadable sanitized artifacts after each complete evaluation round;
6. **About the Owner** — a polished personal/product-builder profile that can communicate more effectively than a repository profile alone.

The tab set is progressive: do not expose empty or fake product tabs. Each surface needs an explicit public-readiness decision, copy, privacy review, accessibility/responsive QA and release evidence. This future work is a significant public UI/product architecture change and requires its own approved package; it does not expand Task 056 implementation scope.

## MIDEX publication direction

MIDEX serves Mimi first, but its contracts should permit later open-source use:

- publish category champions plus `MIDEX-S`/`MIDEX-P`, not only one opaque score;
- publish formula/version, hard gates, weights, anchors, dataset manifest, confidence intervals, route timestamp and known omissions;
- publish sanitized aggregate receipts and reproducible fixtures/graders where privacy and licensing permit;
- identify cost provenance (`OBSERVED_BILLED`, `ROUTER_REPORTED`, `CATALOG_ESTIMATED`, `OWNER_SUPPLIED_ESTIMATE`, `NOT_AVAILABLE`);
- abstract private/local acquisition details behind `LOCAL_ABSTRACTED`; never expose keys, accounts or upstream arrangements;
- distinguish model/config research results from production-route certification when provider/quantization is not observable;
- retain versioned historical rounds so homepage visitors can see model, provider, pricing and methodology drift over time;
- keep the Owner's final selection and rationale distinct from the numerical ranking.

## Nearest future package

After Mimi and the first complete MIDEX round exist, prepare a separate homepage information-architecture/specification package covering routes/tabs, public artifact schema, publication automation boundaries, visual design, bilingual copy, SEO, accessibility, privacy/redaction, performance and rollback. No automatic publication follows from completing a benchmark; a sanitized release artifact remains an explicit gate.
