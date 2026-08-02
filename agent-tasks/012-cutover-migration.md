# 012 — Cutover: đưa dữ liệu thật từ Postgres cũ sang Neon, rồi ngừng dùng app cũ

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L1
> · Skill gợi ý: không cần · MCP cần: không cần.**
> **Trạng thái: DRAFT — viết bởi T1 (Opus 5) 2026-08-01, mọi quyết định ở §3 đã chốt trực tiếp với
> chủ. Đã qua một vòng phản biện T2 (Codex) + T3 (Gemini) 2026-08-02, T1 đã vá trực tiếp mọi finding
> xác nhận đúng (xem §10). Chưa được chủ duyệt bản chi tiết.**
>
> ⚠️ **Codex viết script + test. Codex KHÔNG chạy cutover thật.** Buổi chạy thật là nghi thức tay do
> chủ + T1 làm theo §6. Lý do: đây là thao tác một lần lên dữ liệu thật của chủ, và bước ①/③/⑦ của
> §6 nằm ngoài repo (đóng băng DB cũ, ảnh chụp, đổi thói quen dùng).

## 0. Phạm vi

**Làm:** một script chạy-một-lần đọc Postgres local `microschedule_v2` (read-only) và ghi vào Neon
production; cộng với nghi thức chạy + verify quanh nó.

**KHÔNG làm** (dễ tưởng thuộc 012, thật ra không):
- **Không** import lịch học / lịch thi. `010a` đã làm đường `.ics` và chủ nhập lại từ **file gốc**,
  sạch hơn copy 479 dòng đã qua một tầng parser cũ. Việc này giải luôn `migration-mapping-brief.md`
  §3 (121 dòng lịch lệch giữa hai store cũ) — xem §3 mục 3 dưới đây.
- **Không** thêm/sửa schema. Mọi cột cần cho cutover đã có sau `020`; nếu phát hiện thiếu cột nữa thì
  **dừng, báo chủ**, đừng tự thêm migration trong task này.
- **Không** xoá gì ở nguồn cũ. Không bao giờ.

## 1. Điều kiện cổng — kiểm đủ 5 dòng trước khi bắt đầu

| # | Cổng | Cách kiểm |
|---|---|---|
| 1 | `010a` + `010b` đã live, chủ import được lịch thật | mở `microsched.fly.dev`, thấy lịch |
| 2 | `011` đã live | dùng thử một lần capture. **Không phải phụ thuộc dữ liệu** — `tracker`/`entry`/`subscription` tạo rỗng, không có gì để migrate. Nó chỉ là một phần của cổng 4. |
| 3 | **`020` đã merge và migration `0006` đã áp lên Neon** | query `information_schema.columns` thấy `task.completed_at`, `note.pinned`, `note.priority` |
| 4 | App mới **dùng được hằng ngày thay app cũ** | chủ tự đánh giá — đây là cổng chủ quan, và nó là cổng thật: đổ dữ liệu vào một app chưa xem/sửa được là tự mất daily driver |
| 5 | **Đã soi lại giá** | `docs/cost-brief.md` ghi rõ *"bắt buộc trước khi cutover"*; ghi ngày soi + số đo vào brief đó |

Thiếu bất kỳ dòng nào ⇒ chưa chạy §6.

## 2. Nguồn cũ — sự thật đo được, không phải trí nhớ

DDL thật: `docs/_local/v2-schema.sql` (gitignore, dump 2026-08-01 bằng `pg_dump --schema-only`).
Số dòng dưới đây đo **18/07/2026** và **chắc chắn đã cũ** — chủ vẫn dùng app cũ hằng ngày cho tới
tận buổi cutover. **Đo lại lúc chạy, đừng hardcode con số nào vào script hay test.**

Bằng chứng cho câu trên, không phải lời cảnh báo suông: `tasks` đo lại **2026-08-01** ra **191 dòng**
(`open 3` · `completed 188` · `archived 0`) — tức **+28 dòng trong 14 ngày**. Mọi con số trong bảng
này là ảnh chụp, không phải hợp đồng.

| Bảng nguồn (`public`) | ~số dòng 18/07 | Xử lý |
|---|---|---|
| `tasks` | 163 → **191** (01/08) | ➜ `task` |
| `task_items` | 97 | ➜ `task_item` |
| `notes` | 49 | ➜ `note` |
| `note_items` | 81 | ➜ `note_item` |
| `priorities` | 6 | ➜ tan vào `task.priority` / `note.priority`, không thành bảng |
| `calendar_sources` + `calendar_events` | 4 / 479 | ➜ **chỉ phần thủ công** (§3 mục 3) |
| `calendar_source_versions` | — | ⛔ bỏ (lịch sử phiên bản, Fork A đã loại) |
| `app_settings` | 8 | ⛔ bỏ (cấu hình của app cũ, app mới có cấu hình riêng) |
| `agent_action_log` | 0 | ⛔ bỏ (rỗng) |
| `backup_runs` | — | ⛔ bỏ (log vận hành app cũ) |
| schema `test_cal_view_20a05525…`, `test_cal_view_be1043b8…` | — | ⛔ **không đụng** — rác test của app cũ nằm ngoài `public` |

**Ba đặc điểm của nguồn cũ làm bài toán dễ hơn tưởng — đã kiểm trên DDL thật:**

1. **ID đã là UUID** (`gen_random_uuid()`), không phải số tăng dần ⇒ **giữ nguyên ID cũ**. Không cần
   bảng ánh xạ, con nối cha bằng chính khoá cũ, và script **chạy lại được** nhờ `ON CONFLICT (id) DO NOTHING`.
2. **Mọi cột thời gian đều `timestamp with time zone`** ⇒ **không phải đoán múi giờ**. Ghi chú "ép
   timezone thật khi copy" ở `migration-mapping-brief.md` §2 viết khi chưa có DDL trong tay; nó thừa.
   Thêm dated note vào brief đó lúc làm task này, đừng sửa đè.
