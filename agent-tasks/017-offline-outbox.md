# 017 — offline: hàng đợi ghi (outbox) + cache đọc bền

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L2
> · Skill gợi ý: không cần · MCP cần: Playwright (nghiệm thu §7 cần mô phỏng offline).**
> **Trạng thái: ✅ SPEC SẴN GIAO 2026-08-02 (T1 Opus 5 viết). Ba lựa chọn định cỡ ở §3 mục
> 1–3 chủ đã duyệt; đã qua phản biện **T2 Codex** (4 P0 + 3 P1) và **T3 Gemini 3.1 Pro High**
> (9 finding). T1 kiểm từng finding, vá mọi finding xác nhận đúng và ghi biên bản ở §10.**
> **KHÔNG có migration. Backend có vá idempotency cho các POST create còn thiếu (§5).**
> **Chạy SAU `011c`** — tức sau khi cả bốn họ thực thể (`task`/`note`/`calendar`/`tracker`) đã tồn tại.

## 0. Bối cảnh — vì sao lô này tồn tại, và vì sao nó là HAI nửa

Kiến trúc chốt **offline-first** từ 2026-07-20 (`frontend-brief.md` §3: Dexie + outbox tự viết,
**KHÔNG** sync-engine) và luồng ghi chốt kín ở `tracking-brief.md` §8.1/:150 — *bấm = ghi ngay vào
IndexedDB kể cả offline → toast 10 giây Hoàn tác → soft-delete; UUIDv7 sinh ở client (B1) nên online
hay offline cũng một nút.* `008m` đã mở hai seam (id sinh ở client + ghi idempotent) và **cố ý** dừng
ở đó.

Lô này dựng hàng đợi thật lên trên hai seam đó. Nhưng nó phải làm **hai nửa**, không phải một:

```
   NỬA ĐỌC                              NỬA GHI
   persist cache TanStack Query         Dexie queue + máy flush
   → mở app offline THẤY dữ liệu        → chạm offline GHI được
              └───────────────┬───────────────┘
                 thiếu một nửa ⇒ nửa kia vô dụng
```

**Vì sao bắt buộc phải có nửa đọc** (đây là lỗ hổng giữa hai quyết định đúng, không phải phạm vi
phình ra): lưới ghi một chạm của `011a` **render từ danh sách tracker lấy ở server**. Cache của
TanStack Query hôm nay chỉ nằm trong RAM. Mất mạng + reload ⇒ lưới không hiện ⇒ **không có nút nào để
bấm** ⇒ hàng đợi ghi vĩnh viễn rỗng. `frontend-brief.md` §1 đã ghi *"+ persist vào IndexedDB"* trong
bảng chốt nhưng **không lô nào nhận nó** — `017` nhận.

**Lô này cũng đóng ca `008m` cố ý để hở** (`008m` §0, sửa 26/07): *"treo → reload → bấm lại"* hiện
tạo hai bản ghi, vì `id` chỉ sống trong bộ nhớ trang. Có `id` nằm bền trong Dexie thì hết.

## 1. Sự thật đo được (T1 đo trên `develop` 2026-08-02 — đừng suy từ tài liệu)

| Thứ | Trạng thái thật |
|---|---|
| `dexie@4.4.4` trong `package.json` | ✅ đã cài — **0 lần import** trong `frontend/src/`. Dependency chết từ lúc scaffold. |
| Package persist của TanStack Query | ❌ **chưa có**. Chỉ `@tanstack/react-query@5.101.2`. |
| `vite-plugin-pwa@1.3.0` | ✅ đã cấu hình trong `vite.config.ts`, workbox precache **vỏ app** (html/js/css). Không precache dữ liệu. |
| Seam ghi idempotent | ✅ sống ở `task` (`backend/app/domain/tasks.py:61`) **và** `note` (`notes.py:58`). `calendar_source`/tracker-group/tracker/subscription đã được spec trước yêu cầu; **child item + calendar event + mọi POST create còn thiếu phải được vá ở §5**. |
| Session bootstrap offline | ❌ `/api/me` lỗi mạng ⇒ `App` hiện “Không kết nối được API”, không render màn domain dù cache đã bền. Xem §2.5. |
| Điểm gọi mutation hôm nay | **38** trên 4 file: `NotesScreen.tsx` 15 · `TasksScreen.tsx` 13 · `PrivateGate.tsx` 7 · `App.tsx` 3. Sau `010`+`011` sẽ nhiều hơn đáng kể. |
| Write route domain | 14 hôm nay (7 task + 7 note) → ~24 sau `010`+`011`. |
| `PATCH` của task/note | ✅ **gán giá trị tuyệt đối** (`payload.model_dump(exclude_unset=True)` rồi `setattr`) — **không** phải toggle. Nghĩa là replay PATCH vốn đã an toàn. Đây là lý do §3 mục 1 chọn được phạm vi rộng mà gần như không tốn thêm. |
| `DELETE /api/tasks/{id}` gọi lần hai | ❌ **`404`, không phải `204`** — `readable()` lọc mất dòng đã soft-delete. Xem §2.3, đây là một cái bẫy thật. |

