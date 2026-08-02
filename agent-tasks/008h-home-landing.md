# 008h — trang home công khai tại `/`

> **Executor: Codex (T2).** Nhánh `feat/008h-home-landing` → PR nhỏ vào `develop`.
> Spec tự-chứa. Đọc `CLAUDE.md` + `AGENTS.md` trước; **`docs/ui-brief.md` là luật của task này.**

## ⛔ ĐANG HOÃN — làm SAU CÙNG, không phải bây giờ (chủ quyết 2026-07-26)

**Task này chuyển xuống cuối hàng: 008f → 008m → 008g → 009 → 010 → 011 → 012 → *rồi mới* 008h.**

Lý do chủ nêu, và nó đúng: **trang giới thiệu tính năng chưa thuyết phục được vì chưa có tính năng nào để giới thiệu.** Hiện chỉ có lát cắt `task` chạy thật. Dựng trang bây giờ là dựng một trang phải viết lại toàn bộ sau mỗi lát cắt 009–012. Trang home là thứ **đắp vào cuối**, khi đã có cái để trưng.

**Ba việc phải xong trước khi mở lại task này:**

1. **009–012 xong** — mới có ghi chú, lịch, tracker để nói tới ở thì hiện tại.
2. 🔒 **Một phiên riêng với chủ về nhận diện hình ảnh** — logo microSched, bộ icon, hình biểu tượng. Chủ **đích thân** làm, không giao executor. Trang này không dựng được ra hồn khi chưa có logo.
3. **Viết lại văn phong** — xem §2.3a.

Phần dưới đây **giữ nguyên làm hồ sơ**: bản dựng đã chọn, cấu trúc, và các ràng buộc UI/kỹ thuật còn giá trị. Trước khi mở lại phải viết lại **nội dung chữ và mọi dữ kiện hạ tầng/chi phí hiện hành**; phần hạ tầng đã đổi ngày 2026-08-02.

## 0. Bối cảnh — vì sao có task này

Khách chưa đăng nhập hiện thấy `LoginScreen` trong `frontend/src/App.tsx:33-61`: một thẻ trống giữa màn hình với đúng một nút. Repo này **công khai có chủ ý**, và mọi liên kết dẫn về `microsched.fly.dev` đều đổ vào cái thẻ đó.

Cái khó thật của trang này: **không ai đăng ký được.** Google OAuth + allowlist đặt bằng biến môi trường. Mọi khuôn mẫu landing page thương mại đều xây quanh một phễu đăng ký không tồn tại ở đây. Nên trang phải thành thật về chuyện đó **ngay từ đầu**, không phải chỉ ở dòng cuối.

## 1. Đã KHOÁ — chép ra code, không mở lại

1. **Trang này thay `LoginScreen`.** App vẫn không có router: `App.tsx` đã phân nhánh theo `loggedOut`. Home là nhánh chưa-đăng-nhập. **Không thêm `react-router` hay bất kỳ thư viện định tuyến nào.**
2. **Nút đăng nhập nằm ở header, góc phải, sticky.** Là thẻ `<a href="/auth/login">` bọc trong `Button asChild` — OAuth cần điều hướng cả trang, không phải `fetch`. Chép đúng cách `App.tsx:52-57` đang làm.
3. **Không hứa cái chưa có.** Hiện chỉ có slice `task` chạy thật — `backend/app/main.py:78` chỉ nạp `tasks_router`; note / calendar / tracker chưa có endpoint nào. Trang nói rõ phần nào đã chạy, phần nào đang xây. **Đây là ràng buộc, không phải gợi ý.**
4. **Không có con số thời gian thức máy trên trang.** Hạ tầng đã chuyển về always-on ngày 2026-08-02, nhưng deploy/restart/replacement và Neon wake-up vẫn làm một số đơn lẻ dễ gây hiểu sai. Con số **chi phí** cũng chỉ được dùng sau khi re-check ngay trước lúc viết: phải tách gross resource cost khỏi net invoice waiver có điều kiện (`cost-brief.md` §7.6), không được quảng bá “free tier”.
5. **Light-only, hồng ấm.** Không dark mode, không glassmorphism, không hiệu ứng ngoài `ui-brief.md`.
6. **Ảnh và video là placeholder trong task này.** Xem §2.4. Không tự đi chụp màn hình, không tự sinh ảnh.

## 2. Phải làm

### 2.1 ✅ Bản dựng thị giác — chủ đã chọn 2026-07-26

📍 **`docs/_local/home-b-chosen.html`** (gitignore, nằm trên đĩa cùng thư mục làm việc).

