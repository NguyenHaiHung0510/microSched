# 016 — QA product cho private unlock, hard TTL và contrast

> **Trạng thái: DRAFT — owner đã cho phép thực thi ngày 2026-08-15; chưa có
> acceptance nào được coi là PASS.** Đây là product-QA contract, không thay thế
> implementation contract `agent-tasks/016-private-unlock.md` và không ghi nhận
> production acceptance thay cho biên lai chạy trên production.
>
> **Executor đề xuất:** T3 QA + owner handoff iPhone vật lý · **Model/effort:**
> Luna/high · **Viewport bắt buộc:** 390×844 và 1280×800 · **Target production:**
> `https://microsched.fly.dev`.

## 0. Mục tiêu và ranh giới

Spec này trả lời một câu hỏi ở tầng sản phẩm: khi người dùng mở, khoá, hết hạn
hoặc đổi PIN, dữ liệu riêng tư có bị lộ qua UI, API response, cache trong RAM,
ảnh chụp, log hay lock-screen không; và người dùng iPhone có thể nhận biết,
thao tác và khôi phục được lỗi hay không.

Phạm vi gồm:

- private display gate trên session thật: `/api/me`, `/api/private/unlock`,
  `/api/private/lock`, `/api/private/pin`;
- read/write boundary của các bề mặt private đang có (task, note, tracker,
  annotation/calendar nếu fixture hiện tại bật được), lỗi và không-existence
  oracle;
- hard TTL 36 phút, lock-now, logout/401/visibility/focus recovery, global
  throttle và đổi PIN;
- contrast/keyboard/focus/touch trên bản production build ở hai viewport và
  handoff trên iPhone vật lý;
- local, CI và production release gates.

Không thuộc scope:

- migration, Argon2id implementation, schema hoặc redesign private policy;
- offline persistent read cache/outbox/Dexie. Các invariant đó thuộc
  `agent-tasks/017-qa-offline-outbox.md`; spec này chỉ kiểm không để UI private
  hiện lại sau lock/TTL trong session hiện tại và ghi handoff sang 017;
- tracker CRUD/dashboard đầy đủ (011a), subscription CRUD/F6 (011c), hoặc
  startup log của cron (011e);
- dùng PIN, email, tên, tracker, thuốc, endpoint push hay dữ liệu thật của chủ
  trong fixture, report, screenshot, log hoặc commit.

### 0.1 Dữ liệu và credential an toàn

Mỗi run tạo dữ liệu synthetic có prefix `QA016_` và UUID ngẫu nhiên. PIN chỉ là
**dev-only mock credential** được sinh trong memory của test/run; không ghi literal
PIN vào spec, source, terminal capture, artifact hay issue. Production không
được dùng credential thật trong artifact: nếu owner quyết định chạy unlock thủ công
trên account allowlist thì nhập trực tiếp, crop screenshot về nội dung UI,
và report chỉ ghi “allowlisted account”, không ghi email/PIN.

Private fixture phải có ít nhất một cặp:

- `QA016_PUBLIC_MARKER`: dữ liệu được phép nhìn thấy khi khoá;
- `QA016_PRIVATE_MARKER`: dữ liệu không được xuất hiện khi khoá.

`QA016_PRIVATE_MARKER` không được có tên người, thuốc, địa chỉ, email, token,
secret, cookie, endpoint hoặc giá trị giống dữ liệu production.

## 1. Hợp đồng trạng thái và acceptance

Mỗi mục dưới đây phải có receipt raw, trạng thái `PASS`, `FAIL`, `SKIP` hoặc
`CHƯA VERIFY ĐƯỢC`, kèm lane và exact command/URL. Không đánh dấu PASS từ code
đọc, CI docs hoặc test mock nếu lane yêu cầu browser/production/iPhone thật.

### P-01 — Locked is the safe default

1. Tạo session synthetic ở trạng thái locked. `GET /api/me` không trả
   `private_until` đang hiệu lực và UI hiển thị gate/placeholder, không render
   `QA016_PRIVATE_MARKER`.
2. Read API của từng bề mặt private không trả plaintext, ciphertext, title/name,
   count, timestamp hay error detail có thể suy ra row private. Một row private
   không được làm thay đổi empty-state count theo cách tạo existence oracle.
3. Create/update private khi locked trả đúng HTTP/code contract của implementation
   (hiện hành là `403`/private-locked), database không có row/partial write mới,
   response không chứa request marker.
4. Một read/write public ngay cạnh đó vẫn hoạt động, chứng minh gate không làm
   chết toàn app.

### P-02 — Unlock và lock-now

1. Gửi dev-only mock PIN hợp lệ tới `/api/private/unlock`; response có
   `private_until` aware, xấp xỉ 36 phút kể từ server clock, và chỉ session hiện
   tại được mở.
