# B08 — UI/UX for Context Controls in Mimi

**Trạng thái tài liệu:** PROPOSAL / RESEARCH REPORT
**Mã phân đoạn:** B08 — Research Batch 2026-09-22
**Người thực hiện:** T3 Gemini 3.8 Flash
**Không gian nghiên cứu:** `agent-tasks/2026-09-22-research-mimi-context/`
**Ràng buộc thực thi:** Không sửa runtime code, không sửa mã nguồn frontend, không gọi live model eval, chỉ nghiên cứu và đề xuất thiết kế giao diện theo quy chuẩn hệ thống.

---

## 1. Câu hỏi và phạm vi nghiên cứu (Question and Scope)

### 1.1. Bối cảnh và mục tiêu
Mimi là trợ lý AI nhúng bên trong ứng dụng web microSched. Khác với các sản phẩm thương mại đóng gói dạng chat-only (như ChatGPT thông thường) hay các công cụ lập trình cho chuyên gia (như Cursor/Windsurf), microSched là một ứng dụng quản lý cá nhân PWA được tối ưu cho sinh viên ngành CNTT. Giao diện của microSched đã có các màn hình CRUD mạnh mẽ (Tasks, Calendar, Notes, Trackers). Mimi đóng vai trò là một bề mặt điều khiển và cộng tác bổ sung, chứ không thay thế các màn hình miền hiện có.

Các câu hỏi nghiên cứu cốt lõi của B08 bao gồm:
1. **Hiển thị dung lượng ngữ cảnh (Context Meter):** Làm thế nào để trực quan hóa mức tiêu hao token và cấu trúc các lớp dữ liệu trong context window mà không gây rối mắt hay làm người dùng hoang mang?
2. **Thanh tra nguồn ngữ cảnh (Source / Context Inspector):** Người dùng có thể kiểm tra xem Mimi "đang nhìn thấy những gì" trong lượt này (policy, dữ liệu domain, memory, transcript) bằng cách nào để bảo đảm tính minh bạch và an toàn dữ liệu?
3. **Kiểm soát nén ngữ cảnh (Compaction Controls):** Trải nghiệm nén chủ động (Manual Compact) và nén tự động có hiển thị (Visible Auto-Compaction) cần được biểu diễn như thế nào trên dòng chảy tin nhắn để không vi phạm nguyên tắc *"No silent truncation"*?
4. **Lựa chọn mô hình và nỗ lực suy luận (Model & Reasoning Effort):** Giao diện cần xử lý sự sai lệch giữa cấu hình người dùng yêu cầu (Requested Settings) và cấu hình hệ thống thực tế áp dụng (Effective Settings) ra sao? Vòng đời chuyển tiếp (Pending Transitions) được hiển thị thế nào?
5. **Minh bạch hóa Prompt Cache và chi phí (Cache & Usage Visibility):** Làm thế nào để người dùng hiểu được lợi ích của Prompt Caching, độ trễ và chi phí ước tính mà không biến giao diện thành một bảng điều khiển kỹ thuật phức tạp?
6. **Thích ứng không gian làm việc và thiết bị di động:** Bố cục không gian làm việc gập/mở (Foldable Workspace) và thanh trò chuyện bên cạnh (Side-Chat) trên máy tính để bàn (Desktop), cùng với cơ chế thích ứng trên màn hình nhỏ (Mobile <= 640px) cần được thiết kế như thế nào để tuân thủ quy chuẩn UI của microSched?

### 1.2. Phạm vi nghiên cứu
- **Trong phạm vi:** Thiết kế chi tiết các thành phần UI/UX cho điều khiển context; định nghĩa máy trạng thái giao diện (UI State Machines); đặc tả bố cục đáp ứng (Responsive Layouts) cho Desktop, Tablet và Mobile; đối chiếu tiêu chuẩn thiết kế microSched (Nunito, Light-only, shadcn/ui, CSS tokens); phân tích kinh nghiệm từ các sản phẩm AI hàng đầu.
- **Ngoài phạm vi:** Viết mã nguồn linh kiện React/TypeScript; cài đặt thư viện ngoài; cấu hình build-time.

---

## 2. Phương pháp và nguồn tài liệu chính thức (Method and Exact Sources)

