# 010b — Calendar slice, tầng nhìn: lịch cuộn liên tục + mini-nav + đánh dấu ngày + dời việc

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L2
> · Skill gợi ý: không cần · MCP cần: không cần.**
> **Phụ thuộc cứng: `010a` phải merge và chạy thật trên production trước.** 010b không dựng lại
> parser, không đụng luồng import, không đụng CRUD nguồn — nó chỉ **thêm một cách nhìn** lên đúng dữ
> liệu 010a đã có, cộng một bảng mới (`day_annotation`) và một đường ghi mượn từ domain `task`.
> Đã qua **2 lượt phản biện đối kháng** trên spec + code thật (2026-08-01): T3 `gemini-3.1-pro-high`
> và T2 `gpt-5.6-sol`. T2 bắt được **một lỗi CRITICAL thật sự nguy hiểm**: bản nháp đầu quên rằng
> `QueryClient` toàn cục poll **mỗi 1 giây** cho mọi query còn hiển thị (`main.tsx:12-16`) — 13 query
> tháng cộng annotation cộng task sẽ dội hàng chục request/giây vào Fly/Neon nếu không tắt tường
> minh. Dấu vết đầy đủ ở §10.
> **Trạng thái: cả 3 mục ở §8 đã chốt 2026-08-01 — sẵn sàng giao Codex.**

## 0. 010b là nửa nào, và vì sao nó xứng đáng là một PR riêng

`010a` giao được **dữ liệu đúng** (import, CRUD, danh sách theo ngày). Nó cố ý **không** dựng lưới
lịch. 010b là phần chủ thật sự muốn nhìn: **lịch cuộn liên tục kiểu Outlook** của app cũ — thứ chủ
mô tả là *"chủ yếu là đẹp và tường minh"* và vẫn mở ra ngắm.

Tách ra vì ba lý do đo được, không phải vì thẩm mỹ quy trình:
1. **Rủi ro khác loại.** 010a hỏng = dữ liệu sai. 010b hỏng = *nhìn* sai trong khi dữ liệu vẫn đúng.
   Gộp chung thì một lỗi CSS cũng chặn đường import.
2. **Nó đụng domain `task`** (dời hạn từ lịch) — nghĩa là một PR gộp sẽ chạm cả ba domain.
3. **Nó là quyết định thị giác**, mà luật dự án
   (memory `feedback-visual-draft-before-lock`) nói quyết định thị giác thì **dựng bản chạy được cho
   chủ bấm chọn**, không mô tả bằng chữ. §8 giữ đúng ba chỗ cần chủ nhìn rồi mới khoá.

## 1. App cũ thật sự làm gì — đo trên code, và **ba luật UI nó vi phạm**

Đọc `old_prj/VC_QuanLyThoiGian/app/ui/calendar_view.py` (1208 dòng, Flet) ngày 2026-08-01. Đây là
quan sát trên code, không phải mô tả từ ảnh chụp. **Sửa 2026-08-01 (bắt bởi T2):** bản nháp đầu ghi
sai vị trí và số tháng của mini-nav; đã kiểm lại và sửa ở mục 2 dưới.

1. **"Cuộn liên tục" thực chất là các lưới tháng xếp nối đuôi nhau**, không phải một dải tuần vô tận.
   `_fill_calendar_list_view()` (`:563-606`) đổ vào một `ListView` phẳng theo đúng thứ tự:
   *header tháng (cao 50) → từng hàng tuần của tháng đó (cao 100, lấy từ `calendar.monthcalendar`) →
   header tháng kế →…*. Ô ngày của tháng khác được vẽ mờ (`is_other_month`, `:258`), nên hai tháng
   liền nhau có tuần giao lặp lại — **cùng một tuần dương lịch xuất hiện thành hai hàng riêng biệt**
   (một ở cuối khối tháng trước, một ở đầu khối tháng sau), mỗi hàng chỉ tô đậm ngày thuộc tháng của
   khối đó. **Giữ đúng hình dạng này** — nó là cái chủ quen mắt, và §5.2 nói rõ vì sao khoá DOM phải
   mang cả `(year, month, week_index)` chứ không chỉ ngày đầu tuần, chính vì lý do lặp này.
   **Tuần bắt đầu từ Thứ Hai** (`get_week_start()`: `d - timedelta(days=d.weekday())`, Python
   `weekday()` có Monday=0; nhãn cột `["T2","T3","T4","T5","T6","T7","CN"]` ở `:1097`). Bản mới giữ
   nguyên — đừng đổi sang tuần bắt đầu Chủ Nhật.
2. **Mini-nav nằm bên TRÁI, luôn hiện đúng HAI tháng, và là cơ quan điều hướng hai chiều —
   không phải mảng màu trang trí.** (Sửa vị trí + số tháng: `root = ft.Row([sidebar, main_area])`
   ở `:1197` — `sidebar` là con đầu tiên nên nằm trái; `_build_mini_nav()` ở `:641-669` luôn ép
   `visible_months = […][:2]`, giữ đúng 2 khối tháng để chiều cao sidebar cố định.)
   `on_calendar_scroll` (`:499-552`) tính `visible_dates` = tập ngày đang nằm trong khung nhìn, rồi
   `_build_mini_nav()` tô hồng đúng những ô đó (`is_visible_on_screen = (d in visible_dates)`,
   `:724`). Chiều ngược lại: bấm một ô mini ⇒ `_scroll_to_date()` (`:736-738`). Nhãn tháng ở header
   cũng do vòng này cập nhật (`:536`). **Bỏ mini-nav là bỏ luôn cách duy nhất biết mình đang ở đâu
   trong một danh sách cuộn không có điểm mốc.**
   **Quyết định cho bản mới (không bắt buộc chép vị trí/số tháng — chỉ chức năng):** giữ **2 tháng**
   hiển thị (đúng lý do chiều cao ổn định của app cũ), nhưng đặt ở **cột phải, ẩn dưới `sm`** — đây
   là lựa chọn bố cục có chủ ý cho web, không phải claim rằng app cũ làm vậy. Ghi rõ để không ai đọc
   nhầm là port nguyên xi.
3. **Ô ngày**: số ngày + tối đa **3** chip sự kiện + dòng `+N…` (`:283-305`). Hôm nay có viền đậm +
   nền hồng nhạt (`:270,309`). Chạm ô ⇒ mở dialog chi tiết (`on_day_cell_click`, `:413`).

**Ba thứ của app cũ KHÔNG được port — chúng là bug đã có luật cấm, không phải phong cách:**

| App cũ làm | Luật cấm | Vì sao nó hỏng thật |
|---|---|---|
| `height=100` cứng cho hàng tuần, `height=50` cho header (`:589,571`) | `ui-brief.md` §6.3 | Chiều cao cứng chính là lý do chữ bị cắt ở app cũ. Trên web, hàng tuần **giãn theo nội dung**; xem §5.2 về cách làm điều đó mà vẫn đồng bộ được mini-nav. |
| `size=9` cho chip sự kiện, `size=12` cho số ngày (`:296,273`) | `ui-brief.md` §6.4 (≥12px) + `qa-framework.md:70` | 9px trên iPhone là không đọc nổi. Đây là ràng buộc **quyết định luôn cách trình bày ô ngày trên mobile** — xem §5.4. |
| Toàn bộ chi tiết ngày nằm trong **native tooltip** (`:326-410`) | `ui-brief.md` §6.6 + §9(a) | iPhone không có hover. App cũ vẫn có `on_day_cell_click` mở dialog nên đường chạm *tồn tại*, nhưng tooltip là đường **giàu thông tin hơn** ⇒ máy chạm bị bản kém hơn. Ở bản mới: **dialog là đường chính trên mọi kích thước** (§5.5) và tooltip (nếu có ở desktop) **không được** chứa gì mà dialog không có. |

Ngoài ra app cũ hardcode bảng màu ưu tiên task (`calendar_view_service.py:56-95`) — `ui-brief.md`
§6.2 cấm; màu đi qua token, y như luật `SOURCE_COLORS` đã chốt ở `010a` §5.

## 2. Đã khoá — chép ra code, không mở lại

1. **Backend + parser của 010a KHÔNG được sửa. UI screen của 010a THÌ ĐƯỢC sửa — đây là ranh giới
   thật, không phải "không đụng gì của 010a".** (Bản nháp đầu tự mâu thuẫn chỗ này — bắt bởi T2: nói
   "không đụng 010a" rồi lại yêu cầu sửa `CalendarScreen.tsx`.) Cụ thể:
   - **Cấm tuyệt đối, dừng và báo nếu thấy cần đổi:** `backend/app/core/ics.py`,
     `backend/app/domain/calendar.py`, `backend/app/web/routers/calendar.py`. Ba file này chạy
     production, đúng như bản 010a đã duyệt.
   - **Được phép, và bắt buộc phải sửa:** `frontend/src/CalendarScreen.tsx` (thêm nút chuyển chế độ
     xem, §5.1) và `frontend/src/TasksScreen.tsx` (thêm ba nút dời nhanh trên thẻ task quá hạn,
     §5.6). Đây là **bề mặt tích hợp UI có chủ đích** của 010b, không phải ngoại lệ.