2. Reload hoặc mở tab thứ hai với session locked không được kế thừa private gate
   ngoài contract của session đó. Không có private data trong URL/query/local
   storage/cookie.
3. Sau `/api/private/lock` (`204`), UI xoá data private đang hiển thị trong cùng
   tab, mọi read private tiếp theo lại locked, còn public marker vẫn có.
4. Unlock lại hiển thị đúng private marker; không tạo bản sao row và không đổi
   private content.

### P-03 — Hard TTL, không rolling

1. Trong local test dùng clock seam/fake time hoặc chờ ngắn theo seam đã có,
   chứng minh `private_until` chỉ được set lúc unlock và không bị kéo dài bởi
   `/api/me`, reload, focus, visibility, read private hay thao tác public.
2. Tại deadline, UI tự khoá, xoá private query/data hiện hành và không cần reload
   trang. Tab bị background rồi foreground phải re-check deadline trước khi render.
3. Sau deadline, private write/confirm lại bị chặn; không được coi session còn mở
   chỉ vì client timer chưa chạy.

### P-04 — Global throttle và đổi PIN

1. Trên DB throwaway, wrong PIN lần thứ 10, 20, 36 lần lượt mở các lock 5, 8,
   18 phút; response locked là `429`, có `Retry-After` và không gọi verify PIN
   khi đang locked. Xác nhận bằng raw `app_setting`, không chỉ UI.
2. Sau lock cuối, counter reset theo contract; PIN đúng vẫn không bị ghi vào log.
3. `POST /api/private/pin` dùng cùng throttle; current PIN sai không đổi hash,
   new PIN không đúng 6 ASCII digits bị `422`, đổi thành công không tự mở hoặc
   kéo dài private session.
4. Bootstrap indicator chỉ là trạng thái UI; hash/PIN/bootstrap value không xuất
   hiện trong `/api/me`, response, screenshot hoặc log. Không lưu dev-only mock
   credential vào repo.

### P-05 — Privacy boundary khi transition

Đo sau từng transition: locked → unlock, unlock → lock-now, TTL expiry, logout,
401/session expiry và tab focus trở lại.

- Không còn `QA016_PRIVATE_MARKER` trong DOM visible, React/query cache, local
  storage/session storage, URL, console, network response capture hoặc ảnh.
- Không hiện private title/body/name ở error, toast, dialog description, badge,
  page title, accessibility tree hoặc lock-screen text.
- Không dùng “số lượng row = 0” hoặc thời điểm request để suy ra private
  existence trong UI.
- Nếu browser devtools/Playwright capture được request body/response thì redact
  artifact; không lưu artifact chứa mock private content ngoài run directory
  được owner chỉ định.

### P-06 — Contrast, focus, keyboard và touch

Trên bản build production, sau khi mọi CSS transition ổn định, đo bằng computed
style/rendered color, không chỉ nhìn bằng mắt:

- text thường đạt WCAG 4.5:1; text lớn đạt 3:1;
- input border, focus ring, throttled badge, error/status indicator và mọi
  non-text boundary cần nhận biết đạt ít nhất 3:1 với surface kề bên;
- primary action, tab, dialog close và retry có hit area tối thiểu 44×44 CSS px
  theo HIG của thiết bị chính; không overflow ngang ở 390px;
- keyboard Tab có focus visible, thứ tự hợp lý, dialog không trap ngoài chủ ý,
  Escape/close trả focus về trigger; không có hành vi chỉ sống bằng hover;
- input PIN không zoom ngoài ý muốn trên iPhone, `inputmode`/maxlength đúng,
  lỗi nằm trong accessibility tree và không đẩy action ra ngoài viewport.

Đo ở cả 390×844 và 1280×800, ở normal/focus/error/locked/throttled/unlock
success. Screenshot chỉ là evidence thị giác; số ratio/bounds phải nằm trong
report dạng text.

### P-07 — Regression và negative proof

Mỗi guard quan trọng phải có RED→GREEN receipt trong một run an toàn:

1. Tạm thời vô hiệu hoá filter locked hoặc xoá timer re-check trong working tree
   throwaway; test đúng invariant phải đỏ, sau đó restore và xanh.
2. Tạm thời hạ border/focus/badge dưới ngưỡng; phép đo phải đỏ, restore token và
   chạy xanh.
3. Tạm thời làm mock `/api/private/lock` lỗi; UI không được tuyên bố đã khoá khi
   server chưa xác nhận. Restore route và chạy lại.

Không commit các phá guard. Ghi rõ patch tạm, red output và restore output; nếu
không thể thực hiện vì môi trường thì `CHƯA VERIFY ĐƯỢC`, không suy luận.

