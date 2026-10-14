# Feature map — verify-mimi

Broad observed top-level source map for exact candidate `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37` at `harness-b-mimi-qa/microsched`. This is verification navigation, not product authority or whole-product acceptance. Every row is source-mapped and **NOT_RUN**; no runtime receipt exists in R3. The initial runtime batch still proves only public-home and conversation-metadata respectively. Read each feature for real prerequisites/oracle/gotchas before extending QA.

| Entrypoint / feature | Exact source navigation | Status |
|---|---|---|
| [Conversation creation and rename](conversation-metadata.md) | `frontend/src/MimiControlCenter.tsx:9` | NOT_RUN |
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
