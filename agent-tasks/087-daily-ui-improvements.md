# Task 087 — Daily UI improvements

Status 2026-10-20: B1 and annual heatmap implementation approved. Annual heatmap is locally frozen at `89a45b93c2506571d9df33de9eec176ced09fe38`; B1 local builder verification passed (278 frontend tests and 15 applicable synthetic browser cases). Independent QA, CI, physical-device and production acceptance are separate. All B1/B2 visuals are approved; Task preview implementation remains pending its successor handoff.

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

## Approved visuals, pending successor implementation — Task previews

The compact light shared preview for Task and month calendar is visually approved. Keep the actual title on its card/chip; the preview includes content/checklist and useful date/priority metadata, without a duplicate Task title heading or instructional click footer. Implementation is **pending the separate successor handoff**. No Task preview product changes are included in the B1/annual-heatmap candidate. Existing task editing, completion, drag and privacy behavior must remain intact in the successor.

## Evidence and delivery

Use the actual frontend build and isolated synthetic APIs. A baseline browser receipt observed `abcd`, caret 2, insert X → `abXcd` with Note caret 3 and positive-feedback caret 5. Builder verification must demonstrate positive caret 3 after the fix and cover related editing, composition, 8,000-codepoint, keyboard and draft/ACK lifecycle behavior. Chromium composition is not proof of physical UniKey; physical input and iPhone/Safari stay NOT_RUN until observed.

Keep builder evidence separate from consolidated independent QA. Run applicable frontend tests/lint/build and repository hooks; preserve required CI/release gates. This bounded handoff permits local commits, without push/PR/merge/deploy or cleanup. Any later release follows branch → PR into develop, fresh exact head/base/gates and CAS merge; production proof requires matching readiness commit and db=up.

No outbox, reminder/day-annotation backend, schema/auth/provider/policy changes, production data, credentials, new dependencies or unrelated harness work.
