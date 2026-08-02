# 016 — Private unlock (PIN 6 số + Argon2id + throttle leo thang + TTL 36 phút)

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L1
> (security-critical — đây là cổng hiển thị của toàn bộ dữ liệu riêng tư)
> · Skill gợi ý: không cần · MCP cần: không cần.**
> Trạng thái: ⚠️ OPEN — đã qua 2 lượt phản biện phân vai 2026-07-31 (T3 `gemini-3.1-pro-high`,
> brief "mô hình đe doạ + đường vòng qua cổng" · T2 `codex exec high`, brief "thi công + hợp đồng
> với code đang có"). 23 finding, đã fold hết những cái xác nhận thật (T1 tự kiểm tay từng cái
> nghiêm trọng trước khi tin — 2 CRITICAL/BLOCKER đều xác nhận đúng bằng cách đọc code thật, không
> chỉ tin lời agy/Codex). **Sẵn sàng giao Codex thi công.**

## 0. Bối cảnh — 016 mở cửa cho một thứ đã chạy nửa chừng trên production

Toggle **"riêng tư"** đã sống thật trên UI (`frontend/src/TasksScreen.tsx:867`,
`frontend/src/TaskForm.tsx:63`) và backend đã mã hoá đúng khi bật cờ
(`backend/app/domain/tasks.py:227-232`, `269`, `326-329`). Cổng đọc cũng đã gác đúng:
`can_see_private()` (`backend/app/domain/reading.py:82-84`) so `session.private_until` với hiện
tại, và `with_privacy_gate()` lọc `is_private = false` khi cổng đóng.

**Thiếu đúng một mảnh: không có đường nào ghi vào `session.private_until`.** Cột tồn tại
(`backend/app/domain/models.py:549-552`, nullable, chưa từng có giá trị), nhưng không endpoint nào
set nó. Hệ quả đang chạy thật trên prod: **bật riêng tư cho một task là một cửa một chiều** — task
biến mất khỏi mọi `GET` và không có đường lấy lại.

**Dữ liệu KHÔNG mất** — row vẫn nằm nguyên trong Postgres, chỉ bị cổng lọc. 016 là mở lại cửa,
không phải cứu dữ liệu. Không cần backfill, không cần script phục hồi.

### 0.1 🔒 016 KHÔNG CÓ MIGRATION — đừng chạy `alembic upgrade` sau khi merge

Mọi thứ 016 cần đã tồn tại trong schema: `session.private_until` (cột) và `app_setting`
(bảng key–value JSONB, `backend/app/domain/models.py:458-470`). Trạng thái throttle và hash PIN
đều là **row trong `app_setting`**, không phải cột mới.

Dự án này có thói quen *"merge ≠ migration applied"* và nó đúng ở `008d`/`008g`. **Lần này luật đó
vô hiệu.** Chạy `alembic upgrade head` theo quán tính sau khi merge 016 là thao tác thừa lên
production. Nói ra vì quán tính là thứ không tự báo.

### 0.2 🔒 CRITICAL — 016 phải đóng luôn một lỗ đã sống từ `008`, không chỉ mở cổng

Phản biện T3 (`adversarial_review`, 2026-07-31) bắt và T1 đã tự đọc code xác nhận **đúng**:
`TaskStore.create()` (`backend/app/domain/tasks.py:223-260`) **không gọi `can_see_private()` ở bất
kỳ đâu**. Nó seal đúng khi `payload.is_private = true`, nhưng sau đó `_task_read()` giải mã và
`create_task()` (`backend/app/web/routers/tasks.py:46-56`) trả DTO đã giải mã trong `201`.

⇒ Hôm nay vô hại (vì `private_until` chưa từng có giá trị, cổng luôn đóng, nhưng "đóng" không
được ai kiểm ở đường tạo mới — nó chỉ tình cờ chưa bị khai thác). **Sau khi 016 bật cổng thật, đây
là đường vòng nguyên vẹn: `POST /api/tasks` với `is_private: true` trong lúc khoá trả về plaintext
ngay trong response, không cần đọc lại qua `GET`.**

**Bắt buộc trong phạm vi 016** (không phải việc riêng, không hoãn): `TaskStore.create()` và
`TaskStore.update()` (đường bật `is_private` — `tasks.py:296-314`) phải từ chối khi
`payload.is_private` (hoặc `target_private`) là `true` **và** `reading.can_see_private(auth)` là
`false`. Trả **403** — thống nhất với hướng đọc: bạn không tạo được thứ bạn không thấy được. Áp
dụng đúng nguyên tắc R7 (`auth-brief.md` §4) vốn đã áp cho AI, nay áp luôn cho người: *"agent chỉ
ghi vào private khi unlocked"* — chưa có lý do gì để người dùng được miễn.

Viết test cho đúng cả hai đường (create + update-to-private) trong `test_private_gate.py`
(§4): khoá ⇒ 403, không lộ nội dung trong response body ở bất kỳ trường nào.

### 0.3 Rủi ro còn lại đã ghi nhận, KHÔNG bắt buộc sửa trong 016

T3 cũng bắt một **existence oracle hẹp** (F2): khi khoá, `POST /tasks` với một UUID trùng một task
riêng tư đã tồn tại trả `409 Conflict`; với UUID không tồn tại trả `201`. Đây là oracle nhị phân
thật, nhưng nó đòi hỏi kẻ tấn công **đã biết trước gần đúng UUIDv7** của task cụ thể (48 bit
timestamp + phần còn lại) — không phải dò một không gian ID nhỏ. Cơ chế `409` này chính là hợp
đồng **idempotent-create** mà `008m` dựng ra (client retry với cùng ID phải nhận lại đúng row cũ,
không tạo trùng) — sửa nó theo hướng "không tiết lộ" sẽ phá hợp đồng đó cho use-case hợp lệ (client
mất mạng giữa chừng, retry, cần biết "đã tạo rồi, đừng tạo lại"). **Quyết định: giữ nguyên hành vi,
ghi lại làm rủi ro đã cân nhắc** — không phải bị bỏ sót. Nếu muốn đóng nốt, đó là việc riêng ngoài
016 (đổi ngữ nghĩa 409 cho toàn bộ API, ảnh hưởng hơn cả private).