**Không có migration. Không thêm cột.** Thấy mình đang mở `alembic` là dấu hiệu đi chệch — dừng, hỏi.

## 2. Bốn chỗ sẽ SAI nếu làm theo trực giác — đọc kỹ nhất mục này

### 2.1 🔴 Query-key allowlist **KHÔNG đủ** — một query có thể trộn public + private

`auth-brief.md` §4 R6 khoá cứng: response chứa private **không persist vào IndexedDB**; private chỉ
sống trong RAM tab đang mở. Nhưng `tasks`/`notes` dùng **cùng query key** lúc locked và unlocked. Khi
unlocked, một response danh sách trộn cả dòng `is_private=false` lẫn `is_private=true`. Allowlist
`['tasks']` theo key vẫn ghi nguyên plaintext private xuống đĩa — cổng `016` thủng sau một reload.

**Bắt buộc, bốn lớp (làm cả bốn):**
1. **Sanitize ở mức item trước khi serialize.** Query danh sách chỉ ghi snapshot đã lọc từng dòng
   `is_private === false`; query chi tiết có `is_private === true` không được dehydrate. Mỗi query
   key trong allowlist phải có một sanitizer typed riêng; query mới mặc định **không persist**. Cấm
   transformer “đệ quy xoá mọi object có field `is_private`” — nó dễ sót cấu trúc envelope và dễ xoá
   nhầm object không phải entity.
2. **`purgePrivateSurface()` trung tâm.** Khi khoá tay, TTL hết hoặc privacy response ⇒ xoá private
   khỏi RAM Query cache rồi **ghi đè persisted snapshot bằng bản public-only đã sanitize**; không xoá
   public cache đang cần cho offline. Logout/`401` thì purge toàn bộ RAM + persisted Query snapshot
   và session bootstrap. Hai nhánh đều không đụng outbox.
3. **Hai namespace lưu trữ tách hẳn.** Query persister và Dexie outbox không cùng DB/store. Purge
   cache **không bao giờ** được xoá outbox — outbox có thể chứa bản ghi private chưa tồn tại ở đâu
   khác, xoá nó là mất dữ liệu thật.
4. **Rehydrate không cấp quyền private.** Không persist `private_until`; offline bootstrap (§2.5)
   luôn dựng cổng ở trạng thái **locked**. Private pending trong outbox vẫn nằm trên đĩa nhưng không
   được overlay lên màn hình khi locked.

> **Phân biệt với outbox:** hàng đợi ghi **được phép** chứa nội dung riêng tư đang chờ gửi vì
> `tracking-brief.md`:150 đã chốt “ghi ngay vào IndexedDB kể cả offline”; đó là dữ liệu duy nhất.
> Cache đọc là bản sao của dữ liệu đã ở server, nên áp R6 tuyệt đối: **outbox giữ · cache lọc + purge**.

### 2.2 🔴 Classifier phải **route-aware**, không chỉ nhìn status code

Cùng một `404` có bốn nghĩa: DELETE đã chạy ở lượt trước; id sai thật; parent private bị gate che;
restore chưa thành công. Cùng một `409` có thể là trùng tên business hoặc create với id vô hình.
Bảng “status → hành động” toàn cục sẽ âm thầm nuốt dữ liệu. Vì vậy mỗi row bắt buộc mang metadata
typed: `operation_kind`, `resource`, `requires_private`, `idempotency_mode`,
`dependency_operation_id`, `affected_query_keys` — **không parse URL bằng regex để đoán**.

