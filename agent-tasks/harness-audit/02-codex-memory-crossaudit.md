# 02 — Codex đối soát bộ nhớ hai bên và tự học

**Trạng thái:** ⏳ CHƯA CHẠY (chờ `01-codex-self-audit.md`)

> Executor: **T2 Codex** · Bậc: **Sol** · Effort: **xhigh** · **Skill gợi ý:** không · **MCP cần:** KHÔNG — *bắt buộc tắt*, xem §"Không được làm"

**Vì sao Sol/xhigh:** đây đúng chỗ `xhigh` xứng đáng. Hành vi phân biệt của nó — đo được thật ở task 006 — là **dừng lại trước khi viết để escalate mâu thuẫn có thật**, thay vì tự chọn một bên. Đó chính xác là thứ **rổ D** của task này cần. Chi phí tham chiếu: 006 ở Sol/xhigh tốn ~11% pool tuần, và quota đã được đo nhiều lần là **không phải ràng buộc** ở nhịp làm việc này (`docs/devops-brief.md` §7).

## Việc của CHỦ trước khi chạy task

- [ ] **`01-codex-self-audit.md` đã chạy xong cả A lẫn B**, và đã có bảng so sánh. Kết quả đó quyết định rổ A nên đề xuất đích đến nào.
- [ ] **Chạy trong Codex app** (interactive), **KHÔNG qua plugin**.
- [ ] **Tắt web search và mọi MCP tool** trong phiên đó.
- [ ] Chọn Sol + xhigh trong UI.

## Vì sao chạy ở app chứ không qua plugin

Ba lý do, xếp theo mức quan trọng:

1. **Mục tiêu là để bộ nhớ Codex thật sự ghi nhận phiên này.** Task 01 mới là thứ trả lời "đường plugin có memory không" — không dùng đường chưa kiểm chứng cho việc mà trí nhớ *là* sản phẩm.
2. **`memories.disable_on_external_context = true`** trong `~/.codex/config.toml`: phiên nào chạm MCP/web-search thì **không sinh memory**. Đọc file local bằng tool sẵn có thì không rơi vào nhóm đó — nên phiên này phải sạch MCP.
3. Phiên dài, đọc nhiều file; chính chủ có thể muốn chen ngang.

## Mục tiêu

So hai hệ bộ nhớ của cùng một người dùng — của Claude Code và của Codex — rồi báo cáo khoảng trống **kèm đề xuất vá cụ thể**. Bối cảnh có thật: chính chủ dùng Codex **lâu hơn** dùng Claude, nên rổ "Codex biết mà Claude không" nhiều khả năng là rổ nặng nhất — và nó chưa từng được ai đọc.

## Quyền ghi — ranh giới hẹp

**Được ghi, và chỉ ở đây:** `harness-reports/02-memory-crossaudit/` (tạo nếu chưa có), gồm ba file:
- `report.md` — báo cáo đầy đủ, cấu trúc ở §Định dạng
- `proposed-repo-AGENTS.md` — **đề xuất** bản mới cho `AGENTS.md` của repo
- `proposed-global-AGENTS.md` — **đề xuất** bản mới cho `~/.codex/AGENTS.md`

Ghi bằng **UTF-8**. *(Luật `AGENTS.md`: text tiếng Việt qua file, không qua tham số inline — PowerShell nuốt dấu và mất là mất hẳn.)*

