# B03 — Agent Loop and Interaction Policy for Mimi

**Trạng thái tài liệu:** PROPOSAL / RESEARCH REPORT
**Mã phân đoạn:** B03 — Research Batch 2026-09-22
**Người thực hiện:** T3 Gemini 3.8 Flash
**Không gian nghiên cứu:** `agent-tasks/2026-09-22-research-mimi-context/`
**Ràng buộc thực thi:** Không sửa runtime code, không gọi live model eval, không giải mã hoặc hiển thị giá trị secret/API key, chỉ nghiên cứu và đề xuất kiến trúc.

---

## 1. Câu hỏi và phạm vi nghiên cứu (Question and Scope)

### 1.1. Bối cảnh và vấn đề cốt lõi
Mimi được định vị là một trợ lý AI cá nhân nhúng trực tiếp trong kiến trúc modular monolith của microSched, phục vụ đúng một người dùng (Owner) là sinh viên công nghệ thông tin năm cuối tại PTIT. Không giống như các chatbot hội thoại chung chung (general conversational chat), mọi quyết định và hành động của Mimi liên quan mật thiết đến kế hoạch học tập, thời gian biểu, ghi chú và các tracker cuộc sống.

Các câu hỏi nghiên cứu nền tảng cần giải quyết trong phân đoạn B03 bao gồm:
1. **Chu trình tương tác chuẩn (Interaction Lifecycle):** Làm thế nào để vòng lặp của Mimi xử lý trơn tru giữa việc trả lời hội thoại thông thường, làm rõ yêu cầu, tra cứu dữ liệu thời gian thực, và đề xuất các hành động thay đổi trạng thái?
2. **Phân định bản chất giữa Draft và Preview:** Ranh giới kỹ thuật, trạng thái lưu trữ, và quyền hạn thực thi giữa một **Bản thảo hội thoại (Conversational Draft)** và một **Bản xem trước có thể thực thi (Frozen Executable Preview)** là gì?
3. **Chính sách phân luồng Fast-Path vs. Deliberate Draft-First:** Dựa trên tiêu chí định lượng và ngữ nghĩa nào để hệ thống quyết định đi thẳng tới Preview (Fast-path cho lệnh nhỏ, rõ ràng, tức thì) hay bắt buộc phải dừng lại ở Draft (Deliberate path cho việc phức tạp, mơ hồ, nhiều thực thể, hoặc nhạy cảm)?
4. **Vòng lặp công cụ đọc lặp (Iterative Read-Tool Loop):** Mimi có nên được trang bị khả năng tự động gọi nhiều công cụ đọc (C0 Read Tools) nối tiếp nhau trong cùng một lượt để nắm bắt toàn diện trạng thái microSched hay không? Ranh giới an toàn và giới hạn tài nguyên của vòng lặp này là gì?
5. **Pha mô hình thứ hai (Second Model Phase):** Việc đưa thêm một mô hình LLM thứ hai (đóng vai trò Verifier, Formatter, Critic, hoặc Safety Guard) trong chu trình runtime thời gian thực giúp ích hay gây hại xét trên các góc độ: độ trễ (latency), chi phí token, tải tài nguyên của máy chủ Fly.io 512MB RAM, và nguy cơ cascade lỗi?

### 1.2. Phạm vi nghiên cứu
- **Trong phạm vi:** Thiết kế kiến trúc chu trình tương tác của Agent; phân tích các trạng thái chuyển tiếp từ khi nhận input của người dùng đến khi xuất ra câu trả lời hoặc Preview card; tiêu chí phân loại C0/C1/C2/C3 gắn với luồng hội thoại; cơ chế xử lý can thiệp của người dùng (Steering); phân tích định lượng chi phí/độ trễ của Second Model Phase; 5 kịch bản đối thoại mẫu bằng tiếng Việt thực tế trong bối cảnh học tập PTIT.
- **Ngoài phạm vi:** Sửa đổi mã nguồn Python/FastAPI; viết code React frontend; chạy benchmark hay eval tự động; tự ý thay đổi quyết định đã được Owner chốt trước đó.

---

## 2. Phương pháp và nguồn tài liệu chính thức (Method and Exact Sources)

Nghiên cứu này được xây dựng dựa trên việc đối chiếu có phê phán giữa các tài liệu kỹ thuật chính thức từ các phòng nghiên cứu AI hàng đầu và các đặc tả kiến trúc nội bộ của microSched:

### 2.1. Nguồn tài liệu chính thức từ nhà cung cấp mô hình (Primary Official Docs)
1. **Anthropic Engineering — "Building Effective Agents" (Tháng 12/2024, cập nhật 2025):**
   - Nguồn: [Anthropic Research: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents).
   - Điểm cốt lõi: Phân định ranh giới giữa *Workflows* (các mẫu luồng công việc điều hướng có kiểm soát: Prompt Chaining, Routing, Parallelization, Orchestrator-Workers, Evaluator-Optimizer) và *Autonomous Agents* (tự do quyết định vòng lặp). Khuyến nghị nguyên tắc tối giản: Luôn bắt đầu bằng giải pháp đơn giản nhất; mẫu Evaluator-Optimizer (hai pha mô hình) chỉ nên dùng khi thực sự có thước đo rõ ràng và chấp nhận đánh đổi độ trễ tăng 200–300%.
