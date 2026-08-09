# 011a — Tracker slice, tầng nền: `tracker_group` / `tracker` / `entry` + lưới ghi + dashboard

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L2
> · Skill gợi ý: không cần · MCP cần: không cần.**
> **Trạng thái: OWNER-APPROVED theo handoff 2026-08-09 — đã qua phản biện
> **T3** (`gemini-3.1-pro-high`) + **T2 Codex**; T1 kiểm tay từng finding rồi vá.

## 0. Bối cảnh — `011` tách làm ba, đây là lô nào

`tracking-brief.md` đã chốt **toàn bộ** thiết kế tracking từ 2026-07-19/20 (0 mục ⚠️ còn treo) và
schema vật lý đã nằm sẵn trong migration `0001` — nhưng **chưa có một dòng domain/router/UI nào**.
Gộp cả cụm vào một PR thì nó to hơn `009` và `010a` cộng lại, và phần nặng nhất (tiền mã hoá + cổng
đọc qua cha) sẽ chìm giữa đống CRUD.

- **`011a` (file này)** — `tracker_group` + `tracker` + `entry`: CRUD, **lưới nút ghi một chạm**,
  dashboard **A1–A4** (hành vi) + **F1–F5** (tài chính từ entry). Đích: chủ tạo được tracker, bấm
  ghi dưới 3 giây, hoàn tác được, và nhìn thấy "lần cuối là bao giờ" + "tháng này tiêu bao nhiêu".
- **`011b`** (`agent-tasks/011b-medication-reminder-webpush.md`, đã viết) — hạ tầng Web Push + cron
  3 khe + nhắc thuốc + nhắc sub hết hạn. **Phụ thuộc `011a`** cho đường ghi `Entry`.
- **`011c`** (`agent-tasks/011c-subscription-renewal-settings.md`, **đã viết 2026-08-01**) — entity
  `subscription`, luồng gia hạn (`tracking-brief.md` §11), **F6** (burn cố định), toggle hiển thị giá
  qua `app_setting`, và seam định tuyến. Nó sửa vào ba file của `011a` — xem §9.

**Thứ tự thi công: `011a` → `011c` → `011b`.** `011b` nhắc được cả thuốc lẫn sub, mà phần nhắc sub
cần `subscription` đã tồn tại; làm `011b` ở cuối thì không phải ship một nửa tính năng rồi quay lại.
Cả hai spec đã được đồng bộ về thứ tự này sau phản biện T2 ngày 2026-08-01; không còn ngoại lệ hay
câu supersede chéo nào.

## 1. Sự thật đo được về schema hiện có — **`011a` KHÔNG có migration**

Đọc tay `backend/app/domain/models.py` + `backend/alembic/versions/0001_initial_schema.py` ngày
2026-08-01. Bốn bảng của lô này **đã tồn tại đủ cột**, kể cả những cột chỉ dùng ở `011b`/`011c`:

| Bảng | Dòng | Cột đáng nhớ |
|---|---|---|
| `tracker_group` | `models.py:273-292` | `name` (trần) · `kind` · `color` · `position`; `UNIQUE(id, kind)` phục vụ composite FK |
| `tracker` | `models.py:295-345` | `name` 🔐 · `kind` · `direction` · `input_mode` · `group_id` · `unit` · `color` · `reminder_time`/`reminder_text` (011b) · `is_private` · `deleted_at` |
| `subscription` | `models.py:348-399` | 011c — **011a không chạm** |
| `entry` | `models.py:402-455` | `tracker_id` · `subscription_id` (011c) · `quantity` · `amount` 🔐 · `list_amount` 🔐 · `occurred_at` · `note_md` 🔐 · `deleted_at` |

Index đã có (`models.py:565-579`): `uq_tracker_group_name_lower` (unique, **trên `tracker_group`
thôi**) · `ix_tracker_group_id` (thực chất là `tracker.group_id`) · `ix_entry_tracker_occurred_at`
(`tracker_id`, `occurred_at DESC`) · `ix_entry_occurred_at`.

⇒ **Không tạo file alembic nào trong `011a`.** Nếu trong lúc thi công thấy "cần thêm cột", **dừng
lại và hỏi** — nhiều khả năng đó là dấu hiệu đang đi chệch một quyết định đã chốt ở
`tracking-brief.md`, không phải schema thiếu. Trước khi bắt đầu, xác minh 4 bảng có thật trên Neon
bằng truy vấn `information_schema.columns` (luật cứng `CLAUDE.md`: không dừng ở `alembic current`).

## 2. Bốn chỗ khuôn `task`/`note` **SAI** nếu chép nguyên xi — đọc kỹ nhất mục này

`009` chép khuôn `008` gần như nguyên vẹn và đó là cách làm đúng. `011a` **không** chép nguyên vẹn
được, vì bốn điểm dưới đây khác về bản chất chứ không khác về chi tiết.

### 2.1 🔴 Mã hoá là **VÔ ĐIỀU KIỆN**, không phụ thuộc `is_private`

`note`/`task` mã hoá **theo cờ**: `_sealed(x) if is_private else x` (`notes.py:207-209`). Tracker thì
khác — CHECK trong DB là **vô điều kiện**:

```
models.py:302   CHECK (name LIKE 'enc:v1:%')                      -- tracker.name, LUÔN LUÔN
models.py:411   CHECK (amount IS NULL OR amount LIKE 'enc:v1:%')  -- entry.amount, hễ có là ciphertext
models.py:415   CHECK (list_amount IS NULL OR ...)
models.py:419   CHECK (note_md IS NULL OR ...)
```

Đây không phải sơ suất của DDL — nó thi hành đúng verdict `tracking-brief.md` §6: `tracker.name` mã
hoá **toàn bộ, không rẽ nhánh theo độ nhạy**, vì `"Hút thuốc"` rò gần hết thông tin dù mọi entry đã
mã hoá.

**Ba hệ quả bắt buộc:**

1. **Luôn `_sealed()`**, kể cả tracker công khai. Chép `_sealed(x) if is_private else x` sang đây ⇒
   `IntegrityError` ⇒ `500` ngay lần tạo tracker công khai đầu tiên. *(Hỏng ồn ào, sẽ bị bắt sớm —
   ghi ở đây chỉ để đỡ mất một vòng.)*
2. **🔴 Bật/tắt `is_private` KHÔNG đụng gì tới cột dữ liệu.** Toàn bộ vũ điệu mã-hoá-lại khi toggle
   ở `notes.py:272-295` (seal trước rồi mới bật cờ / hạ cờ rồi mới giải mã, theo đúng thứ tự để
   không vỡ ràng buộc) **không có lý do tồn tại ở đây** — cột đã là ciphertext ở cả hai trạng thái.
   `is_private` của tracker chỉ điều khiển **cổng đọc**. Chép vũ điệu đó sang là vừa thừa vừa nguy:
   nhánh "hạ cờ ⇒ `_clear()`" sẽ ghi **plaintext** vào `tracker.name` ⇒ vi phạm CHECK ⇒ `500` ở đúng
   thao tác mà chủ hay dùng nhất (tắt riêng tư). Đây là **hỏng im lặng ở tầng thiết kế**: code trông
   giống hệt `notes.py`, review lướt qua thấy "đúng khuôn", chỉ vỡ lúc chạy.
3. **Không có trigger nào canh con như `task_item`** (`tracking-brief.md` note 2026-07-24). Không cần
   — `entry` không có cột nào "trần khi cha private" để mà lệch.

