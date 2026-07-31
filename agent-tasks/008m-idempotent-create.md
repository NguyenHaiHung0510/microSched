# 008m — hai seam của offline capture: id sinh ở client + ghi idempotent

> **Executor: Codex (T2).** Nhánh `feat/008m-idempotent-create` → PR nhỏ vào `develop`.
> Spec tự-chứa. Đọc `CLAUDE.md` + `AGENTS.md` trước.
> **KHÔNG có migration.** **KHÔNG đụng file nào của `008f`/`008g`/`008h`** — xem §3.

## 0. Bối cảnh — vì sao có task này, và vì sao là BÂY GIỜ

Kiến trúc đã chốt **offline-first** từ 2026-07-20 (`docs/frontend-brief.md` §2: Dexie + outbox tự viết, KHÔNG sync-engine), và luồng ghi đã được spec kín ở `docs/tracking-brief.md:150` (✅ CHỐT): *bấm = ghi ngay vào IndexedDB kể cả offline → toast 10 giây Hoàn tác → soft-delete; **UUIDv7 sinh ở client (B1)** nên online hay offline cũng một nút.*

`agent-tasks/008-task-slice.md` §2.8 (24/07) **hoãn** phần đó cho lát cắt 008: *"Phạm vi UI (online-only). KHÔNG outbox/Dexie."* Đó là hoãn phạm vi, **không phải đảo kiến trúc** — và nó vẫn đúng.

Nhưng hoãn *hàng đợi* thì rẻ, hoãn *hai cái seam* thì đắt theo cấp số:

- **Nếu server sinh `id`**, mỗi bản ghi tạo lúc offline **không có danh tính** cho tới khi sync xong. Mọi tham chiếu trong UI — ghim, checklist, hoàn tác — phải viết lại khi outbox về. `tracking-brief.md:150` chốt seam này (B1) đúng vì lý do đó: cùng một nút Hoàn tác chạy được cho cả bản chưa sync lẫn bản đã sync **chỉ vì id có sẵn từ trước**.
- **Nếu ghi không idempotent**, mọi lần retry của outbox là một dòng trùng.

008 là **lát cắt đặt khuôn** — 009/010/011/012 chép hình dạng của nó. Không có hai seam này thì khuôn là *online-only*, và lúc outbox về là phải sửa **năm** lát cắt thay vì một.

**📝 Sửa 2026-07-26 — đoạn này trước đây NÓI QUÁ, và phản biện spec bắt được.** Bản đầu viết: *"`008i` ghi nhận nguy cơ tạo trùng task khi request treo rồi người dùng tải lại trang… Ghi idempotent thì có [ngăn]"*. **Sai ở phạm vi.** Tải lại trang là **mất `id`** — nó chỉ sống trong bộ nhớ trang, mà outbox/IndexedDB đang cố ý hoãn. Nên task này **không** ngăn được ca "treo → reload → bấm lại".

**Cái nó thật sự cho, phát biểu cho đúng:** ghi trở nên **idempotent theo `id`**, nên **mọi retry mang cùng `id` đều an toàn** — retry của `apiRequest`, cú bấm thứ hai trên cùng một trang chưa reload, và sau này là retry của outbox. Không có nó thì mỗi retry là một dòng trùng, và chính đó là thứ khoá cửa cho lát cắt outbox. Ca "reload rồi bấm lại" chỉ đóng được khi `id` được **lưu bền** — đó là slice outbox, không phải slice này.

## 1. Đã KHOÁ — chép ra code, không mở lại

1. **`id` do client sinh, kiểu UUIDv7, gửi trong body.** Không phải header `Idempotency-Key`, không phải bảng phụ lưu khoá. Bản ghi *là* khoá của chính nó. Lý do: `tracking-brief.md:150` đã chốt cơ chế này ở tầng thiết kế, và nó cho ta idempotency miễn phí mà không thêm trạng thái nào ở server.
2. **`id` là tuỳ chọn.** Client không gửi ⇒ server sinh như hiện nay. Không được phá bất kỳ lời gọi nào đang chạy.
3. **Chỉ làm cho `task` trong task này.** 009–012 sẽ chép; đây là bản mẫu.
4. **Không đụng outbox, không đụng Dexie, không đụng IndexedDB.** Task này chỉ mở cửa; hàng đợi là một slice khác, sau.

## 2. Phải làm

### 2.1 Sinh UUIDv7 ở client

`frontend/` chưa có hàm sinh UUIDv7. **Không thêm dependency** — viết một hàm nhỏ trong `frontend/src/lib/` (ví dụ `uuidv7.ts`):