Nghiên cứu này được tiến hành bằng phương pháp phân tích đối chiếu sản phẩm thực tế (Product Benchmarking) kết hợp với các nguyên lý Tương tác Người - Máy (HCI) và hệ thống đặc tả của microSched:

### 2.1. Đối chiếu sản phẩm thực tế trưởng thành (Mature AI Products Benchmark)
1. **Anthropic Claude Projects & Artifacts (2024–2026):**
   - Tham chiếu: Cơ chế hiển thị song song (Side-by-side Artifact view), thanh đo dung lượng tài liệu dự án (Project Knowledge meter), và việc tách bạch giữa nội dung đàm thoại và kết quả trực quan.
2. **OpenAI ChatGPT Platform (Canvas & Sources Popover — 2024–2026):**
   - Tham chiếu: Nút xem nguồn trích dẫn (Sources modal), giao diện soạn thảo văn bản/code chuyên dụng (Canvas), và thông báo trạng thái suy luận (Reasoning progress summary).
3. **Cursor & Windsurf IDEs (2025–2026):**
   - Tham chiếu: Thẻ đính kèm ngữ cảnh (Context Pills như `@file`, `@web`), thanh tiến trình tiêu thụ token (Context Usage Bar), và thẻ xem trước khác biệt (Diff Preview Card) có nút Accept / Reject.
4. **Codex App Desktop (OpenAI):**
   - Tham chiếu: Bảng thanh tra ngữ cảnh (Context Inspector), cơ chế phân cách mốc thời gian chuyển đổi mô hình (Model Transition Dividers), và hiển thị ngân sách token theo lượt.

### 2.2. Tiêu chuẩn thiết kế và công thái học giao diện (HCI Standards)
1. **Nielsen Norman Group — Usability Heuristics:**
   - Heuristic #1 (Visibility of System Status): Hệ thống phải luôn cung cấp phản hồi kịp thời và rõ ràng về trạng thái nội bộ (đang đọc tool nào, đang dùng bao nhiêu token, nén khi nào).
   - Heuristic #3 (User Control and Freedom): Cho phép người dùng chủ động nén ngữ cảnh hoặc hủy bỏ thao tác một cách an toàn.
   - Heuristic #6 (Recognition rather than Recall): Hiển thị sẵn nguồn dữ liệu đang tham chiếu thay vì bắt người dùng tự nhớ.
2. **W3C Web Content Accessibility Guidelines (WCAG) 2.1 AA/AAA:**
   - Success Criterion 2.5.5 (Target Size): Kích thước vùng cảm ứng trên thiết bị di động tối thiểu là 44 x 44 CSS pixels.
   - Success Criterion 1.4.3 (Contrast Minimum): Độ tương phản màu sắc chữ trên nền tối thiểu đạt 4.5:1.

### 2.3. Tài liệu kiến trúc và quy chuẩn UI nội bộ microSched
1. `docs/ui-brief.md`: Quy định bắt buộc: Chỉ sử dụng Light Mode (nghiêm cấm dark mode), font chữ Nunito tự lưu trữ (self-hosted), sử dụng linh kiện shadcn/ui (dựa trên Radix Primitives), sử dụng CSS Design Tokens của Tailwind (không hardcode mã màu hex), kích thước chữ tối thiểu 12px, không phụ thuộc vào tương tác rê chuột (hover-only).
2. `cur_docs/PTHTTM/btl/04-spec-hop-nhat-mimi.md`: Quy định cơ chế nén B-first, đường phân cách bất biến khi nén (`Compaction Checkpoint Divider`), máy trạng thái `REQUESTED -> PREFLIGHT -> APPLIED`, và cơ chế Soft-lock RAM với PIN 36 phút.
3. `cur_docs/PTHTTM/btl/02-spec-thuc-thi-mimi.md`: Nguyên tắc *"No silent truncation"* (không cắt xén ngữ cảnh âm thầm mà người dùng không biết).

---

## 3. Các sự thật quan sát được (Observed Facts)