3. **Toàn bộ dữ liệu cũ là công khai** — private mode là tính năng *mới*. Mọi hàng vào với
   `is_private = false`, và CHECK ciphertext của `task`/`note` là **có điều kiện** (`NOT is_private OR …`)
   nên plaintext hợp lệ. Trigger `0003` (privacy của `task_item`) chỉ nổ khi cha private ⇒ đi qua sạch.
   Trigger `set_updated_at` là **`BEFORE UPDATE`**, không phải INSERT ⇒ ghi thẳng `created_at`/`updated_at`
   cũ **không bị đè**, không cần tắt trigger, không cần quyền owner.

## 3. Quyết định đã chốt với chủ 2026-08-01 — không hỏi lại

1. **Mang hết, không lọc.** 163 task phần lớn đã xong, vẫn mang. Lý do: ~400 dòng không đủ nhiều để
   phải lọc, và lọc sai thì không có đường về; dọn bằng tay trong app mới sau, khi nhìn thấy tận mắt.
2. **6 mức `priorities` gộp còn 3** — 2 cao nhất ➜ `p1`, 2 giữa ➜ `p2`, 2 thấp ➜ `p3`. Schema mới cứng
   ở `CHECK (priority IN ('p1','p2','p3'))`, không có cách khác.

   **Đã giải sẵn 2026-08-01 trên dữ liệu thật** — `sort_order` tăng dần = mức khẩn tăng dần
   (`0 Optional` … `5 Quan trọng hơn TN`). Viết thành hằng, **không tính lại lúc chạy**:

   ```python
   # nguồn public.priorities.name (có UNIQUE ⇒ khoá ổn định) → task.priority / note.priority
   PRIORITY_MAP: Final[dict[str, str]] = {
       "Quan trọng hơn TN": "p1",   # sort_order 5 · Red/Warning
       "Nguy hiểm":         "p1",   # sort_order 4 · Red/Warning
       "Bỏ là nhót":        "p2",   # sort_order 3 · Orange/Danger
       "Phải làm":          "p2",   # sort_order 2 · Amber/High
       "Nên làm":           "p3",   # sort_order 1 · Green/Check
       "Optional":          "p3",   # sort_order 0 · Grey/Low
   }
   ```

   ⚠️ **Gặp `name` không có trong dict ⇒ dừng cả script với lỗi rõ ràng.** Tuyệt đối không im lặng gán
   `NULL`. Chủ vẫn dùng app cũ hằng ngày; thêm một mức ưu tiên thứ 7 trước buổi cutover là chuyện có
   thể xảy ra, và cách hỏng tệ nhất là mọi task ở mức mới lặng lẽ mất ưu tiên.

   *(Bản nháp trước có cờ `--priority-order=asc|desc` để chủ tự chỉnh chiều lúc chạy, mặc định `asc`
   = "số nhỏ là cao". Dữ liệu thật cho thấy chiều đó **ngược**, tức mặc định sẽ đảo `p1`↔`p3` trên
   toàn bộ dữ liệu. Đã biết 6 tên thật rồi thì bảng cứng đúng hơn một cái cờ — cờ chỉ là thêm một
   cách nữa để chọn sai.)*
3. **Lịch: chỉ mang buổi thủ công.** Lịch học/thi nhập lại từ `.ics` gốc qua `010a`. Nhưng buổi chủ tự
   thêm tay **không nằm trong file `.ics` nào** ⇒ mất là mất hẳn.

   > 📝 **2026-08-02 — SỬA sau phản biện T2 (Codex), bản trước SAI hoàn toàn cách nhận diện.** Bản
   > nháp đầu ghi `calendar_sources.kind = 'manual_task_calendar'` và `calendar_events.event_type =
   > 'manual'` — **hai giá trị này không hề tồn tại trên đường ghi thật**. Đọc thẳng code app cũ
   > (`old main.py:1774-1792`, `app/migration/migrate_sqlite_to_postgres.py:261,329`): mọi buổi —
   > cả buổi import gốc từ SQLite lẫn buổi chủ thêm tay sau này — đều nằm chung một
   > `calendar_sources.display_name = 'v1_sqlite_schedule'` (`kind = 'legacy_v1'`), và cột
   > `event_type` được app cũ hardcode `'legacy'` cho **mọi** buổi (kể cả buổi thêm tay). Với predicate
   > cũ, script sẽ đếm ra **0 dòng ở mọi lần chạy thật** — và vì §3 mục 5 nói "đếm ra 0 ⇒ bỏ qua nhánh,
   > coi là bình thường", đây là kiểu lỗi tệ nhất: **mất đúng thứ mục này viết ra để cứu, mà không có
   > cảnh báo nào**.
   >
   > Nhận diện đúng nằm ở cột `external_uid`, không phải `kind`/`event_type`:
   > - Buổi import gốc từ SQLite: `external_uid` dạng `v1-schedule-{id cũ}` (gán lúc migrate, xem
   >   `migrate_sqlite_to_postgres.py:329`) — đây là **tập cha** của mọi buổi `.ics` sẽ tái nhập qua
   >   `010a`, **không mang**.
   > - Buổi chủ tự thêm tay sau đó qua UI app cũ: `external_uid` dạng `manual_{uuid4}` (gán lúc ghi,
   >   `main.py:1784`) — **đây mới là tập cần mang**, vì `.ics` gốc không có chúng.
   >
   > **Predicate đúng:**
   > ```sql
   > SELECT ce.* FROM calendar_events ce
   > JOIN calendar_sources cs ON ce.source_id = cs.id
   > WHERE cs.display_name = 'v1_sqlite_schedule'
   >   AND ce.external_uid LIKE 'manual\_%' ESCAPE '\'
   > ```
   > Dry-run **phải in cả hai bucket riêng** (`manual_* → N mang`, `v1-schedule-* → M bỏ, tái nhập qua
   > 010a`), không chỉ một con số gộp — để chủ nhìn thấy N không lặng lẽ bằng 0 nếu đáng ra phải khác 0.
   > Nếu `N = 0` ⇒ bỏ qua nhánh lịch như cũ (không tạo nguồn rỗng), nhưng dòng in ra vẫn phải hiện diện
   > để phân biệt "đếm ra 0 thật" với "predicate sai, im lặng bỏ sót".
