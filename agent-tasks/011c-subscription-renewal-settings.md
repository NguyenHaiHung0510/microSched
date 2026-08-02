# 011c — `subscription` + luồng gia hạn + F6 + `app_setting` + seam định tuyến

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L2
> · Skill gợi ý: không cần · MCP cần: không cần.**
> **Trạng thái: DRAFT 2026-08-01 (T1 Opus 5 viết) — đã qua phản biện **T3** (`gemini-3.1-pro-high`,
> 9 finding) + **T2 Codex** (18 finding); T1 kiểm tay từng finding rồi vá, và ghi rõ chỗ nào kết luận
> đúng nhưng lý do sai (§8). **CHƯA được chủ duyệt — đừng giao thi công trước khi chủ duyệt.**

## 0. Bối cảnh — lô này nằm GIỮA, không phải cuối

`011` tách làm ba (`011a` §0). Thứ tự thi công **`011a` → `011c` (file này) → `011b`**:

- **`011a`** (đã viết) — `tracker_group`/`tracker`/`entry`, lưới ghi một chạm, dashboard A1–A4 +
  F1–F5. Là nền của mọi thứ dưới đây.
- **`011c`** (file này) — entity `subscription`, luồng gia hạn S2, **F6** (burn cố định/tháng),
  CRUD `app_setting` tối thiểu, và **seam định tuyến** (§5.1 — phát sinh khi rà, không có trong dàn
  ý gốc).
- **`011b`** (đã viết) — Web Push + cron 3 khe + nhắc thuốc + **nhắc sub sắp hết hạn**. Chạy cuối vì
  nửa sau của nó cần `subscription` tồn tại, cần ngưỡng "sắp hết hạn" trong `app_setting`
  (`011b` §7 mục 3), và cần một màn để notification mở ra.

**Ba món nợ có tên, `011c` là chủ nợ:**

| Nợ | Ai ghi | Trả ở đâu trong file này |
|---|---|---|
| Toggle giá gốc/thực trả (cần `app_setting`) | `011a` §5.4 + §8 mục 4 | §4.4 + §5.4 |
| Ngưỡng "sắp hết hạn 3 ngày" trong `app_setting` | `011b` §7 mục 3 | §4.4 |
| Màn để notification sub-expiry mở ra (`/subscription?highlight=id`) | `011b` §3.2 + §4.2 | §5.1 + §5.2 |

Phạm vi file này **dừng ở đó**: không push, không cron, không service worker — `011b` lo.

## 1. Sự thật đo được về schema — **`011c` KHÔNG có migration**

Đọc tay `backend/app/domain/models.py` + `backend/alembic/versions/0001_initial_schema.py` ngày
2026-08-01. Mọi thứ lô này cần **đã có sẵn**:

| Thứ | Dòng | Ghi chú |
|---|---|---|
| bảng `subscription` | `models.py:348-399` | đủ 15 cột theo `tracking-brief.md` §11; `__privacy_gate__ = VIA_PARENT`, `__delete_gate__ = APPLIES` |
| CHECK của nó | `models.py:353-368` | `name`/`amount` phải `enc:v1:%` (**vô điều kiện**) · `list_amount` null-hoặc-ciphertext · `period_count > 0` · `period_unit IN (day,week,month,year)` · `expires_on >= started_on` |
| `entry.subscription_id` | `models.py:432-439` | UUID NULL, FK `ON DELETE SET NULL` (K15) |
| bảng `app_setting` | `models.py:458-470` | `key` TEXT unique · `value` JSONB · `__privacy_gate__ = NONE`, `__delete_gate__ = NONE` |
| index | `models.py:571-572, 579` | `ix_subscription_tracker_id` · `ix_subscription_expires_on` (K16) · `ix_entry_subscription_id` |

⇒ **Không tạo file alembic nào trong `011c`.** Thấy "cần thêm cột" thì **dừng lại và hỏi** — nhiều
khả năng đang đi chệch một quyết định đã chốt ở `tracking-brief.md` §11, không phải schema thiếu.
Trước khi bắt đầu, xác minh trên Neon bằng `information_schema.columns` + `pg_constraint` (luật cứng
`CLAUDE.md`: không dừng ở `alembic current`).

**Không có unique index cho `subscription.name`** — đúng theo K19 (§2.6), không phải thiếu sót. Đừng
thêm.

## 2. Bảy chỗ sẽ SAI nếu chép khuôn `011a`/`notes.py` nguyên xi

### 2.1 🔴 `app_setting` là bảng **DÙNG CHUNG với cổng riêng tư** — CRUD tổng quát làm rò hash PIN

Đây là mục nguy hiểm nhất của cả lô, và nó **không nhìn thấy được** nếu chỉ đọc `tracking-brief.md`:
bảng `app_setting` trông như một bảng cấu hình vô hại, nhưng `private_gate.py:19-21` đã dùng nó cho
**ba key bí mật**:

| Key | Nội dung `value` | Rò ra thì sao |
|---|---|---|
| `private_pin` | `{"hash": <argon2id>, "bootstrap": bool}` (`private_gate.py:114-120`) | Hash của một **PIN 6 chữ số** — không gian 10⁶. Đẩy ra client là mời brute-force offline, bỏ qua toàn bộ throttle leo thang (ngưỡng 10/20/36 lần sai, khoá 5/8/18 phút — `private_gate.py:23`) đã dựng ở `016` |
| `private_unlock_throttle` | `{"fail_count": n, "locked_until": …}` | Ghi được = tự xoá lịch sử sai PIN |
| `private_unlock_ttl_minutes` | `{"value": n}` | Ghi được = tự nới TTL phiên riêng tư lên vô hạn |

Một `GET /api/settings` trả nguyên bảng, hoặc một `PATCH /api/settings/{key}` nhận key tuỳ ý, phá
đúng cái cửa mà `016` vừa đóng xong. Người viết code sẽ **không** thấy điều này: cả ba key nằm trong
một file khác (`private_gate.py`), không có comment nào trong `models.py` cảnh báo.

⇒ **Chốt: allowlist hằng số trong code, không bao giờ truy vấn theo key do client gửi.**

```python
# app/domain/settings.py
PUBLIC_SETTING_SPECS: Final[dict[str, SettingSpec]] = {...}   # đúng 2 key, §4.4

# Router chỉ được đọc/ghi key có trong PUBLIC_SETTING_SPECS.
# CẤM select(AppSetting) không kèm .where(AppSetting.key.in_(PUBLIC_SETTING_SPECS)).
```

Key ngoài allowlist ⇒ **`404` ở CẢ `GET` LẪN `PATCH`** — một luật, một mã, cho mọi key không nằm
trong allowlist, **không phân biệt** key đó có tồn tại thật trong bảng hay không. Bản nháp trước
dùng `422` cho `PATCH` (lý lẽ: payload sai); đổi sau phản biện T3 2026-08-01 vì hai mã cho cùng một
điều kiện là lời mời để người thi công sau "làm cho đúng ngữ nghĩa" và vô tình tách `private_pin`
(có thật) khỏi `key_bịa` (không có) thành hai phản hồi khác nhau. Một mã thì không có gì để tách.
Test bắt buộc, mỗi bài phải đỏ được khi gỡ luật:
`GET` danh sách **không** chứa ba key trên; `GET`/`PATCH` từng key trong ba key ⇒ **`404`** (không
phải `422` — `422` chỉ dành cho key hợp lệ mà giá trị sai) **và** giá trị trong DB không đổi một byte.

### 2.2 🔴 `subscription` đọc qua **cha** — `readable(stmt, Subscription, auth)` sẽ **ném lỗi**

`models.py:352`: `__privacy_gate__ = Gate.VIA_PARENT`; `reading.py:92-93` ném `ReadingGateError` khi
gặp `VIA_PARENT`. Cha là **`Tracker` qua `Subscription.tracker_id`** (`models.py:370-376`) — **không
phải `tracker_group`**. Khuôn đúng, chép nguyên xi:

