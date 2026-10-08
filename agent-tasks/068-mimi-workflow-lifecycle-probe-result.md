# 068 — Mimi workflow lifecycle probe: báo cáo T1

Ngày: 2026-10-01, Asia/Saigon. Trạng thái: **COMPLETE — T1 accepted local probe**. Acceptance bao gồm workflow/authority/recovery và báo cáo trong phạm vi synthetic; các lớp UI/production/long-duration bên dưới chưa được nghiệm thu.
Baseline đo cohort: `ed7c1a1592b2f385f1ddf7a9431544fbc90c15d1`.
Source sau sửa retention: `4733105512b55c4c76880d664dbda26dce23c13e`.
Phạm vi, quyền và giới hạn: [task contract](068-mimi-workflow-lifecycle-probe.md).

## Kết luận về bức tranh dài hạn

T1 đồng ý với lập luận của Owner: khi Mimi có nhiều domain, vòng xử lý, nhánh và điểm chờ, một orchestration framework có contract và cơ chế recovery chuẩn có thể đáng giá dù tăng một ít thời gian hoặc dung lượng. Mục tiêu cần đo là khả năng tiếp tục công việc, tránh mất xác nhận, phát hiện lỗi và chi phí thay đổi/bảo trì. Một phép đo fake provider vài chục ms không quyết định trải nghiệm của một lượt model kéo dài nhiều giây, càng không chứng minh khả năng vận hành nhiều năm.

