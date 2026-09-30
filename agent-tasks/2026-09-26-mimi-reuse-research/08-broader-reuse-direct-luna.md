# Rà soát reuse ngoài Mimi — 2026-09-26

Phạm vi: rà soát kiến trúc microSched ngoài riêng Mimi, tập trung cron timer, lưu feedback, ICS, PWA/offline và các seam Mimi liên quan để làm đối chứng. Đây là tư vấn chỉ đọc; không sửa kiến trúc, cài thư viện, chạy test, gọi API, dùng khóa hay triển khai.

## Kết luận ngắn

**OBSERVED:** MicroSched có một số phần tự xây trùng với cơ chế phổ biến, rõ nhất là parser cú pháp ICS. Tuy vậy chưa có bằng chứng rằng mức bespoke hiện tại làm lệch sản phẩm khỏi giá trị người dùng. Các phần tự xây lớn nhất đang gắn với invariants riêng: lịch nhắc theo tracker/subscription, offline capture với undo/idempotency, và luồng Mimi có xác nhận/reconcile. Đặc biệt, outbox offline là hướng thiết kế/seam; không thấy implementation outbox hay import Dexie trong frontend source được rà soát.

**INFERRED:** Ba ứng viên đáng điều tra nhất là parser ICS, lựa chọn data/mutation layer khi triển khai outbox, và mức độ dùng APScheduler cho scheduling plumbing. Không có ứng viên nào đủ bằng chứng để đề xuất thay trực tiếp. Cần chứng minh parity cho semantics và failure cases trước.

## Watchlist xếp hạng

### 1. Parser ICS — cơ hội reuse cụ thể nhất; blast radius vừa

**OBSERVED — repo:** [backend/app/core/ics.py](../../backend/app/core/ics.py) tự xử lý giới hạn payload 1 MiB và 5.000 VEVENT (dòng 8–9), unfolding (77), unescape (90), property extraction (107), datetime/TZID (120–153), rồi parse event (156 trở đi). Parser hiện loại RRULE/RDATE/EXDATE/DURATION (dòng 28, 40, 182–198), từ chối TZID (134–135, 197–198, 216–217), và chuẩn hóa/đặt duration/dedupe theo chính sách riêng.