**Tuyệt đối KHÔNG sửa file đang có hiệu lực:** `C:\Users\os\.codex\AGENTS.md` · `AGENTS.md` · `CLAUDE.md` · `docs/*` · toàn bộ `C:\Users\os\.claude\` · toàn bộ `C:\Users\os\.codex\memories\`. Với những file đó chỉ **đề xuất**; chính chủ và T1 áp. Lý do: đó là luật đang chạy, và **một agent tự viết lại luật của chính nó là vòng lặp không ai kiểm được**.

**Về bộ nhớ của chính Codex:** đừng viết tay vào `~/.codex/memories/` — docs OpenAI gọi đó là *generated state* và nó có lifecycle consolidate sẽ nuốt mất thứ đặt tay vào. Cứ để phiên diễn ra tự nhiên, cơ chế auto-memory làm việc của nó. Thứ cần **bền** thì đặt vào `proposed-global-AGENTS.md`.

## KHÔNG được làm

- **Không bật web search, không dùng MCP tool.** (Xem §"Vì sao chạy ở app".)
- **Không commit, không `git add`, không đụng git.**
- **Không đọc ngoài phạm vi §Phạm vi.** Cụ thể không mở: transcript hội thoại (`*.jsonl`), các dự án khác của chính chủ, `.env`, `auth.json`, `*.sqlite`, thư mục `sessions/`.
- **Không ghi vào báo cáo:** địa chỉ email, token, key, tên tài khoản. Repo này **public** và threat model của chủ là **social engineering** (`docs/devops-brief.md` §1) — viết theo vai (*"tài khoản trong allowlist"*), không viết địa chỉ.
- **Không tự quyết bên nào đúng ở rổ D.** Nêu đủ hai phía rồi dừng.

## Phạm vi được đọc — đúng những đường dẫn này

**Bên A — bộ nhớ Claude:**
- `C:\Users\os\.claude\projects\C--Users-os-Desktop-ai-eng-path-microsched\memory\` — toàn bộ `*.md` (gồm `MEMORY.md` là chỉ mục)

**Bên B — bộ nhớ Codex (của chính bạn):**
- `C:\Users\os\.codex\memories\MEMORY.md`
- `C:\Users\os\.codex\memories\memory_summary.md`
- `C:\Users\os\.codex\memories\raw_memories.md`
- `C:\Users\os\.codex\memories\rollout_summaries\` (toàn bộ)
- `C:\Users\os\.codex\memories\skills\` (toàn bộ)
- `C:\Users\os\.codex\AGENTS.md`

**Bên C — luật đang có hiệu lực** (để biết cái gì *đã* được ghi ở chỗ đúng):
- `CLAUDE.md` · `AGENTS.md` (gốc repo)

## Phải làm

Phân loại **mọi** thứ đáng nhớ tìm được vào đúng 4 rổ. Mỗi mục **bắt buộc** có: đường dẫn file + **trích dẫn ngắn nguyên văn** làm bằng chứng + nhãn `[QUAN SÁT]` hoặc `[SUY LUẬN]`.

**Rổ A — Claude biết, Codex không biết.** Với mỗi mục đề xuất **đúng một** đích đến:
- `→ AGENTS.md repo` — luật riêng của dự án microSched
- `→ ~/.codex/AGENTS.md` — cách làm việc **xuyên dự án** với người này
- `→ BỎ` — nghi thức của vai điều phối/quyết định (viết brief, chốt trạng thái quyết định, đóng phiên). Bạn không giữ vai đó; nạp vào chỉ gây hiểu nhầm về thẩm quyền.

**Rổ B — Codex biết, Claude không biết.** ← *rổ có giá trị nhất, làm kỹ nhất.* Nêu cụ thể những gì bộ nhớ của bạn có mà phía Claude hoàn toàn không có dấu vết: thói quen, bẫy môi trường, quy ước, sự cố cũ, sở thích diễn đạt. Mỗi mục nói rõ **nó đến từ đâu** (task nào, ngày nào nếu có). Gom thành một mục liền mạch dễ copy — nó sẽ được nạp ngược vào memory của Claude.

**Rổ C — trùng lặp.** Cùng một sự thật đang nằm ở ≥2 nơi. Chỉ ra **nơi nào nên là bản gốc**, nơi nào nên bỏ. *(Bối cảnh: `CLAUDE.md` mở đầu bằng chính bài học này ở tầng dữ liệu — app cũ chạy SQLite lẫn Postgres rồi mất dấu đâu là thật. Dự án này coi một-sự-thật-hai-chỗ là **lỗi kiến trúc**, không phải dự phòng.)*

**Rổ D — mâu thuẫn.** Hai nguồn nói ngược nhau. Nêu đủ hai phía kèm trích dẫn rồi **dừng**.

## Định dạng báo cáo (`report.md`)

1. Một đoạn 5 dòng: đã đọc bao nhiêu file mỗi bên, tổng dung lượng, file nào không mở được.
2. Bốn rổ A/B/C/D, mỗi mục một dòng gọn.
3. **"Ba điều tôi khuyên đổi ngay"** — xếp theo mức **đắt-nếu-bỏ-sót**, không theo mức dễ làm.
4. **"Điều tôi không chắc"** — liệt kê thẳng, không lấp bằng phỏng đoán.
5. Danh sách file đã tạo trong `harness-reports/02-memory-crossaudit/`.

## Acceptance (kiểm chứng được)

- [ ] Ba file tồn tại trong `harness-reports/02-memory-crossaudit/`, đọc được, **không mất dấu tiếng Việt**.
- [ ] `git status --short` cho thấy **không file nào ngoài `harness-reports/` bị đổi**. Có file khác đổi ⇒ task **thất bại**, hoàn tác rồi báo cáo.
- [ ] Mọi mục trong 4 rổ đều có đường dẫn + trích dẫn + nhãn. Mục thiếu bằng chứng không được tính.
- [ ] Rổ B **không rỗng** — nếu rỗng thì hoặc phạm vi đọc bị hụt, hoặc kết luận đó phải được nêu tường minh kèm lý do, không im lặng bỏ qua.
- [ ] Rổ D: mỗi mâu thuẫn nêu **đủ hai phía**, không có mục nào Codex đã tự chọn bên.

## Sau khi xong (việc của T1 + chính chủ)

1. Đọc rổ B, nạp thứ đáng giá vào memory của Claude.
2. Duyệt hai file `proposed-*`, áp phần đồng ý vào `AGENTS.md` / `~/.codex/AGENTS.md`.
3. **Rồi dọn `harness-reports/02-memory-crossaudit/`** — báo cáo đã hết vai. Đây là chỗ tạm ứng, không phải kho (`agent-tasks/harness-audit/README.md` luật 3).