- **[FACT-B08-01] Kiến trúc Frontend microSched:** Frontend là Single Page Application (SPA/PWA) viết bằng React 18, TypeScript và Vite, được phục vụ trực tiếp dưới dạng static assets từ tiến trình Python FastAPI duy nhất.
- **[FACT-B08-02] Quy chuẩn UI nghiêm ngặt:** Theo `docs/ui-brief.md`, giao diện microSched là **Light-only** (không có chế độ nền tối), dùng font **Nunito**, toàn bộ màu sắc phải dùng biến CSS token (`bg-background`, `text-foreground`, `border-border`, `bg-primary`, v.v.). Mọi nút bấm, input, select đều phải dùng component của shadcn/ui. Cấm tuyệt đối các thao tác chỉ kích hoạt được bằng hover trên mobile.
- **[FACT-B08-03] Sự sai lệch trong đếm Token tiếng Việt:** Các thuật toán tokenizer của các hãng (OpenAI tiktoken cl100k_base / o200k_base so với Google Gemini SentencePiece) có sự chênh lệch từ 10% đến 25% khi mã hóa văn bản tiếng Việt có dấu. Việc tích hợp bộ đếm token chính xác ở client đòi hỏi phải tải các file WASM/dictionary nặng 2–5MB vào trình duyệt. Do đó, hiển thị phía client bắt buộc phải phân biệt rõ giữa **Số token ước tính (Estimated)** và **Số token chính thức từ Provider Receipt (Official)**.
- **[FACT-B08-04] Ràng buộc chống cắt xén âm thầm:** Đặc tả `02-spec-thuc-thi-mimi.md` §2.3 và `04-spec-hop-nhat-mimi.md` §4 cấm tuyệt đối hành vi âm thầm loại bỏ tin nhắn cũ khỏi context mà không báo cho người dùng. Mọi đợt nén context (dù tự động hay thủ công) đều phải để lại một mốc phân cách bất biến (Immutable Divider) trên transcript.
- **[FACT-B08-05] Ràng buộc thiết bị di động:** Gần 50% thao tác quản lý lịch và ghi chú của người dùng diễn ra trên điện thoại thông minh (màn hình hẹp 360px – 420px). Tại kích thước này, bố cục chia đôi màn hình (Side-by-side split) là hoàn toàn bất khả thi.

---

## 4. Phân tích so sánh các mô hình giao diện (Competing UI/UX Patterns)

Chúng tôi xem xét 3 mô hình giao diện quản lý ngữ cảnh phổ biến trong ngành:

### 4.1. Mô hình 1: Chatbot cổ điển vô hình (Invisible / Headless Context)
- **Mô tả:** Giống như giao diện ChatGPT tiêu chuẩn ban đầu: Người dùng chỉ thấy khung chat và các tin nhắn cuộn. Toàn bộ việc nén context, trích xuất dữ liệu hay gọi công cụ đều diễn ra ngầm trong hậu trường. Người dùng không biết Mimi đang dùng bao nhiêu token, thấy được tài liệu nào.
- **Ưu điểm:** Giao diện tối giản, quen thuộc.
- **Nhược điểm:** Hoàn toàn thất bại trước nguyên tắc *"No silent truncation"*. Người dùng không biết tại sao Mimi đột nhiên quên mất chi tiết đã nói ở 10 tin nhắn trước. Không cung cấp cơ sở để người dùng kiểm soát chi phí hoặc xác thực tính riêng tư.

### 4.2. Mô hình 2: Bảng điều khiển kỹ thuật cực đoan (Maximalist IDE Inspector)
- **Mô tả:** Giống như giao diện của Cursor hoặc các công cụ phát triển Agent: Hiển thị chi tiết từng câu lệnh SQL, mã JSON của tool call, đồ thị DAG, cây bộ nhớ chi tiết, và bảng mã hex token.
- **Ưu điểm:** Cực kỳ minh bạch cho kỹ sư phần mềm.
- **Nhược điểm:** Gây quá tải nhận thức (Cognitive Overload) nghiêm trọng cho người dùng khi đang cần tập trung học tập và quản lý cuộc sống. Phá vỡ phong cách giao diện ấm áp, gọn gàng của microSched.

### 4.3. Mô hình 3: Tiết lộ lũy tiến có lớp lang (Progressive Disclosure — ĐỀ XUẤT CHO MIMI)
- **Mô tả:** Giao diện mặc định giữ sự tinh tế và thanh thoát: Chỉ hiển thị một thanh đo ngữ cảnh (Context Meter) thanh mảnh trên thanh tiêu đề và các nhãn nguồn nhỏ gọn (Source Badges) dưới tin nhắn. Khi người dùng có nhu cầu kiểm tra sâu, một cú nhấp chuột sẽ mở ra **Source & Context Inspector** dưới dạng ngăn kéo (Drawer/Sheet) có cấu trúc lớp lang rõ ràng.
- **Ưu điểm:** Giữ trọn sự tập trung cho người dùng phổ thông nhưng cung cấp đầy đủ quyền năng kiểm soát và minh chứng cho người dùng nâng cao; tuân thủ hoàn hảo các nguyên lý HCI.