```python
stmt = select(Subscription).join(Tracker, Subscription.tracker_id == Tracker.id)
stmt = readable(stmt, Tracker, auth)        # cổng riêng tư + xoá-mềm của CHA
stmt = not_deleted(stmt, Subscription)      # xoá-mềm của CHÍNH nó
```

Hệ quả không được quên: tracker cha riêng tư + cổng đang khoá ⇒ sub **biến mất hoàn toàn** (404 khi
đọc trực tiếp, vắng mặt trong danh sách, vắng mặt trong F6). Đó là **đúng**, và **không** được thêm
chú thích "một số mục đang ẩn" — cùng lý lẽ `011a` §4.3 (nói cho người ngó qua vai biết là có dữ
liệu riêng tư tồn tại).

### 2.3 🔴 Tiền của sub cũng là ciphertext (K20) — mọi phép cộng chạy ở Python

`subscription.amount`/`list_amount` mang CHECK `enc:v1:%` y như `entry` (`models.py:355-361`). Vì
thế:

- **Cấm** `func.sum(Subscription.amount)`, cấm `ORDER BY amount`, cấm mọi so sánh số trong SQL trên
  hai cột đó. Chạy được, ra rác (so chuỗi base64) — hỏng im lặng.
- Dùng lại **nguyên xi** `app/domain/money.py` của `011a` §4.1 (`to_storage` / `from_storage`).
  **Không** viết hàm định dạng thứ hai cho sub; hai bản khác nhau của cùng một hợp đồng chuỗi là mầm
  lệch round-trip.
- F6 kéo các sub đủ điều kiện về, `_clear()`, `from_storage()`, cộng bằng `Decimal` (§4.3).
- `started_on`/`expires_on` **là `DATE` trần** — so sánh/lọc trong SQL thì **được** (K14). Đừng gộp
  chung luật với tiền.

### 2.4 🔴 Gia hạn có **HAI** tác dụng, chỉ một cái tự idempotent

Luồng S2 làm hai việc trong một lượt: (a) tạo `entry` gắn `subscription_id`, (b) đẩy `expires_on`
thêm một chu kỳ. `011a` §4.2 bẫy 5 đã làm (a) idempotent theo id client (`ON CONFLICT DO NOTHING`).
**(b) thì không tự idempotent** — và hàng đợi offline gửi lại đúng một request đã thành công là
chuyện bình thường, không phải ngoại lệ.

Hỏng cụ thể: chủ gia hạn Netflix tháng 8, mạng chập, outbox gửi lại ⇒ **một** entry (đúng, nhờ
`ON CONFLICT`) nhưng `expires_on` nhảy **hai** tháng ⇒ tháng 9 không được nhắc, hết hạn im lặng.
Đúng loại lỗi mà tính năng này tồn tại để chặn.

⇒ **Chốt: buộc (b) vào kết quả thật của (a), trong CÙNG một transaction.**

```python
# Trong SubscriptionStore.renew(), một transaction.
# KHÔNG tự viết INSERT — gọi lại đúng đường tạo entry của 011a (xem hộp ngay dưới).
entry_id, created = await tracker_store.create_entry(
    db, payload, auth, subscription_id=subscription.id   # subscription_id là tham số TIN CẬY, không đến từ API
)
if not created:
    # Lần gửi lại: KHÔNG đẩy expires_on. Đọc lại qua cổng, trả 200 + trạng thái hiện tại.
    return await self._renew_result(db, subscription_id, created=False, auth=auth)
# Chỉ nhánh này mới được UPDATE subscription SET expires_on = ...
```

> 🔴 **Đừng nhân bản đường tạo entry — T2 bắt 2026-08-01.** Bản nháp trước viết thẳng
> `insert(Entry) … ON CONFLICT DO NOTHING` trong `renew`, và như thế là **chép lại bốn thứ** mà
> `011a` đã sở hữu: mã hoá tiền (`_sealed(money.to_storage(...))`), kiểm UUIDv7, ép `occurred_at`
> tz-aware, và luật K8 (`input_mode` × field). Bốn bản sao đó sẽ lệch ở lượt sửa đầu tiên. Tệ hơn:
> `011a` §4.2 bẫy 5 quy định conflict phải **đọc lại row qua cổng** rồi mới kết luận — trùng id
> nhưng thuộc bản ghi khác ⇒ `409`, không phải "retry". Coi mọi conflict là retry như bản nháp là
> **âm thầm nuốt một `409` thật**.
> ⇒ **`011a` phải xuất `create_entry` trả về `(entry_id, created: bool)` và nhận thêm keyword
> `subscription_id: UUID | None = None`** — tham số nội bộ, **không** có trong `EntryCreate` DTO,
> router của `011a` không bao giờ set (nó vẫn bị cấm chạm `subscription_id` theo `011a` §6). Chỉ
> `renew` truyền vào. Đây là chỗ thứ ba `011c` sửa file của `011a`, đã ghi vào §6.

Khoá hàng sub bằng `SELECT … FOR UPDATE` **trước** khi tính ngày mới (hai tab cùng bấm gia hạn).
Test bắt buộc: gửi **cùng một** `POST /renew` với cùng `entry_id` hai lần ⇒ đúng một `Entry`, và
`expires_on` chỉ tiến **một** chu kỳ.

### 2.5 🔴 Tracker cha của sub phải là `finance` + `money`, nếu không luồng gia hạn tự vấp K8

Luồng gia hạn tạo một `Entry` **có `amount`**. `011a` §4.2 bẫy 2 (K8) bắt entry phải khớp
`input_mode` của tracker: `event` ⇒ `amount` phải vắng ⇒ **`422`**. Nghĩa là nếu chủ lỡ gắn sub vào
một tracker `event` (ví dụ "Hút thuốc"), mọi lần gia hạn sẽ `422` — và nó nổ **đúng lúc chủ vừa trả
tiền xong**, chỗ tệ nhất để gặp lỗi.

