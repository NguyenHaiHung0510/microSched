# Mimi context builder — snapshot v1

Bản **v1 · 2026-10-11 · Asia/Saigon** mô tả source commit `43b50366a08f7ae84486ec6dc4fadcf2b8758b20`: collection OFF, policy v2, LangGraph và OpenAI SDK qua OpenRouter.

![Mimi lắp context và dùng công cụ như thế nào?](assets/mimi/context-builder-2026-10-11-v1.png)

Ảnh giải thích cách lắp messages, gắn native tools riêng và xử lý kết quả qua read, candidate, frozen preview, Confirm và atomic receipt. Nhánh collection ON được ghi rõ là điều kiện của snapshot. Đây là hình minh họa source, không phải receipt QA.

Metadata và SHA256: [context-builder-2026-10-11-v1.json](assets/mimi/context-builder-2026-10-11-v1.json). PNG gốc được giữ nguyên, SHA256 `35d121544fdd0e335cc9f82fd0930fa511725a8006719536c26b936667959f76`.

Ảnh đã lưu trong hệ thống tài liệu local theo ngày và version. Giữ snapshot này để tra cứu lâu dài; thay đổi kiến trúc tạo bản mới kèm source commit mới. Candidate EN policy, compact272K và pool động được mô tả riêng trong [routing/context contract](mimi-owner162-routing-contract.md); candidate còn chờ các gate QA và production.

Nguồn mã: `backend/app/agent/context_builder.py`, `service.py`, `langgraph_runner.py`, `tools/registry.py` và `openrouter.py`. Ảnh được tạo bằng built-in imagegen từ source map T1.