Ba bản A/B/C được dựng thành trang chạy được cho chủ bấm; chủ chọn **B — trưng bày sản phẩm**: khối "Nhìn thử" nằm trên nếp gấp, khung video 16:9 lớn, ba ảnh 9:16 xếp so le, hồ sơ kỹ thuật ở dưới. Đó là bản duy nhất thật sự đặt phần trưng bày lên trước — đúng thứ tự chủ đã chốt.

Chỗ nào bản dựng và `ui-brief.md` nói khác nhau: **`ui-brief.md` thắng về luật** (màu, tương phản, cỡ chữ), **bản dựng thắng về hình**.

Bản dựng đã được đo trên trình duyệt thật ở 390px: không cuộn ngang · 0 chữ dưới 12px · 0 đích chạm dưới 24px · 0 cặp trượt tương phản. **Đừng làm nó tệ đi khi chuyển sang React.**

⚠️ **Bố cục của bản dựng B viết cho nội dung CŨ.** Nội dung mới (§2.2a) có sáu trụ cột thay vì bốn — bố cục phải giãn ra theo, không phải nhét thêm vào chỗ cũ.

### 2.2 Cấu trúc — bảy khối, đúng thứ tự này

| # | Khối | Việc của nó |
|---|---|---|
| 1 | Header | Thương hiệu · neo `Trưng bày` `Kỹ thuật` `GitHub` · nút **Đăng nhập** góc phải |
| 2 | Hero | Một câu app là gì + một câu nói thật về tiến độ |
| 3 | Trưng bày | Placeholder video 16:9 + ba ảnh giao diện |
| 4 | Bốn chỗ làm khác | Bốn mục ngắn |
| 5 | Hồ sơ kỹ thuật | Bảng stack + ba dòng quyết định + hai nút ra ngoài |
| 6 | Quyền truy cập | Đoạn ngắn nói thật về chuyện không đăng ký được |
| 7 | Footer | Liên kết + một dòng kết |

### 2.2a 🔴 SÁU TRỤ CỘT — khung nội dung mới (chủ đề xuất 2026-07-26)

Bản copy ở §2.3 được viết quanh *"bốn chỗ làm khác"*. Chủ đã thay khung đó. Nội dung trang xoay quanh **bốn trụ chính + hai trụ phụ**:

| | Trụ | Nói gì |
|---|---|---|
| 1 | **microSched là gì** | Thay hẳn câu mở *"microSched là ứng dụng cá nhân tôi tự viết…"*. Đây là trụ, không phải một dòng giới thiệu. |
| 2 | **Hạ tầng đằng sau** | Fly.io 1× shared-cpu-1x 256MB always-on, Neon PG18 autosuspend độc lập, Docker, CD tự động, gross cost và invoice waiver có điều kiện |
| 3 | **Tech stack đằng sau** | FastAPI · SQLModel · React 19 · Vite · Tailwind v4 · TanStack Query · PWA |
| 4 | 🔑 **Harness engineering dựng nên nó** | Mô hình ba tầng T1/T2/T3, spec-trước-thi-công, luật biên lai, phản biện khác-họ. **Đây là trụ khác biệt nhất** — thứ mà một trang giới thiệu app cá nhân bình thường không có. |
| 5 | *(phụ)* **Bảo mật** | AES-256-GCM tầng ứng dụng, OAuth + allowlist, tách quyền DB |
| 6 | *(phụ)* **QA** | Dữ liệu ác ý, đo tương phản bằng số, kiểm trên thiết bị thật |

⚠️ Trụ 4 **chưa có tài liệu công khai nào để trỏ tới** — `harness-*` hiện nằm trong memory và trong `devops-brief.md` §7. Trước khi viết trụ này, kiểm xem có gì công khai được không, và **tuyệt đối không** để lọt tên tài khoản, tên công cụ nội bộ có gắn danh tính, hay chi tiết thói quen làm việc (`devops-brief.md` §1).

### 2.3a 🔴 VĂN PHONG — phải viết lại, đừng dùng bản §2.3 như đang có

Chủ đã đọc bản §2.3 và **chưa ưng**. Một chỉnh sửa cụ thể, bắt buộc:

🔒 **Bỏ hết ngôi "tôi". Viết ở góc nhìn khác.** Không *"tôi tự viết"*, không *"tôi thà nói vậy còn hơn hứa"*, không *"Bản cũ của app này…"* kể theo ngôi thứ nhất. Trang nói về **sản phẩm và cách nó được dựng**, không phải về tác giả kể chuyện mình.

Việc này còn phục vụ threat model: bớt ngôi thứ nhất là bớt vật liệu dựng pretext (`devops-brief.md` §1).

