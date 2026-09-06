# Task 043 — delivery evidence, 2026-09-06

Status: local validation and independent review closure in progress. Implementation freeze: `236597738a218e88fb4be1cfa7a9189434655f11`, base `ac35b75db73a0c4e78aebea536bc7a026f594a98`. See [the task contract](043-ui-ux-readability.md) for the Owner grant and boundaries. This receipt is appended by batch; later results supersede an explicitly identified earlier failure, never erase it.

## Delivered behavior

| Owner problem | Implemented behavior |
|---|---|
| Logo does not provide a useful return action | Semantic home link returns to the default Task view without reloading normal SPA navigation; modified link clicks keep browser behavior. |
| Private and standard objects look alike | Shared lock label, leading border and token-based surface across Task, Notes, Tracker, calendar grid/detail and agenda. Existing locked/unlocked data gates remain intact. |
| Laptop month chips are too narrow | Calendar can use the wider application canvas, with collapsible mini-calendar and two-line chips including start times. Sticky month heading follows the central visible week. Full day/event detail remains accessible. |
| Phone month grid truncates almost everything | Optional persisted “Theo ngày” mode combines a month picker with readable selected-day event and task cards. Month navigation extends fetched ranges; loading/error/retry and quick-add draft states are explicit. |
| Reminder section shows a clock time without the next date | “Nhắc nhở sắp tới” groups by projected date and time in Vietnam, describes recurrence and preserves an unknown-date fallback. Same clock time on different dates forms distinct groups. |
| Task page stacks large empty day cards | Empty dates form compact chronological rows, while today and populated dates retain full-width groups. Existing filter, loaded range, history and overdue actions remain available. |

The server adds nullable `next_reminder_at` to the existing tracker response. The scheduler and projection share the extracted canonical recurrence helpers. Fixed and after-entry schedules, recorded dispatches, Vietnam date boundaries and the existing 15-minute grace are preserved. This is schedule projection, not a delivery/retry promise. There is no schema change, new polling or permission-boundary change.

## Verification batches

Commands ran in the respective frontend/backend/root directories unless explicitly stated. Raw logs are retained locally under `worktrees/043-ui-ux-readability/output/task-043/`, outside browser output cleanup. These ignored files are local evidence, not files downloadable from a GitHub checkout.

| Layer and frozen source | Command / receipt | Observed result |
|---|---|---|
| Backend, unchanged since `c8841c3` | Sanitized environment pytest runner, `-m 'not pg' -q -p no:cacheprovider`; `backend-nonpg-final.log` | 394 PASS, 197 PG deselected, exit 0. Two existing deprecation/syntax warnings. |
| Backend lint/format | Ruff check and format check; `ruff-final.log`, `ruff-format-final.log` | PASS, exit 0; 124 files already formatted. |
| Frontend unit at `f97c6b9` | `npm test`; `unit-final.log` | 116 PASS in 15 files, exit 0. Later delta is agenda presentation and a test ID; no unit-tested helper changed. |
| Frontend lint after review delta | `npm run lint`; `frontend-lint-review.log` | PASS, exit 0. |
| Repository at `f97c6b9` | Python 3.14 `-m pre_commit run --all-files`; `hooks-final.log` | All hooks PASS, exit 0. Staged review delta hooks also passed. |
| Full browser at `f97c6b9` | Explicit frontend config from repository root, capture enabled; `e2e-full.log` | 213 PASS, 29 conditional skips, 4 FAIL, exit 1. All four failures: duplicate reminder display/form test ID. |
| Review findings RED | Mobile agenda entry and pending mutation tests before correction; `review-red.log` | 2 intended FAIL, exit 1: retained scrollTop 183 instead of 0; checkbox remained enabled during PATCH. |
| Related browser regression | Agenda, privacy/reminders, dogfooding-036 and ui-standards; `review-green.log` | 62 PASS, 2 FAIL, exit 1. Both failures were the new test's missing cross-context evaluate argument, subsequently corrected. Existing tracker editor flows passed. |
| Review findings GREEN | Both viewports; `review-green-final.log` | 4 PASS, exit 0. Picker entry, grid restoration, pending feedback, failed update and successful retry verified. |

Browser runs launch the production frontend build through the existing Playwright configuration and use isolated API-mocked contexts. They are full-application synthetic frontend tests, not a local production-image/Postgres cell. No real browser profile, account payload, Neon operation or live data fixture was used. The original personal screenshots were not copied into fixtures or published.

## Independent review ledger

Backend reviewer `/root/review_projection` reviewed `016bf36` versus the base, independently compared the extracted helpers' AST and executed a synthetic +5-day calculation. PASS on recurrence parity, readable/deleted scope, maximum two batched metadata queries, compatibility and null/error behavior. It inspected the worker's intended RED and 394-PASS raw evidence; it did not independently rerun the full suite or Postgres performance checks.

UI reviewer `/root/review_ui` reviewed frozen `f97c6b9` with independent context, then the delta to `2365977`. Axes covered navigation, month ranges, empty/loading/error states, quick-add drafts, private remount/cache boundaries, reminder instants, Task history/filter semantics and changed touch/focus/text behavior. It verified all 19 initial screenshot entries against the frozen SHA and MD5/SHA256, and visually inspected 14. T1 independently checked all 19 image hashes.

