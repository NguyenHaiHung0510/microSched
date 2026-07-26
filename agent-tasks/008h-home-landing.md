# 008h — trang home công khai tại `/`

> **Executor: Codex (T2).** Nhánh `feat/008h-home-landing` → PR nhỏ vào `develop`.
> Spec tự-chứa. Đọc `CLAUDE.md` + `AGENTS.md` trước; **`docs/ui-brief.md` là luật của task này.**
> ⚠️ **Chưa giao được ngay.** §2.1 cần một bản dựng thị giác mà chủ đã bấm chọn — T1 làm bước đó trước.

## 0. Bối cảnh — vì sao có task này

Khách chưa đăng nhập hiện thấy `LoginScreen` trong `frontend/src/App.tsx:33-61`: một thẻ trống giữa màn hình với đúng một nút. Repo này **công khai có chủ ý**, và mọi liên kết dẫn về `microsched.fly.dev` đều đổ vào cái thẻ đó.

Cái khó thật của trang này: **không ai đăng ký được.** Google OAuth + allowlist đặt bằng biến môi trường. Mọi khuôn mẫu landing page thương mại đều xây quanh một phễu đăng ký không tồn tại ở đây. Nên trang phải thành thật về chuyện đó **ngay từ đầu**, không phải chỉ ở dòng cuối.

## 1. Đã KHOÁ — chép ra code, không mở lại

1. **Trang này thay `LoginScreen`.** App vẫn không có router: `App.tsx` đã phân nhánh theo `loggedOut`. Home là nhánh chưa-đăng-nhập. **Không thêm `react-router` hay bất kỳ thư viện định tuyến nào.**
2. **Nút đăng nhập nằm ở header, góc phải, sticky.** Là thẻ `<a href="/auth/login">` bọc trong `Button asChild` — OAuth cần điều hướng cả trang, không phải `fetch`. Chép đúng cách `App.tsx:52-57` đang làm.
3. **Không hứa cái chưa có.** Hiện chỉ có slice `task` chạy thật — `backend/app/main.py:78` chỉ nạp `tasks_router`; note / calendar / tracker chưa có endpoint nào. Trang nói rõ phần nào đã chạy, phần nào đang xây. **Đây là ràng buộc, không phải gợi ý.**
4. **Không có con số thời gian thức máy trên trang.** `architecture-brief.md` §105-110 ghi resume 0,33–0,48s **nhưng có đuôi trễ, một lần đo ~12s**. Một con số mà khách bấm phát đầu là thấy sai thì tệ hơn không có con số. Con số **chi phí** thì giữ — nó ổn định và kiểm được.
5. **Light-only, hồng ấm.** Không dark mode, không glassmorphism, không hiệu ứng ngoài `ui-brief.md`.
6. **Ảnh và video là placeholder trong task này.** Xem §2.4. Không tự đi chụp màn hình, không tự sinh ảnh.

## 2. Phải làm

### 2.1 ⚠️ Điều kiện tiên quyết — T1 làm trước khi giao

Như `008e`, chủ chọn bằng cách **bấm vào bản dựng chạy được**, không bằng cách đọc mô tả. T1 dựng 2–3 bản HTML của trang này, chủ chọn một, bản đó đặt ở `docs/_local/` (gitignore) và **spec này trỏ vào nó**. Chỗ nào bản dựng và `ui-brief.md` nói khác nhau: **`ui-brief.md` thắng về luật** (màu, tương phản, cỡ chữ), **bản dựng thắng về hình**.

Executor: nếu tới tay bạn mà mục này chưa điền đường dẫn ⇒ **dừng và hỏi**, đừng tự tưởng tượng bố cục.

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

### 2.3 Nội dung — chép nguyên văn, đừng viết lại

Bản này đã qua một vòng soi giọng và đã được chốt. **Không tự sửa chữ.** Thấy sai chính tả hay sai sự thật thì **dừng và báo**, đừng tự chữa.

**Khối 2 — Hero**
> **Việc, ghi chú, lịch, thói quen — gom về một nơi.**
> microSched là ứng dụng cá nhân tôi tự viết và tự dùng mỗi ngày. Phần quản lý việc đã chạy thật; ghi chú, lịch và tracker đang xây, theo đúng thứ tự ghi trong hồ sơ kiến trúc.

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

b. **Ghi được cả khi mất mạng**
> Là PWA cài lên màn hình chính. Ghi vào máy trước, đồng bộ sau — vì lúc cần ghi nhất thường là lúc sóng tệ nhất.

c. **Riêng tư là mã hoá thật, không phải một cái công tắc**
> Việc và ghi chú đánh dấu riêng tư được mã hoá AES-256-GCM ở tầng ứng dụng trước khi xuống cơ sở dữ liệu. Ai đọc được file dump cũng chỉ thấy chuỗi rác.

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

- **Video:** khối tỉ lệ **16:9** dùng `aspect-video`, nền `bg-brand-50`, icon play mờ, chữ ở §2.3. 🔒 **Phải giữ đúng tỉ lệ bằng CSS**, không đặt chiều cao cứng — mai này thả video thật vào mà không có chỗ chừa sẵn thì cả trang nhảy layout.
- **Ba ảnh:** ba khối placeholder tỉ lệ **9:16** (ảnh chụp iPhone). Dùng `<img>` trỏ tới ba file trong `frontend/public/` mà **T1 sẽ đặt vào**; nếu file chưa có, để `alt` mô tả và một nền `bg-muted` — **đừng** để ảnh vỡ.
- 🔒 **Không tự đi chụp màn hình app, không tự sinh ảnh.** Ảnh thật chứa dữ liệu thật; nguồn ảnh là việc của T1 (`devops-brief.md` §1).
- Mọi `<img>` phải có `width`/`height` hoặc bọc trong khung tỉ lệ. Ảnh không có kích thước là nguyên nhân số một của layout nhảy.

### 2.5 Ràng buộc kỹ thuật

- File mới trong `frontend/src/` — đặt tên `HomePage.tsx`, tách khối con nếu file quá dài. `App.tsx` chỉ đổi đúng chỗ render `LoginScreen` thành `HomePage`.
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
- **Không** thêm số liệu hiệu năng nào ngoài con số chi phí đã cho (§1.4).
- **Không** thêm form, ô nhập email, nút "đăng ký", "liên hệ", hay bất cứ thứ gì gợi ý rằng có đường xin quyền truy cập.
- **Không** thêm analytics, tracking pixel, font từ CDN, hay bất kỳ request ra ngoài nào. Trang phải tự chứa.
- **Không** thêm dark mode. **Không** đổi tên required check trong CI.

## 4. Acceptance — kiểm chứng được

1. `npm run lint` sạch, `npm test` xanh, `npm run build` xanh.
2. Ở **390px**: không cuộn ngang (`documentElement.scrollWidth <= innerWidth`), mọi đích chạm ≥24px.
3. Không có request ra ngoài origin — kiểm bằng tab network, không suy đoán.
4. Chỉ một `<h1>`; Tab đi hết trang, mọi điểm dừng đều thấy viền focus.
5. Precache PWA vẫn **12 mục** trừ khi bạn thêm asset — thêm thì kê ra trong PR, đừng để nó lặng lẽ đổi.
6. `gh pr checks <PR>` xanh 5/5.

## 5. Báo cáo

Biên lai: số PR + checks xanh + diff. Sandbox chặn Docker/`.git` ⇒ báo đúng cái chưa verify được. T1 chạy lại tay và đặt ảnh thật vào.

## 6. Sau khi merge

**Không có migration** — đừng chạy `alembic upgrade` theo quán tính.