Bản §2.3 dưới đây **giữ lại làm hồ sơ** — phần *cách nói* thì bỏ; phần *sự thật kỹ thuật* chỉ là ảnh chụp trước 2026-08-02 và phải đối soát lại với decision record hiện hành.

### 2.3 Nội dung — ⚠️ BẢN CŨ, GIỮ LÀM HỒ SƠ, KHÔNG DÙNG NGUYÊN VĂN

⛔ **Bản dưới đây KHÔNG còn là nội dung sẽ dùng.** Chủ đã đọc và chưa ưng văn phong (§2.3a), và khung nội dung đã đổi sang sáu trụ cột (§2.2a). Giữ lại làm nguyên liệu lịch sử; **không giả định các dữ kiện hạ tầng/chi phí trong đó còn đúng** — Fly scale-to-zero đã bị đảo ngày 2026-08-02.

*(Ba câu đã bị gỡ ở vòng phản biện 26/07, đừng vô tình dựng lại: "Ghi vào máy trước, đồng bộ sau" — **sai**, không có đường ghi offline; tiêu đề kê bốn tính năng khi mới một cái chạy; và mọi con số thời gian đánh thức máy — resume có đuôi trễ ~12s nên không con số nào nói đúng được.)*

**Khối 2 — Hero**
> **Một cái app cho đúng một người.**
> microSched là ứng dụng cá nhân tôi tự viết và tự dùng mỗi ngày. Việc, ghi chú, lịch, thói quen — phần quản lý việc đã chạy thật, ba phần còn lại đang xây theo đúng thứ tự ghi trong hồ sơ kiến trúc.

*(Bốn tính năng cố ý **không** nằm ở dòng H1: chỉ mới một trong bốn chạy được, và H1 là chỗ lời hứa nặng nhất. Đừng đảo hai dòng này.)*

Badge: `Đơn người dùng` · `Tự chủ dữ liệu` · `PWA offline-first`

**Khối 3 — Trưng bày**
> **Nhìn thử**
> Giao diện thật, chụp từ bản đang chạy. Dữ liệu trong ảnh là dữ liệu mẫu.

Placeholder video, đặt chính giữa khung 16:9:
> **Lười quá làm sau `<3`**

Chú thích ba ảnh:
1. > Thêm việc bằng một dòng. Ô nhập tự dọn và giữ con trỏ để gõ tiếp.
2. > Mỗi việc tách được thành checklist, tick ngay trên thẻ.
3. > Ghim việc quan trọng lên đầu; việc trễ hạn tự nổi thành dải cảnh báo.

**Khối 4 — Bốn chỗ làm khác, đều là cố ý**

a. **Đúng một người dùng**
> Không chia sẻ, không phân quyền, không đồng bộ nhiều máy phải hoà giải xung đột. Bỏ hết những thứ đó thì phần còn lại chạy nhanh hơn và ít chỗ hỏng hơn.

b. **Cài lên màn hình chính như một app**
> Là PWA: vỏ ứng dụng nằm sẵn trên máy nên mở được cả khi mất mạng. Còn *ghi* khi ngoại tuyến thì chưa — outbox nằm trong lộ trình. Tôi thà nói vậy còn hơn hứa.

c. **Riêng tư là mã hoá thật, không phải một cái công tắc**
> Việc đánh dấu riêng tư được mã hoá AES-256-GCM ở tầng ứng dụng trước khi xuống cơ sở dữ liệu. Ai đọc được file dump cũng chỉ thấy chuỗi rác. Ghi chú sẽ dùng đúng cơ chế đó khi tới lượt.

d. **Một tiến trình, một nguồn sự thật**
> Bản cũ của app này từng chạy SQLite và Postgres cùng lúc rồi lạc mất bên nào đang giữ sự thật. Đó là lý do bản này được viết lại từ đầu.

**Khối 5 — Bên dưới là gì**
> Toàn bộ mã nguồn công khai, kèm hồ sơ quyết định giải thích vì sao chọn từng thứ.

Bảng stack:
- Backend — Python · FastAPI · SQLModel · Alembic
- Dữ liệu — PostgreSQL 18 trên Neon · pgvector · khoá chính UUIDv7
- Frontend — React 19 · TypeScript · Vite · Tailwind v4 · shadcn/ui · TanStack Query
- Hạ tầng — Docker · Fly.io Singapore · scale-to-zero · CD tự động
- Đăng nhập — Google OAuth, danh sách cho phép đặt bằng biến môi trường

