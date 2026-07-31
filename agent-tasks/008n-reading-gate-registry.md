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

> **📝 Sửa 2026-07-26 sau HAI lượt phản biện — cờ boolean là KHÔNG ĐỦ, và chỗ thiếu đúng là chỗ chủ bắt phải chặn.** Bản đầu khai hai cờ `bool`, nghĩa là bảng nào không có cột thì cổng **bỏ qua im lặng**. Nhưng `task_item`, `note_item`, `entry`, `subscription` **không có cột `is_private` mà VẪN riêng tư** — chúng riêng tư **qua bảng cha**. Với cờ boolean, `readable(select(Entry), Entry, session)` sẽ **trả entry của tracker riêng tư cho session đang khoá**, và test khai-vs-schema **vẫn xanh** (`False == False`). Hiện tại ca đó **nổ** (`AttributeError`); bản đầu của spec này sẽ **biến một tiếng nổ thành một lỗ im lặng** — đúng thứ phải tránh. ⇒ Lời khai phải nói **ý định**, không nói **sự có mặt của cột**, và cần **ba trạng thái**.

Trong `backend/app/domain/models.py`, mỗi model `table=True` phải khai **hai cờ lớp**, mỗi cờ nhận **một trong ba giá trị** (dùng `enum.Enum` hoặc `Literal`, đừng dùng chuỗi trần):

```python
__privacy_gate__: ClassVar[Gate]   # APPLIES | NONE | VIA_PARENT
__delete_gate__:  ClassVar[Gate]   # APPLIES | NONE | VIA_PARENT
```

| Giá trị | Nghĩa | Bảng |
|---|---|---|
| `APPLIES` | Bảng **có** cột, cổng lọc trực tiếp | privacy: `task`, `note`, `tracker`, `message` · delete: `task`, `note`, `tracker`, `subscription`, `entry` |
| `VIA_PARENT` | **Có** tính riêng tư/xoá-mềm nhưng nó nằm ở **bảng cha** | `task_item`, `note_item` (cha là `task`/`note`) · `entry`, `subscription` cho trục **privacy** (cha là `tracker`) · `message` cho trục **delete** nếu 012 cần |
| `NONE` | Bảng **thật sự không có** khái niệm đó | `calendar_source`, `calendar_event`, `tracker_group`, `app_setting`, `audit_log`, `session` |

- Khai trên **từng class**, **không** đặt default ở `UUIDTimestampModel`. Default ở cha nghĩa là bảng mới **im lặng thừa hưởng** giá trị sai.
- 🔒 **`VIA_PARENT` không phải nhãn trang trí — nó là hợp đồng:** truy vấn bảng đó **phải** `JOIN` bảng cha rồi áp cổng **trên model cha** (`with_privacy_gate(stmt, Tracker, session)`), hoặc đi qua đường `_parent()` như `TaskStore` đang làm.
- Giá trị lấy từ bảng trên; **kiểm lại bằng cách đọc `0001_initial_schema.py`**, đừng tin bảng trong spec này.

### 2.2 Hai hàm cổng đọc

`backend/app/domain/reading.py`:

- `with_privacy_gate(stmt, model, session)`:
  - model **chưa khai** `__privacy_gate__` ⇒ **`raise`** (xem §2.3).
  - `APPLIES` mà model **không có** thuộc tính `is_private` ⇒ **`raise`** (lời khai và schema đá nhau).
  - `APPLIES` và cổng đang khoá ⇒ lọc như hiện nay.
  - `NONE` ⇒ trả `stmt` **nguyên vẹn**, không lọc, không log ồn. *(Đây là nhánh "bỏ qua im lặng" chủ đã chọn — và nó chỉ an toàn vì `VIA_PARENT` đã tách ra khỏi nhánh này.)*
  - 🔒 `VIA_PARENT` ⇒ **`raise`**, thông điệp chỉ đúng việc: *"Entry riêng tư theo Tracker cha; JOIN Tracker rồi gọi with_privacy_gate(stmt, Tracker, session)"*. Gọi cổng trực tiếp trên model `VIA_PARENT` **luôn** là lỗi lập trình, không bao giờ là ý định.
- `not_deleted(stmt, model)`: y hệt trên, với `__delete_gate__` và cột `deleted_at`.
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
| `APPLIES` ⇔ cột **có** trong `__table__.columns` | Lời khai lệch schema (migration thêm/bớt cột mà quên sửa khai) ⇒ đỏ |
| `NONE` và `VIA_PARENT` ⇒ cột **không** có | Bảng đã có cột mà vẫn khai là không có ⇒ đỏ |
| 🔒 `VIA_PARENT` ⇒ model **phải có** một FK trỏ tới bảng cha, và bảng cha đó khai `APPLIES` trên **cùng trục** | Khai `VIA_PARENT` mà không có cha để gác, hoặc cha cũng không gác ⇒ đỏ. Đây là chốt chặn cho lớp lỗi ở note §2.1 |

