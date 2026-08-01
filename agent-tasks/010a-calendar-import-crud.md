# 010a — Calendar slice, tầng nền: migration + parser `.ics` + CRUD + màn danh sách

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L2
> · Skill gợi ý: không cần · MCP cần: không cần.** Đã qua **2 lượt phản biện đối kháng** trên spec +
> code thật (2026-08-01): T3 `gemini-3.1-pro-high` (12 finding, fold 11, bác 1 có lý do — §4.2) và
> T2 `gpt-5.6-sol` (22 finding + 4 claim sai + danh sách lỗ hổng acceptance; fold gần hết, hạ mức 1,
> bác 0 — dấu vết ở §10). Ba loại hỏng nặng nhất đều là **sai im lặng**: `astimezone` trên naive
> datetime lệch 7 tiếng *chỉ trên Fly*; một file rác parse ra 0 buổi **xoá sạch nguồn đang tốt** rồi
> báo thành công; `list_events` lọc kiểu `BETWEEN` làm biến mất buổi bắc qua biên khoảng nhìn.
> **Trạng thái: chủ đã duyệt 2026-08-01 — sẵn sàng giao Codex.**

## 0. Bối cảnh — vì sao 010 bị tách đôi, và 010a là nửa nào

`calendar_source` / `calendar_event` đã có đủ ở tầng schema (`backend/app/domain/models.py:229-269`,
migration `0001`) nhưng **chưa có một dòng domain / router / UI nào**. Khác `009` (chép khuôn từ
Task), 010 là **đất trống**: parser `.ics`, ngữ nghĩa re-import, và một giao diện lịch trực quan —
không có bản mẫu nào trong repo để mirror.

**Chốt với chủ 2026-08-01:** 010 tách làm hai lô, vì gộp lại nó to ~2,5× `009` và nửa sau còn đụng cả
domain `task` (kéo-thả đổi hạn) — một PR như thế không phản biện kỹ được, và nếu phần UI hỏng thì
phần import cũng nằm chờ theo.

- **010a (file này)** — migration, parser `.ics`, CRUD nguồn + buổi, màn hình **danh sách** đủ dùng.
  Đích: chủ import được 4 file lịch thật, xem được, sửa được, xoá được.
- **010b (spec riêng)** — lịch **cuộn liên tục** kiểu Outlook + thanh bên mini-lịch + quick-add
  + kéo-thả đổi hạn task + đánh dấu ngày đặc biệt. Dàn ý ở §9.

**Ba quyết định phạm vi đã chốt với chủ 2026-08-01 (không hỏi lại):**
1. **Bỏ hẳn đường `.xlsx`.** Lịch thi của trường xuất được `.ics` với đủ metadata, nên toàn bộ logic
   Excel mô tả ở `docs/v1-reference.md:14-15` (dò header 10 dòng đầu, map cột kiểu mờ, "ca 1/sáng"→
   07:00, tự gắn tiền tố `[THI]`) **hết lý do tồn tại**. Đo thêm trên file thật `LichThi.xlsx`: cột
   ngày lúc là chuỗi `28/05/2026`, lúc là số serial `46087.00034722222` — bẩn hơn hẳn `.ics` cùng kỳ,
   mà nội dung thì trùng nhau (8 ca thi ↔ 8 `VEVENT`).
2. **Tạo/sửa/xoá buổi thủ công làm đủ ngay trong 010a** (`calendar_source.kind = 'manual'`).
3. **Thêm cột mô tả** cho `calendar_event` (§3) — xem §1 mục 3 để biết mất gì nếu không có.

## 1. Sự thật đo được về file `.ics` thật — đọc kỹ, đây là chỗ dễ sai nhất

Đo ngày 2026-08-01 trên **4 file thật** của chủ (`C:\Users\os\Desktop\TKB-QLDT20252.ics`,
`LichThi-QLDT-20252.ics`, `LichThi-QLDT-20251.ics`, `TKB-QLDT20261.ics`), nguồn phát hành
`qldt.ptit.edu.vn`. Đây là **quan sát**, không phải suy luận từ chuẩn RFC:

1. **Không có múi giờ, ở đâu cả.** Mọi mốc đều dạng `DTSTART;VALUE=DATE-TIME:20260113T070000` —
   không hậu tố `Z`, không tham số `TZID`. Đếm được **0** lần xuất hiện của `TZID`, `Z`-suffix trên
   cả 4 file ⇒ toàn bộ là giờ trôi nổi (floating), phải tự ép về giờ Việt Nam.
2. **Không có `RRULE`.** Đếm được **0**. Mọi buổi đã được liệt kê sẵn từng cái một (139 / 164 / 8 / 6
   `VEVENT`) ⇒ **không cần engine giãn lịch lặp**. Đừng cài thư viện chỉ để phòng xa.
3. **`DESCRIPTION` nhiều dòng nhưng KHÔNG fold đúng chuẩn.** File lịch thi ghi:
   ```
   DESCRIPTION:Mã môn: <mã>
   Nhóm thi: <nhóm>
   Tổ thi: <tổ>
   Hình thức: <hình thức>
   Thời gian: <số> phút
   Kỳ thi: <tên kỳ>
   DTSTAMP;VALUE=DATE-TIME:20260801T151010
   ```
   Kiểm bằng `cat -A`: các dòng nối **bắt đầu ở cột 0, không có dấu cách/tab đầu dòng** — tức sai
   RFC 5545 §3.1. Hệ quả đã đo trên app cũ: `app/importers/ics_importer.py:122-126` tách mỗi dòng
   theo dấu `":"` đầu tiên, nên `Nhóm thi: …` biến thành *thuộc tính* tên `Nhóm thi`, và
   **5 trong 6 dòng metadata bị nuốt im lặng** — app cũ chỉ giữ được `Mã môn: …`. Không lỗi, không
   cảnh báo, chỉ mất chữ.
   **⇒ Luật parse bắt buộc:** một dòng chỉ được coi là *content line mới* khi phần trước dấu `":"`
   đầu tiên, sau khi bỏ tham số sau `";"`, **nằm trong danh sách tên thuộc tính biết trước** (§4.1).
   Không khớp ⇒ **nối vào giá trị của thuộc tính liền trước, ngăn bằng `\n`**. Vẫn phải xử lý cả kiểu
   fold chuẩn (dòng bắt đầu bằng space/tab ⇒ nối, **không** thêm `\n`) vì file nguồn có thể đổi cách
   xuất bất cứ lúc nào.
   **Vì sao danh-sách-biết-trước chứ không phải regex `^[A-Za-z0-9-]+:`** (bắt bởi lượt phản biện T3,
   2026-08-01): một dòng mô tả bình thường như `Note: mang thẻ` hay `Room: 304` **khớp regex đó**, và
   parser sẽ coi nó là thuộc tính mới ⇒ cắt cụt phần mô tả còn lại, **im lặng, không lỗi** — đúng
   loại hỏng mà cả mục này sinh ra để chặn. Đo trên 4 file hiện tại thì hai luật cho kết quả **giống
   hệt nhau (0 dòng lệch)**; whitelist là bảo hiểm cho lần trường đổi cách xuất, giá gần bằng 0.
4. **`UID` chỉ là số thứ tự.** `UID:0@qldt.ptit.edu.vn-20252`, `UID:1@…`, `UID:2@…`. Thêm hoặc bớt
   một môn ở đầu học kỳ là **mọi UID phía sau lệch hết** ⇒ **UID không dùng làm khoá chống trùng
   được**, dù nó trông đúng như một khoá. `DTSTAMP` cũng vô dụng cho việc này: nó là giờ bấm nút
   xuất file (đo được `20260801T151010` vs `20260801T150909` giữa hai file cùng buổi xuất).
5. **Xuống dòng là LF**, không phải CRLF như chuẩn đòi. Đọc bằng `str.splitlines()` là đủ cho cả hai.
6. **Vài chi tiết nhỏ nhưng phải xử lý:** `SUMMARY;LANGUAGE=en-us:` có tham số ⇒ phải tách tham số
   khỏi tên thuộc tính. `LOCATION:304-A2-304-A2(HN)` lặp tên phòng hai lần — **lưu nguyên văn, không
   tự "làm sạch"** (nguyên tắc `forward-spec.md` §C: lưu full, chỉ cắt lúc hiển thị). Mã hoá tệp là
   UTF-8 không BOM.

## 2. Đã khoá — chép ra code, không mở lại

