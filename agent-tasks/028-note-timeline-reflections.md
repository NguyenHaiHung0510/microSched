# Task 028 — Dòng thời gian ghi chú, ghim và lời nhắn nhìn lại

> Trạng thái: 📋 READY — owner chốt hướng sản phẩm 2026-08-24; chưa implement
> Executor đề xuất: T2 Sol · Bậc: high · Effort: high · Skill gợi ý: không bắt buộc · MCP cần: không có

## 1. Mục tiêu người dùng

Ghi chú phải trả lời rõ ba câu hỏi khác nhau mà không sửa lịch sử:

1. **Ghi chú nói về lúc nào?** Người dùng chọn chính xác `date-time`, `date-only`, hoặc
   `unscheduled`. Nếu bỏ qua khi tạo, mặc định là phút hiện tại.
2. **Bản ghi gốc được tạo/sửa lúc nào?** `created_at` và `updated_at` vẫn là audit timestamp,
   không bị ghi đè khi người dùng đổi mốc nội dung.
3. **Sau này người dùng nghĩ thêm gì?** “Lời nhắn từ tương lai” là một reflection có timestamp
   được nối vào timeline của chính ghi chú; nó không phải notification, task, archive hay discard.

Đồng thời đưa cột `note.pinned` đã có trong DB ra API/UI. Phase này không đưa `priority` ra UI.

## 2. Bằng chứng hiện trạng và ranh giới suy luận

- [QUAN SÁT] `backend/app/domain/models.py:176-211` có `Note`, gồm `pinned`, `priority`,
  `is_private`, `deleted_at`; lớp nền ở `:92-97` đã có `created_at`/`updated_at`.
- [QUAN SÁT] `backend/app/domain/notes.py:55-98` chưa nhận/trả `pinned` hoặc mốc nội dung;
  `NoteRead` chỉ trả audit timestamps. `:158-178` đang sắp mới nhất theo `created_at`.
- [QUAN SÁT] `frontend/src/NotesScreen.tsx:53-59,211-270,347-378` chưa khai báo hay hiển thị
  timestamp/pin; `frontend/src/NoteForm.tsx:14-41` chỉ có title, body và privacy.
- [QUAN SÁT] `backend/tests/test_notes_api.py:437-456` khóa hành vi list mới nhất trước.
- [QUAN SÁT] migration `0009_legacy_preserving_columns.py:20-47` đã thêm `pinned` và
  `priority`; `agent-tasks/020-legacy-preserving-columns.md:109-114` chỉ hoãn UI của hai cột
  trong scope 020. Quyết định owner 2026-08-24 mở lại **pin**, không mở `priority`.
- [QUAN SÁT] `docs/schema-physical-brief.md:100-104` dùng `TIMESTAMPTZ` và trigger DB cho
  `updated_at`; DML backfill sẽ có nguy cơ làm audit timestamp lịch sử trông như vừa sửa.
- [QUAN SÁT] `docs/forward-spec.md:15-24` trước đây để “Lời nhắn từ tương lai” ở DEFER. Quyết định
  owner 2026-08-24 thay thế đúng trạng thái defer này bằng semantics tối thiểu trong task 028.
- [SUY LUẬN] Giữ ba trạng thái legacy bằng `NULL` thay vì backfill là cách ít blast radius nhất:
  không chạm dữ liệu cũ, không kích trigger `updated_at`, vẫn cho UI một fallback trung thực.
- [KHÔNG BIẾT] Timestamp lịch sử có phản ánh đúng thời điểm người dùng từng muốn gắn cho note
  hay không; không được suy diễn điều đó từ `created_at` rồi ghi ngược vào DB.

## 3. Hành vi đã khóa

### 3.1 Ba precision của mốc nội dung

API dùng discriminated object `time`:

```json
{"precision":"datetime","value":"2026-08-24T21:37:00+07:00"}
{"precision":"date","value":"2026-08-24"}
{"precision":"unscheduled"}
```

- `datetime` có **precision đến phút**: offset RFC 3339 là bắt buộc; giây và phần thập phân
  phải bằng 0. Server lưu instant bằng `TIMESTAMPTZ`; client chính gửi offset `+07:00`.