- 48 bit đầu = milli-giây Unix (big-endian), 4 bit version = `7`, 2 bit variant = `10`, phần còn lại ngẫu nhiên qua `crypto.getRandomValues`.
- Trả về chuỗi dạng chuẩn 8-4-4-4-12.
- 🔒 **Đơn điệu trong cùng một milli-giây.** Hai lần gọi liên tiếp trong cùng ms phải ra id **tăng dần**, không phải hai id ngẫu nhiên. Nếu không, thứ tự `created_at` và thứ tự id đá nhau, mà PK=UUIDv7 được chọn chính vì nó sắp được theo thời gian (`schema-physical-brief.md`).
- Test: 10 000 id sinh liên tiếp phải **đơn điệu tăng** và **không trùng**; version nibble là `7`; variant bits đúng.

### 2.2 Backend nhận `id` và ghi idempotent

- `TaskCreate` (`backend/app/domain/tasks.py`) thêm `id: UUID | None = None`.
- `TaskStore.create`:
  - `id` là `None` ⇒ y như hiện nay.
  - `id` có giá trị **và chưa tồn tại** ⇒ tạo bản ghi với đúng id đó.
  - `id` có giá trị **và đã tồn tại** ⇒ **không tạo gì**, trả về bản ghi đang có, status `200` (không phải `201`).
- 🔒 **Chống đua bằng DB, không bằng "kiểm rồi ghi".** Hai request cùng id tới cùng lúc thì `SELECT` rồi `INSERT` vẫn lọt cả hai. Dùng `INSERT … ON CONFLICT (id) DO NOTHING` rồi đọc lại, hoặc bắt `IntegrityError` rồi đọc lại. **Kiểm-rồi-ghi là sai**, và test §2.4 sẽ bắt.
- 🔴 **`payload.items` PHẢI bị bỏ hoàn toàn khi dòng cha đã tồn tại.** *(Thêm 26/07 sau phản biện spec — đây là lỗ mà bản đầu để hở.)* `TaskStore.create` hiện chạy `db.add_all(items)` **vô điều kiện** sau khi flush dòng cha (`backend/app/domain/tasks.py:221-229`). Nếu chỉ làm dòng cha idempotent mà để nguyên khối items, thì gửi lại lần hai sẽ **đắp thêm checklist vào task cũ** — tức vẫn là "biến tạo thành sửa", chỉ đổi chỗ. ⇒ Phải biết **INSERT dòng cha có thật sự xảy ra hay không** (số dòng bị ảnh hưởng của `ON CONFLICT … DO NOTHING`, hoặc bắt `IntegrityError`), và **chỉ khi nó xảy ra** mới tạo items. Trùng id ⇒ đọc lại và trả về **items đang có**, không thêm dòng nào.
- **Phân biệt "vô hình" với "không tồn tại".** Để trả `409` đúng như §2.3, `create` cần biết id **có tồn tại vật lý** hay không, mà cửa đọc thường (`readable()`) trả `None` cho cả hai ca. Cách làm: sau khi `INSERT … ON CONFLICT DO NOTHING` **không** tạo được dòng nào, đọc lại **hai lần** — một lần qua `readable()` (đọc được ⇒ `200`, trả bản ghi đang có), một lần bằng `select(Task.id).where(Task.id == …)` **không qua cửa** (chỉ lấy `id`, tuyệt đối không đọc trường nội dung nào ⇒ `409` thân rỗng). **Không** sửa `reading.py` để làm việc này.

### 2.3 🔒 Đây là chỗ task này có thể tạo lỗ bảo mật — đọc kỹ

`id` do client gửi nghĩa là **client chọn được khoá chính**. Ba đường phải chặn:

1. **Không được biến "tạo" thành "sửa".** Trùng id ⇒ trả về **bản ghi đang có nguyên vẹn**, tuyệt đối **không** ghi đè trường nào bằng payload mới. Nếu không, ai đó gửi `create` với id của một task đang có là sửa được nó qua cửa `POST`.
2. **Trùng id với một task KHÔNG đọc được** (riêng tư lúc cổng khoá, hoặc đã soft-delete) ⇒ **`409 Conflict`, không kèm nội dung gì**. Không `200` (lộ sự tồn tại + nội dung), không `201` (sẽ nổ ở DB). Chỉ `409` trống.
3. **Không tin định dạng.** **Không** ghép chuỗi id vào bất kỳ câu SQL nào bằng tay — ép kiểu `UUID` của Pydantic lo phần cú pháp.
4. 🔴 **Phải kiểm `version == 7`, và trả `422` nếu không.** *(Thêm 26/07 sau phản biện spec — bản đầu viết "ép kiểu Pydantic là đủ", và điều đó KHÔNG đủ.)* `UUID` của Pydantic nhận **mọi** version: v4, v1, kể cả nil `00000000-0000-0000-0000-000000000000`. Mà `schema-physical-brief.md` chọn **PK = UUIDv7 chính vì nó sắp được theo thời gian** — client gửi v4 là phá đúng tính chất đó, và không có gì báo lỗi. ⇒ validator trên `TaskCreate` từ chối id có `version != 7`. Test: gửi một UUIDv4 hợp lệ ⇒ `422`, **không** phải `201`.

