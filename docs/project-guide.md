# Bản đồ tài liệu microSched

Đọc theo câu hỏi; source/config và migration là bằng chứng về implementation. Tài liệu không tự cấp quyền chạy command, truy cập dữ liệu hoặc triển khai.

| Cần biết | Nguồn chuẩn |
|---|---|
| Sản phẩm hiện có, phạm vi v2.0 | [README](../README.vi.md), [CHANGELOG](../CHANGELOG.md) |
| Module, API, frontend, offline flow | [Architecture](engineering/architecture.md) |
| Entity, quan hệ, encryption, schema | [Data model](engineering/data-model.md), [reading gates](verification/reading-gates.md) |
| Fresh clone, env, chạy local, lint/test/build | [Development](engineering/development.md) |
| Deploy/release, readiness, backup/recovery, migration | [Operations runbook](operations/runbook.md) |
| Auth/session/private R1–R7 và threat model | [Auth](auth-brief.md), [security baseline](security-brief.md) |
| UI/interaction và artwork được dùng | [UI contract](ui-brief.md), [brand](brand-identity.md) |
| Check layers, QA runners, cases, evidence | [Verification](verification/README.md), [UI QA](qa-framework.md), [agent QA](qa-agent-framework.md) |
| Mimi hiện có và các contract còn hoạt động | [Mimi — PARTIAL](mimi/README.md) |
| Quyền của actor, review, merge | [AGENTS](../AGENTS.md), [harness policy](harness-policy.md) |

Outbox core đã được tích hợp qua [PR272](https://github.com/NguyenHaiHung0510/microSched/pull/272): 11 command Task/checklist/Entry. Các scope offline rộng hơn của bản nháp cũ không phải backlog tự động. Mimi Task/checklist đã được triển khai; trạng thái phát triển của cả module và các giới hạn QA được mô tả riêng.

Task, nghiên cứu, session log và receipt cũ đã commit có thể tra bằng `git log --all -- <path>` rồi `git show <commit>:<path>`. Baseline trước lần sắp xếp này là `48dc397663b145dab35994326af007dd0e26dcc7`; tham chiếu lịch sử phải gắn revision, không dùng làm trạng thái hiện tại. QA hình ảnh/canonical transcript được Owner quản lý trong archive local riêng; xem provenance tại Verification. Repo không phân phối archive cá nhân, backup hay key.
