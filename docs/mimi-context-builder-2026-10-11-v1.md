# Mimi context builder — ảnh tham khảo

Bản **v1 · 2026-10-11** mô tả source commit43b50366a08f7ae84486ec6dc4fadcf2b8758b20, khi collection OFF và policy v2. Ngày dùng Asia/Saigon.

![Mimi lắp context và dùng công cụ như thế nào?](assets/mimi/context-builder-2026-10-11-v1.png)

Ảnh được tạo bằng built-in imagegen từ source map T1. Đây là sơ đồ giải thích mã nguồn, không phải bằng chứng runtime hoặc QA. Native tools được gắn riêng ngoài messages; dữ liệu/checkpoint không cấp quyền; Model đề xuất và server chỉ ghi sau explicit Confirm. Nhánh collectionON trong ảnh là điều kiện tương lai của snapshot này.

Metadata và SHA256: [context-builder-2026-10-11-v1.json](assets/mimi/context-builder-2026-10-11-v1.json).

Giữ nguyên ảnh theo ngày/version; khi kiến trúc thay đổi, thêm snapshot mới và dẫn chiếu source commit mới. Không sửa ảnh cũ để mô tả runtime hiện tại.

Code roots: backend/app/agent/context_builder.py, service.py, langgraph_runner.py, tools/registry.py và openrouter.py. Canonical local source map: harness-reports/mimi-product-inquiry-20261008/owner144-approved-batch-language-context/T1-phase1/CONTEXT-BUILDER-MAP.md. Private handoff/report là provenance nội bộ, không cần sao chép vào tài liệu công khai.

Trạng thái lưu: local documentation preparation, chưa commit/merge. Batch sản phẩm vẫn chờ Owner duyệt theo latestOwner149.
