# 01 — Codex tự khai cấu hình (chạy HAI lần, A và B)

**Trạng thái:** ⏳ CHƯA CHẠY

> Executor: **T2 Codex** · Bậc: **Sol** · Effort: **high** · **Skill gợi ý:** không · **MCP cần:** KHÔNG — *cố ý*, xem §"Không được làm"

**Vì sao Sol/high** (luật `agent-tasks/README.md`: spec phải ghi bậc + effort): không phải vì việc khó — nó dễ. Vì **blast-radius của một câu trả lời sai ở đây rất cao**: kết quả này quyết định **luật của dự án được đặt ở đâu**. Nếu Codex khai nhầm *"tôi có memories"* thì luật bị đặt vào một chỗ không ai đọc. Không dùng `xhigh`: đây không phải việc thiết kế, và `xhigh` chỉ thêm xu hướng scope creep (bài học đo được ở task 003).

## Việc của CHỦ trước khi chạy task

- [ ] **Cài `codex` toàn cục:** `npm install -g @openai/codex`. *Hiện `codex` KHÔNG có trên PATH* — máy đang chạy Codex desktop app với CLI ẩn ở `…\AppData\Local\OpenAI\Codex\bin\<hash>\codex.exe`, mà thư mục có hash nên **không thêm vào PATH được**. Bản npm dùng chung `~/.codex` (cùng `CODEX_HOME`) ⇒ chung auth, chung config, chung memories.
- [ ] **Cài plugin** trong Claude Code: `/plugin marketplace add openai/codex-plugin-cc` → `/plugin install codex@openai-codex` → `/reload-plugins` → `/codex:setup`.
- [ ] **KHÔNG bật review gate** (`--enable-review-gate`). README của plugin cảnh báo nó tạo vòng lặp Claude↔Codex dài và đốt limit nhanh; nó cũng đặt cổng sai chỗ (chặn *câu trả lời của Claude*, chứ không chặn *diff*).
- [ ] Node ≥ 18.18 — máy đang có v24.15.0 ✓ (không cần làm gì).

Lỗi sẽ gặp nếu quên bước 1: plugin báo không tìm thấy binary `codex`.

## Mục tiêu

Trả lời bằng **quan sát** (không phải suy đoán từ kết quả) hai câu: Codex thấy gì, và làm được gì — **ở từng bề mặt gọi**.

## Phải làm

Chạy **đúng khối prompt ở §Prompt** hai lần, không kèm file nào, không giải thích thêm:

| Lần | Nơi chạy | Cách đặt model/effort |
|---|---|---|
| **A** | **Codex app** (interactive) | chọn Sol + high trong UI |
| **B** | **Claude Code**, qua plugin | `/codex:rescue --model gpt-5.6-sol --effort high --wait` |

Lưu hai output nguyên văn vào `harness-reports/01-codex-self-audit/` thành `run-A.md` và `run-B.md`.

## KHÔNG được làm

- **Không kèm file, không tóm tắt bối cảnh, không "giúp" nó bằng cách nói trước câu trả lời.** Toàn bộ giá trị của task nằm ở chỗ nó *tự* thấy được gì.
- **Không bật web search, không gọi MCP tool.** Ngoài lý do không cần, còn một lý do cứng: config có `memories.disable_on_external_context = true` ⇒ phiên chạm MCP/web-search sẽ **không sinh memory**, làm nhiễu chính thứ đang đo.
- **Không sửa file nào** — trừ đúng một ngoại lệ ở mục 5 của prompt (tạo rồi xoá ngay `.probe`).
- Không chạy lại bản B rồi lấy nó thay bản A, hoặc ngược lại. **Thiếu một bản thì task chưa xong** — sản phẩm là *hiệu số*, không phải một trong hai.

## Prompt (dán nguyên khối, không sửa)

---

Mở đầu output bằng đúng một dòng: `Lần chạy: A (Codex app)` hoặc `Lần chạy: B (qua Claude Code plugin)`.

Đây là một phiên **chỉ-đọc, chỉ-khai-báo**. Không sửa file, không chạy lệnh thay đổi trạng thái, không commit, không gọi mạng ngoài. Nhiệm vụ duy nhất: **khai báo chính xác bạn đang thấy gì và làm được gì.**

Luật trả lời — bắt buộc, áp cho từng ý một:

- Gắn nhãn `[QUAN SÁT]` nếu bạn **thực sự nhìn thấy** thứ đó trong context / trong output lệnh bạn vừa chạy.
- Gắn nhãn `[SUY LUẬN]` nếu bạn đang đoán từ kiến thức chung hoặc từ tài liệu.
- Gắn nhãn `[KHÔNG BIẾT]` nếu bạn không có cách nào biết. **`[KHÔNG BIẾT]` là câu trả lời hợp lệ và được ưa hơn một phỏng đoán.**
- Không có nhãn = câu trả lời không được tính.

Trả lời đủ 8 mục, theo đúng thứ tự:

**1. Danh tính phiên**
Model đang thực chạy (tên đầy đủ) · reasoning effort · personality (nếu có) · phiên bản Codex CLI. Nếu bạn chỉ đọc được từ `~/.codex/config.toml` chứ không thấy giá trị *đang chạy*, nói rõ điều đó.