Ba dòng quyết định:
> **Modular monolith, không microservice.** Một người dùng thì tách dịch vụ chỉ mua thêm chỗ hỏng.
> **Scale-to-zero.** Máy ngủ khi không ai dùng. Chi phí chạy khoảng 0,30 đô một tháng.
> **Mọi quyết định đều có hồ sơ.** Mỗi lựa chọn kiến trúc nằm trong một tài liệu tự chứa, kèm cả những phương án đã bị loại và lý do loại.

Hai nút: `Mã nguồn trên GitHub` · `Đọc hồ sơ kiến trúc`

**Khối 6 — Một lời về quyền truy cập**
> microSched chỉ mở cho đúng một tài khoản. Không có đăng ký, không có danh sách chờ, không có cách nào xin quyền — nút đăng nhập ở trên chỉ dành cho chủ sở hữu.
>
> Đây là thiết kế, không phải lỗi. Nếu bạn quan tâm cách nó được dựng thì mã nguồn và toàn bộ hồ sơ quyết định đều mở.

**Khối 7 — Footer**
- `microSched` — dự án cá nhân · `GitHub` · `Hồ sơ kiến trúc`
- Dòng kết: > Xây bằng tay, dùng mỗi ngày.

### 2.4 Ảnh và video — placeholder, có kích thước cố định

- **Video:** khối tỉ lệ **16:9** dùng `aspect-video`, nền `bg-brand-50`, chữ ở §2.3. 🔒 **Phải giữ đúng tỉ lệ bằng CSS**, không đặt chiều cao cứng — mai này thả video thật vào mà không có chỗ chừa sẵn thì cả trang nhảy layout.
  🔒 **Icon play: KHÔNG làm "mờ".** Nó là icon mang nghĩa ⇒ non-text contrast ≥3:1 trên `bg-brand-50` (WCAG 1.4.11). Dùng `text-primary`. **Cấm** `opacity-*`, `--n-400` (2,40:1 trên nền đó), `rose-300`, `rose-500`. *Bản spec đầu của chính task này viết "icon play mờ" — đó là lần thứ TƯ cùng một luật phát biểu một chiều mở cửa cho lỗi. Nay nói cả hai nửa.*
- **Ba ảnh:** ba khối placeholder tỉ lệ **9:16** (ảnh chụp iPhone). Dùng `<img>` trỏ **đúng** ba đường dẫn sau, không tự đặt tên khác — T1 sẽ thả file vào đúng chỗ đó:
  `/showcase-1.png` · `/showcase-2.png` · `/showcase-3.png` (tức `frontend/public/showcase-N.png`).
  File chưa có ⇒ để `alt` mô tả và một nền `bg-muted` giữ đúng tỉ lệ — **đừng** để ảnh vỡ.
- 🔒 **Không tự đi chụp màn hình app, không tự sinh ảnh.** Ảnh thật chứa dữ liệu thật; nguồn ảnh là việc của T1 (`devops-brief.md` §1).
- Mọi `<img>` phải có `width`/`height` hoặc bọc trong khung tỉ lệ. Ảnh không có kích thước là nguyên nhân số một của layout nhảy.

### 2.5 Ràng buộc kỹ thuật

- File mới trong `frontend/src/` — đặt tên `HomePage.tsx`, tách khối con nếu file quá dài.
- 🔴 **`App.tsx` phải đổi nhiều hơn một dòng, và đây là chỗ dễ làm hỏng nhất.** `App.tsx:115-119` bọc **mọi** trạng thái trong `<main className="min-h-screen bg-muted px-4 py-6 …"><div className="mx-auto max-w-5xl">`. Chỉ thay `<LoginScreen />` bằng `<HomePage />` là **nhốt trang home trong khung 1024px có lề xám** — sticky header không dính được mép trên, không khối nào tràn lề được. **Được phép** tái cấu trúc `App.tsx` để nhánh `loggedOut` render `HomePage` **ngoài** lớp bọc đó, miễn là hai nhánh còn lại (`session.isPending`, `session.isError`, `SignedIn`) **giữ nguyên hình dạng cũ**. Cách gọn nhất là chuyển lớp bọc vào trong từng nhánh; nếu bạn thấy đường khác, giải thích trong PR.
- **Neo — dùng đúng ba `id` này**, đừng tự đặt tên khác: `#trung-bay` · `#ky-thuat` · và nút `GitHub` là liên kết ra ngoài, **không** phải neo trong trang.
- 🔒 **Mọi `<section>` có neo phải có `scroll-mt-*`** đủ lớn hơn chiều cao sticky header. Thiếu nó thì bấm neo xong tiêu đề khối chui xuống dưới header và không ai thấy — lỗi im lặng, trông như neo trỏ sai chỗ.
- 🔒 **Header ở <640px phải thu gọn**, không được để năm phần tử tự xuống hàng. Header cao 80–120px trên màn 390px là ăn mất hơn 15% màn hình đứng, ở mọi lần cuộn. Ẩn ba neo chữ ở mobile là chấp nhận được (trang đủ ngắn để cuộn tay); **không** dùng menu chỉ mở bằng hover.
- 🔒 **Không chạm `TasksScreen.tsx`, `TaskForm.tsx`, `api.ts`, `task-ui.ts`.** Có một PR khác đang sống trong các file đó.
- Chỉ dùng 9 component sẵn có trong `components/ui/`. Thiếu ⇒ **dừng và hỏi**; **không** chạy `npx shadcn@latest add` (bốn cái bẫy ở `ui-brief.md` §8, cái nào cũng báo thành công khi hỏng).
- Neo trong header cuộn mượt tới khối tương ứng, và **phải tới được bằng bàn phím**.
- Trang này khách vãng lai xem ⇒ mỗi khối là một `<section>` có `aria-labelledby`, đúng một `<h1>`.
- 🔒 Không tương tác nào chỉ sống bằng `hover`. Không hardcode màu. Chữ ≥12px. Không chiều cao cứng cho thẻ.

