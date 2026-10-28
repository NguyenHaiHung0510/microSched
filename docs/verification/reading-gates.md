# Reading-gate registry

Contract hiện hành của [reading.py](../../backend/app/domain/reading.py), [domain models](../../backend/app/domain/models.py) và [Mimi models](../../backend/app/agent/models.py). Đây là reference/verification contract duy trì, không phải task implementation mới.

Mỗi model table=True khai trực tiếp cả `__privacy_gate__` và `__delete_gate__`: enum Gate.APPLIES/NONE/VIA_PARENT, không inherited default trên base model.

| Gate | Ý nghĩa | Helper |
|---|---|---|
| APPLIES | Có is_private/deleted_at trực tiếp | Kiểm metadata/cột; lọc private khi locked và lọc tombstone |
| NONE | Không có khái niệm ở trục này | Statement nguyên vẹn |
| VIA_PARENT | Khái niệm đi theo parent | Gọi trực tiếp raise ReadingGateError; JOIN và gate trên đúng parent/trục |

`readable` hợp `with_privacy_gate` và `not_deleted`. Missing/invalid declaration, APPLIES thiếu cột hoặc VIA_PARENT không có parent đúng trục phải báo table/flag/cách sửa, không đổi thành list rỗng thành công.

| Current models | Privacy | Delete |
|---|---|---|
| Task, Note, Tracker | APPLIES | APPLIES |
| TaskItem | VIA_PARENT (Task) | APPLIES |
| NoteItem | VIA_PARENT (Note) | VIA_PARENT (Note) |
| Entry, Subscription | VIA_PARENT (Tracker) | APPLIES |
| DayAnnotation, Message, MimiConversation | APPLIES | NONE |
| OneShotReminder, ReminderOccurrenceHandled | VIA_PARENT (typed source) | VIA_PARENT (typed source) |
| MimiMessage/Run/Event/ProviderCall/ChangeSet/ExecutionReceipt/RefreshMarker/Feedback/Evidence/NotificationIntent/NotificationDelivery | VIA_PARENT (conversation/causal owner) | NONE |
| CalendarSource/Event, TrackerGroup, AppSetting, AuditLog, PushSubscription, ReminderDispatch, TrackerReminderBatch/Item, AuthSession, ReminderHandledBatch, MimiDevicePreference | NONE | NONE |

Registry giúp đọc source; tests tự enumerate models, không tin danh sách chép tay. Thêm bảng/cột phải cập nhật metadata/migration/caller/reference cùng nhau. NONE không bỏ authentication hoặc domain-specific authorization.

## Verification obligations

- Enumerate mọi mapped table, kiểm hai declarations, APPLIES ⇔ physical column, NONE/VIA_PARENT không có cột, VIA_PARENT có FK parent APPLIES cùng trục.
- PG lane so với schema thật, mọi table app schema có model tương ứng; ORM match chưa chứng minh DB match.
- Behavioral list/get tests dùng locked/unlocked, child của private parent, deleted parent/child. Declaration đúng không chứng minh caller gọi gate.
- Guard/declaration semantic changes cần intended FAIL → restore → PASS và regression phù hợp. Hygiene này chỉ thay diagnostic locator, không thay gate/thêm guard.

Tests hiện hữu thuộc reading-gate và domain API/PG/Mimi safety suites; [Development](../engineering/development.md) giữ full non-PG/Migration QA commands.