- Lấy cột từ **`model.__table__.columns`** (metadata thật của SQLAlchemy), không dùng `hasattr`.
- **Thêm test ở lane `pg`**, hai khẳng định:
  1. Lời khai so với **schema thật** (`information_schema.columns`, schema `microsched`) — metadata Python và DB thật lệch nhau là đúng lớp lỗi mà `Migration QA` tồn tại để bắt.
  2. 🔒 **Mọi bảng trong schema `microsched`** (`information_schema.tables`) **đều có một model khai cờ**. Bảng tồn tại trong DB mà không có model ⇒ đỏ. Không có chốt này thì một bảng thêm bằng SQL thô sẽ vô hình với cả bộ test.
- 🔒 **Luật cho 009–012, ghi vào PR để người làm 009 đọc thấy:** mỗi slice phải kèm **một test hành vi** — session đang khoá gọi endpoint list/get thì **không thấy** dòng riêng tư, và với thực thể con thì test đi qua **cha riêng tư** (ví dụ: `entry` của một `tracker` riêng tư phải biến mất khi cổng khoá). Test khai-vs-schema chỉ chứng minh **lời khai đúng**; nó không chứng minh **có ai gọi cổng**. Hai thứ đó khác nhau, và chỗ thứ hai chỉ test hành vi mới bắt được.
- 🔒 **Chứng minh BIẾT ĐỎ:** tạm đổi một cờ khai cho sai (ví dụ `Tracker.__privacy_gated__ = False`) ⇒ test phải đỏ; và tạm bỏ hẳn một cờ ⇒ test phải đỏ. Ghi cả hai vào PR.

### 2.5 Nợ 1 — `restore()` đừng giải mã thứ nó không dùng

`TaskStore.restore` (`backend/app/domain/tasks.py`) kết thúc bằng `return self._task_read(task, await self._items(db, task_id))` — giải mã `title`, `body_md` và **toàn bộ** item, cộng một query phụ. Router thì chỉ dùng `task.id`:

```python
return {"id": str(task.id), "status": "restored"}
```

⇒ Đổi chữ ký **nội bộ** của `TaskStore.restore()` thành **`Task | None`** — *(chốt một đường duy nhất; bản đầu ghi "`Task | None` hoặc `UUID | None`" và phản biện chỉ ra hai đường đó không thay thế nhau: trả `UUID` thì router mất `task.id` ⇒ phải sửa router, mà §3 cấm)*. Bỏ `_items()` và `_task_read()` khỏi đường này. Router **giữ nguyên** `{"id": str(task.id), "status": "restored"}`. **Response của endpoint không đổi một byte** (`{"id": …, "status": "restored"}`) và test hiện có phải xanh không sửa. Đây không phải rò rỉ trên dây — nó là plaintext dựng vô cớ trong RAM + một query thừa, và là **khuôn cho undo của 009–012**.

### 2.6 Nợ 2 — test lane `pg` đừng đọc biến môi trường thô

Trong `backend/tests/test_tasks_api.py`, bốn chỗ tạo engine bằng `os.environ["NEON_MIGRATOR_URL"]` (khoảng dòng 81, 145, 248, 330) trong khi chính test đó đã nhận fixture `pg_dsn` — mà **fixture mới là chỗ có chốt chặn từ chối host non-local** (`conftest.py`, `EPHEMERAL_HOSTS`).

Hiện tại **chưa hỏng**: fixture chạy trước thân test nên vẫn chặn. Nhưng một test tương lai **không** nhận `pg_dsn` mà đọc biến thô sẽ **đi vòng qua chốt chặn** và xoá row trên Neon production.

⇒ Lấy URL engine **từ giá trị fixture đã qua cửa**, không đọc `os.environ` trực tiếp trong thân test. Nếu cần dạng URL khác dạng DSN thì thêm một fixture dẫn xuất trong `conftest.py` (cũng qua chốt chặn), đừng lách.

### 2.7 Nợ 3 — cron ghi thêm `uptime` và cờ `restart_advised`

`architecture-brief.md:115` yêu cầu job cron ghi **"RSS + uptime"**; `014` chỉ làm RSS. Thiếu uptime thì con số **không đọc được** — 200MB sau 10 giờ và sau 10 ngày là hai kết luận trái ngược.