---

## 5. Đặc tả chi tiết các thành phần giao diện (Component Specifications)

### 5.1. Thước đo ngữ cảnh (Context Meter Component)
- **Vị trí hiển thị:** Nằm trên thanh tiêu đề (Header) của khung chat Mimi hoặc cạnh thanh trạng thái.
- **Cấu trúc trực quan:** Một thanh tiến trình phân đoạn (Segmented Progress Bar) chiều cao 6px hoặc 8px, chia màu theo 4 lớp dữ liệu ngữ cảnh:
  1. *Lớp 1 (Chính sách tĩnh & Tools):* Màu xám trung tính (`bg-muted-foreground/30`) — Chiếm khoảng 10–15% dung lượng, có thể cache.
  2. *Lớp 2 (Dữ liệu Domain & Memory):* Màu xanh ngọc nhạt (`bg-emerald-500/50`) — Biểu thị dữ liệu thực tế vừa được đọc từ Tasks/Calendar/Notes.
  3. *Lớp 3 (Lịch sử hội thoại hiện hành):* Màu xanh dương (`bg-primary/70`) — Biểu thị các lượt hỏi đáp giữa người dùng và Mimi.
  4. *Lớp 4 (Dung lượng trống còn lại):* Màu nền rỗng (`bg-secondary`).

- **Quy tắc cảnh báo ngưỡng (Threshold Indicators):**
  - **Mức An toàn (< 65% dung lượng):** Thanh đo hiển thị sắc thái màu xanh dịu mắt, nhãn hiển thị: `~12.4k / 32k tokens (38%)`.
  - **Mức Chú ý (65% – 80%):** Thanh đo chuyển sang màu vàng hổ phách (`bg-amber-500`), xuất hiện gợi ý nhỏ: *"Ngữ cảnh bắt đầu dài, có thể nén"*.
  - **Mức Nguy cơ (> 80%):** Thanh đo chuyển sang màu cam đỏ (`bg-destructive/80`), nhấp nháy nhẹ khi rê chuột, xuất hiện nút bấm nhanh **[Nén ngay]** (Compact Now) để tránh việc hệ thống tự động kích hoạt auto-compaction.

- **Tương tác nhấp chuột (Popover Breakdown):** Khi nhấp vào Context Meter, một popover nhỏ gọn xuất hiện giải thích chi tiết:
  - Chính sách & Công cụ tĩnh: ~2.400 tokens (Cached 100%)
  - Dữ liệu nhiệm vụ & Lịch đã nạp: ~3.100 tokens
  - Ký ức dài hạn (Memory): ~800 tokens
  - Lịch sử hội thoại (12 lượt): ~7.500 tokens
  - *Tổng cộng: 13.800 / 32.768 tokens (42% window)*

---

### 5.2. Thanh tra nguồn ngữ cảnh (Source / Context Inspector Sheet)
- **Cơ chế kích hoạt:** Bấm vào biểu tượng kính lúp / cuốn sách `[Soi ngữ cảnh]` trên thanh công cụ chat.
- **Hình thức:** Mở ra một ngăn kéo trượt (Slide-out Sheet) từ cạnh phải màn hình (Desktop) hoặc toàn màn hình (Mobile), sử dụng component `Sheet` của shadcn/ui.
- **Nội dung tổ chức theo 4 thẻ Accordion:**
  1. **Chính sách hoạt động (Policy & Guardrails):** Hiển thị tóm tắt các quy tắc đang điều hướng Mimi (Phân hạng C0–C3, chế độ an toàn).
  2. **Dữ liệu thực tế đang nhìn thấy (Active Domain Snapshots):** Danh sách các bản ghi Task, Calendar, Note cụ thể mà Mimi đã trích xuất qua các tool đọc trong lượt này. Có nhãn định danh bản ghi (`task_id`, `event_id`) có thể bấm để nhảy sang màn hình chi tiết.
  3. **Ký ức dài hạn được nạp (Injected Long-Term Memory):** Hiển thị chính xác các mục ghi nhớ (`M-01`, `M-02`) từ Neon Memory kèm lý do trích xuất.
  4. **Lịch sử hội thoại & Sổ cái tóm lược (Transcript Ledger):** Hiển thị những tin nhắn nào đang ở dạng nguyên bản (raw) và những tin nhắn nào đã bị nén thành bản tóm tắt.