⇒ **Chốt: chặn ở cửa vào, không để tới lúc gia hạn.** `POST`/`PATCH` subscription kiểm tracker cha
phải `kind='finance'` **và** `input_mode='money'`, sai ⇒ `422` với câu tiếng Việt chỉ đúng cách sửa
(*"Đăng ký phải gắn vào một tracker tài chính nhập số tiền — chọn tracker khác hoặc đổi kiểu nhập của
tracker này"*). Đối xứng với luật của `011b` §4.3 (tracker nhắc thuốc phải `health` + `event`).

**Hệ quả ngược cần chặn luôn:** `011a` cho `PATCH` đổi `input_mode` của tracker. Đổi một tracker
đang có sub từ `money` sang `event` là mở lại đúng cái bẫy trên bằng cửa sau. `011c` **mở rộng**
`TrackerStore.update_tracker`: nếu tracker còn ít nhất một `subscription` chưa xoá mềm thì đổi
`input_mode` khỏi `money` (hoặc `kind` khỏi `finance`) ⇒ `422`, kèm số lượng sub đang gắn.

> 🔴 **Hai cửa sau của chính guard này — T2 bắt 2026-08-01, cả hai đều thật:**
> 1. **Đường vòng qua `restore`.** Xoá mềm hết sub ⇒ guard hết đếm được ⇒ đổi tracker sang `event` ⇒
>    `POST /subscriptions/{id}/restore` khôi phục sub dưới một tracker nay đã sai kiểu. ⇒ `restore`
>    **phải validate lại `finance` + `money`** của tracker cha, sai ⇒ `422` chỉ đúng cách sửa. Rẻ hơn
>    là đếm cả sub đã xoá mềm trong guard, nhưng thế thì xoá sub xong vẫn không đổi được tracker mãi
>    mãi — chọn validate ở `restore`.
> 2. **Archive tracker còn sub sống** ⇒ ba lô hiểu khác nhau về cùng một hàng dữ liệu: `011a` cho
>    archive vô điều kiện · `011c` đọc qua `readable(…, Tracker, …)` nên **sub biến mất khỏi UI và
>    F6** · `011b` §3.4 mục 4 **không** lọc `Tracker.deleted_at` nên **vẫn bắn notification**, và
>    notification đó mở tới một màn trả 404. ⇒ **Chốt: `soft_delete_tracker` chặn khi tracker còn sub
>    chưa xoá mềm** (`422`, *"Còn N đăng ký đang gắn — xoá hoặc chuyển chúng trước"*). Cùng họ lý lẽ
>    với D1 (`RESTRICT` bảo vệ lịch sử), và là luật rẻ nhất vì nó áp một chỗ thay vì bắt cả ba lô
>    đồng bộ predicate. **`011b` không phải sửa gì** — điều kiện của nó tự đúng khi tracker không thể
>    archive lúc còn sub.

Đây là chỗ `011c` được phép sửa file của `011a`; danh sách đầy đủ ở §6.

### 2.6 Chống trùng tên: không có unique index, quét ở app — và quét **TRONG** cổng

K19 (`tracking-brief.md` §10, note 2026-07-20): AES-GCM nonce ngẫu nhiên ⇒ unique index trên
`lower(name)` của cột đã mã hoá **không bao giờ bắt được trùng**, nên `models.py` cố ý không khai.
Bảng `subscription` ăn đúng luật đó.

⇒ Chống trùng bằng decrypt-scan ở app lúc tạo/đổi tên, **và quét TRONG cổng riêng tư** — nhất quán
với quyết định đã chốt ở `011a` §2.4 (ưu tiên không-rò hơn không-trùng: trả `409` cho một hàng người
dùng không nhìn thấy vừa khó hiểu vừa rò). Phạm vi quét = các sub đọc được qua khuôn §2.2. Đua ghi
được chấp nhận (single-writer). **Đừng** thêm unique index, **đừng** dựng `name_hmac`.

### 2.7 Trạng thái là **suy ra**, và ba trạng thái không dùng thay nhau được

`tracking-brief.md` §11: **không cột `status`** — suy từ (`expires_on`, `canceled_at`), lưu riêng là
update-anomaly. Bảng chốt (tính theo **ngày Việt Nam**, `+07:00`, không phải UTC — cùng quy ước K14):

| Trạng thái | Điều kiện | F6 đếm? | `011b` nhắc? | Nút "Ghi gia hạn"? |
|---|---|---|---|---|
| `active` | `canceled_at IS NULL` và `expires_on >= today` | chỉ khi `auto_renew` | có, khi sắp hết hạn | có |
| `canceled` (đã huỷ, còn hạn) | `canceled_at IS NOT NULL` và `expires_on >= today` | **không** | **không** | có (huỷ rồi đổi ý) |
| `expired` | `expires_on < today` | **không** | **không** (`011b` §3.4 mục 4: `expires_on >= today`) | có |

Viết **một** hàm thuần `derive_status(expires_on, canceled_at, today)` trong `app/domain/subscription.py`
và dùng nó ở cả API lẫn F6. Ba chỗ tự suy lại bằng `if` rời rạc là cách chắc chắn để chúng lệch nhau
sau lượt sửa thứ hai. `SubscriptionRead` trả `status` như **field tính sẵn**, không phải cột.

## 3. Đã khoá — chép ra code, không mở lại

Nguồn: `tracking-brief.md` §11 + §8.2 (F6) + `ui-brief.md` + `qa-framework.md`. Có mâu thuẫn thì
brief thắng file này, báo lại T1.

1. **KHÔNG nút "đã gia hạn" một chạm** từ notification (S2 — chủ **sửa** đề xuất gốc 2026-07-19:
   *"cần xem xét + đánh giá + trả tiền rồi mới được coi là gia hạn"*). Noti chỉ **báo**; app chỉ
   **ghi nhận việc thật đã xảy ra ở ngoài**. Auto-write không confirm để dành AI Bước 2.
2. **Không cột `status`** (§2.7). Không thêm.
3. **`started_on`/`expires_on` là `DATE`** (K14) — ngoại lệ có chủ đích với B2, **không** ép
   timestamptz. `canceled_at` + timestamps vẫn timestamptz.
4. **`auto_renew` mặc định `false`** (amendment của chủ 2026-07-19: *"app là ghi lại thôi, quyết
   định thực tế ở ngoài"*). Đừng "tiện tay" bật mặc định.
5. **F6 chỉ đếm `auto_renew = true`** (`tracking-brief.md` §8.2) — món trả-trước-một-cục không phải
   burn cố định.
6. **VND-only** — chỉ `amount` + `list_amount`, không quy đổi tỷ giá.
7. **Không bảng price-history** — lịch sử giá thật chính là các `entry` gắn `subscription_id` (§11).
8. **Sub xoá mềm** (K10); tracker cha `ON DELETE RESTRICT` nên **không** xoá cứng tracker còn sub.
9. **Ranh giới sub vs entry thường** (S1): tiêu chí duy nhất = **có ngày hết hạn hay không**. Game
   pass / gói trả trước một cục ⇒ vẫn là sub (`auto_renew=false`). Mua đứt vĩnh viễn ⇒ `entry`
   thường. Đừng phát minh tiêu chí thứ hai.
10. **Luật UI cứng `ui-brief.md` §6** áp nguyên (không thẻ thô, không hardcode màu, không chiều cao
    cứng, chữ ≥12px, không tương tác chỉ-hover, light-only). Thiếu component thì `shadcn add` (§8 +
    4 cái bẫy), không viết tay.
11. **Chuẩn `data-testid`** `qa-framework.md` §6.3; id riêng đi bằng `data-subscription-id`.
12. **Không seed dữ liệu mẫu** (Q2 — data-migration Alembic lúc cutover = `012`). Màn phải dùng được
    từ DB rỗng.

## 4. Backend

### 4.1 `backend/app/domain/subscription.py` — DTO + `SubscriptionStore` (file mới)

Mirror **cấu trúc** `app/domain/tracker.py` của `011a` (DTO → exception → store; store không giữ
state, nhận `db: AsyncSession`, tham gia transaction của request). Dùng lại nguyên xi `_clear()` /
`_sealed()`, `require_uuidv7`, `reject_null_required_fields`, `PrivateWriteLocked` — **import, đừng
chép lần thứ ba**.

| DTO | Field | Ghi chú |
|---|---|---|
| `SubscriptionCreate` | `id: UUID\|None` · `name: str` · `tracker_id: UUID` · `amount: Decimal` · `list_amount: Decimal\|None` · `period_count: int = 1` · `period_unit: Literal["day","week","month","year"] = "month"` · `started_on: date` · `expires_on: date` · `auto_renew: bool = False` · `note_md: str\|None` | `name` strip rồi kiểm rỗng; `expires_on >= started_on` kiểm ở app **trước** khi chạm DB (câu tiếng Việt, không để CHECK ném `IntegrityError` → `500`) |
| `SubscriptionUpdate` | mọi field trên **trừ `id`, `tracker_id`** · thêm `canceled_at: datetime\|None` | **Cấm đổi `tracker_id`** — sub đã có entry gắn theo tracker cũ, reparent làm lệch F3/F6 lịch sử. Muốn đổi thì xoá mềm rồi tạo mới |
| `SubscriptionRead` | các cột + `status: Literal["active","canceled","expired"]` (§2.7) + `days_left: int` + `monthly_amount: Decimal\|None` (§4.3) + timestamps | tiền đã `from_storage()` ⇒ ra ngoài là **số**. `days_left` âm khi đã hết hạn — trả đúng số âm, UI tự diễn giải |
| `RenewRequest` | `entry_id: UUID\|None` · `amount: Decimal\|None` · `occurred_at: datetime\|None` · `new_expires_on: date\|None` · `note_md: str\|None` · **`clear_canceled: bool = False`** | mọi field vắng ⇒ lấy default từ sub (§4.2). `clear_canceled` = **quyết định của chủ**, không phải suy luận của server: ghi một lượt trả tiền cuối cho sub đã đánh dấu huỷ là chuyện có thật, và tự xoá `canceled_at` là app đoán ý — đúng thứ §3 mục 1 cấm |
| `RenewResult` | `subscription: SubscriptionRead` · `entry_id: UUID` · `created: bool` | `created=False` = lần gửi lại (§2.4) |

**Method:** `list_subscriptions(status?, tracker_id?)` · `get_subscription` · `create_subscription` ·
`update_subscription` · `cancel_subscription` (đặt `canceled_at`, **không** phải xoá) ·
`uncancel_subscription` · `soft_delete_subscription` · `restore_subscription` · `renew`.

Bẫy còn lại:

1. **Idempotent create theo id** (seam `008m`, khuôn `011a` §4.2 bẫy 5) — áp cho `subscription` y
   như ba bảng kia.
2. **`PrivateWriteLocked` ⇒ `403`** khi tracker cha riêng tư và cổng đang khoá? **Không** — cha
   không đọc được thì trả **`404`** (§2.2), đúng và không rò. Sub **không có** cờ `is_private` riêng;
   đừng thêm.
3. **Huỷ ≠ xoá.** `cancel_subscription` chỉ đặt `canceled_at = now()`; `DELETE` là soft-delete
   (`deleted_at`). Hai đường khác nhau, hai nút khác nhau, đừng gộp.
4. **`list_subscriptions` không phân trang** (vài chục dòng, cùng lý lẽ `011a` §4.2). Sắp mặc định:
   `active` trước (theo `expires_on` tăng dần — sắp hết hạn lên trên), rồi `canceled`, rồi `expired`.
   `expires_on` là DATE trần nên sắp **trong SQL** được, dùng `ix_subscription_expires_on`.

### 4.2 Luồng gia hạn — `POST /api/subscriptions/{id}/renew`

Một transaction, đúng thứ tự:

1. `SELECT … FOR UPDATE` hàng sub **qua cổng §2.2**; không thấy ⇒ `404`.
2. Kiểm tracker cha vẫn `finance` + `money` (§2.5); không ⇒ `422`.
3. Tính giá trị mặc định: `amount` ← `amount` hiện tại của sub; `occurred_at` ← `now()`;
   `entry_id` ← client gửi (outbox sinh UUIDv7) hoặc server sinh; `new_expires_on` ←
   `add_period(max(expires_on, today_vn), period_count, period_unit, anchor_day)` (chốt ngay dưới).
4. `INSERT … ON CONFLICT DO NOTHING RETURNING id` (§2.4). 0 dòng ⇒ trả `200`, `created=False`,
   **không** đụng `expires_on`.
5. Có dòng ⇒ `UPDATE subscription SET expires_on = new_expires_on` — và **`canceled_at` chỉ bị xoá
   khi payload gửi `clear_canceled=true`** (§4.1), không bao giờ tự động.
6. Trả `RenewResult`.

**Cộng chu kỳ — chốt cứng:** `day`/`week` cộng bằng `timedelta`; `month`/`year` cộng bằng **số
tháng** với luật cắt-cuối-tháng: 31/01 + 1 tháng = 28/02 (29/02 năm nhuận), **không** tràn sang
03/03. Hàm thuần `add_period(d: date, count: int, unit: str, anchor_day: int) -> date`, không dùng
`dateutil` (không có trong `pyproject.toml`; số học lịch ba dòng không đáng một dependency).

> 🔴 **`anchor_day` không phải trang trí — thiếu nó là mất ngày thanh toán, âm thầm, mỗi năm một
> ít (thêm 2026-08-01 sau phản biện T3).** Cộng dồn từ `expires_on` **đã bị cắt** thì mốc trôi một
> chiều và không bao giờ quay lại: 31/01 → 28/02 → **28/03** → 28/04… Sub tính tiền ngày 31 hàng
> tháng bị ghi nhận thành ngày 28 sau đúng hai lần gia hạn, và từ đó `011b` nhắc sớm 3 ngày mãi mãi.
> Không có test nào tự đỏ vì mỗi bước lẻ đều "đúng".
> ⇒ **`anchor_day = started_on.day`** (bất biến, không lấy từ `expires_on`). `add_period` cộng tháng
> rồi đặt ngày về `min(anchor_day, số ngày của tháng đích)`. Kết quả: 31/01 → 28/02 → **31/03**.
> Chỉ áp cho `month`/`year`; `day`/`week` không có khái niệm neo.

**Sub đã lapsed thì mốc mới tính từ HÔM NAY, không từ mốc cũ.** Sub hết hạn 3 tháng trước, chủ trả
tiền hôm nay ⇒ cộng từ `expires_on` cũ ra một ngày **vẫn ở quá khứ**: chủ vừa trả tiền xong mà app
vẫn báo `expired`, và `011b` không bao giờ nhắc lại. Vì thế mặc định lấy `max(expires_on, today_vn)`
— với sub còn hạn thì `max` chính là `expires_on`, không đổi gì, nên luật không-trôi ở trên vẫn giữ
nguyên. *(T3 xếp đây là CRITICAL; T1 đồng ý: §5.3 có hiện ngày mới trước khi bấm nên chủ **thấy**
được, nhưng một mặc định sai buộc chủ sửa tay mỗi lần là mặc định sai.)*

**`new_expires_on` client gửi lên thì server nhận** — validate `> expires_on` cũ **và**
`>= started_on`, sai ⇒ `422`. Ngoài mặc định `max(...)` ở trên, server **không** tự đuổi ngày thêm
lần nữa: app **ghi nhận** cái đã xảy ra, không đoán chủ đã trả mấy kỳ.

### 4.3 F6 — thêm vào `dashboard.py` của `011a`, **không** endpoint mới

F6 là một ô của cùng một dashboard (`tracking-brief.md` §8.2). Thêm vào response của
`GET /api/tracker/dashboard` (`011a` §4.3) — đây là chỗ thứ hai `011c` được sửa file của `011a`.

```
"f6": {
  "monthly_burn": Decimal,              # tổng burn cố định quy về tháng
  "subscription_count": int,            # số sub đang tính vào burn
  "upcoming": [ {subscription_id, name, amount: Decimal|null, monthly_amount: Decimal|null,
                 expires_on, days_left, corrupted: bool} ],   # null + corrupted=true: xem hộp dưới
  "corrupted_subscription_count": int   # cùng luật §4.3 của 011a
}
```

**Điều kiện vào burn** (tất cả phải đúng): `deleted_at IS NULL` · `canceled_at IS NULL` ·
`expires_on >= today_vn` · `auto_renew = true` · đọc được qua cổng §2.2.

**Quy về tháng — công thức chốt:** `monthly = amount / (số tháng của một chu kỳ)`, với

| `period_unit` | số tháng của chu kỳ |
|---|---|
| `month` | `period_count` |
| `year` | `period_count × 12` |
| `week` | `period_count × 7 / 30.4375` |
| `day` | `period_count / 30.4375` |

`30.4375 = 365.25 / 12`. Làm tròn **cuối cùng** về đồng nguyên, `ROUND_HALF_UP`, chỉ khi trả ra
ngoài — cộng bằng `Decimal` chưa làm tròn ở giữa. UI hiện `≈` trước số (§5.5): đây là **ước lượng**,
không phải sao kê, và nói thẳng ra thì rẻ hơn để chủ tự phát hiện lệch vài nghìn rồi mất tin.

> 🔴 **Hằng số phải là `Decimal("30.4375")`, không phải literal `30.4375` (thêm 2026-08-01 sau phản
> biện T3).** `amount` là `Decimal` sau `from_storage()`, và trong Python `Decimal / float` ném
> `TypeError` — không phải ra số sai, mà là **`500` cho cả dashboard** ngay khi tồn tại đúng một sub
> `week`/`day`. Khai `MONTH_DAYS: Final = Decimal("30.4375")` ở cấp module. Test bắt buộc phải có
> **một sub `period_unit='week'`** trong fixture F6, nếu không bài test xanh mà production đỏ.

**`upcoming`** = sub `active` có `days_left <= ngưỡng app_setting` (§4.4), sắp tăng dần theo
`expires_on`, tối đa 5 mục. Dùng **cùng một ngưỡng** với `011b` — hai con số khác nhau giữa màn hình
và notification là lỗi người dùng sẽ thấy ngay.

> 📝 **Sub hỏng ciphertext vẫn phải hiện trong `upcoming` (thêm 2026-08-01 sau phản biện T3).** Luật
> bỏ-qua-dòng-hỏng ở trên đúng cho **burn**, nhưng nếu áp luôn cho `upcoming` thì một sub sắp trừ
> tiền trong 2 ngày sẽ biến mất khỏi đúng cái danh sách sinh ra để cảnh báo nó — chủ chỉ thấy con số
> `corrupted_subscription_count = 1` mà không biết là khoản nào. ⇒ `upcoming` **giữ** mục đó với
> `amount: null` + `corrupted: true`; UI hiện tên + ngày hết hạn và thay chỗ số tiền bằng *"không đọc
> được"*. Tên vẫn giải mã được (`name` và `amount` là hai lần mã hoá độc lập); tên **cũng** hỏng thì
> mới bỏ mục đó.

**Ba luật chung của tầng dashboard (`011a` §4.3) áp nguyên cho F6:** riêng tư khoá ⇒ số thiếu và
không chú thích · tháng rỗng ⇒ `200` với số 0 · một dòng ciphertext hỏng ⇒ bỏ dòng đó **khỏi phép
cộng burn** (không phải khỏi cả response — nó vẫn ở `upcoming` với `corrupted: true` nếu tên còn đọc
được) + `logger.error` kèm `subscription.id` (**không** kèm ciphertext) + đếm vào
`corrupted_subscription_count`, **không** hạ cả dashboard.

⚠️ **F6 không đi theo `?month=`.** F1–F5 nhìn về quá khứ theo tháng được chọn; F6 trả lời *"mỗi tháng
tôi mất cố định bao nhiêu **từ giờ trở đi**"* — nó là ảnh chụp hiện tại. Xem lại tháng 6 vẫn thấy F6
của hôm nay. Cùng họ lý lẽ với A2/A3/A4 trong `011a` §4.3 (bám hôm nay, không bám `month`). Ghi vào
docstring, nếu không lượt review sau sẽ "sửa cho đồng nhất".

### 4.4 `backend/app/domain/settings.py` — `app_setting` có allowlist (file mới)

Đúng **hai** key ở `011c`. Quy ước `value` = `{"value": <scalar>}`, mirror
`private_gate.py:189-194` (kể cả cái bẫy nhỏ ở đó: `isinstance(value, bool)` phải bị loại khi kiểm
`int`, vì `True` là `int` trong Python).

| Key | Kiểu | Mặc định | Biên | Ai dùng |
|---|---|---|---|---|
| `subscription_expiry_lead_days` | int | `3` | `0 ≤ n ≤ 30` | F6 `upcoming` (§4.3) + cron nhắc sub của `011b` §3.4 mục 4 |
| `show_list_price` | bool | `true` | — | UI hiện/ẩn giá niêm yết gạch ngang (`011a` §5.4, §8 mục 4) |

- **Hàng vắng ⇒ dùng mặc định**, không phải lỗi (khuôn `_ttl_minutes`). Không seed lúc khởi động;
  ghi lần đầu bằng `INSERT … ON CONFLICT DO UPDATE`.
- **Giá trị sai kiểu/ngoài biên trong DB ⇒ ném ồn ào** ở đường đọc của settings (dữ liệu hỏng, không
  đoán) — nhưng **cron của `011b` phải chịu được**: `011b` đọc ngưỡng qua một hàm
  `expiry_lead_days(db)` trả **mặc định 3 + `logger.error`** nếu hàng hỏng, chứ không để một dòng
  JSON sai làm chết lượt nhắc thuốc buổi sáng. Hai đường, hai cách xử — viết rõ vào docstring.
- Allowlist §2.1 là **luật cứng** của file này.

### 4.5 Router

`backend/app/web/routers/subscription.py` + `settings.py`, cả hai đăng ký **dưới `protected_api`**
(`main.py:87-91` — đọc file thật, đừng đoán tên biến). Mirror `routers/notes.py`: `Database` /
`CurrentSession` alias, `_not_found()`.

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/api/subscriptions` | envelope `{"items": [...]}`; query `status?`, `tracker_id?`; không phân trang |
| GET | `/api/subscriptions/{id}` | `404` qua cổng |
| POST | `/api/subscriptions` | `201` mới / `200` trùng id; `409` trùng tên (quét trong cổng, §2.6); `422` tracker cha sai kiểu (§2.5); `404` tracker cha không đọc được |
| PATCH | `/api/subscriptions/{id}` | không đổi `tracker_id`; `422` `expires_on < started_on` |
| POST | `/api/subscriptions/{id}/cancel` | đặt `canceled_at`; `200` + bản ghi mới |
| POST | `/api/subscriptions/{id}/uncancel` | `canceled_at = NULL` |
| POST | `/api/subscriptions/{id}/renew` | §4.2; `200` cho cả lần đầu lẫn lần gửi lại (`created` phân biệt) |
| DELETE | `/api/subscriptions/{id}` | `204`, **soft-delete** |
| POST | `/api/subscriptions/{id}/restore` | khuôn `notes.py:98-104` |
| GET | `/api/settings` | **chỉ** key trong allowlist, kèm giá trị hiệu lực (đã áp mặc định) |
| GET | `/api/settings/{key}` | `404` cho mọi key ngoài allowlist |
| PATCH | `/api/settings/{key}` | `404` cho mọi key ngoài allowlist (§2.1 — cùng mã với GET); `422` chỉ khi key **hợp lệ** mà giá trị sai kiểu hoặc ngoài biên |

`datetime` naive bị từ chối `422` ở `occurred_at`/`canceled_at` (cùng luật `011a` §4.4). `date` thì
nhận `YYYY-MM-DD` trần — nó là ngày lịch, không có múi giờ (K14).

## 5. Frontend

### 5.1 🔴 Seam định tuyến — app **CHƯA có router**, và `011b` đã giả định là có

Đo tay 2026-08-01: `frontend/src/App.tsx:70` khai `activeScreen` bằng `useState` (khối tab ở
`104-125`, nhánh render ở `127`), và `frontend/package.json` **không có `react-router`**. Trong
khi đó `011b` §3.2 + §4.2 viết payload push mang URL `/reminder-confirm?dispatch=…` và *"URL mở màn
subscription/highlight=id"* — **hai deep link vào một ứng dụng không có đường dẫn nào**. Không spec
nào nhận phần dựng đường đi đó; nó rơi đúng vào khe giữa `011a` (không cần route) và `011b` (cần,
nhưng giả định đã có).

`011c` nhận, vì nó ship trước `011b` và sở hữu chính cái màn mà notification phải mở.

**Chốt: seam tối thiểu tự viết, KHÔNG thêm `react-router`.**

- `frontend/src/lib/route.ts` (~40 dòng): `useLocation()` đọc **`pathname + search`** (một chuỗi,
  không phải riêng `pathname`) + `useSyncExternalStore` trên `popstate`; `navigate(path)` gọi
  `history.pushState` rồi phát `popstate`. Đọc query bằng `URLSearchParams` sẵn có.
  > 🔴 **Snapshot phải gồm cả `search` — T2 bắt 2026-08-01.** Cả hai deep link mang tham số trong
  > query (`?highlight=`, `?dispatch=`). Nếu snapshot chỉ là `pathname` thì đi từ `/subscription`
  > sang `/subscription?highlight=id` cho ra **cùng một giá trị**, `useSyncExternalStore` coi là
  > không đổi và **không rerender** — notification thứ hai trỏ sang sub khác sẽ không làm gì cả.
  > Lỗi này không lộ ra ở lần tap đầu tiên (lúc đó là tải nguội), chỉ lộ khi app đang mở.
- `App.tsx` rẽ **hai** nhánh: `/subscription` ⇒ `SubscriptionScreen`; còn lại ⇒ khối tab hiện có
  (mọi tab giữ nguyên URL `/`, đừng đổi hành vi tab đang chạy tốt).
- **Tab cố ý KHÔNG sở hữu URL.** Chỉ hai deep link có path riêng; `activeScreen` vẫn là `useState`
  như hiện nay. Đừng "làm cho đồng nhất" bằng cách đẩy cả 4 tab vào path — đó là viết lại điều hướng
  của ba lô đã chạy tốt, ngoài phạm vi `011c`.
  > 📝 **Hệ quả phải xử, không được bỏ lửng (T3 nêu 2026-08-01, T1 thu hẹp lại):** T3 cảnh báo
  > `activeScreen` sẽ "lệch pha" với lịch sử trình duyệt. Kiểm tay thì kịch bản T3 mô tả **không xảy
  > ra** — `activeScreen` luôn có giá trị hợp lệ nên không có màn trắng, và Back từ `/subscription`
  > về `/` trả đúng tab đang mở. Nhưng có một trường hợp **thật** ở gần đó: **tải nguội**
  > `/subscription` từ notification thì không có mục lịch sử nào phía trước. ⇒ Nút quay lại trong màn
  > **phải** gọi `navigate('/')`, **không** `history.back()` (back sẽ rơi ra ngoài app). Playwright
  > phải phủ đúng đường này: mở thẳng `/subscription`, bấm quay lại, khẳng định đang ở khối tab.
- Lý do không dùng `react-router`: một dependency runtime mới cho đúng hai đường dẫn, trong một app
  một-người-dùng, đi ngược quy ước supply-chain npm ở `frontend-brief.md`. Cửa nâng cấp để mở: khi
  có deep link thứ tư, đổi seam này sang `react-router` là việc một buổi.
- **Tải nguội không 404**: backend đã có `SPAStaticFiles` trả `index.html` cho path không khớp file
  (`main.py:28-37, 102`) — đã kiểm, không phải giả định. `011b` §4.1 đổi sang `injectManifest` thì
  phải giữ `navigateFallbackDenylist` như cũ; nếu vỡ, deep link chết chung với nút đăng nhập.

**Đây là hợp đồng `011b` dựa vào** — chép sang §9.

### 5.2 Màn `SubscriptionScreen` — vào từ tab Tracker, **không** thêm tab thứ năm

Thanh tab sẽ có `Task` · `Ghi chú` · `Lịch` (010a) · `Tracker` (011a). Tab thứ năm trên màn 390px là
vỡ; sub cũng không phải thứ mở hàng ngày như lưới ghi.

- Đường vào: một nút/hàng trong `TrackerScreen` (khối tài chính) — *"Đăng ký · N khoản"*, bấm ⇒
  `navigate('/subscription')`. Có nút quay lại rõ ràng.
- `?highlight=<id>`: cuộn tới thẻ đó + viền nhấn ~2 giây rồi tắt. **Không tự mở dialog, không tự mở
  form gia hạn** — tap một notification trên màn khoá mà app tự mở form ghi tiền là thao tác ngoài ý
  muốn; S2 nói rõ chủ phải *xem xét* trước.
- `id` không tồn tại / không đọc được (riêng tư đang khoá) ⇒ hiện danh sách bình thường, **không**
  báo lỗi "không tìm thấy đăng ký X" (rò sự tồn tại). Cùng lý lẽ §2.2.
- Danh sách nhóm theo `status` (§2.7), mỗi thẻ: tên · số tiền/chu kỳ · `expires_on` + `days_left` ·
  chip trạng thái · `auto_renew`. Empty state có đường tạo mới (DB rỗng phải dùng được).

### 5.3 Form gia hạn — "xem trước rồi mới bấm"

Mở từ nút **Ghi gia hạn** trên thẻ. Default sẵn từ sub, mọi ô sửa được: số tiền (giá đổi thì sửa) ·
ngày trả · **ngày hết hạn mới** (hiện sẵn kết quả `add_period`, sửa được) · ghi chú.

Ngay trên nút xác nhận, một dòng tóm tắt bằng chữ: *"Ghi 260.000 ₫ vào Sub AI · hết hạn mới:
15/09/2026"*. Đây là "nhìn thấy được" theo `forward-spec.md` — luồng này ghi tiền **và** dời một cột
mốc; cả hai phải đọc được trước khi bấm.

- `entry_id` sinh ở client bằng UUIDv7 (seam `008m`) và **giữ nguyên khi bấm lại sau lỗi mạng** —
  đây là nửa client của §2.4. Sinh id mới ở lần retry là tự phá idempotency.
- Nút xác nhận khoá từ lúc bấm tới khi mutation settle (khuôn debounce `011a` §5.3).
- Thành công ⇒ toast, đóng form, cập nhật thẻ. **Không** toast Hoàn tác 10 giây ở đây: hoàn tác một
  lượt gia hạn phải lùi cả `expires_on`, và đó là một endpoint chưa có. Sửa nhầm thì sửa entry
  (`011a`) + sửa `expires_on` (form sửa sub) — hai thao tác nhìn thấy được, đúng tinh thần S2.

### 5.4 Hai món nợ cấu hình

- **Toggle giá gốc** (`show_list_price`, nợ từ `011a` §5.4): bật ⇒ chỗ nào có `list_amount` khác
  `amount` thì hiện giá niêm yết gạch ngang cạnh giá thực trả (cả thẻ sub lẫn danh sách entry của
  `011a`); tắt ⇒ chỉ giá thực trả. Đặt trong một khối "Cài đặt" nhỏ ngay trong `SubscriptionScreen` —
  **không** dựng màn Settings riêng ở lô này (hai key thì chưa đáng).
- **Ngưỡng sắp hết hạn** (`subscription_expiry_lead_days`): ô số 0–30 cùng khối, đổi ⇒ F6
  `upcoming` đổi theo ngay (invalidate query dashboard).

### 5.5 Tiền, ngày, microcopy, dữ liệu ác ý

- Tiền: **dùng lại nguyên xi** ô nhập tiền của `011a` §5.4 — kể cả **dòng vọng lại** *"= 260.000 ₫"*
  cập nhật theo từng phím. Đừng viết ô thứ hai.
- Ngày: `<input type="date">` (không phải `datetime-local`) — `started_on`/`expires_on` là DATE, gửi
  `YYYY-MM-DD` trần, **không** nối `+07:00`, **không** `toISOString()`. Đây là chỗ khác `011a` và
  executor rất dễ chép nhầm luật.
- Hiển thị ngày: `Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })`. **`days_left` lấy
  thẳng từ `SubscriptionRead` của server, frontend KHÔNG tính lại** — server đã cắt biên theo giờ VN
  (§4.1), tính lại bằng `new Date()` của thiết bị là dựng chỗ thứ hai định nghĩa "hôm nay" và hai
  chỗ đó lệch nhau đúng quanh nửa đêm (sửa 2026-08-01 sau phản biện T3: bản nháp trước bảo tính lại
  ở client, mâu thuẫn với chính §4.1).
- F6: `≈ 1.240.000 ₫/tháng` — giữ dấu `≈` (§4.3). `monthly_burn = 0` ⇒ *"Chưa có khoản cố định
  nào"*, không phải `≈ 0 ₫`.
- `corrupted_subscription_count > 0` ⇒ dải cảnh báo *"N bản ghi không đọc được — số liệu có thể
  thiếu"* (khuôn `011a`).
- **Nghiệm thu bằng dữ liệu ác ý** (`ui-brief.md` §9(d) + `qa-framework.md` §5): tên sub 70 ký tự
  không khoảng trắng · tiếng Việt 150 ký tự dấu dày · emoji · toàn khoảng trắng (phải bị từ chối) ·
  `amount` 14 chữ số · `period_count = 999` · sub hết hạn 400 ngày trước (`days_left` âm lớn, thẻ
  không vỡ).

### 5.6 `data-testid`

`subscription-screen` · `subscription-card` · `subscription-status` · `subscription-form` ·
`subscription-renew` · `subscription-renew-form` · `subscription-renew-summary` ·
`subscription-cancel` · `subscription-empty` · `dashboard-f6-burn` · `dashboard-f6-upcoming` ·
`settings-list-price-toggle` · `settings-expiry-lead-days`.
Id riêng đi bằng `data-subscription-id`.

## 6. Không được làm

- Không tạo migration, không thêm cột, không thêm index (§1).
- Không thêm unique index cho `subscription.name`, không dựng `name_hmac` (§2.6).
- Không `SUM`/`ORDER BY`/so sánh số trong SQL trên `amount`/`list_amount` (§2.3).
- Không gọi `readable()` trực tiếp lên `Subscription` (§2.2).
- **Không đọc/ghi `app_setting` ngoài allowlist** — tuyệt đối không chạm `private_pin`,
  `private_unlock_throttle`, `private_unlock_ttl_minutes` (§2.1).
- Không thêm **cột DB** `status` (§2.7). Field `status` **tính sẵn** trong `SubscriptionRead` thì
  ngược lại là **bắt buộc** — đừng đọc mục này thành "cấm luôn field DTO" (T2 bắt 2026-08-01).
- Không làm nút "đã gia hạn" một chạm, không auto-write từ notification (§3 mục 1).
- Không chạm `push_subscription` / `reminder_dispatch` / service worker / cron — `011b` lo. Không
  gửi notification từ lô này.
- Không chạm `reminder_time`/`reminder_text` của tracker (`011b`).
- Không thêm tab thứ năm (§5.2). Không dựng màn Settings riêng (§5.4).
- Không thêm `react-router` hay bất kỳ dependency runtime mới nào (§5.1).
- Không seed dữ liệu mẫu (§3 mục 12).
- Không sửa file của `task`/`note`/`calendar`.
- **Danh sách đầy đủ file của `011a` mà `011c` được sửa** (T2 bắt 2026-08-01: bản nháp trước chỉ
  liệt kê hai chỗ backend trong khi §5 lại yêu cầu sửa cả frontend — spec tự cấm thứ chính nó bắt
  làm). Ngoài danh sách này thì không:
  | File | Sửa gì |
  |---|---|
  | `app/domain/tracker.py` | guard `update_tracker` + chặn `soft_delete_tracker` khi còn sub (§2.5); `create_entry` trả `(entry_id, created)` + nhận keyword nội bộ `subscription_id` (§2.4) |
  | `app/domain/dashboard.py` | thêm ô `f6` (§4.3) |
  | `frontend/src/App.tsx` | thêm nhánh path `/subscription` (§5.1) — **không** đổi cơ chế tab |
  | `TrackerScreen.tsx` | thêm đúng một đường vào màn sub (§5.2) |
  | danh sách entry của `011a` | áp `show_list_price` (§5.4) |
  | `MoneyInput` (component dùng chung của `011a`) | **chỉ import, không sửa** (§5.5) |

## 7. Nghiệm thu (Definition of Done)

1. `uv run ruff check` + `uv run pytest` xanh; `npm run build` + `npm run lint` xanh.
2. Test bắt buộc, **mỗi bài phải chứng minh được biết đỏ** (gỡ luật ⇒ test đỏ):
   - **Allowlist settings:** `GET /api/settings` không chứa `private_pin` /
     `private_unlock_throttle` / `private_unlock_ttl_minutes`; `GET` **và** `PATCH` từng key đó ⇒
     `404` (cùng một mã, §2.1) và giá trị DB **không đổi** (so byte trước/sau); `GET`/`PATCH` một key
     bịa hoàn toàn ⇒ **`404` giống hệt**, không phân biệt được với ba key trên. Bài này là bài quan
     trọng nhất lô.
   - **Gia hạn idempotent:** hai `POST /renew` cùng `entry_id` ⇒ đúng một `Entry`, `expires_on` tiến
     đúng **một** chu kỳ, lần hai trả `created=false` (§2.4).
   - **`add_period` biên:** 31/01 +1 tháng ⇒ 28/02 (và 29/02 năm nhuận) · 31/12 +1 năm ⇒ 31/12 năm
     sau · `week`/`day` cộng đúng.
   - **`add_period` DÂY CHUYỀN (bài bắt trôi mốc, §4.2):** `anchor_day=31`, gia hạn ba lần liên tiếp
     từ 31/01 ⇒ **28/02 → 31/03 → 30/04**, không phải 28/02 → 28/03 → 28/04. Bỏ `anchor_day` đi thì
     bài này phải đỏ; các bài một-bước ở trên **vẫn xanh** — đó chính là lý do phải có bài này.
   - **Sub đã lapsed:** `expires_on` cách đây 3 tháng, `POST /renew` không gửi `new_expires_on` ⇒
     mốc mới **ở tương lai** và `status` trả về là `active`, không phải `expired` (§4.2).
   - **`clear_canceled`:** gia hạn một sub đang `canceled` mà **không** gửi cờ ⇒ `canceled_at` giữ
     nguyên; gửi `clear_canceled=true` ⇒ mới bị xoá (§4.1).
   - **F6 có sub `period_unit='week'` trong fixture** ⇒ dashboard `200` và burn đúng tới đồng. Bài
     này chặn đúng bẫy `Decimal / float` ném `TypeError` (§4.3); fixture chỉ có `month` thì bẫy lọt.
   - **Sub hỏng ciphertext `amount` nhưng sắp hết hạn** ⇒ vẫn có mặt trong `f6.upcoming` với
     `amount: null` + `corrupted: true`, **và** vẫn đếm vào `corrupted_subscription_count` (§4.3).
   - **Tracker cha sai kiểu:** tạo sub trên tracker `event` ⇒ `422`, không `500`; và `PATCH`
     `input_mode` của tracker **đang có sub** khỏi `money` ⇒ `422` (§2.5).
   - **Trạng thái suy ra:** ba tổ hợp (`canceled_at`, `expires_on`) ⇒ đúng ba `status`; sub `expired`
     và sub `canceled` **không** vào `monthly_burn`.
   - **F6:** `auto_renew=false` không vào burn · quy đổi `year`/`week`/`day` đúng tới đồng ·
     `?month=` tháng quá khứ **không** đổi F6 (§4.3).
   - **Riêng tư:** sub dưới tracker riêng tư biến mất khỏi list + F6 khi cổng khoá, hiện lại khi mở;
     `?highlight=<id>` của sub đó **không** làm lộ tên (§5.2).
   - **Ciphertext hỏng:** một dòng `subscription.amount` hỏng cố ý ⇒ dashboard vẫn `200`,
     `corrupted_subscription_count=1`, các dòng còn lại cộng đúng.
   - **Idempotent create** theo id: gửi hai lần cùng `id` ⇒ một dòng, lần hai `200`.
   - **Playwright:** mở `/subscription?highlight=<id>` ⇒ đúng thẻ đó được cuộn tới + nhấn viền, và
     **không** có dialog nào tự mở (§5.2).
   - **Playwright:** tải nguội thẳng `/subscription` (không đi qua tab) rồi bấm nút quay lại ⇒ về
     khối tab, **không** rơi ra ngoài app (§5.1 — `navigate('/')`, không phải `history.back()`).
   - **Playwright:** form gia hạn hiện đúng dòng tóm tắt (số tiền đã định dạng + ngày hết hạn mới)
     trước khi bấm (§5.3).
3. Migration: **không có** — dán output `information_schema.columns` chứng minh `subscription` +
   `app_setting` đã sẵn trên Neon (§1).
4. QA giao diện theo `qa-framework.md` (T3 trước, T2 nếu T3 tắc — **không chạy ở T1**), viewport
   390×844, đủ ma trận trạng thái §4 của file đó, có phần (a) "đã soi những gì".
5. PR mô tả rõ mọi **judgment call** tự quyết lúc thi công (luật `feedback-t1-verify-not-refix`).

## 8. Chín mục chủ veto được (T1 tự quyết lúc viết spec, đổi chỉ tốn 1–2 dòng)

1. **Tracker cha của sub bắt buộc `finance` + `money`** (§2.5) — chặt hơn `tracking-brief.md` §11
   (chỉ nói "phải mang `tracker_id`"). Đổi = bỏ ràng buộc và chấp nhận `422` lúc gia hạn.
2. **`30.4375` ngày/tháng cho quy đổi `day`/`week`** (§4.3) — thay bằng 30 cho tròn cũng được, lệch
   ~1,4%.
3. **F6 không đi theo `?month=`** (§4.3) — nó là ảnh chụp hiện tại, không phải số liệu tháng.
4. **Seam định tuyến tự viết thay vì `react-router`** (§5.1).
5. **Sub vào từ tab Tracker, không phải tab thứ năm** (§5.2).
6. **Không có toast Hoàn tác cho lượt gia hạn** (§5.3) — vì hoàn tác phải lùi cả `expires_on`.
7. **`anchor_day = started_on.day`** cho cộng tháng/năm (§4.2) — chấp nhận `expires_on` "nhảy" từ
   28/02 lên 31/03. Bỏ neo thì mốc trôi một chiều; đổi neo sang một cột riêng thì cần migration.
8. **Sub lapsed thì mặc định tính từ hôm nay** (`max(expires_on, today_vn)`, §4.2) — chỗ duy nhất
   server "đoán" thay chủ, và nó chỉ kích hoạt khi mốc cũ đã ở quá khứ.
9. **`clear_canceled` mặc định `false`** (§4.1) — ghi một lượt trả tiền không tự bỏ đánh dấu đã huỷ.

> ✅ **T3 (`gemini-3.1-pro-high`) đã soi bản đầu 2026-08-01: 9 finding, T1 kiểm tay từng cái.**
> Nhận 8 (mục 1/2/3 CRITICAL đều thật: trôi mốc thanh toán · `Decimal / float` ném `TypeError` làm
> `500` cả dashboard · sub lapsed gia hạn xong vẫn `expired`; cộng 4 mục MAJOR/MINOR — sub hỏng bị
> giấu khỏi `upcoming`, tự xoá `canceled_at`, `days_left` tính hai nơi, thiếu bài test dây chuyền).
> **Một mục lập luận sai:** T3 cho rằng `404` ở GET vs `422` ở PATCH tạo "oracle" phân biệt
> `private_pin` với key bịa — không đúng, bản nháp trả `422` cho **mọi** key ngoài allowlist nên
> không có gì để phân biệt. Vẫn gộp về một mã `404` (§2.1) vì lý do khác: hai mã cho cùng một điều
> kiện là chỗ để lượt sửa sau vô tình tách ra. Ghi lại cả hai vế — đúng dạng lỗi `qa-framework.md`
> §8 (**kết luận dùng được, trích dẫn sai**), không được để lời giải thích sai đi kèm bản vá đúng.

> ✅ **T2 Codex (`gpt-5.6-sol`) review chéo với repo thật, 2026-08-01: 18 finding.** Lane này đọc
> được code nên bắt đúng loại T3 không bắt được. Bốn cái đáng nhất, T1 đã kiểm tay từng cái rồi vá:
> - **`navigateFallbackDenylist` không tồn tại dưới `injectManifest`** — option đó thuộc
>   `GeneratePartial` (`workbox-build/build/types.d.ts:286`), còn `InjectManifestOptions`
>   (`types.d.ts:487`) không gồm partial đó. `011b` §4.1 bảo "giữ nguyên" một thứ **không giữ được**,
>   và mất nó là `/auth/*` bị service worker nuốt — đúng sự cố nút đăng nhập câm ghi trong
>   `vite.config.ts`. Vá ở `011b`: chuyển sang `NavigationRoute` viết tay trong `sw.ts`.
> - **`return_to` chưa tồn tại ở đâu cả** (`App.tsx:59` trỏ `/auth/login` cứng, `auth.py:148` luôn
>   redirect `/`) — noti lúc session hết hạn sẽ **nuốt mất lượt nhắc thuốc**. Giao `011b`, kèm luật
>   chống open-redirect.
> - **Archive tracker còn sub** ⇒ ba lô hiểu khác nhau về cùng một hàng: `011a` cho archive ·
>   `011c` làm sub biến mất khỏi UI/F6 · `011b` vẫn bắn noti tới màn trả 404. Vá bằng một luật ở
>   `soft_delete_tracker` (§2.5) thay vì bắt ba lô đồng bộ predicate.
> - **`renew` tự viết `INSERT Entry`** = nhân bản mã hoá/UUIDv7/timezone/K8 của `011a` **và** nuốt
>   mất `409` thật. Vá: dùng lại `create_entry` của `011a` (§2.4).
>
> Cộng thêm: mâu thuẫn nội bộ về API settings, `status` bị chính §6 cấm, phạm vi sửa file frontend
> không khai, `usePath` không thấy đổi query, schema `upcoming` chưa khớp luật corrupted, và bốn
> **sai số thật trong chính spec này** (throttle `016` là *ngưỡng 10/20/36 lần, khoá 5/8/18 phút* chứ
> không phải "10/20/36 phút" — con số này còn đang sai trong `CLAUDE.md`; `subscription` có 15 cột
> không phải 14; hai dải dòng `models.py` lệch; `App.tsx` khai `useState` ở dòng 70). Tất cả đã sửa.

## 9. Hợp đồng `011c` → `011b` (đừng đổi khi thi công mà không sửa `011b`)

`011b` được viết **trước** file này và đã giả định sẵn bốn thứ. Đổi thì phải sửa `011b` cùng lượt:

1. **Route `/subscription?highlight=<id>`** tồn tại và mở đúng thẻ (§5.1, §5.2) — `011b` §3.2
   `build_subscription_payload` dựng đúng URL này.
2. **Ngưỡng `subscription_expiry_lead_days` trong `app_setting`**, mặc định 3, đọc qua
   `expiry_lead_days(db)` **chịu được hàng hỏng** (§4.4) — `011b` §3.4 mục 4 dùng để lọc
   `expires_on - today <= ngưỡng`.
3. **Cách suy `status`** (§2.7): `011b` nhắc **chỉ** sub `canceled_at IS NULL` **và**
   `expires_on >= today`. Dùng chung `derive_status`, không viết lại điều kiện.
4. **Seam định tuyến** (§5.1) là chỗ `011b` §4.2 gắn route `/reminder-confirm`. `011b` **không** phải
   dựng router, chỉ thêm một nhánh.

> 📌 Hai lỗ hổng phát hiện lúc viết file này, **không** phải phát minh mới: (a) không spec nào nhận
> phần dựng định tuyến dù `011b` cần hai deep link (§5.1); (b) `app_setting` dùng chung với
> `private_gate.py` nên một CRUD "bình thường" sẽ rò hash PIN (§2.1). Cả hai đều nằm **giữa** hai
> quyết định đúng ở hai file không tham chiếu nhau — đúng dạng lỗi `qa-framework.md` §8 và memory
> `feedback_gap_between_correct_decisions` đã cảnh báo.