4. **Đường ghi = script dùng chính SQLModel table model của app** (không phải SQL trần, không phải
   HTTP API). Lý do: `tracking-brief.md` §116 nói thẳng có những bất biến **app canh, DB không canh**
   — quên một chỗ thì không có gì báo động; đi qua model của app là cách rẻ nhất để thừa hưởng chúng mà
   không phải dựng session đăng nhập.

   > 📝 **2026-08-02 — LÀM RÕ sau phản biện T2, câu gốc mơ hồ tới mức tự mâu thuẫn với §2 mục 1.**
   > "SQLModel của app" ở đây nghĩa là **table model** (`Task`, `Note`, `TaskItem`, `NoteItem`,
   > `CalendarSource`, `CalendarEvent` — class kế thừa `SQLModel, table=True` trong `models.py`), dùng
   > qua `insert(Task).values(id=..., **fields).on_conflict_do_nothing(index_elements=[Task.id])`
   > (đúng khuôn `TaskStore.create()` đã làm ở `tasks.py:245-252`). **Tuyệt đối KHÔNG** đi qua
   > `TaskCreate`/`NoteCreate` (Pydantic DTO) hay `TaskStore.create()`/`NoteStore.create()` (store
   > method) — hai lớp đó có `@model_validator` `require_uuidv7` (`tasks.py:70-74`) **từ chối mọi ID
   > không phải UUIDv7**, mà §2 mục 1 vừa nói ID nguồn là UUIDv4 (`gen_random_uuid()`) và **phải giữ
   > nguyên**. Câu gốc "đi qua model của app để thừa hưởng bất biến" đọc theo nghĩa DTO/Store thì
   > **tự mâu thuẫn với chính spec này** — 100% task sẽ bị validator chặn ngay dòng đầu.
   >
   > Vì bỏ qua DTO/Store, script phải **tự tái tạo tay** đúng ba bất biến mà lẽ ra Store lo hộ:
   > - `is_private = false` cứng cho mọi hàng (đã đúng theo §2 mục 3, không cần mã hoá/`_sealed`).
   > - `ON CONFLICT (id) DO NOTHING` ở từng bảng (mã idempotent, giống `tasks.py:245-252`).
   > - **Không** áp `require_uuidv7`/`can_see_private` — hai kiểm tra này thuộc tầng API cho client mới,
   >   không áp cho hàng lịch sử; đây là quyết định có chủ ý, không phải bỏ sót.
5. **`tasks.status = 'archived'` và `notes.archived_at IS NOT NULL`: ⚠️ OPEN, tạm bỏ.**
   CHECK mới chỉ cho `open`/`completed` (đã query Neon xác nhận), nên `archived` không phải "thêm cột"
   mà là **thêm trạng thái thứ ba** — đụng bộ lọc, API, tab UI, test. Chủ chốt 2026-08-01: *ghi lại,
   tạm bỏ.* ⇒ Script **bỏ qua** những hàng đó, **đếm và in ra**, và **không mất gì**: chúng vẫn nằm
   nguyên trong `microschedule_v2` mà §6 giữ read-only vĩnh viễn. Xoá ngăn kéo cũ trước khi quyết ⇒
   mới là mất.

   📊 **Đo 2026-08-01: `tasks` có 0 hàng `archived`** (`open 3` · `completed 188`). Tức quyết định này
   hiện tốn đúng 0 dòng dữ liệu. **Vẫn giữ nhánh đếm-và-bỏ trong script** — nó rẻ, và nó là thứ duy
   nhất báo động nếu tới buổi cutover con số ấy không còn là 0. `notes.archived_at` **chưa đo**,
   dry-run phải in ra.
6. **Tuyên bố xong = 7 ngày liên tục không phải mở app cũ.** Sau mốc đó vẫn **không xoá gì**, chỉ đổi
   tư cách `microschedule_v2` từ "đường lùi" thành "archive".

## 4. Script

### 4.1 Vị trí + cách gọi

File mới `backend/scripts/cutover_v2.py`, chạy `uv run python -m scripts.cutover_v2 …` (cùng khuôn với
`scripts/check_migration_drift.py` — chạy dạng module từ `backend/`, nếu không thì `import app` gãy).

| Cờ | Mặc định | Nghĩa |
|---|---|---|
| *(không cờ)* | ✅ | **dry-run**: đọc cả hai đầu, in mọi con số + bảng ánh xạ, **ghi 0 byte** |
| `--commit` | | thật sự ghi. Không có cờ này thì tuyệt đối không mở transaction ghi |
| `--confirm-target-host=<host>` | | **bắt buộc đi kèm `--commit`**, xem ghi chú dưới |
| `--skip-calendar` | | bỏ nhánh lịch (dùng khi `010a` chưa live, hoặc đếm ra 0 buổi thủ công) |

**Biến môi trường:**

| Biến | Vai |
|---|---|
| `PGPW` | mật khẩu superuser `postgres` local — **chỉ để đọc**, không hardcode, không in ra log |
| `CUTOVER_SOURCE_URL` | tuỳ chọn; mặc định dựng bằng `URL.create()` (xem §4.2), không nối chuỗi |
| `CUTOVER_TARGET_URL` | **bắt buộc**, không có mặc định |

`CUTOVER_TARGET_URL` **cố ý không lấy từ `.env`**: nó phải trỏ được sang **Neon branch** ở bước ② của
§6 mà không cần sửa file nào. Bắt khai tường minh cũng loại luôn kiểu tai nạn "tưởng đang chạy dry-run
trên branch, hoá ra đang ghi vào production".

> 📝 **2026-08-02 — THÊM sau phản biện T3, "khai tường minh" một mình không đủ.** Chủ tự đọc lại biến
> môi trường trước khi gõ `--commit` là bước tay, và bước tay thì có lúc bỏ sót — nhất là sau khi vừa
> làm xong bước ② (dry-run + verify trên Neon branch) rồi quên đổi `CUTOVER_TARGET_URL` trước bước ④
> (chạy thật trên production). `--commit` **bắt buộc đi kèm** `--confirm-target-host=<hostname production
> thật>`; script parse host từ `CUTOVER_TARGET_URL`, so sánh với giá trị cờ, **lệch thì dừng ngay trước
> khi mở kết nối ghi**. Đây là double-entry rẻ tiền cho chính xác một hành động không có đường lùi.

### 4.2 Ràng buộc an toàn (bắt buộc, không phải khuyến nghị)