| Nhóm | Tín hiệu đã phân theo route + metadata | Xử lý |
|---|---|---|
| **A. Tạm thời** | lỗi mạng/timeout · `408` · `425` · `429` · `5xx` | Retry backoff 1→2→4→8→16→30s; `429` tôn trọng `Retry-After`. **Không park chỉ vì số lần thử** — số lần chỉ là telemetry; hết mạng nhiều ngày không biến payload đúng thành payload hỏng. |
| **B. Chờ đăng nhập** | `401` / `UnauthenticatedError` | Giữ nguyên queue, dừng flush, hiện “Cần đăng nhập để gửi N mục”. Sau OAuth thành công tự flush. Không tăng retry, không park, không purge outbox. |
| **C. Chờ private unlock** | exact private-locked response; **hoặc** `404`/`409` trên row `requires_private=true` khi client biết gate đang locked | Giữ row, không retry cho tới khi unlock. Unlock xong gửi lại: `2xx` ⇒ xong; còn `404`/`409` ⇒ park vì lúc này không còn gate để giải thích. Row private đang hold **không chặn** các row public độc lập phía sau (§2.4). |
| **D. Đã đạt postcondition** | mọi `2xx`; thêm `404` **chỉ cho DELETE** row public/đang-unlocked (resource đã vắng đúng như mong muốn) | Gỡ queue. `404` restore **không** thuộc nhóm này. `409` create **không bao giờ** tự coi là success; idempotent replay đúng phải trả `200` từ backend. |
| **E. Hỏng thật** | `400`/`409`/`422` business/validation đã xác định; `404` không thuộc C/D; 4xx còn lại | Park, không auto-retry, không chặn row độc lập. Hiện lỗi gốc; descendants bị suppress (§2.4). |

🔒 **Hai luật chống nuốt lỗi:**
- Success duplicate chỉ đến từ **hợp đồng route idempotent trả `200`**, không suy từ `409`.
- `011b` và các router trước có thể dùng envelope private khác nhau; lúc thi công phải chuẩn hoá về
  **một error code máy-đọc-được** (`PRIVATE_UNLOCK_REQUIRED`) trước khi classifier dựa vào nó. Không
  so chuỗi tiếng Việt/Anh.

### 2.3 🔴 `DELETE` replay 404 là success; `restore` 404 thì KHÔNG

Đo được ở §1: `DELETE /api/tasks/{id}` lần hai trả `404`, vì dòng đã soft-delete bị `readable()` lọc.
Ca thật: server xử lý DELETE, response mất trên 3G, retry nhận 404. Với row DELETE đã được app tạo từ
một entity có thật, postcondition “resource vắng” đã đạt ⇒ nhóm D.

Nhưng `restore` muốn postcondition ngược lại (“resource hiện lại”). `404` ở restore nghĩa là **chưa
đạt**, nên phải đi C nếu private-gated, còn lại đi E. **Không sửa backend thành 204-khi-không-thấy**:
UI trực tiếp vẫn cần 404 thật; outbox có `operation_kind` nên mới đủ thông tin phân biệt replay.

### 2.4 🔴 Dependency trỏ tới **operation row**, và FIFO không được chặn cả thế giới

Offline tạo group G → tracker T → entry E là một chuỗi ba tầng. Entity UUID không nói được entity đó
đã có trên server hay vừa được row nào tạo. `dependency_operation_id` phải trỏ tới **primary key của
row outbox cha**, không trỏ entity id. Parent có trên server ⇒ `null`; parent cũng đang queue ⇒ id
row tạo parent.

- **Một request một lúc, ưu tiên thứ tự chèn**, nhưng được **skip** row `failed`/auth-held/
  private-held và mọi descendant của nó để gửi row độc lập phía sau. “FIFO nghiêm” toàn cục sẽ làm
  một private write chờ unlock chặn mọi public write vô hạn.
- Parent failed ⇒ toàn bộ descendants thành `suppressed` và UI hiện **một lỗi gốc**. Discard parent
  ⇒ discard descendants. Parent hold ⇒ descendants hold, không gửi vượt.
- Tạo row + xác định dependency phải ở **một Dexie transaction**, không regex URL.

### 2.5 🔴 Có cache domain vẫn chưa đủ — `/api/me` phải có offline bootstrap công khai

`App.tsx` chỉ render `SignedIn` khi query `['session']` thành công. Mất mạng + reload hiện làm
`/api/me` lỗi và app dừng ở “Không kết nối được API”; cache task/tracker có bền cũng không có màn để
hiện. Vì chủ đã duyệt “offline đọc sau reload”, `017` bắt buộc persist một **session bootstrap tối
thiểu**:

- Chỉ giữ `email`, `signed_in_at`, `expires_at` và cờ “đã xác thực lần cuối”; **không persist
  `private_until`** hay bất kỳ quyền private nào. Rehydrate luôn `private_unlocked=false`.
- Chỉ render public shell offline khi `now < expires_at`; quá hạn ⇒ màn “Cần kết nối để xác thực
  lại”, không đoán session còn sống.