### 2.4 Test — bắt buộc chứng minh BIẾT ĐỎ

| Test | Phải khẳng định |
|---|---|
| Không gửi id | Hành vi cũ nguyên vẹn, `201`, server sinh id |
| Gửi id mới | `201`, bản ghi mang **đúng** id đã gửi |
| Gửi lại y hệt | `200`, **vẫn đúng một dòng** trong DB |
| 🔒 Gửi lại với payload KHÁC | `200`, và bản ghi **không đổi một trường nào** — đây là test chống-biến-thành-sửa |
| 🔴 Gửi lại với `items` KHÁC | `200`, và **số dòng `task_item` không đổi** (đếm trong DB, đừng chỉ đọc response) — test cho luật ở §2.2 |
| 🔴 Gửi id không phải v7 | Một UUIDv4 hợp lệ ⇒ `422`, **không** có dòng nào được tạo |
| 🔒 Hai request song song cùng id | Đúng một dòng được tạo, cả hai bên đều nhận trả lời hợp lệ, **không** `500` |
| 🔒 Trùng id với task riêng tư lúc cổng khoá | `409`, thân rỗng, và task gốc **không đổi** |
| Trùng id với task đã soft-delete | `409`, và `deleted_at` **vẫn nguyên** |

Test "hai request song song" là test **chứng minh chống đua**: viết nó sao cho một bản cài kiểu kiểm-rồi-ghi sẽ **đỏ**. Ghi lại trong PR bạn đã phá gì để thấy đỏ.

### 2.5 Frontend dùng seam đó

> **📝 Viết lại 2026-07-26.** Bản đầu ghi *"đây là **dòng duy nhất** bạn được sửa trong `TasksScreen.tsx`"*. Phản biện spec chỉ ra ràng buộc đó **tự phá mục tiêu của task**: chỗ duy nhất sửa được khi đó là `mutationFn`, mà `mutationFn` chạy lại mỗi lần `mutate()` ⇒ **mỗi lần bấm lại sinh một `id` mới**, tức không còn idempotency nào. Phạm vi đúng là bốn chỗ dưới đây.

`id` phải được sinh **tại thời điểm người dùng submit**, nằm trong payload, và **không được sinh lại** khi cùng payload đó được gửi lần nữa:

1. `frontend/src/task-ui.ts` — thêm `id: string` vào type `TaskPayload`.
2. `TasksScreen.tsx` · `quickAdd` (form thêm nhanh) — sinh `uuidv7()` và đính vào payload trước khi `create.mutate(...)`.
3. `TasksScreen.tsx` · `onSubmit` của dialog tạo task — y như trên.
4. `TasksScreen.tsx` · `mutationFn` của `create` — chỉ **truyền payload đã có `id`** vào body. **Tuyệt đối không** gọi `uuidv7()` ở đây.

⚠️ **Chỉ sửa bốn chỗ trên trong `TasksScreen.tsx`; mọi handler khác giữ nguyên.** `008g` sẽ viết lại phần render danh sách của cùng file này ngay sau bạn — chạm rộng là conflict.

**Nói đúng lợi ích trong PR, đừng nói quá** (xem §0): cùng một payload gửi lại — do `apiRequest` retry, do người dùng bấm lần hai khi request đầu còn treo — **chỉ tạo đúng một task**. Ca "tải lại trang rồi bấm lại" **vẫn tạo task thứ hai**, vì `id` chưa được lưu bền; đóng ca đó là việc của slice outbox.

## 3. KHÔNG được làm