### 2.2 🔴 `entry` đọc qua **cha**: `readable(stmt, Entry, auth)` sẽ **ném lỗi**

`models.py:406-407`: `Entry.__privacy_gate__ = Gate.VIA_PARENT`, `__delete_gate__ = Gate.APPLIES`.
`reading.py:92-93` ném `ReadingGateError` khi gặp `VIA_PARENT` — cố ý, kèm câu tiếng Việt chỉ đúng
việc phải làm. Khuôn đúng:

```python
stmt = select(Entry).join(Tracker, Entry.tracker_id == Tracker.id)
stmt = readable(stmt, Tracker, auth)   # cổng riêng tư + xoá-mềm của CHA
stmt = not_deleted(stmt, Entry)        # xoá-mềm của CHÍNH nó
```

`Subscription` cũng `VIA_PARENT` (011c) — cùng khuôn, và **cha là `Tracker` qua
`Subscription.tracker_id` (`models.py:370-376`)**, không phải `TrackerGroup`. T3 final-review từng
báo ngược rằng bảng này có `group_id` và không có `tracker_id`; kiểm tay model thật xác nhận finding
đó sai. `011c` phải join `Subscription.tracker_id == Tracker.id`.

### 2.3 🔴 Tiền là `TEXT` ciphertext ⇒ **mọi phép cộng chạy ở Python**, mọi validate cũng vậy

K18 (`tracking-brief.md` §10, note 2026-07-20) đã chốt: cột 🔐 có kiểu vật lý `TEXT`, nên precision
`NUMERIC(14,0)` của C2 và CHECK `>= 0` của K5 **không tồn tại trong DB** cho `amount`/`list_amount` —
chúng chuyển thành validate app-layer. Hệ quả cụ thể:

- **Cấm** `func.sum(Entry.amount)`, cấm `ORDER BY amount`, cấm mọi so sánh số trong SQL trên hai cột
  đó. Viết được, chạy được, ra rác — nó so sánh **chuỗi base64**. Đây là hỏng im lặng loại tệ nhất
  trong cả spec này: `ORDER BY amount DESC LIMIT 5` cho ra 5 dòng, trông như câu trả lời của F4, và
  không sai ở đâu nhìn thấy được.
- `quantity` **là** `NUMERIC(10,2)` trần với CHECK `> 0` trong DB (`models.py:409`) — cột này vẫn
  tính được trong SQL. Đừng gộp chung luật với tiền.
- Mọi tổng của dashboard = kéo entry về, `_clear()`, `Decimal`, cộng bằng Python (§4.3).

### 2.4 🔴 Không có unique index cho tên tracker ⇒ chống trùng ở app, và nó nằm **TRONG** cổng riêng tư

K19: AES-GCM dùng nonce ngẫu nhiên (`crypto.py:61`) ⇒ cùng một tên mã hoá ra hai chuỗi khác nhau ⇒
unique index trên `lower(name)` **không bao giờ bắt được trùng**. Vì thế `models.py:565-577`
**không** khai unique cho `tracker.name` (chỉ `tracker_group.name` — cột trần — mới có). Chống trùng
làm bằng decrypt-scan ở app lúc tạo/đổi tên.

**Câu hỏi K19 chưa trả lời, chốt tại đây: quét trong hay ngoài cổng riêng tư?** Có một tracker riêng
tư tên `"Thuốc X"`, chủ đang **khoá** riêng tư, và gõ tạo tracker công khai cũng tên `"Thuốc X"`:

- Quét **ngoài** cổng (thấy cả hàng riêng tư) ⇒ trả `409 "tên đã tồn tại"` cho một hàng người dùng
  **không nhìn thấy** ⇒ vừa khó hiểu vừa **rò**: người ngó qua vai gõ thử một cái tên là biết nó có
  tồn tại hay không. Đúng threat model chủ sợ (`devops-brief.md` §1: social engineering).
- Quét **trong** cổng ⇒ cho tạo trùng tên. Tên tracker không phải khoá của bất cứ thứ gì (không FK
  theo tên, không lookup theo tên), nên hậu quả tối đa là hai nút cùng nhãn lúc **đã mở** riêng tư —
  nhìn thấy được và sửa được bằng đổi tên.

⇒ **Chốt: quét TRONG cổng** (`readable(select(Tracker), Tracker, auth)` rồi `_clear()` từng tên, so
`casefold()`). Ưu tiên không-rò hơn không-trùng. Ghi lại để lượt QA sau không gắn cờ "chống trùng
hỏng".