- Một `/api/me` online thành công thay snapshot. `401` hoặc logout chủ động ⇒ purge bootstrap + RAM/
  persisted Query cache, **không purge outbox**; sau OAuth cùng account thì flush tiếp.
- Offline shell không được có nút unlock (unlock phải online) và không render private pending từ
  outbox (§2.1).
- 🔴 **Sửa nhánh render thật trong `App.tsx`:** network error khi đã có `session.data` rehydrated
  không được render cả alert lẫn `SignedIn`. Card “Không kết nối được API” chỉ hiện khi
  `session.isError && !loggedOut && !session.data`; có cached bootstrap thì render đúng một public
  shell + offline banner.

## 3. Đã khoá — chép ra code, không mở lại

1. ✅ **Phạm vi ghi = MỌI write domain** (chủ duyệt 2026-08-02): create + patch + soft-delete +
   restore + thao tác trên `*_item`, cho cả bốn họ `task`/`note`/`calendar`/`tracker`. **Loại trừ**
   `auth` (login/logout) và `private` (unlock/lock) — hai thứ đó **bản chất phải online**, xếp hàng
   một lần mở khoá để gửi sau là vô nghĩa và nguy hiểm. Lý do chọn rộng: (a) tick một checkbox lúc
   mất mạng là thao tác offline phổ biến nhất của app to-do, (b) `PATCH` đã là gán-tuyệt-đối (§1) nên
   replay vốn an toàn — gần như không tốn thêm, (c) **một LUẬT** ("mọi write domain đi qua outbox")
   rẻ hơn **một DANH SÁCH NGOẠI LỆ** khi các slice sau phải nhớ.
2. ✅ **Nửa đọc nằm trong lô này** (chủ duyệt 2026-08-02) — §4.4.
3. ✅ **Chạy sau `011c`** (chủ duyệt 2026-08-02), kèm ràng buộc ngược cho `011a` ở §9.
4. **Dexie giữ đúng MỘT bảng domain: hàng đợi ghi.** Không mirror thực thể, không bảng `tasks`/
   `notes` cục bộ. Query persister dùng **namespace/DB khác** (§2.1), không được chia store với outbox.
5. **Command typed, không phải request mù.** Row là discriminated union theo `operation_kind` +
   adapter registry tĩnh; method/path/body chỉ là phần vận chuyển. Adapter sở hữu optimistic apply,
   reconcile, discard/rollback và affected query keys (§4.2).
6. **Không Background Sync.** Safari không hỗ trợ API đó ⇒ hàng đợi chỉ flush **khi app đang mở**.
   Đây là giới hạn đã biết, ghi vào PR, **kiểm trên iPhone thật** (`frontend-brief.md` §5).
7. **Chỉ số toàn cục “N đang chờ gửi”**, không đeo badge lên từng dòng. Badge từng dòng chỉ xuất hiện
   cho optimistic entity bị park, để trạng thái hỏng không giả làm dữ liệu đã sync (`ui-brief.md` §6).
8. **`sonner` giữ nguyên vai trò:** toast 10 giây + Hoàn tác vẫn là UI của thao tác ghi. Hoàn tác
   mục chưa gửi ⇒ coalesce/gỡ command create; đã gửi ⇒ enqueue DELETE. Cùng một nút.
9. **Một flusher trên toàn origin, không chỉ một tab.** Dùng Web Locks API với lock
   `microsched-outbox-flush`; cờ module chỉ là lớp phụ. Web Locks cần secure context: iPhone test qua
   **production HTTPS** (hoặc local HTTPS proxy), không qua `http://192.168…`. Nếu `navigator.locks`
   không tồn tại ở production, không âm thầm flush cạnh tranh: hiện cảnh báo “trình duyệt không hỗ
   trợ đồng bộ offline” và giữ queue cho tới môi trường hỗ trợ.

## 4. Frontend — thi công

### 4.1 `frontend/src/lib/outbox-db.ts` — Dexie, một bảng

Một bảng `outbox`, khoá chính tự tăng = `operation_id` (thứ tự chèn là thứ tự ưu tiên; đừng sắp
theo timestamp). Mỗi row là command typed và mang tối thiểu:

- `operation_kind` / `resource` / method / path / JSON body;
- `entity_id`, `parent_id`, `requires_private`, `idempotency_mode`;
- `dependency_operation_id` (§2.4), `group_id` nếu một thao tác UI có nhiều bước;
- `affected_query_keys`, trạng thái (`pending` / `auth_hold` / `private_hold` /
  `outcome_unknown` / `failed` / `suppressed`), số lần thử, mốc thử tiếp theo, mốc tạo và lỗi cuối.

