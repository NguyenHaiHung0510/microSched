# 008n — cổng đọc khai báo tường minh (và ba món nợ của `008f`)

> **Executor: T2 Codex** (`gpt-5.6-sol`, `--write`). Nhánh `feat/008n-reading-gate` → PR nhỏ vào `develop`.
> Spec tự-chứa. Đọc `CLAUDE.md` + `AGENTS.md` trước.
> ⚠️ **PHẢI merge trước 009.** 009/010/011/012 chép hình dạng của cổng đọc này.
> **KHÔNG có migration.** **KHÔNG đụng frontend.**

## 0. Bối cảnh — vì sao có task này

`008f` (PR #23, đã merge) tách `readable()` thành `with_privacy_gate()` + `not_deleted()` để 010 (calendar) khỏi vấp. **Nó chỉ chữa được một nửa.** Bảng cột thật, đo trên `0001_initial_schema.py` ngày 26/07:

| Bảng | `is_private` | `deleted_at` |
|---|---|---|
| `task`, `note`, `tracker` | có | có |
| `message` | có | **không** |
| `subscription`, `entry` | **không** | có |
| `calendar_source`, `calendar_event`, `tracker_group` | **không** | **không** |

`with_privacy_gate()` chạm `model.is_private` **vô điều kiện** ⇒ với calendar (không có cột nào trong hai cột) **cả hai hàm vẫn nổ**, tức mục đích của `008f` chưa đạt. Người viết 010 gọi hàm nào cũng ăn `AttributeError` trên 100% request GET.

**Chủ quyết 2026-07-26** (sau khi so hai đường): **hàm bỏ qua cổng khi bảng thật sự không có khái niệm đó** — nhưng kèm điều kiện cứng: **"không để lỡ thiếu cột xảy ra"**, và chỉ khi bất khả kháng thì mới chịu "nổ" có kiểm soát.

Cách thoả cả hai: **chuyển tiếng ồn từ runtime sang CI.** Model **khai** cổng nào áp cho nó; một test so **lời khai với schema thật**. Sai lệch ⇒ CI đỏ, không merge được. Runtime chỉ còn hai ca: khai-không-có ⇒ bỏ qua im lặng; **chưa khai / khai sai** ⇒ nổ có thông điệp.

## 1. Đã KHOÁ — chép ra code, không mở lại

1. **Khai tường minh, KHÔNG suy đoán bằng `hasattr`.** `hasattr` không phân biệt được "bảng này vốn không có khái niệm riêng tư" với "ai đó quên thêm cột" — mà đó đúng là ca chủ bắt phải chặn.
2. **Hành vi quan sát được của `readable()` với `task` KHÔNG ĐỔI.** Đây là bất biến của task này; test hiện có phải xanh mà không sửa assertion nào.
3. **Không migration, không thêm/bớt cột nào.** Lời khai phải khớp schema đang có, không phải ngược lại.
4. **Không đụng `frontend/`.**
5. Cổng riêng tư và cổng xoá-mềm là **hai trục độc lập**; một bảng có thể có trục này mà không có trục kia (xem bảng ở §0).

## 2. Phải làm

### 2.1 Lời khai trên model

Trong `backend/app/domain/models.py`, mỗi model `table=True` **mang cấu trúc cha** (`task`, `note`, `tracker`, `subscription`, `entry`, `calendar_source`, `calendar_event`, `tracker_group`, `message`, `app_setting`, `audit_log`, `session`, và các bảng con `task_item`/`note_item`) phải khai **hai cờ lớp**:

```python
__privacy_gated__: ClassVar[bool]   # True ⇔ bảng có cột is_private
__soft_deleted__: ClassVar[bool]    # True ⇔ bảng có cột deleted_at
```

- Khai trên **từng class**, không đặt default ở lớp cha `UUIDTimestampModel`. Default ở cha nghĩa là một bảng mới **im lặng thừa hưởng** giá trị sai — đúng thứ §0 cấm.
- Giá trị lấy từ bảng ở §0; **kiểm lại bằng cách đọc `0001_initial_schema.py`**, đừng tin bảng trong spec này.

### 2.2 Hai hàm cổng đọc

`backend/app/domain/reading.py`:

- `with_privacy_gate(stmt, model, session)`:
  - model **chưa khai** `__privacy_gated__` ⇒ **`raise`** (xem §2.3).
  - khai `False` ⇒ trả `stmt` **nguyên vẹn**, không lọc, không log ồn.
  - khai `True` mà model **không có** thuộc tính `is_private` ⇒ **`raise`** (lời khai và schema đá nhau).
  - khai `True` và cổng đang khoá ⇒ lọc như hiện nay.
- `not_deleted(stmt, model)`: y hệt trên, với `__soft_deleted__` và cột `deleted_at`.
- `readable(stmt, model, session)`: giữ nguyên chữ ký và **giữ nguyên hành vi** — chỉ là hợp của hai hàm trên.

### 2.3 Câu báo lỗi phải chỉ đúng việc phải làm

Dùng một exception rõ nghĩa (ví dụ `ReadingGateError(RuntimeError)`), thông điệp phải nêu **tên bảng + cờ còn thiếu + việc cần làm**. Mẫu:

```
Tracker chưa khai __privacy_gated__. Khai True nếu bảng có cột is_private,
False nếu bảng không có khái niệm riêng tư; xem agent-tasks/008n.
```

🔒 **Không** bắt exception này ở tầng router để biến thành `500` đẹp đẽ hay `200` rỗng. Nó phải nổ to ở dev; đây là ca "bất khả kháng" mà chủ chấp nhận đánh đổi.

### 2.4 🔴 Test khai-vs-schema — đây là phần chính của task

Một test **liệt kê mọi model `table=True`** (đi qua `SQLModel.metadata.tables` hoặc `__subclasses__`, đừng chép tay danh sách — chép tay là bảng mới bị bỏ sót) và khẳng định, cho từng bảng:

| Khẳng định | Nếu sai nghĩa là |
|---|---|
| Model có khai **cả hai** cờ | Bảng mới thêm mà chưa khai ⇒ đỏ |
| `__privacy_gated__ == ('is_private' in columns)` | Lời khai lệch schema (thêm/bớt cột mà quên sửa khai) ⇒ đỏ |
| `__soft_deleted__ == ('deleted_at' in columns)` | Như trên |

- Lấy cột từ **`model.__table__.columns`** (metadata thật của SQLAlchemy), không dùng `hasattr`.
- **Thêm một test ở lane `pg`** so lời khai với **schema thật trên Postgres** (`information_schema.columns`, schema `microsched`). Lý do: metadata trong Python và DB thật có thể lệch nhau — chính đó là lớp lỗi mà `Migration QA` tồn tại để bắt.
- 🔒 **Chứng minh BIẾT ĐỎ:** tạm đổi một cờ khai cho sai (ví dụ `Tracker.__privacy_gated__ = False`) ⇒ test phải đỏ; và tạm bỏ hẳn một cờ ⇒ test phải đỏ. Ghi cả hai vào PR.

### 2.5 Nợ 1 — `restore()` đừng giải mã thứ nó không dùng

`TaskStore.restore` (`backend/app/domain/tasks.py`) kết thúc bằng `return self._task_read(task, await self._items(db, task_id))` — giải mã `title`, `body_md` và **toàn bộ** item, cộng một query phụ. Router thì chỉ dùng `task.id`:

```python
return {"id": str(task.id), "status": "restored"}
```

⇒ Đổi `restore()` trả về thứ vừa đủ (`Task | None` hoặc `UUID | None`), bỏ `_items()` và `_task_read()` khỏi đường này. **Response của endpoint không đổi một byte** (`{"id": …, "status": "restored"}`) và test hiện có phải xanh không sửa. Đây không phải rò rỉ trên dây — nó là plaintext dựng vô cớ trong RAM + một query thừa, và là **khuôn cho undo của 009–012**.

### 2.6 Nợ 2 — test lane `pg` đừng đọc biến môi trường thô

Trong `backend/tests/test_tasks_api.py`, bốn chỗ tạo engine bằng `os.environ["NEON_MIGRATOR_URL"]` (khoảng dòng 81, 145, 248, 330) trong khi chính test đó đã nhận fixture `pg_dsn` — mà **fixture mới là chỗ có chốt chặn từ chối host non-local** (`conftest.py`, `EPHEMERAL_HOSTS`).

Hiện tại **chưa hỏng**: fixture chạy trước thân test nên vẫn chặn. Nhưng một test tương lai **không** nhận `pg_dsn` mà đọc biến thô sẽ **đi vòng qua chốt chặn** và xoá row trên Neon production.

⇒ Lấy URL engine **từ giá trị fixture đã qua cửa**, không đọc `os.environ` trực tiếp trong thân test. Nếu cần dạng URL khác dạng DSN thì thêm một fixture dẫn xuất trong `conftest.py` (cũng qua chốt chặn), đừng lách.

### 2.7 Nợ 3 — cron ghi thêm `uptime` và cờ `restart_advised`

`architecture-brief.md:115` yêu cầu job cron ghi **"RSS + uptime"**; `014` chỉ làm RSS. Thiếu uptime thì con số **không đọc được** — 200MB sau 10 giờ và sau 10 ngày là hai kết luận trái ngược.

Trong `backend/app/core/process_stats.py` + `backend/app/web/routers/cron.py`:

- **`uptime_s`** — tuổi của **tiến trình**, tính bằng **giờ tường** (`datetime.now(UTC)` ghi lúc import/startup rồi lấy hiệu). 🔒 **Không dùng `time.monotonic()`**: máy Fly chạy `suspend`, và thời gian nằm ngủ **phải được tính** — nó là phần lớn tuổi thọ tiến trình.
- **`mem_total_kb`** — đọc `MemTotal` từ `/proc/meminfo`, cùng kiểu None-safe như `read_rss_kb`.
  🔒 **Không** hardcode 256MB và **không** thêm setting cấu hình cho nó: `fly.toml` đổi cỡ máy thì hằng số trong app thành sai mà không có gì báo. Đo thì không bao giờ lệch.
- **`rss_pct`** — `rss_kb / mem_total_kb * 100`, làm tròn 1 chữ số; `None` nếu thiếu một trong hai.
- **`restart_advised`** — `True` khi `rss_pct >= 90`, ngược lại `False`; `None` nếu không đo được.
- Trả cả bốn field trong body heartbeat, và ghi vào **một** dòng log grep được (giữ nguyên chuỗi `Cron heartbeat received`).

🔒 **CHỈ khuyến nghị, KHÔNG hành động** (chủ quyết 26/07): **không** restart, **không** gọi API Fly, **không** `sys.exit`, **không** gửi cảnh báo, **không** thêm ngưỡng nào khác. Cờ này để người đọc định kỳ nhìn.

Test: `rss_pct` đúng với cặp số đút vào; `restart_advised` đúng ở **89,9 / 90,0 / 90,1**; thiếu `mem_total` ⇒ cả `rss_pct` lẫn `restart_advised` là `None` mà endpoint **vẫn `200`**. Mọi test phải **độc lập hệ điều hành** — patch hàm đọc hoặc truyền tham số `path`, đừng để kết quả phụ thuộc `/proc` có thật (đây là đúng lỗi đã làm CI đỏ ở PR #24).

## 3. KHÔNG được làm

- **Không** migration, **không** thêm/bớt cột, **không** đụng `alembic/`.
- **Không** đụng `frontend/`, `api.ts`, `TasksScreen.tsx` — `008m` và `008g` sống trong đó ngay sau bạn.
- **Không** dùng `hasattr` để quyết có lọc hay không (xem §1.1).
- **Không** đặt default cho hai cờ ở `UUIDTimestampModel`.
- **Không** đổi chữ ký hay hành vi của `readable()`.
- **Không** đổi response của `/api/tasks/{id}/restore`.
- **Không** bắt/nuốt `ReadingGateError` ở tầng web.
- **Không** thêm dependency. **Không** đổi tên required check trong CI.
- **Không** tự chạy `alembic` hay lệnh Fly nào.

## 4. Acceptance — chạy đúng danh sách của `ci.yml`, không phải danh sách mình nhớ

1. `cd backend && uv run ruff check .` **và** `uv run ruff format --check .` — cả hai sạch.
2. `uv run pytest -m "not pg"` xanh.
3. Lane `pg`: nếu sandbox không chạy được Postgres thì **khai rõ là chưa chạy**, đừng báo đạt (T1 sẽ chạy lại).
4. Ghi trong PR: hai lần đỏ đã chứng minh ở §2.4, và bảng lời khai cuối cùng của 14 bảng.
5. `git diff --stat` chỉ hiện file thuộc §2.

## 5. Báo cáo

PR nhỏ vào `develop`, tiêu đề `008n: cổng đọc khai báo tường minh + ba món nợ của 008f`. Khai rõ mọi thứ **không** tự verify được. Mọi quyết định ngoài spec ghi vào PR description.
