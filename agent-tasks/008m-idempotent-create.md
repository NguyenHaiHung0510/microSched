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

**Và nó vá một rủi ro đang sống, không phải phòng xa:** `008i` ghi nhận nguy cơ **tạo trùng task** khi request treo rồi người dùng tải lại trang. Timeout 20 giây chỉ làm việc treo *hiện ra*; nó không ngăn cú bấm thứ hai sinh ra bản ghi thứ hai. Ghi idempotent thì có.

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

### 2.3 🔒 Đây là chỗ task này có thể tạo lỗ bảo mật — đọc kỹ

`id` do client gửi nghĩa là **client chọn được khoá chính**. Ba đường phải chặn:

1. **Không được biến "tạo" thành "sửa".** Trùng id ⇒ trả về **bản ghi đang có nguyên vẹn**, tuyệt đối **không** ghi đè trường nào bằng payload mới. Nếu không, ai đó gửi `create` với id của một task đang có là sửa được nó qua cửa `POST`.
2. **Trùng id với một task KHÔNG đọc được** (riêng tư lúc cổng khoá, hoặc đã soft-delete) ⇒ **`409 Conflict`, không kèm nội dung gì**. Không `200` (lộ sự tồn tại + nội dung), không `201` (sẽ nổ ở DB). Chỉ `409` trống.
3. **Không tin định dạng.** Ép kiểu `UUID` của Pydantic là đủ; **không** ghép chuỗi id vào bất kỳ câu SQL nào bằng tay.

### 2.4 Test — bắt buộc chứng minh BIẾT ĐỎ

| Test | Phải khẳng định |
|---|---|
| Không gửi id | Hành vi cũ nguyên vẹn, `201`, server sinh id |
| Gửi id mới | `201`, bản ghi mang **đúng** id đã gửi |
| Gửi lại y hệt | `200`, **vẫn đúng một dòng** trong DB |
| 🔒 Gửi lại với payload KHÁC | `200`, và bản ghi **không đổi một trường nào** — đây là test chống-biến-thành-sửa |
| 🔒 Hai request song song cùng id | Đúng một dòng được tạo, cả hai bên đều nhận trả lời hợp lệ, **không** `500` |
| 🔒 Trùng id với task riêng tư lúc cổng khoá | `409`, thân rỗng, và task gốc **không đổi** |
| Trùng id với task đã soft-delete | `409`, và `deleted_at` **vẫn nguyên** |

Test "hai request song song" là test **chứng minh chống đua**: viết nó sao cho một bản cài kiểu kiểm-rồi-ghi sẽ **đỏ**. Ghi lại trong PR bạn đã phá gì để thấy đỏ.

### 2.5 Frontend dùng seam đó

Mutation `create` trong `frontend/src/TasksScreen.tsx` sinh `id` **trước** khi gọi API và gửi kèm trong body.

⚠️ **Đây là dòng duy nhất bạn được sửa trong `TasksScreen.tsx`.** File đó đang có PR khác sống trong nó. Chạm thêm chỗ nào là conflict.

Lợi ích thấy ngay, và nên nói trong PR: người dùng bấm "Thêm", request treo, họ tải lại trang rồi bấm lại — **không còn sinh ra task thứ hai**.

## 3. KHÔNG được làm

- **Không** migration, **không** đổi schema, **không** thêm cột. `id` đã là PK.
- **Không** thêm dependency nào (kể cả thư viện uuid).
- **Không** dựng outbox / Dexie / IndexedDB / service-worker sync. Task này **chỉ** mở seam.
- **Không** làm cho `note`/`tracker`/`entry` — chỉ `task`.
- **Không** thêm bảng lưu idempotency key.
- **Không** đụng `frontend/src/api.ts` (hợp đồng vừa vá ở `008i`), `reading.py`, `deleted_at`, `pinned`, `App.tsx`, hay `HomePage.tsx`.
- **Không** sửa gì khác trong `TasksScreen.tsx` ngoài đúng chỗ ở §2.5.
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