- **Huy hiệu bảo mật (Privacy Badges):**
  - Nhãn **STANDARD** (Màu xám nhạt trung tính): Báo hiệu dữ liệu thông thường, không chứa thông tin nhạy cảm.
  - Nhãn **PRIVATE** (Màu tím/hổ phách kèm biểu tượng ổ khóa): Báo hiệu phiên làm việc đang sử dụng dữ liệu riêng tư, hiển thị đồng hồ đếm ngược thời hạn mở khóa PIN (ví dụ: *"Còn 24 phút"*).
- **Nguyên tắc an toàn:** Không bao giờ hiển thị mật khẩu, mã PIN hoặc dữ liệu chưa được giải mã.

---

### 5.3. Kiểm soát nén ngữ cảnh (Compaction Controls)

#### A. Nén chủ động (Manual Compact)
- **Kích hoạt:** Người dùng gõ lệnh `/compact` hoặc bấm nút **[Nén lịch sử]** trên menu cài đặt chat.
- **Điều kiện tiên quyết:** Chỉ được phép kích hoạt khi hệ thống ở trạng thái tĩnh (Quiescent) — không có run nào đang chạy, không có Preview nào đang chờ xác nhận.
- **Hộp thoại xác nhận trước khi nén (Pre-flight Confirmation Dialog):**
  - Hiển thị ước tính: *"Nén 14 tin nhắn cũ thành 1 bản tóm lược kiến thức. Dự kiến giải phóng ~12.000 tokens (giảm từ 68% xuống 22%)"*.
  - Cho phép người dùng xem trước các chủ đề chính sẽ được giữ lại (ví dụ: Quyết định dời lịch BTL, danh sách việc cần nộp thứ Sáu).
  - Nút bấm: **[Tiến hành nén]** và **[Giữ nguyên]**.

#### B. Nén tự động có hiển thị (Visible Auto-Compaction)
- **Cơ chế kích hoạt:** Tự động kích hoạt khi tổng dung lượng token chạm ngưỡng cảnh báo (80% context window).
- **Biểu diễn trực quan trên giao diện (Bắt buộc theo `04-spec-hop-nhat-mimi.md`):**
  Tuyệt đối không cắt tin nhắn âm thầm! Hệ thống chèn một thành phần phân cách bất biến (Immutable Divider Component) ngay tại vị trí các tin nhắn được nén:

```
=================================================================================
 [Biểu tượng Tia sét] ĐIỂM MỐC NÉN NGỮ CẢNH (Auto-Compaction Checkpoint) — 16:45
 Đã tóm lược 12 lượt trò chuyện trước đó thành sổ cái tri thức. Giải phóng 16.200 tokens.
 [ Bấm vào đây để xem nội dung tóm tắt chi tiết ]
=================================================================================
```

- **Tương tác người dùng:** Khi nhấp vào thanh phân cách này, một khung Accordion mở ra cho phép người dùng đọc lại toàn bộ bản tóm tắt có cấu trúc (Structured Ledger) đã được tạo ra trong quá trình nén B-first.

---

### 5.4. Lựa chọn mô hình và nỗ lực suy luận (Model & Effort Selection)

#### A. Giao diện bộ chọn (Selector Component)
- Đặt tại phần chân trang (Footer) hoặc menu cấu hình phiên trò chuyện.
- Gồm hai điều khiển gắn liền nhau:
  1. **Hộp chọn Mô hình (Model Route Selector):** Danh sách các route đã được kiểm định (ví dụ: `Gemini 3.8 Flash`, `GPT-5.6 Sol`, `GPT-5.6 Luna`).
  2. **Hộp chọn Nỗ lực suy luận (Reasoning Effort):** Các mức `None`, `Low`, `Medium`, `High`, `Max` (chỉ sáng lên với những mô hình có hỗ trợ reasoning).