## 1. Quyết định đã chốt với chủ (2026-07-31) — không hỏi lại, không "cải tiến"

### 1.1 Bí mật là **PIN 6 chữ số**, hash Argon2id, lưu trong `app_setting`

Nguyên tắc chủ nêu: *giá trị tài sản phải cân bằng với cách bảo vệ nó*. Lập luận đầy đủ, vì
executor cần hiểu để không tự "nâng cấp":

- PIN chỉ gác **cửa NHÌN**, không gác **cửa ĐỌC**. Khoá AES-256-GCM nằm ở Fly secrets
  (`ENCRYPTION_MASTER_KEY`, `backend/app/core/crypto.py:43`), **không** nằm trong DB.
- ⇒ Kẻ có bản dump Neon crack được PIN cũng **không mở thêm được gì**: ciphertext vẫn câm.
- ⇒ Dùng PIN online thì phải có cookie session hợp lệ, tức phải đăng nhập Google bằng account
  trong allowlist.
- ⇒ Threat thật mà PIN gác là **"người đang đứng cạnh, máy đang mở"** (`auth-brief.md` §3,
  `devops-brief.md` §1). Với threat đó, 10⁶ tổ hợp + throttle là thừa đủ.

### 1.2 🔒 PIN KHÔNG BAO GIỜ được dùng làm, hoặc dẫn xuất ra, khoá mã hoá

Hôm nay không ai định làm thế. Nhưng ở `011` hoặc phiên AI Bước 1, ý tưởng *"lấy PIN derive ra
khoá cho nội dung private"* nghe rất hợp lý — và nó biến một bí mật **10⁶** thành thứ gác dữ liệu
at-rest, tức phá thẳng §1.1. Cấm một chiều thì chiều còn lại tự động được phép, nên nói cả hai
nửa ra: **`private_pin.py` không được import `crypto.py`, và không hàm nào trong 016 được trả về
thứ dùng làm key material.** Ghi thành comment trong `private_pin.py`.

### 1.3 Throttle **TOÀN CỤC**, không theo session

Thang leo (chủ chốt): **sai lần thứ 10 → khoá 5 phút · lần thứ 20 → 8 phút · lần thứ 36 → 18
phút**. Giữa hai mốc thì thử tự do. Hết lock cuối (18 phút) → **bộ đếm về 0**. Mở khoá đúng →
bộ đếm về 0 ngay.

**Vì sao toàn cục chứ không phải cột trên `session` (kiến nghị ban đầu đã bị đảo):**
`PostgresSessionStore.create()` (`backend/app/domain/auth.py:41-55`) `INSERT` một session row mới
mỗi lần đăng nhập, với mọi giá trị mặc định. Nếu bộ đếm nằm trên session row thì **đăng xuất →
đăng nhập lại = nút reset throttle**, một cú bấm. Thang leo công phu tới đâu cũng vô nghĩa trước
một cái nút. App một người dùng nên "toàn cục" và "theo tài khoản" là một thứ.

### 1.4 TTL **36 phút, CỨNG, không bao giờ gia hạn theo hoạt động**

`session.expires_at` cuộn theo mỗi request (`auth.py:74-75`). **`private_until` TUYỆT ĐỐI KHÔNG
được cuộn như thế.** `018` đã chốt `refetchInterval` cho danh sách task; một tab để mở sẽ tự gia
hạn liên tục ⇒ private mở vĩnh viễn, đúng thứ threat model muốn chặn. Hai quyết định đều đúng
riêng lẻ, hỏng khi gặp nhau — đây là họ lỗi `feedback_gap_between_correct_decisions`.

⇒ `private_until` chỉ được ghi ở đúng **một** chỗ: lúc verify PIN thành công. Không hàm nào khác
được chạm nó, kể cả `load_valid()`.

### 1.5 Đổi PIN được trong app

Chủ muốn đổi PIN từ trong app (đó là lý do hash nằm trong `app_setting` chứ không phải env).
⇒ 016 gồm cả endpoint đổi PIN.

### 1.6 🔒 Endpoint đổi PIN là cái oracle THỨ HAI — phải chịu CHUNG throttle

Đổi PIN phải kiểm PIN hiện tại ⇒ nó đoán được PIN. Gắn throttle cho `/unlock` mà quên `/pin` là
để nguyên một cửa sau không giới hạn. Cả hai đường verify **phải đi qua đúng một hàm** có throttle
bên trong — không được có đường thứ hai gọi thẳng `verify_pin()`.

### 1.7 PIN khởi tạo đọc từ env, **giá trị không nằm trong repo**

Repo này public có chủ đích (`devops-brief.md` §1). Một PIN mặc định đăng công khai làm cổng thành
đồ trang trí cho tới khi chủ đổi. ⇒ PIN khởi tạo đọc từ biến môi trường `PRIVATE_PIN_BOOTSTRAP`
(chủ tự đặt giá trị); **không ghi giá trị đó vào source, spec, test, hay commit message.**

Và vì "chủ sẽ đổi sau cutover" là một lời hứa chứ không phải một cơ chế: khi PIN còn là bản khởi
tạo, UI phải hiện **badge cảnh báo thường trực**. Cờ `bootstrap` trong row `app_setting` tắt vĩnh
viễn khi đổi PIN lần đầu.

### 1.8 Tham số Argon2id: **m=19456 KiB (19 MiB), t=2, p=1** — cố định, có lý do

Đã đo tay 2026-07-31 trên máy dev (`argon2-cffi 25.1.0`): verify **21,1 ms**, đúng và sai bằng
nhau (không rò timing). Chuỗi hash 97 ký tự, tự mô tả tham số (`$argon2id$v=19$m=19456,t=2,p=1$…`)
⇒ đổi tham số về sau không phá hash cũ.