**2. Context của bạn gồm những khối nào**
Liệt kê **tên từng khối** đang có trong context của bạn lúc này (system prompt, developer instructions, user message, file được đính kèm, khối memories, tóm tắt phiên trước…) kèm **độ dài ước lượng** mỗi khối. Không cần nội dung, cần **danh sách**.

**3. Memories — câu hỏi quan trọng nhất**
a) Trong context có khối nào là **memories / bộ nhớ dài hạn** không?
b) Nếu **có**: dán **300 ký tự đầu tiên** của khối đó, nguyên văn.
c) Nếu **không có**: nói thẳng "không có khối memories trong context".
d) Không đọc thư mục `~/.codex/memories/` để trả lời mục này — tôi đang hỏi **context**, không hỏi **đĩa**. (Mục 6 mới hỏi đĩa.)

**4. File chỉ dẫn bạn thấy được**
Với **từng** file sau, trả lời `CÓ TRONG CONTEXT` / `CÓ TRÊN ĐĨA NHƯNG KHÔNG TRONG CONTEXT` / `KHÔNG THẤY`:
- `C:\Users\os\.codex\AGENTS.md`
- `<thư mục làm việc hiện tại>\AGENTS.md`
- `<thư mục làm việc hiện tại>\CLAUDE.md`
- `<thư mục làm việc hiện tại>\.codex\config.toml`

Với file nào bạn khai `CÓ TRONG CONTEXT`, **trích một dòng nguyên văn** của nó làm bằng chứng.

**5. Quyền hạn thật**
Thư mục làm việc hiện tại (đường dẫn tuyệt đối) · sandbox mode · approval policy · có truy cập mạng không · ghi file được không · chạy `git` được không · chạy lệnh shell được không.
Thêm: **bạn có ghi được ra một thư mục NGOÀI thư mục làm việc không**? Trả lời bằng cách **thử tạo và xoá ngay** một file rỗng tên `.probe` ở `C:\Users\os\Desktop\ai_eng_path\` rồi khai kết quả — đây là ngoại lệ duy nhất của luật "không sửa file".
Với mỗi mục, nói rõ bạn biết bằng cách nào (đọc config? thử? được khai trong system prompt?).

**6. Bộ nhớ trên đĩa**
Liệt kê nội dung thư mục `C:\Users\os\.codex\memories\` (tên file + kích thước). **Chỉ liệt kê, không mở nội dung.**

**7. Công cụ**
Liệt kê **tên đúng** của mọi tool bạn gọi được trong phiên này. Nếu có tool trình duyệt / MCP, nêu riêng.

**8. Ai đang gọi bạn**
a) Bạn có biết phiên này được khởi động từ đâu không (người gõ trực tiếp? một chương trình khác? Claude Code?) — và **bạn biết bằng dấu hiệu nào**?
b) Bạn có thấy transcript hay lịch sử hội thoại của một agent khác trong context không?
c) Phiên này **có sinh memory mới** cho lần sau không? Bạn dựa vào đâu để nói vậy?

Kết thúc bằng đúng một dòng:

`TỔNG KẾT: lần=A/B · memories trong context=CÓ/KHÔNG · AGENTS.md repo=CÓ/KHÔNG · AGENTS.md global=CÓ/KHÔNG · ghi file trong cwd=ĐƯỢC/KHÔNG · ghi file ngoài cwd=ĐƯỢC/KHÔNG · mạng=CÓ/KHÔNG`

---

## Acceptance (kiểm chứng được)

- [ ] Tồn tại `harness-reports/01-codex-self-audit/run-A.md` và `run-B.md`, mỗi file mở đầu bằng dòng `Lần chạy:` đúng bản của nó.
- [ ] Cả hai file có đủ 8 mục và **mọi ý đều có nhãn** `[QUAN SÁT]` / `[SUY LUẬN]` / `[KHÔNG BIẾT]`. Ý không nhãn ⇒ chạy lại, không tự suy ra nhãn hộ.
- [ ] Cả hai file kết bằng đúng dòng `TỔNG KẾT: …` với đủ 7 trường.
- [ ] Có một bảng so sánh A↔B (do T1 hoặc chính chủ viết, không phải Codex tự viết) nêu **mọi trường khác nhau** giữa hai dòng TỔNG KẾT.

## Quyết định mà kết quả này mở khoá

| Kết quả | Hệ quả |
|---|---|
| B **có** memories trong context | Đường plugin giữ được trí nhớ ⇒ giao việc qua plugin không mất ngữ cảnh tích luỹ. |
| B **không** có, A **có** | Đúng như nghi ngờ: plugin là bề mặt "sạch trí nhớ". ⇒ **mọi luật phải-luôn-áp-dụng bắt buộc nằm trong `AGENTS.md`**, memory chỉ là lớp gợi nhớ. Ảnh hưởng trực tiếp task 02. |
| B **ghi được ngoài cwd** | Codex chạy qua plugin có thể đổ báo cáo vào `harness-reports/` — cần biết trước khi thiết kế task 02. |
| B cwd **khác** cwd của Claude | Mở đường cho worktree riêng mỗi luồng (giới hạn cứng #4, `devops-brief.md` §8). Nếu **trùng** cwd thì luật *"chạy nền ⇒ Claude không chạm cây làm việc"* là bắt buộc. |
