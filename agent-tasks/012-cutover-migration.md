# 012 — Cutover: đưa dữ liệu thật từ Postgres cũ sang Neon, rồi ngừng dùng app cũ

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L1
> · Skill gợi ý: không cần · MCP cần: không cần.**
> **Trạng thái: DRAFT — viết bởi T1 (Opus 5) 2026-08-01, mọi quyết định ở §3 đã chốt trực tiếp với
> chủ. Chưa qua phản biện T2/T3, chưa được chủ duyệt bản chi tiết.**
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
   thêm tay **không nằm trong file `.ics` nào** ⇒ mất là mất hẳn. Nguồn cũ có sẵn cách nhận diện:
   `calendar_sources.kind = 'manual_task_calendar'` và `calendar_events.event_type = 'manual'`.
   **Lấy hợp của hai điều kiện.** Nếu đếm ra **0 dòng** ⇒ bỏ qua toàn bộ nhánh lịch, không tạo nguồn rỗng.
4. **Đường ghi = script dùng chính SQLModel của app** (không phải SQL trần, không phải HTTP API).
   Lý do: `tracking-brief.md` §116 nói thẳng có những bất biến **app canh, DB không canh** — quên một
   chỗ thì không có gì báo động; đi qua model của app là cách rẻ nhất để thừa hưởng chúng mà không
   phải dựng session đăng nhập.
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
| `--skip-calendar` | | bỏ nhánh lịch (dùng khi `010a` chưa live, hoặc đếm ra 0 buổi thủ công) |

**Biến môi trường:**

| Biến | Vai |
|---|---|
| `PGPW` | mật khẩu superuser `postgres` local — **chỉ để đọc**, không hardcode, không in ra log |
| `CUTOVER_SOURCE_URL` | tuỳ chọn; mặc định `postgresql://postgres:$PGPW@localhost:5432/microschedule_v2` |
| `CUTOVER_TARGET_URL` | **bắt buộc**, không có mặc định |

`CUTOVER_TARGET_URL` **cố ý không lấy từ `.env`**: nó phải trỏ được sang **Neon branch** ở bước ② của
§6 mà không cần sửa file nào. Bắt khai tường minh cũng loại luôn kiểu tai nạn "tưởng đang chạy dry-run
trên branch, hoá ra đang ghi vào production".

### 4.2 Ràng buộc an toàn (bắt buộc, không phải khuyến nghị)

- Kết nối nguồn mở với `options="-c default_transaction_read_only=on"` — cùng cơ chế
  `scripts/inventory_old_stores.py` đã dùng. Nguồn cũ là đường lùi; một câu `UPDATE` lạc vào đó là hỏng đường lùi.
- Toàn bộ phần ghi nằm trong **một transaction duy nhất**. Bất kỳ exception nào ⇒ rollback, Neon trở
  về đúng trạng thái trước khi chạy. Không commit từng bảng.
- Ghi bằng role **app** (`microsched_app`), không dùng `NEON_MIGRATOR_URL`. Quyền tối thiểu, và nó
  chứng minh luôn role app đủ sức làm mọi thứ app cần.
- `ON CONFLICT (id) DO NOTHING` ở mọi bảng ⇒ chạy lại lần hai là no-op, không phải nhân đôi.
- **Không log giá trị `title`/`body` của chủ.** In id + số đếm. Repo public, threat model là social
  engineering (`devops-brief.md` §7) — log dán nhầm vào PR là rò dữ liệu cá nhân thật.

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

**Lịch thủ công** (bỏ qua nếu đếm 0, hoặc `--skip-calendar`)
- Tạo **một** `calendar_source`: `kind='manual'`, `name` = `"Buổi thủ công (app cũ)"`, id sinh mới.
  Tên phải qua `uq_calendar_source_name_lower` — nếu đã tồn tại thì **dùng lại**, đừng đổi tên thành `… (2)`.
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

## 5. Verify — điều kiện để nói "đã cutover"

Script có lệnh con `--verify` (chạy được độc lập, sau khi commit):

1. **Đếm khớp** từng bảng: `nguồn (đã lọc) == đích`.
2. **Vân tay nội dung.** Với mỗi bảng, tính `sha256` của danh sách `id|title` đã sắp xếp ở **cả hai
   đầu** và so bằng nhau. Đếm dòng không bắt được lỗi "đúng số lượng, sai nội dung"; vân tay thì có.
3. **Spot-check 5 hàng** in ra `id`, độ dài `title`, `created_at` — **không in nội dung**.
4. **Mở app thật trên `microsched.fly.dev` bằng mắt**: task cũ hiện đúng ngày tạo, note cũ mở ra đọc
   được, subtask đúng thứ tự. `agent-tasks/README.md` (quy ước báo cáo sau 007) nói thẳng: lỗi lọt tới
   chủ bám đúng vào tầng executor **không chạy được** thứ mình viết. Script xanh không chứng minh app đúng.

## 6. Nghi thức chạy — việc của CHỦ, không phải của executor

```
CỔNG VÀO   §1 đủ 5 dòng

NGÀY T     ① ĐÓNG BĂNG app cũ — ngừng ghi, rồi:
              ALTER DATABASE microschedule_v2 SET default_transaction_read_only = on;
              (từ đây trở đi không có dữ liệu mới nào sinh ra ở nguồn)

           ② DRY-RUN trên Neon BRANCH:
              chủ tạo branch trong Neon console → CUTOVER_TARGET_URL trỏ vào branch
              → chạy --commit trên BRANCH → --verify → XOÁ BRANCH
              (branch là hạn mức LIÊN TỤC, chỉ tăng — cost-brief.md:127. Quên xoá là nợ vĩnh viễn.)

           ③ ẢNH CHỤP production: pg_dump Neon (lúc này còn nhỏ) ra file ngoài repo

           ④ CHẠY THẬT: dry-run lần cuối → chủ đọc bảng priority → --commit

           ⑤ VERIFY §5, gồm cả bước nhìn bằng mắt

           ⑥ nhập lại lịch học/thi từ .ics gốc qua 010a (nếu chưa làm)

T + 7 NGÀY ⑦ chưa lần nào phải mở app cũ ⇒ tuyên bố xong.
              microschedule_v2 giữ read-only làm archive. KHÔNG xoá.
              Nhánh `main` của repo app cũ vẫn là đường lùi cuối cùng.
```

**Việc của chủ phải bật tay trước khi executor chạy bất cứ gì:**
- [ ] Postgres local đang chạy (nếu tắt: `connection refused` ở cổng 5432 — đừng đi debug script)
- [ ] `PGPW` đã set trong shell
- [ ] `CUTOVER_TARGET_URL` đã set, và **đã đọc lại xem nó trỏ branch hay production**

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

1. `uv run pytest` xanh, có đủ 6 bài §4.5.
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