⚠️ **KHÔNG dùng profile `argon2.profiles.RFC_9106_LOW_MEMORY`** (m=65536 KiB, t=3, **p=4**). Máy
Fly là `shared-cpu-1x` **256 MB** (`architecture-brief.md` §5) — 64 MB + 4 luồng mỗi lần mở khoá
là rủi ro OOM thật, và job cron `014` đang canh RSS. Với không gian 10⁶ thì tăng cost KDF chỉ mua
cảm giác an toàn (8 giờ CPU vs 42 giờ CPU đều là "crack được"); thứ bảo vệ thật là §1.1 — crack
xong không mở thêm gì. Đổi RAM thật lấy sức mạnh giả là lỗ. Viết tham số tường minh + comment
này vào code.

## 2. Backend — thi công chi tiết

### 2.1 Dependency

Thêm `argon2-cffi>=25.1.0` vào **`[project] dependencies`** trong `backend/pyproject.toml`
(**không** vào `[dependency-groups] dev`) rồi `uv lock`.

Lý do bắt buộc là runtime dep: job CI `Production dependency check` (`.github/workflows/ci.yml:31`)
chạy `uv sync --frozen --no-dev` rồi `create_app()`. Một thư viện chỉ có ở nhóm dev vẫn khiến
`pytest` xanh trong khi image production không import nổi app — chính lỗi đã làm 007 crash-loop
trên Fly. `uv sync --frozen` cũng nghĩa là **`uv.lock` phải được commit kèm**.

Đã kiểm 2026-07-31: `argon2-cffi 25.1.0` có wheel `cp39-abi3` (phủ CPython 3.14) cho
`manylinux_2_28_x86_64` — khớp base image `python:3.14-slim-bookworm` (glibc 2.36) ⇒ **không phải
biên dịch C**, không cần thêm build-essential vào Dockerfile.

🔒 Job `Production dependency check` chỉ bắt được thiếu dependency nếu module dùng nó **nằm trên
đường import của `create_app()`** (`main.py` import router ở top-level, giống mọi router khác —
`main.py:17-21`). Đăng ký `private_router` bằng `from app.web.routers.private import router as
private_router` ở đầu `main.py` cùng chỗ với `tasks_router`/`me_router` — **không** import trễ
(lazy import bên trong hàm) — nếu không thì thiếu `argon2-cffi` trên production image sẽ không bị
job này bắt, y hệt kiểu lỗi đã làm 007 crash-loop.

### 2.2 `backend/app/core/private_pin.py` (mới) — seam thuần, không chạm DB

Chép đúng tinh thần `crypto.py`: module tự-chứa, lazy, có thể import khi chưa cấu hình gì.

```
PIN_LENGTH = 6
_TIME_COST, _MEMORY_COST_KIB, _PARALLELISM = 2, 19456, 1

@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher          # tham số tường minh + comment §1.8
def is_valid_pin(value: str) -> bool     # ĐÚNG 6 ký tự, mỗi ký tự thuộc "0123456789"
def hash_pin(pin: str) -> str
def verify_pin(stored_hash: str, pin: str) -> bool
```

🔒 **`is_valid_pin` KHÔNG được dùng `str.isdigit()`.** `"٦٦٦٦٦٦".isdigit()` là `True` (chữ số
Ả Rập–Ấn Độ), `"²²²²²²".isdigit()` cũng vậy. Kiểm bằng tập ASCII tường minh. Cùng họ lỗi với
`compare_digest` non-ASCII đã vá ở `008d`: một hàm chuẩn thư viện có phạm vi rộng hơn ta tưởng.

`verify_pin` bắt `argon2.exceptions.VerifyMismatchError` → trả `False`. **`InvalidHash` thì để
nổ** (row hỏng là sự cố cấu hình, không phải "sai PIN"). Không bắt `Exception` trần.

### 2.3 `backend/app/domain/private_gate.py` (mới) — toàn bộ logic cổng

Hằng số:
```
PIN_SETTING_KEY      = "private_pin"                # {"hash": str, "bootstrap": bool}
THROTTLE_SETTING_KEY = "private_unlock_throttle"    # {"fail_count": int, "locked_until": str|None}
TTL_SETTING_KEY      = "private_unlock_ttl_minutes" # {"value": int}
DEFAULT_TTL_MINUTES  = 36
LOCK_LADDER = ((10, 5), (20, 8), (36, 18))          # (bộ đếm chạm mốc, số phút khoá)
```

TTL đọc từ `app_setting` theo đúng `auth-brief.md` §3 (*"TTL … (`app_setting`)"*); không có row
thì dùng `DEFAULT_TTL_MINUTES`. **Không seed row TTL** — mặc định trong code là đủ, thêm row chỉ
tạo hai nguồn sự thật.

🔒 **JSONB read-modify-write PHẢI dùng gán lại toàn bộ dict, không mutate tại chỗ.**
SQLAlchemy **không** tự theo dõi thay đổi bên trong một `dict` Python thường
(`AppSetting.value: dict = Field(sa_column=Column(JSONB, ...))`, `models.py:469-470`) — viết
`row.value["fail_count"] = 1` rồi `commit()` có thể **không sinh `UPDATE` nào**, throttle coi như
chưa từng tăng. Mọi hàm dưới đây phải viết theo khuôn:
```
row.value = {**row.value, "fail_count": n, "locked_until": iso_or_none}
```
gán lại biến `.value`, không sửa dict đang tham chiếu. Thêm một test pg xác nhận giá trị **còn sau
khi nạp lại row bằng session khác** (không chỉ đọc lại object đang giữ trong RAM — object đó có
thể "đúng" dù `UPDATE` chưa từng xảy ra).

Định dạng thời gian trong JSONB: **ISO-8601 UTC có suffix `Z`** (`datetime.now(UTC).isoformat()`),
parse lại bằng `datetime.fromisoformat`. Không lưu naive datetime.

Hàm chính (tất cả nhận `db: AsyncSession` của request, không tự mở transaction mới):