**Đua ghi (race):** hai request tạo cùng lúc có thể cùng lọt. K19 đã chấp nhận điều này ("single-writer,
đủ"). **Đừng vá bằng unique index** (vô tác dụng, §2.4 đoạn đầu) và **đừng** dựng `name_hmac` — K19
ghi đó là *cửa nâng cấp*, không phải việc của v1. Trùng id (outbox gửi lại) đã được chặn bằng đường
khác: idempotent create theo UUIDv7 client-side, §4.2.

## 3. Đã khoá — chép ra code, không mở lại

Nguồn: `tracking-brief.md` (§1–§10) + `ui-brief.md` + `qa-framework.md`. Liệt kê ở đây để executor
không phải đọc chéo ba file giữa lúc code; **có mâu thuẫn thì brief thắng file này**, báo lại T1.

1. **Ghi = bấm phát ghi ngay + toast Hoàn tác 10 giây. KHÔNG hộp xác nhận** (§8.1). Hoàn tác =
   soft-delete entry (`deleted_at`), không phải xoá thật ⇒ hoàn tác nhầm vẫn khôi phục được.
2. **Không streak, không heatmap, không run-rate, không "tổng tiết kiệm"** (§8.2 "MUỐN — sau"). Bốn
   thứ này nằm trong danh sách *muốn có sau*, không phải v1.
3. **Không AI, không insight, không "vì sao tháng này cao"** — cố ý để cho AI Bước 1, `forward-spec.md`
   §E ghi thẳng: đừng để UI tracker nuốt thời gian hai tính năng AI.
4. **`tracker` không có cột `position`** (K10) — lưới nút sắp **động**; công thức chốt ở §5.2.
   `tracker_group` **có** `position`.
5. **Nhóm xoá thật, không soft-delete** (Q1); FK composite tự set `tracker.group_id = NULL`
   (`models.py:314-319`, `ON DELETE SET NULL (group_id)`). Tracker/entry thì **soft-delete**, và
   tracker **không bao giờ bị xoá cứng** (D1: RESTRICT bảo vệ lịch sử).
6. **Tiền luôn lưu số dương**; dấu là việc của `tracker.direction` lúc cộng (§4). Lưu số âm là ổ bug
   kinh điển — spec cấm.
7. **VND-only** (§3 note 2026-07-19 muộn): chỉ `amount` + `list_amount`. Không `orig_amount`,
   không `orig_currency`, không quy đổi tỷ giá, **không** thêm lại "cho chắc".
8. **Seed bộ tracker/nhóm khởi đầu KHÔNG thuộc `011a`** (Q2: data-migration Alembic **lúc cutover** =
   `012`). `011a` phải dùng được từ **DB rỗng** — nghĩa là UI bắt buộc có đường tạo nhóm và tạo
   tracker từ con số không.
9. **Luật UI cứng `ui-brief.md` §6** áp nguyên: không thẻ `<button>`/`<input>` thô · không hardcode
   màu · không chiều cao cứng · chữ ≥ 12px · không dùng `n-400` cho chữ · không tương tác chỉ-hover ·
   light-only. Component thiếu thì `shadcn add` (§8 của brief đó, kèm 4 cái bẫy), không viết tay.
10. **Chuẩn `data-testid`** `qa-framework.md` §6.3, kebab-case `<thực-thể>-<phần-tử>`; id riêng đi
    bằng thuộc tính `data-tracker-id`/`data-entry-id`, **không** nhét vào testid.

## 4. Backend

### 4.1 `backend/app/domain/money.py` — định dạng plaintext của số tiền (file mới, thuần)

Cột 🔐 lưu ciphertext của **một chuỗi**. Chuỗi đó trông thế nào là **hợp đồng giữa đường ghi và
đường đọc**, và nếu không chốt thì hai chỗ trong cùng một PR có thể ghi `"600000"` còn chỗ kia ghi
`"600000.00"` — round-trip lệch, không có test nào tự đỏ, và hỏng chỉ lộ ra khi cộng tổng.

**Chốt: plaintext của tiền = chuỗi thập phân nguyên, không dấu, không phân cách, không số 0 thừa.**
Khớp `^(0|[1-9][0-9]{0,13})$` (14 chữ số = trần `NUMERIC(14,0)` của C2).

```python
MAX_VND_DIGITS = 14

def to_storage(value: Decimal) -> str:
    """Validate rồi ép về dạng chính tắc; ném ValueError kèm câu tiếng Việt."""
    # nguyên (exponent >= 0 sau normalize) · >= 0 · <= 14 chữ số
    ...

def from_storage(raw: str) -> Decimal:
    """Nghịch đảo; raw không khớp regex ⇒ ValueError (dữ liệu hỏng, KHÔNG đoán)."""
    ...
```

`from_storage` **không được** khoan dung với chuỗi lạ. Một giá trị không khớp nghĩa là hoặc sai khoá,
hoặc ai đó ghi bằng đường khác — cả hai đều phải nổ ồn ào, không được trả về `Decimal(0)`.

Validate ở đây thay cho CHECK đã mất (K18/K5): `>= 0` (0 hợp lệ — bản dùng thử), nguyên (VND không có
phần lẻ), trần 14 chữ số. Test bằng bảng giá trị biên, không cần DB.

### 4.2 `backend/app/domain/tracker.py` — DTO + `TrackerStore`

Mirror **cấu trúc** `notes.py` (DTO → exception → store; store không giữ state, mọi method nhận
`db: AsyncSession` và tham gia transaction của request), nhưng theo đúng bốn khác biệt ở §2.

Dùng lại nguyên xi từ `notes.py`: `_clear()` / `_sealed()` (`notes.py:109-120`), validator
`require_uuidv7` (`notes.py:64-69`), `reject_null_required_fields`, exception `PrivateWriteLocked`.
**Đừng viết lại — import hoặc chép y hệt**; hai bản khác nhau của cùng một hàm là mầm lệch.

**DTO — liệt kê đủ field, không để executor tự suy:**

| DTO | Field | Ghi chú |
|---|---|---|
| `GroupCreate` | `id: UUID\|None` · `name: str` · `kind: Literal["health","finance"]` · `color: str\|None` · `position: int = 0` | `name` strip rồi mới kiểm rỗng |
| `GroupUpdate` | `name` · `color` · `position` | **không có `kind`** — xem §4.2 bẫy 3 |
| `GroupRead` | `id` · `name` · `kind` · `color` · `position` · `tracker_count: int` · timestamps | `tracker_count` để viết câu xác nhận xoá |
| `TrackerCreate` | `id: UUID\|None` · `name: str` · `kind: Literal["health","finance"]` · `direction: Literal["in","out"] = "out"` · `input_mode: Literal["event","money","quantity"] = "event"` · `group_id: UUID\|None` · `unit: str\|None` · `color: str\|None` · `is_private: bool = False` | |
| `TrackerUpdate` | `name` · `kind` · `direction` · `input_mode` · `group_id` · `unit` · `color` · `is_private` | `group_id`/`unit`/`color` nhận null = xoá; các field còn lại `reject_null_required_fields` |
| `TrackerRead` | `id` · `name` · `kind` · `direction` · `input_mode` · `group_id` · `unit` · `color` · `is_private` · **`last_entry_at: datetime\|None`** · **`entry_count_30d: int`** · timestamps | hai field cuối phục vụ A1 + thứ tự lưới (§5.2) — một request là đủ cho cả màn ghi |
| `EntryCreate` | `id: UUID\|None` · `tracker_id: UUID` · `occurred_at: datetime\|None` · `quantity: Decimal\|None` · `amount: Decimal\|None` · `list_amount: Decimal\|None` · `note_md: str\|None` | `occurred_at` vắng ⇒ `now()`; **có gửi thì bắt buộc tz-aware** |
| `EntryUpdate` | `occurred_at` · `quantity` · `amount` · `list_amount` · `note_md` | **không có `tracker_id`** — cấm reparent |
| `EntryRead` | `id` · `tracker_id` · `occurred_at` · `quantity` · `amount: Decimal\|None` · `list_amount` · `note_md` · timestamps | tiền đã `from_storage()`, ra ngoài là **số**, không phải chuỗi |

**Sáu bẫy DTO/store không được đoán:**

1. **`amount`/`list_amount` là `Decimal` ở biên API, `str` ciphertext trong DB.** Đường ghi:
   `_sealed(money.to_storage(value))`. Đường đọc: `money.from_storage(_clear(raw))`. Không có đường
   tắt nào khác. Pydantic nhận JSON number lớn ra `float` nếu khai `float` ⇒ **khai `Decimal`**, và
   `EntryCreate` phải từ chối số có phần lẻ bằng câu tiếng Việt (`money.to_storage` ném, router đổi
   thành `422`).
2. **K8 — entry phải khớp `input_mode` của tracker, kiểm ở app, trả `422`:**
   `event` ⇒ `amount`/`quantity` phải vắng · `money` ⇒ `amount` bắt buộc, `quantity` phải vắng ·
   `quantity` ⇒ `quantity` bắt buộc, `amount` phải vắng. `list_amount` chỉ hợp lệ khi có `amount`.
   **Luật chỉ áp lúc GHI.** Đổi `input_mode` của tracker về sau **không** làm entry cũ thành không
   hợp lệ, **không** backfill, **không** ẩn chúng đi — lịch sử là lịch sử. Viết thẳng câu này vào
   docstring, nếu không lượt review sau sẽ đề nghị "dọn dữ liệu không nhất quán".
3. **CHECK `unit_matches_input_mode` (`models.py:309-313`) là bẫy `PATCH` một-field.** Đổi
   `input_mode` từ `quantity` sang `event` mà không xoá `unit` ⇒ vi phạm CHECK ⇒ `500`. Store phải
   tự xử: đổi **sang** `quantity` mà không có `unit` (cũ lẫn mới) ⇒ `422` có chữ; đổi **khỏi**
   `quantity` ⇒ tự đặt `unit = None` trong cùng lượt UPDATE.
4. **Composite FK `(group_id, kind)` → `tracker_group(id, kind)`** (`models.py:314-319`): tracker
   **không thể** thuộc một nhóm khác `kind`. Hai đường vấp, cả hai phải ra `422` chứ không `500`:
   gán `group_id` của nhóm khác kind; và đổi `tracker.kind` trong khi vẫn giữ `group_id` cũ. Luật:
   **`kind` đổi được**, nhưng cùng lượt `PATCH` phải hoặc `group_id = null` hoặc trỏ tới nhóm đúng
   kind mới.
   > 📝 **Nói rõ 2026-08-01 sau phản biện T3 — chỗ này executor chắc chắn hụt nếu chỉ đọc câu trên.**
   > `PATCH` dùng `exclude_unset=True`, nên payload `{"kind": "finance"}` **không có** `group_id` ⇒
   > code kiểm "cùng lượt PATCH có `group_id` không" sẽ thấy không có, cho qua, và Postgres ném
   > `IntegrityError` ⇒ `500`. Luật đúng: khi `kind` **có** trong payload, store **đọc `group_id`
   > hiện tại từ DB** (bản ghi đã `SELECT … FOR UPDATE` sẵn) nếu payload không gửi, rồi validate cặp
   > `(group_id_hiệu_lực, kind_mới)`. Không khớp ⇒ `422` với câu tiếng Việt chỉ đúng cách sửa
   > (*"Nhóm hiện tại thuộc loại 'sức khoẻ' — bỏ nhóm hoặc chọn nhóm 'tài chính' trong cùng lần
   > sửa"*), **không** tự ý set `group_id = null` giùm chủ. Test bắt buộc: `PATCH {"kind": …}` đơn độc
   > trên tracker **đang có** nhóm ⇒ phải `422`, và test đó phải đỏ được trước khi sửa.

   `GroupUpdate` thì **không có `kind`** — đổi kind của một nhóm đang có tracker sẽ phá FK
   của **nhiều** hàng cùng lúc; muốn đổi thì tạo nhóm mới rồi chuyển tracker, tường minh và nhìn
   thấy được.
5. **Idempotent create theo id (seam `008m`)**, khuôn `notes.py:215-236`: `INSERT … ON CONFLICT DO
   NOTHING RETURNING id`; không có dòng trả về ⇒ đọc lại qua cổng ⇒ thấy được thì trả `200` + bản
   ghi hiện có (`created = False`), không thấy nhưng tồn tại vật lý ⇒ `TrackerIdConflict` ⇒ `409`.
   Áp cho **cả ba** `tracker_group` / `tracker` / `entry` — hàng đợi offline gửi lại một lượt ghi
   không được đẻ entry thứ hai.
6. **`PrivateWriteLocked` ⇒ `403`** khi tạo/đổi tracker sang `is_private=true` lúc cổng đang khoá
   (khuôn `notes.py:204-205`). Entry thì **không cần luật riêng**: tracker riêng tư đang khoá thì
   `_parent()` trả `None` ⇒ `404`, đúng và không rò.

**Method của `TrackerStore`:** `list_groups` · `create_group` · `update_group` · `delete_group`
(xoá thật) · `list_trackers` · `create_tracker` · `update_tracker` · `soft_delete_tracker` ·
`restore_tracker` · `list_entries(tracker_id?, from_, to_)` · `create_entry` · `update_entry` ·
`soft_delete_entry` · `restore_entry`.

Hai chỗ có bẫy truy vấn:

- **`list_trackers` phải trả `last_entry_at` + `entry_count_30d` mà không bắn N+1.** Một câu cho
  `last_entry_at`: `SELECT DISTINCT ON (tracker_id) tracker_id, occurred_at FROM entry WHERE
  deleted_at IS NULL ORDER BY tracker_id, occurred_at DESC` — khớp đúng
  `ix_entry_tracker_occurred_at`. Một câu `GROUP BY tracker_id` đếm 30 ngày. Rồi ghép trong Python.
  **Đếm và "lần cuối" phải bỏ entry đã soft-delete** — nếu không, hoàn tác xong con số "12 ngày
  trước" vẫn đứng nguyên và chủ sẽ tưởng nút Hoàn tác không ăn.
- **Không `limit`/`offset` cho `list_groups` và `list_trackers`** (vài chục dòng, và lưới nút thiếu
  một nút là mất một đường ghi — cùng lý do đã ghi ở `010a` §4.2). `list_entries` **thì có** phân
  trang (`limit` mặc định 100, trần 500) *và* lọc theo khoảng — lịch sử entry là thứ tăng vô hạn.

### 4.3 `backend/app/domain/dashboard.py` — A1–A4, F1–F5 (file mới)

**Một endpoint duy nhất** `GET /api/tracker/dashboard?month=YYYY-MM`, tính hết ở server. Lý do
không để client cộng: tiền chỉ tồn tại dưới dạng số **sau khi server giải mã** (§2.3), nên để client
tính thì phải ship toàn bộ entry của tháng xuống chỉ để cộng lại — vừa tốn, vừa đẻ ra chỗ thứ hai
định nghĩa "tháng này là từ ngày nào".

**🔒 Mọi ranh giới thời gian tính theo `+07:00`, ép bằng `timezone(timedelta(hours=7))`, KHÔNG
`zoneinfo`** — image Python slim trên Fly không đảm bảo có tzdata, `ZoneInfoNotFoundError` chỉ nổ
trên production (lý do đầy đủ: `010a` §2 mục 6). Tuần bắt đầu **thứ Hai**.

> 📝 **`?month=` không phải tháng hiện tại — định nghĩa bổ sung 2026-08-01 sau phản biện T3.** Bảng
> dưới viết bằng chữ "tới bây giờ", đúng cho tháng hiện tại và **vô nghĩa** cho tháng quá khứ (chủ
> mở lại tháng 6 thì "bây giờ" nằm ngoài tháng đó). Chốt một khái niệm duy nhất, dùng ở mọi ô:
> **`period_end = min(now_vn, đầu tháng kế tiếp)`**. Hệ quả từng mục:
> - **Tháng quá khứ** ⇒ `period_end` = cuối tháng ⇒ F1/F5/F3/F4 là số **cả tháng**, F2 so **trọn
>   tháng với trọn tháng trước** (thời lượng đã trôi = cả tháng, luật F2 không phải viết riêng).
> - **A3** ("tuần này/tháng này/năm nay") là **luôn luôn tương đối với hôm nay**, không theo `month` —
>   nó trả lời "tôi đang thế nào", không phải "tháng đó thế nào". Trả nguyên cả khi xem tháng cũ.
> - **A2/A4** cũng bám hôm nay, vì cùng lý do. Chỉ **F1–F5** đi theo `month`.
> - **`month` ở tương lai** ⇒ `period_end` = đầu tháng ⇒ mọi số bằng 0. Hợp lệ, không `422` —
>   `010a` đã cho phép điều hướng lịch sang tháng chưa tới.
>
> Trả kèm `period_start` / `period_end` (ISO, có offset `+07:00`) trong response. Không phải trang
> trí: đây là cách duy nhất để test khẳng định server đã cắt đúng biên, thay vì đoán từ tổng tiền.

| # | Trả lời bằng | Định nghĩa chốt cứng |
|---|---|---|
| A1 | `last_entry_at` mỗi tracker | Đã có sẵn trong `TrackerRead` (§4.2) — dashboard **không** tính lại |
| A2 | khoảng cách hiện tại vs trung bình | Lấy `occurred_at` của entry trong **90 ngày** gần nhất của tracker đó; cần **≥ 3** entry mới có trung bình, ít hơn ⇒ trả `null` và UI ghi "chưa đủ dữ liệu" (đừng vẽ "0 ngày"). Trung bình = trung bình các khoảng giữa hai entry liên tiếp, tính bằng Python |
| A3 | đếm 3 khung | Tuần này (từ thứ Hai 00:00 +07) · tháng này · năm nay, tới **thời điểm hiện tại** |
| A4 | tháng này vs trung bình 3 tháng trước | Đếm entry tháng hiện tại (một phần) so với trung bình của **3 tháng dương lịch đầy đủ** liền trước. **Không** chuẩn hoá theo số ngày đã trôi — A4 là "đang tăng hay giảm", chủ đọc kèm A3; muốn so công bằng thì đã có F2 |
| F1 | tổng `out` MTD | `direction='out'` **và** `amount IS NOT NULL`, từ 00:00 +07 ngày 1 tháng hiện tại tới bây giờ. Cộng bằng `Decimal` sau `from_storage()` |
| F2 | so **cùng kỳ** tháng trước | So theo **thời lượng đã trôi**, không theo ngày-trong-tháng: kỳ này `[đầu tháng, bây giờ)`, kỳ trước `[đầu tháng trước, đầu tháng trước + cùng thời lượng)`, **cắt tại cuối tháng trước** nếu tràn (31/3 vs tháng 2). Đây là chỗ §8.2 gọi là "sai lệch kinh điển" — so cả tháng thì tháng này luôn trông ít hơn. **Khi có cắt, trả thêm `prev_period_truncated: true`** (xem ghi chú ngay dưới bảng) |
| F3 | theo `tracker_group`, drill xuống tracker | Nhóm theo `group_id`; tracker không nhóm gom vào một mục **"Chưa nhóm"** (`group_id = null` là hợp lệ và phổ biến, K1). Chỉ liệt kê nhóm có ít nhất 1 đồng |
| F4 | top 5 entry lớn nhất tháng | **Bắt buộc sắp trong Python** sau khi giải mã — `ORDER BY amount` trong SQL sắp chuỗi base64 (§2.3) |
| F5 | net theo `direction` | `sum(in) − sum(out)` trong tháng. Có thể âm; UI dùng `--bad`/`--good`, không dùng dấu trừ trần |

> 📝 **`prev_period_truncated` — thêm 2026-08-01 sau phản biện T3.** Ngày 30/3, F2 so 30 ngày của
> tháng 3 với **28 ngày** của tháng 2 (đã cắt) và gọi đó là "cùng kỳ". Sai lệch tới ~7% và nó **im
> lặng** — chủ nhìn thấy "tháng này tiêu nhiều hơn 6%" trong khi thật ra đang tiêu ít hơn. Không đổi
> thuật toán (chuẩn hoá theo ngày sẽ đẻ ra một định nghĩa "trung bình/ngày" thứ ba, và F2 vốn để đọc
> nhanh), mà **làm sai lệch nhìn thấy được**: response mang thêm `prev_period_truncated: bool` +
> `prev_period_days: int` + `current_period_days: int`; UI bật cờ thì in chú thích nhỏ *"Kỳ trước chỉ
> có N ngày"* dưới con số. Đúng nguyên tắc §1.2 của `011b`: lượng tử hoá thì được, nhưng phải hiện ra.

> 🔴 **Một dòng ciphertext hỏng KHÔNG được hạ cả dashboard — thêm 2026-08-01 sau phản biện T3.**
> §4.1 bắt `money.from_storage()` ném khi gặp chuỗi lạ (đúng, và giữ nguyên) — nhưng dashboard cộng
> **hàng trăm** entry trong một request, nên một dòng hỏng ⇒ `500` ⇒ **toàn bộ màn tài chính trắng**,
> vĩnh viễn, cho tới khi có người vào sửa DB bằng tay. Luật cho **riêng đường aggregation** (không
> phải đường đọc một entry): bọc mỗi lần giải mã, dòng nào ném thì **bỏ qua dòng đó**, `logger.error`
> kèm `entry.id` (**không** kèm ciphertext hay bất kỳ mảnh giá trị nào), và đếm vào field
> `corrupted_entry_count: int` trả về cùng response. UI: `> 0` ⇒ dải cảnh báo *"N bản ghi không đọc
> được — số liệu có thể thiếu"*. Vẫn là "nổ ồn ào" theo tinh thần §4.1 — chỉ là nổ **ở chỗ nhìn thấy
> được** thay vì làm sập màn hình. Đường `GET /api/tracker/entry/{id}` thì **giữ nguyên ném `500`**:
> ở đó dòng hỏng chính là câu trả lời, không có gì để bỏ qua.

**Ba luật chung của tầng dashboard:**

- **Riêng tư đang khoá ⇒ số liệu thiếu, và đó là ĐÚNG.** Mọi truy vấn đi qua `readable(…, Tracker,
  auth)` nên entry của tracker riêng tư biến mất khỏi mọi tổng khi cổng khoá. **Đừng** thêm chú thích
  kiểu "một số mục đang ẩn" — nó nói cho người ngó qua vai biết là có dữ liệu riêng tư tồn tại, đúng
  thứ threat model muốn tránh; chủ đã có chỉ báo khoá/mở ngay trên thanh đầu (`PrivateGate`) nên tự
  biết. Ghi vào docstring để lượt QA sau không báo "tổng sai".
- **Tracker đã soft-delete (archive) thì entry của nó vẫn nằm trong F1–F5, nhưng tracker biến mất
  khỏi lưới ghi và A1–A4.** Đây là chỗ hai luật đúng đá nhau nếu không ai hoà giải: cổng đọc bảo
  "cha bị xoá mềm thì con biến mất", còn D1 (`tracking-brief.md` §7) bảo soft-delete tồn tại **chính
  vì** "xoá nhầm mất sạch lịch sử tiền = đau". Nếu archive làm tổng tháng trước tụt xuống thì
  soft-delete phản bội lý do nó ra đời, và F2 (so cùng kỳ) thành vô nghĩa. ⇒ **Đường aggregation cố
  ý KHÔNG gọi `not_deleted(stmt, Tracker)`**, chỉ gọi `with_privacy_gate(stmt, Tracker, auth)` +
  `not_deleted(stmt, Entry)`. Riêng tư thì **không** có ngoại lệ nào. Viết comment tại chỗ giải thích
  — nếu không, review sau sẽ "sửa" nó thành `readable()` cho đồng nhất và làm hỏng F2 một cách im
  lặng. *(Tên tracker của mục đã archive vẫn hiện trong F3/F4 — chấp nhận: chủ cần biết tiền đã đi
  đâu, và tracker archive vẫn là dữ liệu của chính chủ.)*

  Khuôn chuẩn, chép nguyên xi cho **mọi** truy vấn F1–F5:

  ```python
  from app.domain.reading import not_deleted, with_privacy_gate   # KHÔNG import readable ở file này

  stmt = select(Entry).join(Tracker, Entry.tracker_id == Tracker.id)
  stmt = with_privacy_gate(stmt, Tracker, auth)  # cổng riêng tư của CHA — vẫn áp, không có ngoại lệ
  stmt = not_deleted(stmt, Entry)                # xoá-mềm của CHÍNH entry — vẫn áp
  # CỐ Ý không có not_deleted(stmt, Tracker): xem đoạn văn ngay trên.
  ```

  > 📝 **Đính chính một luận điểm của T3 (2026-08-01).** T3 cho rằng thiết kế này buộc executor "phá
  > lớp trừu tượng `reading.py`". **Không đúng** — `with_privacy_gate` là helper **công khai**
  > (`reading.py:87`), gọi thẳng trên `Tracker` (`Gate.APPLIES`) là cách dùng hợp lệ; `readable()`
  > (`reading.py:109`) chỉ là hàm tiện lợi ghép sẵn hai helper đó. Không có gì bị bypass. Kết luận
  > của T3 (spec phải đưa snippet cụ thể) thì **đúng** và đã áp ở trên. Ghi lại cả hai vế vì đây
  > đúng dạng lỗi `qa-framework.md` §8 cảnh báo: **kết luận đúng, trích dẫn sai** — người đọc sau
  > không được để lời giải thích sai đi kèm một bản vá đúng.
- **Tháng rỗng không phải lỗi.** `month` hợp lệ mà chưa có entry ⇒ `200` với các số bằng 0 /
  danh sách rỗng, **không** `404`.

### 4.4 `backend/app/web/routers/tracker.py`

Mirror `routers/notes.py`: `Database`/`CurrentSession` alias, `_not_found()`, `_private_locked()`.
Đăng ký trong `backend/app/main.py` **dưới `protected_api`** (`main.py:87-91`, nơi
`Depends(require_session)` đã gắn sẵn) — đọc file thật, đừng đoán tên biến.

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/api/tracker/groups` | envelope `{"items": [...]}`; không phân trang |
| POST | `/api/tracker/groups` | `201` mới / `200` trùng id; **`409` trùng tên** — `tracker_group.name` trần **có** unique index thật (`models.py:565`), bắt `IntegrityError` đổi thành 409 tiếng Việt, đừng để bò ra `500` |
| PATCH | `/api/tracker/groups/{group_id}` | tên/màu/thứ tự; `409` nếu tên mới trùng; **không đổi `kind`** |
| DELETE | `/api/tracker/groups/{group_id}` | **204, xoá thật**; tracker con tự về "chưa nhóm" |
| GET | `/api/tracker/trackers` | envelope; kèm `last_entry_at` + `entry_count_30d`; không phân trang |
| POST | `/api/tracker/trackers` | `201`/`200` idempotent; `403` khi tạo private lúc khoá; `409` trùng **tên** (quét trong cổng, §2.4) |
| PATCH | `/api/tracker/trackers/{tracker_id}` | `422` cho vi phạm `unit`/`kind`×`group` (§4.2 bẫy 3, 4) |
| DELETE | `/api/tracker/trackers/{tracker_id}` | **204, soft-delete** (archive) |
| POST | `/api/tracker/trackers/{tracker_id}/restore` | khuôn `notes.py:98-104` |
| GET | `/api/tracker/entries` | query `tracker_id?`, `from`/`to` (ISO-8601 **có offset**), `limit`/`offset` |
| POST | `/api/tracker/entries` | đường ghi một chạm; `422` cho vi phạm K8 |
| PATCH | `/api/tracker/entries/{entry_id}` | "làm giàu sau" — sửa giờ/tiền/ghi chú; không đổi `tracker_id` |
| DELETE | `/api/tracker/entries/{entry_id}` | **204, soft-delete** — đây chính là nút Hoàn tác |
| POST | `/api/tracker/entries/{entry_id}/restore` | hoàn tác của hoàn tác |
| GET | `/api/tracker/dashboard` | query `month=YYYY-MM` (mặc định tháng hiện tại theo +07:00) |

**`datetime` naive bị từ chối `422`** ở mọi field thời gian nhận vào (`occurred_at`, `from`, `to`) —
cùng lý do và cùng cách đã chốt ở `010a` §4.2: ô `<input type="datetime-local">` gửi chuỗi không có
offset, nhận bừa thì Postgres diễn giải theo timezone của phiên và ta có lệch 7 tiếng ở đường ghi
tay. Frontend gắn `+07:00` trước khi gửi (§5.4).

## 5. Frontend

Thêm **một tab mới** vào khối tab ở `frontend/src/App.tsx:104-125` — mirror đúng cách các tab hiện
có đang làm (`role="tab"` + `aria-selected` + `Button variant`, icon `lucide-react`; `Activity` hoặc
`CircleDot` hợp lẽ). **Đếm số tab bằng mắt lúc thi công, đừng tin con số ở đây:** trên `develop`
ngày 2026-08-01 mới có **hai** tab (`Task`, `Ghi chú`) — tab `Lịch` nằm trong `010a` chưa merge. Tuỳ
thứ tự merge, đây là tab thứ ba hoặc thứ tư; không có gì phụ thuộc vào con số đó.

File mới: `TrackerScreen.tsx` · `TrackerForm.tsx` · `GroupForm.tsx` · `EntryEditDialog.tsx` ·
`DashboardPanel.tsx` · `tracker-ui.ts` · `tracker-undo.ts`.

### 5.1 Màn ghi **kiêm** dashboard hành vi — không tách hai màn

`tracking-brief.md` §8.2 A1 ghi thẳng: "lần cuối" hiện **trên chính nút ghi**, "màn ghi kiêm dashboard
chính". Nghĩa là nút không phải chỉ có tên: mỗi nút mang **tên tracker + `12 ngày trước`**. Tách
dashboard thành một tab riêng là làm hỏng chủ ý — con số phải đập vào mắt mỗi lần định bấm.

Bố cục màn: lưới nút (A1 trên nút) → khối A2/A3/A4 của tracker vừa chạm hoặc dạng gấp → khối tài
chính F1–F5 → danh sách entry gần đây (sửa/xoá).

### 5.2 Thứ tự lưới nút — công thức chốt, và **đóng băng trong phiên**

K10 bỏ cột `position` vì lưới "sắp động theo tần suất + gần đây". Công thức: sắp giảm dần theo
`entry_count_30d`, hoà thì theo `last_entry_at` mới hơn trước, hoà nữa thì theo tên (`localeCompare`
`vi`) cho **tất định**.

**🔒 Tính đúng một lần lúc mount màn, giữ nguyên cho tới khi rời màn / tải lại.** Không có luật này
thì mỗi lần bấm ghi xong, `entry_count_30d` tăng, lưới **tự sắp xếp lại ngay dưới ngón tay** — trên
điện thoại đó là cách chắc chắn để ghi nhầm tracker ở lần bấm kế tiếp, và nó phá đúng cái trí nhớ cơ
bắp mà "ghi < 3 giây" dựa vào. Đây là hệ quả không ai viết ra khi chốt "sắp động" ở K10.

### 5.3 Ghi một chạm + Hoàn tác

- `input_mode='event'` ⇒ chạm = ghi, không hỏi gì.
- `input_mode='money'` ⇒ chạm mở một ô số **duy nhất**, bàn phím số (`inputMode="numeric"`), Enter =
  ghi. Không mở dialog nhiều field.
- `input_mode='quantity'` ⇒ như trên, kèm nhãn `unit`.
- **Nhấn giữ** (long-press, ~500ms) = ghi lùi giờ: chọn nhanh *hôm qua / 2 giờ trước / chọn giờ*.
  ⚠️ Long-press là tương tác **chỉ-chạm** — trên desktop phải có đường tương đương nhìn thấy được
  (một nút nhỏ "⋯" trên thẻ), nếu không là vi phạm `ui-brief.md` §9(a) theo chiều ngược lại: luật đó
  cấm hover-là-đường-duy-nhất, và cấm-một-chiều-là-cho-phép-chiều-còn-lại đã sinh lỗi thật ba lần
  trong dự án này (`qa-framework.md` §3.C).
  > 🔴 **Nhấn giữ đẻ ra HAI entry nếu không chặn — thêm 2026-08-01 sau phản biện T3.** Trên iOS,
  > sau `touchend` trình duyệt vẫn phát một `click` tổng hợp: chủ nhấn giữ để ghi lùi giờ **hôm qua**,
  > nhả tay, và cái `click` đó kích luôn đường ghi một chạm ⇒ **hai** entry, một sai giờ. Debounce
  > 1,5 giây **không** cứu được vì hai lượt ghi này khác nhau về payload chứ không phải trùng lặp.
  > Bắt buộc: khi long-press đã kích hoạt, đặt cờ `longPressFired` và `preventDefault()` trên
  > `touchend`, rồi bỏ qua `click` kế tiếp (cửa sổ ~400ms) — cờ reset ở `touchstart` sau. Test
  > Playwright bắt buộc: mô phỏng nhấn giữ trên một tracker `event`, khẳng định **đúng một** entry
  > tồn tại sau đó. Bài này phải đỏ được nếu gỡ đoạn chặn.
- Ghi xong ⇒ toast **10 giây** có nút Hoàn tác (`sonner`, khuôn `task-undo.ts`); Hoàn tác gọi
  `DELETE /api/tracker/entries/{id}`.
- 🔌 **Seam bắt buộc cho `017` (chủ duyệt 2026-08-02):** mọi write của màn tracker — tạo/sửa/xoá
  group, tracker, entry; ghi một chạm; và Hoàn tác — phải đi qua **một helper mutation dùng chung**
  bọc `useMutation`/`apiRequest`, không rải lời gọi `apiRequest` trực tiếp khắp component. `011a` chỉ
  dựng seam online này; **không** thêm Dexie, IndexedDB hay hành vi offline (đó là `017`). Các lô
  `010`/`011b`/`011c` nên chép cùng khuôn để `017` bọc một cửa thay vì đuổi theo hàng chục điểm gọi.
- **Debounce (K9):** khoá nút của **chính tracker đó** từ lúc chạm tới khi mutation settle **+ 1,5
  giây**. ⚠️ K9 viết trong ngoặc là *"khoá nút khi toast hiện"* — hiểu đúng nghĩa đen là khoá đủ 10
  giây, và như thế thì ghi hai lon bia cách nhau nửa phút trở thành không làm được. Quyết định của
  spec này là giữ **đúng quyết định** ("debounce UI") và **thu hẹp cơ chế** trong ngoặc. Đây là một
  trong bốn mục ở §8 chủ veto được.

### 5.4 Vùng giờ, tiền, và dữ liệu ác ý

- **Đọc:** `Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', … })` ở **mọi** chỗ hiện
  giờ. **Ghi:** nối `"+07:00"` vào chuỗi của `datetime-local`, **không** `new Date(x).toISOString()`
  (hiểu ô nhập theo múi giờ *thiết bị*). Hai lớp, giống hệt `010a` §5 mục 3.
- **Tiền hiển thị:** `Intl.NumberFormat('vi-VN')` + hậu tố `₫`. Nhập thì chỉ nhận chữ số (chặn dấu
  chấm/phẩy ngay ở ô, đừng để tới `422`).
  > 🔴 **Ô nhập tiền phải VỌNG LẠI kết quả đã định dạng — thêm 2026-08-01 sau phản biện T3.** Chặn
  > dấu chấm/phẩy một cách im lặng là bẫy: chủ dán `100.000` (cách người Việt viết một trăm nghìn),
  > ô nuốt dấu chấm và còn `100000`… nhưng dán `100.000.000` thì thành `100000000` — đúng. Vấn đề
  > là `1.000,50` → `100050`. Nói chung: **xoá ký tự phân cách là một phép biến đổi thầm lặng trên
  > tiền của chủ**, và một lần lệch 10× trong sổ chi tiêu là mất niềm tin vào cả tính năng. Bắt
  > buộc: ngay dưới ô hiện dòng chữ lớn *"= 100.000 ₫"* cập nhật theo từng phím, lấy từ **đúng con
  > số sẽ gửi lên server** (không format lại từ chuỗi thô). Nhập rỗng ⇒ không hiện dòng nào, nút ghi
  > tắt. Đây là "nhìn thấy được" theo `forward-spec.md`, không phải trang trí.

  `list_amount` có và khác `amount` ⇒ hiện gạch ngang cạnh
  giá thực trả. **Không** làm toggle giá gốc/thực trả ở `011a` — nó cần `app_setting` mà repo chưa
  có CRUD cho bảng đó (`app_setting` hiện chỉ được `private_gate.py` dùng cho PIN + throttle), và
  một toggle với đúng một mặc định hợp lý chưa đáng một vòng round-trip. Đẩy sang `011c` cùng lúc
  dựng `app_setting` (§9).
- **Nghiệm thu bằng dữ liệu ác ý** (`ui-brief.md` §9(d) + `qa-framework.md` §5): tên tracker 70 ký
  tự không khoảng trắng · tiếng Việt 150 ký tự dấu dày · CHỮ HOA CÓ DẤU · emoji · toàn khoảng trắng
  (phải bị từ chối) · **và số tiền 14 chữ số** (`99999999999999` — kiểm nút/thẻ không vỡ, không
  tràn). Câu hỏi nghiệm thu là *"nó vỡ ở đâu"*, không phải *"nó có chạy không"*.

### 5.5 `data-testid`

`tracker-grid` · `tracker-button` · `tracker-last-seen` · `tracker-amount-input` ·
`tracker-form` · `tracker-archive` · `tracker-private-toggle` · `group-form` · `group-delete` ·
`entry-row` · `entry-edit` · `entry-undo` · `dashboard-panel` · `dashboard-f1-total` ·
`dashboard-f2-compare` · `dashboard-f3-group` · `dashboard-f4-top` · `dashboard-f5-net` ·
`dashboard-a2-gap` · `dashboard-a3-counts` · `dashboard-a4-trend`.
Id riêng đi bằng `data-tracker-id` / `data-entry-id`.

## 6. Không được làm

- Không tạo migration (§1). Không thêm cột. Không thêm index.
- Không chép nhánh mã-hoá-theo-cờ hay vũ điệu toggle của `notes.py` (§2.1).
- Không gọi `readable()`/`with_privacy_gate()` trực tiếp lên `Entry`/`Subscription` (§2.2).
- Không `SUM`/`ORDER BY`/so sánh số trong SQL trên `amount`/`list_amount` (§2.3).
- Không thêm unique index cho `tracker.name`, không dựng `name_hmac` (§2.4).
- Không chạm `subscription` — kể cả `entry.subscription_id` (để `null`, `011c` lo).
- Không chạm `reminder_time`/`reminder_text` — `011b` lo. Cột có sẵn nhưng `011a` không đọc, không
  ghi, không đưa ra DTO *(cùng loại với `note.embedding` ở `009`, `calendar_event.is_hidden` ở
  `010a`)*.
- Không seed dữ liệu mẫu (Q2 — thuộc `012`).
- Không làm streak / heatmap / run-rate / tổng tiết kiệm / insight AI (§3 mục 2, 3).
- Không thêm cột `position` cho tracker (§3 mục 4).
- Không hộp xác nhận cho thao tác ghi (§3 mục 1). Xoá **tracker** thì có xác nhận (kéo theo lịch sử,
  cùng lý lẽ `010a` §2 mục 5) — xoá **entry** thì không, đã có Hoàn tác.
- Không sửa file của `task`/`note`/`calendar` ngoài đúng khối tab trong `App.tsx`.

## 7. Nghiệm thu (Definition of Done)

1. `uv run ruff check` + `uv run pytest` xanh; `npm run build` + `npm run lint` xanh.
2. Test bắt buộc có, **mỗi bài phải chứng minh được biết đỏ** (bỏ luật ⇒ test đỏ):
   - `money.to_storage`/`from_storage` round-trip + biên (0, 14 chữ số, có phần lẻ ⇒ ném, âm ⇒ ném,
     chuỗi rác ⇒ ném).
   - Tạo tracker **công khai** ⇒ `tracker.name` trong DB bắt đầu bằng `enc:v1:` (§2.1 hệ quả 1).
   - Bật rồi tắt `is_private` ⇒ `name` **vẫn** là ciphertext và giải mã ra đúng chuỗi cũ (§2.1 hệ
     quả 2 — đây là bài chặn đúng cái bug im lặng nguy nhất của lô này).
   - Entry của tracker riêng tư **không** xuất hiện trong `list_entries` lẫn trong tổng F1 khi cổng
     khoá; xuất hiện lại khi mở (§2.2 + §4.3).
   - Tracker đã archive: **biến mất** khỏi `list_trackers`, nhưng entry của nó **vẫn** vào F1 (§4.3
     luật 2).
   - K8: ba `input_mode` × ba tổ hợp field sai ⇒ `422`, không phải `500`.
   - `unit`/`kind`×`group`: bốn đường vấp ở §4.2 bẫy 3–4 ⇒ `422`.
   - F2 cắt đúng khi tháng trước ngắn hơn (chạy với "hôm nay" = 31/03), **và** response mang
     `prev_period_truncated=true` + đúng `prev_period_days=28` (§4.3).
   - `PATCH {"kind": …}` đơn độc trên tracker đang có nhóm khác kind ⇒ `422`, **không** `500`
     (§4.2 bẫy 4).
   - `?month=` tháng quá khứ ⇒ `period_end` = cuối tháng đó và F1 là tổng cả tháng; `?month=` tháng
     tương lai ⇒ mọi số 0, `200` (§4.3).
   - Một dòng `entry.amount` ciphertext bị hỏng cố ý ⇒ dashboard vẫn `200`, `corrupted_entry_count=1`,
     các dòng còn lại cộng đúng; nhưng `GET /api/tracker/entry/{id}` của **chính** dòng đó thì `500`
     (§4.3).
   - Idempotent create: gửi hai lần cùng `id` ⇒ một dòng, lần hai trả `200`.
   - **Playwright:** nhấn giữ một tracker `event` ⇒ **đúng một** entry (§5.3 bẫy click tổng hợp).
   - **Playwright:** gõ `100000` vào ô tiền ⇒ dòng vọng hiện `100.000 ₫` (§5.4).
3. Migration: **không có** — thay vào đó dán output truy vấn `information_schema.columns` chứng minh
   4 bảng đã sẵn trên Neon (§1).
4. QA giao diện chạy theo `qa-framework.md` (T3 trước, T2 nếu T3 tắc — **không chạy ở T1**), viewport
   390×844, đủ ma trận trạng thái §4 của file đó, có phần (a) "đã soi những gì".
5. PR mô tả rõ mọi **judgment call** đã tự quyết trong lúc thi công (luật `feedback-t1-verify-not-refix`:
   T1 đọc hết mục này **trước** khi dọn dẹp theo trực giác).

## 8. Bốn mục chủ veto được (T1 tự quyết trong phiên viết spec, đổi chỉ tốn 1–2 dòng)

1. **Debounce 1,5 giây thay vì khoá suốt 10 giây toast** (§5.3) — thu hẹp cơ chế trong ngoặc của K9.
2. **Quét trùng tên TRONG cổng riêng tư**, chấp nhận trùng tên xuyên cổng (§2.4).
3. **Entry của tracker đã archive vẫn vào tổng tài chính** (§4.3 luật 2).
4. **Bỏ toggle giá gốc/thực trả khỏi `011a`**, đẩy sang `011c` cùng `app_setting` (§5.4).

> ✅ **T3 đã soi cả bốn mục này (2026-08-01) và tán thành cả bốn**, có nêu lý do riêng cho từng mục
> (đáng chú ý nhất: mục 3 — archive mà làm tụt tổng tháng trước thì F2 hỏng im lặng, đúng lập luận
> spec đưa ra). Ghi lại để phiên sau không tưởng đây là bốn chỗ chưa ai xem; **chủ vẫn veto được** —
> T3 là cố vấn, không phải người quyết.

## 9. Dàn ý `011c` (viết sau, đừng làm trong lô này)

> 📝 **2026-08-01 — `011c` đã được viết thành spec đầy đủ:**
> `agent-tasks/011c-subscription-renewal-settings.md`. Dàn ý dưới đây giữ nguyên làm dấu vết, nhưng
> **file kia mới là bản thi công**. Hai chỗ `011c` sẽ **sửa vào file của `011a`** — biết trước để
> lượt review sau không coi là vượt phạm vi:
> - `TrackerStore.update_tracker`: chặn đổi `input_mode` khỏi `money` (hoặc `kind` khỏi `finance`)
>   khi tracker còn subscription ⇒ `422`. Lý do: luồng gia hạn tạo `Entry` **có `amount`**, mà K8
>   (§4.2 bẫy 2) bắt entry khớp `input_mode` — không chặn thì mọi lần gia hạn `422` đúng lúc chủ vừa
>   trả tiền xong (`011c` §2.5).
> - `dashboard.py`: thêm ô `f6` vào response của `GET /api/tracker/dashboard` (`011c` §4.3). **F6 cố
>   ý KHÔNG đi theo `?month=`** — nó là ảnh chụp hiện tại, cùng họ với A2/A3/A4.

- Entity `subscription`: DTO + store, `name`/`amount` 🔐 **vô điều kiện**, `list_amount` nullable 🔐;
  `started_on`/`expires_on` là `DATE` (K14, ngoại lệ có chủ đích với B2 — **không** ép timestamptz).
- Trạng thái **suy ra**, không lưu: `active` / `đã huỷ còn hạn` / `hết hạn` từ (`expires_on`,
  `canceled_at`) — §11 đã chốt không có cột `status`.
- Luồng gia hạn theo S2: noti **chỉ để báo**, chủ trả tiền ở ngoài rồi mới vào app ghi — form
  default sẵn từ sub, tạo `entry` gắn `subscription_id`, đẩy `expires_on` thêm một chu kỳ.
  **Không** có nút "đã gia hạn" một chạm (chủ đã sửa đúng hướng này 2026-07-19).
- **F6** burn cố định/tháng: quy mọi `period_unit` về tháng, **chỉ đếm `auto_renew=true`**.
- `app_setting` CRUD tối thiểu + toggle hiển thị giá (§5.4) + ngưỡng "sắp hết hạn" 3 ngày mà `011b`
  §7 mục 3 đang chờ.