- `date` là ngày lịch thuần `DATE`, không biến thành nửa đêm giả và không đổi theo timezone.
- `unscheduled` là lựa chọn chủ động, không phải thiếu dữ liệu.
- Create không gửi `time`: server lấy `now()` trong `Asia/Ho_Chi_Minh`, truncate xuống phút.
  UI online và outbox offline phải gửi mốc capture đã chụp khi người dùng bấm lưu để replay
  muộn không làm timestamp “nhảy” sang lúc đồng bộ.
- PATCH không gửi `time`: giữ nguyên. Gửi object `unscheduled`: xóa cả hai value. `time: null`
  là 422, không được ngầm hiểu là unscheduled.
- Edit form khởi tạo đúng value đã lưu/fallback; mở form không tự đặt lại `now`. Có action rõ
  “Đặt về bây giờ” nếu người dùng chủ động muốn đổi.

### 3.2 Audit timestamp không đổi nghĩa

- `created_at` là lúc row gốc được tạo và bất biến; không nhận trong create/update payload.
- `updated_at` do trigger hiện hành quản lý và chỉ đổi khi nội dung/pin/privacy/mốc được sửa.
- Đổi `time` không sửa `created_at`. UI detail luôn có nhãn riêng “Tạo lúc …”; nếu đã sửa,
  thêm “Sửa lần cuối …”. Không gọi `updated_at` là lịch sử phiên bản.
- Không dựng revision history trong phase này. “Lịch sử” ở đây là original node + reflection
  nodes + hai audit timestamps trung thực.

### 3.3 Ghim, thứ tự cũ/mới và nhãn thời gian

- `pinned` là boolean công khai ở `NoteCreate` (default `false`), `NoteUpdate` và `NoteRead`.
  Dùng cột hiện có; **không thêm migration cho pin**. Không expose `priority`.
- List có lựa chọn `sort=newest|oldest`, mặc định `newest`; pin luôn đứng trước unpinned trong
  filter hiện tại. Trong mỗi partition pin:
  1. unscheduled luôn cuối;
  2. so sánh ngày lịch ở `Asia/Ho_Chi_Minh`;
  3. datetime cùng ngày theo instant và theo chiều sort;
  4. date-only đứng sau các datetime cùng ngày ở cả hai chiều vì nó không phát biểu giờ;
  5. tie-break bằng `created_at`, rồi `id`, theo cùng chiều sort.
- Legacy fallback được xếp như datetime theo `created_at`, nhưng DTO/UI phải gắn nguồn fallback;
  không được viết fallback xuống DB.
- List card luôn hiển thị absolute label: `21:37 · 24/08/2026`, `24/08/2026 · cả ngày`,
  `Chưa xếp lịch`, hoặc `Tạo lúc 21:37 · 24/08/2026` cho legacy. Relative text như “2 giờ
  trước” chỉ được bổ sung, không thay absolute label.

### 3.4 “Lời nhắn từ tương lai” là reflection

- Original note vẫn là node đầu tiên. Reflection là đoạn Markdown ngắn nối vào note đó;
  không có title, checklist, completion, archive, reminder, embedding, AI hoặc notification.
- Reflection sắp tăng dần theo `reflected_at`, rồi `id`. Timestamp đó là lúc reflection được
  thêm, không phải mốc nội dung của original note.
- Create mặc định phút hiện tại; client/offline capture action time như note. Người dùng không
  chọn một ngày tương lai để hẹn gửi. Sau khi tạo, `reflected_at` bất biến; edit chỉ sửa body.
- Edit cập nhật `updated_at` và UI ghi “đã sửa”; delete là soft delete. UI cho Undo 10 giây,
  nhưng server restore vẫn kiểm privacy/parent state và không dựa vào timer client để bảo mật.
- Xóa mềm original note ẩn toàn timeline theo gate cha. Restore note đưa các reflection chưa
  bị xóa riêng trở lại; reflection đã xóa riêng không tự sống lại.
- Không có màn archive/discard. Reflection nằm trong detail/timeline của original note.

## 4. Data contract và migration

Task 028 tạo **một Alembic revision** từ head đang tồn tại lúc implement:

### 4.1 Cột mới trên `note`