- `async def _locked_throttle_row(db) -> AppSetting`
  `INSERT … ON CONFLICT DO NOTHING` để đảm bảo row tồn tại (chép khuôn idempotent của `008m`,
  `tasks.py`), rồi `SELECT … WHERE key = THROTTLE_SETTING_KEY FOR UPDATE`. **Mọi đường đọc–sửa–ghi
  throttle phải đi qua đây** — đây là khuôn khoá dòng cha mà `008` đã đặt; JSONB read-modify-write
  không có khoá là một cuộc đua. **`set_pin` cũng bắt buộc gọi hàm này TRƯỚC bước kiểm "đã có PIN
  chưa"** (xem `set_pin` bên dưới) — nếu không, một lượt seed-bootstrap-lười và một lượt `set_pin`
  đầu tiên có thể chạy chồng nhau và ghi đè nhau.

- `VerifyOutcome`: `Literal["OK"] | tuple[Literal["LOCKED"], int] | tuple[Literal["WRONG"], int] | Literal["NO_PIN"]`
  (`int` thứ hai của `LOCKED` = `retry_after_seconds`; của `WRONG` = `remaining` lần trước mốc kế
  tiếp). Viết type cụ thể này trong code — đừng để executor tự chọn hình dạng.

- `async def _verify_under_throttle(db, pin) -> VerifyOutcome`
  🔒 **Đường verify DUY NHẤT** (§1.6). Trình tự:
  1. Khoá row throttle (`_locked_throttle_row`).
  2. `locked_until` còn hiệu lực ⇒ trả `("LOCKED", retry_after_seconds)`, **không** verify,
     **không** tăng bộ đếm (nếu không thì spam lúc đang khoá sẽ tự đẩy lên bậc cao hơn).
  3. Đọc row PIN; chưa có ⇒ seed từ `PRIVATE_PIN_BOOTSTRAP` (§2.5); vẫn không có ⇒ `"NO_PIN"`.
  4. `verify_pin()`.
     - **Đúng:** ghi lại `{"fail_count": 0, "locked_until": None}` → `"OK"`.
     - **Sai:** `fail_count += 1`; nếu `fail_count` **chạm đúng** một mốc trong `LOCK_LADDER` thì
       `locked_until = now + phút`; nếu chạm mốc **cuối** (36) thì đồng thời `fail_count = 0` —
       lock vẫn giữ vì bước 2 chỉ nhìn `locked_until`, và bộ đếm đã reset sẵn cho sau khi hết lock
       (đúng luật "hết lock cuối thì tính lại từ 1"), không cần thêm field nào. Ghi lại row bằng
       khuôn gán-lại-toàn-bộ ở trên.
     - Trả `("LOCKED", retry_after_seconds)` nếu vừa chạm mốc, ngược lại
       `("WRONG", remaining_lần_trước_mốc_kế_tiếp)`.

- `async def unlock(db, session, pin) -> tuple[Literal["OK"], datetime] | VerifyOutcome`
  Gọi `_verify_under_throttle`. `"OK"` ⇒
  🔒 **`SELECT * FROM session WHERE id = :session_id FOR UPDATE`** trên `db` hiện tại (object từ
  `require_session` thuộc session DB **khác** — store dùng factory riêng, xem `auth.py:60-77`,
  `deps.py:42-57`), set `private_until = now + ttl` trên row **vừa nạp lại**, không phải object
  tham số — **đây là chỗ DUY NHẤT trong toàn bộ codebase được ghi vào `private_until`** (§1.4).
  Trả `("OK", private_until)`.

- `async def lock_now(db, session) -> None`
  🔒 **Làm ĐÚNG cùng bước reload-by-id-FOR-UPDATE như `unlock`**, set `private_until = None` trên
  row nạp lại. Không throttle (đóng cửa không bao giờ cần giới hạn). **Đây là chỗ dễ bỏ sót nhất
  trong toàn spec: nếu chỉ set `session.private_until = None` trên object tham số mà không nạp lại
  trong `db` hiện tại, route trả `204` thành công nhưng KHÔNG ghi gì xuống DB** — nút "Khoá lại
  ngay" sẽ không khoá gì cả, và không ai biết vì response vẫn 204.

- `async def set_pin(db, session, current_pin, new_pin) -> None`
  - `is_valid_pin(new_pin)` sai ⇒ `ValueError` → 422.
  - **Luôn gọi `_locked_throttle_row(db)` trước bất kỳ bước nào khác** — kể cả khi chưa có PIN —
    để khoá đúng thứ tự với seed-bootstrap-lười và tránh đua giữa hai request `set_pin` đồng thời.
  - Nếu đã có PIN: bắt buộc `current_pin`, verify **qua `_verify_under_throttle`** (§1.6, cùng
    row throttle đã khoá ở bước trên — không mở transaction/lock lần hai).
  - Nếu **chưa** có PIN (kể cả sau khi seed bootstrap thất bại vì env trống): cho đặt không cần
    `current_pin` — chỉ cần session đã đăng nhập, mà session ấy đã là account allowlist duy nhất.
  - Ghi `{"hash": hash_pin(new_pin), "bootstrap": False}` (row PIN, `INSERT … ON CONFLICT DO
    UPDATE`) và **reset throttle** về `{"fail_count": 0, "locked_until": None}` bằng khuôn gán-lại.
  - Đổi PIN **không** đóng cổng đang mở và **không** gia hạn TTL — kể cả khi gọi lúc đang khoá:
    verify đúng chỉ mở lại throttle, **không** gọi `unlock()`, cổng vẫn đóng sau khi đổi PIN xong
    (người dùng bấm mở khoá lần nữa nếu muốn vào). Hành vi này cố ý bất đối xứng với `unlock` —
    đổi PIN là một hành động khác với xin xem private, không tự động gộp hai việc.

- `async def gate_status(db, session) -> GateStatus`
  `GateStatus`: `{private_until: datetime | None, locked_until: datetime | None, pin_is_set: bool,
  pin_is_bootstrap: bool}`. Trả `session.private_until` trực tiếp (không tính lại
  `can_see_private` ở đây — router/frontend tự so với `now`; `reading.can_see_private()` vẫn là
  nguồn sự thật duy nhất cho **quyết định lọc dữ liệu**, hàm này chỉ trả trạng thái để hiển thị).