`dependency_operation_id` tham chiếu row outbox, không tham chiếu entity UUID. Tạo command + nối
dependency trong một Dexie transaction. Method/path không được dùng để suy ngược `operation_kind`.
Transport lỗi sau khi request đã dispatch phải chuyển row sang `outcome_unknown`; retry giữ nguyên
operation/client UUID và payload. Lỗi trước dispatch (`not_attempted`) chỉ là telemetry, row vẫn
`pending` và không tăng attempts — hai nhánh không được gộp.

**Lazy-open:** không `new Dexie()` ở module top-level. Mở qua factory có `try/catch`; IndexedDB bị
chặn ⇒ app vẫn chạy online, hiện cảnh báo offline unavailable, không crash toàn bundle.

**Không thêm dependency nào ngoài Dexie** (đã có) và **một** package persist chính thức của TanStack
Query cho §4.4. Quy ước supply-chain: `frontend-brief.md` §6.

### 4.2 🔴 Seam ghi dùng chung + adapter typed theo domain

Hôm nay có **38 điểm gọi mutation** rải trên 4 file (§1); sau 010/011 sẽ nhiều hơn. Dựng một cửa
`queuedMutation`, nhưng **không** làm một hàm generic “nhét payload vào cache”. Payload create thiếu
server defaults/timestamps; DELETE trả 204; dashboard là derived; import thay cả collection.

Mỗi `operation_kind` đăng ký một adapter tĩnh (functions **không** lưu vào Dexie):

```text
encodeCommand(input) → row serializable
optimisticApply(queryClient, row)
reconcileSuccess(queryClient, row, serverResponse)
discardOrRollback(queryClient, row)
affectedQueryKeys(row)
```

- Online ⇒ gọi `apiRequest` như hiện nay, rồi `reconcileSuccess`.
- Offline/lỗi mạng/timeout ⇒ lưu command trước, sau đó optimistic apply. Trước `setQueryData`,
  adapter phải `await queryClient.cancelQueries()` cho mọi affected key để response in-flight không
  ghi đè state optimistic. Create dùng **client UUIDv7 đã nằm trong payload**, không sinh lại.
- Reload offline ⇒ rehydrate public server snapshot, rồi replay `optimisticApply` của **public** rows
  pending theo operation order. Private row không overlay khi gate locked (§2.1).
- Server success ⇒ thay optimistic model bằng response thật; 204 chạy adapter tương ứng. Park ⇒ giữ
  optimistic entity nhưng gắn trạng thái “Chưa gửi được”; chỉ khi chủ discard mới rollback/rebuild.
  Không để dữ liệu hỏng trông như đã sync.
- Chuỗi create→patch→delete chưa gửi phải **coalesce**: delete huỷ cả chuỗi; nhiều absolute PATCH có
  thể giữ bản cuối. Không coalesce operation có side effect (`renew`, import).

Rồi chuyển **mọi write domain** sang cửa này. Auth/private/web-push registration/cron cố tình bypass
phải có comment. Không rải direct `apiRequest` trong component domain.

🔴 **Thao tác nhiều request:** `NotesScreen.reorderItems` hiện gửi hai PATCH bằng `Promise.all`; một
thành công, một fail sẽ để thứ tự nửa vời. `017` phải thay bằng một endpoint reorder **atomic** nhận
danh sách `{item_id, position}` tuyệt đối trong một transaction; retry tự idempotent. Không queue hai
PATCH như một “group” rồi giả vờ có atomicity.

### 4.3 `frontend/src/lib/outbox-flush.ts` — coordinator, không chỉ vòng retry

Lấy Web Lock (§3 mục 9), xử lý một request một lúc theo §2.2/§2.4. Kích hoạt khi app khởi động,
`online`, focus, sau write online thành công, sau login, và sau private unlock.

**Chặn refetch ghi đè optimistic state:** domain queries dùng một helper query chung với
`refetchOnReconnect=false`; reconnect/focus đi qua sync coordinator. Khi có pending rows, coordinator
cancel domain refetch liên quan → flush các row runnable → reconcile response → chỉ sau đó
`invalidateQueries(affected_query_keys)`. Không pending ⇒ invalidate public queries ngay. Polling của
domain query liên quan cũng pause khi có pending command. Query `['session']` vẫn được phép refetch
để phát hiện `401`; nó không thuộc domain cache.

Hai tab cùng nhận `online` phải cạnh tranh Web Lock; tab thắng flush, tab kia chờ rồi reload queue.
Test hai **page** thật, không chỉ gọi hai promise trong một module. Cờ module chỉ chống re-entry trong
cùng tab; không được gọi nó là bảo vệ chính.

