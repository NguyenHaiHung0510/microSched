# 008g — đưa `pinned` xuống DB (và mang theo những cái ghim đang có)

> **Executor: Codex (T2).** Nhánh `feat/008g-pinned-column` → PR nhỏ vào `develop`.
> Spec tự-chứa. Đọc `CLAUDE.md` + `AGENTS.md` trước.
> ⚠️ **Task này CÓ migration.** Đọc §6 trước khi báo xong.
> ✅ Đã qua 1 lượt `adversarial_review` (T3, `gemini-3.6-flash-high`, 2026-07-28, đọc code thật
> `tasks.py`/`reading.py`/`TasksScreen.tsx`/`0003`) — xem §7.

## 0. Bối cảnh — vì sao có task này

`008e` dựng chức năng ghim khi `task` **chưa có cột `pinned`**, nên nó được cắm tạm vào `localStorage` (`PINNED_STORAGE_KEY = 'microsched:pinned-task-ids'`, `TasksScreen.tsx`). Điều đó đã được ghi rõ là tạm thời ngay lúc làm.

Vì sao phải trả nợ **trước** 009: `008` là **task đặt khuôn** — 009 (note), 010 (calendar), 011 (tracker), 012 sẽ chép hình dạng của nó. Một trạng thái người dùng sống trong `localStorage` mà được chép sang bốn slice nữa là bốn lần phải gỡ, chứ không phải một.

Và nó hỏng thật, không chỉ hỏng về nguyên tắc: ghim **không sống qua việc đổi máy**, không sống qua việc xoá dữ liệu trình duyệt, và **không sống qua việc gỡ rồi cài lại PWA** — mà PWA là cách chủ dùng app.

## 1. Đã KHOÁ — chép ra code, không mở lại

1. **Cột `pinned BOOLEAN NOT NULL DEFAULT false`** trên bảng `task`. Không phải bảng nối, không phải cột thứ tự — chỉ một cờ.
2. **Không mã hoá.** `pinned` là boolean có thể truy vấn, và luật của dự án là *"markdown cho văn xuôi, cột có cấu trúc cho thứ cần truy vấn"* (`CLAUDE.md`). Nó **không** rơi vào diện mã hoá của `tracking-brief.md` §6.
3. **Không đẩy xuống `task_item`.** Ghim là chuyện của task, K11 cấm đẩy cờ xuống bảng con.
4. **Sắp xếp làm ở tầng đọc, không ở client.** Ghim nổi lên đầu **bất chấp bộ lọc** — đó là hành vi đã chốt ở `008e`. Nay `pinned` có trong DB thì thứ tự đó thuộc về câu truy vấn.
5. **Ghim đang có phải được mang theo.** Xem §2.4 — đây là phần dễ bị bỏ quên nhất và là phần chủ sẽ nhận ra ngay.

## 2. Phải làm

### 2.1 Migration `0004_task_pinned.py`

- `revision` nối tiếp `0003_task_item_privacy_trigger`. Kiểm `down_revision` bằng cách **đọc file `0003`**, đừng đoán.
- `ALTER TABLE task ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT false` (dùng `sa.Column` + `server_default=sa.text('false')`).
- `downgrade()` phải bỏ được cột.
- **Không** tạo index. Bảng một-người-dùng, số dòng ba chữ số; một index trên cột boolean độ chọn lọc thấp là chi phí ghi đổi lấy con số không. Muốn thêm thì **dừng và hỏi**, kèm số dòng thật.

### 2.2 Model + schema

- `backend/app/domain/models.py`: thêm `pinned` vào `Task`, khớp đúng migration (`nullable=False`, `server_default=text('false')`).
- `backend/app/domain/tasks.py`:
  - `TaskRead` — thêm `pinned: bool`.
  - `TaskUpdate` — thêm `pinned: bool | None = None`, **và thêm `"pinned"` vào danh sách trong `reject_null_required_fields`** (`tasks.py:88-94`) cùng với `title`/`status`/`is_private`. `pinned` là `NOT NULL` ở DB y như ba cột đó; bỏ sót bước này thì `PATCH {"pinned": null}` lọt qua Pydantic và nổ `IntegrityError` 500 chưa được bắt ở `db.flush()`.
  - `TaskCreate` — **không** thêm. Task mới tạo không bao giờ được ghim sẵn; ghim là một hành động riêng.