### 2.4 `backend/app/web/routers/private.py` (mới)

```
POST /private/unlock   {pin}                    → 200 {private_until}
POST /private/lock                              → 204
POST /private/pin      {current_pin?, new_pin}  → 204
```

🔒 **Envelope lỗi tường minh — `HTTPException(detail=...)` mặc định KHÔNG tạo ra hình dạng này.**
`HTTPException(detail={"detail": "...", "remaining": 9})` bọc lồng thành
`{"detail": {"detail": "...", "remaining": 9}}`, không phải envelope phẳng bên dưới. Dùng
`JSONResponse` trực tiếp (không phải `HTTPException`) cho hai mã có payload phụ:

```
401  JSONResponse(401, {"detail": "Sai PIN", "remaining": <int>})
429  JSONResponse(429, {"detail": "Đang khoá tạm", "retry_after_seconds": <int>},
                  headers={"Retry-After": str(retry_after_seconds)})
409  HTTPException(409, "Chưa đặt PIN")                      # chưa đặt PIN mà gọi unlock
422  HTTPException(422, "PIN phải đúng 6 chữ số")             # PIN sai định dạng — hoặc để
                                                               # FastAPI tự sinh từ Pydantic validate
```
`Retry-After` là **chuỗi số nguyên giây thập phân** theo RFC 9110, không phải ISO datetime.

Đăng ký trong `backend/app/main.py` vào **`protected_api`** (`main.py:85-88`), cạnh
`me_router`/`tasks_router` — mount ở đó là thứ khiến route được `require_session` gác; đừng
`include_router` thẳng vào `app`.

**Mở rộng `backend/app/web/routers/me.py`:** `SessionInfo` thêm `private_until: datetime | None`,
`private_locked_until: datetime | None`, `pin_is_set: bool`, `pin_is_bootstrap: bool`. `read_me`
cần `db` (`Depends(get_session)`) để đọc `app_setting`. **Không** tạo thêm endpoint
`GET /private/status` — một nguồn là đủ, và `App.tsx` đã query `/api/me` sẵn.

🔒 **Test seam vỡ nếu không sửa:** `read_me` hôm nay chỉ phụ thuộc `require_session`
(`me.py:22-29`). `get_session()` (`deps.py:42-49`) trả **503** khi không có sessionmaker cấu hình.
`build_client()` trong `backend/tests/test_auth.py` chỉ override `get_session_store`, **không**
override `get_session` — mọi test `/api/me` hiện có (`test_auth.py`, ~dòng 103-107) sẽ đổi từ
`200` thành `503` ngay khi thêm dependency này, dù không đụng gì tới logic của chúng. **Bắt buộc
sửa `build_client()` (hoặc fixture tương đương) để override luôn `get_session` bằng một
`AsyncSession` giả/thật trước khi thêm field mới vào `SessionInfo`** — không để CI tự phát hiện,
vì phát hiện qua CI đỏ ở đây là 5+ test hiện có gãy cùng lúc, khó phân biệt lỗi thật với lỗi do
thiếu fixture.

**Truyền dữ liệu xuống UI — không tự query lần hai:** `App.tsx` hôm nay gọi
`<SignedIn />` không kèm prop (`App.tsx:160-161`). Sửa để **truyền `session.data` (kiểu
`SessionResponse` đã mở rộng) làm prop xuống `SignedIn`, rồi xuống `PrivateGate`**. `PrivateGate`
**không** tự mở `useQuery` thứ hai cho cùng dữ liệu — một nguồn (`['session']`, đã có sẵn) để badge
và mọi phần khác của app luôn thấy cùng một `private_until`, không có hai bản có thể lệch nhau.

### 2.5 Seed PIN khởi tạo

`backend/app/core/settings.py`: thêm `private_pin_bootstrap: str | None = None`.

Seed **lười**, trong `_verify_under_throttle` bước 3 (không dùng startup hook — app phải boot được
khi env trống): row `private_pin` chưa tồn tại **và** `private_pin_bootstrap` hợp lệ định dạng ⇒
`INSERT … ON CONFLICT DO NOTHING` với `{"hash": hash_pin(...), "bootstrap": True}`. Env không hợp
lệ định dạng ⇒ **không seed**, coi như chưa có PIN (đừng nuốt im lặng: log một dòng cảnh báo).

Seed chạy **một lần duy nhất** nhờ `ON CONFLICT`; sau khi chủ đổi PIN, đổi lại giá trị env cũng
không ghi đè được gì.

## 3. Frontend — thi công chi tiết

Đọc `docs/ui-brief.md` §6 (luật UI cứng) trước khi viết dòng đầu tiên: không thẻ thô, không
hardcode màu, không chiều cao cứng, chữ ≥12px, **không tương tác chỉ sống bằng hover**, light-only.

### 3.1 `frontend/src/private-gate.ts` (mới)
Kiểu + 3 hàm gọi API qua `apiRequest` (`frontend/src/api.ts:50`). Không tự `fetch` — `apiRequest`
là chỗ giữ hạn 20 giây và ném `UnauthenticatedError`/`TimeoutError`.

### 3.2 `frontend/src/PrivateGate.tsx` (mới)

**Badge trạng thái** (`@/components/ui/badge`), ba trạng thái + một cảnh báo chồng lên:
- đóng: "Riêng tư · đang khoá" + nút mở khoá;
- mở: "Riêng tư · còn N phút" + nút **Khoá lại ngay**;
- đang bị throttle: "Khoá tạm · còn M:SS", nút mở khoá `disabled`;
- `pin_is_bootstrap` ⇒ thêm cảnh báo thường trực "PIN còn là mặc định — hãy đổi" (§1.7).

**Dialog nhập PIN** (`@/components/ui/dialog`, `input`, `button`):
- Ô PIN: `type="password"` · `inputMode="numeric"` · `maxLength={6}` · `autoComplete="current-password"`.
  `inputMode="numeric"` để iPhone bật bàn phím số.
