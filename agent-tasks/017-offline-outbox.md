# 017 — offline: hàng đợi ghi (outbox) + cache đọc bền

> **Executor: T2 Codex (`gpt-5.6-sol`, full-access `-s danger-full-access`, effort `high`) · Bậc: L2
> · Skill gợi ý: không cần · MCP cần: Playwright (nghiệm thu §7 cần mô phỏng offline).**
> **Trạng thái: DRAFT 2026-08-02 (T1 Opus 5 viết). Ba lựa chọn định cỡ ở §3 mục 1–3 **chủ đã duyệt
> 2026-08-02**; phần còn lại chưa qua phản biện T2/T3 — đừng giao thi công trước khi có ít nhất một
> vòng.**
> **KHÔNG có migration. Backend gần như không đổi (§5).**
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
| Seam ghi idempotent | ✅ sống ở `task` (`backend/app/domain/tasks.py:61`) **và** `note` (`notes.py:58`). `calendar`/`tracker` do `010a`/`011a` mang theo — **kiểm lại bằng mắt lúc thi công**, đừng tin dòng này. |
| Điểm gọi mutation hôm nay | **38** trên 4 file: `NotesScreen.tsx` 15 · `TasksScreen.tsx` 13 · `PrivateGate.tsx` 7 · `App.tsx` 3. Sau `010`+`011` sẽ nhiều hơn đáng kể. |
| Write route domain | 14 hôm nay (7 task + 7 note) → ~24 sau `010`+`011`. |
| `PATCH` của task/note | ✅ **gán giá trị tuyệt đối** (`payload.model_dump(exclude_unset=True)` rồi `setattr`) — **không** phải toggle. Nghĩa là replay PATCH vốn đã an toàn. Đây là lý do §3 mục 1 chọn được phạm vi rộng mà gần như không tốn thêm. |
| `DELETE /api/tasks/{id}` gọi lần hai | ❌ **`404`, không phải `204`** — `readable()` lọc mất dòng đã soft-delete. Xem §2.3, đây là một cái bẫy thật. |

**Không có migration. Không thêm cột.** Thấy mình đang mở `alembic` là dấu hiệu đi chệch — dừng, hỏi.

## 2. Bốn chỗ sẽ SAI nếu làm theo trực giác — đọc kỹ nhất mục này

### 2.1 🔴 Cache đọc bền sẽ **phá cổng riêng tư**, nếu persist tất cả

`auth-brief.md` §3 định nghĩa private unlock là **cổng hiển thị**: mở khoá ⇒ server trả nội dung
riêng tư đã giải mã; khoá lại (hoặc hết TTL 36 phút) ⇒ server ngừng trả. Cả cơ chế dựa vào việc
**client không giữ bản sao**.

Persist nguyên cache TanStack Query vào IndexedDB là đúng cái việc giữ bản sao đó: chủ mở khoá, xem
ghi chú riêng tư, khoá lại — nội dung vẫn nằm trên đĩa; reload ⇒ persister rehydrate ⇒ **nội dung
riêng tư hiện ra trong lúc cổng đang khoá**. Cổng một chiều mà `016` vừa đóng xong sẽ mở lại bằng
cửa sau, và không có gì báo.

**Bắt buộc, hai lớp (làm cả hai, không chọn một):**
1. **Lọc lúc dehydrate.** `shouldDehydrateQuery` chỉ cho qua query đã biết chắc là công khai. Cơ chế
   phải là **allowlist** (chỉ persist query key đã liệt kê), **không** phải blocklist — blocklist thì
   mỗi query mới của mọi slice sau mặc định bị persist, và không ai nhớ kiểm.
2. **Xoá sạch lúc khoá.** Khi cổng đóng (chủ bấm khoá, hoặc TTL hết, hoặc `403` private-locked từ
   server) ⇒ **purge toàn bộ cache đã persist**, không chỉ phần riêng tư. Lý do purge tất: một danh
   sách công khai vẫn có thể *tiết lộ sự tồn tại* của mục riêng tư qua số đếm/phân trang.