Trong `backend/app/core/process_stats.py` + `backend/app/web/routers/cron.py`:

- **`uptime_s`** — tuổi của **TIẾN TRÌNH**, không phải của app instance. Ghi `datetime.now(UTC)` vào **một hằng cấp module trong `process_stats.py`, tính lúc import**, rồi lấy hiệu. 🔒 **Không** neo vào `create_app()`: test dựng nhiều instance (`_make_client`) nên mỗi instance sẽ ra một tuổi khác nhau, và `main.py` hiện **không có** lifespan hook. 🔒 **Không dùng `time.monotonic()`**: máy chạy `suspend`, thời gian nằm ngủ **phải được tính** — nó là phần lớn tuổi thọ tiến trình.
- **`mem_total_kb`** — 🔒 lấy **giá trị NHỎ HƠN** giữa hai nguồn, cái nào đọc được thì dùng: (a) hạn mức cgroup (`/sys/fs/cgroup/memory.max`, fallback `/sys/fs/cgroup/memory/memory.limit_in_bytes`) và (b) `MemTotal` trong `/proc/meminfo`. Cả hai None-safe như `read_rss_kb`.
  *Vì sao lấy min thay vì chọn một nguồn:* phản biện cảnh báo `/proc/meminfo` có thể báo RAM của **host** chứ không phải hạn mức của máy ảo. Trên microVM của Fly thì `MemTotal` **thường** đúng bằng cỡ máy, nhưng trong container thì không — **và ta không cần phân xử chuyện đó**: lấy min thì đúng ở cả hai kiến trúc. Cái không đọc được thì bỏ qua; cả hai không đọc được ⇒ `None`.
  🔒 **Không** hardcode 256MB và **không** thêm setting cấu hình: `fly.toml` đổi cỡ máy thì hằng số trong app thành sai mà không có gì báo.
- **`rss_pct`** — `rss_kb / mem_total_kb * 100`, làm tròn 1 chữ số; `None` nếu thiếu một trong hai.
- **`restart_advised`** — `True` khi `rss_pct >= 90`, ngược lại `False`; `None` nếu không đo được.
- **Body heartbeat có ĐÚNG SÁU key**, không hơn không kém: `status`, `rss_kb` (hai key đang có, **giữ nguyên**), `uptime_s`, `mem_total_kb`, `rss_pct`, `restart_advised`. *(Bản đầu chỉ nói "trả cả bốn field", đọc được thành "thay thế" hoặc "thêm vào" — phản biện bắt đúng chỗ này.)* Thêm một test khẳng định **tập key chính xác**, để lần sau không ai thêm field mà không ai biết.
- Ghi vào **một** dòng log grep được, giữ nguyên chuỗi `Cron heartbeat received`.

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

## 4. Acceptance

**Bạn PHẢI chạy, và cả hai lệnh chứ không phải một** *(CI chạy hai lệnh ruff; bỏ lệnh thứ hai đã từng làm CI đỏ sau 10 giây — 26/07)*:

1. `cd backend && uv run ruff check .` **và** `uv run ruff format --check .` — cả hai sạch.
2. `cd backend && uv run pytest -m "not pg"` xanh toàn bộ.
3. Chứng minh **BIẾT ĐỎ** ở §2.4: (a) đổi một cờ khai cho sai ⇒ test đỏ; (b) bỏ hẳn một cờ ⇒ test đỏ. Dán output cả hai lần.

**Không cần bạn chạy** (T1 chạy lại hoặc CI lo), nhưng **phải khai rõ là chưa chạy** — báo thiếu là đúng, báo đạt cái chưa đo là hỏng cả lane:

4. Lane `pg` (cần Postgres thật) · `pre-commit run --all-files` · ba lệnh frontend · `uv sync --no-dev` + `create_app()`. Task này không chạm `frontend/` nên ba lệnh frontend chỉ cần xanh ở CI.
5. **Git/PR là việc của T1** — bạn **không** cắt nhánh, **không** commit, **không** push, **không** mở PR. Để nguyên working tree + báo cáo; T1 kiểm rồi tự làm phần git.

## 5. Báo cáo

Báo cáo phải có: `git diff --stat` (chỉ file thuộc §2), **bảng lời khai cuối cùng của toàn bộ 14 bảng** (ba trạng thái × hai trục), hai output đỏ ở mục 3, và một mục **"chưa tự verify được"** liệt kê đúng những gì ở mục 4. Mọi quyết định ngoài spec ghi rõ kèm lý do.