```text
time_precision TEXT NULL     -- 'datetime' | 'date' | 'unscheduled'; NULL = legacy
noted_at       TIMESTAMPTZ NULL
noted_on       DATE NULL
```

CHECK duy nhất chấp nhận đúng bốn shape:

```text
(time_precision IS NULL AND noted_at IS NULL AND noted_on IS NULL)
OR (time_precision = 'datetime' AND noted_at IS NOT NULL AND noted_on IS NULL)
OR (time_precision = 'date' AND noted_at IS NULL AND noted_on IS NOT NULL)
OR (time_precision = 'unscheduled' AND noted_at IS NULL AND noted_on IS NULL)
```

Không DML backfill. Existing rows giữ triple-NULL. Read adapter trả:

```json
{
  "time": {
    "precision": "datetime",
    "value": "<created_at RFC3339>",
    "source": "created_at_fallback"
  }
}
```

Rows mới/đã chọn lại trả `source: "explicit"`. `source` read-only; request gửi `source` là 422.

### 4.2 Bảng `note_reflection`

```text
id            UUID PK, UUIDv7
note_id       UUID NOT NULL FK note(id) ON DELETE CASCADE
body_md       TEXT NOT NULL
reflected_at  TIMESTAMPTZ NOT NULL
created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at    TIMESTAMPTZ NOT NULL DEFAULT now() + trigger hiện hành
deleted_at    TIMESTAMPTZ NULL
```

- Index live timeline: `(note_id, reflected_at, id) WHERE deleted_at IS NULL`.
- Model khai `Gate.VIA_PARENT` cho privacy và delete. Không thêm `is_private` riêng; parent note
  là source of truth.
- `body_md` dùng cùng crypto envelope `enc:v1:` như `NoteItem`: public lưu cleartext, private
  lưu ciphertext. Không index/search/embedding reflection trong phase này.
- Khi toggle note public ↔ private, lock row cha và convert original, items, **mọi reflection
  kể cả soft-deleted** trong cùng transaction; lỗi giữa chừng rollback toàn bộ.
- Downgrade chỉ drop index/table/check/cột mới; vì upgrade không sửa row cũ nên round-trip không
  cần phục hồi audit timestamps.

### 4.3 API tối thiểu

```text
GET    /api/notes?sort=newest|oldest&limit=&offset=
POST   /api/notes
PATCH  /api/notes/{note_id}
GET    /api/notes/{note_id}/reflections
POST   /api/notes/{note_id}/reflections
PATCH  /api/notes/{note_id}/reflections/{reflection_id}
DELETE /api/notes/{note_id}/reflections/{reflection_id}
POST   /api/notes/{note_id}/reflections/{reflection_id}/restore
```

Reflection create/read DTO:

```json
{
  "id": "<UUIDv7>",
  "body_md": "Bây giờ nhìn lại…",
  "reflected_at": "2026-08-24T21:37:00+07:00",
  "created_at": "<RFC3339>",
  "updated_at": "<RFC3339>"
}
```

- `id` client-selected UUIDv7 để đi qua outbox 017; replay cùng ID + cùng logical payload trả
  row cũ, payload khác trả conflict theo contract idempotency hiện hành sau 017.
- `reflected_at` có thể bỏ ở client online để server default, nhưng outbox bắt buộc gửi capture
  time. PATCH chỉ nhận `body_md`; extra field, `null` body, body rỗng/whitespace là 422.
- Parent không tồn tại, soft-deleted hoặc private đang khóa đều trả 404 như reading gate hiện
  hành. Không tiết lộ trường hợp nào qua response khác nhau.

## 5. UI mobile-first, privacy và accessibility

- Quick add mặc định datetime phút hiện tại nhưng không bắt thêm tap. Form đầy đủ có segmented
  control ba lựa chọn, native-feeling date/date-time picker và action pin có text/accessible name.
- Note card không có fixed height; title/body vẫn wrap. Pin là state nhìn thấy bằng icon + text,
  không chỉ màu/hover. Touch target tối thiểu 44×44 px.
- Detail trình bày timeline theo DOM order: original, reflection cũ → mới, composer cuối. Có
  action “Mới nhất” để cuộn cuối khi timeline dài; không auto-scroll làm mất vị trí đọc.
