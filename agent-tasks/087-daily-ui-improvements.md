# Task 087 — Daily UI improvements

Status 2026-10-20: B1/B2 implemented in the local candidate, including shared Task previews. Annual heatmap frozen at `89a45b93c2506571d9df33de9eec176ced09fe38`; B1 frozen at `82435864070ec8659e056bc0f6619a79bf991765` with builder checks passed and Owner manual Vietnamese input acceptance reported. All B1/B2 visuals approved. Task-preview builder checks passed (281 frontend tests, 7 applicable synthetic browser cases); native reschedule and quick-create drag paths verified. Consolidated independent QA/CI/release acceptance remains with the release coordinator; no production result is claimed here. B3 held; day-annotation reminders require a separate packet.

## B1 — Note checklist and positive supplemental feedback

- Note checklist: Ctrl+Enter adds/saves; Enter inserts a newline. Keep the existing add/edit row layout and visible click controls, with concise hints beneath each textarea. Blank, pending, repeated shortcut and composing input must not cause unintended writes. Acknowledged add/edit must preserve any newer draft revision, including edits that return to the same text.
- Positive supplemental feedback: synchronous native editing must preserve caret and selection for insert/delete/replace/paste and Vietnamese composition. Keep memory-only query drafts keyed by conversation and turn; immediate editing state must not replace their lifecycle. Do not restore selection after every render.
- Detail capacity is exactly **8,000 Unicode code points**, with a matching counter/client guard. The combined API comment contract remains **10,000**; negative feedback retains its existing 500-character scope. Preserve composition text without slicing or rewriting it; over-limit content stays editable and cannot start a new submission until shortened.
- Keep explicit positive vote separate from optional supplemental submission, with separate client IDs. Preserve reasons, target binding, unknown-result retries using the original body/key, acknowledgment identity/provenance checks and newer drafts after late acknowledgments. Closing a dialog or changing target must not rebind another draft.
- Approved positive layout: moderately wider desktop dialog, compact reason chips, larger textarea, and an aligned “Để sau” / “Gửi bổ sung” footer. Mobile must fit. Surrounding app layout remains unchanged.

## Annual heatmap

- Add grouped day hover/focus preview to the annual SVG contribution grid. Show Vietnam date/count, tracker name/type, each full note/time and amount VND, quantity with actual unit, or event count. All and single tracker modes follow the selected filter.
- Show clear per-group totals without summing incompatible dimensions. Historical entry values remain visible when current tracker input mode differs.
- Load only an active day's details; no 365 eager detail requests. Large days use explicit bounded paging and visible partial totals until all entries are loaded.
- Preserve month/touch details, click/keyboard access to full records, private gating and loading/error/empty/future states. Annual keyboard navigation uses one tab stop plus directional navigation; no essential information is hover-only. Long text wraps at readable sizes using existing components/tokens/Nunito/light theme.

## Shared Task previews — local implemented candidate

The compact light preview is shared by Task titles and month-calendar task chips. Keep the actual title on its card/chip; the preview includes content/checklist and useful Vietnam date/priority metadata, without a duplicate Task title heading or instructional click footer. All checklist rows are read-only, with completed/total counts; full body/list content scrolls without stored-text truncation. Empty sections are omitted. Desktop hover/focus and existing touch/full-detail/edit paths remain available. Calendar summaries retain existing body/items/priority data from every cursor page; no preview API requests or polling are added. Existing completion and drag actions remain independent; the drop target respects move/copy compatibility for task rescheduling versus quick-create drags.

## Evidence and delivery

Use the actual frontend build and isolated synthetic APIs. The B1 browser receipt changed positive feedback caret5 to caret3 for the same middle-insert action, with editing/composition/8,000-codepoint/draft-ACK checks. Owner separately reported normal manual UniKey typing and middle edits on the frozen B1 preview; this is Owner-observed acceptance, not synthetic proof. Physical iPhone/Safari remains NOT_RUN until observed. Task-preview builder checks cover both surfaces, keyboard/full-detail paths, checkbox/drag independence, privacy, empty/long content, paged history, Vietnam dates and mobile layout.

Keep builder evidence separate from consolidated independent QA. Run applicable frontend tests/lint/build and repository hooks; preserve required CI/release gates. The technical-writer handoff permits local commits, without push/PR/merge/deploy or cleanup. The separately authorized release coordinator owns delivery through branch → PR into develop, fresh exact head/base/gates, CAS merge/deploy and readiness verification; production proof requires matching readiness commit and db=up.

No outbox, reminder/day-annotation backend, schema/auth/provider/policy changes, production data, credentials, new dependencies or unrelated harness work.