- `TaskStore.update` phải xử lý `pinned` **cùng đường với các trường thường khác** (`title`, `priority`, …).
  🔒 **Không** đưa `pinned` vào nhánh khoá dòng cha. `008` đã chốt: chỉ đổi `is_private` mới `SELECT … FOR UPDATE`, vì đó là trường duy nhất mà đua transaction làm hỏng bất biến. `pinned` không đụng bất biến nào.

### 2.3 Sắp xếp ở tầng đọc

`TaskStore.list` hiện sắp `due_at.asc().nulls_last(), created_at.desc()` (`backend/app/domain/tasks.py:178`). Thứ tự mới, **viết đúng một chuỗi này, đừng biến tấu**:

```python
stmt.order_by(Task.pinned.desc(), Task.due_at.asc().nulls_last(), Task.created_at.desc())
```

Client **bỏ hết** phần tự sắp theo ghim — thứ tự nay do server quyết, một nơi duy nhất. Hai nơi cùng sắp là hai nơi sẽ lệch nhau.

### 2.4 🔴 Mang ghim đang có sang — một lần, ở client

Chủ **đang có ghim thật** trong `localStorage` của PWA trên iPhone. Deploy xong mà không mang theo thì chúng **biến mất không lời báo** — đúng loại lỗi tệ nhất: không đỏ, không log, chỉ là một buổi sáng thấy mọi thứ mất ghim.

Trong `TasksScreen.tsx`, chạy **đúng một lần**:

1. **Chỉ chạy sau khi danh sách task đã tải xong** (`tasks.isSuccess === true`). Đây chỉ là mốc **thời điểm** để chờ app mount xong — **không** dùng làm nguồn xác định "id còn tồn tại hay không" (xem điểm 3).
2. Đọc `microsched:pinned-task-ids`. Rỗng, không có, hoặc `navigator.onLine === false` ⇒ **không làm gì, không xoá gì**.
3. 🔒 **Với MỌI id đọc được từ `localStorage`**, gửi `PATCH /api/tasks/{id}` `{ pinned: true }` — **đừng lọc qua `tasks.data.items` trước**. Danh sách đó bị cắt ở `limit=100` (`TasksScreen.tsx:599`, `/api/tasks?status=all&limit=100&offset=0`); một task ghim thật nằm ngoài 100 dòng đầu (sắp theo `due_at`/`created_at`) sẽ bị coi nhầm là "đã xoá" và **mất ghim vĩnh viễn, không lỗi không log**. Để chính response của `PATCH` làm trọng tài tồn-tại: `404` ⇒ task đã xoá thật, coi như xong, bỏ id đi; `2xx` ⇒ thành công, bỏ id đi; lỗi mạng/5xx ⇒ chưa xong, giữ lại để thử lần sau.
4. 🔒 **`Promise.allSettled`, không `Promise.all`.** Một `404` hay một lỗi mạng không được phép huỷ lượt mang dữ liệu của những id còn lại.
5. 🔒 **Xoá theo TỪNG ID, không xoá cả khoá.** Ghi lại vào `localStorage` đúng những id **chưa** thành công theo định nghĩa ở điểm 3 (tức chỉ giữ lại id gặp lỗi mạng/5xx). Cách "tất cả xong mới xoá" là sai ở chỗ: một id hỏng vĩnh viễn thì lượt sau retry lại cả mười, mãi mãi.
6. Không chặn giao diện, không spinner. Hỏng thì im và thử lại lần mở sau — nhưng **`console.warn`** để còn dấu vết.

⚠️ **Đua với chính người dùng.** Trong lúc lượt mang dữ liệu đang chạy, người dùng bấm *bỏ ghim* một task — request của migration tới sau sẽ ghim lại và **nuốt mất thao tác vừa rồi**. Chặn bằng một cờ `migrating` ở `TasksScreen` (state, không phải prop mỗi thẻ tự tính), truyền xuống **vô hiệu hoá nút ghim của MỌI `TaskCard`** cho tới khi lượt mang dữ liệu kết thúc — không chỉ những task đang được migrate, vì người dùng có thể bấm ghim một task BẤT KỲ trong lúc đó (nó chỉ kéo dài vài trăm ms). Đừng chọn cách "so sánh timestamp" — phức tạp hơn và vẫn thua.