> **Phân biệt với outbox — hai thứ này KHÁC nhau, đừng áp cùng một luật.** Hàng đợi ghi **được phép**
> chứa nội dung riêng tư đang chờ gửi: `tracking-brief.md`:150 đã chốt "ghi ngay vào IndexedDB kể cả
> offline", đó là dữ liệu **chưa tồn tại ở đâu khác** — vứt đi là mất thật. Cache đọc thì ngược lại:
> nó là bản sao của thứ đã an toàn trên server, giữ lại chỉ để tiện, và nó vô hiệu hoá cổng. ⇒
> **outbox: giữ. Cache đọc: lọc + purge.**

### 2.2 🔴 Bốn loại lỗi, không phải hai — gộp lại là hàng đợi tự kẹt hoặc tự báo động giả

Đây là chỗ outbox tự viết hay mục rữa. Một `422` mà retry mãi sẽ **chặn cả hàng đợi phía sau** (FIFO).
Nhưng gộp mọi 4xx thành "hỏng vĩnh viễn" thì hai loại dưới đây bị báo động giả. Phân đúng bốn nhóm:

| Nhóm | Tín hiệu | Xử lý |
|---|---|---|
| **A. Tạm thời** | mất mạng, `TimeoutError`, `5xx` | Retry backoff (1s → 2 → 4 → 8 → 16 → 30, trần 30s). Không giới hạn số lần — mạng sẽ về. |
| **B. Cổng đóng** | `403` + đúng envelope private-locked | **Giữ nguyên trong hàng đợi, KHÔNG retry, KHÔNG park.** Chờ cổng mở lại rồi flush tiếp. Ca thật: chủ ghi một entry riêng tư lúc cổng mở → mất mạng → 40 phút sau mạng về nhưng TTL đã hết. Bản ghi đó **không hỏng**, nó chỉ đang chờ. Park nó là bắt chủ xử lý một thứ không sai gì cả. |
| **C. Đã xong rồi** | `200` cho `POST` create (008m) · `409` cho create (008m §2.3 mục 2) · `404` cho `DELETE`/`restore` | **Coi là THÀNH CÔNG**, gỡ khỏi hàng đợi, không báo lỗi. Xem §2.3. |
| **D. Hỏng thật** | `422`, `400`, `4xx` còn lại | **Park**: chuyển sang trạng thái `failed`, **không** auto-retry nữa, **không** chặn các mục sau, hiện cho chủ xem + xoá tay. Kèm trần: một mục ở nhóm A quá **50** lần thử cũng rơi xuống đây (để một lỗi lạ không quay vòng vĩnh viễn). |

🔒 **Nhóm D không được chặn hàng đợi.** Park là *nhấc ra khỏi dòng chảy*, không phải *dừng dòng chảy*.
Test bắt buộc: xếp `[hỏng-422, tốt, tốt]` ⇒ hai mục tốt vẫn phải gửi được.

### 2.3 🔴 `DELETE` gọi lần hai trả `404` — replay sẽ báo động giả

Đo được ở §1: `DELETE /api/tasks/{id}` lần hai trả **`404`**, vì `readable()` lọc mất dòng đã
soft-delete. Ca thật rất thường gặp: outbox gửi `DELETE`, server xử lý xong, **trả lời bị mất trên
đường** (mạng 3G chập chờn) ⇒ outbox retry ⇒ `404` ⇒ nếu áp luật "4xx = park" thì chủ thấy một mục
báo hỏng cho một thao tác **đã thành công**.

**Quyết định: sửa ở CLIENT, không sửa backend.** Outbox coi `404` trên `DELETE`/`restore` là nhóm C
(đã xong). **Không** đổi backend thành `204`-khi-không-thấy: người gọi tương tác (UI trực tiếp) cần
`404` thật để phân biệt "id gõ sai" với "đã xoá" — chỉ **outbox** mới biết rằng đây là *replay của
việc mình từng gửi*, và cái biết đó không truyền được sang server. Đúng chỗ để đặt luật là nơi có
thông tin.

### 2.4 🔴 Thứ tự: cha trước con, và con phải chết theo cha

Offline chủ tạo task T rồi thêm 3 checklist item vào nó. Hàng đợi có 4 mục, mục 2–4 tham chiếu `id`
của mục 1 qua URL (`/api/tasks/{T}/items`). Hai hệ quả:

1. **FIFO nghiêm, một request một lúc** (single-flight). Không chạy song song. Một user + hàng đợi
   nhỏ ⇒ song song không mua được gì, mà FIFO cho *cha-trước-con* **miễn phí** thay vì phải dựng đồ
   thị phụ thuộc.