2. **`GET /api/calendar/events` giữ nguyên hợp đồng của 010a** — `from`/`to` bắt buộc, có offset,
   lọc **giao nhau**, `ORDER BY starts_at, id`, **không phân trang**, trả về envelope
   `{"items": [...]}` (đồng nhất với `list_sources`/`list_tasks` — 010a không nói rõ điều này ở bảng
   endpoint, coi đây là phần bổ sung chốt cho cả hai spec, không phải diễn giải lại). 010b là khách
   hàng đầu tiên thật sự cần luật giao-nhau: mỗi biên tuần trên màn hình là một lần buổi 07:00–09:00
   có thể biến mất nếu ai đó "tối ưu" thành `BETWEEN` (`010a` §4.2).
   **`EventRead` của 010a không mang màu/`kind` của nguồn** (chỉ có `source_id`). 010b **không** xin
   sửa DTO đó; thay vào đó §5.2 nói rõ cách nối phía client bằng một lượt `GET /api/calendar/sources`
   giữ trong bộ nhớ.
3. **`day_annotation` là bảng riêng, không phải buổi cả-ngày trong `calendar_source(kind='manual')`**
   — chốt với chủ 2026-08-01. Hai lý do: CHECK `ends_at > starts_at` (`models.py:252`) buộc phải
   **bịa một giờ kết thúc** cho thứ vốn không có giờ; và "ngày về quê" nằm lẫn trong danh sách buổi
   học thật sẽ làm rối đúng cái màn hình nó sinh ra để làm rõ.
4. **🔒 `day_annotation` khai `Gate.APPLIES` (riêng tư) ngay từ đầu — chốt với chủ 2026-08-01, không
   để `Gate.NONE` rồi tính sau.** Lý do đổi: `reading.py` (`_gate_column`) **ném lỗi ngay khi nạp
   model** nếu một bảng khai `Gate.APPLIES` mà không có cột `is_private` tương ứng sẵn có — nghĩa là
   "bật riêng tư sau" không phải một dòng khai miễn phí, mà là một migration thêm cột **cộng** rà lại
   mọi đường đọc gọi `readable()`. Chủ chưa hình dung cụ thể ngày nào cần giấu, nhưng chi phí làm
   **ngay bây giờ**, trong đúng migration `0006` này, rẻ hơn hẳn chi phí quay lại thêm cột sau — nên
   làm luôn. Cột `is_private` cộng vào bảng ở §3; DTO/Store/UI ở §4.1/§5.5.
   **Hệ quả:** `day_annotation` giờ theo đúng bộ luật AI × riêng tư R1–R7 (`auth-brief.md`) như
   `note` — khoá ⇒ agent lọc `is_private`; mở khoá ⇒ đọc đủ; annotation riêng tư trong ngữ cảnh ⇒ ép
   zdr/no-train cho cả cascade. `calendar_event` (buổi thật) **vẫn `Gate.NONE`**, không đổi — chỉ
   annotation đổi.
5. **Dời hạn task KHÔNG cần endpoint mới.** `TaskUpdate` đã patch `due_at` (`tasks.py:339` liệt
   `due_at` trong vòng lặp gán, `tasks.py:85` khai field). `PATCH /api/tasks/{task_id}` là đường
   ghi duy nhất được dùng. **Không** thêm `/api/calendar/move-task`, **không** sửa
   `backend/app/domain/tasks.py` / `backend/app/web/routers/tasks.py`, **không** nới `le=100`.
   *(Ứng viên "tool ghi đầu tiên" của AI Bước 2 vì thế cũng là chính endpoint này —
   `forward-spec.md` §B/§D. Một đường ghi, hai người gọi.)*
6. **Không đụng `calendar_event.is_hidden`** (`010a` §2 mục 4 — cột có, slice không chạm).
7. **Giờ Việt Nam cố định `+07:00` ở mọi chỗ**, đọc lẫn ghi, y hệt `010a` §5 mục 3. Ranh giới **ngày**
   trên lịch cắt theo `+07:00`, **không** theo múi giờ thiết bị: một buổi 23:30 giờ VN phải rơi vào
   ô ngày hôm đó dù chủ đang mở máy ở đâu.
8. **🔴 Tắt polling toàn cục cho MỌI query của 010b — bắt buộc, không phải tối ưu.** (CRITICAL, bắt
   bởi T2.) `frontend/src/main.tsx:12-16` cấu hình `QueryClient` toàn cục:
   `refetchInterval: (query) => query.state.status === "error" ? false : LIVE_REFETCH_MS` với
   `LIVE_REFETCH_MS = 1000` — **mọi query hiển thị tự poll lại mỗi giây**, trừ khi tự khai
   `refetchInterval: false`. Cửa sổ ±6 tháng của §5.2 mở **13 query tháng** song song; cộng query
   annotation và query task phân trang thì con số poll có thể lên **20–30 request/giây liên tục**
   khi tab Lịch đang mở — đủ để dội DB Neon và tạo tải CPU/network vô ích liên tục trên Fly
   always-on. Đây là loại lỗi **CI xanh tuyệt đối, chỉ lộ ra khi chủ dùng thật** — không acceptance
   nào của 010a hay bản nháp đầu 010b đo lưu lượng request.
   **Luật bắt buộc:** mọi `useQuery` mà 010b thêm (tháng sự kiện, annotation, task phân trang) phải
   khai tường minh `refetchInterval: false`. Dữ liệu lịch không cần "sống" theo giây như task —
   invalidate theo hành động (mục 9 dưới) là đủ. Test ở §7.1.
9. **Bất biến-hoá cache — chốt luật, không để executor tự đoán.** (MAJOR, bắt bởi T2: bản nháp đầu
   chọn khoá query theo tháng nhưng không nói khi nào invalidate, nên sửa một buổi qua `EventForm`
   có thể để lưới hiện dữ liệu cũ vô thời hạn vì đã tắt polling ở mục 8.) Mọi mutation của 010b
   (`create/update/delete` event tái dùng từ `010a`, mọi thao tác `day_annotation`) phải
   `queryClient.invalidateQueries({ queryKey: ["calendar"] })` — **invalidate cả họ `"calendar"`**,
   không chỉ tháng đang mở, vì một buổi có thể đổi ngày sang tháng khác. Toggle `is_visible` của
   nguồn (010a) và import lại cũng phải invalidate cùng khoá — nếu 010a's `CalendarScreen.tsx` chưa
   làm việc này, 010b phải thêm khi sửa file đó (mục 1).

## 3. Migration `0006` — bảng `day_annotation`

File mới `backend/alembic/versions/0006_day_annotation.py`, `down_revision = "0005"` (kiểm lại bằng
`ls backend/alembic/versions/`). Thêm model vào `backend/app/domain/models.py` cạnh `CalendarEvent`,
kế thừa `UUIDTimestampModel` như các bảng khác.

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | UUID PK | UUIDv7 do client sinh được (seam `008m`), y như `calendar_source`. |
| `starts_on` | `DATE NOT NULL` | **`DATE`, không `timestamptz`** — đây là toàn bộ lý do bảng này tồn tại. Một ngày lịch không có giờ và không có múi giờ; lưu nó thành `timestamptz` là mời lại đúng lớp bug lệch-7-tiếng của `010a` §4.1. |
| `ends_on` | `DATE NOT NULL` | **Bao gồm cả ngày cuối** (inclusive). Ngày lẻ ⇒ `ends_on = starts_on`. |
| `label` | `TEXT NOT NULL` | Chữ hiện trên ô ngày. |
| `note_md` | `TEXT NULL` | Ghi chú dài, chỉ hiện trong sheet chi tiết. |
| `color` | `TEXT NULL` | **Khoá bảng màu**, cùng tập `SOURCE_COLORS` của `010a` §5 (`rose`/`amber`/`emerald`/`sky`/`violet`/`slate`). Không lưu mã hex. |
| `is_private` | `BOOLEAN NOT NULL DEFAULT false` | **Mới, do §2 mục 4 chốt 2026-08-01.** Cùng khuôn `note.is_private` (`models.py` — kiểm tên cột thật khi thi công) — mặc định công khai, chủ tự bật riêng tư từng dấu ngày qua checkbox "Riêng tư" (§5.5, tái dùng đúng component/label `NoteForm.tsx:65-71` đã dùng). |

Ràng buộc + index:
- `CheckConstraint("ends_on >= starts_on", name="day_range")` — cùng tinh thần với
  `ends_at > starts_at` của `calendar_event`, nhưng **`>=`** vì một ngày lẻ là hợp lệ.