⚠️ **Hai tab.** Đặt cờ `microsched:pinned-migrated-v1 = "1"` **NGAY TRƯỚC** khi phát request đầu tiên, và kiểm cờ đó trước khi chạy. Tab thứ hai mở sẵn từ trước thấy cờ thì đứng yên. Không cần `storage` event listener — cờ đọc lúc chạy là đủ cho ca này.

⚠️ **Mất gói xác nhận.** `PATCH {pinned: true}` là idempotent ở server, nên client retry vô hại. Đó là lý do bước 5 an toàn.

### 2.5 Frontend — bỏ trạng thái client

- Bỏ `PINNED_STORAGE_KEY`, `pinnedIds` state, `useEffect` ghi `localStorage`, và phần tự sắp theo ghim.
- `pinned` nay đọc từ `task.pinned`.
- Nút ghim gọi `PATCH` với `{ pinned: !task.pinned }`.
- 🔒 `onSuccess` **không** `await invalidateQueries` — lỗi `008i`, đừng chép lại.
- Giữ nguyên `aria-label` hai trạng thái đang có (`Ghim …` / `Bỏ ghim …`).

### 2.6 Test

Backend, và **phải chứng minh biết đỏ**:

| Test | Phải khẳng định |
|---|---|
| Mặc định | Task mới tạo có `pinned = false` |
| Bật/tắt | `PATCH {pinned: true}` rồi `false`, đọc lại đúng cả hai lần |
| Thứ tự | Task ghim đứng trước task không ghim trong `list`, **kể cả khi nó được tạo sau** |
| Thứ tự × bộ lọc | Ghim vẫn nổi lên đầu khi `status` filter đang bật |
| Không rò riêng tư | `pinned` **không** làm lộ task riêng tư khi private mode khoá |

### 2.7 ⚠️ Bạn đang làm SAU 008f — đây là những gì bạn sẽ thấy khác spec

`008f` merge trước và nó **đổi cấu trúc `backend/app/domain/reading.py`**: `readable()` được tách thành `with_privacy_gate()` + `not_deleted()`, và `readable()` giữ nguyên hành vi. Bạn **không cần đụng gì** ở đó — chỉ đừng ngạc nhiên khi mã không giống mô tả cũ.

`008f` cũng chèn **toast Hoàn tác** vào `TasksScreen.tsx` (mutation `remove`, `onSuccess`). Task này viết lại phần render danh sách để bỏ trạng thái ghim ở client. 🔒 **Đừng viết đè lên toast đó.** Trước khi commit, kiểm lại: xoá một task vẫn phải hiện toast có nút `Hoàn tác`, và nút đó vẫn phải chạy. Nếu bạn thấy mình đang xoá dòng nào liên quan tới `toast`, dừng lại.

*(Vì sao 008f đi trước dù nó phức tạp hơn: bản refactor `readable()` của nó là một **bản vá khuôn** — `readable()` hiện gọi `model.deleted_at` vô điều kiện, mà `calendar_source`/`calendar_event` không có cột đó, nên 010 chép nguyên là sập. Cái đó xuống càng sớm càng ít slice chép phải hình sai.)*

## 3. KHÔNG được làm

- **Không** thêm index (xem §2.1).
- **Không** thêm `pinned` vào `TaskCreate`.
- **Không** khoá dòng cha khi đổi `pinned` (xem §2.2).
- **Không** đẩy `pinned` xuống `task_item`.
- **Không** mã hoá `pinned`.
- **Không** xoá khoá `localStorage` trước khi mọi lời gọi thành công (xem §2.4).
- **Không** đụng `api.ts`, `deleted_at`, hay bất cứ gì thuộc `008f`.
- **Không** tự chạy `alembic upgrade` lên Neon. Migration áp bằng tay, do T1 (xem §6).
- **Không** đổi tên required check trong CI.
- 🔒 **Không** chép đoạn mang dữ liệu `localStorage` ở §2.4 sang 009/010/011/012. Nó là vá tình thế cho **đúng một** dữ liệu cũ có thật; các slice sau không có gì để mang, chép sang chỉ tạo request thừa và một đường đua vô cớ. Ghi rõ điều này trong PR description để người làm 009 đọc thấy.

## 4. Acceptance — kiểm chứng được