- 🔒 **Bọc trong `<form>` và kèm một ô `username` ẩn** (`autoComplete="username"`, giá trị =
  email từ `/api/me`, `readOnly`, class `sr-only`). Không có ô username thì trình quản lý mật khẩu
  thường **không** chào lưu/điền. Đây không phải tiểu tiết: `auth-brief.md` §3 coi
  **iCloud Keychain + FaceID autofill** là chỗ vá đúng điểm đau nhất của threat model (không gõ gì
  trước mặt người đang nhìn) với 0 dòng code thêm — hỏng autofill là hỏng chính lý do chọn phương
  án này. Dùng `sr-only`, **không** `display:none`/`hidden` (trình quản lý bỏ qua ô bị ẩn hẳn).
- Lỗi hiện **trong Dialog và cả ngoài badge** khi Dialog đã đóng — lỗi vẽ trong Dialog thì Dialog
  đóng là mất chữ, đúng lỗi đã bắt ở `008i`.
- Sai PIN: "Sai PIN. Còn N lần trước khi khoá tạm." · Đang khoá: đếm ngược M:SS.

**Đổi PIN**: Dialog thứ hai (PIN hiện tại + PIN mới + nhập lại), `autoComplete="new-password"` cho
ô mới. Khi `pin_is_set = false` thì ẩn ô PIN hiện tại.

### 3.3 🔒 Vòng đời cache — R6

⚠️ Cú pháp TanStack Query v5 dùng object, **không phải mảng trần**:
`queryClient.invalidateQueries({ queryKey: [...] })`. Khoá thật của task list là
`taskInvalidationKey = ['tasks']` xuất từ `frontend/src/task-ui.ts:27` — dùng đúng hằng số này,
đừng viết tay `['tasks']` ở nơi khác (match theo prefix của TanStack đã đúng, nhưng lệch tay dễ gõ
sai thành `['task']`).

- Mở khoá thành công ⇒ `queryClient.invalidateQueries({ queryKey: ['session'] })` **và**
  `queryClient.invalidateQueries({ queryKey: taskInvalidationKey })`.
- **Khoá lại (bấm tay HOẶC hết TTL) ⇒ `queryClient.removeQueries({ queryKey: taskInvalidationKey })`
  rồi mới invalidate.** `invalidate` một mình để lại dữ liệu private trong cache và vẫn render nó
  cho tới khi request mới về — R6 (`auth-brief.md` §4) đòi private không nằm lại sau khi khoá.
- **Timer hết hạn:** `setTimeout` đúng mốc `private_until` → tự lật UI + `removeQueries`. Clear
  khi unmount và **tính lại khi `private_until` đổi**. Không dùng `setInterval` 1 giây để dò.
- 🔒 **`setTimeout` một mình KHÔNG đủ.** Trình duyệt throttle/tạm dừng timer của tab nền hoặc khi
  máy ngủ (đã đo thật ở dogfooding trước đây rằng background tab behavior không đáng tin cho
  đồng hồ chính xác) — TTL có thể đã hết từ lâu mà UI vẫn hiện private vì timer chưa kịp bắn.
  **Bắt buộc thêm:** lắng nghe `document.visibilitychange` (chuyển `visible`) **và**
  `window.addEventListener('focus', ...)`, mỗi lần trigger so `private_until` với `Date.now()` — hết
  hạn thì chạy đúng logic khoá (`removeQueries` + lật badge) ngay lập tức, không đợi timer. Đây là
  đường bảo hiểm, `setTimeout` vẫn là đường chính cho tab đang mở/focus liên tục.
- Đồng hồ đếm ngược chỉ là hiển thị: **server luôn là trọng tài**. Mọi request tới `/api/tasks*`
  sau khi `private_until` hết hạn nhận dữ liệu đã lọc bởi `reading.py` bất kể client nghĩ gì —
  client-side check ở trên chỉ để UI phản ứng nhanh, không phải cơ chế bảo mật.
- **Ghi chú cho `017` (outbox offline, sau này):** nếu dự án bật `persistQueryClient` cho
  IndexedDB, khoá `taskInvalidationKey`/`['tasks']` **phải** nằm trong danh sách loại trừ khỏi
  persist — R6 cấm private nằm lại trên đĩa. Hôm nay dự án **chưa dùng** `persistQueryClient`
  (đã kiểm: không có ở `frontend/src`), nên không có gì phải sửa trong 016, chỉ để lại dấu cho
  người dựng 017 không quên.

### 3.4 Mount + testid
Đặt `<PrivateGate />` trong header của `SignedIn` (`frontend/src/App.tsx:76-91`), cạnh nút đăng
xuất. `data-testid` bắt buộc (khuôn `018`): `private-badge`, `private-unlock-open`, `private-pin-input`,
`private-unlock-submit`, `private-lock-now`, `private-pin-change-open`, `private-error`.

## 4. Test

Lane `pg` chạy trên Postgres Docker thật (`backend/tests/conftest.py` — `pg_dsn` từ chối host
non-localhost, giữ nguyên, **không nới**).

🔒 **`test_private_gate.py` và `test_private_api.py` là DB-backed thật — cả hai phải mang
`pytestmark = pytest.mark.pg`, không chỉ cái đầu.** Job `Backend checks` chạy `-m "not pg"`
(database-free); thiếu marker thì test hoặc lỗi kết nối trong job sai, hoặc — tệ hơn — bị bỏ sót
hoàn toàn khỏi cả hai job, và CI vẫn xanh trong khi endpoint chưa từng chạy qua Postgres thật.

