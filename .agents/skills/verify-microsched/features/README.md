# microSched feature recipes

Đây là source/prerequisite map, không phải current runtime acceptance. Read [SKILL](../SKILL.md), current grant và [verification](../../../../docs/verification/README.md) trước khi chạy. Recipe line numbers, frozen tuples và historical verdicts cần đối chiếu exact candidate; không tự launch historical runtime. Current implementation overview ở [project guide](../../../../docs/project-guide.md).

Bảng bên dưới giữ dated source snapshot để định vị recipe. NOT_RUN/OBSERVED_ACCEPTED trong snapshot chỉ có nghĩa tại source/receipt của nó; không phải toàn app hiện tại. Mọi required cases/gates vẫn theo current contracts/specs.

Affected recipes bổ sung: [offline outbox](offline-outbox.md), [responsive shell](responsive-shell.md), [content density](content-density.md), [funding Entry](funding-entry.md).

| Entrypoint / feature | Exact source navigation | Status |
|---|---|---|
| [Public homepage language and login link](public-home.md) | `frontend/src/HomePage.tsx:144` | OBSERVED_ACCEPTED — attempt4, 6/6 UI +15/15 image observations |
| [Task tab and task lifecycle](task-calendar.md) | `frontend/src/App.tsx:168` | NOT_RUN |
| [Calendar navigation and event sources](calendar.md) | `frontend/src/App.tsx:108` | NOT_RUN |
| [Notes and reflections](notes.md) | `frontend/src/App.tsx:178` | NOT_RUN |
| [Tracker editors and records](tracker-form.md) | `frontend/src/App.tsx:198` | NOT_RUN |
| [Subscription management route](subscription.md) | `frontend/src/App.tsx:131` | NOT_RUN |
| [Reminder confirmation deep link](reminder-confirm.md) | `frontend/src/App.tsx:131` | NOT_RUN |
| [Reminder center](reminder-center.md) | `frontend/src/App.tsx:139` | NOT_RUN |
| [Private visibility gate](private-gate.md) | `frontend/src/App.tsx:140` | NOT_RUN |
| [Mimi workspace and dock entrypoints](mimi-entry.md) | `frontend/src/App.tsx:137` | NOT_RUN |
| [Session, error and logout shell](session.md) | `frontend/src/App.tsx:44` | NOT_RUN |
| [PWA and visible data freshness](pwa-freshness.md) | `frontend/src/LiveStatus.tsx:43` | NOT_RUN |