1. `uv run ruff check` sạch; `uv run pytest` xanh, **gồm lane `-m pg`**.
2. `npm run lint` / `npm test` / `npm run build` xanh.
3. Migration chạy được **cả hai chiều** trên PG local: `upgrade head` rồi `downgrade -1` rồi `upgrade head`.
4. Ít nhất một test ở §2.6 đã chứng minh biết đỏ, có ghi trong PR.
5. `gh pr checks <PR>` xanh 5/5.
6. PR description nêu rõ đường mang dữ liệu ở §2.4 và điều gì xảy ra khi nó hỏng giữa chừng.

## 5. Báo cáo

Biên lai, không phải lời khai: số PR + checks xanh + diff. Sandbox chặn Docker/`.git` ⇒ báo đúng cái chưa verify được, T1 chạy lại tay.

## 6. ⚠️ Sau khi merge — việc của T1, KHÔNG phải của executor

**Merge ≠ migration applied.** Không có `release_command` trong `fly.toml`, không có bước alembic trong `deploy.yml`. Deploy xong mà chưa áp migration thì **app mới chạy trên schema cũ** — cột `pinned` không tồn tại, mọi truy vấn task đổ 500. Không có cảnh báo nào.

Thứ tự bắt buộc: **áp migration lên Neon TRƯỚC, rồi mới merge.** Cột có `DEFAULT false` và code cũ không đọc nó, nên schema mới tương thích ngược với bản đang chạy — áp trước là an toàn, áp sau là một cửa sổ hỏng.

Verify **không dừng ở `alembic current`** — truy vấn `information_schema.columns` thật trên Neon để thấy cột có mặt.

## 7. Lượt phản biện T3 (2026-07-28) — đã fold, sẵn sàng giao Codex

`adversarial_review` (`gemini-3.6-flash-high`, đọc trực tiếp `agent-tasks/008g-pinned-column.md` +
`backend/alembic/versions/0003_task_item_privacy_trigger.py` + `backend/app/domain/tasks.py` +
`backend/app/domain/reading.py` + `frontend/src/TasksScreen.tsx`), câu hỏi *"spec sai ở đâu"*.

**3 finding thật, đã fold vào §2.2/§2.4 ở trên:**
1. [MAJOR] §2.4 dùng danh sách đã tải (cắt ở `limit=100`) để quyết "còn tồn tại hay không" ⇒ task
   ghim nằm ngoài 100 dòng đầu bị coi nhầm là đã xoá, mất ghim vĩnh viễn không lỗi không log. Vá:
   dùng response của chính `PATCH` (`404` so với `2xx`) làm trọng tài, không dùng list membership.
2. [MAJOR] `TaskUpdate.reject_null_required_fields` (`tasks.py:88-94`) không có `pinned` trong danh
   sách cột `NOT NULL` được gác ⇒ `PATCH {"pinned": null}` lọt qua Pydantic, nổ `IntegrityError` 500.
3. [MINOR] "Vô hiệu hoá nút ghim khi đang migrate" thiếu chỉ dẫn nó phải là **một cờ toàn cục**
   (mọi `TaskCard`), không phải chỉ những task đang được mang dữ liệu — người dùng có thể ghim BẤT
   KỲ task nào trong lúc đó.

**1 finding SAI, đã kiểm tay và loại bỏ (không fold):** T3 cho rằng chuyển sắp xếp xuống
`TaskStore.list` (`Task.pinned.desc()`) sẽ làm task ghim đã hoàn thành biến mất khi tab lọc
`status=open`, vì `list()` áp `WHERE status = status` trước khi sắp xếp (`tasks.py:190-193`). Đọc
`TasksScreen.tsx:596-599`: client **luôn** gọi `/api/tasks?status=all&limit=100&offset=0` bất kể tab
đang chọn — lọc theo tab hoàn toàn ở client (`visibleTasks`, dòng 630-649), giữ nguyên hành vi
"ghim nổi bất chấp bộ lọc" mà không đụng gì tới nhánh `status != "all"` ở server. T3 kết luận đúng
từ code nó đọc (`tasks.py`) nhưng bỏ sót phía gọi (`TasksScreen.tsx`) — không phải nguy cơ thật.

Kết luận: **agy là cố vấn, đã kiểm tay từng mục** ([[agy-model-capabilities]]). Spec sẵn sàng giao T2.
