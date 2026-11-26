# Mimi feature recipes

Source map for `develop@2a1760aa5b5b27702fcf354a566e8ae852e32c74`. Read [SKILL](../SKILL.md), the current grant and the [verification contract](../../../../docs/verification/README.md). A current synthetic batch needs the correct STANDARD session/workspace, entitled capabilities, fixture/oracle and transport. Preserve existing provider, write, device and evidence gates.

| Entrypoint | Source on this baseline | Historical journey | Runtime on this baseline |
|---|---|---|---|
| [Conversation creation and rename](conversation-metadata.md) | `frontend/src/MimiControlCenter.tsx:87` | `J1` | NOT_RUN |
| [Responsive side-chat and pop-out](dock.md) | `frontend/src/MimiDock.tsx:61` | `J1/J2` | NOT_RUN |
| [Workspace rails and conversation history](history-workspace.md) | `frontend/src/MimiControlCenter.tsx:209` | `J1/J2` | NOT_RUN |
| [Model/effort and durable operating policy](configuration.md) | `frontend/src/MimiConfiguration.tsx:139` | `J5` | NOT_RUN |
| [Workspace context, preview and run diagnostics](context-rail.md) | `frontend/src/MimiContextRail.tsx:109` | `J2/J4` | NOT_RUN |
| [Messages, provenance and composer](messages.md) | `frontend/src/MimiScreen.tsx:1292` | `J2` | NOT_RUN |
| [Preview, revision and frozen confirmation](proposal-confirmation.md) | `frontend/src/MimiScreen.tsx:142` | `J3` | NOT_RUN |
| [Run observations, context and recovery](run-context.md) | `frontend/src/MimiScreen.tsx:1068` | `J4` | NOT_RUN |
| [Technical detail dialog](technical.md) | `frontend/src/MimiScreen.tsx:1341` | `J2/J4` | NOT_RUN |
| [Response feedback and target binding](feedback.md) | `frontend/src/MimiScreen.tsx:1109` | `EDGE_DEFERRED` | NOT_RUN |
| [Mimi attention and device notifications](attention.md) | `frontend/src/MimiNotifications.tsx:33` | `EXISTING_DEVICE_GATE` | NOT_RUN |
| [Task collection review and revision](collection.md) | `frontend/src/MimiCollectionReview.tsx:24` | `J3` | NOT_RUN |
| [Voice v1 and v2](voice.md) | `frontend/src/MimiScreen.tsx:1322` | — | NOT_RUN |

Historical journeys refer to the Owner192 G2 binding (exact closure with inherited base `aa79a94`) and dated evidence in each recipe. The [archived source doctor](../scripts/driver.py) accepts its approved old checkout only. Its matching files never established full closure. Use a current task-owned binding and admitted runner for a new runtime. Experimental workflow pilot has a separate backend/flag and no mounted app entrypoint at this baseline.
