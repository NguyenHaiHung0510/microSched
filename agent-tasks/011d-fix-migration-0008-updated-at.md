# Spec sửa lỗi — Migration 0008 thiếu updated_at + trigger set_updated_at

> **Executor:** Agent CRON (011d) · **Nguồn phát hiện:** T2 011c (DeepSeek/OpenCode free) khi chạy PG lane local — 2026-08-06.
> **Trạng thái:** MỚI — chờ xử lý. Không phải lỗi của 011c: 8 file của 011c đã commit `c21741f`, không đụng models/migration.

---

## 1. Tóm tắt phát hiện

`check_migration_drift` (gate bắt buộc của CI Migration QA) đỏ với đúng 2 diff, cả hai đều thuộc migration `0008` của bạn:

- `push_subscription` thiếu cột `updated_at` (model đang khai, DB không có).
- `reminder_dispatch` thiếu cột `updated_at` (tương tự).

Ngoài phần drift bắt được, còn **một lỗi thứ hai mà drift KHÔNG bắt được**: cả 2 bảng đều thiếu trigger `set_updated_at` — cơ chế thật duy trì `updated_at` của toàn bộ dự án (autogenerate không nhìn trigger).

## 2. Bằng chứng (đã chạy, output thật)

Chạy trên container `pgvector/pgvector:pg18` local (port 5433), chuỗi migration y hệt CI:

```
migration_prerequisites=ok
migration_drop_guard=ok
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema
… (0001 → 0008 đều thành công)
```

```
uv run python -m scripts.check_migration_drift
('add_column', 'microsched', 'push_subscription', Column('updated_at', DateTime(timezone=True), table=<push_subscription>, nullable=False, server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x…; now>, for_update=False)))
('add_column', 'microsched', 'reminder_dispatch', Column('updated_at', DateTime(timezone=True), table=<reminder_dispatch>, nullable=False, server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x…; now>, for_update=False)))
migration_drift=detected
```

```
uv run pytest -m pg -q
75 passed, 133 deselected (26.78s)   ← toàn bộ lane PG xanh, kể cả test của bạn đang có trên đĩa
```

Dấu vết thời gian trên đĩa (cùng ngày 2026-08-06): `0008_push_subscription_and_reminder_dispatch.py` — 15:29; `backend/app/domain/models.py` — 15:38. Migration viết **trước**, model sửa **sau** → hai bên lệch nhau.

## 3. Root cause

- `models.py:565` `class PushSubscription(UUIDTimestampModel, table=True)` và `models.py:590` `class ReminderDispatch(UUIDTimestampModel, table=True)` — cả hai kế thừa `UUIDTimestampModel` (`models.py:91–96`), lớp nền khai cứng `created_at` + `updated_at` với chú thích *"Fields required on every persisted entity by B1 and B2"*.
- `updated_timestamp()` (`models.py:72–79`): `nullable=False`, `server_default=func.now()` — nghĩa là mọi bảng phải có cột `updated_at` NOT NULL, default `now()`, và được trigger giữ sống.
- Migration `0008` tạo 2 bảng chỉ có `created_at`/`last_seen_at`, **không có `updated_at`** → drift. Cũng **không gắn trigger** → lệch pattern chuẩn.
- Pattern chuẩn cho bảng thêm sau 0001 chính là `0006` (`day_annotation`): docstring của 0006 ghi rõ *"It is the first table added since 0001, so it also receives the shared `set_updated_at` trigger that every other domain table already has"* — vừa tạo cột `updated_at`, vừa `CREATE TRIGGER set_updated_at … EXECUTE FUNCTION microsched.set_updated_at()`, và `downgrade()` phải `DROP TRIGGER`.

## 4. Vì sao phải sửa gấp (impact)

1. **Runtime vỡ im lặng:** ORM `SELECT`/`INSERT` qua 2 model này trên DB thật sẽ lỗi `column updated_at does not exist` ở code path đầu tiên chạm bảng (thêm device push, ghi dispatch, retry…).
2. **Chưa ai thấy vỡ vì chưa có test chạm PG:** `test_push_api.py`, `test_reminder_domain.py`, `test_cron_timer.py` **không có marker `pg`** (đã kiểm danh sách file pg-marked: không có 3 file này) → chưa từng chạy trên Postgres thật, chỉ chạy trong lane non-PG. Lỗi sẽ nổ ở production, không nổ ở CI hiện tại.
3. **Bẫy "sửa nửa chừng":** chỉ thêm cột cho hết drift mà quên trigger thì `check_migration_drift` xanh nhưng `updated_at` sẽ **không bao giờ đổi khi UPDATE row** — dữ liệu sai im lặng, đúng kiểu lỗi dự án này chủ trương chặn. Trigger là cơ chế thật, drift không cảnh báo được nó.

## 5. Hướng xử lý đề xuất

### 5a. Khuyến nghị: giữ `UUIDTimestampModel`, sửa `0008` tại chỗ — KHÔNG tạo 0009

Lý do: `0008` đang **untracked** (chưa commit) → chưa thể đã deploy → sửa thẳng file migration là đúng quy trình, không phình chuỗi migration.

**Gate an toàn bắt buộc TRƯỚC khi sửa** — xác nhận 0008 chưa từng áp vào DB thật (Neon):