| ID | Original finding | Resolution and proof |
|---|---|---|
| UI-1, P2 | Shared calendar scroll offset hid the month picker when entering agenda | Layout effect resets agenda to top after mounting and restores the saved grid position on return. Intended RED → GREEN in both viewports. |
| UI-2, P2 | New agenda checkbox lacked pending/error guidance and allowed duplicate submission | Pending controls disabled, active task shows “Đang lưu…”, error explains retry through the checkbox. Delayed failing PATCH → visible error → successful retry tested. |
| CHECK-1 | New time display duplicated the existing editor input test ID | Display uses `tracker-upcoming-time`; existing editor input is unchanged. All four previously failing editor cases passed in the related suite. |

No other required findings were reported. Final screenshot delta closure and full-suite result are appended below when observed.

## Unrun boundaries

Physical iPhone/Safari, assistive technology, Owner aesthetic preview, real-account/production UI acceptance, local Docker production-image cell and local Postgres QA are NOT_RUN. CI Postgres, exact-head gates and ordinary deployment/readiness are separate pending delivery steps. No production migration or main release is part of this change. Existing branches/worktrees and user artifacts are retained.

## Final local batch, 2026-09-06 23:43 VN

Full production-frontend synthetic browser run at `2365977`: **219 PASS, 31 conditional skips, exit 0**, `e2e-final.log`, 6.1 minutes. The capture switch was enabled; both Task043 capture cases passed. Prior four editor failures are resolved. The command ran from frontend with `--output=test-results/task-043/browser-final --workers=2`. Unchanged long observer cases verified the existing polling/session behavior.

T1's final screenshot inspection found mobile Task text still squeezed by the existing action column. Presentation-only delta `8e5a2f0be347e90e16c9d8b7155c072cf5c50305` moves actions below task content on phones, uses a 24px checkbox and limits tab transitions to colors. The new geometry test checks title width above 180px, actions below the title, touch dimensions, containment and no page overflow. Focused Task/App regression and full screen recapture: **68 PASS, 4 conditional skips, exit 0**, `layout-final.log`; the two unchanged long polling tests were excluded from this delta run because they had just passed in the full run. Final-source full suite remains a CI gate, not implied by this focused result. Lint passed in `lint-layout-final.log`.

Independent UI delta review through `8e5a2f0`: **PASS**, all three ledger items closed, no new findings. The reviewer inspected raw results, both corrected picker captures at `2365977`, and final mobile Task top/dates at `8e5a2f0`. T1 verified all **19** final entries against `8e5a2f0`, MD5 and SHA256: **0 mismatches, 0 duplicate MD5s**, recorded in `screenshot-hash-final.json`. Screenshots at `output/task-043/screenshots/` comprise 10 desktop 1280×800 and 9 mobile 1170×2532 (390×844 CSS pixels). The prior complete set is preserved under `screenshots-2365977/`. The capture locks the synthetic private gate at the end and disposes its isolated browser context.

### Screenshot taste checkpoints

Paths below are relative to the integration worktree's `output/task-043/screenshots/`; all are synthetic. The visible header descriptions are literal image observations, not runtime/privacy acceptance claims. T1 inspected the final images below after checking all hashes; reviewer observations are separately identified above.

| Image | Visible header and taste |
|---|---|
| `desktop-notes-locked-30.png` | Header reads “Riêng tư · đang khoá”, with “Mở khoá” and the Notes tab selected. Standard cards form an even list, with aligned titles and actions and generous spacing between records. |
| `mobile-notes-locked-30.png` | The locked header and “Danh sách ghi chú” are visible. Card text uses the available width and actions sit on their own row; the visible list has a regular rhythm. |
| `desktop-notes-unlocked-35.png` | Header reads “Riêng tư · còn 36 phút”; the first private note shows “Đã ghim” and an outlined “Riêng tư” label. Its leading edge and tinted surface distinguish it from the next white standard card without changing the established palette. |
| `mobile-notes-unlocked-35.png` | The unlocked header appears above the first pinned private note. The filled pin badge and outlined privacy label have different visual roles, while the strong leading edge identifies the card even across its longer content. |
| `desktop-note-private-long-checklist.png` | Dialog title is “Riêng tư · kế hoạch học tập và dự án 1”, followed by privacy/pin badges and “10/30 mục đã xong”. Text and action columns align across the visible checklist rows, and the list continues within the dialog. |
| `mobile-note-private-long-checklist.png` | The same dialog title, two badges and checklist count are visible above the long list. Actions stack below each item's text, preserving readable lines and regular spacing through the captured portion. |
| `mobile-tasks-top.png` | The unlocked header, selected Task tab, quick-add and “Đang mở” appear above compact September 3–5 dates and the September 6 “Hôm nay” group. The first task title now occupies two readable lines, with the actions below rather than beside it. |
| `desktop-calendar-wide.png` | The unlocked header and “tháng 9 năm 2026” appear above the grid, with “Hiện lịch nhỏ” available. Two-line chips retain start times and more title text; the dense Sunday grows taller, and the grid still needs the detail view for complete long content. |

The preserved corrected picker evidence also has independent taste review: mobile `screenshots-2365977/mobile-calendar-picker.png` shows the unlocked badge, September header and month picker with September 6 selected directly below the controls. Regularly spaced dates and event dots make the selection easy to read. Desktop `screenshots-2365977/desktop-calendar-picker.png` shows the unlocked header, full picker and selected-day heading; the seven columns are evenly spaced, with a sparse but orderly wide layout.

Local checks do not claim that Owner has approved the appearance or used a physical phone. The remaining delivery gate is exact-head CI followed by authorized ordinary deploy and readiness verification.