2. 🔒 **Mục bị park (nhóm D) phải kéo theo mọi mục phụ thuộc.** Nếu tạo T hỏng `422` mà 3 item vẫn
   gửi, cả ba sẽ `404` liên tiếp và chủ thấy **bốn** báo lỗi cho **một** nguyên nhân. Luật: mỗi mục
   ghi kèm `depends_on` (id của bản ghi cha nếu URL/payload có nhắc tới một id do outbox tạo ra);
   cha bị park ⇒ con bị park im lặng, chỉ hiện **một** dòng lỗi gốc. Chủ xoá mục cha ⇒ xoá luôn con.

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
4. **Dexie giữ đúng MỘT bảng: hàng đợi ghi.** Không mirror thực thể, không bảng `tasks`/`notes` cục
   bộ. Mirror toàn bộ = sync-engine trá hình, đúng cái `frontend-brief.md` §3 đã loại.
5. **Không Background Sync.** Safari không hỗ trợ API đó ⇒ hàng đợi chỉ flush **khi app đang mở**.
   Đây là giới hạn đã biết, ghi vào PR, **kiểm trên iPhone thật** (`frontend-brief.md` §5) — đừng tin
   chay theo dòng này.
6. **Chỉ số toàn cục "N đang chờ gửi"**, không đeo badge lên từng dòng. Đường happy chiếm 99% và
   không đáng bị đánh thuế thị giác (`ui-brief.md` §6). Badge từng dòng **chỉ** xuất hiện cho mục đã
   park (nhóm D).
7. **`sonner` giữ nguyên vai trò**: toast 10 giây + Hoàn tác vẫn là UI của thao tác ghi, không đổi.
   Hoàn tác một mục **chưa gửi** ⇒ gỡ khỏi hàng đợi (đúng `tracking-brief.md`:150). Hoàn tác một mục
   **đã gửi** ⇒ xếp một `DELETE` vào hàng đợi. Cùng một nút — đó là điều seam `008m` mua về.

## 4. Frontend — thi công

### 4.1 `frontend/src/lib/outbox-db.ts` — Dexie, một bảng

Một bảng `outbox`, khoá chính tự tăng (thứ tự chèn **là** thứ tự FIFO — đừng sắp theo timestamp, hai
mục cùng mili-giây sẽ hoà và mất tất định). Mỗi dòng mang: phương thức HTTP, đường dẫn, body, trạng
thái (`pending` / `failed`), số lần đã thử, mốc thử kế tiếp, `depends_on` (§2.4), và mốc tạo.

**Không thêm dependency nào ngoài Dexie** (đã có sẵn, §1) và **một** package persist của TanStack
Query cho §4.4. Quy ước supply-chain: `frontend-brief.md` §6.

### 4.2 🔴 Seam ghi dùng chung — đây là phần quan trọng nhất của lô

Hôm nay có **38 điểm gọi mutation** rải trên 4 file (§1), mỗi chỗ tự gọi `apiRequest`. Bọc từng chỗ
một là 38 lần cơ hội sót, và mỗi slice sau lại thêm điểm mới.

**Dựng đúng một cửa** — ví dụ `frontend/src/lib/queued-mutation.ts`, xuất một hook mỏng bọc quanh
`useMutation` của TanStack Query. Hợp đồng của nó:

- Online ⇒ gọi thẳng `apiRequest` như hiện nay. **Đường happy không đổi một chút nào.**
- Offline (hoặc `apiRequest` ném lỗi mạng/timeout) ⇒ ghi vào Dexie, trả về **thành công lạc quan**,
  cập nhật cache TanStack Query bằng payload đang có.
- `id` cho create **lấy từ payload** (đã có sẵn nhờ `008m`/`009`), **không** sinh lại — sinh lại
  trong hàm này là tái lập đúng lỗi mà `008m` §2.5 đã vá.

Rồi **chuyển cả 38 điểm gọi sang cửa đó**. Không chừa. Điểm nào cố tình không đi qua (auth, private —
§3 mục 1) phải có **một dòng comment nói vì sao**, để lần soát sau không tưởng là sót.

### 4.3 `frontend/src/lib/outbox-flush.ts` — máy chạy hàng đợi