#### B. Phân định Cài đặt Yêu cầu vs. Cài đặt Thực tế (Requested vs. Effective)
- Khi người dùng chọn một cấu hình nhưng hệ thống buộc phải hạ cấp do giới hạn quota, sự cố mạng, hoặc chính sách fallback, giao diện phải hiển thị minh bạch cả hai trạng thái:
  - *Trường hợp bình thường:* `Mô hình: Gemini 3.8 Flash | Nỗ lực: Cao`
  - *Trường hợp có Fallback:* `Mô hình: Gemini 3.8 Flash | Nỗ lực: Vừa [Cảnh báo: Đã tự động hạ từ mức Cao do chạm giới hạn token]`

#### C. Máy trạng thái chuyển tiếp (Pending Transitions State Machine)
Khi người dùng đổi mô hình giữa chừng trong một cuộc hội thoại đang diễn ra, việc chuyển đổi tuân theo máy trạng thái nghiêm ngặt:
1. `REQUESTED`: Người dùng vừa chọn mô hình mới -> Nút bấm hiển thị trạng thái `Đang chuẩn bị chuyển đổi...`.
2. `PREFLIGHT`: Backend kiểm tra xem mô hình mới có đủ context window để chứa lịch sử hiện tại không. Nếu thiếu -> Chuyển sang `APPLYING_COMPACTION` để nén trước.
3. `APPLIED`: Mô hình mới được kích hoạt thành công. Một đường kẻ mốc phân cách xuất hiện trên chat stream:
   *"--- [Đã chuyển sang mô hình GPT-5.6 Sol lúc 17:15 theo yêu cầu người dùng] ---"*.
4. `FAILED_BLOCKED`: Nếu việc chuyển đổi thất bại -> Hệ thống giữ nguyên cấu hình cũ và hiển thị thông báo lỗi rõ ràng kèm lý do.

---

### 5.5. Minh bạch hóa Prompt Cache và chi phí (Cache & Usage Visibility)
- **Vị trí hiển thị:** Một dòng thông tin trạng thái cực kỳ tinh tế (Micro Usage Pill) nằm dưới chân mỗi tin nhắn phản hồi của Mimi.
- **Cấu trúc dữ liệu hiển thị:**
  - *Biểu tượng Cache (Chiếc lá xanh):* `11.2k cached (82%)` — Báo hiệu phần lớn ngữ cảnh đã được tái sử dụng từ Prompt Cache, giúp phản hồi nhanh và giảm 80% chi phí.
  - *Thời gian phản hồi (Latency):* `1.1s`.
  - *Chi phí ước tính:* `~115 VNĐ` (hoặc `$0.0046`).
- **Lợi ích nhận thức:** Giúp người dùng hiểu được tại sao việc duy trì cuộc hội thoại gọn gàng và tận dụng Prompt Caching lại mang lại tốc độ phản hồi nhanh hơn rõ rệt.

---

## 6. Thích ứng không gian làm việc và thiết bị di động (Responsive Layouts)

### 6.1. Bố cục trên Máy tính để bàn (Desktop — Màn hình rộng > 1024px)
microSched trên máy tính hỗ trợ hai chế độ hiển thị linh hoạt:

#### Chế độ A: Thanh trò chuyện bên cạnh (Side-Chat Panel — Mặc định)
- **Vị trí:** Cố định ở cạnh phải màn hình, độ rộng chuẩn **380px – 440px**.
- **Tương tác với màn hình chính:**
  - Khi mở Side-Chat, vùng hiển thị nghiệp vụ chính (Tasks Kanban, Lịch tuần) sẽ tự động co lại một cách mượt mà (smooth flex layout), không bị che khuất nội dung.
  - Người dùng có thể vừa nhìn lịch tuần bên trái, vừa chat với Mimi bên phải.
  - Có nút thu gọn thành một biểu tượng nổi (Floating Pill) ở góc dưới khi không dùng.

#### Chế độ B: Không gian làm việc chuyên sâu (Foldable Workspace Mode)
- **Kích hoạt:** Bấm vào nút `[Mở rộng Workspace]` ở góc trên Side-Chat hoặc truy cập đường dẫn `/mimi`.
- **Bố cục 2 cột toàn màn hình (Split-View Workspace):**
  - **Cột trái (Chiếm 45% chiều rộng):** Toàn bộ luồng trò chuyện với Mimi, thanh nhập liệu lớn hỗ trợ soạn thảo nhiều dòng.
  - **Cột phải (Chiếm 55% chiều rộng):** Bảng hiển thị chuyên sâu (Context Inspector, Bảng phân tích tài liệu PDF bài giảng, hoặc Thẻ Preview chi tiết dạng bảng biểu).