### 4.4 Nửa đọc — public snapshot + offline bootstrap, private bằng 0 byte

Thêm persister chính thức của TanStack Query vào IndexedDB **namespace riêng**, với allowlist query
key **và sanitizer typed ở mức item** (§2.1). Đặt `maxAge=7 ngày`, buster theo build SHA. Snapshot
session bootstrap theo §2.5 dùng `expires_at` thật làm trần riêng; buster không được kéo dài session.

Dữ liệu offline phải nói rõ là cũ: dải đầu màn *“Đang ngoại tuyến · dữ liệu lúc HH:mm”*. Mở offline
luôn private-locked. Persisted store phải qua test quét plaintext canary private ra **0 kết quả**;
đồng thời outbox store vẫn giữ canary private pending — hai invariant ngược nhau, test cả hai.

`purgePrivateSurface()` là seam dùng chung nhưng có hai nhánh: lock/TTL/privacy-response ⇒ xoá private
khỏi RAM rồi reserialize public-only snapshot; logout/`401` ⇒ purge toàn bộ Query namespace +
bootstrap. Cả hai **không** gọi `Dexie.delete()` trên outbox DB.

### 4.5 UI của hàng đợi

Một chỉ số nhỏ ở khung app: *“N đang chờ gửi”* (ẩn khi `N = 0`), bấm mở danh sách. Phân biệt
*chờ mạng · cần đăng nhập · cần mở khoá riêng tư · gửi thất bại*. Mục failed hiện lý do người-đọc-được
+ nút **Xoá bỏ**; xoá gọi adapter rollback và kéo descendants. Entity optimistic tương ứng cũng mang
badge “Chưa gửi được”. Không nút retry cho validation/business failure; auth/private hold tự chạy lại
khi điều kiện được đáp ứng.

`data-testid`: `outbox-indicator` · `outbox-panel` · `outbox-item` · `outbox-item-discard` ·
`offline-banner`.

## 5. Backend — mở nốt idempotency seam, vẫn không migration

Lời hứa offline chỉ đúng khi **mọi POST tạo bản ghi** retry cùng payload không tạo dòng thứ hai.
Single-flight/Web Lock không che được ca server commit xong nhưng response mất. Do đó:

1. Kiểm toàn bộ POST user-domain sau khi 010/011 merge. Mọi create entity còn thiếu — tối thiểu
   `task_item`, `note_item`, `calendar_event`; cộng bất kỳ group/tracker/entry/subscription/annotation
   nào chưa nhận id client — phải nhận `id: UUIDv7 | None`, dùng khuôn `008m`: `ON CONFLICT DO
   NOTHING`, `201` mới / `200` replay đọc được / `409` id vô hình. Parent + child insert chỉ chạy
   khi parent/child thật sự mới; không biến create replay thành update.
2. `calendar import` không tạo một outbox row cho từng event: queue nguyên `ImportRequest` JSON;
   endpoint thay-sạch đã idempotent theo nội dung + transaction (`010a` §4.2). `renew` giữ nguyên
   `entry_id` qua retry (`011c` §2.4). Restore/cancel/uncancel là absolute state command.
3. Thêm endpoint reorder note-item atomic (§4.2):
   `PATCH /api/notes/{note_id}/items/positions`, body
   `{"items": [{"id": <UUID>, "position": <int>}, ...]}`; validate mọi item thuộc đúng note, từ
   chối id trùng/position trùng, rồi cập nhật trong một transaction. Payload là absolute state nên
   retry tự idempotent. Không migration.
4. Chuẩn hoá privacy failure ở mọi router thành error code máy-đọc-được
   `PRIVATE_UNLOCK_REQUIRED`; giữ HTTP status hiện tại nếu cần chống enumeration. Classifier dựa
   `requires_private` + code, không dựa text.

**Không dùng một bảng idempotency key phụ.** PK UUIDv7 của bản ghi vẫn là key của chính nó.

## 6. Không được làm

- **Không** migration, **không** đổi schema, **không** thêm cột.
- **Không** mirror thực thể vào Dexie (§3 mục 4). Dexie giữ một bảng outbox; Query cache ở namespace
  khác và chỉ là public snapshot.
- **Không** chuyển sang TanStack DB / PowerSync / ElectricSQL / Zero (`frontend-brief.md` §3) — xem
  ngưỡng dừng ở §8.