1. **Calendar KHÔNG có riêng tư, KHÔNG có mã hoá, KHÔNG có xoá mềm.** `models.py:233-234,249-250`
   khai `__privacy_gate__ = Gate.NONE` và `__delete_gate__ = Gate.NONE` cho **cả hai** bảng. Vì thế:
   - Gọi `readable()` / `with_privacy_gate()` / `not_deleted()` lên `CalendarSource`/`CalendarEvent`
     là **hợp lệ nhưng vô nghĩa** — `reading.py:91,102` trả lại nguyên câu truy vấn. Cứ gọi
     `readable()` cho đồng nhất với `tasks.py`/`notes.py`, nhưng **đừng** tự thêm điều kiện lọc nào.
   - **Không dùng `app/core/crypto.py`.** Không có `_sealed()`/`_clear()` trong domain này.
     `tracking-brief.md:206` liệt `calendar_event.*` vào nhóm "cột giữ trần" có chủ đích.
   - **Không có `deleted_at`, không có undo-toast, không có endpoint `/restore`.** Đây là chỗ dễ
     cargo-cult nhất từ 008f/009 — **đừng chép sang**. Xem mục 5 dưới về cái thay thế.
2. **Re-import = xoá sạch buổi của nguồn đó rồi chèn lại**, trong **một transaction**
   (`schema-v1-brief.md` §3-A: *"re-import = thay sạch không nhân đôi"*; `schema-physical-brief.md`
   §D1 đã đặt `ON DELETE CASCADE` sẵn cho quan hệ này). §1 mục 4 vừa cho lý do kỹ thuật độc lập:
   không có khoá ổn định nào để so từng dòng. **Hệ quả phải nói thẳng với người dùng ở UI:** mọi
   chỉnh sửa tay lên buổi *đã import* sẽ mất khi import lại nguồn đó. Buổi thủ công nằm ở nguồn
   `kind='manual'` riêng nên không bị đụng (§2 mục 7 khoá luật này ở tầng API).
3. **Không có version-history của nguồn lịch.** App cũ có `calendar_source_versions` +
   `current_version_id` (`app/services/calendar_view_service.py:30,163-168`); `schema-v1-brief.md`
   §3-A đã chốt **bỏ**. Đừng dựng lại.
4. **Không làm "Don't care 😒" / ẩn từng buổi.** `ui-brief.md:92` chốt ❌ với lý do của chủ: lịch bị
   báo nghỉ thì để nguyên và tự nhớ tốt hơn là ẩn đi. Cột `calendar_event.is_hidden` **có tồn tại**
   trong schema nhưng **010a không đọc, không ghi, không đưa ra DTO** — để nguyên `false`.
   *(Cùng loại với `note.embedding` ở `009`: cột có sẵn cho tương lai, slice này không chạm.)*