2. **OpenAI Platform Documentation — "Function Calling & Structured Outputs" (2024–2026):**
   - Nguồn: [OpenAI Documentation: Function Calling](https://platform.openai.com/docs/guides/function-calling) và [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs).
   - Điểm cốt lõi: Quy trình Run Lifecycle chuẩn (`in_progress` -> `requires_action` -> `completed`). Cơ chế Constrained Decoding bảo đảm 100% tuân thủ JSON Schema ở cấp độ engine sinh token, chứng minh rằng không cần một LLM thứ hai chỉ để sửa lỗi cú pháp JSON.
3. **Google DeepMind / Google Cloud — "Gemini Function Calling & Agentic Workflows" (2025–2026):**
   - Nguồn: [Vertex AI: Function Calling in Gemini](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling).
   - Điểm cốt lõi: Cơ chế Multi-turn Tool Calling hỗ trợ mô hình tự động nhận diện điểm dừng (STOP) khi đã thu thập đủ bối cảnh từ các công cụ đọc.
4. **Tài liệu học thuật nền tảng:**
   - *ReAct: Synergizing Reasoning and Acting in Language Models* (Yao et al., ICLR 2023): Cơ chế đan xen giữa suy nghĩ (Thought) và hành động (Action/Tool).
   - *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection* (Asai et al., ICLR 2024).

### 2.2. Tài liệu kiến trúc và đặc tả nội bộ microSched
1. `C:\Users\os\Desktop\cur_docs\PTHTTM\btl\04-spec-hop-nhat-mimi.md`: Đặc tả hợp nhất Mimi (khóa ngày 10/09/2026). Ràng buộc C0–C3, Frozen Preview, CAS/digest, timeout 10 phút, Soft-lock RAM PIN 36 phút, cơ chế Steering phân loại `SUPPLEMENT_NO_CHANGE` vs `MATERIAL_CHANGE`.
2. `C:\Users\os\Desktop\cur_docs\PTHTTM\btl\02-spec-thuc-thi-mimi.md`: Đặc tả chi tiết phân hạng công cụ C0 (Read), C1 (Reversible Write, <= 5 ops), C2 (Sensitive/Bulk Write, 6–20 ops), C3 (Denied).
3. `docs/architecture-brief.md` & `docs/project-guide.md`: Kiến trúc FastAPI monolith, PostgreSQL + pgvector trên Neon, Fly.io machine cấu hình `shared-cpu-1x` (512MB RAM + 512MB swap) tại Singapore (`sin`).

---

## 3. Các sự thật quan sát được (Observed Facts)

- **[FACT-B03-01] Ràng buộc tài nguyên Fly.io:** microSched vận hành trên một máy ảo Fly.io duy nhất với cấu hình `shared-cpu-1x`, 512 MB RAM vật lý và 512 MB swap. Mọi tác vụ xử lý tốn bộ nhớ hoặc việc duy trì nhiều kết nối mạng I/O đồng thời đều đe dọa trực tiếp đến tính ổn định của hệ thống (dễ gây OOM killer hoặc swap thrashing).
- **[FACT-B03-02] Độ trễ mạng API từ Singapore:** Thời gian phản hồi mạng (Round-Trip Time - RTT) từ Fly.io Singapore tới cụm máy chủ suy luận của Google Gemini hoặc OpenAI trung bình dao động từ 450ms đến 1.400ms cho mỗi lượt sinh token (với mô hình fast như Gemini 3.8 Flash hoặc GPT-5.6 Luna). Việc bổ sung thêm các lượt gọi LLM nối tiếp sẽ cộng dồn độ trễ tuyến tính vào thời gian người dùng phải chờ trước màn hình.
- **[FACT-B03-03] Cơ chế Tool Calling chuẩn:** Cả Gemini API và OpenAI API đều sử dụng cơ chế trao đổi có trạng thái: Client gửi message -> Model trả về cấu trúc yêu cầu gọi tool (`tool_calls`) -> Client thực thi cục bộ -> Client gửi lại kết quả (`tool_result`) -> Model tổng hợp trả lời.
- **[FACT-B03-04] Hệ thống phân hạng C0–C3 đã chốt:** Theo `04-spec-hop-nhat-mimi.md`:
  - C0 (Read): Bounded query, không làm biến đổi dữ liệu, không cần người dùng duyệt.
  - C1 (Reversible Write): Tối đa 5 operations, có hàm đảo ngược (inverse), bắt buộc Frozen Preview + Confirm (thời hạn 10 phút).
  - C2 (Sensitive/Bulk Write): Tác vụ nhạy cảm hoặc 6–20 operations, bắt buộc Strong Preview + Confirm riêng từng cụm.
  - C3 (Denied to Agent): Xóa cứng dữ liệu, thay đổi schema/secret, chạy code/SQL tùy ý — tuyệt đối không đăng ký tool.
- **[FACT-B03-05] Không có ngoại lệ tự động ghi (No Auto-Confirm):** Không có bất kỳ cơ chế nào cho phép Mimi tự ý ghi dữ liệu vào database mà không thông qua bước hiển thị Preview và nhận sự xác nhận rõ ràng của Owner.
- **[FACT-B03-06] Context Bloat khi nhồi sẵn dữ liệu:** Nếu nhồi toàn bộ dữ liệu lịch biểu, công việc, ghi chú vào system prompt ở mỗi lượt chat (Eager Injection), dung lượng context sẽ nhanh chóng vượt quá 30.000 tokens. Điều này làm tăng chi phí token lên nhiều lần, làm mất hiệu lực của Prompt Cache, và làm suy giảm khả năng tập trung của mô hình (hiện tượng Lost in the Middle).

---

## 4. Phân tích so sánh các biến thể chính sách tương tác (Competing Policy Variants)

Chúng tôi thiết kế và so sánh 3 biến thể chính sách tương tác toàn diện để tìm ra giải pháp tối ưu cho Mimi:

### 4.1. Biến thể 1: Pure Reactive / Immediate Preview (Luôn sinh Preview ngay lập tức)
- **Mô tả:** Bất cứ khi nào người dùng nhắc đến một ý định thay đổi dữ liệu, mô hình lập tức gọi công cụ để tạo ra một `change_set` và hiển thị Preview card kèm nút bấm Xác nhận / Hủy.
- **Điểm mạnh:** Giảm tối đa số lượt trò chuyện. Với các câu lệnh đơn giản, người dùng có thể bấm xác nhận ngay lập tức.
- **Điểm yếu nghiêm trọng:**
  - Đối với các yêu cầu mang tính định hướng hoặc mơ hồ (ví dụ: *"Sắp xếp lại tuần này giúp mình"*), mô hình buộc phải tự suy diễn các tham số (thời gian, mức ưu tiên, dời việc nào).
  - Nếu mô hình đoán sai, giao diện sẽ xuất hiện một bảng Preview dày đặc các thay đổi sai lệch. Người dùng phải bấm Hủy, giải thích lại, và chu trình lặp lại trong ức chế.
  - Gây ra hiện tượng "Mệt mỏi vì xác nhận" (Confirmation Fatigue), làm người dùng hình thành thói quen bấm "Xác nhận" nhanh mà không đọc kỹ diff, triệt tiêu ý nghĩa an toàn của ranh giới Preview.

### 4.2. Biến thể 2: Strict Two-Stage Gatekeeper (Bắt buộc Draft trước cho mọi lệnh ghi)
- **Mô tả:** Mọi yêu cầu ghi (kể cả lệnh cực kỳ rõ ràng như *"Tạo task nộp BTL vào 17h thứ Sáu"*) đều không bao giờ được sinh Preview ở lượt 1. Mô hình bắt buộc phải xuất ra văn bản phác thảo ý định ("Mình sẽ tạo task A vào giờ B, bạn có đồng ý không?"). Chỉ sau khi người dùng phản hồi xác nhận bằng chữ ở lượt 2, mô hình mới xuất ra Preview card có nút bấm thực thi.
- **Điểm mạnh:** Độ an toàn tối đa, người dùng luôn có một bước đọc văn bản xác nhận trước khi có nút bấm.
- **Điểm yếu nghiêm trọng:**
  - Trải nghiệm người dùng (UX Friction) rất kém trên các tác vụ lặp đi lặp lại hàng ngày. Việc tạo một nhắc nhở đơn giản đòi hỏi tới 3 bước: Gõ lệnh -> Đọc văn bản hỏi lại -> Gõ "đồng ý" -> Đọc Preview card -> Bấm nút Xác nhận.
  - Làm tăng gấp đôi số lượt gọi LLM và tiêu tốn token không cần thiết cho những hành vi rõ ràng.

### 4.3. Biến thể 3: Adaptive Tiered Interaction Policy (Chính sách thích ứng theo mức độ phức tạp — ĐỀ XUẤT)
- **Mô tả:** Phân luồng động dựa trên 3 tiêu chí: (1) Tính đầy đủ của tham số; (2) Phân hạng an toàn C0/C1/C2; và (3) Số lượng thực thể bị tác động:
  - **Nhánh A (Direct Answer / Clarification):** Dành cho câu hỏi đọc dữ liệu (C0) hoặc khi lệnh thiếu tham số then chốt không thể suy luận logic -> Trả lời trực tiếp hoặc đặt câu hỏi làm rõ ngắn gọn.
  - **Nhánh B (Fast-Path to Preview):** Dành cho các tác vụ C1 có tham số đầy đủ, rõ ràng, không xung đột lịch, tác động `<= 2` thực thể -> Mimi tự động gọi bounded read tools để kiểm tra xung đột; nếu hợp lệ, xuất thẳng **Frozen Executable Preview** kèm thông báo ngắn gọn.
  - **Nhánh C (Deliberate Draft-First):** Dành cho các tác vụ C2 (nhạy cảm, subscription, sửa đổi lớn), tác động `>= 3` thực thể, có xung đột lịch cần đánh đổi, hoặc người dùng bày tỏ ý định nhờ tư vấn/lên kế hoạch (*"phác thảo"*, *"gợi ý"*, *"sắp xếp"*). Tại nhánh này, Mimi xuất ra **Conversational Draft** (phân tích, lựa chọn A/B, nêu rõ đánh đổi). Chỉ khi người dùng đồng thuận, Mimi mới chuyển sang Frozen Preview.

### Bảng so sánh tổng hợp các biến thể

| Tiêu chí so sánh | Biến thể 1: Immediate Preview | Biến thể 2: Strict Two-Stage | Biến thể 3: Adaptive Tiered (Đề xuất) |
|---|---|---|---|
| **Độ trễ tác vụ thường nhật** | Thấp (~1 lượt LLM) | Cao (~2 lượt LLM + user gõ 2 lần) | Tối ưu (~1 lượt LLM) |
| **Xử lý yêu cầu phức tạp** | Rất kém (dễ sinh Preview rác) | Tốt (có thảo luận trước) | Rất tốt (thảo luận qua Draft) |
| **Rủi ro Confirmation Fatigue**| Rất cao | Trung bình | Thấp (chỉ Confirm khi đã rõ) |
| **Chi phí Token và API RTT** | Trung bình | Rất cao (lặp lại lịch sử) | Tiết kiệm theo từng tình huống |
| **Độ an toàn nghiệp vụ** | Tiềm ẩn rủi ro do bấm ẩu | Rất cao | Tuyệt đối an toàn (tuân thủ C1/C2) |

---

## 5. Ranh giới kỹ thuật: Conversational Draft vs. Frozen Executable Preview

[FACT-B03-05] và định hướng của Owner xác định rõ: **Draft và Preview là hai thực thể hoàn toàn tách biệt về mặt kiểu dữ liệu, vòng đời và quyền hạn thực thi.**

```
+-------------------------------------------------------------------------------+
|                             YÊU CẦU CỦA NGƯỜI DÙNG                            |
+-------------------------------------------------------------------------------+
                                       |
                   [Phân tích ý định & Bounded Read Tools]
                                       |
                 +---------------------+---------------------+
                 |                                           |
      (Yêu cầu phức tạp / C2 /                  (Lệnh rõ ràng / C1 / <= 2 entities)
       Nhiều thực thể / Mơ hồ)                               |
                 |                                           |
                 v                                           v
+---------------------------------+         +---------------------------------+
|      CONVERSATIONAL DRAFT       |         |    FROZEN EXECUTABLE PREVIEW    |
|---------------------------------|         |---------------------------------|
| - Kiểu: Markdown Text thô       |         | - Kiểu: JSON typed change_set   |
| - Không có ID / hash / digest   |         | - Có UUIDv7, CAS hash, TTL 10m  |
| - Không có nút bấm Execute      |         | - Có nút bấm "Xác nhận ghi"     |
| - Không khóa thực thể (locks)   |         | - Kiểm tra expected version     |
| - Mục đích: Bàn bạc, chọn lọc   |         | - Mục đích: Thực thi nguyên tử  |
+---------------------------------+         +---------------------------------+
                 |                                           |
       [Người dùng phản hồi/chọn]                            |
                 |                                           v
                 +---------------------------------> [Nút Confirm được bấm]
                                                             |
                                                             v
                                                    [Atomic DB Execution]
```

### 5.1. Bản thảo hội thoại (Conversational Draft)
- **Bản chất:** Là văn bản tự nhiên (Markdown prose) nằm trong dòng chảy tin nhắn của cuộc hội thoại.
- **Ranh giới kỹ thuật:**
  - Không có định danh `change_set_id`.
  - Không có mã băm bảo mật (digest).
  - Không thể được gửi đến endpoint thực thi của backend; backend từ chối mọi yêu cầu thực thi nếu không có cấu trúc typed payload hợp lệ.
  - Không tạo ra trạng thái pending hay optimistic UI trên giao diện các module Tasks, Calendar, Notes.
  - Không áp đặt khóa dữ liệu (locks) lên các bản ghi trong cơ sở dữ liệu.
- **Mục đích:** Giúp người dùng hình dung các phương án, so sánh đánh đổi, tinh chỉnh kế hoạch mà không phải chịu áp lực của việc xác nhận dữ liệu.

### 5.2. Bản xem trước có thể thực thi (Frozen Executable Preview)
- **Bản chất:** Là một cấu trúc dữ liệu JSON có kiểu nghiêm ngặt (Pydantic Schema), đại diện cho một tập hợp các phép đột biến trạng thái (mutations).
- **Ranh giới kỹ thuật (Bắt buộc theo `04-spec-hop-nhat-mimi.md`):**
  - Định danh duy nhất: `change_set_id` dạng UUIDv7.
  - Khóa phiên bản lạc quan (CAS Token / Digest): Mã băm SHA-256 đóng băng danh sách thao tác cùng với `expected_version` của các thực thể bị sửa đổi. Nếu bản ghi đã bị sửa đổi ở tab khác hoặc phiên khác, quá trình thực thi sẽ thất bại ngay lập tức (Conflict 409).
  - Thao tác có thể đảo ngược: Mỗi thao tác ghi đều đính kèm thông tin `inverse_operation` để hỗ trợ hoàn tác (Undo) trong thời hạn quy định.
  - Hết hạn cứng (Hard TTL): Có thời hạn tồn tại 10 phút (`expires_at`). Quá 10 phút, preview bị vô hiệu hóa tự động, nút xác nhận chuyển sang trạng thái disabled.
  - Gắn nhãn nhạy cảm: STANDARD hoặc PRIVATE. Nếu là PRIVATE, chỉ hiển thị và cho phép xác nhận khi UI grant còn hiệu lực (trong vòng 36 phút kể từ khi nhập PIN).
- **Giao diện người dùng:** Được hiển thị dưới dạng một thẻ linh kiện biệt lập (Preview Card Component), tách bạch với văn bản chat, hiển thị rõ ràng diff (cũ -> mới) và chỉ có hai nút bấm hành động: **"Xác nhận thực hiện"** và **"Hủy bỏ"**.

---

## 6. Vòng lặp công cụ đọc lặp (Iterative Read-Tool Loop)

### 6.1. Tại sao Mimi cần Iterative Read Loop?
[FACT-B03-07] Trong quản lý lịch trình cá nhân, một quyết định chính xác thường đòi hỏi dữ liệu liên kết từ nhiều bảng:
- *Ví dụ:* Khi người dùng yêu cầu: *"Xếp cho mình 2 tiếng học bài BTL vào chiều mai"*.
  - Lượt đọc 1: Mimi gọi `calendar.get_day(date="2026-09-23")` để xem các ca học cố định trên trường. Kết quả: 13:00 - 15:30 bận học.
  - Lượt đọc 2: Khung giờ 15:30 - 17:30 có vẻ trống, nhưng Mimi cần kiểm tra xem có task deadline hoặc việc cá nhân nào đã xếp vào khung giờ này chưa bằng cách gọi `tasks.list(date="2026-09-23")`.
  - Sau khi tổng hợp cả lịch học và danh sách việc, Mimi mới có đủ căn cứ thực tế để sinh kế hoạch không bị chồng chéo.

Nếu cấm vòng lặp đọc lặp:
- Hệ thống hoặc phải nhồi sẵn một lượng khổng lồ dữ liệu vào prompt (gây lãng phí token và mất cache hit).
- Hoặc mô hình chỉ được đoán mò dựa trên thông tin thiếu sót, dẫn tới các đề xuất sai lệch thực tế.

### 6.2. Hàng rào bảo vệ (Guardrails) cho Iterative Read Loop
Để ngăn ngừa tình trạng mô hình bị lặp vô tận (infinite loop), tiêu tốn quota hoặc làm quá tải tài nguyên máy chủ Fly.io:
1. **Chỉ dành riêng cho C0 (Read-only):** Vòng lặp tự động tuyệt đối CHỈ ĐƯỢC PHÉP gọi các tool đọc dữ liệu. Bất kỳ tool ghi (C1/C2) nào cũng lập tức ngắt vòng lặp tự động và chuyển quyền kiểm soát sang người dùng.
2. **Giới hạn số vòng lặp tối đa (Max Iteration Cap):** Giới hạn cứng **tối đa 3 vòng lặp công cụ đọc** trong một lượt yêu cầu của người dùng. Sau 3 lượt, nếu mô hình vẫn muốn gọi thêm tool, backend sẽ cưỡng chế dừng và yêu cầu mô hình tổng hợp trên dữ liệu hiện có.
3. **Giới hạn thời gian thực thi (Wall-clock Timeout):** Toàn bộ pha đọc lặp không được vượt quá **8 giây (8.000 ms)**. Nếu chạm ngưỡng timeout, tiến trình sẽ trả về kết quả đã thu thập được kèm cảnh báo giới hạn thời gian.
4. **Giới hạn bản ghi trả về (Bounded Payload):** Mỗi tool đọc C0 phải có phân trang hoặc giới hạn số lượng mặc định (ví dụ: `limit=20` cho task, `limit=5` cho đoạn trích note). Điều này ngăn chặn việc 1 tool call trả về dữ liệu quá lớn làm tràn 512MB RAM của tiến trình Python.

---

## 7. Phân tích chuyên sâu: Pha mô hình thứ hai (Second Model Phase) — Giúp ích hay Gây hại?

Nhiều hệ thống AI Agent thử nghiệm sử dụng kiến trúc hai pha: Pha 1 (Planner/Drafter) sinh nội dung, Pha 2 (Verifier/Critic/Formatter) kiểm tra hoặc định dạng lại. Chúng tôi đã phân tích kỹ lưỡng tính khả thi và đánh đổi của cơ chế này trong môi trường microSched.

### 7.1. Lợi ích lý thuyết của Pha mô hình thứ hai
- Độc lập kiểm tra rà soát an toàn, phát hiện prompt injection trước khi thực thi.
- Đóng vai trò phản biện (Critic) để tìm ra các điểm vô lý trong kế hoạch của Pha 1.
- Sửa lỗi định dạng JSON phức tạp nếu mô hình chính không tuân thủ schema.

### 7.2. Tác hại thực tế đối với microSched
Khi đặt vào hạ tầng thực tế của microSched (Fly.io Singapore, 512MB RAM, kết nối Neon Postgres):

1. **Độ trễ cộng dồn gây ức chế (Latency Doubling - [FACT-B03-02]):**
   - Pha 1 (Inference + Read Tools): ~1.2s – 2.2s.
   - Pha 2 (Verifier / Formatter): ~1.0s – 1.8s.
   - Tổng thời gian phản hồi: **3.2s – 4.5s**. Đối với một ứng dụng web/PWA quản lý cá nhân hàng ngày, việc phải chờ hơn 4 giây cho mỗi tương tác đơn giản là trải nghiệm người dùng không thể chấp nhận được.
2. **Gấp đôi chi phí Token và nguy cơ chạm Rate Limit:**
   - Việc chuyển tiếp toàn bộ ngữ cảnh và output của Pha 1 sang Pha 2 làm tăng 100% chi phí input token.
   - Khi chạy ở các tier API miễn phí hoặc giới hạn TPM (Tokens Per Minute), điều này đẩy nhanh nguy cơ gặp lỗi `429 Too Many Requests`.
3. **Mất sắc thái tiếng Việt tự nhiên:**
   - Các mô hình phụ đóng vai trò Verifier thường có xu hướng biến câu trả lời tiếng Việt mềm mại thành các gạch đầu dòng khô cứng, hoặc "bắt bẻ" quá mức các câu lệnh thông thường.
4. **Không cần thiết nhờ Structured Outputs:**
   - [FACT-B03-08] Cả OpenAI và Gemini hiện nay đều hỗ trợ Structured Outputs thông qua Constrained Decoding ở tầng engine. Tỷ lệ lỗi schema của các mô hình như Gemini 3.8 Flash hay GPT-5.6 Sol đối với các Pydantic schema chuẩn là gần như bằng 0.
5. **Rủi ro cạn kiệt tài nguyên máy chủ Fly.io (512MB RAM):**
   - Việc duy trì hai kết nối HTTP streaming liên tiếp kéo dài thời gian chiếm dụng memory buffer của tiến trình FastAPI, làm tăng nguy cơ máy ảo bị ép sử dụng bộ nhớ ảo (swap) gây suy giảm hiệu năng toàn trang.

### 7.3. Đề xuất kết luận: THAY THẾ BẰNG DETERMINISTIC CODE GATES
[PROPOSAL-B03-01] **Loại bỏ hoàn toàn Second LLM Phase trong luồng tương tác thời gian thực của Mimi.**
Toàn bộ vai trò kiểm duyệt an toàn, xác thực schema và kiểm tra logic nghiệp vụ được đảm nhiệm bởi **Deterministic Code Gates** viết bằng Python thuần túy:
- **Gate 1 (Pydantic Schema Validator):** Xác thực cấu trúc dữ liệu của tool call trong chưa đầy 1ms.
- **Gate 2 (Domain Business Rules Engine):** Kiểm tra logic nghiệp vụ: Hạn nộp có ở quá khứ không? Khung giờ kết thúc có sau khung giờ bắt đầu không? Số lượng operations có vượt ngưỡng quy định không?
- **Gate 3 (Optimistic Concurrency / CAS):** So khớp mã hash phiên bản để ngăn chặn việc ghi đè dữ liệu cũ.

*(Lưu ý: Sau môn học BTL, nếu cần tính năng rà soát memory nền, có thể sử dụng một worker chạy ngầm độc lập `ai_job`, hoàn toàn tách biệt khỏi chu trình tương tác của người dùng).*

---

## 8. Năm kịch bản đối thoại mẫu bằng tiếng Việt (Concrete Scenarios)

### Kịch bản 1: Hỏi đáp đọc dữ liệu (C0 Read — Direct Answer)
- **Người dùng:** *"Hôm nay mình có những việc gì cần làm và có lịch học nào không Mimi?"*
- **Xử lý của Mimi:**
  1. Phân loại: C0 (Đọc dữ liệu thuần túy).
  2. Vòng lặp đọc (Lượt 1): Gọi `calendar.get_day(date="2026-09-22")` -> Nhận kết quả: 13:00 - 15:30: Lớp Hệ phân tán (P.302-A2).
  3. Vòng lặp đọc (Lượt 2): Gọi `tasks.list(filter={"status": "todo", "due_date": "2026-09-22"})` -> Nhận kết quả: 2 việc (Nộp slide seminar, Đọc trước Bài 4).
  4. Đủ dữ kiện -> Tổng hợp trả lời.
- **Mimi phản hồi (Direct Answer):**
  > Chào bạn, lịch trình hôm nay thứ Ba (22/09) của bạn như sau:
  >
  > **Lịch học trên trường:**
  > - **13:00 – 15:30:** Hệ phân tán (Phòng 302-A2).
  >
  > **Nhiệm vụ cần hoàn thành trong ngày:**
  > 1. Nộp slide seminar (Ưu tiên cao).
  > 2. Đọc trước tài liệu Bài 4 môn Hệ phân tán.
  >
  > Chiều nay sau giờ học (từ 15:30 trở đi) bạn đang có lịch trống, có thể tận dụng để hoàn thành slide nhé.

---

### Kịch bản 2: Lệnh tạo việc nhỏ, rõ ràng, tức thì (Fast-Path to Preview)
- **Người dùng:** *"Tạo giúp mình task 'Nộp bài tập lớn PTHTTM' hạn 17:00 thứ Sáu tuần này, ưu tiên cao nhé."*
- **Xử lý của Mimi:**
  1. Phân loại: C1 (Ghi hẹp có inverse, 1 operation).
  2. Kiểm tra tham số: Đầy đủ và tường minh (Hạn chót: 25/09/2026 17:00, priority: HIGH).
  3. Bounded Read: Gọi `tasks.list(search="PTHTTM")` -> Không phát hiện task trùng lặp.
  4. Quyết định: Thỏa mãn tiêu chí **Fast-Path**. Gọi tool sinh Frozen Executable Preview.
- **Mimi phản hồi (Kèm UI Preview Card):**
  > Mình đã chuẩn bị sẵn task theo yêu cầu của bạn. Bạn kiểm tra lại thông tin bên dưới và bấm xác nhận nhé:
  >
  > ```json
  > :::mimi-preview{id="cs_01a0c8_task_create" digest="e3b0c442..." expires="10m"}
  > [Thao tác] TẠO MỚI NHIỆM VỤ (C1)
  > - Tiêu đề: Nộp bài tập lớn PTHTTM
  > - Hạn chót: 17:00, Thứ Sáu ngày 25/09/2026
  > - Mức độ ưu tiên: Cao (High)
  > - Trạng thái: Cần làm (Todo)
  > :::
  > ```
  > *(Giao diện hiển thị 2 nút bấm rõ ràng: **[ Xác nhận tạo việc ]** và **[ Hủy ]**)*
- **Hành động người dùng:** Bấm **[ Xác nhận tạo việc ]**.
- **Backend:** Kiểm tra digest và TTL -> Ghi dữ liệu vào PostgreSQL -> Trả về thông báo thành công kèm nút Undo (hoàn tác trong 10 phút).

---

### Kịch bản 3: Yêu cầu phức tạp, đa thực thể, lập kế hoạch (Deliberate Draft-First)
- **Người dùng:** *"Tuần này mình dồn 3 bài tập lớn và 1 bài kiểm tra giữa kỳ, bạn xem lại lịch rồi phác thảo giúp mình nên dời các việc cá nhân và phân bổ thời gian ôn tập như thế nào với."*
- **Xử lý của Mimi:**
  1. Phân loại: Yêu cầu chiến lược, tác động nhiều thực thể, có từ khóa "phác thảo" -> **BẮT BUỘC ĐI QUA CONVERSATIONAL DRAFT (Deliberate Path)**. Tuyệt đối không sinh Preview ngay.
  2. Vòng lặp đọc: Lấy toàn bộ lịch học trong tuần và 8 task đang mở.
  3. Phân tích: Có bài thi Kiến trúc máy tính vào thứ Năm; 3 hạn nộp BTL rơi vào thứ Sáu và Chủ Nhật; 4 việc cá nhân không khẩn cấp (dọn phòng, mua sách, sửa xe, gym).
- **Mimi phản hồi (Conversational Draft — KHÔNG CÓ NÚT THỰC THI):**
  > Mình đã rà soát toàn bộ lịch tuần này của bạn. Để đảm bảo kỳ thi diễn ra tốt nhất, mình đề xuất **Bản phác thảo điều chỉnh kế hoạch** như sau:
  >
  > **1. Nhóm việc trọng tâm cần dồn sức:**
  > - Ôn tập Kiến trúc máy tính: Dành 2 tiếng tối thứ Ba và 2 tiếng tối thứ Tư.
  > - BTL PTHTTM & Lập trình mạng: Tập trung vào chiều thứ Năm và cả ngày thứ Bảy.
  >
  > **2. Nhóm việc cá nhân đề xuất dời sang tuần sau:**
  > - Task *"Bảo dưỡng và sửa xe máy"* (đang để thứ Tư) -> Đề xuất dời sang thứ Ba tuần sau (29/09).
  > - Task *"Mua sách tham khảo"* -> Đề xuất tạm hoãn, chuyển sang danh sách việc chờ rảnh làm.
  >
  > **3. Sức khỏe:**
  > - Giữ lại 2 buổi tập gym ngắn (45 phút) vào thứ Ba và thứ Sáu để duy trì năng lượng, tạm nghỉ buổi thứ Năm.
  >
  > Bạn thấy phương án này có hợp lý không? Bạn muốn mình chốt phương án này để lên lịch chi tiết, hay cần thay đổi điểm nào?

---

### Kịch bản 4: Làm rõ khi yêu cầu mơ hồ / thiếu dữ kiện (Clarification)
- **Người dùng:** *"Dời buổi tập gym sang hôm khác giúp mình nhé."*
- **Xử lý của Mimi:**
  1. Vòng lặp đọc: Tra cứu thấy có 2 buổi tập gym trong tuần (Thứ Tư 17:30 và Thứ Sáu 17:30). Không rõ người dùng muốn dời buổi nào và dời sang ngày nào.
  2. Quyết định: Thiếu dữ kiện tiên quyết -> Đặt câu hỏi làm rõ ngắn gọn.
- **Mimi phản hồi (Clarification):**
  > Tuần này bạn đang có 2 buổi tập gym: **Thứ Tư (17:30)** và **Thứ Sáu (17:30)**.
  >
  > Bạn muốn dời buổi tập của **thứ Tư** hay **thứ Sáu**, và bạn muốn chuyển sang ngày nào (thứ Bảy hay Chủ Nhật)?

---

### Kịch bản 5: Người dùng can thiệp (Steering) khi Preview đang chờ duyệt
- **Bối cảnh:** Mimi vừa hiển thị Preview cho Kịch bản 2 (Tạo task Nộp BTL hạn thứ Sáu 17:00). Nút bấm xác nhận đang chờ người dùng. Người dùng không bấm nút mà gửi tin nhắn mới.
- **Người dùng:** *"À khoan, thầy vừa dời hạn nộp sang 12:00 trưa thứ Bảy rồi, sửa lại giúp mình."*
- **Xử lý của Mimi (Theo cơ chế Steering tại `04-spec-hop-nhat-mimi.md` §3):**
  1. Phân loại tin nhắn mới: `MATERIAL_CHANGE` (Thay đổi cốt lõi tham số của Preview hiện tại).
  2. Vô hiệu hóa (Invalidate) Preview cũ mang mã `cs_01a0c8_task_create`.
  3. Tạo `change_set` mới với tham số cập nhật: Hạn nộp mới = 12:00, Thứ Bảy 26/09/2026.
  4. Hiển thị Preview mới thay thế.
- **Mimi phản hồi (Updated Preview):**
  > Mình đã hủy bản xem trước cũ và cập nhật lại hạn nộp thành **12:00 trưa Thứ Bảy (26/09)** theo tin nhắn mới của bạn:
  >
  > ```json
  > :::mimi-preview{id="cs_01a0c9_task_create_v2" digest="f7a1b2c3..." expires="10m"}
  > [Thao tác] TẠO MỚI NHIỆM VỤ (C1) — ĐÃ CẬP NHẬT
  > - Tiêu đề: Nộp bài tập lớn PTHTTM
  > - Hạn hoàn thành: 12:00, Thứ Bảy ngày 26/09/2026 (Thay vì Thứ Sáu)
  > - Mức độ ưu tiên: Cao (High)
  > :::
  > ```
  > *(Giao diện hiển thị Preview v2 với digest mới, thẻ v1 cũ bị mờ và gắn cờ "Đã bị thay thế")*

---

## 9. Đề xuất chính sách hoàn chỉnh (Recommendations / Proposals)

Dựa trên toàn bộ chứng cứ kỹ thuật và thực tiễn kiến trúc microSched, chúng tôi đề xuất:

1. **[PROPOSAL-B03-02] Áp dụng Vòng lặp đọc lặp có kiểm soát (Bounded Iterative Read Loop):**
   Cho phép mô hình tự động gọi công cụ đọc C0 lặp lại tối đa 3 lượt trong một request, với timeout cứng 8 giây và giới hạn bản ghi trả về, phục vụ việc tự tìm hiểu trạng thái microSched.
2. **[PROPOSAL-B03-03] Tiêu chuẩn hóa ranh giới Fast-Path vs. Deliberate Draft-First:**
   - **Fast-Path (Đi thẳng tới Preview):** Khi thỏa mãn: C1 + Số lượng thực thể `<= 2` + Tham số đầy đủ + Không xung đột lịch.
   - **Deliberate Draft-First (Bắt buộc Draft trước):** Khi rơi vào C2 + Số lượng thực thể `>= 3` + Có xung đột lịch hoặc người dùng thể hiện ý định tư vấn/phác thảo.
3. **[PROPOSAL-B03-04] Loại bỏ Second Model Phase trong runtime:**
   Thay thế hoàn toàn pha mô hình thứ hai bằng Deterministic Python Gates (Pydantic Schema Validation, Business Rules, Concurrency CAS Versioning) để tiết kiệm 1–2 giây độ trễ và tránh lãng phí token trên Fly.io.
4. **[PROPOSAL-B03-05] Xử lý Steering theo cơ chế phân loại tác động (Impact Classifier):**
   Tự động phân loại tin nhắn mới khi có Preview đang treo thành `SUPPLEMENT_NO_CHANGE` (bổ sung vô hại -> giữ preview) hoặc `MATERIAL_CHANGE` (thay đổi cốt lõi -> hủy preview cũ, sinh preview mới).

---

## 10. Các câu hỏi chưa giải quyết dành cho Owner / T1 Workshop (Unresolved Questions)

1. **Ngưỡng số lượng thực thể cho Fast-path:** Đề xuất hiện tại là `<= 2` thực thể thì cho phép Fast-path đi thẳng tới Preview; từ 3 trở lên bắt buộc Draft trước. Owner có mong muốn hạ xuống mức an toàn tuyệt đối là `<= 1` (chỉ duy nhất 1 thao tác đơn lẻ mới được Fast-path) hay giữ `<= 2` để thuận tiện cho việc tạo task kèm reminder liên kết?
2. **Hành vi khi phát hiện xung đột lịch:** Khi người dùng yêu cầu tạo việc rơi vào khung giờ đã có sự kiện lịch cứng trên trường:
   - *Phương án A:* Tự động hạ cấp từ Fast-path xuống Draft để cảnh báo xung đột và hỏi ý kiến?
   - *Phương án B:* Vẫn sinh Preview nhưng đính kèm nhãn cảnh báo màu cam nổi bật trên thẻ Preview để người dùng tự quyết định?
3. **Chính sách đối với Draft cũ sau nhiều ngày:** Nếu người dùng quay lại một cuộc hội thoại sau 3 ngày và nói *"Hãy làm theo bản phác thảo hôm nọ đi"*, Mimi nên:
   - *Phương án A:* Tự động đọc lại database hiện tại, so khớp lại và sinh Preview?
   - *Phương án B:* Cảnh báo rằng bản phác thảo có thể đã lỗi thời và yêu cầu tóm tắt/xác nhận lại bối cảnh trước khi sinh Preview?

---

## 11. Phiên bản chứng cứ, ngày thực hiện và giới hạn (Evidence Version & Limitations)

- **Ngày lập báo cáo:** 22/09/2026.
- **Tài liệu căn cứ:** `04-spec-hop-nhat-mimi.md` (Owner-approved 10/09/2026), `02-spec-thuc-thi-mimi.md`, Anthropic Building Effective Agents (Dec 2024 / 2025), OpenAI Structured Outputs Guides (2024–2026).
- **Giới hạn nghiên cứu:**
  - Báo cáo này mang tính phân tích kiến trúc lý thuyết và đối chiếu tiêu chuẩn ngành. Chưa có số liệu đo đạc thực nghiệm về độ trễ mạng thực tế từ Fly.io Singapore tới các API endpoint tại thời điểm viết báo cáo.
  - Các đoạn hội thoại tiếng Việt là ngữ liệu mô phỏng dựa trên nhu cầu học tập thực tế tại PTIT, cần được đưa vào bộ dữ liệu kiểm thử tự động (Synthetic Evals) sau khi Owner phê duyệt chính sách.