### 2.6 Test

`frontend/tests/` — ít nhất: `HomePage` render đủ bảy khối; nút đăng nhập là `<a href="/auth/login">` (không phải `<button>`); và `App` hiện `HomePage` khi chưa đăng nhập.

## 3. KHÔNG được làm

- **Không** thêm router, **không** thêm dependency nào.
- **Không** đụng `backend/`, migration, hay bất kỳ file test backend nào.
- **Không** đụng bốn file đã kê ở §2.5.
- **Không** sửa chữ trong §2.3 (thấy sai thì dừng và báo).
- **Không** đưa lên trang: ảnh chụp có dữ liệu thật, địa chỉ email thật, tên thật, hay bất cứ gì về lịch sinh hoạt của chủ.
- **Không** thêm số liệu hiệu năng. Mọi con số chi phí phải re-check ngay trước khi viết và ghi đủ **gross resource cost + điều kiện net waiver** theo `cost-brief.md` §7.6; cấm claim vô điều kiện “\$0” hoặc “free tier”.
- **Không** thêm form, ô nhập email, nút "đăng ký", "liên hệ", hay bất cứ thứ gì gợi ý rằng có đường xin quyền truy cập.
- **Không** thêm analytics, tracking pixel, font từ CDN, script ngoài, ảnh remote — nói cách khác: **trang không được TỰ ĐỘNG tải bất cứ thứ gì ngoài origin**. Liên kết `<a href>` để người dùng tự bấm ra ngoài thì **được phép** — đó là hai chuyện khác nhau, đừng gộp. Hai đích duy nhất, ghi đủ URL, `target="_blank"` kèm `rel="noopener noreferrer"`:
  `https://github.com/NguyenHaiHung0510/microSched` và `https://github.com/NguyenHaiHung0510/microSched/blob/main/docs/architecture-brief.md`.
  ⚠️ **Đừng** trỏ đường dẫn tương đối kiểu `/docs/architecture-brief.md` — backend chỉ mount `frontend/dist`, nên nó rơi vào SPA fallback và trả về chính trang home.
- **Không** thêm dark mode. **Không** đổi tên required check trong CI.

## 4. Acceptance — kiểm chứng được

1. `npm run lint` sạch, `npm test` xanh, `npm run build` xanh.
2. Ở **390px**: không cuộn ngang (`documentElement.scrollWidth <= innerWidth`), mọi đích chạm ≥24px.
3. Không có request ra ngoài origin — kiểm bằng tab network, không suy đoán.
4. Chỉ một `<h1>`; Tab đi hết trang, mọi điểm dừng đều thấy viền focus.
5. Precache PWA: **12 mục** nếu chưa có ảnh, **15 mục** nếu ba `showcase-N.png` đã nằm trong `frontend/public/` — `globPatterns` ở `vite.config.ts` có `png` nên plugin tự nạp chúng. **Đếm danh sách thật trong `dist/sw.js`, đừng đọc dòng tổng kết của công cụ**, và kê con số + danh mục file vào PR. Lệch so với hai mốc trên ⇒ dừng và báo.
6. `gh pr checks <PR>` xanh 5/5.

## 5. Báo cáo

Biên lai: số PR + checks xanh + diff. Sandbox chặn Docker/`.git` ⇒ báo đúng cái chưa verify được. T1 chạy lại tay và đặt ảnh thật vào.

## 6. Sau khi merge

**Không có migration** — đừng chạy `alembic upgrade` theo quán tính.