Single-flight, FIFO, phân loại lỗi theo đúng bốn nhóm §2.2. Kích hoạt flush khi: app khởi động · sự
kiện `online` · window focus · sau mỗi lần ghi thành công · cổng riêng tư vừa mở (để tháo nhóm B).

🔒 **Chống chạy chồng.** Hai kích hoạt gần nhau (ví dụ `online` và `focus` nổ cùng lúc khi rút máy
bay) không được tạo hai vòng flush song song trên cùng hàng đợi — nếu không, cùng một mục gửi hai
lần. Seam idempotent của `008m` che được ca create, nhưng **không** che `POST /items` (mỗi lần là một
item mới). Dùng một cờ "đang chạy" trong module. Test phải chứng minh biết đỏ.

### 4.4 Nửa đọc — persist cache, có cổng

Thêm persister của TanStack Query ghi xuống IndexedDB, với **allowlist** `shouldDehydrateQuery` và
**purge lúc khoá cổng** — cả hai bắt buộc, lý do ở §2.1. Đặt `maxAge` hợp lý (đề xuất 7 ngày) và
buster theo phiên bản build, để đổi hình dạng dữ liệu không làm app hiển thị cache lệch schema.

Dữ liệu offline hiển thị **phải nói rõ là cũ**: một dải nhẹ ở đầu màn *"Đang ngoại tuyến · dữ liệu
lúc HH:mm"*. Không có nó thì chủ nhìn số dashboard cũ mà tưởng là mới — sai lặng lẽ, đúng loại lỗi
`forward-spec.md` gọi là vi phạm "nhìn thấy được".

### 4.5 UI của hàng đợi

Một chỉ số nhỏ ở khung app: *"N đang chờ gửi"* (ẩn khi `N = 0`), bấm vào mở danh sách. Mục park hiện
lý do người-đọc-được + nút **Xoá bỏ** (kéo theo mục phụ thuộc, §2.4). Không nút "thử lại" cho nhóm D
— nó đã hỏng vĩnh viễn, mời chủ bấm lại là mời thất vọng.

`data-testid`: `outbox-indicator` · `outbox-panel` · `outbox-item` · `outbox-item-discard` ·
`offline-banner`.

## 5. Backend — kiểm, gần như không sửa

Lô này **không** đổi hợp đồng API. Hai việc kiểm, vá chỉ khi đo thấy sai:

1. **Seam idempotent create có mặt đủ bốn họ chưa** — `task`/`note` đã có (§1); kiểm `calendar`/
   `tracker` do `010a`/`011a` mang vào. Thiếu chỗ nào ⇒ vá theo đúng khuôn `008m` §2.2 (`ON CONFLICT
   … DO NOTHING` + validate `version == 7`), **không** phát minh khuôn mới.
2. **`POST /{parent}/{id}/items` KHÔNG idempotent** và lô này không làm nó idempotent. Hệ quả được
   che bằng §4.3 (chống chạy chồng) + FIFO. **Ghi thẳng giới hạn này vào PR** — đây là chỗ mỏng nhất
   của thiết kế, người review sau phải biết nó nằm ở đâu.

## 6. Không được làm

- **Không** migration, **không** đổi schema, **không** thêm cột.
- **Không** mirror thực thể vào Dexie (§3 mục 4). Dexie giữ đúng một bảng hàng đợi.
- **Không** chuyển sang TanStack DB / PowerSync / ElectricSQL / Zero (`frontend-brief.md` §3) — xem
  ngưỡng dừng ở §8.
- **Không** đưa `auth`/`private` vào hàng đợi (§3 mục 1).
- **Không** persist query chứa dữ liệu riêng tư (§2.1). **Không** dùng blocklist.
- **Không** sửa backend thành `204` cho `DELETE` không tìm thấy (§2.3).
- **Không** dựng Background Sync / periodic sync trong service worker (§3 mục 5).
- **Không** đổi `apiRequest` trong `frontend/src/api.ts` (hợp đồng đã vá ở `008i`) — bọc **quanh** nó.
- **Không** sinh lại `uuidv7()` bên trong seam ghi (§4.2).
- **Không** đổi tên required check trong CI.

## 7. Nghiệm thu (Definition of Done)