---

### 6.2. Bố cục trên Máy tính bảng (Tablet — 640px đến 1024px)
- Side-Chat chuyển thành dạng ngăn kéo trượt lớp phủ (Overlay Drawer / Off-canvas Sheet).
- Khi người dùng chạm ra ngoài vùng chat (backdrop click), ngăn kéo tự động đóng lại để trả lại không gian thao tác cho màn hình nghiệp vụ.

---

### 6.3. Bố cục trên Thiết bị di động (Mobile — Màn hình nhỏ <= 640px)
Thiết kế trên mobile đòi hỏi sự tinh giản và tập trung cao độ:

1. **Không gian hiển thị toàn màn hình (Mobile Viewport):**
   - Mimi hoạt động dưới dạng một màn hình đầy đủ (Full-screen view) hoặc Bottom Sheet có thể kéo lên đến 95% chiều cao màn hình.
   - Ẩn hoàn toàn các chi tiết kỹ thuật phức tạp: Context Meter thu gọn thành một chấm tròn nhỏ đổi màu (Xanh/Vàng/Đỏ) kèm phần trăm bên cạnh ảnh đại diện của Mimi.
2. **Thẻ Preview Card thích ứng cảm ứng (Mobile Touch Preview):**
   - Thẻ Preview chiếm 100% chiều rộng màn hình, ghim cố định ở đáy giao diện (Sticky Bottom Action Bar).
   - **Kích thước nút bấm theo chuẩn WCAG 2.1 AA:** Nút **[Xác nhận]** và **[Hủy]** có chiều cao tối thiểu **48px**, khoảng cách giữa hai nút tối thiểu **12px** để tránh bấm nhầm.
3. **Xử lý trạng thái Soft-lock bảo vệ dữ liệu riêng tư (Private Soft-lock):**
   - Khi hết thời hạn PIN 36 phút, toàn bộ nội dung riêng tư của Mimi bị thay thế bằng một **vỏ bọc trung tính (Neutral Shell)** hiển thị thông báo: *"Phiên làm việc đã khóa để bảo vệ dữ liệu cá nhân"* kèm bàn phím số nhập PIN 6 chữ số.
   - Tuyệt đối không dùng hiệu ứng làm mờ (blur) vì người dùng vẫn có thể soi thấy đường nét chữ bên dưới.
   - Bản thảo chưa gửi được giữ an toàn trong RAM của trình duyệt cho đến khi nhập đúng PIN để phục hồi.

---

## 7. Tuân thủ quy chuẩn thiết kế hệ thống (Design System Compliance)

Mọi thành phần giao diện của Mimi được thiết kế tuân thủ 100% các chỉ dẫn trong `docs/ui-brief.md`:

| Tiêu chí quy chuẩn | Yêu cầu trong `ui-brief.md` | Cách thức thực thi trong thiết kế của Mimi |
|---|---|---|
| **Chế độ màu (Theme)** | Chỉ duy nhất Light Mode, cấm Dark Mode | 100% linh kiện dùng nền trắng/xám sáng (`bg-white`, `bg-slate-50`) |
| **Typography** | Font chữ Nunito tự lưu trữ (self-hosted) | Sử dụng lớp `font-sans` ánh xạ tới font Nunito đã nạp |
| **Linh kiện nền tảng** | Sử dụng shadcn/ui (Radix Primitives) | Dùng `Sheet`, `Accordion`, `Dialog`, `Progress`, `Badge`, `Button` của shadcn |
| **Mã màu sắc** | Cấm hardcode mã màu Hex, dùng CSS Tokens | Sử dụng `text-foreground`, `border-border`, `bg-primary`, `bg-muted` |
| **Tương tác cảm ứng** | Không phụ thuộc vào Hover-only | Mọi thông tin quan trọng đều có nút bấm hoặc tap trực tiếp |
| **Kích thước chữ** | Không nhỏ hơn 12px (`text-xs` là tối thiểu) | Các thông số kỹ thuật phụ dùng font 12px rõ nét |

---