5. **Xoá là xoá thật, có hộp thoại xác nhận — không phải undo-toast.** Vì `Gate.NONE` (mục 1) nên
   không có đường xoá mềm mà không đổi schema. Chọn xác nhận-trước thay vì hoàn-tác-sau, ba lý do:
   ⓐ xoá một nguồn kéo theo **hàng trăm** buổi qua CASCADE (139–164 buổi/file thật) — sức công phá
   quá lớn cho một toast 10 giây; ⓑ nguồn sự thật của buổi đã import nằm **ngoài app** (file `.ics`
   chủ tải lại được bất cứ lúc nào), nên mất là mất *công import*, không mất dữ liệu gốc; ⓒ khai
   `Gate.NONE` là lời khai có chủ ý từ `008n`, đổi nó là mở lại một quyết định đã đóng.
   **Hộp thoại phải nói rõ số buổi sẽ mất** ("Xoá nguồn *Lịch học 2025 kỳ 2* và **139 buổi** của nó?
   Không hoàn tác được."). Xoá một buổi lẻ cũng cần xác nhận, nhưng chỉ một dòng.
6. **Giờ Việt Nam ép bằng `timezone(timedelta(hours=7))`, KHÔNG dùng `zoneinfo`.** Việt Nam không có
   DST từ 1975, nên offset cố định là đúng về mặt dữ liệu. Quan trọng hơn: `ZoneInfo("Asia/Ho_Chi_Minh")`
   cần **tzdata của hệ điều hành**, mà image Python slim trong `Dockerfile` không đảm bảo có —
   thiếu nó thì `ZoneInfoNotFoundError` chỉ nổ **trên Fly, lúc chạy thật**, không nổ ở CI hay máy
   Windows. Đúng hình dạng "lỗi chỉ lộ ở tầng executor không chạy được" mà `agent-tasks/README.md`
   §25 cảnh báo. App cũ cũng dùng offset cố định (`ics_importer.py:4`).
7. **🆕 `kind` quyết định thao tác nào hợp lệ — khoá ở tầng API, không phải quy ước miệng.**
   (Bắt bởi lượt phản biện T2: spec cũ chỉ *mô tả* "buổi thủ công nằm ở nguồn manual" mà không cấm
   gì, nên hai executor hợp lý sẽ ship hai hệ khác nhau.) Luật:
   - `POST /sources/{id}/import` vào nguồn `kind='manual'` ⇒ **`409`**, chữ tiếng Việt. Nếu cho phép,
     một lượt import sẽ **xoá sạch buổi chủ tự gõ** qua đúng luồng thay-sạch của mục 2 — mất dữ liệu
     duy nhất **không có bản gốc bên ngoài** để nhập lại.
   - `POST /events` với `source_id` trỏ vào nguồn `kind='ics'` ⇒ **`409`**. Cho phép thì buổi vừa gõ
     sẽ biến mất ở lần import kế tiếp, im lặng, và người dùng sẽ đổ cho "app mất dữ liệu".
   - `PATCH`/`DELETE` một buổi **đã import** thì **cho phép** (nó là dữ liệu tái tạo được), nhưng UI
     phải cảnh báo một dòng: *"Buổi này thuộc nguồn nhập từ file — sửa tay sẽ mất khi nhập lại."*
   - `PATCH /sources/{id}` **không được đổi `kind`**; `EventUpdate` **không được đổi `source_id`**
     (không reparent — cùng lý do `update_item` của Task cấm reparent).

## 3. Migration `0005` — ba cột mới

File mới `backend/alembic/versions/0005_calendar_description_and_visibility.py`,
`down_revision = "0004"` (head hiện tại — kiểm lại bằng `ls backend/alembic/versions/` trước khi
viết, đừng tin con số này nếu thư mục đã khác). Sửa `models.py` khớp, đủ cả `upgrade()` và
`downgrade()`.

| Cột | Bảng | Kiểu | Vì sao |
|---|---|---|---|
| `description_md` | `calendar_event` | `TEXT NULL` | Chứa nguyên văn `DESCRIPTION` **sau khi unfold đúng** (§1 mục 3). Không có nó thì mất Mã môn / Nhóm thi / Tổ thi / Hình thức thi / Thời lượng của mọi ca thi — đúng thứ app cũ đang vô tình đánh rơi. Tên `_md` theo nguyên tắc `schema-v1-brief.md` §3: markdown ở chỗ viết văn xuôi. |
| `is_visible` | `calendar_source` | `BOOLEAN NOT NULL DEFAULT true` | Checkbox bật/tắt từng nguồn (chủ đang dùng thật ở app cũ — `calendar_view_service.py:129-142` lưu xuống DB để sống sót qua restart). Không có cột thì trạng thái này chỉ nằm trong `useState` và mất mỗi lần tải lại trang. |
| `all_day` | `calendar_event` | `BOOLEAN NOT NULL DEFAULT false` | 🆕 Bắt bởi phản biện T2. Không có cột này thì một sự kiện cả ngày (lưu 00:00 → 00:00 hôm sau) **không phân biệt được** với một buổi timed dài đúng 24 tiếng — `010b` sẽ phải render hai thứ như nhau, và không có đường sửa mà không thêm migration lần hai. Thêm bây giờ rẻ hơn thêm sau đúng một migration. |

**Không đụng gì khác.** Cụ thể: **giữ nguyên** CHECK `kind IN ('ics','excel','manual')` dù `'excel'`
từ nay không còn đường nào sinh ra — gỡ một giá trị khỏi CHECK là một migration có rủi ro mà không
đổi lấy gì; ghi một dòng comment trong migration là đủ. **Hệ quả bắt buộc nhớ:** `SourceRead.kind`
phải là `str`, **không** phải `Literal["ics","manual"]` — một row cũ `kind='excel'` gặp `Literal` sẽ
nổ response-validation thành `500` (§4.2).

**Áp bằng tay, không tự động** (`CLAUDE.md`, luật cứng): `cd backend && uv run alembic upgrade head`
với `NEON_MIGRATOR_URL`, rồi **xác minh bằng truy vấn thật** vào `information_schema.columns` —
không dừng ở `alembic current`.

## 4. Backend

### 4.1 `backend/app/core/ics.py` — parser thuần, không chạm DB

File mới, **không import gì từ `app.domain` hay SQLAlchemy**. Đây là điều kiện để test được nó
không cần Postgres (lane `-m "not pg"` của CI).

```python
VIETNAM_TZ = timezone(timedelta(hours=7))   # §2 mục 6 — cố ý không dùng zoneinfo
DEFAULT_DURATION = timedelta(minutes=90)    # v1-reference.md:10
MAX_BYTES = 1_048_576                       # đo trên BYTE, không phải ký tự — xem §4.3
MAX_EVENTS = 5000

@dataclass(frozen=True)
class ParsedEvent:
    title: str
    starts_at: datetime          # luôn tz-aware, +07:00
    ends_at: datetime            # luôn > starts_at
    all_day: bool
    location: str | None
    description_md: str | None

@dataclass(frozen=True)
class ParseReport:
    events: list[ParsedEvent]    # đã bỏ trùng — len(events) là số sẽ được INSERT
    skipped: list[str]           # một dòng/VEVENT bị bỏ, KHÔNG chứa nội dung file (xem dưới)
    duplicates: int              # số VEVENT bị loại vì trùng hệt nhau trong CÙNG một file

def parse_ics(text: str) -> ParseReport: ...
```

**Ngữ nghĩa con số — chốt cứng để receipt UI và test không lệch nhau** (bắt bởi T2: `parsed` cũ có
hai cách đọc): `len(report.events)` = số buổi **sau** khi bỏ trùng = số dòng sẽ `INSERT`.
`ImportReport.parsed` = `len(events) + duplicates + len(skipped)` = tổng số `VEVENT` đọc được trong
file. `ImportReport.inserted` = `len(events)`. Viết thẳng đẳng thức này thành một assert trong test.

Luật thân hàm, theo đúng thứ tự:
- **Kiểm trần TRƯỚC khi làm bất cứ việc gì khác:** `len(text.encode("utf-8")) > MAX_BYTES` ⇒ ném
  `ValueError`. Kiểm bằng **byte**, không bằng `len(text)` — `len()` đếm code point, nên một chuỗi
  1 triệu ký tự tiếng Việt là ~3 MB thật (bắt bởi T2). Đếm số `BEGIN:VEVENT` trước khi parse sâu;
  `> MAX_EVENTS` ⇒ ném `ValueError` ngay, đừng parse rồi mới đếm.
- Tách dòng bằng `splitlines()` (nuốt cả LF lẫn CRLF — §1 mục 5).
- **Unfold hai kiểu** đúng như §1 mục 3: dòng mở đầu bằng space/tab ⇒ nối **không** thêm ký tự;
  dòng có tên thuộc tính **không nằm trong `KNOWN_PROPERTIES`** ⇒ nối kèm `\n`.
  `KNOWN_PROPERTIES = {BEGIN, END, VERSION, PRODID, UID, CLASS, SUMMARY, DESCRIPTION, LOCATION,
  DTSTART, DTEND, DTSTAMP, DURATION, TRANSP, STATUS, CATEGORIES, RRULE, RDATE, EXDATE, SEQUENCE,
  CREATED, LAST-MODIFIED, ORGANIZER, ATTENDEE, URL, GEO, PRIORITY}` cộng mọi tên mở đầu `X-`.
  Tên không biết mà **thật sự** là thuộc tính thì hậu quả chỉ là nó bị nối vào mô tả — hỏng nhẹ và
  nhìn thấy được; ngược lại (dòng mô tả bị coi là thuộc tính) thì mất chữ im lặng. Chọn chiều hỏng
  nhìn thấy được.
  **Nối bằng `list.append()` + `"".join(...)` ở cuối, KHÔNG bằng `buf += line` trong vòng lặp**
  (bắt bởi T2): một `VEVENT` vài trăm nghìn dòng nối vẫn lọt trần 1 MB, và phép `+=` trên chuỗi làm
  việc này thành bậc hai — request treo, không lỗi. Trần theo *kích thước* không chặn được độ phức
  tạp theo *hình dạng*.
- Tách tham số khỏi tên (`SUMMARY;LANGUAGE=en-us` → `SUMMARY`), giữ nguyên phần giá trị.
- **Giải escape của iCal — chỉ cho `SUMMARY`/`DESCRIPTION`/`LOCATION`, và chỉ SAU khi unfold xong:**
  `\n` và `\N` → xuống dòng, `\,` → `,`, `\;` → `;`, `\\` → `\`. Thứ tự quan trọng: giải trước khi
  unfold sẽ đẻ ra ký tự xuống dòng giả rồi làm hỏng vòng unfold. **Đo được 0 lần xuất hiện trên cả
  4 file thật của chủ** — tức đây là luật cho file `.ics` *chuẩn* (Google/Outlook xuất) chứ không
  phải cho dữ liệu hiện có; đừng đầu tư test trên file thật cho nhánh này, hãy phủ bằng fixture.
- Bỏ qua `VEVENT` thiếu `DTSTART` **hoặc** thiếu `SUMMARY` (giữ đúng luật app cũ,
  `v1-reference.md:8`), ghi một dòng vào `skipped`.
- **🆕 `VEVENT` mang `RRULE`, `RDATE`, `EXDATE`, `DURATION`, hoặc `DTSTART;TZID=…` ⇒ BỎ QUA có ghi
  lý do, KHÔNG âm thầm parse phần còn lại.** (Bắt bởi T2.) Năm thuộc tính này có mặt trong
  `KNOWN_PROPERTIES` chỉ để vòng unfold nhận ra chúng là thuộc tính; **nhận ra tên mà bỏ nghĩa** là
  đúng loại sai im lặng cả spec này sinh ra để chặn — một lịch có `RRULE` sẽ import ra **một** buổi
  thay vì 15, và receipt vẫn báo thành công. Dữ liệu thật hiện tại có **0** trường hợp (§1 mục 2),
  nên đây là chi phí bằng 0 hôm nay và là lưới chặn cho ngày trường đổi cách xuất hoặc chủ import
  một file Google Calendar. Ghi vào `skipped` dạng `"Bỏ qua buổi #12: có RRULE (lịch lặp chưa hỗ
  trợ)"` — **số thứ tự `VEVENT`, không phải nội dung**.
- **Ép múi giờ bằng `replace`, KHÔNG bằng `astimezone`.** `datetime.strptime()` trả về datetime
  *naive*; gọi `.astimezone(VIETNAM_TZ)` lên một datetime naive khiến Python hiểu nó là **giờ hệ
  điều hành**, mà container trên Fly chạy **UTC** ⇒ `07:00` thành `14:00+07:00`. Lệch đúng 7 tiếng,
  **chỉ xảy ra trên production**, xanh hết ở CI lẫn máy Windows của chủ. Luật:
  - `YYYYMMDDTHHMMSS` (trôi nổi — toàn bộ dữ liệu thật) ⇒ `dt.replace(tzinfo=VIETNAM_TZ)`.
  - `YYYYMMDDTHHMMSSZ` ⇒ `dt.replace(tzinfo=UTC).astimezone(VIETNAM_TZ)` — ở đây `astimezone` mới
    đúng, vì lúc này datetime đã tz-aware.
  - `YYYYMMDD` (cả ngày) ⇒ `all_day = True`, `starts_at` = `00:00` giờ VN; và **nếu `DTEND` vắng thì
    `ends_at = starts_at + 1 ngày`**, không phải +90 phút (một sự kiện cả ngày bị bóp thành
    00:00–01:30 là dữ liệu sai mà không ai báo).
- `DTEND` thiếu, không parse được, **hoặc `<= DTSTART`** ⇒ `ends_at = starts_at + 90 phút` (trừ
  trường hợp cả-ngày ở trên). *Vế `<= DTSTART` không có trong app cũ và là thứ bắt buộc phải thêm:*
  DB có CHECK `ends_at > starts_at` (`models.py:252`), nên **một buổi dài 0 phút sẽ làm nổ nguyên
  lượt import** chứ không chỉ hỏng dòng đó.
- Trùng hệt nhau trong cùng file (bộ bốn `title|starts_at|ends_at|location` bằng nhau) ⇒ giữ một,
  cộng `duplicates`. *(Không phải chống trùng giữa các lần import — cái đó xử ở §4.2 bằng cách thay
  sạch.)*