- Kết nối nguồn read-only: **không dùng lại nguyên văn cơ chế của `scripts/inventory_old_stores.py`** —
  script đó chạy bằng `psycopg` (`inventory_old_stores.py:42-54`), nhưng `cutover_v2.py` chạy trong môi
  trường `backend/` chỉ có `asyncpg` (`backend/pyproject.toml:10` — không có `psycopg` trong deps).
  `asyncpg`/SQLAlchemy không nhận kwarg `options=`; dùng `connect_args={"server_settings":
  {"default_transaction_read_only": "on"}}` khi tạo engine nguồn. **Test bắt buộc**: thử một `UPDATE`
  bất kỳ trên kết nối nguồn phải văng lỗi Postgres `25006` (`cannot execute UPDATE in a read-only
  transaction`) — không kiểm bằng cách đọc code, kiểm bằng cách cho nó thất bại thật.
  *(2026-08-02, sửa sau phản biện T2 — bản trước giả định sai driver.)*
- Dựng cả `CUTOVER_SOURCE_URL` mặc định lẫn mọi URL có mật khẩu bằng `sqlalchemy.engine.URL.create()`
  (đã có sẵn ở `backend/app/core/database_urls.py`), **không nối chuỗi f-string**. Mật khẩu Postgres có
  thể chứa `@`/`:`/`/`/`%`/`#` — nối chuỗi thẳng sẽ làm sai chuỗi kết nối *trước cả khi* script chạy tới
  dòng SQL đầu tiên. *(2026-08-02, thêm sau phản biện T2.)*
- Toàn bộ phần ghi nằm trong **một transaction duy nhất** — cơ chế cụ thể: mở **một** `AsyncSession`
  đích bằng `async with sessionmaker() as db, db.begin():`, chạy hết mọi `INSERT`/`ON CONFLICT` của
  §4.4 trên `db` đó, **không** commit từng bảng, **không** đi qua `app.web.deps.get_session` (dependency
  đó tự `commit()` cuối mỗi *request* HTTP — script không phải request, phải tự quản lý transaction,
  xem `deps.py:42-57`). Bất kỳ exception nào ⇒ rollback, Neon trở về đúng trạng thái trước khi chạy.
  *(2026-08-02, làm rõ sau phản biện T2 — bản trước chỉ nêu yêu cầu, không nêu cơ chế.)*
- Ghi bằng role **app** (`microsched_app`), không dùng `NEON_MIGRATOR_URL`. Quyền tối thiểu, và nó
  chứng minh luôn role app đủ sức làm mọi thứ app cần.
- `ON CONFLICT (id) DO NOTHING` ở mọi bảng ⇒ chạy lại lần hai là no-op, không phải nhân đôi.
- **Trước khi mở transaction ghi**, script tự kiểm tra (không tin checklist người ở §1): query
  `information_schema.columns` ở đích thấy đủ `task.completed_at`/`note.pinned`/`note.priority`, và
  đếm nguồn xác nhận `priorities.name` khớp đúng 6 khoá của `PRIORITY_MAP` (không thiếu, không thừa).
  Sai bất kỳ điều nào ⇒ dừng với lỗi rõ ràng, không chạy tới `INSERT` đầu tiên rồi mới báo lỗi khó hiểu.
  *(2026-08-02, thêm sau phản biện T2 — gate #3 ở §1 trước đây chỉ là dòng người tự kiểm, không phải
  thứ script tự chặn.)*
- **Không log giá trị `title`/`body` của chủ.** In id + số đếm. Repo public, threat model là social
  engineering (`devops-brief.md` §7) — log dán nhầm vào PR là rò dữ liệu cá nhân thật. Bọc toàn script
  trong một `try/except` ở tầng ngoài cùng; khi in exception, chỉ in `type(e).__name__` + id/tên bảng
  liên quan, **không** để traceback mặc định in `repr()` của một row có thể chứa `title`/`body`.
  *(2026-08-02, thêm sau phản biện T3.)*

### 4.3 Dry-run phải in đủ những gì

Dry-run là **cửa duyệt của chủ**, không phải bước lấy lệ. Tối thiểu:

```
NGUỒN  microschedule_v2 @ localhost          (read-only)
ĐÍCH   <host của CUTOVER_TARGET_URL>          ← in HOST, không in chuỗi kết nối

priorities → task.priority / note.priority   (PRIORITY_MAP, §3 mục 2)
  sort_order  name                 → p?     dùng bởi
  5           Quan trọng hơn TN    → p1     … task, … note
  …đủ 6 dòng, đọc từ nguồn rồi tra dict; tên lạ ⇒ DỪNG, không in "?" rồi chạy tiếp…

tasks        191 nguồn →  191 ghi ·   0 bỏ (status='archived')
task_items     ? nguồn →    ? ghi ·   0 bỏ (cha bị bỏ)
notes          ? nguồn →    ? ghi ·   ? bỏ (archived_at IS NOT NULL)
note_items     ? nguồn →    ? ghi
lịch thủ công  ? nguồn →    ? ghi   (0 ⇒ không tạo calendar_source)

đích trước khi chạy: task=0 note=0 …          ← đích KHÔNG rỗng cũng không sao (chủ đã dùng thật),
                                                 nhưng phải in ra để chủ biết mình đang chồng lên gì
```

Chỉ hai số trong khung là thật (191 task, 0 archived — đo 2026-08-01); phần còn lại là `?` **cố ý**,
để không ai nhìn khung này rồi tưởng đó là kết quả phải khớp. Dòng "bỏ" **luôn in ra kể cả khi bằng 0**
— một dòng `0 bỏ` là thông tin, một dòng vắng mặt là chỗ để lỗi nấp.

### 4.4 Bảng ánh xạ cột — nguồn `public.*` ➜ đích `microsched.*`

**`tasks` ➜ `task`**

| Nguồn | Đích | Ghi chú |
|---|---|---|
| `id` | `id` | giữ nguyên UUIDv4 cũ |
| `title` | `title` | |
| `note` | `body_md` | |
| `priority_id` | `priority` | join `priorities` rồi tra `PRIORITY_MAP` theo `name` (§3 mục 2); `NULL` ➜ `NULL`; tên lạ ➜ dừng script |
| `due_at` | `due_at` | |
| `status` | `status` | `open`➜`open`, `completed`➜`completed`, **`archived`➜ bỏ hàng** (§3 mục 5) |
| `completed_at` | `completed_at` | cột do `020` thêm |
| `created_at`, `updated_at` | như cũ | trigger là `BEFORE UPDATE`, không đè |
| — | `is_private` | `false` |
| — | `pinned` | `false` — app cũ **không có** ghim cho task |
| — | `deleted_at` | `NULL` |