- **Không** đưa auth/private unlock, web-push registration hay cron vào hàng đợi (§3 mục 1).
- **Không** persist private plaintext — kể cả nằm lẫn trong query public key (§2.1). Không blocklist.
- **Không** sửa backend thành `204` cho DELETE không tìm thấy (§2.3).
- **Không** coi single-tab flag là cross-tab lock; bắt buộc Web Locks (§3 mục 9).
- **Không** dựng Background Sync / periodic sync trong service worker (§3 mục 6).
- **Không** đổi timeout/error contract của `apiRequest`; bọc quanh nó. Có thể thêm export error-code
  parser dùng chung nếu router đã chuẩn hoá §5 mục 4.
- **Không** sinh lại `uuidv7()` bên trong seam ghi (§4.2).
- **Không** parse URL để đoán cache/dependency/classifier; command typed sở hữu metadata.
- **Không** đổi tên required check trong CI.

## 7. Nghiệm thu (Definition of Done)

1. `npm run build` + `npm run lint` + `npm test` xanh; `uv run ruff check` + `uv run pytest` xanh.
2. **Classifier unit — mỗi bài biết đỏ:** network/timeout/408/425/429/5xx retry; 429 tôn trọng
   `Retry-After`; 401 auth-hold; private 403/404/409 hold rồi unlock; DELETE-public 404 success;
   restore 404 failed; business 409/422 failed. Không test “status đơn lẻ” — truyền đủ typed metadata.
3. **Idempotency PG thật:** với **mọi POST create** được 017 phủ, gửi cùng UUIDv7 hai lần và mô phỏng
   “commit xong mất response” ⇒ đúng một row, lần replay 200. Bắt buộc có task-item/note-item/
   calendar-event; `renew` cùng `entry_id` chỉ tiến một kỳ. UUID khác nhưng trùng business name chỉ
   trả 409 ở resource có contract tên duy nhất thật: `calendar_source`, `tracker_group`, `tracker`,
   `subscription`. Task/note/event/annotation/entry và item được phép trùng title/label/content;
   classifier không được phát minh 409 cho các resource đó.
4. **Dependency + optimistic:** group→tracker→entry gửi đúng thứ tự; parent fail suppress descendants
   nhưng public row độc lập phía sau vẫn gửi; park giữ optimistic entity + badge; discard rollback;
   response server thay placeholder; create→patch→delete chưa gửi coalesce về 0 command.
5. **Race refetch:** reconnect trong lúc có 3 optimistic writes ⇒ refetch không ghi đè; sau flush,
   invalidate trả đúng state server. Test `NotesScreen` reorder qua endpoint atomic, không nửa-vời.
6. 🔒 **Private × storage — bài quan trọng nhất:** query mixed public/private được persist thành public
   only; query private detail = 0 byte; lock/TTL/logout/401 purge RAM + Query store; **outbox canary
   private vẫn còn**. Reload offline không hiện private và gate luôn locked.
7. **Offline session bootstrap:** online một lần → offline + reload ⇒ render public shell/cache;
   `private_until` không tồn tại trên đĩa; snapshot quá `expires_at` ⇒ không render shell; 401/logout
   purge bootstrap nhưng giữ outbox.
8. **PWA Playwright lane riêng:** config hiện tại có `serviceWorkers:'block'`, nên thêm lane production
   build/preview với `serviceWorkers:'allow'`. Chờ `navigator.serviceWorker.ready` **và controller**
   trước `context.setOffline(true)` + reload. API write lúc offline phải bị abort thật, không
   `route.fulfill()` giả. Kiểm: shell + public data hiện, banner offline, write tăng queue, online về 0.
9. **Cross-tab:** hai page cùng origin, cùng IndexedDB, cùng nhận `online`; Web Lock bảo đảm mỗi command
   gửi đúng một lần. Test này không được thay bằng hai promise trong một module.
10. **Ca `008m` để hở:** create → response mất → reload → flush/bấm lại cùng payload ⇒ một bản ghi.
11. Đường happy online của 008–011 còn xanh; `gh pr checks <PR>` xanh toàn bộ.
12. **iPhone thật qua production HTTPS** (Web Locks cần secure context): PWA đã cài, máy bay →
    reload → thấy public cache → ghi task/note/entry → tắt máy bay ⇒ queue về 0. Không nghiệm thu
    qua `http://192.168…`. Ghi rõ cái **đã chạy** và cái chỉ suy luận.

## 8. Ngưỡng dừng — cửa nâng cấp hai chiều

`frontend-brief.md` §3 ghi sẵn: *"nếu outbox tự viết bắt đầu phình thì chuyển [sang TanStack DB]"*.
Ngưỡng đó cần một con số, nếu không nó không bao giờ kích hoạt. **Chạm bất kỳ điều nào dưới đây ⇒
DỪNG, báo T1/chủ, không tự đi tiếp:**