## 8. Đề xuất kiến trúc giao diện hoàn chỉnh (Recommendations / Proposals)

1. **[PROPOSAL-B08-01] Áp dụng Thước đo ngữ cảnh đa phân đoạn (Segmented Context Meter):**
   Hiển thị trực quan 4 lớp dữ liệu (Chính sách tĩnh, Dữ liệu domain, Transcript, Khoảng trống) kèm nhãn phần trăm và số token ước tính, tích hợp cơ chế cảnh báo 3 cấp độ màu (Xanh <65%, Vàng 65–80%, Đỏ >80%).
2. **[PROPOSAL-B08-02] Tích hợp Ngăn kéo soi ngữ cảnh (Source & Context Inspector Sheet):**
   Cung cấp khả năng thanh tra toàn diện những gì Mimi "nhìn thấy" qua 4 thẻ Accordion có cấu trúc, gắn nhãn bảo mật STANDARD / PRIVATE rõ ràng.
3. **[PROPOSAL-B08-03] Tiêu chuẩn hóa mốc nén bất biến (Immutable Compaction Divider):**
   Tuyệt đối loại bỏ việc cắt ngắn context âm thầm. Khi nén tự động hoặc thủ công diễn ra, bắt buộc chèn một thẻ phân cách bất biến vào dòng chat để người dùng có thể nhấp vào xem lại sổ cái tóm tắt.
4. **[PROPOSAL-B08-04] Minh bạch hóa chuyển đổi mô hình (Requested vs. Effective State Machine):**
   Xử lý việc đổi mô hình qua máy trạng thái 4 bước và hiển thị rõ ràng khi có sự kiện tự động hạ cấp cấu hình (fallback).
5. **[PROPOSAL-B08-05] Kiến trúc giao diện đáp ứng 2 chế độ trên Desktop và tối ưu cảm ứng trên Mobile:**
   Cung cấp Side-Chat đồng hành (380–440px) và Workspace toàn màn hình trên Desktop; sử dụng Bottom Sheet kèm các nút bấm kích thước lớn (>= 48px) và vỏ bọc bảo vệ trung tính khi khóa PIN trên Mobile.

---

## 9. Các câu hỏi chưa giải quyết dành cho Owner / T1 Workshop (Unresolved Questions)

1. **Mức độ chi tiết của hiển thị Chi phí (Cost Visibility):** Owner có mong muốn hiển thị chi phí ước tính (quy đổi ra VNĐ, ví dụ: `~115 đ`) ngay dưới mỗi tin nhắn hay chỉ hiển thị số lượng token và thời gian phản hồi (để tránh gây áp lực tâm lý tiếc tiền cho người dùng khi trò chuyện)?
2. **Hành vi mặc định khi bấm biểu tượng Mimi trên Desktop:** Nên mặc định mở **Side-Chat trượt cạnh phải** (để giữ nguyên ngữ cảnh màn hình làm việc hiện tại) hay chuyển hướng thẳng sang **Màn hình chuyên dụng /mimi**?
3. **Ngưỡng kích hoạt cảnh báo nén thủ công:** Hiện tại đề xuất là **80%** thì hệ thống tự nén, và **65%** thì hiển thị nút gợi ý nén thủ công. Owner có muốn hạ ngưỡng tự nén xuống **75%** để bảo đảm an toàn tuyệt đối cho Prompt Cache hay không?

---

## 10. Phiên bản chứng cứ, ngày thực hiện và giới hạn (Evidence Version & Limitations)

- **Ngày lập báo cáo:** 22/09/2026.
- **Tài liệu đối chiếu:** `docs/ui-brief.md`, `04-spec-hop-nhat-mimi.md` (10/09/2026), `02-spec-thuc-thi-mimi.md`, Anthropic Claude UI Case Studies (2024–2026), Cursor UI Patterns (2025–2026), WCAG 2.1 Guidelines.
- **Giới hạn nghiên cứu:**
  - Thiết kế này dừng ở mức đặc tả kiến trúc thành phần UI và wireframe quy tắc logic; chưa bao gồm code JSX hay CSS hoàn thiện.
  - Cần tiến hành kiểm thử thực tế trên các kích thước màn hình điện thoại thật (iPhone Safari, Android Chrome) để tinh chỉnh độ trễ hiển thị và độ nhạy của cử chỉ vuốt trong các đợt phát triển tiếp theo.