**`task_items` ➜ `task_item`** — `id`/`task_id`/`content`/`is_completed`/`position`/`created_at`/`updated_at` 1:1.
⚠️ **Phải bỏ item có cha bị bỏ**, nếu không FK `task_id` nổ và cả transaction rollback ở dòng cuối.

**`notes` ➜ `note`**

| Nguồn | Đích | Ghi chú |
|---|---|---|
| `id`, `title`, `created_at`, `updated_at` | như tên | `notes.title` cũ `NOT NULL`, đích nullable — không sao |
| `body` | `body_md` | |
| `pinned` | `pinned` | cột do `020` thêm |
| `priority_id` | `priority` | cột do `020` thêm; cùng bảng giải với task |
| `archived_at IS NOT NULL` | — | **bỏ hàng** (§3 mục 5) |
| — | `is_private`, `embedding`, `deleted_at` | `false`, `NULL`, `NULL` |

**`note_items` ➜ `note_item`** — 1:1, đổi tên đúng một cột: **`is_done` ➜ `is_completed`**.
⚠️ **Phải bỏ item có cha bị bỏ** (cha là note `archived_at IS NOT NULL`, §3 mục 5) — cùng lý do và cùng
cách xử lý như `task_items`, chỉ khác bảng cha. *(2026-08-02, thêm sau phản biện T3 + T2 — cả hai độc
lập bắt cùng một lỗ hổng: bản trước có luật này cho `task_items` nhưng quên hẳn cho `note_items`, và vì
FK `note_item.note_id` bắt buộc có cha, một note archived có item con sẽ làm cả transaction rollback.)*

**Lịch thủ công** (bỏ qua nếu đếm 0, hoặc `--skip-calendar`)
- `kind='manual'` hợp lệ ở đích (`CHECK kind IN ('ics','excel','manual')`, `models.py:236`).
- Tạo **một** `calendar_source`: `name` = `"Buổi thủ công (app cũ)"`. **Cơ chế dedup cụ thể** (không
  phải "id sinh mới rồi hy vọng trùng tên tự xử lý" — `ON CONFLICT (id)` không bắt được va chạm trên
  `name`): `SELECT id FROM calendar_source WHERE lower(name) = lower('Buổi thủ công (app cũ)')` trước;
  có hàng ⇒ dùng `id` đó; không có ⇒ sinh UUID mới rồi `INSERT`. Chạy script hai lần (idempotency test
  §4.5 mục 4) phải ra **cùng một** `calendar_source.id` ở cả hai lần, không phải hai nguồn trùng tên.
  *(2026-08-02, làm rõ sau phản biện T3 — câu gốc "id sinh mới... nếu đã tồn tại thì dùng lại" không
  nói cơ chế, dễ bị hiểu thành insert-rồi-bắt-lỗi, trong khi transaction một-lần-rollback-toàn-bộ của
  §4.2 không hợp với select-catch-exception-rồi-tiếp-tục.)*
- Mỗi buổi: `id`/`title`/`location`/`starts_at`/`ends_at` giữ nguyên · `source_id` = nguồn vừa tạo ·
  `description` ➜ **`description_md`** (cột của `010a`) · `all_day` = `false` (nguồn cũ không có khái niệm này) ·
  `is_hidden` = `true` khi `user_cancelled` hoặc `status='cancelled'`.
- `calendar_event` có `CHECK (ends_at > starts_at)` ở **cả hai** schema ⇒ không có hàng nào vi phạm sẵn.

### 4.5 Test

Script này chạy **một lần trong đời**, nên test không phải để bảo trì mà để **bắt lỗi trước buổi chạy thật**.
Bắt buộc, chạy trên Postgres local của CI (khuôn `backend/tests/conftest.py`, biến `NEON_MIGRATOR_URL`):

1. Dựng một schema nguồn giả đúng DDL `docs/_local/v2-schema.sql`, đổ ~10 hàng phủ: task `open`/`completed`/`archived` ·
   task có `priority_id` và không · task_item của task `archived` · note có `archived_at` · note `pinned` ·
   note_item `is_done=true` · buổi lịch `manual` + buổi `class` (chỉ cái đầu được mang).
2. Chạy dry-run ⇒ **0 hàng ở đích**, và các con số in ra khớp kỳ vọng.
3. Chạy `--commit` ⇒ đếm khớp, `is_done` đã thành `is_completed`, `archived` vắng mặt, ID **bằng đúng ID nguồn**.
4. Chạy `--commit` **lần hai** ⇒ số dòng đích **không đổi** (chứng minh idempotent).
5. Ép một lỗi giữa chừng (vd bảng con vi phạm FK) ⇒ đích **rỗng như trước**, chứng minh một-transaction thật.
6. Nguồn có một `priorities.name` **không nằm trong `PRIORITY_MAP`** ⇒ script dừng với lỗi nêu đúng
   tên đó, và **đích không thêm một dòng nào** (kể cả các bảng lẽ ra đã ghi xong trước đó — chứng
   minh lại tính một-transaction ở một đường thoát khác).
7. *(2026-08-02, thêm sau phản biện T2)* Fixture có một **note `archived_at IS NOT NULL` kèm
   `note_item` con** ⇒ commit không rollback (item bị lọc theo cha, giống mục 5 test cho `task_item`),
   không phải một fixture riêng gây lỗi — đây là test cho *đường đi đúng*, không phải test cho crash.
8. *(2026-08-02, thêm sau phản biện T2)* Fixture có **cả hai bucket lịch**: buổi `external_uid` dạng
   `v1-schedule-*` (import gốc — không mang) và buổi `external_uid` dạng `manual_*` (thêm tay — phải
   mang) ⇒ dry-run in đúng hai con số riêng, `--commit` chỉ tạo buổi `manual_*` ở đích.