🔒 **`AuthSession` dùng trong test API phải là ROW ĐÃ INSERT, không phải object dựng tay.** Khuôn
`_auth()` hiện có ở `test_tasks_api.py:27-35` dựng `AuthSession(...)` **không đưa vào DB** — object
đó có `id` (UUIDv7 sinh client-side qua `uuid_primary_key()` default), nhưng row **không tồn tại**
trong Postgres. `unlock`/`lock_now` viết ở §2.3 làm `SELECT ... WHERE id = :id FOR UPDATE` — chạy
trên một `id` không có row thật sẽ tìm ra **0 dòng**, và code phải quyết định làm gì (không được để
executor tự chọn: raise). Test `test_private_api.py` **bắt buộc** một fixture mới `seed_auth_session
(pg_dsn) -> AuthSession` thật sự `INSERT` một row (dùng `PostgresSessionStore.create()` hoặc insert
tay), trả về row đã có `id` thật, và `require_session` override phải trả về **đúng row đó** — không
phải một `AuthSession(...)` dựng tay riêng. Dọn row này (và hai row `app_setting` cố định) ở cuối
mỗi test — cả hai khoá `app_setting` (`private_pin`, `private_unlock_throttle`) là **global**, test
chạy sau sẽ thấy trạng thái của test chạy trước nếu không dọn.

- `backend/tests/test_private_pin.py` (non-pg, thuần hàm — không cần fixture DB): `is_valid_pin`
  nhận đúng 6 chữ số ASCII và **từ chối `"٦٦٦٦٦٦"`, `"²²²²²²"`**, 5/7 ký tự, có chữ cái, chuỗi rỗng,
  khoảng trắng · hash/verify round-trip · chuỗi hash chứa đúng `m=19456,t=2,p=1` · sai PIN trả
  `False` chứ không nổ.
- `backend/tests/test_private_gate.py` (`@pytest.mark.pg`, dùng `seed_auth_session`): **F1 §0.2 —
  `create`/`update` từ chối `is_private=true` khi khoá, response không lộ nội dung ở bất kỳ trường
  nào** · lock nổ đúng ở lần sai **thứ 10 / 20 / 36** (không phải 9 hay 11) · giữa hai mốc thử tự do
  · đang khoá thì verify **không** chạy và bộ đếm **không** tăng · hết lock cuối thì bộ đếm về 0 ·
  mở khoá đúng reset bộ đếm · **`private_until` KHÔNG đổi sau nhiều request đọc** (§1.4) ·
  **`lock_now` thật sự ghi `NULL` xuống DB — verify bằng cách nạp lại row từ MỘT session/engine
  khác, không đọc lại object đang giữ trong tay** (đây chính là bẫy F1/T2: object có thể "đúng"
  trong RAM dù `UPDATE` chưa từng chạy) · JSONB throttle sống sót qua việc nạp lại bằng session
  khác (bẫy mutation-tracking, không đọc lại đúng object đang mutate) · `set_pin` cũng bị throttle
  (§1.6) và khoá đúng thứ tự với seed-bootstrap (không đua) · seed bootstrap chỉ chạy một lần và
  `bootstrap` tắt vĩnh viễn sau `set_pin`.
- `backend/tests/test_private_api.py` (`@pytest.mark.pg`, dùng `seed_auth_session`): mã lỗi
  401/409/422/429 đúng hình dạng envelope ở §2.4 (không phải `{"detail": {"detail": ...}}` lồng) +
  header `Retry-After` là chuỗi số nguyên · `/api/me` trả 4 field mới · **không cookie ⇒ 401** cho
  cả 3 endpoint (chứng minh chúng nằm trong `protected_api`).
- Frontend `vitest`: **giữ phạm vi ở logic thuần** (dự án hiện chưa có `@testing-library` hay
  harness render component — không thêm trong 016). Test hàm/controller tách khỏi JSX: đưa
  logic "so `private_until` với `now`, quyết định lật trạng thái + gọi `removeQueries`" vào một
  hàm/hook thuần nhận `queryClient` qua tham số, test hàm đó trực tiếp (đếm ngược đúng, lật đúng
  lúc hết hạn, gọi đúng `removeQueries({ queryKey: taskInvalidationKey })`) — không test qua render
  `<PrivateGate />` đầy đủ.
- Playwright (`frontend/e2e/`, mở rộng `fixtures/tasks.ts`): fixture hiện tại **chỉ** mock
  `/api/me` (3 field cũ) và `/api/tasks*` (`fixtures/tasks.ts:154-216`) — **bắt buộc thêm** handler
  cho `/api/private/unlock`, `/api/private/lock`, `/api/private/pin`, và mở rộng body `/api/me`
  với 4 field mới + trạng thái mock (biến trong closure của fixture, không phải state thật) để mô
  phỏng: mở khoá đúng → badge đổi · sai 10 lần liên tiếp → 429 + nút disabled + đếm ngược đúng ·
  **Khoá lại ngay** → badge về đóng · response `/api/tasks` đổi theo trạng thái khoá/mở của mock.

### 4.1 🔒 Red-proof bắt buộc

*Một cổng bảo mật chưa bao giờ đỏ là một cổng chưa được chứng minh đang chạy* (luật đặt ra ở
`013`). Làm **hai** lượt, dán output cả hai chiều vào PR:
1. Tạm bỏ bước kiểm `locked_until` trong `_verify_under_throttle` ⇒ test thang leo phải **ĐỎ** →
   khôi phục ⇒ **XANH**.
2. Tạm cho `private_until` cuộn theo mỗi lần đọc ⇒ test §1.4 phải **ĐỎ** → khôi phục ⇒ **XANH**.

Không commit bản phá. Nếu một trong hai không đỏ được, **dừng và báo** — nghĩa là test đang không
đo thứ nó tưởng.

## 5. Acceptance (chạy thật, dán output — không viết "đã làm xong và nó chạy")

Nhãn ở đầu mỗi dòng: **[CI]** = một job trong `ci.yml` bắt lỗi này nếu sai · **[thủ công]** =
không job nào bắt được, chỉ nghiệm thu bằng đọc output tay (T2 báo rõ 4 job thật hiện có cho code
mới: `Backend checks`, `Production dependency check`, `Frontend checks`, `Frontend e2e`,
`Migration QA` — không có job riêng cho "RSS", "red-proof", hay "không có migration").

- **[CI]** `uv run ruff check .` **và** `uv run ruff format --check .` — **hai lệnh**, đúng danh
  sách `ci.yml`, không phải danh sách trong trí nhớ (bài học 26/07).
- **[CI]** `uv run pytest -m "not pg"` (job `Backend checks`) · `uv run pytest -m pg` trên
  `pgvector/pgvector:pg18` cục bộ (mô phỏng job `Migration QA`).