- Index trên `starts_on` và trên `ends_on` (truy vấn khoảng dùng cả hai vế, §4.1).
- `__privacy_gate__ = Gate.APPLIES` (cột `is_private`, §2 mục 4), `__delete_gate__ = Gate.NONE`
  (xoá không cần mở khoá riêng tư — cùng quy ước `note`).
- **Không** unique trên `starts_on`: cho phép nhiều dấu trong cùng một ngày. *(Ngược với hướng
  "chặt trước, nới sau" thường dùng — ở đây chọn nới vì "về quê" và "sinh nhật mẹ" trùng ngày là
  chuyện thật, còn UI đã có luật gấp `+N` sẵn từ `ui-brief.md` §5 nên chật chội không phải rủi ro
  mở. Nếu sau này thấy thừa thì thêm unique là migration một dòng, mà **thêm unique lên dữ liệu đã
  trùng thì không**; vậy nên hãy chốt luôn ở đây là ta chấp nhận rủi ro đó, đừng để executor tự
  thêm unique cho "sạch".)*

**Áp bằng tay, trước khi merge**, cùng khuôn `010a` §8: `uv run alembic upgrade head` với
`NEON_MIGRATOR_URL` → xác minh bằng truy vấn thật vào `information_schema.columns` **và**
`pg_constraint` (để thấy `day_range`) → dán output vào PR → mới merge. `0006` tương thích ngược
(bảng hoàn toàn mới, không ai đọc) nên chiều này an toàn.

## 4. Backend — nhỏ, cố ý

### 4.1 `backend/app/domain/annotations.py` + router

Mirror **cấu trúc** `010a`'s `calendar.py` (DTO → exception → store), nhưng đơn giản hơn nhiều: không
parser, không import, không transaction lồng.

DTO: `AnnotationCreate` (`id: UUID|None` + `require_uuidv7`, `starts_on: date`, `ends_on: date|None`
— vắng thì bằng `starts_on`, `label: str` strip-rồi-kiểm-rỗng, `note_md: str|None`, `color: str|None`,
`is_private: bool = False`) với `model_validator` kiểm `ends_on >= starts_on` ngay ở DTO (cả hai giá
trị luôn có mặt ở `Create`, nên validator DTO-only ở đây **đủ**, khác `Update` dưới đây).

`AnnotationUpdate` — **bốn field optional để hỗ trợ patch từng phần; `starts_on`/`ends_on`/`label`
KHÔNG được nhận `null`, riêng `is_private` là `bool | None` bình thường** (bắt bởi T2: cột DB `NOT
NULL`, patch `{"label": null}` phải là lỗi người dùng đọc được, không phải `IntegrityError` `500`).
Dùng `reject_null_required_fields` cho ba field `("starts_on","ends_on","label")` — **khác**
`010a`'s `SourceUpdate` (nơi `color` được phép null để "xoá màu"): ở đây không field nào có ngữ
nghĩa "xoá" ngoại trừ `is_private` quay về `false` khi gửi tường minh. `label` cũng `.strip()` trước
khi kiểm rỗng.
**Kiểm `ends_on >= starts_on` không làm được ở tầng DTO khi chỉ một trong hai field được gửi** —
DTO không biết giá trị đang lưu trong DB. Luật: `AnnotationStore.update()` nạp bản ghi hiện có, ghép
giá trị mới đè lên, kiểm `ends_on >= starts_on` trên **bản đã ghép**, `422` nếu sai — **trước** khi
gọi `db.flush()`. Đừng để CHECK của Postgres bắt lỗi này.

`AnnotationRead` — đủ field + `created_at`/`updated_at`, `color: str | None`, `is_private: bool`.

`AnnotationStore`: `list_annotations(from_, to_)`, `create`, `update`, `delete`. Giữ tham số
`auth: AuthSession` + gọi `readable()` — **ở đây `readable()` không còn là dead-code phòng hờ như
`010a` §4.2 nói về calendar, mà là luật đang thi hành thật**: `Gate.APPLIES` (§2 mục 4, §3) nghĩa là
khi phiên đang khoá riêng tư, mọi dấu ngày có `is_private=true` phải bị lọc khỏi `list_annotations`
— kiểm bằng test ở §7.4b, không chỉ tin `readable()` tự làm đúng.