9. *(2026-08-02, thêm sau phản biện T2)* Thử `UPDATE` bất kỳ trên kết nối nguồn (đang mở read-only theo
   §4.2) ⇒ phải văng lỗi Postgres `25006`, không phải chạy được rồi bị bỏ qua.
10. *(2026-08-02, thêm sau phản biện T3)* Chạy `--commit` cho nhánh lịch **hai lần** ⇒ `calendar_source`
    ở đích vẫn chỉ có **một** hàng, cùng `id` ở cả hai lần (không phải hai nguồn trùng tên khác `id`).

## 5. Verify — điều kiện để nói "đã cutover"

Script có lệnh con `--verify` (chạy được độc lập, sau khi commit):

> 📝 **2026-08-02 — VIẾT LẠI mục 1+2 sau phản biện T3 + T2, cả hai độc lập bắt cùng lỗi thiết kế.**
> Bản gốc so **toàn bảng đích** với **toàn bảng nguồn (đã lọc)** — cả đếm lẫn hash. Nhưng §4.3 chính
> spec này đã nói "đích KHÔNG rỗng cũng không sao, chủ đã dùng thật" (dòng ~228). Nếu chủ tạo dù chỉ
> một task mới qua app (`TaskCreate`, `tasks.py:58`) giữa lúc `010a`/`011` đã live và buổi cutover thật
> diễn ra, tổng đích sẽ **vĩnh viễn không thể bằng** tổng nguồn-đã-lọc — verify sẽ đỏ mãi mãi dù cutover
> đúng 100%. Sửa: verify theo **tập ID đã import**, không theo tổng toàn bảng.

1. **Tập import ⊆ đích.** Script tự ghi lại (trong bộ nhớ, lúc `--commit`) tập `id` mỗi bảng vừa ghi
   (hoặc suy lại lúc `--verify` bằng chính filter của §4.4 chạy trên nguồn). Verify = anti-join:
   `expected_ids - (SELECT id FROM đích) = ∅` cho từng bảng. **Không** so tổng hai bên — đích có thể
   lớn hơn tập import vì chủ đã dùng app mới, và đó là chuyện bình thường, không phải lỗi. In thêm một
   dòng thông tin `đích - import = N` (N ≥ 0, không phải lỗi) để chủ nhìn thấy có bao nhiêu hàng tự tạo
   sau khi app mới đã sống.
2. **Vân tay nội dung, theo tập import, theo đúng cột từng bảng.** `task`/`note`/lịch: `id|title`.
   `task_item`/`note_item`: **`id|content`** — hai bảng này **không có cột `title`**
   (`models.py:160,218` chỉ có `content`). Tính `sha256` của danh sách đã sắp xếp, **giới hạn ở tập
   `expected_ids`** (không phải toàn bảng đích), so nguồn với đích. Đếm dòng không bắt được lỗi "đúng số
   lượng, sai nội dung"; vân tay thì có — nhưng vân tay trên sai cột (hoặc trên toàn bảng thay vì tập
   import) thì cũng vô nghĩa như không kiểm.
3. **Spot-check 5 hàng** in ra `id`, độ dài `title`, `created_at` — **không in nội dung**.
4. **Mở app thật trên `microsched.fly.dev` bằng mắt**: task cũ hiện đúng ngày tạo, note cũ mở ra đọc
   được, subtask đúng thứ tự. `agent-tasks/README.md` (quy ước báo cáo sau 007) nói thẳng: lỗi lọt tới
   chủ bám đúng vào tầng executor **không chạy được** thứ mình viết. Script xanh không chứng minh app đúng.

## 6. Nghi thức chạy — việc của CHỦ, không phải của executor

> 📝 **2026-08-02 — SỬA bước ①③ sau phản biện T2, hai lỗ hổng thật trên dữ liệu thật.**
> 1. `ALTER DATABASE ... SET default_transaction_read_only = on` chỉ đổi **default cho session MỚI mở
>    sau đó** — không đụng session đang sống. App cũ mở một kết nối Postgres dài hạn ngay lúc khởi động
>    và giữ suốt phiên làm việc; nếu app cũ vẫn đang chạy lúc gõ lệnh này, kết nối cũ **vẫn ghi được
>    bình thường**, và dữ liệu có thể trôi giữa lúc rehearsal (bước ②) và lúc chạy thật (bước ④) dù bước
>    ① tưởng đã khoá xong.
> 2. Bước ③ chỉ chụp ảnh **đích** (Neon) — không chụp **nguồn**. Giữ `microschedule_v2` read-only không
>    thay thế một bản backup độc lập nằm ngoài máy: nếu ổ đĩa local hỏng giữa lúc freeze và lúc tuyên bố
>    xong (⑦), đường lùi biến mất dù chưa từng xoá gì.

```
CỔNG VÀO   §1 đủ 5 dòng

NGÀY T     ① ĐÓNG BĂNG app cũ — theo đúng thứ tự, không đảo:
              1. THOÁT hẳn app cũ (đóng cửa sổ ứng dụng) — đây là bước khoá THẬT, vì nó tự đóng
                 connection dài hạn của nó.
              2. Xác nhận không còn session nào khác đang mở vào microschedule_v2:
                 SELECT pid, usename, state FROM pg_stat_activity
                 WHERE datname = 'microschedule_v2' AND pid <> pg_backend_pid();
                 → phải rỗng. Còn hàng nào lạ ⇒ dừng, hỏi tại sao, đừng tự terminate mà không biết nó là gì.
              3. ALTER DATABASE microschedule_v2 SET default_transaction_read_only = on;
                 (backstop cho phiên nào lỡ mở lại sau này — không phải cơ chế khoá chính)
              4. pg_dump microschedule_v2 ra file **ngoài repo** — bản backup nguồn độc lập, không phụ
                 thuộc "để máy local yên là an toàn". Đặt cạnh bản backup Neon ở bước ③.

           ② DRY-RUN trên Neon BRANCH:
              chủ tạo branch trong Neon console → CUTOVER_TARGET_URL trỏ vào branch
              → chạy --commit --confirm-target-host=<host của branch> → --verify → XOÁ BRANCH
              (branch là hạn mức LIÊN TỤC, chỉ tăng — cost-brief.md:127. Quên xoá là nợ vĩnh viễn.)

           ③ ẢNH CHỤP production: pg_dump Neon (lúc này còn nhỏ) ra file ngoài repo, cùng chỗ với
              bản backup nguồn ở bước ①.4. Ghi lại thời điểm chụp — mốc này là ranh giới "trước cutover".

           ④ CHẠY THẬT: dry-run lần cuối → chủ đọc bảng priority → CUTOVER_TARGET_URL trỏ production →
              --commit --confirm-target-host=<host production thật>

           ⑤ VERIFY §5, gồm cả bước nhìn bằng mắt. **Nếu verify đỏ**: KHÔNG restore nguyên bản dump ③ —
              app mới có thể đã nhận ghi mới của chủ sau bước ③, restore toàn bộ sẽ xoá mất chúng.
              Thay vào đó: xoá đúng các hàng vừa import (script biết chính xác `expected_ids` từ §5 mục
              1), rồi điều tra, rồi thử lại từ ④.

           ⑥ nhập lại lịch học/thi từ .ics gốc qua 010a (nếu chưa làm)

T + 7 NGÀY ⑦ chưa lần nào phải mở app cũ ⇒ tuyên bố xong.
              microschedule_v2 giữ read-only làm archive. KHÔNG xoá.
              Nhánh `main` của repo app cũ vẫn là đường lùi cuối cùng.
```