1. `npm run build` + `npm run lint` + `npm test` xanh; `uv run ruff check` + `uv run pytest` xanh.
2. **Mỗi bài test dưới đây phải chứng minh biết đỏ** (gỡ luật ⇒ test đỏ), ghi trong PR đã phá gì:
   - Ghi lúc offline ⇒ vào hàng đợi; online lại ⇒ tự gửi, hàng đợi rỗng.
   - `[hỏng-422, tốt, tốt]` ⇒ hai mục tốt **vẫn gửi được** (§2.2 nhóm D không chặn dòng).
   - `403` private-locked ⇒ mục **ở lại** hàng đợi, **không** bị park; mở cổng ⇒ gửi được (§2.2 B).
   - `DELETE` trả `404` ⇒ coi là **thành công**, không hiện lỗi (§2.3).
   - Cha bị park ⇒ con bị park im lặng, hiện **đúng một** dòng lỗi (§2.4).
   - Hai kích hoạt flush đồng thời ⇒ mỗi mục gửi **đúng một lần** (§4.3).
   - Tạo cha + 3 item offline ⇒ gửi đúng thứ tự, cha trước.
3. 🔒 **Test cổng riêng tư × persist** (bài quan trọng nhất): mở khoá → đọc nội dung riêng tư → khoá →
   **reload** ⇒ nội dung riêng tư **không** hiện. Kiểm thêm bằng cách soi thẳng IndexedDB: không có
   bản ghi nào chứa nội dung đó.
4. **Playwright, mạng thật giả lập** (`context.setOffline(true)`): mở app **rồi reload** lúc offline ⇒
   vẫn thấy dữ liệu + dải "Đang ngoại tuyến"; chạm ghi ⇒ chỉ số "N đang chờ gửi" tăng; bật mạng ⇒ về 0.
   Bài này là lý do lô cần MCP Playwright — nó là thứ **không** suy luận thay được
   (`agent-tasks/README.md` §"Quy ước BÁO CÁO").
5. **Ca `008m` để hở đã đóng:** ghi → reload giữa chừng → bấm lại ⇒ **một** bản ghi, không phải hai.
6. Đường happy online **không đổi hành vi**: mọi test của `008`–`011` còn xanh, không sửa bài nào để
   nó xanh.
7. `gh pr checks <PR>` xanh toàn bộ.
8. **Kiểm trên iPhone thật** (chủ hoặc T3): cài PWA, bật chế độ máy bay, ghi vài mục, tắt chế độ máy
   bay ⇒ đồng bộ. Ghi rõ trong PR cái gì **đã chạy** và cái gì **chỉ suy luận**.

## 8. Ngưỡng dừng — cửa nâng cấp hai chiều

`frontend-brief.md` §3 ghi sẵn: *"nếu outbox tự viết bắt đầu phình thì chuyển [sang TanStack DB]"*.
Ngưỡng đó cần một con số, nếu không nó không bao giờ kích hoạt. **Chạm bất kỳ điều nào dưới đây ⇒
DỪNG, báo T1/chủ, không tự đi tiếp:**

- Tổng `outbox-db.ts` + `outbox-flush.ts` + `queued-mutation.ts` vượt **400 dòng**.
- Phải viết logic **merge/conflict resolution** (hai phiên bản của cùng một bản ghi cần hoà giải).
- Phải dựng **đồ thị phụ thuộc** thật sự, tức FIFO + `depends_on` một tầng ở §2.4 không đủ.

Ba dấu hiệu đó nghĩa là bài toán đã đổi họ, và tự viết tiếp là đang xây một sync-engine mà không gọi
tên nó.

## 9. Ràng buộc ngược cho `011a` (T1 đã ghi vào spec `011a`, đừng bỏ)

`017` chạy sau `011c`, nên tới lúc đó `010a`/`010b`/`011a`/`011b`/`011c` đã đẻ thêm rất nhiều điểm
gọi mutation. Để `017` chỉ phải bọc **một** seam thay vì đuổi theo ~60 điểm gọi, `011a` §5.3 nhận một
ràng buộc: **mọi write của màn tracker đi qua một helper mutation dùng chung**, không rải `apiRequest`
khắp component. Các lô `010`/`011b`/`011c` chép theo. Bảo hiểm rẻ, trả bằng đúng một chỗ để sửa.
