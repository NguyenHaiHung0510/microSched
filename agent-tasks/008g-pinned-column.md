# 008g — đưa `pinned` xuống DB (và mang theo những cái ghim đang có)

> **Executor: Codex (T2).** Nhánh `feat/008g-pinned-column` → PR nhỏ vào `develop`.
> Spec tự-chứa. Đọc `CLAUDE.md` + `AGENTS.md` trước.
> ⚠️ **Task này CÓ migration.** Đọc §6 trước khi báo xong.

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
  - `TaskUpdate` — thêm `pinned: bool | None = None`.
  - `TaskCreate` — **không** thêm. Task mới tạo không bao giờ được ghim sẵn; ghim là một hành động riêng.
- `TaskStore.update` phải xử lý `pinned` **cùng đường với các trường thường khác** (`title`, `priority`, …).
  🔒 **Không** đưa `pinned` vào nhánh khoá dòng cha. `008` đã chốt: chỉ đổi `is_private` mới `SELECT … FOR UPDATE`, vì đó là trường duy nhất mà đua transaction làm hỏng bất biến. `pinned` không đụng bất biến nào.

### 2.3 Sắp xếp ở tầng đọc

`TaskStore.list` sắp `pinned DESC` **trước** thứ tự hiện có (đọc code để biết thứ tự hiện tại là gì; đừng đổi nó, chỉ thêm khoá sắp xếp lên trước). Client bỏ hết phần tự sắp theo ghim.

### 2.4 🔴 Mang ghim đang có sang — một lần, ở client

Chủ **đang có ghim thật** trong `localStorage` của PWA trên iPhone. Deploy xong mà không mang theo thì chúng **biến mất không lời báo** — đúng loại lỗi tệ nhất: không đỏ, không log, chỉ là một buổi sáng thấy mọi thứ mất ghim.

Trong `TasksScreen.tsx`, chạy **đúng một lần**:

1. Đọc `microsched:pinned-task-ids`. Rỗng hoặc không có ⇒ không làm gì.
2. Với mỗi id trong đó **mà có mặt trong danh sách task vừa tải về**, gửi `PATCH /api/tasks/{id}` với `{ pinned: true }`.
3. **Chỉ khi tất cả lời gọi đều thành công** mới `localStorage.removeItem(...)`. Một cái hỏng ⇒ **giữ nguyên khoá** để lần mở sau thử lại. Xoá khoá trước khi chắc chắn là tự tay vứt dữ liệu.
4. Không chặn giao diện, không hiện spinner. Hỏng thì im lặng và thử lại lần sau — nhưng **ghi `console.warn`** để còn dấu vết mà đọc.

⚠️ Id trong `localStorage` có thể trỏ tới task đã bị xoá. Bỏ qua, đừng để một `404` làm hỏng cả lượt mang dữ liệu (đó là lý do bước 2 lọc theo danh sách vừa tải).

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