**Việc của chủ phải bật tay trước khi executor chạy bất cứ gì:**
- [ ] Postgres local đang chạy (nếu tắt: `connection refused` ở cổng 5432 — đừng đi debug script)
- [ ] `PGPW` đã set trong shell
- [ ] `CUTOVER_TARGET_URL` đã set, và **đã đọc lại xem nó trỏ branch hay production**
- [ ] `--confirm-target-host` (bước ②④) khớp đúng host đang thật sự nhắm tới — cờ này script tự chặn
      nếu lệch, nhưng chủ vẫn nên tự đọc trước khi gõ Enter

## 7. Cố ý KHÔNG làm

- **Không** chạy song song hai app "một thời gian cho chắc". Đó đúng là split-brain mà cả dự án này
  tồn tại để tránh (`migration-mapping-brief.md` §4): app cũ chạy đồng thời SQLite lẫn Postgres rồi
  không ai biết bản nào thật. Sau bước ① là một chiều.
- **Không** đụng SQLite `todo.db` (`C:\Users\os\Desktop\Tools\VC_microSchedule_home\todo.db`). Nó chết
  từ 03/06/2026, là tập con cũ hơn, và nằm trong vùng do-not-touch.
- **Không** xoá / sửa / vacuum `microschedule_v2`.
- **Không** hardcode số dòng vào test hay acceptance — mọi con số ở §2 là ảnh chụp 18/07, sẽ khác.
- **Không** in nội dung task/note ra log, PR, hay báo cáo.
- **Không** tự quyết `archived` (§3 mục 5). Gặp hàng `archived` thì đếm và bỏ, không sáng tạo.

## 8. Acceptance

1. `uv run pytest` xanh, có đủ 10 bài §4.5.
2. `uv run ruff check` + `uv run ruff format --check` sạch (đọc `.github/workflows/ci.yml` để lấy
   đúng danh sách lệnh, đừng chạy danh sách nhớ trong đầu).
3. Dry-run chạy thật trên máy chủ, in đủ khối §4.3, và **`SELECT count(*)` ở Neon không đổi một dòng nào**.
4. PR tách rõ **đã chạy** / **chưa chạy** theo quy ước `agent-tasks/README.md`. Cutover thật nằm ở
   vế "chưa chạy" cho tới khi chủ làm §6.
5. Dated note thêm vào `docs/migration-mapping-brief.md`: §2 bỏ mục "ép timezone" (nguồn đã tz-aware),
   §2 sửa mục `app_settings + priorities` (priorities tan vào `task.priority`, `app_settings` bị bỏ),
   §5 trỏ sang file này. **Thêm note, không viết đè** — luật `CLAUDE.md`.

## 9. Chỗ T1 tự quyết — chủ veto được

1. **Ghi bằng role app thay vì migrator** (§4.2). Quyền tối thiểu, đổi lại nếu role app thiếu grant
   nào đó thì lộ ra ngay tại buổi cutover chứ không phải lúc dùng hằng ngày — tôi coi đó là điểm cộng.
2. **Bỏ `app_settings` (8 dòng)** thay vì mang sang. Đó là cấu hình của app cũ cho các màn hình không
   còn tồn tại; mang sang là mang rác có tên đẹp. Nếu chủ muốn xem 8 dòng đó trước khi bỏ, dry-run in
   danh sách **khoá** (không in giá trị) là đủ.
3. **Một `calendar_source` gộp chung cho mọi buổi thủ công**, thay vì dựng lại đúng 4 nguồn cũ. Ba
   nguồn kia là lịch từ file, sẽ được `010a` tạo lại khi import — dựng lại vỏ rỗng của chúng chỉ để
   giữ hình dạng cũ là giữ nhầm thứ.

## 10. Vòng phản biện T2 + T3 (2026-08-02) — đã vá, ghi lại để không lặp lại

Chạy song song trên bản DRAFT đầu tiên: T3 (`gemini-3.1-pro-high` qua `agy-bridge`) và T2 (`codex exec
-m gpt-5.6-sol -s danger-full-access`, chạy nền, prompt hai phần: xác minh claim theo file:line + săn lỗ
hổng logic riêng cho một script ghi-một-lần lên dữ liệu thật). T1 kiểm tay từng finding trước khi vá —
không tin bất kỳ finding nào chỉ vì reviewer nói vậy.

**Đã xác nhận đúng và vá trực tiếp trong file này** (dated note `2026-08-02` tại từng chỗ):
- **[BLOCKER, T2]** Predicate nhận diện "buổi lịch thủ công" ở §3 mục 3 sai hoàn toàn — `kind=
  'manual_task_calendar'`/`event_type='manual'` không tồn tại trên đường ghi thật của app cũ. T2 tự đọc
  code app cũ (`old main.py:1774-1792`, `migrate_sqlite_to_postgres.py:261,329`) để chứng minh, không
  suy đoán. Đây là finding nặng nhất cả hai vòng: với predicate cũ, script sẽ đếm ra 0 dòng ở **mọi lần
  chạy thật** và §3 mục 5 khi đó bảo "0 dòng thì bỏ qua, bình thường" — mất đúng dữ liệu mục này viết ra
  để cứu, không một cảnh báo nào bật lên.