- **Chuỗi rỗng và chuỗi toàn khoảng trắng là như nhau:** `title` sau `.strip()` mà rỗng ⇒ coi như
  thiếu `SUMMARY` ⇒ `skipped`. `location`/`description_md` sau `.strip()` mà rỗng ⇒ `None`, không
  phải `""`. (`Field(min_length=1)` một mình **không** chặn `"   "` — bắt bởi T2, và nó mâu thuẫn bộ
  dữ liệu test bắt buộc ở `qa-framework.md:138`.)
- **Không** phân loại `class`/`exam`: app cũ có `event_type` (`ics_importer.py:96-102`) nhưng schema
  mới không có cột đó, và **không cần** — chủ import lịch học và lịch thi thành **hai nguồn riêng,
  mỗi nguồn một màu**, đó chính là cách phân loại. Đừng thêm cột.

**🆕 `skipped` KHÔNG được chứa nội dung file.** (Bắt bởi T2.) Mỗi phần tử là một câu do ta viết,
tham chiếu `VEVENT` bằng **số thứ tự** (`"Bỏ qua buổi #7: thiếu tiêu đề"`). Cấm nhét nguyên dòng
`.ics`, cấm `str(ValueError)` từ `strptime` (nó in nguyên chuỗi giá trị vào response — khuôn
`tasks.py` router:147 chuyển thẳng `str(error)` ra ngoài, cargo-cult chỗ này là rò nội dung file).
Cấm ghi `content` hoặc `filename` vào log/exception. `filename` **không bao giờ** được dùng làm
đường dẫn hay tên file tạm — nó là chuỗi do người dùng gõ, chỉ để hiển thị và làm tên nguồn mặc định.

### 4.2 `backend/app/domain/calendar.py` — DTO + `CalendarStore`

Mirror **cấu trúc** `backend/app/domain/tasks.py` (thứ tự: DTO → exception → store; store không giữ
state, mọi method nhận `db: AsyncSession` và tham gia transaction của request), nhưng **bỏ toàn bộ
nhánh crypto / privacy / soft-delete** theo §2 mục 1.

**DTO — liệt kê đủ field, không để executor tự suy** (spec cũ chỉ nêu tên class; bắt bởi T2):

| DTO | Field | Ghi chú |
|---|---|---|
| `SourceCreate` | `id: UUID \| None` · `name: str` · `kind: Literal["ics","manual"]` · `color: str \| None` | validator `require_uuidv7` **copy nguyên xi từ `TaskCreate`, `tasks.py:70-75`** (seam `008m`). `name` strip rồi mới kiểm rỗng. |
| `SourceUpdate` | `name` · `color` · `is_visible` | `reject_null_required_fields` cho `("name","is_visible")`; **`color` được phép null** = "bỏ màu". **Không có `kind`** (§2 mục 7). |
| `SourceRead` | `id` · `name` · `kind: str` · `color` · `is_visible` · `event_count: int` · `created_at` · `updated_at` | `kind` là **`str`**, không `Literal` (§3). `event_count` để viết câu xác nhận xoá ở §2 mục 5. |
| `EventCreate` | `id: UUID \| None` · `source_id: UUID` · `title: str` · `starts_at` · `ends_at` · `all_day: bool = False` · `location: str \| None` · `description_md: str \| None` | cùng validator `require_uuidv7`. |
| `EventUpdate` | `title` · `starts_at` · `ends_at` · `all_day` · `location` · `description_md` | **không có `source_id`** — cấm reparent (§2 mục 7). `location`/`description_md` nhận null = xoá. |
| `EventRead` | `id` · `source_id` · `title` · `starts_at` · `ends_at` · `all_day` · `location` · `description_md` · `created_at` · `updated_at` | `is_hidden` **không** ra DTO (§2 mục 4). |
| `ImportRequest` | `filename: str` · `content: str = Field(max_length=…)` | xem §4.3 về trần body. |
| `ImportReport` | `parsed: int` · `inserted: int` · `removed: int` · `duplicates: int` · `skipped: list[str]` | ngữ nghĩa từng số khoá ở §4.1. |

Bốn luật DTO không được đoán:
- `EventCreate`/`EventUpdate` phải tự kiểm `ends_at > starts_at` bằng `model_validator` **ngay ở tầng
  DTO** — để buổi thủ công hỏng trả `422` có chữ đọc được, thay vì để CHECK của Postgres ném
  `IntegrityError` thành `500`. (Với `EventUpdate` chỉ gửi một trong hai mốc: kiểm sau khi ghép với
  giá trị hiện có, ở tầng store.)
- **`starts_at`/`ends_at` nhận vào phải tz-aware; datetime naive bị từ chối `422`.** Ô
  `<input type="datetime-local">` gửi lên `2026-08-15T08:00` **không có offset**; nhận bừa thì
  Postgres diễn giải theo timezone của phiên kết nối và ta lại có đúng cái lệch 7 tiếng của §4.1,
  lần này ở đường ghi tay. Frontend có nhiệm vụ gắn offset trước khi gửi (§5 mục 3); DTO là lưới
  chắn thứ hai, không phải chỗ đoán ý.
- **Patch phân biệt "không gửi" với "gửi null" bằng `model_fields_set`**, không bằng `is not None` —
  y hệt `NoteUpdate` ở `009` §2.1. Cụ thể `color`: `if "color" in payload.model_fields_set:
  source.color = payload.color`. Viết `if payload.color is not None` là **bỏ màu không bao giờ chạy**
  mà không có test nào tự đỏ.
- **Mọi field chuỗi `.strip()` trước khi kiểm rỗng** (§4.1 cuối). `Field(min_length=1)` nhận
  `"   "` — một nguồn tên toàn khoảng trắng lọt qua rồi hiện thành dòng trống trong sidebar.

`CalendarStore` — các method: `list_sources`, `create_source`, `update_source`, `delete_source`,
`import_into_source`, `list_events(from_, to_, include_hidden_sources: bool)`, `create_event`,
`update_event`, `delete_event`.

**Giữ tham số `auth: AuthSession` và vẫn gọi `readable()`, dù cả hai hiện không lọc gì** — đây là lựa
chọn có chủ ý, không phải chép máy móc từ `tasks.py` (T3 đề nghị bỏ, T1 giữ, 2026-08-01). Lý do:
`008n` thiết kế để **lời khai `Gate` trên model là nguồn sự thật duy nhất**; mọi đường đọc đi qua
`reading.py` thì ngày nào đó lịch cần gác riêng tư, đổi một dòng khai `Gate.APPLIES` là **mọi truy
vấn tự gác**. Bỏ `readable()` ra thì lần đổi ấy sẽ âm thầm không có tác dụng lên calendar — đúng hình
dạng "hai quyết định đều đúng, lỗi nằm ở chỗ không cái nào tham chiếu cái kia". Ghi lại ở đây để lượt
review sau không gắn cờ "dead code".