**Truy vấn khoảng phải là GIAO NHAU, y như event:** `WHERE starts_on <= :to AND ends_on >= :from`.
Đây là chỗ lỗi sẽ tái diễn nếu ai đó chép nhầm: một dấu "về quê 20/08–25/08" phải hiện ở **mọi**
tuần chạm vào nó, kể cả tuần chỉ chứa ngày 24. Lưu ý **`<=`/`>=`** (khác `<`/`>` của event) vì hai
vế đều là ngày bao gồm, không phải mốc thời gian nửa mở.

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/api/calendar/annotations` | query `from`/`to` **dạng `YYYY-MM-DD`**, bắt buộc; giao nhau; envelope `{"items": [...]}`; không phân trang |
| POST | `/api/calendar/annotations` | `201`; trùng `id` ⇒ **`200` + bản ghi cũ** (idempotent, cùng khuôn `010a` §4.2 — **không** `409`) |
| PATCH | `/api/calendar/annotations/{annotation_id}` | `422` nếu `ends_on < starts_on` sau khi ghép với giá trị hiện có (xem trên); `422` nếu `null` cho field bắt buộc |
| DELETE | `/api/calendar/annotations/{annotation_id}` | `204`, xoá thật, có xác nhận ở UI |

Mount dưới `protected_api` (`main.py:85`) như mọi router khác.

### 4.2 Task lên lịch — **không viết endpoint mới**

Lịch cần biết task nào rơi vào ngày nào. Dùng `GET /api/tasks` sẵn có (`tasks router:42`,
`TaskListStatus = Literal["open","completed","all"]` — `tasks.py:18`). **Hai nơi gọi, hai giá trị
`status` khác nhau — chốt tường minh (bắt bởi T2, bản nháp đầu bỏ ngỏ):**
- **Sheet chi tiết ngày** (§5.5 mục 4, chỉ hiển thị): `status=all`. Một task đã hoàn thành vẫn có
  `due_at` hôm đó và `TasksScreen.tsx` hiện tại cũng không giấu task đã xong — giấu nó riêng ở lịch
  là một hành vi mới không ai yêu cầu.
- **Ô chọn "dời việc sang ngày này"** (§5.6 mục 1): `status=open`. Dời một task đã xong đi đâu cũng
  vô nghĩa.

**Một lần fetch, hai nơi dùng.** Danh sách `status=all` dưới đây là **nguồn dữ liệu duy nhất** cho cả
sheet chi tiết ngày (§5.5 mục 4) **và** chip task trên `DayCell.tsx` (§5.4) — nhóm theo `due_at` ở
tầng client (`calendar-scroll.ts`, cùng chỗ nhóm sự kiện theo ngày, §7.6). **Không** để hai nơi gọi
hai lượt fetch khác nhau: sai lệch giữa "task hiện trên ô" và "task hiện trong dialog cùng ngày" là
đúng loại bug khó thấy khi test riêng lẻ từng phần.

**Phân trang — chốt cứng một luật, KHÔNG được vừa "lấy hết" vừa "cảnh báo sau 5 vòng"** (bắt bởi T2:
bản nháp đầu tự mâu thuẫn — nếu vòng lặp tiếp tục thì câu cảnh báo nói dối, nếu dừng thì "lấy hết"
nói dối). Luật thật: **lặp tối đa 5 trang (≤ 500 task)**. Trang thứ 5 mà vẫn đầy (`len(items) == 100`)
⇒ **dừng lại**, hiện một dòng cảnh báo cố định *"Danh sách task dài hơn mức lịch hiển thị được — mở
tab Task để xem đủ."*, và **vẫn dùng phần đã tải được** (không phải màn trắng). Đây là suy giảm dần,
không phải lỗi. **Không sửa `tasks.py`, không nới `le=100`** (§2 mục 5) — 500 task là đủ rộng cho
quy mô thật của chủ (163 task đo được, `forward-spec.md` §F).

## 5. Frontend — phần chính của slice

File mới: `frontend/src/CalendarScrollView.tsx`, `frontend/src/MiniNav.tsx`,
`frontend/src/DayDetailDialog.tsx`, `frontend/src/AnnotationForm.tsx`, `frontend/src/calendar-scroll.ts`
(logic thuần: sinh danh sách tháng/tuần, gom sự kiện theo ngày, tính khoảng cần fetch, dedupe theo
`id`). **Sửa** (không phải file mới): `frontend/src/CalendarScreen.tsx` (thêm chế độ xem, §5.1) và
`frontend/src/TasksScreen.tsx` (thêm ba nút dời nhanh, §5.6, cộng `data-testid`). Không tạo tab
thứ tư.

### 5.1 Hai chế độ trong cùng một tab "Lịch"

Tab Lịch của `010a` giữ nguyên nội dung, thêm một cặp nút chuyển: **`Lịch`** (mới, mặc định) ·
**`Danh sách`** (màn của `010a`). Lý do giữ cả hai chứ không thay thế: danh sách theo ngày là đường
đọc **luôn đúng trên mọi bề rộng màn hình** và là chỗ dự phòng khi lưới có vấn đề — bỏ nó đi là tự
tay gỡ mất lưới an toàn ngay lúc thêm phần rủi ro nhất. Lựa chọn lưu ở `localStorage`, mặc định
`Lịch`. `data-testid`: `calendar-view-toggle-grid` / `calendar-view-toggle-list`.

Quản lý nguồn (danh sách nguồn, import, xoá) **ở lại màn `Danh sách`** — không nhân đôi vào lưới.
Nếu `010a`'s import/toggle/xoá chưa gọi `invalidateQueries(["calendar"])`, thêm nó ở đây khi sửa
file này (§2 mục 9) — không thì lưới sẽ hiện dữ liệu cũ vô thời hạn sau khi tắt polling (§2 mục 8).

### 5.2 Cuộn liên tục — dùng `IntersectionObserver`, KHÔNG tính offset bằng tay

App cũ tính `item_offsets` với chiều cao cứng 50/100 px rồi so với `e.pixels` (`:499-531`). **Đừng
port cách đó**: nó là nguyên nhân trực tiếp của luật cấm chiều-cao-cứng (`ui-brief.md` §6.3), và
comment trong chính code cũ thừa nhận phải bù *"cumulative layout errors"* bằng ngưỡng ±30px.

**Khung cuộn phải là một container có chiều cao/`overflow-y` xác định của riêng nó** (không phải
`document`/`body`) — `IntersectionObserver` cần biết `root` là gì, và `scrollIntoView` (§5.3) chỉ
được cuộn khung này, không được cuộn cả trang. `App.tsx:81` đã có một tổ tiên `overflow-hidden`;
đặt `root` của observer thẳng vào container cuộn của 010b, không dựa vào tổ tiên đó.

Cách của bản web:
- Mỗi hàng tuần mang `data-week-key="{year}-{month:02}-w{week_index}"` (**không phải** chỉ ngày đầu
  tuần — bắt bởi T2: hai khối tháng liền kề có thể vẽ **cùng một tuần dương lịch** hai lần theo đúng
  hình dạng app cũ ở §1 mục 1, nên khoá theo `(năm, tháng, thứ-tự-tuần-trong-tháng)`, đúng khuôn
  `week_{year}_{month:02d}_{w_idx}` app cũ đã dùng ở `:598`, mới tránh được việc chọn nhầm hàng khi
  cuộn/nhảy tới ngày). **Cao theo nội dung** (`min-height` được, `height` cứng thì không).
- Một `IntersectionObserver` trên tất cả hàng tuần, `root` = khung cuộn, `threshold: 0`.
  **`entries` trong callback chỉ chứa phần tử VỪA đổi trạng thái, không phải toàn bộ tập đang giao**
  (bắt bởi T2, đúng theo spec IntersectionObserver): giữ một `Map<weekKey, boolean>` cập nhật từng
  entry, rồi suy `visibleWeekKeys = [...map].filter(([,v]) => v).map(([k]) => k)` mỗi lần callback
  chạy — **không** đọc trực tiếp `entries` như một ảnh chụp đầy đủ.
  Header sticky (§5.3, nếu dùng) không được che phần tử mà vẫn tính là "đang thấy" — nếu header
  sticky cao `H`, đặt `rootMargin: "-Hpx 0px 0px 0px"` để vùng bị che không tính là giao.
- **Tháng ở header** = tháng của tuần có `weekKey` nhỏ nhất (theo thứ tự DOM) trong tập đang giao —
  "nhỏ nhất theo DOM", không phải "phần tử đầu tiên trong `entries`" (đúng lỗi trên). Cuộn chậm
  không làm nhãn nhấp nháy vì tập chỉ đổi từng phần tử một.
- **Không tự viết throttle bằng `setTimeout`.** So **tập giá trị** `visibleWeekKeys` với lần trước
  (dùng `.join(",")` như `last_visible_weeks_hash` của app cũ, `:529`) và bỏ qua render khi giống —
  đó là so **giá trị**, không phải hẹn giờ.
- **Thêm hàng tuần mới ⇒ `observer.observe()`; hàng bị gỡ (mép ngoài cửa sổ ±6 tháng, nếu virtualize
  sau này) ⇒ `observer.unobserve()`.** Ở phạm vi 010b (không virtualize, xem dưới) điều này chỉ có
  nghĩa: quan sát ngay khi một hàng mount, không có bước gỡ nào cần làm vì mọi hàng ở lại DOM.

**Cửa sổ dữ liệu:** render sẵn **±6 tháng** quanh tháng hiện tại = **13 khối tháng**. Vì tuần biên bị
lặp giữa hai khối liền kề (§1 mục 1), tổng số **hàng tuần thật trên DOM lớn hơn 13× số tuần trung
bình một tháng** — đo bằng `calendar.monthcalendar` (Thứ Hai đầu tuần) từ 02/2026 đến 02/2027 ra
**67 hàng tuần + 13 header = 80 khối DOM**. *(Bản nháp đầu ước tính "~57 hàng" — sai, đã sửa; số
đúng không đổi kết luận: 80 khối vẫn đủ nhỏ để không cần virtualization, nhưng đừng chép con số cũ
vào code hay comment.)* Chạm mép ⇒ nối thêm 6 tháng về phía đó (thêm khối DOM, không gỡ khối cũ —
80 khối không đáng để dựng `react-window`).

**Fetch theo tháng, một `useQuery` một tháng**, key `["calendar","events",yyyy,mm]`,
**`refetchInterval: false` bắt buộc** (§2 mục 8). Khoảng của mỗi query là
`[ngày đầu tháng 00:00+07:00, ngày đầu tháng kế 00:00+07:00)` — nửa mở, cùng quy ước `010a` §5. Vì
một buổi bắc qua biên tháng **sẽ được trả về bởi cả hai query tháng liền kề** (đúng luật giao-nhau
của `010a` §4.2 — đây là hệ quả cố ý, không phải bug), khi gộp kết quả các tháng để nhóm theo ngày
**phải dedupe theo `event.id`** trước khi đếm/hiển thị — không dedupe thì một buổi bắc-đêm hoặc một
annotation nhiều-ngày-bắc-tháng sẽ bị đếm hai lần ở dòng `+N`. Cùng luật áp cho annotation.
**Query nguồn** (`GET /api/calendar/sources`, đã có ở `010a`) tải **một lần**, `refetchInterval:
false`, dùng để dựng map `source_id → {color, kind}` cho việc tô màu chip/chấm (§2 mục 2).

**Nhảy tới hôm nay:** nút `Hôm nay` luôn hiện; cuộn bằng
`element.scrollIntoView({ block: "center" })` **gọi trên chính khung cuộn, không phải trên
`window`** — mặc định `scrollIntoView` có thể cuộn **mọi** tổ tiên cuộn được, kể cả trang (bắt bởi
T2). Cách an toàn: dùng `scrollIntoView({ block: "nearest" })` kết hợp `container.scrollTop =` tính
tay, **hoặc** đảm bảo khung cuộn là tổ tiên cuộn-được duy nhất trên đường tới phần tử đó (không còn
`overflow` nào khác ở giữa) rồi mới dùng `block: "center"`. Chọn cách nào cũng phải test bằng
`page.evaluate(() => window.scrollY)` giữ nguyên `0` sau khi nhảy (§7). Lần mở đầu tiên **phải tự
nhảy tới hôm nay trước khi người dùng thấy gì** — không có hiệu ứng nhấp nháy "mở giữa trang rồi
giật lên": tính vị trí cuộn ban đầu trước lần vẽ đầu tiên (`useLayoutEffect`, không phải
`useEffect`).

### 5.3 Mini-nav

Cột bên phải trên desktop (bố cục mới, không phải port app cũ — §1 mục 2), **ẩn trên mobile**
(§5.4). Nội dung: **2 khối tháng nhỏ** (giữ số 2 của app cũ — chiều cao ổn định) + nút lùi/tiến
tháng.

- Ngày nằm trong `visibleWeekKeys` (§5.2) ⇒ tô nền bằng token **`--accent`** (chữ
  `--accent-foreground`) — token này **đã tồn tại** trong `index.css:67-68` (rose nhạt), **không**
  bịa `--primary-light` (bắt bởi T2: token đó không có trong registry).
- Bấm một ô ⇒ cuộn lịch chính tới tuần chứa ngày đó (§5.2 cách an toàn).
- Tháng đầu của mini-nav **tự đi theo** tháng đang xem khi cuộn (app cũ: `:539-546`); bấm lùi/tiến
  tháng thì mini-nav đi trước, và **cũng kéo lịch chính đi theo** — nếu không, hai bên lệch nhau và
  người dùng không hiểu mình đang nhìn cái gì.
- **Đích chạm ô mini ≥ 24×24 CSS px** (`qa-framework.md:71` — dưới ngưỡng này là **đỏ**, không phải
  vàng theo **luật riêng của dự án**; ghi rõ đây là quy ước nội bộ chặt hơn WCAG 2.5.8 gốc — bản
  WCAG có các ngoại lệ về khoảng cách/kiểm soát tương đương mà dự án cố ý không áp dụng, bắt bởi
  T3). Ô mini là nơi dễ vi phạm nhất vì bản năng là làm nó thật nhỏ cho gọn.
- **Chỉ đo/kiểm mini-nav ở viewport desktop** (§7 — nó không tồn tại trên 390px, đo ở đó chỉ ra
  `0×0`).
- `data-testid`: `calendar-mininav`, `calendar-mininav-day`, `calendar-mininav-prev` /
  `calendar-mininav-next`.

### 5.4 Ô ngày — và chỗ thiết kế này yếu nhất: 390px

Viewport chính của chủ là **390 × 844** (`qa-framework.md:40`). Đo bằng phần đệm THẬT của layout
hiện có, không ước lượng: `<main>` có `px-4` (`App.tsx:153`, = 16px mỗi bên, `sm:px-6` không áp dụng
dưới 640px) lồng `<div>` có `px-5` (`App.tsx:103`, = 20px mỗi bên) — tổng đệm ngang
**16×2 + 20×2 = 72px**. Vùng lưới còn lại: `390 - 72 = 318px`. Bảy cột, 6 khe hở `gap-0.5` (2px ×
6 = 12px): `(318 - 12) / 7 ≈ 43.7px/cột` — **dưới ngưỡng 44px** (bắt bởi cả T2 lẫn T3 độc lập; bản
nháp đầu ước lượng "~50px" là sai vì bỏ qua đệm layout thật).

**⇒ Quyết định bắt buộc, không phải tuỳ chọn thi công:** lưới lịch phải **thoát khỏi đệm ngang** của
layout chuẩn trên mobile — dùng kỹ thuật full-bleed (âm margin bằng đúng đệm cha, hoặc render lưới
trong một container riêng ở ngoài `px-4`/`px-5`) để cột thật sự có **390 / 7 ≈ 55.7px** trước khe hở,
đủ dư so với 44px ngay cả sau khi trừ `gap`. Executor phải **đo thật** bằng
`getBoundingClientRect()` sau khi dựng (§7.7), không tin phép tính trên giấy — kể cả phép tính đã
sửa này.

**Chốt 2026-08-01 (chủ chọn qua bản mẫu chạy được, không mô tả bằng chữ — đúng luật
`feedback-visual-draft-before-lock`): phương án C — ô cao gấp đôi, tối đa 2 chip có chữ trên mobile
— và task CÓ hiện thành chip/chấm ngay trên ô ngày, không chỉ trong dialog.** Một component
`DayCell.tsx`, cắt ở `sm` (640px, breakpoint mặc định Tailwind) chỉ còn khác nhau về **số chip tối
đa**, không còn khác nhau về "có chữ hay không" như bản nháp bị bác:

| | `< 640px` (iPhone) | `≥ 640px` (desktop) |
|---|---|---|
| Chiều cao ô | **gấp đôi** ô thường (~96–108px, đo thật, không chốt số cứng — miễn ≥ 44px) để 2 dòng chip vừa mà không đè chữ | vừa đủ cho 3 dòng chip, đo thật |
| Ô ngày chứa | số ngày + **tối đa 2 chip có chữ** (gộp cả buổi lẫn task, xem thứ tự dưới) + dòng `+N…` nếu còn | số ngày + **tối đa 3 chip có chữ** (cùng luật gộp) + dòng `+N…` (đúng app cũ) |
| Mini-nav | **ẩn** — thanh tháng dính (sticky) ở đầu khung cuộn thay thế | cột bên phải, 2 tháng |
| Đường tới chi tiết | **chạm cả Ô ⇒ dialog** (§5.5) — **chip không phải đích chạm riêng**: một chip cao ~16-18px không đạt 44px tối thiểu, nên toàn ô là một vùng chạm duy nhất, không chia nhỏ theo từng chip | **bấm cả ô ⇒ cùng dialog**; tooltip (nếu thêm) chỉ là bổ sung, không mang thông tin riêng |

**Thứ tự gộp chip (cả hai breakpoint):** buổi sự kiện trước (sắp theo `starts_at`), task sau (sắp
theo `due_at`) — buổi là nội dung chính của lịch, task là lớp phủ. Cắt ở 2 (mobile) / 3 (desktop)
phần tử đầu tiên của danh sách đã gộp; phần còn lại gộp chung vào **một** số `+N` (không tách riêng
"+N buổi" và "+N task" — giữ dòng cuối gọn).

**Không thêm shadcn `Sheet`.** (Bắt bởi T2: repo hiện chỉ có `Dialog`, spec cũ ngụ ý một "sheet"
tách biệt mà không định nghĩa, mở đường cho ba lối triển khai khác nhau.) Dùng **đúng một**
`@/components/ui/dialog.tsx` hiện có cho mọi kích thước màn hình; trên `< 640px` style nó trồi lên
từ dưới bằng CSS (`data-[state=open]:slide-in-from-bottom`, Radix Dialog hỗ trợ sẵn qua
`Content`'s animation classes) thay vì `zoom`/`fade` giữa màn hình. Một component, hai giao diện qua
CSS — không hai thư viện.

**Chip sự kiện** (cả hai breakpoint): nền nhạt màu nguồn + chữ đậm cùng ramp (`--rose-100`/`--rose-700`
kiểu, tra qua map §5.2), 12px, cắt một dòng bằng `text-overflow: ellipsis`. **Chip task**: kiểu khác
hẳn để không lẫn với buổi thật — viền đứt nét (`border: 1px dashed`), chữ `--text-secondary`, nền
trong suốt; task đã hoàn thành thêm `text-decoration: line-through` (đồng bộ cách `TasksScreen.tsx`
đánh dấu task xong). Task chip **thừa hưởng lọc riêng tư có sẵn**: `task.__privacy_gate__` đã là
`Gate.APPLIES` từ trước 010b (`models.py:103`), và dữ liệu chip lấy từ đúng danh sách `GET
/api/tasks` mà §4.2 đã fetch cho dialog — nghĩa là khi phiên khoá riêng tư, task riêng tư tự biến
mất khỏi cả chip lẫn dialog **mà không cần thêm logic nào ở 010b**; chỉ cần chắc chắn chip dùng
chung một nguồn dữ liệu với dialog, không fetch lại bằng đường khác.
Toàn bộ đổi cao gấp đôi trên mobile đánh đổi lấy **ít tuần hiện cùng lúc hơn khi cuộn** — chủ đã
chọn ưu tiên đọc được chữ hơn mật độ, ghi lại để không ai "tối ưu ngược" sau này.

**Đích chạm cả ô ngày ≥ 44×44** (`qa-framework.md:70`) — đo thật sau full-bleed (trên), không suy
từ phép tính. Đo bằng `getBoundingClientRect()`.

**Hôm nay**: viền + nền `--accent` nhạt, giống app cũ. **Ngày tháng khác** trong lưới tháng: chữ mờ
(token `--muted-foreground`), **không** dùng `n-400` cho chữ (`ui-brief.md` §6.5, `index.css:34-35`
tự ghi chú `n-400` "KHÔNG dùng cho chữ").

**Dấu ngày đặc biệt** (`day_annotation`) hiện thành một dải nhỏ ở **đỉnh ô**, khác hẳn chip sự kiện
về hình dạng để không nhầm — có `label` trên desktop, chỉ có màu trên mobile. **Annotation nhiều
ngày** (`ends_on > starts_on`) hiện thành dải lặp lại ở đỉnh mỗi ô nó phủ qua — **không** cố vẽ một
thanh liền mạch bắc qua nhiều ô của `DayCell.tsx` (mỗi ô độc lập, không biết ô lân cận); nếu dải này
bắc qua biên tuần, nó lặp lại y hệt ở hàng tuần kế — đúng cách chip sự kiện đã xử lý biên tuần.
**Nhiều annotation trùng ngày**: xếp chồng theo thứ tự tạo, tối đa 2 dải hiện đủ + số đếm `+N` nếu
nhiều hơn (cùng ngôn ngữ gấp-lại đã dùng cho chip sự kiện desktop).

> ✅ **§8 mục 1+2 đã chốt 2026-08-01** qua bản mẫu chạy được (không mô tả bằng chữ, đúng luật
> `feedback-visual-draft-before-lock`) — phương án C + task hiện thành chip, đúng bảng trên. Vẫn giữ
> nguyên tắc thi công: mọi logic render ô ngày nằm gọn trong **một** component `DayCell.tsx` với
> props rõ ràng (`events`, `tasks`, `variant` không còn cần thiết vì chỉ còn một phương án — nhưng
> giữ props tách bạch `events`/`tasks`/`annotations` để test từng loại độc lập, §7).

### 5.5 Dialog chi tiết ngày

Chạm/bấm một ô ngày ⇒ mở `frontend/src/DayDetailDialog.tsx` — **một** component cho mọi kích thước
màn hình (§5.4). Nội dung, theo thứ tự:

1. Ngày dạng đầy đủ tiếng Việt, ví dụ **`Thứ Bảy, 15/08/2026`** (sửa lỗi bắt bởi T2: bản nháp đầu
   ghi nhầm `Thứ Năm` — 15/08/2026 thật sự là Thứ Bảy; dùng ví dụ này đúng để executor không copy
   nhầm chữ sai vào code/test).
2. **Dấu ngày đặc biệt** của ngày đó — sửa/xoá tại chỗ, và nút **"+ Đánh dấu ngày này"** (mở
   `AnnotationForm.tsx`: `label`, `note_md`, `color`, khoảng ngày, cộng checkbox **"Riêng tư"** —
   tái dùng nguyên component/label của `NoteForm.tsx:65-71` (`Checkbox` + span `"Riêng tư"`), không
   tự vẽ control mới. Khi phiên đang khoá riêng tư, checkbox này **disable + gợi ý "mở khoá riêng tư
   để đặt"**, cùng hành vi `NoteForm` đã có với `is_private` — kiểm chéo trước khi copy để không lệch
   UX giữa hai form).
3. **Buổi** trong ngày, sắp theo giờ: giờ · tiêu đề · địa điểm · chấm màu nguồn (tra từ map §5.2).
   Bấm một buổi ⇒ mở `EventForm` của `010a`. **Hợp đồng props của `EventForm` mà 010b cần** (010a
   §5 chỉ nói tên file, chưa định props — bắt bởi T2, đây là phần bổ sung chốt cho cả hai spec):
   `open: boolean`, `onOpenChange: (open: boolean) => void`, `initialEvent?: EventRead` (có ⇒ chế
   độ sửa, không ⇒ tạo mới), `defaultDate?: string` (điền sẵn ngày khi tạo mới từ dialog), `allowedSourceIds?: string[]`
   (010b truyền danh sách nguồn `kind='manual'` để giữ đúng luật `010a` §2 mục 7 — chỉ chọn được
   nguồn thủ công), `onSuccess?: () => void`. Nếu `EventForm` hiện tại của 010a chưa có props này,
   **010b phải bổ sung khi thực thi** (đây là mở rộng tương thích-ngược, không phải sửa hành vi khoá
   của 010a). Buổi thuộc nguồn `ics` vẫn hiện cảnh báo một dòng "sửa tay sẽ mất khi nhập lại"
   (`010a` §2 mục 7).
4. **Task đến hạn ngày đó** (`status=all`, §4.2) — tiêu đề + trạng thái (gạch ngang nếu đã xong,
   cùng quy ước `TasksScreen.tsx` hiện có), bấm ⇒ mở form task hiện có.
5. Nút **"+ Thêm buổi vào ngày này"** (mở `EventForm` với `defaultDate` điền sẵn,
   `allowedSourceIds` chỉ gồm nguồn `kind='manual'`) và **"Dời một việc sang ngày này"** (§5.6,
   dùng `status=open`).

**Luật cứng:** nếu desktop có thêm tooltip hover trên chip sự kiện, nó **không được** chứa gì mà
dialog không có. `ui-brief.md` §9(a) cho phép tooltip tồn tại **chỉ vì** có đường chạm thay thế đủ
giàu — nếu tooltip biết gì mà dialog không biết, luật đó gãy và đây thành đúng lỗi `018` đã bắt.

`data-testid`: `calendar-day-cell` · `calendar-day-chip-event` · `calendar-day-chip-task` ·
`calendar-day-dialog` · `calendar-day-add-event` · `calendar-day-add-annotation` ·
`calendar-day-move-task` · `calendar-annotation-form`.

### 5.6 Dời việc — chạm là đường chính, kéo-thả là bonus của desktop

`forward-spec.md` §B có hai mục liên quan: *"Reschedule nhanh task trễ hạn → hôm nay / mai / ngày
kia"* và *"quick-add + kéo-thả vào ô ngày"*. Chúng **không cùng mức ưu tiên**, và thứ tự này là quyết
định, không phải gợi ý:

1. **BẮT BUỘC — dời bằng chạm, hai lối vào.**
   - Trong `DayDetailDialog`: "Dời một việc sang ngày này" ⇒ danh sách task `status=open` (quá hạn
     lên trước, sắp `due_at` ⇒ `created_at`) ⇒ chọn ⇒ `PATCH /api/tasks/{id}` với `due_at` = ngày
     đó lúc `23:59:00+07:00`.
   - **Trên `TasksScreen.tsx`** (sửa file này, §2 mục 1): mỗi thẻ task **quá hạn** có thêm ba nút
     nhanh **Hôm nay · Mai · Ngày kia** — đây chính là mục `forward-spec.md` §B, làm được **mà
     không cần mở lịch**. `data-testid`: `task-reschedule-today` / `task-reschedule-tomorrow` /
     `task-reschedule-day-after`.
2. **TUỲ CHỌN — kéo-thả, chỉ `≥ 640px`.** HTML5 drag-and-drop **không chạy trên iOS Safari**; làm
   được trên mobile thì phải tự dựng bằng Pointer Events, và nó đắt hơn giá trị. Vì mục 1 đã phủ
   đủ chức năng trên mọi thiết bị, kéo-thả là **cải thiện tốc độ cho desktop**, không phải đường duy
   nhất tới bất cứ việc gì — đúng luật `ui-brief.md` §6.6 / `qa-framework.md:61`. **Nếu thiếu thời
   gian, cắt mục 2 trước, không cắt mục 1.**
3. **Xác nhận sau khi dời bằng toast + Hoàn tác — và chấp nhận tường minh rủi ro ghi-đè-sau-cùng.**
   (Bắt bởi T2: nếu chủ dời task A→B rồi lại tự sửa B→C từ một chỗ khác trước khi bấm Hoàn tác trên
   toast cũ, Hoàn tác sẽ đưa `due_at` về A, âm thầm xoá mất lựa chọn C.) Đây là app một-người-dùng,
   một thiết bị hoạt động tại một thời điểm — rủi ro này **thấp và được chấp nhận có ý thức**, không
   phải bị bỏ sót: không xây khoá phiên bản (`version`/`updated_at` so sánh) cho một thao tác nhỏ
   như dời hạn. **Chốt hành vi:** toast tự ẩn sau 8 giây (đủ ngắn để giảm cửa sổ va chạm, đủ dài để
   bấm kịp), nút Hoàn tác gọi lại `PATCH` với `due_at` cũ đã lưu trong state của toast lúc dời —
   **không** gọi GET lại trước khi Hoàn tác (thêm round-trip cho một rủi ro đã chấp nhận là không
   đáng). Dời hạn vẫn là hành động đảo ngược được bằng một `PATCH` nữa nếu chủ tự nhận ra, nên đây
   là chỗ toast **đúng chỗ** — ghi rõ để không ai đọc `010a` §2 mục 5 rồi tưởng dự án cấm toast.

## 6. Không được làm

- Không sửa `backend/app/core/ics.py`, `backend/app/domain/calendar.py`,
  `backend/app/web/routers/calendar.py` — 010a đang chạy production (§2 mục 1). Cần sửa ⇒ **dừng và
  báo**.
- Không sửa `backend/app/domain/tasks.py` / `backend/app/web/routers/tasks.py`, **không** nới
  `le=100` (§4.2).
- Không thêm endpoint `move-task` hay bất kỳ đường ghi task nào ngoài `PATCH /api/tasks/{id}`.
- Không để bất kỳ `useQuery` nào của 010b poll theo giây — **mọi** query mới phải khai
  `refetchInterval: false` tường minh (§2 mục 8). Đừng dựa vào giá trị mặc định của app.
- Không dùng chiều cao cứng cho hàng tuần / ô ngày (`ui-brief.md` §6.3, §1 bảng trên).
- Không dùng cỡ chữ < 12px ở bất kỳ đâu, kể cả chip và mini-nav (`ui-brief.md` §6.4).
- Không để thông tin nào **chỉ** tới được bằng hover (`ui-brief.md` §6.6). Tooltip desktop (nếu có)
  phải là tập con của dialog.
- Không hardcode màu; dùng token có sẵn (`--accent`, `--accent-foreground`, …) hoặc
  `SOURCE_COLORS` (`010a` §5) — **không** bịa token mới như `--primary-light` (§5.3).
- Không thêm shadcn `Sheet` hay bất kỳ primitive dialog thứ hai nào — một `Dialog`, style theo
  breakpoint bằng CSS (§5.4).
- Không cài thư viện lịch (`react-big-calendar`, `fullcalendar`, `@schedule-x/*`…): chúng mang theo
  CSS riêng, mô hình sự kiện riêng và luật timezone riêng — ba thứ dự án này đã chốt khác đi. Lưới
  tháng + `IntersectionObserver` là ~250 dòng tự viết, ít hơn phần code để thuần hoá một thư viện.
- Không cài thư viện kéo-thả nếu chỉ để làm §5.6 mục 2 (bonus desktop). Native HTML5 DnD đủ; thêm
  `dnd-kit` cho một tính năng tuỳ chọn là đổi kích thước bundle lấy một thứ có thể bị cắt.
- Không dựng virtualization (`react-window`…) — cửa sổ 13 tháng ≈ 80 khối DOM là quá nhỏ để cần.
- Không đụng `.ics`, không đụng luồng import, không thêm cột nào ngoài bảng `day_annotation`.
- Không đảo tuần sang bắt đầu Chủ Nhật — giữ Thứ Hai, đúng app cũ (§1 mục 1) và đúng quy ước Việt
  Nam.
- **Không copy file `.ics` thật của chủ vào repo**; trước khi mở PR chạy và dán
  `git status --short --untracked-files=all` + `git ls-files '*.ics'` (`010a` §6).

## 7. Acceptance — kiểm chứng được bằng lệnh

1. `cd backend && uv run ruff check` sạch. **Hai lane, hai lệnh riêng, ghi pass/skip từng lệnh:**
   `uv run pytest -m "not pg"` và `uv run pytest -m pg` (marker `pg` tự skip khi thiếu Postgres —
   `pyproject.toml:37-42`). **`-m pg` phải chạy với 0 skip** — trỏ `NEON_MIGRATOR_URL` vào một
   Postgres cục bộ dùng chung với `010a`/`008`/`009` (không phải Neon: `conftest.py:44-59` tự chối
   host không phải `localhost`/`127.0.0.1`/container CI trừ khi `ALLOW_REMOTE_PG_TESTS=1` — **đừng**
   đặt biến đó chỉ để lách). Dán số pass thật, không chỉ "xanh".
2. `cd frontend && npm run lint && npm test && npm run build` xanh.
3. **Test polling bị tắt (`npm test`, không cần DB):** dựng `QueryClient` test với `refetchInterval`
   mock đếm số lần gọi; mount `CalendarScrollView` (mock API); đợi 3 giây thật (`vi.useFakeTimers` +
   advance) ⇒ **mỗi query tháng/annotation/nguồn được gọi đúng 1 lần**, không tăng theo thời gian.
   Đây là lưới duy nhất bắt lại lỗi CRITICAL đã sửa ở §2 mục 8 nếu ai đó xoá `refetchInterval: false`
   trong một lần refactor sau này.
4. **Test `day_annotation` (`-m pg`)**: tạo dấu 20/08–25/08 ⇒ hỏi `from=2026-08-24&to=2026-08-24`
   **vẫn trả về** (giao nhau bao gồm hai đầu, §4.1 — đây là ca `<`/`>` sẽ trượt còn `<=`/`>=` thì
   không); tạo với `ends_on < starts_on` ⇒ `422` **không** `500`; `PATCH` chỉ gửi `starts_on` mới
   khiến `starts_on > ends_on` hiện có ⇒ **`422`** (ca ghép-rồi-kiểm ở tầng store, không phải DTO
   đơn thuần); `PATCH {"label": null}` ⇒ `422`, **không** `500`; trùng `id` khi `POST` ⇒ `200` + bản
   cũ, không tạo bản hai; `PATCH {"color": null}` ⇒ màu bị xoá thật (`model_fields_set`); `label`
   toàn khoảng trắng ⇒ `422`.
   **4b. Test cổng riêng tư (`-m pg`, §2 mục 4):** tạo một dấu `is_private=true` ⇒ phiên **đã** mở
   khoá riêng tư thấy nó trong `GET /annotations`; cùng phiên đó **khoá lại** (hoặc một phiên mới
   chưa mở khoá) gọi lại cùng khoảng ngày ⇒ dấu đó **biến mất khỏi kết quả** — đây là test duy nhất
   chứng minh `readable()` thật sự lọc, không phải gọi cho có; `PATCH {"is_private": true}` một dấu
   đang công khai ⇒ đọc lại ngay sau (cùng phiên, đã mở khoá) vẫn thấy — patch riêng tư không tự
   khoá phiên hiện tại.
5. **Test 401 (`-m pg`)**: gọi cả 4 endpoint annotation không cookie ⇒ `401`. Vòng lặp qua cả bốn,
   đừng kiểm mẫu một cái.
6. **Test thuần `calendar-scroll.ts` (`npm test`, không cần DB)** — đây là chỗ logic thật sự nằm:
   ⓐ sinh danh sách tuần cho tháng 02/2026, **tuần bắt đầu Thứ Hai** (§1 mục 1, §6) ⇒ số hàng và
   ngày đầu/cuối đúng cho **đúng một** quy ước rõ ràng (test phải khẳng định con số, không để mơ hồ
   Chủ Nhật-đầu-tuần lọt qua) · ⓑ gom sự kiện theo ngày với một buổi `23:30+07:00` ⇒ rơi vào **đúng
   ngày đó**, và **một buổi khác vào khung 00:00–06:59+07:00** ⇒ cũng rơi đúng ngày (ca lệch múi giờ
   dễ trượt nhất, bắt bởi T2) — cả hai test này phải **chạy được với `TZ=UTC`** cho kết quả y hệt ·
   ⓒ một buổi 23:00–01:00 bắc qua nửa đêm ⇒ hiện ở **cả hai** ngày · ⓓ dấu 20/08–25/08 ⇒ hiện ở đủ
   6 ngày · ⓔ khoảng fetch của tháng là nửa mở `[đầu tháng, đầu tháng kế)` — không chồng lấn, không
   hở một ngày · ⓕ **dedupe theo `id`**: một buổi bắc qua biên tháng xuất hiện trong kết quả của cả
   hai query tháng liền kề ⇒ sau khi gộp chỉ còn **một** bản ghi, không đếm hai lần ở `+N` (§5.2) ·
   ⓖ **gộp chip (§5.4)**: một ngày có 3 buổi + 2 task ⇒ ở mobile (giới hạn 2) danh sách hiện là
   `[buổi 1, buổi 2]` + `+3` (buổi thứ 3 và cả 2 task gộp vào `+N`, **không tách** "+N buổi"/"+N
   task"); ở desktop (giới hạn 3) là `[buổi 1, buổi 2, buổi 3]` + `+2` · ⓗ một ngày có 0 buổi + 1
   task ⇒ chip hiện đúng 1 phần tử, kiểu task (viền đứt), không có dòng `+N`.
7. **e2e Playwright** `frontend/e2e/calendar-scroll.spec.ts` — chạy `npm run e2e` (script thật,
   `package.json:9`), dán output. Chia rõ theo `project` (`mobile` = `390×844` + `hasTouch:true`,
   `desktop` = `1280×800`, không chạm — `playwright.config.ts:18-37`):
   - **`mobile`**: mở tab Lịch ⇒ tự ở tuần chứa hôm nay (không phải đầu danh sách), đo bằng
     `window.scrollY === 0` (khung cuộn nội bộ nhảy, trang không nhảy — §5.2) · `page.tap` một ô
     ngày ⇒ dialog mở, đóng được bằng chạm ra ngoài · thêm dấu ngày từ dialog ⇒ thấy nó trên ô ngày
     sau khi đóng · dời một task từ dialog ⇒ toast có nút Hoàn tác, bấm Hoàn tác ⇒ hạn về chỗ cũ ·
     `calendar-mininav*` **không tồn tại trong DOM hoặc `display:none`** (khẳng định mini-nav thật
     sự ẩn, không chỉ tin bảng ở §5.4).
   - **`desktop`**: bấm một ô mini-nav ⇒ lịch chính nhảy tới tuần đó · cuộn xuống ⇒ nhãn tháng ở
     header đổi theo, đo bằng so **giá trị text trước/sau**, không suy luận cơ chế IntersectionObserver
     · chuyển `Lịch` ↔ `Danh sách` ⇒ lựa chọn sống qua reload · trên `TasksScreen`, một task quá hạn
     có đủ ba nút `task-reschedule-*` và bấm "Hôm nay" đổi `due_at` đúng.
   - **Cả hai project**: một buổi thuộc nguồn `ics` mở từ dialog ⇒ thấy cảnh báo "sửa tay sẽ mất".
8. **Đo đích chạm bằng số, không bằng mắt** — ở project `mobile` (390×844), `page.evaluate` lấy
   `getBoundingClientRect()` của `calendar-day-cell` ⇒ khẳng định **≥ 44×44**. Ở project `desktop`,
   đo `calendar-mininav-day` ⇒ **≥ 24×24**. **Không đo mini-nav ở `mobile`** — nó ẩn ở đó, phép đo
   sẽ ra `0×0` và không chứng minh gì (sửa lỗi test-không-thể-pass của bản nháp đầu). Dán số thật
   vào PR.
9. **Đo cỡ chữ bằng số, ở CẢ HAI viewport** (sau chốt 2026-08-01, mobile cũng có chip chữ — bảng
   §5.4) — `getComputedStyle(...).fontSize` của `calendar-day-chip-event`, `calendar-day-chip-task`
   và nhãn dấu ngày ⇒ **không cái nào < 12px**, ở cả `mobile` lẫn `desktop` (`ui-brief.md` §6.4; app
   cũ ở 9px, §1). Dán số thật vào PR cho cả hai project.
10. **Không hover-only**: khẳng định e2e ở `mobile` đi trọn đường **chỉ bằng `page.tap`** (không
    `hover`, và `hover` cũng không được dùng ở project `desktop` như đường *duy nhất*): ô ngày →
    dialog → chi tiết một buổi. Nếu có tooltip desktop, khẳng định nó **không** chứa gì mà dialog
    không có (`ui-brief.md` §9a).
11. **Test trạng thái lỗi (`npm test` hoặc e2e với route mock trả lỗi)** — theo `qa-framework.md`
    §4 (bộ trạng thái bắt buộc): một trong 13 query tháng trả `500` ⇒ tháng đó hiện một dòng lỗi
    nhỏ tại chỗ (không phải toàn màn trắng, không phải nuốt lỗi im lặng), các tháng khác vẫn hiện
    bình thường; query annotation lỗi ⇒ lưới vẫn hiện được (annotation là lớp phủ, không phải điều
    kiện tiên quyết); trang mở lại khi mất mạng (route mock timeout) ⇒ hiện dữ liệu cache cũ kèm một
    dấu hiệu "có thể chưa mới nhất", không phải màn trắng.
12. Migration `0006` áp lên Neon **bằng tay**, xác minh bằng truy vấn thật vào
    `information_schema.columns` **và** `pg_constraint` (thấy `day_range`) — dán output vào PR.
    *"Merge ≠ migration applied"* (`CLAUDE.md`). Thứ tự: áp → xác minh → **rồi mới** merge.
13. `gh pr checks <PR>` — **dán nguyên output**, mọi job xanh, không job nào pending. Đừng viết
    "đủ N required check": `ci.yml` khai 7 job và file repo không cho biết job nào đang được đặt
    required trên GitHub.
14. **Báo cáo tách rõ ĐÃ CHẠY / CHƯA CHẠY** (`agent-tasks/README.md` §25-40). Phần chắc chắn nằm ở
    vế "chưa chạy" và phải nói thẳng để QA T3 biết soi vào đâu: **cảm giác cuộn thật trên iPhone**
    (quán tính, sticky header, dialog vs bàn phím ảo) và **kéo-thả trên chuột thật**. e2e phủ được
    *logic*, không phủ được *cảm giác*. Cũng nói rõ: lưu lượng request thật khi chủ để tab Lịch mở
    hàng giờ (§7.3 chỉ test 3 giây trong môi trường giả lập thời gian) — đề nghị QA T3 mở DevTools
    Network trong một phiên dùng thật và đếm request/phút.

## 8. Việc của CHỦ — cả ba mục đã chốt 2026-08-01

- [x] **1. Cách trình bày ô ngày mobile.** Chốt qua bản mẫu chạy được: **phương án C** — ô cao gấp
      đôi, tối đa 2 chip có chữ. Xem §5.4.
- [x] **2. Task có hiện thành chip trên lịch không.** Chốt: **có** — chip viền đứt, gộp chung thứ tự
      với chip sự kiện (buổi trước, task sau), thừa hưởng lọc riêng tư có sẵn của `task`. Xem §5.4,
      §4.2.
- [x] **3. `day_annotation` gác riêng tư ngay từ đầu.** Chốt — làm luôn trong migration `0006`
      (`Gate.APPLIES` + cột `is_private`), không đợi retrofit. Xem §2 mục 4, §3, §4.1, §5.5, §7.4b.

**Không còn mục nào chờ chủ — sẵn sàng giao Codex sau khi gộp PR (xem tin nhắn kế tiếp).**

Ngoài ra, giống `010a`: không cần bật dịch vụ nền nào mới; migration `0006` **Codex tự chạy** bằng
`NEON_MIGRATOR_URL` sẵn có, **áp trước khi merge** (§3, cùng lý lẽ `010a` §8).

## 9. Còn lại sau 010b

- **Quick-add task bằng cách gõ thẳng vào ô ngày** (`forward-spec.md` §B) — 010b chỉ làm *dời* việc
  đã có, chưa làm *tạo* việc từ lịch. Để sau vì nó cần một luồng nhập gọn mà chưa có bản mẫu.
- **Task hiện thành chip trên ô ngày** — treo ở §8 mục 2.
- **Lịch làm nguồn ngữ cảnh cho AI Bước 1** — retrieval trên `calendar_event` + `day_annotation`.
  **Sau quyết định 2026-08-01 (§2 mục 4), chỉ `calendar_event` còn `Gate.NONE`** — `day_annotation`
  giờ theo đúng R1–R7 như `note` (khoá ⇒ lọc, riêng tư trong ngữ cảnh ⇒ ép zdr). `calendar_event`
  một mình vẫn là **corpus dễ nhất** để cắm AI vào đầu tiên; `day_annotation` nhập vào cùng lúc với
  `note` khi AI Bước 1 xử lý nội dung riêng tư, không sớm hơn. Ghi lại vì nó ảnh hưởng thứ tự của
  `011`/`012`.
- **`010b` xong là đóng slice 010**; hàng đợi tiếp theo `011 → 012 → 008h` (`CLAUDE.md`).

## 10. Dấu vết phản biện

Hai lượt review đối kháng chạy trên **spec + code thật**, 2026-08-01: T3 (`agy-bridge`,
`gemini-3.1-pro-high`, cộng một lượt sơ bộ tự động route vào `gemini-3.6-flash-high` trước đó — cả
hai hội tụ vào cùng lỗi mini-nav/mobile) và T2 (Codex `gpt-5.6-sol`). Phát hiện nặng nhất là
**CRITICAL** ở §2 mục 8 (polling storm) — do T2 bắt, T3 không thấy (T3 không đọc `main.tsx`). Điểm
đã cân nhắc và **cố ý không đổi**, để lượt sau không mở lại:

| Điểm bị nêu | Xử lý | Lý do |
|---|---|---|
| T2: đo mini-nav touch-target ở viewport mobile khiến test không thể pass (`0×0`) | **Fold** | Chuyển phép đo sang project `desktop` (§7.8); mini-nav vốn ẩn trên mobile theo đúng thiết kế, đây không phải lỗ hổng che giấu mà là chỗ mô tả test sai viewport. |
| T2: `24×24` là "ngưỡng WCAG tuyệt đối" — không hoàn toàn đúng theo văn bản WCAG 2.5.8 gốc | **Fold, sửa chữ** | Đổi thành "luật riêng của dự án, chặt hơn WCAG gốc" (§5.3) — đúng tinh thần `qa-framework.md:71` vốn đã tự nhận là ngưỡng nội bộ, không đổi hành vi. |
| T2: nên xây khoá phiên bản (`version`/so sánh `updated_at`) để undo-toast không ghi đè lựa chọn mới hơn | **Không làm, chấp nhận rủi ro có ghi lại** | §5.6 mục 3 — app một-người-dùng một-thiết-bị-hoạt-động-tại-một-thời-điểm; chi phí khoá phiên bản cho một thao tác dời-hạn nhỏ không tương xứng. Ghi lại tường minh thay vì im lặng bỏ qua. |
| T2: "13 tháng ≈ 57 hàng" sai số học | **Fold, sửa số** | Số đúng đo bằng `calendar.monthcalendar` là 67 hàng + 13 header = 80 khối (§5.2). Kết luận không virtualize không đổi, chỉ số liệu minh hoạ sai bị sửa. |
| T2: mini-nav app cũ ở bên trái, luôn 2 tháng — spec cũ ghi sai vị trí/số tháng | **Fold, sửa mô tả + giữ 2 tháng cho bản mới** | §1 mục 2 — sửa lại đúng quan sát về app cũ; bản mới vẫn đặt bên **phải** làm lựa chọn bố cục có chủ ý (ghi rõ đây là đổi có chủ đích, không phải nhầm lẫn tiếp). |
| T3 (cả hai lượt): mini-nav test 390px | Trùng với T2 finding trên | Đã fold một lần. |