## 2. Ma trận lane bắt buộc

| Lane | Cách chạy | Điều chứng minh | Không được claim |
|---|---|---|---|
| L0 unit/static | `cd backend; uv run pytest tests/test_private_pin.py`; `uv run ruff check .`; `cd frontend; npm test; npm run build` | pure PIN contract, static và build | PG/iPhone/production chưa chứng minh |
| L1 PG throwaway | `cd backend; uv run pytest -m pg tests/test_private_gate.py tests/test_private_api.py` với `APP_ENV=local`, OAUTH state synthetic, `ENCRYPTION_MASTER_KEY` synthetic và PIN sinh runtime; raw schema/row query sau run | throttle, TTL/session row, no partial private write | không dùng Neon production; không lưu mock credential |
| L2 browser | `cd frontend; npx playwright test e2e/private.spec.ts` ở mobile 390×844 và desktop 1280×800, production build/preview | UI gate, contrast, keyboard/touch, transitions | route mock không chứng minh API/production |
| L3 CI | required `Backend checks`, `Frontend checks`, `Frontend e2e`, `Migration QA`, `Production dependency check`, `Repository hooks` theo workflow hiện hành | commit/CI reproducibility | CI xanh không chứng minh production acceptance |
| L4 production read-only | gọi `GET /api/readyz`, assert JSON `commit` đúng SHA dự kiến và `db=up`; browser trên `https://microsched.fly.dev` bằng account allowlist; chỉ synthetic/mock scope được owner cho phép | deploy/HTTPS/cookie/locked privacy surface | không bật flag, không nhập credential thật vào artifact, không claim private unlock nếu chưa được owner cho phép |
| L5 iPhone | owner handoff trên iPhone vật lý, Safari/PWA Home Screen, 390×844 tương đương; crop ảnh trước khi lưu | focus, keyboard, dialog, safe-area, lock/expiry visual thật | Chromium mobile emulation không thay iPhone |

L1 phải restore toàn bộ env, cache settings và DB fixture trong `finally`; nếu
container/process chết giữa chừng vẫn chạy cleanup rồi xác nhận `docker ps` không
còn container test. Không dùng quyền migrator/owner trong runtime app.

## 3. Production gate và explicit no-activation

Trước L4/L5, người chạy phải ghi receipt current:

1. exact deployed SHA từ JSON field `commit` của `/api/readyz`, `db=up`, một Fly machine/process;
2. owner authorization dated cho lane private/product được phép chạy;
3. xác nhận không thay đổi `ENABLE_INPROCESS_CRON`, VAPID, OAuth allowlist, PIN,
   secret hoặc production data trong QA.

“Nút đang có trong UI”, `fly.toml`, local PASS, CI green hay log startup không phải
production acceptance. Nếu thiếu authorization hoặc không có synthetic fixture
được owner duyệt, L4/L5 ghi `CHƯA VERIFY ĐƯỢC`; không bịa tài khoản/credential.

## 4. Report và artifact policy

Report append-only phải có:

- exact HEAD, worktree status, browser/OS/build SHA, lane và command/URL;
- từng P-01…P-07: `PASS/FAIL/SKIP/CHƯA VERIFY ĐƯỢC`, raw output liên quan và
  phân loại `OBSERVED` hoặc `INFERRED`;
- lỗi có severity + file:line/selector + expected/observed metric;
- screenshot của 390×844, 1280×800 và iPhone nếu có, đã crop tab/bookmark/avatar,
  gắn SHA-256/MD5 trước khi đọc comment; không chứa private marker, PIN, email,
  cookie, token hay dữ liệu thật;
- explicit list những lane chưa chạy và vì sao.

Không sửa `agent-tasks/README.md` để biến receipt cũ thành PASS. Không gọi
`/api/healthz` là readyz; không gọi CI/docs là production proof.

## 5. Quan hệ với spec hiện có

- `agent-tasks/016-private-unlock.md`: implementation/security contract và unit/PG
  DoD; file này thêm product matrix, rendered contrast, production/iPhone và
  artifact boundary.
- `agent-tasks/011a-qa-tracker-slice.md`: tracker/dashboard QA; file này chỉ kiểm
  private gate cross-surface và không lặp tracker CRUD matrix.
- `agent-tasks/011c-qa-subscription.md`: subscription/F6 QA; file này không thay
  F6 acceptance.
- `agent-tasks/017-qa-offline-outbox.md`: persistent cache/outbox/real-SW; file
  này chỉ handoff sau lock/TTL và không claim offline purge.
- `agent-tasks/011e-cron-observability-receipts.md`: cron startup/queue logs; file
  này không claim scheduler sống từ log đó.