**Ứng viên reuse:** thư viện Python [`icalendar`](https://icalendar.readthedocs.io/en/latest/usage.html) (usage docs về parsing iCalendar/timezone), cùng chuẩn [RFC 5545](https://www.rfc-editor.org/info/rfc5545/) định nghĩa format iCalendar. Tra cứu nguồn: 2026-09-26. RFC là chuẩn gốc; thư viện là implementation tham khảo, không bảo đảm semantics khớp microSched.

**Lợi ích có thể đo:** giảm code parser protocol-level tự duy trì; giảm lỗi tương thích với content lines, escape, parameter và ngày giờ; đo bằng số dòng parser/protocol tests chuyển sang thư viện, differential fixtures từ exporter được phép dùng, và lỗi import còn lại sau corpus run.

**Chi phí và fit:** chỉ thêm dependency backend, không thêm process/provider; Neon/Fly topology không đổi. Cần đo image/RAM dưới giới hạn Fly 512 MB. Blast radius vừa vì import tạo event và cách báo event bị skip có thể đổi dữ liệu. Cần giữ giới hạn bytes/events, reject/skip policy, timezone Việt Nam, default-duration, duplicate rule và thông báo an toàn. Recurrence/TZID support không đồng nghĩa được phép tự động chấp nhận các event này.

**Đánh giá:** ứng viên số 1 cho differential spike/fixture audit nếu Owner muốn đầu tư vào interoperability. Chưa khuyến nghị thay parser khi chưa xác nhận parity chính xác.

### 2. Offline capture/outbox — khảo sát lúc triển khai, chưa phải duplication đã xảy ra

**OBSERVED — repo:** [docs/frontend-brief.md](../../docs/frontend-brief.md) dòng 16, 30, 46–50 ghi nhận Dexie + outbox tự viết là lựa chọn dự kiến; rationale là client UUIDv7, server idempotency/soft-delete, một người dùng và tránh thêm sync service. [docs/tracking-brief.md](../../docs/tracking-brief.md) dòng 150 nêu offline undo và khác biệt giữa item chưa sync/đã sync. [frontend/src/tracker-ui.ts](../../frontend/src/tracker-ui.ts) và [frontend/src/subscription-ui.ts](../../frontend/src/subscription-ui.ts) chỉ đánh dấu mutation seam dành cho outbox 017. `dexie` nằm trong [frontend/package.json](../../frontend/package.json), nhưng không thấy import Dexie trong `frontend/src` lúc rà soát; không quan sát thấy outbox đã được xây.

**Ứng viên reuse:** TanStack DB có collection/query/mutation và optimistic transaction. Tài liệu hiện hành: [Overview](https://tanstack.com/db/latest/docs/overview) và [Mutations](https://tanstack.com/db/latest/docs/guides/mutations), truy cập 2026-09-26. Tài liệu cảnh báo transaction completion tự nó không chứng minh backend đã xác nhận nếu handler không đợi acknowledgement/read-back. Tài liệu hiện đánh dấu DB beta; kiểm tra lại trạng thái trước quyết định.

**Lợi ích có thể đo:** khi task offline bắt đầu, so số dòng retry/transaction/state tự viết, số trường hợp lỗi và thời gian bảo trì với TanStack DB. Đánh giá trên cùng tình huống: offline reload, UUID collision/idempotent retry, undo trước/sau sync, timeout có kết quả không rõ, retry và restore state.

**Chi phí và fit:** TanStack DB không buộc thêm backend service cho kiểu Query collection; có thể giữ một FastAPI process, cùng origin và Neon. Adapter, UUID semantics, API retry, offline bootstrap, cache lifetime/purge và server confirmation vẫn cần code/hợp đồng microSched. IndexedDB lưu private data nên cần rà lifecycle/privacy. PowerSync/ElectricSQL/RxDB sync stack không phải thay thế ngang giá: giải quyết replication/conflict/sync rộng hơn, có thể thêm service/provider và chi phí không tương xứng với một người dùng, Fly 512 MB, Neon và mục tiêu một process.

**Đánh giá:** khảo sát lựa chọn lúc task offline bắt đầu; chưa thể gọi outbox là “reinvented wheel” khi implementation chưa có. Giữ parity UUIDv7, soft-delete undo và phân biệt acknowledged/unknown trước khi chọn abstraction.

### 3. Cron timer — code bespoke lớn nhưng thay thế có rủi ro cao

**OBSERVED — repo:** [backend/app/core/cron_timer.py](../../backend/app/core/cron_timer.py) định nghĩa `CronTimer` từ dòng 153; dùng heap/snapshot (snapshot logic quanh dòng 529–570); dùng PostgreSQL advisory lock để fenced ownership (hằng số dòng 59–61, acquire quanh 277–319); quản lý stale recovery, provider workers và shutdown. [docs/architecture-brief.md](../../docs/architecture-brief.md) dòng 48, 146 ghi quyết định dùng timer trong process, thay external scheduler để bỏ external target và giữ single-process always-on hosting.

**Ứng viên reuse:** APScheduler hỗ trợ `AsyncScheduler`, persistent data store và PostgreSQL ([User guide](https://apscheduler.readthedocs.io/en/master/userguide.html), [API](https://apscheduler.readthedocs.io/en/master/api.html); truy cập 2026-09-26). Có nhiều thế hệ API; cần pin version và đọc docs tương ứng trước spike.

**Lợi ích có thể đo:** giảm code wakeup/schedule bookkeeping, lỗi lịch tổng quát và diện tích bảo trì; đo bằng phần code thực sự bỏ được, behavior matrix và semantics vẫn phải bọc lại. Không tính giảm tổng LOC nếu domain dispatch, locking, catch-up, batching vẫn phải tồn tại.

**Chi phí và fit:** có thể cùng process và dùng PostgreSQL store, nhưng persistence có thể thêm kết nối/truy vấn và memory. Cần đánh giá Neon idle/wake, connection limits, Fly RSS, single-process ownership và deploy/restart. Blast radius cao: lịch nhắc có thể trễ/trùng/mất. APScheduler không tự thay recurrence domain helpers, idempotency ledger, one-shot catch-up, push outcome ambiguity, tracker batch hoặc lock-fencing.

**Đánh giá:** nghiên cứu có điều kiện, xếp sau ICS và outbox. Không khuyến nghị thay timer nếu chưa map từng invariant và chứng minh không làm tăng DB wakeups hoặc độ trễ.

## Hai seam bespoke có lý do hiện tại

1. **Mimi domain/orchestration.** [backend/app/web/routers/mimi.py](../../backend/app/web/routers/mimi.py) có SSE stream (dòng 245–305), resume/reconcile (314 trở đi; reconcile route quanh 376), và change-set decision với Idempotency-Key (466–476). [backend/app/agent/service.py](../../backend/app/agent/service.py) có confirm/change-set (khoảng dòng 2039) và reconcile unknown run (khoảng dòng 2630). Đây là quyền thực thi, preview/confirm, unknown-result reconciliation và dữ liệu riêng tư — phần có giá trị sản phẩm và học AI engineering. LangGraph có checkpoint/interrupt/HITL ([tài liệu](https://docs.langchain.com/oss/javascript/langgraph/thinking-in-langgraph), truy cập 2026-09-26), nên đáng làm comparator nếu state-machine maintenance đo được là gánh nặng; nhưng framework không thay hợp đồng transaction/privacy/idempotency. **Inference:** rewrite sang framework có thể thêm abstraction/dependency mà vẫn phải giữ nhiều policy code; chỉ cân nhắc khi đối chiếu run disconnect/resume, confirmation, replay, unknown reconcile và durable state.

2. **EncryptedReviewStore.** [backend/app/agent/feedback_store.py](../../backend/app/agent/feedback_store.py) tự lưu bundle/feedback mã hóa, có kích thước cap (dòng 32–36), idempotency (65, 97), pending recovery (180 trở đi) và atomic write (216). Docstring nói đây là store synthetic-only, P0 không đăng ký runtime route (dòng 32–33). **Inference:** với scope tooling/evidence tách biệt, triển khai nhỏ này tránh đưa evidence test vào Neon/runtime path và có lifecycle riêng; chưa thấy lợi ích rõ khi thay bằng database abstraction. Rà lại nếu nó thành runtime, giữ dữ liệu thật, hoặc store file nhân rộng đáng kể.

## Đánh giá câu hỏi “có đang phát minh lại bánh xe và lệch product value không?”

**OBSERVED:** ICS parser là phần trùng rõ nhất với chuẩn/thư viện có sẵn. Timer là code tự quản lớn nhưng đã được chọn vì topology one-process và chứa domain workflow. Outbox vẫn là kiến trúc dự kiến. Feedback store có phạm vi synthetic-only. Mimi orchestration tự sở hữu các chính sách confirm/privacy/reconcile.

**INFERRED:** nguy cơ lệch product value không đến từ “custom” tự thân, mà từ duy trì parser chuẩn tổng quát hoặc scheduling plumbing mà không tạo trải nghiệm/invariant riêng. Điều tra ICS trước; thiết kế outbox bằng phép so sánh ngang khi implementation khởi động; giữ timer/Mimi bespoke đến khi đo được chi phí bảo trì lớn hơn chi phí framework.

Không nên kết luận “framework phổ biến hơn nên tốt hơn”; không đưa khuyến nghị hard replacement trước exact invariant parity.

## Cues repo đã kiểm tra

- `docs/project-guide.md`: app một người dùng; modular monolith FastAPI, PostgreSQL/Neon, React/TypeScript/Vite PWA; một Python process serve API và frontend; hosting hiện thời cần re-query trước quyết định vận hành.
- `backend/pyproject.toml`: không có APScheduler hoặc icalendar dependency ở backend.
- `frontend/package.json`: có Dexie, TanStack Query, vite-plugin-pwa; không có `@tanstack/react-db`.
- `backend/app/core/cron_timer.py`, `backend/app/core/ics.py`, `backend/app/agent/feedback_store.py`, `backend/app/agent/service.py`, `backend/app/web/routers/mimi.py`.
- `docs/architecture-brief.md`, `docs/frontend-brief.md`, `docs/tracking-brief.md`.

Nguồn ngoài được tra cứu ngày 2026-09-26; URLs ở trên là tài liệu chính thức hoặc RFC. Chưa kiểm tra benchmark RSS, Neon wakeups, runtime/production behavior hay exact invariant parity. Status: advisory shortlist, not implementation approval.