- **[CI]** `uv sync --frozen --no-dev && uv run --no-dev python -c "from app.main import create_app; create_app()"`.
- **[CI]** `npm run lint` · `npx vitest run` · `npm run build` · `npx playwright test`.
- **[thủ công]** Đo RSS: in RSS trước và sau 20 lần unlock liên tiếp, ghi số vào PR (canh 19
  MiB/lần trên máy 256 MB — `014` đang theo dõi trục này). Không job CI nào đo cái này.
- **[thủ công]** Red-proof §4.1, cả hai chiều — dán output tay, không job nào tự chạy phá-rồi-vá.
- **[thủ công]** Xác nhận **không có file migration mới** trong diff (`git diff --stat` phần
  `backend/alembic/versions/`) — không có gate CI nào chặn nếu ai đó lỡ tạo một cái.
- Báo cáo tách rõ **ĐÃ CHẠY / CHƯA CHẠY / vì sao vẫn tin là đúng** (quy ước `agent-tasks/README.md`)
  — dùng đúng hai nhãn trên để phân định phần nào có receipt máy móc, phần nào chỉ có lời khai.

### 5.1 Đường khôi phục khi quên PIN — quyết định tường minh, không phải lỗ hổng bỏ sót

App một người dùng, không có admin, không có "quên mật khẩu qua email". T3 chỉ đúng: nếu chủ quên
PIN (kể cả PIN bootstrap trước khi đổi), **không có đường trong app** để lấy lại — private data
vẫn còn nguyên (không mất), chỉ là không xem được qua UI nữa.

**Đường khôi phục duy nhất, ghi rõ để không ai phải tự nghĩ ra lúc cần:**
```sql
DELETE FROM microsched.app_setting WHERE key = 'private_pin';
```
Chạy tay qua `NEON_MIGRATOR_URL` (đúng khuôn migration thủ công đã dùng cho `008d`/`008g`). Sau đó
`app_setting` không còn row PIN ⇒ lần gọi `set_pin` kế tiếp coi như "chưa có PIN", đặt PIN mới
không cần `current_pin` (§2.3). **Không mất dữ liệu riêng tư** — chỉ mất chính PIN, dữ liệu vẫn
mã hoá nguyên vẹn chờ PIN mới mở lại.

## 6. 🚫 KHÔNG được làm

1. **Không tạo migration.** §0.1 — mọi thứ cần đã có trong schema.
2. **Không đụng `backend/app/domain/reading.py`.** Cổng đã đúng; 016 chỉ cấp giá trị cho nó.
3. **Không cho `private_until` cuộn theo hoạt động** ở bất kỳ đâu, đặc biệt `load_valid()`.
4. **Không dùng PIN làm/dẫn xuất key material** (§1.2); `private_pin.py` không import `crypto.py`.
5. **Không dùng `RFC_9106_LOW_MEMORY`** hay bất kỳ profile dựng sẵn nào (§1.8).
6. **Không viết giá trị PIN khởi tạo vào source/test/commit** (§1.7). Test tự sinh PIN riêng.
7. **Không đường verify thứ hai** vòng qua throttle (§1.6).
8. **Không `str.isdigit()`** cho kiểm định dạng PIN (§2.2).
9. **Không chạm Neon, không tự merge.** T1 giữ hai việc đó.
10. **Không thêm dark mode, không thẻ thô, không hardcode màu** (`ui-brief.md` §6).
11. **Không mutate `AppSetting.value` tại chỗ** (`row.value["k"] = v`) — luôn gán lại toàn bộ dict
    (§2.3). SQLAlchemy không tự theo dõi thay đổi bên trong dict thường.
12. **Không set `private_until`/`locked_until`/`fail_count` lên object `AuthSession`/`AppSetting`
    tham số mà không nạp lại bằng `SELECT … FOR UPDATE` trong `db` của request hiện tại** — object
    tham số thuộc một session DB khác (§2.3), sửa nó không ghi gì xuống Postgres dù response vẫn
    trả mã thành công.
13. **Không tạo `is_private=true` khi khoá** ở bất kỳ đường ghi nào (create/update) — §0.2, bắt
    buộc trong phạm vi 016, không phải việc riêng.
14. **Không dựng lại `AuthSession` bằng constructor tay trong test API** (`AuthSession(...)` không
    insert) — dùng fixture seed row thật (§4). Mẫu cũ ở `test_tasks_api.py::_auth()` chỉ đúng cho
    test không cần ghi `private_until` xuống DB thật.

## 7. Việc của CHỦ trước khi chạy task

- [ ] Bật **Docker Desktop** (lane `-m pg` và build cục bộ). Quên thì lỗi sẽ là
      `Cannot connect to the Docker daemon` / `pytest` skip toàn bộ lane `pg` — nhận ra ngay thay
      vì đi debug.
- [ ] Đặt `PRIVATE_PIN_BOOTSTRAP=<6 chữ số>` vào `backend/.env` (dev) **và**
      `fly secrets set PRIVATE_PIN_BOOTSTRAP=…` (prod). Không đặt ⇒ app vẫn chạy bình thường,
      chỉ là chưa có PIN và UI sẽ mời đặt PIN lần đầu.

## 8. Sau khi merge (việc của T1, ghi ở đây để không ai làm thay)

- **KHÔNG** `alembic upgrade` (§0.1).
- Xác nhận SHA sống ở `/api/readyz` khớp `git rev-parse HEAD`.
- Kiểm tay trên prod: mở khoá bằng PIN thật → task riêng tư hiện lại → **Khoá lại ngay** → biến
  mất. Đây là bước duy nhất chứng minh cửa một chiều ở §0 đã đóng lại thành cửa hai chiều.
- Ghi **hai dated note** vào `docs/auth-brief.md` §3: TTL 15′ → **36′**, và "passphrase" →
  **PIN 6 số + throttle leo thang 10/20/36**. Đây là đảo quyết định đã khoá, không phải làm rõ —
  luật `docs/` bắt thêm dated note, không viết đè.
