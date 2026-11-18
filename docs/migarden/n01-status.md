# N01 · Gói app để integration/review

T1 app lead, requested/effective pin `gpt-6.1-sol/max`, làm trực tiếp trong `feat/104-migarden-n01`. Base `79d324fb5ee244a7e01d44d223d8b598e7a80dd8`. Freeze ban đầu `ccfc458b7377e778822fffefc2b99cde48cc8dc4`; bản sửa review là commit chứa tài liệu này và được bind exact SHA vào artifact checksum ở handback. `0021` ban đầu giữ nguyên; bản sửa thêm `0022`. Không push protected branches, merge, production apply hoặc thao tác thiết bị.

Tổng quan/Cấu hình theo ảnh C/E đã chọn, trong app shell hiện có. FastAPI human router tách bearer device router, PostgreSQL/SQLModel config/command/report/session, immutable refs/CAS và Alembic. Controller vẫn chịu clock, safety/journal/budget/deadline/STOP và output. [API](n01-api.md), [54 ca](n01-qa-matrix.md), [run/release/provision/rollback](n01-runbook.vi.md).

| Gate/bằng chứng | Kết quả local trước refreeze | Giới hạn |
|---|---|---|
| Non-PG full sau sửa review | 1575 PASS, 1 SKIP | Thêm test commissioning sau lần này: đã chạy targeted; final CI phải kiểm toàn bộ. |
| Frontend unit/lint | 440/440 PASS, lint PASS | Full browser/runtime riêng. |
| Targeted N01/refinement | 36/36 PASS; profile offline synthetic 2/2 PASS | Không substitute toàn full-PG. |
| Forward rehearsal | DB mới đi `0021→0022`, CAS issue/revoke/rotate/audit/unknown guards PASS | Credential production thực chưa tạo/apply. |
| Bootstrap | Intentional broad UPDATE/DELETE detected → bootstrap restore → role app denied, repeat PASS | Chỉ throwaway local. |
| Migration drift/drop guard | Empty/PASS; additive0022 roundtrip riêng đã thử local | Không downgrade hoặc migrate production. |
| Wire vectors | 14/14 khớp, version/root không đổi | Parent bind final firmware revision/runtime. |
| Full Playwright ban đầu | 483 PASS / 57 SKIP / 2 FAIL trên 542 ca | Không gọi toàn suite PASS. |
| Đối chứng hai ca Private | candidate2/2 và unchanged base2/2 PASS | Original traces chỉ thấy GET /404; root cause chưa đủ chứng minh. |
| Full app N01 trước refinement | 1/1 hành trình PASS với API+PG thật và synthetic reports; phone390 không overflow | Screenshot không proof physical device. Bản sửa Recent có thêm assertion. |
| Full PG native | 617 PASS / 33 FAIL / 54 SKIP, 704 ca | Failure đầu: downgrade guard còn Mimi conversation; có provider event-loop/errors. Không tự phân loại pre-existing hoặc sửa Mimi. |
| Full PG Linux attempts | Tooling mismatch loopback hoặc Git metadata, đã giữ raw receipts | Không giảm immutable SHA guard hoặc bỏ gate. Canonical CI Migration QA ở final PR vẫn required. |
| Workflow/QA-cell | 9/9 và80/80 PASS | Không phải release approval. |
| Runtime image/no-dev | Initial candidate build/probe PASS; final image tạo mới theo freeze | Windows dist ZIP và Linux image dist có checksum riêng, không coi byte-identical. |
| Packaging | PWA/runtime intentional canary FAIL → restored PASS | Seed/test/provision commands chỉ ở source/tooling, không final image/PWA. |
| Secrets/hooks | Selected source/history no leaks; all-files hooks PASS trước fixes, hook commit sẽ kiểm delta | Không disable scanner hoặc copy private payload. |

F1–F5/F7 đã có code + regression theo phạm vi review. F6 giữ fail-closed, giới hạn và recovery cần bằng chứng/Owner grant ghi trong runbook; không có reset/bypass. STOP poison recovery không ACK invalid, không grant; unknown boot chỉ nhận STOP tạm và phải có provenance mới xét OPEN. `stop_unconfirmed` giữ chặn cho tới correlated positive report. Applied/forecast không lấy unordered snapshot.

Parent giữ độc lập review, integration, board/COM/private profiles/TLS, CI acceptance. Physical iPhone, nút/driver/power/flow/AP/WAN và production vẫn NOT_RUN trong app author lane. Cost/tokens USD của model không có instrumentation; không gọi provider sản phẩm trả phí. Mọi local DB/artifact/task resource được ghi ở private author report, tách resources PM.
