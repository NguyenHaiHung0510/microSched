# Tracker capture, editors, records and heatmap

Current source at the [indexed baseline](README.md): `frontend/src/TrackerScreen.tsx:512`, `frontend/src/TrackerHeatmap.tsx:288` and `backend/app/web/routers/tracker.py:247`. Original H14 navigation is recoverable with `git show 48dc397663b145dab35994326af007dd0e26dcc7:.agents/skills/verify-microsched/H14-ARCHIVE.md`; private evidence uses the Owner/PM local archive locator in [Verification](../../../../docs/verification/README.md), not current acceptance.

## Sub-features

Existing tracker/group editors and records; affected H2 scope All / Group / Tracker, existing group membership, annual/month counts, grouped day tooltip/touch dialog, paginated records. This slice adds no group privacy model and changes no writes/reminders/schema.

## How to get to it (user POV)

Synthetic login → **Theo dõi** or `/trackers`. **Ghi nhanh** is the default. Use **Nhật ký** for records, **Báo cáo** → `tracker-report-toggle` for heatmap, finance and funding, and **Quản lý** for tracker/group forms. In **Heatmap số lần ghi**, select Tất cả / Nhóm / Tracker; group/tracker mode shows its existing selector. Keep selected year/month. Desktop hover/focus annual day shows grouped details; Enter/click opens records. Touch month day opens heatmap-touch-detail, then Xem chi tiết trong bảng bản ghi retains group scope. Records banner names the group and offers Xem tất cả nhóm explicitly.

Prerequisites: approved current runtime/binding; isolated synthetic groups including two public members, other group, empty group and private member; exact VN timestamps/notes/values and >50 same-day records for paging. Current private gate state declared. Group names stay public; private member labels/counts/entries obey existing authorization.

## Driving it with the current isolated browser

Use the current candidate binding and a fresh owned context. Use `tracker-tab-capture` / `tracker-tab-journal` / `tracker-tab-report` / `tracker-tab-manage` or their tab names. Capture uses `tracker-card` and `tracker-backdate`, Journal uses `entry-row` / `entry-edit` / `entry-edit-dialog`, and Manage uses `tracker-create`, `tracker-edit`, `tracker-form` and `group-form`. Check frozen tracker/group IDs and canonical Entry count/time after any separately granted write.

Heatmap selectors: heatmap-scope-all/group/tracker (aria-pressed), heatmap-group, heatmap-tracker, heatmap-year, heatmap-month, heatmap-summary, heatmap-year-day[data-day], heatmap-day[data-day], heatmap-year-preview, heatmap-touch-detail, heatmap-detail-entry/group/more/jump; records-group-scope, records-date, records-list, records-prev/next.

Oracle: selected group IDs filter authorized active parents in SQL before count/offset/limit. GET activity and entries both carry group_id; tracker_id intersects when supplied. VN half-open day boundaries determine counts. Annual/month/day/detail/record IDs and values agree with frozen seed truth, not just UI totals. All→Group→Tracker→All must not reuse another scope's data. Empty/deleted groups never default to all. Verify pointer and keyboard, actual390×844 touch viewport and1280×800 desktop; physical iPhone separate.

## Gotchas

Heatmap is collapsed until report expands. Annual SVG has one roving tab stop, arrow navigation/F2/Escape; mobile uses month touch dialog. Tooltip data is lazy and pages50 entries with a51st sentinel; partial totals are labelled. A private-lock remount intentionally resets to All. Membership is current, not historical. Group deletion unlinks members; requests for its UUID return empty. A missing selector shows an explicit state, not unfiltered data. Synthetic mock browser tests prove lifecycle only; actual HTTP/DB app smoke and independent batch are separate. Source maintained; independent acceptance NOT_RUN.

Historical Task090 receipts and driver stay with their original freeze. Existing source oracles include `frontend/e2e/task046-reporting.spec.ts` and `frontend/e2e/task046-management.spec.ts`. The later shell/region and funding paths are also mapped in [responsive shell](responsive-shell.md) and [funding Entry](funding-entry.md).