- Dùng component trong `@/components/ui/*`, token `index.css`, light mode; không raw interactive
  element, hardcoded color, font dưới 12 px hay hover-only theo `docs/ui-brief.md` §6.
- Segmented control/accordion có label, keyboard focus rõ, `aria-pressed` hoặc native radio
  semantics; timestamp dùng `<time datetime="…">`. Screen reader nghe được “Đã ghim”, “Cả ngày”,
  “Chưa xếp lịch”, “Đã sửa”.
- Private lock: API không trả reflection/body/timestamp chi tiết của note private khi khóa;
  query cache được xóa cùng lifecycle lock hiện hành. Không log title/body/reflection, plaintext
  hay ciphertext. Offline persistent cache/outbox tuân task 017; không mở cache riêng.

## 6. Acceptance matrix

| ID | Tình huống | Biên lai bắt buộc |
|---|---|---|
| N1 | Create bỏ time online | DB explicit `datetime`, đúng phút VN; response `source=explicit` |
| N2 | Create offline, replay hôm sau | mốc là phút bấm lưu, không phải phút replay |
| N3 | Date-only quanh 23:30 UTC | ngày hiển thị giữ nguyên literal, không lệch ±1 ngày |
| N4 | Unscheduled | cả value NULL nhưng precision explicit; luôn sau scheduled |
| N5 | Legacy row | triple-NULL giữ nguyên; read fallback từ `created_at`; `updated_at` byte-for-byte không đổi sau upgrade |
| N6 | Edit mở rồi đóng | không PATCH, không đổi time/audit; “Đặt về bây giờ” mới đổi |
| N7 | Pin + newest/oldest | pin trước; fixtures cùng ngày/date-only/unscheduled/tie có order deterministic |
| N8 | Reflection CRUD | original không đổi; create/order/edit marker/soft-delete/restore đúng |
| N9 | Toggle privacy có reflection deleted | toàn bộ descendants convert atomically; forced mid-transaction failure rollback |
| N10 | Private đang khóa | list/detail/reflection CRUD không tiết lộ existence; cache bị purge |
| N11 | A11y/mobile | 390×844 và 320×568 không overflow; 44 px targets; keyboard/SR names/focus pass |
| N12 | Migration | upgrade → model checks → downgrade trên Postgres throwaway; không chạy round-trip Neon |

Test bắt buộc:

- Backend unit/API cho mọi valid/invalid discriminated shape, seconds khác 0, missing offset,
  extra `source`, stable ordering, UUIDv7 idempotency/conflict, parent/privacy/deletion gates.
- Migration QA trên Postgres throwaway với legacy fixture đã ghi chính xác
  `created_at`/`updated_at`; so sánh trước/sau upgrade. Không dùng SQLite cho DDL proof.
- Frontend Vitest cho default/edit state, labels, pin/sort, timeline/undo/error rollback; Playwright
  mobile + desktop cho keyboard, wrap, focus restoration và private lock.
- Guardrail mới phải có RED → GREEN receipt: tạm làm adapter ghi fallback vào row hoặc để edit
  reset time, thấy test đỏ đúng lý do; hoàn nguyên và thấy xanh.

## 7. Sequencing, scope và điểm dừng

1. **Gate cứng:** merge task 017 trước vì cùng sửa note API, `NotesScreen`, query cache và offline
   outbox. Rebase task 028 lên head đó rồi mới implement.
2. Implement 028 migration/API trước UI; migration production chạy thủ công theo runbook hiện
   hành, không thêm auto-migrate/deploy/ops.
3. Task 030 có migration phụ thuộc revision 028 và chỉ được tạo sau khi SHA/revision 028 ổn định.
   Task 029 không có migration và có thể chạy song song sau gate 017 nếu không chia sẻ writer.
4. Update đúng các contract docs liên quan trong PR implementation; không sửa status/index rộng.

Không làm: priority UI, AI, embedding/search reflection, revision history, share/export, timezone
preference, reminder từ reflection, recurring note, data backfill, deploy production hay verify iPhone
thật. Nếu code sau task 017 làm một contract trên không còn đúng, dừng và nêu hai phía; không tự
chọn cách “có vẻ mới hơn”.