- **[BLOCKER, T3+T2 độc lập]** `note_items` không lọc theo cha `archived_at IS NOT NULL` — cùng lỗi đã
  biết và đã xử lý cho `task_items`, nhưng quên áp cho `note_items`. FK sẽ nổ, transaction rollback.
- **[BLOCKER, T3+T2 độc lập]** Verify (§5 cũ) so **toàn bảng đích** với **toàn bảng nguồn**, nhưng §4.3
  đã tự nói đích có thể không rỗng — verify không bao giờ pass được nếu chủ dùng app mới trước buổi
  cutover thật. Sửa sang so theo tập ID đã import (anti-join), không so tổng.
- **[BLOCKER, T2]** "Đi qua SQLModel của app để thừa hưởng bất biến" (§3 mục 4 cũ) đọc theo nghĩa DTO
  (`TaskCreate`) thì tự mâu thuẫn với chính §2 mục 1 — `TaskCreate.require_uuidv7` từ chối mọi ID không
  phải UUIDv7, mà toàn bộ ID nguồn là UUIDv4. Làm rõ: dùng **table model** trực tiếp, không qua DTO/Store.
- **[MAJOR, T2]** "Một transaction duy nhất" là yêu cầu chưa có cơ chế — domain store hiện chỉ `flush`,
  transaction thật do FastAPI dependency `deps.py` quản, script không đi qua dependency đó. Đã nêu cơ
  chế cụ thể (`async with session.begin()`).
- **[MAJOR, T2]** Bước freeze `ALTER DATABASE ... read_only=on` không đụng session đang sống — app cũ
  giữ một kết nối dài hạn từ lúc khởi động. Đã sửa: thoát app cũ trước, xác nhận `pg_stat_activity`
  rỗng, `ALTER DATABASE` chỉ là backstop.
- **[MAJOR, T2]** Không có backup độc lập của **nguồn** trước freeze (chỉ dump đích Neon). Đã thêm
  `pg_dump microschedule_v2` vào bước ①.
- **[MAJOR, T2]** "Vân tay nội dung" dùng `id|title` cho mọi bảng, nhưng `task_item`/`note_item` không
  có cột `title` (chỉ có `content`) — hash sẽ lỗi ngay khi implement. Đã sửa theo cột thật từng bảng.
- **[MAJOR, T2]** Mẫu kết nối read-only nguồn nêu "giống `inventory_old_stores.py`" nhưng script đó
  dùng `psycopg`, còn môi trường chạy `cutover_v2.py` (`backend/`) chỉ có `asyncpg` — `options=` không
  phải kwarg của `asyncpg`. Đã sửa sang `connect_args={"server_settings": ...}` + test bắt lỗi `25006`.
- **[MAJOR, T2]** Gate #3 (migration `0006` đã áp) chỉ là dòng người tự kiểm ở §1, script không tự chặn
  — thiếu cột thì lỗi rơi thẳng vào `INSERT` đầu tiên, khó hiểu. Đã thêm preflight tự kiểm trong §4.2.
- **[MAJOR, T2]** `CLAUDE.md` dòng 17 vẫn nói "012 chưa có spec" và hàng đợi thiếu `020` — tự mâu thuẫn
  với chính hai file này đã tồn tại. Đã sửa `CLAUDE.md` trong cùng lượt vá này.
- **[MINOR, T2]** `PGPW` nối thẳng vào URL bằng f-string — mật khẩu có `@`/`:`/`%` sẽ parse sai. Đã yêu
  cầu dùng `URL.create()` (helper có sẵn ở `database_urls.py`).
- **[MINOR/MAJOR tuỳ ngữ cảnh, T3]** Không có `--confirm-target-host` bắt buộc đi kèm `--commit` — rủi
  ro thật vì luồng rehearsal-trên-branch rồi chạy-thật-trên-production đòi đổi biến môi trường giữa hai
  lần, và một bước tay bị bỏ sót thì không có gì chặn. Đã thêm cờ, script tự chặn nếu host lệch.
- **[MINOR, T3]** `calendar_source` dedup theo tên nhưng câu gốc không nói cơ chế cụ thể (id sinh mới +
  hy vọng trùng tên tự xử lý không khớp với contract "một transaction, exception thì rollback toàn bộ").
  Đã nêu cơ chế: `SELECT` trước theo tên, không có mới `INSERT`.
- **[MINOR, T3]** Không có luật chặn `title`/`body` lọt vào traceback exception mặc định. Đã thêm yêu
  cầu bọc `try/except` tầng ngoài, chỉ log `type(e).__name__` + id.

**Đã xác nhận SAI, không vá** (theo kỷ luật `qa-framework.md` §8 — không âm thầm nhận một finding chỉ vì
reviewer đưa fix nghe hợp lý):
- **T3 finding "orphaned `priority_id` FK bị INNER JOIN loại âm thầm".** Kiểm tay `docs/_local/
  v2-schema.sql:622-626`: cả `tasks.priority_id` lẫn `notes.priority_id` đều có FK enforced
  (`tasks_priority_id_fkey`, `notes_priority_id_fkey`) trỏ `priorities(id)`. Postgres không cho một FK
  trỏ tới hàng không tồn tại được ghi xuống, nên `priority_id` orphan **không thể xảy ra** ở nguồn thật
  — lo ngại của T3 mô tả một trạng thái dữ liệu mà schema hiện tại không cho phép tồn tại. Không đổi
  `INNER JOIN` thành `LEFT JOIN`.

**Không kiểm hết** (nằm ngoài phạm vi kiểm tay lần này, để lại cho executor/QA lúc thi công thật):
finding T2 về "không có maintenance window / rollback chọn lọc cho production" (mục §6 bước ⑤ đã thêm
hướng dẫn xoá theo `expected_ids` thay vì restore toàn bộ dump, nhưng chưa viết thành script — đây là
việc của T2/Codex lúc thi công `cutover_v2.py --verify`, không phải việc sửa văn bản spec).