```
SELECT version_num FROM microsched.alembic_version
```

(chạy qua `NEON_MIGRATOR_URL` bằng asyncpg, ví dụ `uv run python -c "…"` hoặc một script throwaway)

- Nếu `version_num` < 0008 (hoặc query lỗi vì bảng chưa có): sửa 0008 tại chỗ.
- Nếu `version_num` ≥ 0008 trên bất kỳ DB thật nào: **KHÔNG sửa 0008 nữa**, tạo `0009` chứa đúng nội dung dưới đây.

**Nội dung sửa (bám pattern 0006, `backend/alembic/versions/0006_*.py`):**

Trong `upgrade()`, mỗi `create_table` thêm cột (sau `created_at`):

```python
sa.Column(
    "updated_at",
    sa.DateTime(timezone=True),
    server_default=sa.text("now()"),
    nullable=False,
),
```

Và trước khi kết thúc `upgrade()`:

```python
op.execute(
    "CREATE TRIGGER set_updated_at "
    "BEFORE UPDATE ON microsched.push_subscription "
    "FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()"
)
op.execute(
    "CREATE TRIGGER set_updated_at "
    "BEFORE UPDATE ON microsched.reminder_dispatch "
    "FOR EACH ROW EXECUTE FUNCTION microsched.set_updated_at()"
)
```

Trong `downgrade()`, trước khi `drop_table`:

```python
op.execute("DROP TRIGGER set_updated_at ON microsched.push_subscription")
op.execute("DROP TRIGGER set_updated_at ON microsched.reminder_dispatch")
```

### 5b. Phương án thay thế — không khuyến nghị

Bỏ `updated_at` khỏi 2 model (đổi base class/override field). Không nên vì: (1) vi phạm comment "required on every persisted entity by B1 and B2"; (2) cả 2 bảng đều có update path thật — `push_subscription.last_seen_at` bị bump mỗi lần gửi push, `reminder_dispatch.status/attempt_count/confirmed_at` đổi qua từng retry. Chỉ làm nếu owner chốt hướng này.

## 6. Checklist acceptance (phải có biên lai)

1. Gate §5a xác nhận 0008 chưa áp DB thật (hoặc đã tạo 0009 nếu ngược lại).
2. Sửa xong chạy lại chuỗi CI Migration QA local, tất cả phải xanh:
   ```
   uv run python -m scripts.prepare_ci_database
   uv run python -m scripts.check_migration_drops
   uv run alembic upgrade head
   uv run python -m scripts.check_migration_drift          → migration_drift=empty
   uv run alembic downgrade base
   uv run alembic upgrade head
   uv run python -m scripts.check_migration_drift          → migration_drift=empty
   uv run pytest -m pg                                     → xanh (75 hiện tại)
   ```
3. Thêm **test pg-marked** chứng minh trigger + cột hoạt động (pattern tham khảo: `backend/tests/test_task_item_trigger.py`, `backend/tests/test_migration_0007.py`):
   - insert row → `updated_at` có giá trị (server_default);
   - UPDATE row → `updated_at` đổi sang mốc mới (trigger);
   - round-trip `downgrade base` → `upgrade head` không drift.
4. Cân nhắc thêm marker `pg` cho các test domain mới nếu chúng đụng DB thật — hiện tại 3 file test mới không pg-marked nên lỗi này đã trốn qua.
5. Báo cáo theo quy ước repo: **Đã chạy** (lệnh + output nguyên văn) / **CHƯA chạy** / **Vì sao vẫn tin là đúng**; guardrail mới phải chứng minh biết đỏ.

## 7. KHÔNG được làm

- **Không tạo 0009 khi 0008 chưa từng áp DB thật** — sửa 0008 tại chỗ là đủ.
- **Không chỉ thêm cột mà bỏ trigger** — đó là sửa cho drift xanh nhưng dữ liệu sai.
- Không sửa model theo hướng 5b khi chưa có owner duyệt.
- Không đụng 8 file của 011c (đã commit `c21741f`): `backend/app/domain/subscription.py`, `backend/app/domain/tracker.py`, `backend/tests/test_subscription_pure.py`, `backend/tests/test_subscription_api.py`, `frontend/src/SubscriptionScreen.tsx`, `frontend/src/lib/route.ts`, `frontend/src/subscription-ui.ts`, `frontend/e2e/subscription.spec.ts`.
- Không merge/push khi drift chưa `empty` và CI Migration QA chưa xanh.

## 8. Files được phép sửa

- `backend/alembic/versions/0008_push_subscription_and_reminder_dispatch.py` (chính — hoặc `0009_*.py` mới nếu gate §5a fail).
- `backend/tests/test_*` mới cho trigger (nếu cần).
- Không sửa `backend/app/domain/models.py` trừ khi owner chốt 5b.

## 9. Môi trường tái lập (đang sẵn sàng)

Container QA còn chạy: `microsched-011c-qa-0001` (`pgvector/pgvector:pg18`, host port **5433**):

```
$env:LOCAL_PG_DSN='postgresql://postgres:postgres@localhost:5433/microsched_ci'
```

Mọi lệnh backend chạy từ `backend/`. Container dùng xong có thể dọn: `docker rm -f microsched-011c-qa-0001`.