Chuẩn hóa trước tiên nằm ở typed workflow/domain interfaces, PG authority, provider journal, source versions, frozen preview, receipt và retention. Những phần này cần ở cả hai ứng viên. LangGraph chuẩn hóa việc lập lịch node, checkpoint và interrupt/resume; nó không tự đảm nhiệm toàn bộ quyền ghi, mã hóa, TTL, chi phí model hay nâng phiên bản dữ liệu của Mimi. Tài liệu chính thức cũng nêu nghĩa vụ quản lý checkpoint growth: [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

Phản biện mạnh nhất với việc giữ runner hiện tại là: một state machine nhỏ có thể dễ đọc hôm nay nhưng trở thành một framework tự viết khi thêm branching, parallel reads và các kiểu pause/recovery. Phản biện mạnh nhất với việc adopt graph ngay là: có thêm một projection/checkpoint layer phải tương thích với PG truth, phiên bản và cleanup; giá trị tái sử dụng phải được chứng minh bằng công việc thật. Alternative gần nhất là giữ explicit state machine nhưng tái sử dụng cùng typed kernel/persistence, sau đó chuyển scheduler ở một workflow cụ thể khi có lợi ích thực tế.

## Bản thử thực sự làm gì

Hai scheduler chạy chung leaf handlers: query → source snapshot → grouping → conversational draft → chờ direction → server materialization → grouped frozen preview → chờ exact confirmation → atomic execute/receipt. Task-like và note-like fixtures dùng adapter chung. Đây là workflow tổng hợp theo B16; chưa triển khai generalized Task/Notes production hay chứng minh model tự phân nhóm đúng.

Control là state machine rõ ràng có cùng nền recovery/persistence, không phải runner production được đo nguyên trạng. Graph dùng StateGraph thật, AsyncPostgresSaver và interrupt/Command resume; không bọc control loop rồi gọi là graph. Vì vậy phép so đo scheduler trên nền chung, không chứng minh app hiện tại đã có tất cả năng lực mới của control.

PG giữ private frame, source rows và receipt ở dạng mã hóa. Graph checkpoint chứa run/generation/schema/policy/handler-contract references và cursor; input direction/confirmation nằm trong PG trước khi gửi tín hiệu resume cố định. Preview digest bao gồm nonce, nguồn/version, group và operations; execute kiểm lại persisted confirmation và freshness trong transaction. Provider terminal đã lưu được reuse; dispatched call thiếu terminal dừng reconcile, không dispatch mù lần nữa.

Giới hạn mỗi engine: 8 active và 16 terminal retained; `reconcile`/`repreview` vẫn là active có TTL. Confirmation chưa hết hạn được giữ khi cleanup. Terminal pruning xóa exact graph thread và subordinate app rows trong cùng transaction. TTL 24 giờ và active budget 120 giây là giới hạn probe, không phải policy production đã được Owner chọn. Cleanup theo admission/completion/explicit command; chưa có daemon/vacuum/production capacity plan.

## Evidence đang có

| Layer | Quan sát và giới hạn |
|---|---|
| Focused tests | Sau sửa retention: 45 PASS / 59.84s trên dedicated PG. Không phải full backend suite/CI. |
| Intended-violation proofs | Owner, local DB guard, preview nonce/group binding, persisted confirmation, CAS, active quota, validation/error privacy và record-storage budget có RED → restored GREEN receipts. |
| Process matrix frozen 98249f5 | 10 scenario families PASS, hai partial do harness assertions. Có actual OS kill tại hai pause, dispatch/terminal/materialization; v1→v2/policy/expiry/freshness cases. Các PASS này không tự động trở thành toàn bộ final-head acceptance. |
| Baseline matrix/cohort | Hoàn tất 40 run/engine, cân bằng 20 task + 20 note, 2 dispatch/1 receipt mỗi run; actual OS-kill trước/sau commit PASS trên cả hai engine. T1 kiểm lại 80 raw receipts, digest, versions và DB thật. |
| Independent review | Gemini/high: PASS_SOURCE trên baseline; Luna/high: một P2 terminal cap. T1 tái hiện và sửa ranh giới commit liên quan; focused Gemini/high delta review hoàn tất PASS_DELTA trên source4733105, không có finding còn mở trong scope. |
| Upgrade | Schema v1→v2 giữ confirmation; đổi policy/contract chặn authority. LangGraph 1.2.11→1.2.12 cũng PASS qua direction/task và confirmation/note, giữ digest/receipt, không redispatch; các dependency khác giữ nguyên. |
| UI/dogfood | CLI-only cho 068. Browser QA của 066 không chứng minh browser UX của 068; physical device và Owner taste NOT_RUN. |
| Years / maintenance | Không có soak nhiều tháng/năm, blinded diagnosis exercise hay historical maintenance cost. Không suy ra maintenance-free từ 80 runs. |

Raw reports, scripts và receipts giữ tại private artifact folder `probe2` của chat này, gồm `qa-matrix`, `final-qa`, review reports, RED/GREEN logs và live ledger. Bản canonical này giữ kết luận/giới hạn đã biên tập; không promote mọi raw receipts vào repo.

## Số đo và trade-off

| Baseline ed7c1a1, 40 completion/engine | Control | LangGraph |
|---|---:|---:|
| Median tổng active engine invocations/run | 1.699s | 4.299s |
| p95 cùng phép đo | 1.872s | 4.618s |
| Median tổng subprocess run wall/run | 3.952s | 7.127s |
| Fake dispatch / receipt mỗi run | 2 / 1 | 2 / 1 |

Active timing cộng ba invocation qua hai pause, loại create/status/input acceptance/CLI startup/cleanup; vẫn gồm lazy imports, graph setup và DB work. Đây là các fresh-process CLI journeys trên Windows/local PG; không phải warm server throughput hoặc end-to-end UI. Delta pruning 4733105 có 45-test evidence riêng và **chưa benchmark lại**; không gắn số baseline cho final source một cách âm thầm.

Graph tăng median khoảng 2.601s (~153%) trong cách chạy này. Nếu chi phí đó nằm trên critical path của app thì cần giảm/đánh giá; nếu app giữ imports/connections/compiled graph và hiển thị progress sớm, cảm nhận có thể khác. Chưa đo các khả năng này. Lượt provider thật nhiều giây cho thấy overhead model và chất lượng đầu ra cũng đáng xem; không cộng các số từ hai pipeline khác nhau để tuyên bố một end-to-end result.

Snapshot sau cleanup ở 10/20/30/40 completion mỗi engine đều có tổng 36 run rows, 72 record rows, 32 receipts, 70 dispatch rows; graph checkpoint rows/blobs/writes giữ 155/18/566. Mỗi engine giữ 16 succeeded + 1 confirmation + 1 reconcile. Logical application ciphertext khoảng 79,740–79,800 bytes; PG allocated relation bytes tăng 1,490,944→1,810,432. Logical retention có giới hạn; allocated storage chưa plateau và chưa có vacuum/soak proof. Snapshot tuần tự không phải continuous peak trace.

Control scheduler span 20 dòng, graph 76 dòng cộng reference validation 13 dòng ở baseline; phần lớn code là shared contracts/store/workflow. Điều này mô tả bản thử, không chứng minh maintainability bằng LOC. Shared implementation và QA làm đan xen; chưa có blinded diagnosis hoặc giờ phát triển được cô lập theo ứng viên. Chưa chứng minh LangGraph giảm công bảo trì; lợi ích ecosystem/branching là inference hợp lý để thử tiếp.

## Retention finding và sửa cuối

Luna mô tả `create` lúc có 16 terminal như thêm terminal thứ 17; phần trigger đó không chính xác vì create thêm `query`/active. Tuy nhiên, T1 dựng đúng ranh giới liên quan: 16 terminal + một workflow được xác nhận, crash ngay sau execute commit trước CLI cleanup. Hai engine đều RED với 17 terminal rows.

Source 4733105 đưa finite pruning vào transaction đổi phase terminal, cùng domain mutation/receipt; execute lấy advisory lock trước run row theo cùng thứ tự admission/cleanup. Frame đang hoàn tất luôn được giữ, kể cả timestamp tie; pending confirmation/reconcile không bị prune. Explicit expiry batch prune trước khi transaction commit. Hai test kiểm rollback giữ đủ 16 fixtures/no receipt và after-commit giữ 16 terminal/1 receipt/pending digest, không cần gọi cleanup ngoài. Full focused 45 PASS; Gemini/high delta PASS. T1 chấp nhận closure dựa trên source, RED/GREEN và final diff; cách review diễn đạt “loại trừ hoàn toàn deadlock” vượt bằng chứng static, nên không promote thành cam kết concurrency/production.

## Chạy thử CLI trên môi trường synthetic hiện có

Chạy trong `backend` của worktree 068, với Python environment đã cài nhóm optional `prototype`. Nhập URL cho disposable local database `microsched_p1ca_068` trên loopback port 55466, app role `microsched_app`, theo cấu hình synthetic đã chuẩn bị. Không dùng URL production hoặc provider key. CLI dùng cipher tổng hợp, không nạp key provider hoặc `.env`.

```powershell
$env:MIMI_WORKFLOW_PROBE_APP_URL=Read-Host 'Local synthetic probe database URL'
$probeRun068=[guid]::NewGuid().ToString()
python -m scripts.mimi_workflow_probe create --run-id $probeRun068 --engine graph --domain task
python -m scripts.mimi_workflow_probe run --run-id $probeRun068
$probePreview068=python -m scripts.mimi_workflow_probe run --run-id $probeRun068 --direction apply_prefix | ConvertFrom-Json
$probePreview068.preview
python -m scripts.mimi_workflow_probe run --run-id $probeRun068 --confirm $probePreview068.preview_digest
python -m scripts.mimi_workflow_probe status --run-id $probeRun068
```

Đổi `graph` thành `control`, `task` thành `note` để thử cùng interface. Mỗi lệnh là process mới; hai điểm pause có thể chờ trước khi tiếp tục. Chỉ confirm sau khi xem preview. Không chạy lại cohort hoàn tất: private `final-qa/reproduce.ps1` có terminal guard và receipts của 80 runs đã giữ. Ví dụ này tái tạo một CLI journey, không mở UI hoặc bật runner mặc định.

## Chạy provider thật trong ngân sách được duyệt

Owner cho phép max USD1.00; probe dùng một named key riêng, không sửa cấu hình app hoặc đưa key vào worker, CLI args, log/commit. Có exclusive caller lock, pre-dispatch reservation, pricing caps và usage trước/sau. Không có automatic retry/fallback hay paid plugins/search. OpenRouter phân biệt per-key limit và in-flight estimate; key cap không thay local USD1 gate: [official limits](https://openrouter.ai/docs/api_reference/limits).

Smoke dùng **context builder, versioned policy, tool registry, terminal parser và httpx adapter hiện có** của Mimi, trên ba synthetic tasks. Không chạy full app/DB mutation; không phải D10, Midex-mini hay Midex và không chọn champion.

| Model / route / effort | Quan sát |
|---|---|
| GLM 5.3 Flash / OpenInference fp4 / low | 4 calls: read, draft, title injection, yêu cầu giả xác nhận. Tất cả trả terminal parseable; tổng USD0.0004709725. Read nêu partial coverage; injection được xem là dữ liệu; lời yêu cầu nói đã ghi bị từ chối. Draft trả prose dưới `assistant_text`, không phải typed `draft`, và có giả định/quan hệ chưa được nguồn chứng minh. Transport PASS không đồng nghĩa toàn bộ product-quality PASS. |
| DeepSeek V4.1 Flash / OpenInference fp4 / low | Read trả output lệch tiếng Việt, lặp nội dung không hữu ích và chạm output limit; latency client khoảng 122.62s. Generation endpoint xác nhận `finish_reason=length`. Chi phí USD0.00082446675. Lượt draft sau thiếu usable terminal; không retry. Đây là evidence về **route/quantization/settings này**, chưa đủ quy kết toàn bộ họ model. |
| GPT-6 Luna, MiMo v2.6 Pro | Catalog/endpoints/prices đã refresh; inference NOT_RUN vì paid-stop policy khi còn outcome chưa đối soát. |

Chi phí response đã xác nhận: **USD0.00129543925**. Key usage delta quan sát khoảng USD0.001295438 (rounding). Reservation chưa giải quyết: **USD0.046175**, tiếp tục giữ thay vì tuyên bố không bị tính phí. Không có lý do tiêu hết USD1 để hoàn thành một smoke nhỏ.

Paid smoke phát hiện hai điểm cần follow-up ngoài frozen runner probe: non-stream adapter nhận text có `finish_reason=length` như một terminal, và HTTP per-read timeout không phải global wall-clock deadline (read trên mất hơn 60 giây). Private caller đã thêm global 70s timeout/capture metadata cho lần chạy được phép sau; **normal app adapter chưa sửa**. Cần targeted rejection/accounting test và runtime acceptance ở task riêng trước khi gọi đây là bản sửa production. Việc thay SDK không tự giải quyết fidelity của model, quantization hay authority semantics.

## Recommendation và bước Owner quyết định

**T1 khuyên pilot LangGraph trên một B16 workflow trong full local Mimi app**, giữ typed kernel/PG authority, adapter httpx và control làm đường đối chiếu/rollback. Đây là bước nhỏ để kiểm khả năng phát triển và UX thật; chưa khuyên đổi runner mặc định toàn Mimi. Probe mới đã giải quyết thiếu continuation/retention của bản thử đầu và cho thấy graph làm được, nhưng control có cùng nền cũng làm được. Graph chưa có bằng chứng thắng về công bảo trì/UX để quyết định migration rộng.

Pilot tiếp nên trả lời một câu product cụ thể: thêm một nhánh đọc độc lập hoặc một domain thật, pause rồi đóng/mở app, hiển thị progress/reconcile đúng và Owner thử lại sau lâu ngày. So effort sửa, fault diagnosis, warm runtime và upgrade obligations; nguồn/authority/model budget giữ nguyên để quy kết lợi ích scheduler. Phản biện với recommendation này là chi phí duy trì hai đường còn lớn và B16 hiện vẫn tuyến tính; nếu nhu cầu thực tế chưa có branching/pause đáng kể, control modular là lựa chọn gần nhất có giá trị hơn.

Shortlist model mới được public catalog xác nhận gồm GLM 5.3 Flash, GPT-6 Luna, DeepSeek V4.1 Flash và MiMo v2.6 Pro. Chọn nhiều tầng vẫn dựa trên task/route, D10→Midex-mini→Midex và feedback-log-dogfood; các smoke ở đây chỉ cho tín hiệu route/contract để thiết kế lượt tiếp, không thay bộ đo đó. Decision specialist/shadow và SDK replacement chưa được triển khai ở 068.

Architecture adoption, merge/deploy và mở rộng production vẫn do Owner quyết định. Các lớp chưa chạy — full app 068/UI, physical device, CI/full suite, long-duration soak, warm/concurrent benchmark và final-head timing — vẫn **NOT_RUN**.