- Tổng **core generic** (`outbox-db.ts` + `outbox-flush.ts` + coordinator + queued-mutation, không tính
  adapter domain/tests) vượt **400 dòng**.
- Phải viết logic **merge/conflict resolution** giữa hai phiên bản server/client.
- Dependency một-cha dạng chain ở §2.4 không đủ, cần nhiều cha/đồ thị topo tuỳ ý.
- Optimistic adapter bắt đầu mirror cả entity store thay vì chỉ overlay command lên Query cache.

Ba dấu hiệu đó nghĩa là bài toán đã đổi họ, và tự viết tiếp là đang xây một sync-engine mà không gọi
tên nó.

## 9. Ràng buộc ngược cho `011a` (T1 đã ghi vào spec `011a`, đừng bỏ)

`017` chạy sau `011c`, nên tới lúc đó `010a`/`010b`/`011a`/`011b`/`011c` đã đẻ thêm rất nhiều điểm
gọi mutation. Để `017` chỉ phải bọc **một** seam thay vì đuổi theo ~60 điểm gọi, `011a` §5.3 nhận một
ràng buộc: **mọi write của màn tracker đi qua một helper mutation dùng chung**, không rải `apiRequest`
khắp component. Các lô `010`/`011b`/`011c` chép theo. Bảo hiểm rẻ, trả bằng đúng một chỗ để sửa.

## 10. Vòng phản biện T2 + T3 (2026-08-02) — đã vá, giữ để không lặp

**T2:** Codex review code/spec thật, 4 P0 + 3 P1. **T3:** `gemini-3.1-pro-high`, 9 finding; một
follow-up dùng để làm rõ R6/409. T1 kiểm từng finding với code + brief, không chép máy móc.

### Finding xác nhận đúng và đã vá

1. **P0 — query-key allowlist vẫn persist private** vì list query trộn public/private. Vá item-level
   sanitizer + `purgePrivateSurface` + namespace tách (§2.1/§4.4). Bác remedy “persist
   `private_until` tới TTL”: trái thẳng `auth-brief.md` R6, private plaintext phải 0 byte trên disk.
2. **P0 — offline reload không qua được `/api/me`.** Vá public session bootstrap không mang quyền
   private (§2.5).
3. **P0 — child POST không idempotent.** Single-flight không che commit-xong-mất-response. Vá mọi
   POST create theo UUIDv7/PK, thêm reorder atomic (§5).
4. **P0 — classifier theo status sẽ nuốt lỗi.** Vá typed route metadata, 401/429/private 404/409,
   DELETE-vs-restore và bỏ mâu thuẫn “retry vô hạn nhưng >50 park” (§2.2–2.3).
5. **P1 — optimistic contract quá mơ hồ + refetch race.** Vá adapter typed, coalesce, server
   reconciliation và sync coordinator (§4.2–4.3).
6. **P1 — dependency theo entity id + cờ một tab không đủ.** Vá operation-id chain, skip hold,
   descendant suppression và Web Locks cross-tab (§2.4/§3).
7. **P1 — Playwright hiện chặn service worker.** Vá lane PWA production riêng, chờ SW controller,
   abort mạng thật và test hai tab (§7).
8. **Minor — Dexie top-level có thể crash khi IndexedDB bị chặn.** Vá lazy factory + visible online
   fallback (§4.1).

**T3 verification pass sau vá** bắt thêm 5 chỗ nối dây, đã vá một lượt rồi dừng: `App.tsx` render
alert + shell cùng lúc; purge private xoá nhầm public offline cache; Web Locks cần HTTPS; optimistic
apply chưa cancel in-flight query; endpoint reorder thiếu path/DTO (§2.1/§2.5/§3/§4.2/§5). Không mở
vòng tự-vá thứ ba — executor phải chứng minh bằng acceptance §7.

### Nghi ngờ đã kiểm và bác/thu hẹp

- **PATCH replay:** task/note là absolute assignment, không phải blocker; vẫn cần adapter reconcile.
- **DELETE 404:** đúng là success **chỉ cho DELETE đạt postcondition**; restore 404 không được nuốt.
- **UUIDv7 collision 409:** không coi success. Private + locked thì hold rồi thử khi unlock; còn 409
  thì park. Không làm yếu gate tồn tại.
- **Autoincrement FIFO lệch do clock:** bác — operation id không dùng clock.
- **Không Background Sync:** giới hạn Safari đã khoá, không phải defect.
- **Không migration:** vẫn đúng; id đã là PK, chỉ mở DTO/store/router seam.
