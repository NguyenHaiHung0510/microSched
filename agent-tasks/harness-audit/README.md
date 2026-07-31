# agent-tasks/harness-audit/ — đối soát giữa hai harness (Claude ↔ Codex)

Thư mục này **không** thuộc hàng đợi `NNN-<slug>.md` của dự án. Nó chứa spec cho một loại việc khác: **kiểm tra và đồng bộ chính bộ máy làm việc**, chứ không phải xây tính năng microSched. Vì vậy đánh số riêng `01-`, `02-` để không lẫn với 001–012.

Bối cảnh (chốt 2026-07-22): dự án chuyển từ **chuyển tay giữa hai harness** sang **Claude điều phối Codex trực tiếp** qua plugin [`openai/codex-plugin-cc`](https://github.com/openai/codex-plugin-cc). Trước khi trao quyền đó phải trả lời hai câu, bằng **quan sát chứ không bằng suy đoán**:

1. Khi Codex bị gọi từ Claude Code, **nó thấy gì?** (memories? `AGENTS.md`? quyền ghi tới đâu?)
2. Hai hệ bộ nhớ đang **lệch nhau chỗ nào**, và mỗi mảnh nên sống ở đâu?

## Thứ tự chạy — không đảo

| Bước | File | Chạy ở đâu | Model / effort |
|---|---|---|---|
| **1A** | `01-codex-self-audit.md` | **Codex app** (interactive) | `gpt-5.6-sol` / `high` |
| **1B** | `01-codex-self-audit.md` | **Claude Code**, qua plugin | `gpt-5.6-sol` / `high` |
| **so** | — | chính chủ + T1 đọc hai bản, **lấy hiệu** | — |
| **2** | `02-codex-memory-crossaudit.md` | **Codex app**, tắt web/MCP | `gpt-5.6-sol` / `xhigh` |

**Vì sao 01 phải chạy hai lần:** một lần chạy chỉ cho một bức ảnh; hai lần cho một **phép trừ**. Chênh lệch giữa bản A và bản B **chính là** câu trả lời cho "đường plugin có làm mất memory/context không" — thứ mà tài liệu OpenAI không nói (docs Memories chỉ mô tả phiên interactive, không nói gì về phiên app-server).

**Vì sao 02 chạy sau:** kết quả 01 quyết định 02 nên đề xuất đặt luật ở đâu. Nếu 01 trả về *"không có khối memories trong context"* thì mọi thứ phải-luôn-áp-dụng **bắt buộc** nằm trong `AGENTS.md`, không được nằm trong memory.

## Nơi đổ báo cáo

Mọi output của hai task này ghi vào **`agent-tasks/harness-reports/`** — xem README trong đó để biết luật. *(2026-07-23: thư mục đã dời từ gốc repo về đây cho nằm cạnh spec sinh ra nó; `.gitignore` đã được sửa từ `harness-reports/*` sang `**/harness-reports/*` vì mẫu cũ neo vào gốc repo nên hết khớp sau khi dời — xem `01-…/comparison.md` §8.)* Tóm tắt: thư mục đó **có trong git nhưng nội dung KHÔNG lên public** (repo này public; báo cáo nói về thói quen làm việc và bộ nhớ cá nhân).

## Ba luật chung cho cả hai task

1. **Không sửa file đang có hiệu lực.** `~/.codex/AGENTS.md`, `AGENTS.md`, `CLAUDE.md`, `docs/*`, `~/.claude/*`, `~/.codex/memories/*` — chỉ **đề xuất patch**, chính chủ và T1 áp. Một agent tự viết lại luật của chính nó là vòng lặp không ai kiểm được.
2. **Không viết tay vào `~/.codex/memories/`.** Docs OpenAI gọi đó là *generated state*; nó có lifecycle consolidate sẽ nuốt mất thứ đặt tay vào. Thứ cần **bền** thì đề xuất vào `~/.codex/AGENTS.md`.
3. **`harness-reports/` là chỗ tạm ứng, không phải kho.** Khi phát hiện đã nhập vào `AGENTS.md` / `~/.codex/AGENTS.md` / memory của Claude thì báo cáo hết vai trò. Mục tiêu cuối là **giảm** số nơi chứa sự thật — không phải thêm một nơi. Đây là cùng một nguyên tắc chống split-brain mà `CLAUDE.md` đặt ra cho tầng dữ liệu.

## Trạng thái

| # | Việc | Trạng thái |
|---|---|---|
| 01 | Codex tự khai cấu hình (chạy 2 lần A/B) | ✅ **XONG 2026-07-23** — nghiệm thu đạt (1 mục đạt một phần). Ba kết luận: ① plugin **giữ** memory của Codex · ② cwd Codex **trùng** cwd Claude ⇒ luật "chạy nền ⇒ Claude không chạm cây làm việc" **bắt buộc** · ③ hai trường "ghi file" **không so được** (prompt tự khai read-only làm nhiễu). |
| 02 | Đối soát bộ nhớ hai bên + đề xuất patch | ✅ **XONG 2026-07-23** (Sol/xhigh, Codex app, không web/MCP). 4 rổ: A 10 · B 6 · C 8 · D 3, đủ nhãn + đường dẫn, không mục nào tự chọn bên ở rổ D. **T1 đã áp:** rổ A → cả hai `AGENTS.md` · rổ B → memory Claude · **D1 = mâu thuẫn thật, đã vá `CLAUDE.md`** · D2/D3 không phải mâu thuẫn (memory Codex là ảnh chụp đóng băng lúc phiên kết thúc). **Còn lại: rổ C (8 điểm trùng lặp) chờ chủ quyết.** |