- **Không** migration, **không** đổi schema, **không** thêm cột. `id` đã là PK.
- **Không** thêm dependency nào (kể cả thư viện uuid).
- **Không** dựng outbox / Dexie / IndexedDB / service-worker sync. Task này **chỉ** mở seam.
- **Không** làm cho `note`/`tracker`/`entry` — chỉ `task`.
- **Không** thêm bảng lưu idempotency key.
- **Không** đụng `frontend/src/api.ts` (hợp đồng vừa vá ở `008i`), `reading.py`, `deleted_at`, `pinned`, `App.tsx`, hay `HomePage.tsx`. *(`frontend/src/task-ui.ts` thì **được** — §2.5 mục 1 yêu cầu.)*
- **Không** sửa gì khác trong `TasksScreen.tsx` ngoài **bốn chỗ** ở §2.5.
- **Không** gọi `uuidv7()` bên trong `mutationFn` (xem §2.5).
- **Không** tạo `task_item` khi dòng cha đã tồn tại (xem §2.2).
- **Không** đổi tên required check trong CI.

## 4. Acceptance — kiểm chứng được

1. `uv run ruff check` sạch; `uv run pytest` xanh **gồm lane `-m pg`** (test đua cần PG thật).
2. `npm run lint` / `npm test` / `npm run build` xanh.
3. Test đua và test chống-biến-thành-sửa đã chứng minh **biết đỏ**, ghi trong PR.
4. Test UUIDv7: 10 000 id đơn điệu tăng, không trùng.
5. `gh pr checks <PR>` xanh 5/5.
6. PR description nói rõ cách chống đua đã chọn (`ON CONFLICT` hay bắt `IntegrityError`) và vì sao.

## 5. Báo cáo

Biên lai: số PR + checks xanh + diff đọc được. Sandbox chặn Docker/`.git` ⇒ **báo đúng cái chưa verify được**, đừng báo đạt. T1 chạy lại tay.

## 6. Sau khi merge

**Không có migration** — đừng chạy `alembic upgrade` theo quán tính.

## 7. T2 feasibility review (2026-07-28)

- **Non-blocking — type frontend trong spec không khớp vai trò hiện tại của
  `TaskPayload`.** `TaskPayload` đang là output của `taskPayload()`/`TaskForm` và được
  dùng cho cả create lẫn update. Nếu chỉ thêm `id: string` đúng nguyên văn §2.5.1 thì
  `taskPayload(state)` không thể tạo giá trị hợp lệ, đồng thời payload edit cũng bị ép
  mang một `id` không thuộc PATCH. Judgment call: tách type payload form/update không
  có `id` khỏi `TaskPayload` dành riêng cho create có `id`; `TaskForm` tiếp tục phát
  type không có `id`, còn đúng hai submit path tạo task trong `TasksScreen.tsx` gắn
  `uuidv7()` trước khi gọi mutation. Việc này giữ nguyên bốn vùng sửa được phép trong
  `TasksScreen.tsx` và đúng seam product đã khóa.
- **Non-blocking — status động cần thêm tín hiệu ngoài `TaskRead`.** Route hiện khóa
  `status_code=201`, còn `TaskStore.create()` chỉ trả `TaskRead`; vì vậy store phải trả
  thêm kết quả “đã insert hay đã tồn tại” để route đặt `201`/`200`, và biểu diễn riêng
  conflict vô hình để route trả `409` thân rỗng. Đây là plumbing bắt buộc suy ra trực
  tiếp từ acceptance, không đổi API contract.
- **Không có blocker ở hai lần đọc.** `readable(select(Task)..., Task, auth)` hiện lọc
  đồng thời privacy và soft-delete; sau `ON CONFLICT DO NOTHING`, có thể đọc visible
  row qua chính gate này rồi chỉ khi không thấy mới chạy `select(Task.id)` vật lý.
  Query thứ hai không cần và không được lấy prose, nên không phải sửa `reading.py`.
- **Không có blocker ở race test PG.** Lane `@pytest.mark.pg` đã dùng Postgres thật,
  nhiều connection/transaction độc lập và `asyncio` trong
  `test_task_item_trigger.py`; fixture từ chối DB remote mặc định. Cùng pattern đó có
  thể dựng hai request/store transaction đồng thời với cùng UUID và đếm trực tiếp
  trong DB. Red proof có thể thay tạm upsert bằng check-then-insert để thấy một nhánh
  lỗi/500, rồi hoàn nguyên.
- **Giả định line number của spec đã drift nhưng hành vi vẫn đúng.** Khối hiện tại ở
  `TaskStore.create()` vẫn flush parent rồi luôn dựng và `db.add_all(items)`; do đó
  nguy cơ đắp checklist mà §2.2 mô tả là có thật dù số dòng không còn chính xác.
