# Mimi feature recipes

Đây là source/prerequisite map, không phải current runtime acceptance. Read [SKILL](../SKILL.md), current grant và [verification](../../../../docs/verification/README.md) trước khi chạy. Recipe line numbers, frozen tuples và historical verdicts cần đối chiếu exact candidate; không tự launch historical runtime. Current implementation overview ở [project guide](../../../../docs/project-guide.md).

Bảng bên dưới giữ dated source snapshot để định vị recipe. NOT_RUN/OBSERVED_ACCEPTED trong snapshot chỉ có nghĩa tại source/receipt của nó; không phải toàn app hiện tại. Mọi required cases/gates vẫn theo current contracts/specs.

| Entrypoint | Current source | Journey | Current runtime |
|---|---|---|---|
| [Conversation creation and rename](conversation-metadata.md) | `frontend/src/MimiControlCenter.tsx:208` | `J1` | NOT_RUN |
| [Responsive side-chat and pop-out](dock.md) | `frontend/src/MimiDock.tsx:21` | `J1/J2` | NOT_RUN |
| [Workspace rails and conversation history](history-workspace.md) | `frontend/src/MimiControlCenter.tsx:207` | `J1/J2` | NOT_RUN |
| [Model/effort and durable operating policy](configuration.md) | `frontend/src/MimiConfiguration.tsx:146` | `J5` | NOT_RUN |
| [Workspace Context / Preview / Run tabs](context-rail.md) | `frontend/src/MimiContextRail.tsx:88` | `J2/J4` | NOT_RUN |
| [Messages, provenance and composer](messages.md) | `frontend/src/MimiScreen.tsx:1098` | `J2` | NOT_RUN |
| [Preview, revision and frozen confirmation](proposal-confirmation.md) | `frontend/src/MimiScreen.tsx:120` | `J3` | NOT_RUN |
| [Run observations, context and recovery](run-context.md) | `frontend/src/MimiRunObservations.tsx:13` | `J4` | NOT_RUN |
| [Technical detail dialog](technical.md) | `frontend/src/MimiScreen.tsx:1144` | `J2/J4` | NOT_RUN |
| [Response feedback and target binding](feedback.md) | `frontend/src/MimiScreen.tsx:931` | `EDGE_DEFERRED` | NOT_RUN |
| [Mimi attention and device notifications](attention.md) | `frontend/src/MimiNotifications.tsx:33` | `EXISTING_DEVICE_GATE` | NOT_RUN |
| [Task collection review and revision](collection.md) | `frontend/src/MimiCollectionReview.tsx:29` | `J3` | NOT_RUN |