Bảy chỗ có bẫy thật:
- **🔴 `import_into_source()` phải PARSE XONG rồi mới được đụng vào DB, và `events == []` ⇒ `422`,
  KHÔNG xoá gì.** (Bắt bởi T2, mức CRITICAL — đây là lỗ hổng mất dữ liệu nặng nhất còn lại trong
  spec.) Thứ tự bắt buộc: `parse_ics()` → nếu ném `ValueError` ⇒ `422`, chưa transaction nào mở →
  nếu `len(events) == 0` ⇒ `422` với chữ *"Không đọc được buổi nào từ file — chưa thay đổi gì"*,
  kèm `skipped` để chủ biết vì sao → chỉ khi có ít nhất 1 buổi mới `DELETE` + `INSERT`.
  **Vì sao đây là CRITICAL:** một file đổi đuôi thành `.ics`, một file dùng `TZID` (nay bị skip theo
  §4.1), hay một lần parser regress đều cho `events == []`; ghép với luật thay-sạch ở §2 mục 2 thì
  **164 buổi thành 0 buổi và API trả 200**. Biên nhận chỉ hiện ra *sau khi* dữ liệu đã mất.
  *(Import trả về ít buổi hơn lần trước nhưng > 0 thì vẫn đi tiếp — không dựng heuristic "giảm quá
  X%": nó sẽ chặn nhầm lúc chủ import lịch kỳ hè ít môn. Biên nhận có số cũ/số mới là đủ để nhìn ra.)*
- **`import_into_source()`** = kiểm nguồn tồn tại + đúng `kind` → khoá dòng nguồn
  `SELECT … FOR UPDATE` → `DELETE FROM calendar_event WHERE source_id = :id` → bulk insert → trả
  `ImportReport`. Tất cả trong **một** transaction. Khoá trước, không phải khoá sau (cùng khuôn
  `tasks.py:391,416,443`): hai lượt import chồng nhau lên cùng một nguồn sẽ đan buổi vào nhau, và
  **không CHECK nào của DB bắt được** vì mỗi dòng riêng lẻ đều hợp lệ. `removed` = số dòng `DELETE`
  trả về, không phải số đếm lại.
- **Nguồn không tồn tại ⇒ `SourceNotFound` ⇒ `404`, kiểm TRƯỚC khi xoá.** Câu `SELECT … FOR UPDATE`
  trả `None` mà cứ chạy tiếp thì `DELETE … WHERE source_id = <id lạ>` **thành công với 0 dòng** rồi
  `INSERT` mới nổ FK thành `500` — người dùng nhận nhầm lỗi, và log chỉ ra ngoại lệ FK chứ không chỉ
  ra nguyên nhân. Đây là cửa im lặng, phải chặn tường minh. Nguồn tồn tại nhưng `kind='manual'` ⇒
  `409` (§2 mục 7).
- **`create_source()` VÀ `update_source()` đều phải bắt vi phạm unique `uq_calendar_source_name_lower`**
  (`models.py:558-562` — unique trên `lower(name)`) và đổi thành lỗi **409 có chữ tiếng Việt**, chứ
  không để `IntegrityError` bò ra thành `500`. Spec cũ chỉ nói `create_source` — nhưng `PATCH` cũng
  sửa `name` và đụng đúng index đó (bắt bởi T2), nên đổi tên nguồn thành tên đã có sẽ ra `500`.
- **🆕 Body của `409` trùng tên phải mang `existing_source_id`.** UI được lệnh chào "nhập đè lên nguồn
  đó" (§5 mục 5) — không có id thì client phải tự dò trong cache bằng `toLowerCase()` của JavaScript,
  mà quy tắc hạ-chữ-hoa của JS và của Postgres `lower()` **không đồng nhất trên mọi Unicode** (bắt
  bởi T2). Trả thẳng id là hết chuyện. Dạng: `{"detail": {"code": "source_name_taken",
  "message": "…", "existing_source_id": "…"}}`.
- **🆕 `POST /sources` với `id` đã tồn tại ⇒ trả `200` + bản ghi hiện có (idempotent), KHÔNG `409`.**
  Spec cũ ghi "mirror `TaskIdConflict`" là **sai** (bắt bởi T2, đã kiểm `tasks.py:245-259`):
  `TaskStore.create()` chỉ ném `TaskIdConflict` khi id tồn tại **nhưng bị reading gate che** — với
  `Gate.NONE` tình huống đó không tồn tại, nên khuôn Task thật sự là *idempotent 200*. Đây là đúng
  hành vi ta muốn: seam `008m` sinh ra để một lần gửi lại request (mạng chập, hàng đợi offline) không
  đẻ nguồn thứ hai. Trùng **tên** thì 409 (khác chuyện), trùng **id** thì 200.
- **`list_events(from_, to_)` lọc theo GIAO NHAU, không theo điểm bắt đầu:**
  `WHERE starts_at < to_ AND ends_at > from_`. Viết `starts_at BETWEEN from_ AND to_` là **buổi bắt
  đầu trước khoảng nhìn biến mất khỏi màn hình** — với lịch học 2 tiết liền (đo thật: 07:00–09:00)
  thì nó biến mất khỏi mọi khoảng bắt đầu lúc 08:00, và `010b` (lịch cuộn theo tuần) sẽ ăn lỗi này
  ở mọi biên tuần. Sắp xếp `ORDER BY starts_at, id`. **Không** dùng `_parent()`-style kiểm cha cho
  từng thao tác event: `update_event` / `delete_event` định vị thẳng bằng `event_id`; chỉ
  `create_event` cần một lượt `_source()` để kiểm tồn tại + `kind` (§2 mục 7).
- **🆕 KHÔNG có `limit`/`offset` trên `list_events` và `list_sources`.** (Bắt bởi T2.) `tasks.py:187`
  mặc định `limit=100` và router chặn cứng `le=100` (`tasks router:42`) — chép sang đây là **mất buổi
  im lặng**: một nguồn thật có 139 và 164 buổi, nên chỉ cần chủ nhìn một khoảng đủ rộng là màn hình
  thiếu buổi mà không có dấu hiệu gì. Khoảng nhìn `from`/`to` **đã là** cơ chế giới hạn của API này;
  thêm phân trang lên trên nó là thêm một cách hỏng chứ không thêm an toàn.

### 4.3 `backend/app/web/routers/calendar.py`

Mirror `backend/app/web/routers/tasks.py`: `Database`/`CurrentSession` type alias, `_not_found()`,
**mọi endpoint qua `require_session`** (luật khoá `auth-brief.md` — không slice nào ship thiếu gác).
Đăng ký router trong `backend/app/main.py` cạnh `notes_router` — **mount dưới `protected_api`**
(`main.py:85`, nơi `Depends(require_session)` đã gắn sẵn), đọc file thật, đừng đoán tên biến.

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/api/calendar/sources` | envelope `{"items": [...]}` như `list_tasks`; **không phân trang** |
| POST | `/api/calendar/sources` | `201` khi tạo mới; **`200` + bản ghi hiện có khi trùng `id`** (idempotent, §4.2); `409` khi trùng **tên** (body mang `existing_source_id`) |
| PATCH | `/api/calendar/sources/{source_id}` | tên / màu / `is_visible`; **`409` khi tên mới trùng**; không đổi `kind` |
| DELETE | `/api/calendar/sources/{source_id}` | **204, xoá thật, CASCADE**; §2 mục 5 |
| POST | `/api/calendar/sources/{source_id}/import` | body `ImportRequest`, trả `ImportReport`; `404` nguồn không tồn tại; `409` nguồn `kind='manual'`; `422` khi parser từ chối **hoặc 0 buổi đọc được** |
| GET | `/api/calendar/events` | query `from`/`to` **bắt buộc, ISO-8601 có offset**; lọc theo giao nhau (§4.2) + `include_hidden` (mặc định `false`); **không phân trang** |
| POST | `/api/calendar/events` | buổi thủ công; `409` nếu `source_id` là nguồn `kind='ics'` |
| PATCH | `/api/calendar/events/{event_id}` | không đổi `source_id` |
| DELETE | `/api/calendar/events/{event_id}` | 204, xoá thật |

**Import đi bằng JSON, KHÔNG dùng `multipart/form-data`.** Bốn lý do, ghi lại để không ai "sửa" ngược:
ⓐ repo **chưa có `python-multipart`** trong `backend/pyproject.toml` và chưa có một `UploadFile` nào
— thêm một dependency + một mặt phẳng parse mới cho việc mà JSON làm được là đắt vô cớ; ⓑ nội dung
là **text thuần ~64 KB**, không phải binary; ⓒ frontend đọc file bằng `FileReader` rồi POST chuỗi —
`apiRequest()` (`frontend/src/api.ts:52`) chạy thẳng, không phải mở ngoại lệ cho `Content-Type`;
ⓓ giữ hình dạng JSON thì hàng đợi offline ở `017` nuốt được request import y như mọi request khác.

**Trần body — hai lớp khác nhau, đừng nhầm là một** (bắt bởi T2):
1. **Lớp thô, trước khi JSON được đọc:** middleware/dependency kiểm `Content-Length` của request
   `> 2 MB` ⇒ `413`. `ImportRequest.content` **chỉ tồn tại sau khi FastAPI đã đọc và decode xong toàn
   bộ body** — tức `max_length` trên field không ngăn được ai gửi một body 200 MB; nó chỉ ngăn cái
   body đó được *chấp nhận* sau khi máy đã nuốt hết. `main.py` hiện **không có** middleware nào loại
   này. (Bề mặt này nằm sau `require_session` và app là một-người-dùng, nên đây là hàng rào vệ sinh
   chứ không phải chống tấn công — nhưng nó rẻ, và không có nó thì `filename` không giới hạn + JSON
   whitespace + escape sequence đều là đường phình body.)
2. **Lớp tinh, sau khi đã có chuỗi:** `Field(max_length=…)` trên `content` + kiểm **byte** trong
   `parse_ics` (§4.1). `filename` cũng phải có `max_length` (256 là rộng rãi).

## 5. Frontend — màn danh sách, **chưa phải lịch**

Thêm tab thứ ba cạnh `Task` / `Ghi chú` trong `frontend/src/App.tsx:104-128` (mirror đúng cách hai
tab kia đang làm: `role="tab"` + `aria-selected` + `Button variant`, icon từ `lucide-react` —
`CalendarDays` hợp lẽ). File mới: `frontend/src/CalendarScreen.tsx`, `frontend/src/SourceForm.tsx`,
`frontend/src/EventForm.tsx`, `frontend/src/calendar-ui.ts`,
`frontend/src/components/ui/file-picker.tsx`.

**Phạm vi UI của 010a — cố ý hẹp:**
- **Danh sách nguồn**: tên · chấm màu · checkbox `is_visible` · số buổi · nút import lại · nút xoá.
- **Nút "+ Thêm nguồn lịch"**: chọn file `.ics` → tạo nguồn (tên mặc định = tên file bỏ đuôi) → gọi
  import. **Hai request nối nhau, cố ý**: nếu import hỏng thì nguồn rỗng vẫn còn đó để bấm "import
  lại" — rẻ hơn và dễ đọc hơn một endpoint đa hình.
- **🆕 Nút "+ Nguồn thủ công"** — tạo nguồn `kind='manual'` chỉ bằng tên + màu, **không chọn file**.
  Không có nút này thì **không có đường nào tạo buổi thủ công từ trạng thái DB rỗng**: form buổi bắt
  chọn nguồn, mà mọi đường tạo nguồn đều đi qua file picker (bắt bởi T2 — một lỗ hổng khiến quyết
  định phạm vi §0 mục 2 không dùng được trên thực tế).
- **Biên nhận import phải hiện lên màn hình**, không được nuốt: "Đã nhập **139** buổi · bỏ qua **0**
  · trùng **0** · thay cho **139** buổi cũ". Lý do trực tiếp: cả bug lớn nhất của app cũ (§1 mục 3)
  lẫn cách nó tồn tại nhiều năm đều là *im lặng*. Có `skipped` ⇒ liệt kê được (gấp lại nếu > 5 dòng).
- **Danh sách buổi** nhóm theo ngày, có nút lùi/tiến khoảng. **Khoảng mặc định chốt cứng:** từ
  `00:00:00+07:00` hôm nay đến `00:00:00+07:00` của **ngày thứ 30 kế tiếp** — tức nửa mở
  `[hôm nay, hôm nay+30 ngày)`, đúng **30 ngày**, biên tính theo giờ Việt Nam **không** theo múi giờ
  thiết bị (bắt bởi T2: "hôm nay tới +30 ngày" có ít nhất bốn cách đọc). Nút lùi/tiến nhảy **đúng
  30 ngày**. Nhóm ngày cũng cắt theo `+07:00`.
- **Form buổi thủ công**: tiêu đề · bắt đầu · kết thúc · cả ngày · địa điểm · mô tả · chọn nguồn
  (**chỉ liệt kê nguồn `kind='manual'`** — §2 mục 7).
- **KHÔNG dựng lưới tháng, KHÔNG dựng lịch cuộn, KHÔNG kéo-thả** — đó là `010b` (§9).

**Bảy ràng buộc UI dễ vấp:**
1. **Chọn file: thêm component, KHÔNG viết `<input>` thô.** `ui-brief.md` §6.1 cấm tuyệt đối và câu
   tiếp theo đã nói cách xử lý: *"Thiếu thì thêm component mới, không vá tại chỗ."* Bản trước của
   spec này tự tuyên bố một ngoại lệ ("input ẩn không thuộc phạm vi cấm") — **sai thẩm quyền**, một
   spec cấp task không được diễn giải lại brief đã khoá (bắt bởi T2). Làm đúng:
   `frontend/src/components/ui/file-picker.tsx` bọc `<input type="file" className="sr-only">` +
   `<Button>`, API kiểu `<FilePicker accept=".ics,text/calendar" onPick={(file) => …} />`. **Đừng**
   `shadcn add` — shadcn không có component này, tự viết ~25 dòng là đúng cách.
2. **`accept` không phải là kiểm tra.** Người dùng vẫn chọn được file khác. Kiểm phần đuôi + kích
   thước ở client (báo lỗi tử tế) **và** để backend kiểm lại (§4.1, §4.3) — client kiểm để nói cho
   nhanh, server kiểm để đúng.
3. **Vùng giờ — chốt cứng `+07:00` ở CẢ đường đọc lẫn đường ghi, không để executor chọn.**
   (Spec cũ cho phép "chọn một, ghi lại lựa chọn trong PR" — đó là contract sản phẩm, không phải
   chi tiết thi công; bắt bởi T2.) Cụ thể:
   - **Đọc:** `Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', … })` ở **mọi** chỗ hiển
     thị giờ, không trừ chỗ nào.
   - **Ghi:** `<input type="datetime-local">` trả `2026-08-15T08:00` **không offset**. Nối
     `"+07:00"` vào chuỗi — **không** dùng `new Date(x).toISOString()`, vì cách đó hiểu ô nhập theo
     múi giờ *thiết bị*. Hai cách này cho kết quả khác nhau ngay khi chủ mang máy ra khỏi UTC+7, và
     cái người dùng gõ vào ô luôn có nghĩa là "giờ Việt Nam" — đó là lịch học ở Hà Nội.
   - Backend từ chối `422` nếu thiếu offset (§4.2). Hai lớp, vì lớp nào một mình cũng từng đủ để
     đẻ ra bug lệch múi giờ trong app cũ.
4. **Trùng tên nguồn (409) phải có đường đi tiếp, không phải ngõ cụt.** Import lại lịch kỳ mới hay
   import nhầm lần hai đều rơi vào đây (§4.2). Khi `POST /sources` trả `409`, UI **không** tự thêm
   hậu tố `(1)` — nó hỏi thẳng: *"Đã có nguồn tên «X». Nhập đè lên nguồn đó, hay đặt tên khác?"*.
   Chọn "nhập đè" ⇒ gọi `POST /sources/{existing_source_id}/import` (id lấy từ body 409, §4.2), tức
   đúng luồng thay-sạch ở §2 mục 2. Tự thêm hậu tố là cách chắc chắn để chủ tích luỹ 4 nguồn trùng
   nhau sau 4 lần import.
5. **🆕 Import có thể chạm trần 20 giây của `apiRequest`.** `frontend/src/api.ts:19,52` áp
   `AbortSignal.timeout(20_000)` cho **mọi** request; import 5000 buổi cộng cold start ~8 giây của
   Fly có thể vượt. Cho riêng lời gọi import một timeout rộng hơn (60 giây). Quan trọng hơn: **nói
   với người dùng rằng thử lại là an toàn** — import là thay-sạch nên chạy lại cho kết quả y hệt,
   không nhân đôi. Không có câu đó thì một lần timeout sẽ khiến chủ tưởng dữ liệu hỏng (bắt bởi T2).
6. **🆕 Không render mô tả bằng HTML thô.** `description_md` là nội dung từ file bên ngoài. Cấm
   `dangerouslySetInnerHTML`; nếu render markdown thì phải qua renderer có sanitize. Lưu nguyên văn
   trong DB là đúng hợp đồng; *đổ nguyên văn vào DOM* thì không.
7. **`data-testid` theo `qa-framework.md` §6.3**, kebab-case `<thực-thể>-<phần-tử>`:
   `calendar-source-row` · `calendar-source-toggle` · `calendar-source-delete` ·
   `calendar-import-button` · `calendar-import-report` · `calendar-manual-source-button` ·
   `calendar-event-card` · `calendar-event-form` · `calendar-range-prev` / `calendar-range-next`.
   Id riêng đi bằng `data-source-id` / `data-event-id`, **không** nhét vào testid.

**Màu nguồn (`color`) — chốt là khoá bảng màu, không phải chuỗi tự do.** (Bắt bởi T2: spec cũ không
định nghĩa gì, mà `ui-brief.md` §6.2 lại cấm hardcode màu.) `calendar-ui.ts` khai một hằng
`SOURCE_COLORS: Record<string, string>` gồm 6 khoá (`rose`, `amber`, `emerald`, `sky`, `violet`,
`slate`), mỗi khoá map sang một **token** trong `index.css` — không `#hex` trong component. DB lưu
**khoá** (`"sky"`), không lưu mã màu. Khoá lạ / `null` ⇒ rơi về `slate`, không vỡ giao diện.

## 6. Không được làm

- Không đụng `.xlsx` — không đọc, không thêm `openpyxl`, không giữ nhánh code chờ sẵn (§0 mục 1).
- Không cài `icalendar`, `ics`, hay bất kỳ thư viện lịch nào. File nguồn **sai chuẩn** (§1 mục 3, 5)
  nên thư viện đúng chuẩn hoặc nổ hoặc nuốt chữ; parser tay ~120 dòng phủ đúng thứ cần phủ.
- Không cài `python-multipart` (§4.3).
- Không dùng `UID`/`DTSTAMP` làm khoá chống trùng (§1 mục 4).
- Không thêm `deleted_at` / undo-toast / endpoint `/restore` cho calendar (§2 mục 1, 5).
- Không đọc/ghi `calendar_event.is_hidden` (§2 mục 4).
- Không dựng `event_type`, không dựng version-history của nguồn (§2 mục 3, §4.1).
- Không thêm `limit`/`offset` cho `list_events`/`list_sources` (§4.2).
- Không dựng engine giãn `RRULE` — luật là **bỏ qua có báo**, không phải hỗ trợ (§4.1).
- Không sửa file của `task`/`note` (`tasks.py`, `notes.py`, `TasksScreen.tsx`, `NotesScreen.tsx`,
  `task-ui.ts`, `note-ui.ts`) — trừ đọc làm mẫu. Tích hợp task × lịch là `010b`.
- Không sửa `reading.py`, không đổi lời khai `Gate.NONE` của hai bảng calendar.
- **Không copy 4 file `.ics` thật của chủ vào repo, và không dán nội dung buổi học/thi vào PR.**
  Repo public (`devops-brief.md` §7). Chủ đã nói rõ đây **không phải dữ liệu nhạy cảm** (lịch học
  chung chung, tải lại được) nên đọc tại chỗ để test là **được phép**; nhưng "không nhạy cảm" không
  có nghĩa là "nên đăng công khai vĩnh viễn". Fixture trong repo là **file tự chế** (§7). Trước khi
  mở PR phải chạy và dán kết quả: `git status --short --untracked-files=all` và
  `git ls-files '*.ics'` — không file `.ics` nào ngoài fixture tự chế. Gitleaks **không** bắt loại
  dữ liệu này, nên đây là lưới duy nhất.

## 7. Acceptance — kiểm chứng được bằng lệnh

1. `cd backend && uv run ruff check` sạch. **Hai lane chạy bằng hai lệnh riêng, ghi số pass/skip của
   từng lệnh:** `uv run pytest -m "not pg"` và `uv run pytest -m pg`. Một lệnh `uv run pytest` xanh
   **không** chứng minh lane `pg` đã chạy — marker `pg` tự skip khi thiếu Postgres
   (`pyproject.toml:37-42`), nên "xanh" có thể nghĩa là "đã bỏ qua hết".
2. `cd frontend && npm run lint && npm test && npm run build` xanh.
3. **Test parser trên fixture tự chế** `backend/tests/fixtures/quirky.ics` — file này phải tái hiện
   **đủ 5 tật thật** đã đo ở §1, mỗi tật ít nhất một ca, và test phải khẳng định từng cái:
   ⓐ xuống dòng LF · ⓑ `DESCRIPTION` nhiều dòng **không** có space đầu dòng ⇒ `description_md` giữ
   đủ **cả 6 dòng** (đây là test chống lại đúng bug app cũ) · ⓒ mốc giờ không múi ⇒ ra `+07:00` ·
   ⓓ `UID` dạng số thứ tự ⇒ **không** xuất hiện ở đâu trong dữ liệu ghi xuống · ⓔ một `VEVENT` có
   `DTEND == DTSTART` ⇒ thành 90 phút, **không** ném lỗi. Cộng thêm: `VEVENT` thiếu `SUMMARY` ⇒ vào
   `skipped`; `SUMMARY` toàn khoảng trắng ⇒ cũng vào `skipped`; hai `VEVENT` trùng hệt ⇒
   `duplicates == 1`.
   Bốn ca từ lượt phản biện T3: ⓕ một dòng mô tả dạng `Note: mang thẻ` (khớp regex tên-thuộc-tính
   nhưng **không** phải thuộc tính) ⇒ vẫn nằm trong `description_md`, không bị cắt · ⓖ `SUMMARY`
   chứa `\,` và `DESCRIPTION` chứa `\n` ⇒ ra dấu phẩy và xuống dòng thật · ⓗ một `VEVENT`
   `DTSTART;VALUE=DATE:20260815` không `DTEND` ⇒ `all_day is True` và dài **1 ngày**, không phải
   90 phút · ⓘ một `VEVENT` `DTSTART:20260815T010000Z` ⇒ ra `08:00+07:00`.
   Ba ca từ lượt phản biện T2: ⓙ một `VEVENT` có `RRULE` ⇒ vào `skipped` với lý do đọc được,
   **không** lặng lẽ thành một buổi đơn · ⓚ một `VEVENT` có `DTSTART;TZID=America/New_York:…` ⇒ vào
   `skipped`, **không** bị hiểu nhầm thành giờ VN · ⓛ đẳng thức đếm
   `parsed == inserted + duplicates + len(skipped)` đúng trên chính fixture này.
   **Một test phải chạy được với biến môi trường `TZ=UTC`** và cho kết quả y hệt — đây là lưới duy
   nhất bắt được lỗi `astimezone` trên naive datetime (§4.1), thứ mà máy Windows của chủ ở +07:00
   **không bao giờ** làm đỏ.
4. **Test trần an toàn (`-m "not pg"`)**: text > 1 MB (đo byte, dùng ký tự tiếng Việt để chứng minh
   không nhầm với `len()`) ⇒ `ValueError`; > 5000 `VEVENT` ⇒ `ValueError`; một `VEVENT` có 200.000
   dòng nối ⇒ parse xong **dưới 2 giây** (lưới chặn bậc hai, §4.1).
5. **Test re-import (`-m pg`)**: import cùng một nội dung **hai lần** vào một nguồn ⇒ tổng số buổi
   **không đổi** (chống nhân đôi — đúng bug app cũ ở `v1-reference.md:12`); import nội dung khác vào
   nguồn đó ⇒ buổi cũ biến mất sạch. Xoá nguồn ⇒ buổi của nó biến mất theo CASCADE và **buổi của
   nguồn khác không suy suyển**.
6. **🔴 Test "file rác không được xoá dữ liệu" (`-m pg`)**: nguồn đang có 10 buổi; import một chuỗi
   không chứa `VEVENT` nào hợp lệ ⇒ API trả **`422`** và nguồn **vẫn còn đủ 10 buổi**. Đây là test
   quan trọng nhất của cả slice — không có nó thì lỗ hổng CRITICAL ở §4.2 lặng lẽ quay lại ở lần
   refactor đầu tiên.
7. **Test bất biến `kind` (`-m pg`)**: import vào nguồn `manual` ⇒ `409`; `POST /events` với
   `source_id` của nguồn `ics` ⇒ `409`; `PATCH /events/{id}` kèm `source_id` ⇒ trường đó bị bỏ qua
   hoặc `422`, buổi **không** đổi nguồn.
8. **Test xung đột tên (`-m pg`)**: `POST /sources` trùng tên khác hoa/thường ⇒ `409` **và body có
   `existing_source_id` đúng**; `PATCH /sources` đổi sang tên đã có ⇒ `409`, **không** `500`;
   `POST /sources` trùng `id` ⇒ **`200`** + bản ghi cũ, **không** `409`, **không** tạo bản thứ hai.
9. **Test 404 và 401 (`-m pg`)**: import vào `source_id` không tồn tại ⇒ `404`, không phải `500`.
   Và **gọi từng endpoint trong bảng §4.3 mà không có cookie phiên ⇒ `401`** — viết vòng lặp qua cả
   9 endpoint, đừng kiểm mẫu một cái. Không có test này thì một endpoint mount nhầm chỗ vẫn để mọi
   test khác xanh (bắt bởi T2).
10. **Test khoảng nhìn giao nhau (`-m pg`)**: một buổi 07:00–09:00, hỏi `from=08:00&to=08:30` ⇒
    **vẫn trả về**. Đây là ca mà cách viết `BETWEEN` sẽ trượt, và nó im lặng. Thêm: một nguồn
    `is_visible=false` ⇒ buổi của nó **không** ra ở `include_hidden=false` và **có** ra ở `true`;
    một nguồn 150 buổi trong khoảng nhìn ⇒ API trả **đủ 150**, không cắt ở 100.
11. **Test `event_count`**: `SourceRead.event_count` khớp số buổi thật sau import và sau khi xoá lẻ.
12. **e2e Playwright** `frontend/e2e/calendar.spec.ts` (mirror `tasks.spec.ts`), phủ ba đường mà
    unit test không chạm được: ⓐ tạo nguồn thủ công → tạo buổi → thấy nó trong danh sách → xoá có
    hộp thoại xác nhận; ⓑ import một fixture `.ics` nhỏ → **biên nhận hiện đúng số**; ⓒ hộp thoại
    xoá nguồn hiển thị **đúng số buổi** sẽ mất. §7.15 dưới nói vì sao mục này bắt buộc chứ không
    phải "nếu kịp".
13. **Đối chiếu trên 4 file thật của chủ — bước tay, ghi số vào PR description.** Chạy `parse_ics`
    trên `C:\Users\os\Desktop\{TKB-QLDT20252,LichThi-QLDT-20252,LichThi-QLDT-20251,TKB-QLDT20261}.ics`
    (đọc tại chỗ, **không copy vào repo**) và báo cáo số buổi parse được. **Con số phải khớp:
    139 · 8 · 6 · 164.** Lệch một dòng nào cũng phải giải thích được lệch ở đâu, đừng làm tròn.
    **Bằng chứng cho bug §1 mục 3 báo cáo bằng HÌNH DẠNG, không bằng nội dung:** với một ca thi bất
    kỳ, in ra `description_md.count("\n") + 1 == 6` và **danh sách 6 nhãn** (`Mã môn` / `Nhóm thi` /
    `Tổ thi` / `Hình thức` / `Thời gian` / `Kỳ thi`) — nhãn là cấu trúc file, không phải dữ liệu của
    chủ. **Không dán giá trị** (mã môn, mã nhóm, tên phòng) vào PR: repo public, và §6 vừa cấm đưa
    chính dữ liệu đó vào repo — dán vào mô tả PR là cùng một chỗ rò qua cửa khác (bắt bởi T2).
14. Migration đã áp lên Neon **bằng tay** và **đã xác minh bằng truy vấn thật** vào
    `information_schema.columns` (thấy `calendar_event.description_md`, `calendar_event.all_day`,
    `calendar_source.is_visible`) — dán output vào PR. *"Merge ≠ migration applied"* (`CLAUDE.md`).
15. `gh pr checks <PR>` — **dán nguyên output**, mọi job xanh, không job nào pending. (Đừng viết
    "đủ N required check": `ci.yml` hiện khai **7** job — `Backend checks`, `Production dependency
    check`, `Repository hooks`, `Secret scan`, `Frontend checks`, `Frontend e2e`, `Migration QA` —
    và file repo **không** cho biết job nào đang được đặt required trên GitHub. Con số là thứ dễ
    chép sai từ spec cũ; output thật thì không.)
16. **Báo cáo tách rõ ĐÃ CHẠY / CHƯA CHẠY** theo `agent-tasks/README.md` §25-40. **Đường chọn file
    trên trình duyệt thật và trên iPhone gần như chắc chắn nằm ở vế "chưa chạy"** — nói thẳng, và
    hiểu rằng §7.12 (e2e) tồn tại chính vì thế: nếu phần tương tác chính không có lưới tự động nào,
    "acceptance xong" chỉ có nghĩa là "code biên dịch được". Phần còn lại (file picker thật trên
    iOS Safari, đọc file lớn qua `FileReader`) là **bàn giao sang QA T3**, ghi rõ trong PR.

## 8. Việc của CHỦ trước khi giao Codex

- [ ] Không cần bật dịch vụ nền nào ngoài những gì `008`/`009` đã cần (Postgres local cho lane
      `-m pg`; không Docker mới, không VPN mới).
- [ ] 4 file `.ics` cần **nằm nguyên tại `C:\Users\os\Desktop\`** để bước Acceptance §7.13 chạy được.

**Migration `0005` lên Neon — chốt 2026-08-01: Codex tự chạy**, không cần chủ bấm tay. `NEON_MIGRATOR_URL`
lấy qua `.env`/biến môi trường sẵn có (đúng cách `008`/`009` đã chạy migration `0001`-`0004`), không
phải secret mới cần chủ gõ vào phiên. Thứ tự bắt buộc, chỉ chạy được một chiều — **áp trước khi merge
PR**, không phải ngược lại:

```
1. Codex: cd backend && uv run alembic upgrade head   (nhắm Neon, dùng NEON_MIGRATOR_URL)
2. Codex: xác minh bằng information_schema.columns, dán output vào PR (Acceptance §7.14)
3. Merge PR  →  develop tự deploy Fly
```

**Vì sao chỉ chạy được chiều này:** merge trước là để code đã biết `description_md`/`all_day`/
`is_visible` chạy trên schema chưa có ba cột đó — mọi truy vấn lịch trả `500` cho tới khi ai đó chạy
tay câu lệnh, đúng hình dạng *"Merge ≠ migration applied"* (`CLAUDE.md`). Chiều đúng an toàn vì
`0005` **tương thích ngược**: cột mới `NULL`/có server-default, code cũ (chưa biết cột) không đọc/ghi
chúng nên không vỡ gì trong lúc chờ merge.

## 9. Dàn ý `010b` — spec riêng, viết sau file này

Ghi lại ở đây để không rơi; **không** phải phạm vi của executor 010a.

- **Lịch cuộn liên tục kiểu Outlook** (chủ chốt 2026-08-01, đảo lại phương án lật-từng-tháng): danh
  sách hàng-tuần cuộn không ngắt. Bản mẫu: `old_prj/VC_QuanLyThoiGian/app/ui/calendar_view.py`
  (1208 dòng, Flet — đọc để lấy *hành vi*, không port code).
- **Thanh bên mini-lịch** — và nó **không phải đồ trang trí**: `calendar_view.py:724` cho thấy vùng
  hồng là `is_visible_on_screen = (d in visible_dates)`, tức **những ngày đang nằm trong khung nhìn**
  của lịch cuộn chính; bấm một ô thì `_scroll_to_date()` nhảy tới đó (`:738`). Nó là cơ quan điều
  hướng hai chiều của lịch cuộn. Ghi lại vì nhìn ảnh chụp thì tưởng chỉ là mảng màu cho đẹp.
- **Đường thu gọn cho iPhone** — lưới 7 cột trên màn 375px là chỗ thiết kế này yếu nhất; phải quyết
  riêng, không để executor tự chế giữa chừng.
- **Quick-add + kéo-thả task vào ô ngày** (`forward-spec.md` §B) — **đụng domain task**, và trùng với
  ứng viên "tool ghi đầu tiên" của AI Bước 2. Cân nhắc để API `move task` dùng chung ngay từ đầu.
- **Đánh dấu ngày đặc biệt** ("ngày về quê", `forward-spec.md` §B) — **chốt 2026-08-01: bảng
  `day_annotation` riêng**, không nhét vào `calendar_source(kind='manual')` với buổi cả-ngày. Hai lý
  do: CHECK `ends_at > starts_at` buộc phải bịa một giờ kết thúc cho một thứ vốn không có giờ; và
  một "ngày về quê" nằm lẫn trong danh sách buổi học thật sẽ làm rối đúng cái màn hình nó sinh ra để
  làm rõ.
- **Task hiện trên lịch** — app cũ trộn task vào cùng luồng sự kiện
  (`calendar_view_service.py:56-95`, gồm cả bảng màu ưu tiên hardcode). Có làm hay không là quyết
  định sản phẩm của chủ, chưa chốt.

## 10. Dấu vết phản biện — đọc trước khi gắn cờ lại một điểm đã bàn

Hai lượt review đối kháng chạy trên **spec + code thật**, 2026-08-01. Ghi lại các điểm **đã cân nhắc
và cố ý giữ nguyên**, để lượt sau không mở lại:

| Điểm bị nêu | Xử lý | Lý do |
|---|---|---|
| T3: bỏ `auth`/`readable()` vì `Gate.NONE` làm chúng vô nghĩa | **Bác** | §4.2 — lời khai `Gate` là nguồn sự thật duy nhất; bỏ ra thì lần đổi `Gate.APPLIES` sau này âm thầm không có tác dụng. |
| T2: acceptance §7.13 làm rò dữ liệu cá nhân vào PR public (mức CRITICAL) | **Fold, hạ mức** | Fold thành báo-cáo-theo-hình-dạng (§7.13) + guard `git ls-files` (§6). Hạ mức vì chủ đã nói rõ 4 file này **không nhạy cảm** và cho phép dùng để test; rủi ro thật là "đăng công khai vĩnh viễn", không phải "đưa vào phiên agent". |
| T2: heuristic chặn khi số buổi giảm đột ngột | **Không làm** | §4.2 — sẽ chặn nhầm lúc chủ import lịch kỳ hè ít môn. Đã chặn ca `0 buổi` là đủ; biên nhận có số cũ/số mới lo phần còn lại. |
| T2: `RRULE` nên có engine giãn lịch | **Không làm** (chỉ skip có báo) | Dữ liệu thật có 0 `RRULE` (§1 mục 2). Bỏ qua **có báo** đã chuyển hỏng-im-lặng thành hỏng-nhìn-thấy-được — đó là phần giá trị; engine là việc của lúc thật sự có file như thế. |
