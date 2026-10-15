# Feature map — verify-mimi

Broad source map for exact candidate `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37` at `harness-b-mimi-qa/microsched`. T1 technical acceptance 2026-10-15 covers only conversation-metadata attempt2: 4/4 assertions, zero blocked and completed owned cleanup. This map has **1/12 OBSERVED_ACCEPTED**, **11/12 NOT_RUN**; combined maps **2/24 (8.3%) OBSERVED_ACCEPTED**, **22/24 (91.7%) NOT_RUN**. Original failures remain in private H14-N1/R9 evidence. No latest-product/whole-app/device/provider-quality/CI/production acceptance. Evidence locator: final-grouped-retest-handback, the named case receipt/pixels, final-runtime-cleanup and R6 final-technical-signoff.

| Entrypoint / feature | Exact source navigation | Status |
|---|---|---|
| [Conversation creation and rename](conversation-metadata.md) | `frontend/src/MimiControlCenter.tsx:9` | OBSERVED_ACCEPTED — attempt2, 4/4 metadata assertions |
| [Responsive side-chat and pop-out](dock.md) | `frontend/src/MimiDock.tsx:21` | NOT_RUN |
| [Workspace rails and conversation history](history-workspace.md) | `frontend/src/MimiControlCenter.tsx:208` | NOT_RUN |
| [Model/effort configuration entrypoints](configuration.md) | `frontend/src/MimiConfiguration.tsx:145` | NOT_RUN |
| [Workspace Context / Preview / Run tabs](context-rail.md) | `frontend/src/MimiContextRail.tsx:16` | NOT_RUN |
| [Messages, provenance and composer](messages.md) | `frontend/src/MimiScreen.tsx:1077` | NOT_RUN |
| [Preview, revision and frozen confirmation](proposal-confirmation.md) | `frontend/src/MimiScreen.tsx:112` | NOT_RUN |
| [Run observations, context and recovery](run-context.md) | `frontend/src/MimiScreen.tsx:744` | NOT_RUN |
| [Technical detail dialog](technical.md) | `frontend/src/MimiScreen.tsx:1121` | NOT_RUN |
| [Response feedback and target binding](feedback.md) | `frontend/src/MimiScreen.tsx:929` | NOT_RUN |
| [Mimi attention and device notifications](attention.md) | `frontend/src/MimiNotifications.tsx:33` | NOT_RUN |
| [Task collection review and revision](collection.md) | `frontend/src/MimiCollectionReview.tsx:39` | NOT_RUN |

Enumeration boundary: observed top-level app routes/tabs/global controls and reachable Mimi workspace/dock entrypoints in the named source. This is a broad inventory, not exhaustive per-field/state QA. Later or hidden/provider-dependent behaviors remain described by prerequisite, not silently accepted. On source changes re-inventory entrypoints and affected recipes; do not treat this old snapshot as current production truth.
