# Task083 acceptance matrix — T1 authored03/10/2026
Use AGENTS.md, docs/qa-framework.md§2.1 + ui-brief. T3 runs frozen candidate, records actualSHA/imageID/commandexit and PASS/FAIL/NOT_RUN percase. No findingquota; T1reconciles/accepts. Work only synthetic disposablecell, never real profiles/Neon/privateharness/authstores. Reuse025entrypoint and finite resourceownership; cleanup ownfixtureIDs/cell, preserve parallelresources.
| Case | Fixture/action | Required oracle |
|---|---|---|
| A01 recent20 | >60 public entries, two trackers, equal timestamps | 20 newest all; tracker filter gives only that tracker; sort deterministic timestamp+id |
| A02 periods | >=55 rows inside chosen VNday and out-of-range neighbors | Page1=50, page2=remaining, no duplicate/missing; day/month/quarter/year boundaries independently computed+07; end exclusive |
| A03 sorting/filter | oldestfirst, switchtracker/period/page | correct order; reset page; no previous-filter records masquerade as new data |
| A04 existing writes | edit/save/cancel/error; delete/undo on visibleentry | reload/API match, failedwrite no success, list/heatmap refresh; same-row controls |
| A05 activity | sameVietnamday counts0,1,2,3,5, leapday, yearboundary17:00UTC | levels0/1/2/3/3, labels exact3/5; correct year/day, no doublecount; sparse rows positive only |
| A06 privacy | public/private trackers, deletedentry/archivedparent; unlockthenlock while deferredresponse | hidden rows/counts absent server; UI draft/selection/cache cleared onlock; no staleprivate repaint |
| A07 navigation | selecttracker, month/year prev/next, dayviaSpace/Enter | visible currentday default; dayjump opens explorer correctfilters; futureday disabled; invalidyear/date finite noAPIcall |
| A08 states | empty, forced APIerror/delayedread thenretry | loading/error not zeros/empty success; retry recovers; failure notinfinite |
| A09 responsive/taste |390x844,768x1024,1280x695 ordinarynonF11; longVietnamese | measuredinnerWidth matches; no pageoverflow/clippedmodal/control; touch>=44px; font>=12px; focusvisible; fixedlegend0/1/2/>=3; exact counts accessible beyondcolor |
| A10 teardown | complete/failure | contextclosed, noforeignmutation, ownedresourcesgone; rawreceipts/sanitizedPNG+SHA256 |
Tests pin intended privacy/boundary violations with meaningful negative oracles; targetedunit/mock tests are not realDB/browserproof. Backend PG regression runs CI MigrationQA. Newactivityquery uses visibility join before aggregation, no decryptneeded. Localfullapp is predeploy gate; postdeploysmoke is narrow read-only realChromeWorkPlace. iPhone NOT_RUN separately; Owner productiondogfood separate.
