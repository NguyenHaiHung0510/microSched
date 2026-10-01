# 073 — B16 local pilot: kết quả và hướng dogfood

Ngày: 2026-10-01. Trạng thái: **COMPLETE_LOCAL_DOGFOOD_READY** — T1 chấp nhận đúng phạm vi pilot local sau QA và đối chiếu review. Đây là báo cáo local synthetic; chưa phát hành, merge, deploy hay quyết định chuyển kiến trúc mặc định.

## Kết quả đã có

Pilot đã nằm trong full local Mimi, dùng Task thật của ứng dụng trong database synthetic riêng. Có hai engine LangGraph/Control trên cùng domain handlers, HTTPX và PostgreSQL authority. Luồng: chọn Task → nhóm → bản nháp → duyệt hướng → xem từng cặp trước/sau → xác nhận đúng preview → ghi atomic và biên nhận. Thao tác được giới hạn ở thêm `[planned] ` vào title, giữ nguyên phần còn lại.

Quyền ghi thuộc máy chủ: source fingerprint, owner, generation, expiry, digest và transaction. Bản nháp model là lời tư vấn. Title không tin cậy không được cấp quyền hay biến thành thao tác. Pilot mặc định tắt và chỉ chạy trên database local được định danh; không bật provider hay cron của ứng dụng chính.

## Bằng chứng QA

| Lớp | Kết quả | Giới hạn |
|---|---|---|
| Workflow/Postgres | 80 PASS, 306,57 giây | Pilot, HTTP, review regressions, store/lifecycle/contracts; không phải toàn bộ suite PG của sản phẩm. |
| Backend ngoài PG | 602 PASS, 1 skipped, 287 deselected | Receipt trước request-builder cuối; builder mới có lượt 8 PASS riêng tại commit được review. |
| Request contract | Intended RED: 2 lỗi đúng mục tiêu, 6 PASS; restored GREEN: 8 PASS; final-source GREEN: 8 PASS | Kiểm enum Task ID và số nhóm thật; không chứng minh model luôn tuân thủ prompt. |
| Frontend | 24 files / 172 PASS; lint PASS | Có lượt chạy cuối sau chỉnh nhãn/loading. Lượt sandbox EPERM được giữ riêng, không đổi thành PASS. |
| Build/PWA | PASS bản cuối `cc37f0b`, asset `app-3lrIxJ1T.js` | Kiểm Apple icon/PWA surface PASS; warning chunk lớn còn được ghi nhận. |
| Browser | Đủ 6 scenario có final PASS evidence | Giữ matrix đầu 4 PASS / 1 FAIL / 1 NOT_RUN; rejected409 đạt qua hai tab UI thật, lost-response đạt bằng nút recovery thật do T1 chạy. Không hồi tố kết quả ban đầu. |
| Restart app và PG | PASS restart thật, không xoá volume | Run Graph giữ UUID/generation/preview/digest/provider count; sau restart xác nhận đổi đúng 1 Task, receipt ổn định. |
| Provider thật | Một MiMo Graph run hoàn tất với 2 calls, tiếng Việt mạch lạc, exact confirmation, 2 Task đúng và biên nhận | Một case synthetic; không phải champion, ranking, hoặc bảo đảm tổng quát. |
| CI, physical iPhone, production | NOT_RUN | Chromium emulation không chứng minh bàn phím, Safari hay thiết bị thật. |

Receipt PG ban đầu `restored-pg-green.txt` là **1 FAIL / 34 PASS**: fixture hết hạn trước khi tới barrier. Đã sửa clock của fixture và chạy regression rồi combined GREEN, được source-bound trong `qa-source-binding.json`. Receipt thất bại vẫn được giữ; không chép lại thành PASS.

## Review và các vấn đề đã xử lý

Review backend ban đầu phát hiện lỗi privacy/source freshness, GET có mutation, replay/admission ordering, identity sau retention, expiry sau lock wait, cancellation và bằng chứng ngôn ngữ/budget. Các thay đổi được giữ trong commit và regression receipts; review recovery Luna/high đã đối chiếu delta.

| Nhóm finding | Disposition trong pilot này |
|---|---|
| BR-01…07: privacy, database namespace, pure GET, replay, retention identity, expiry, lifecycle | Đã sửa trong source được review; các regression thuộc lượt 80 PASS. Không suy ra bảo đảm concurrency/retention nhiều năm. |
| BR-08: predicate bị coi là semantic validator; draft sai/kém | Bỏ claim đó; authority vẫn server-owned, draft advisory. Các draft GLM/MiMo từng bị từ chối vẫn REJECTED; không hồi tố PASS từ case mới. |
| BR-09: ledger thiếu làm mất historical holds | Private caller yêu cầu đủ ledger, giữ unknown reservations, không retry/fallback mù. |
| D01: identity trước restart | Đã fence đủ 5 UUID cũ có receipt trong fixture mới. UUID cũ không được ghi nhận không thể tái tạo từ tmpfs đã mất: generic historical migration UNVERIFIED, ngoài scope fixture mới. |
| D02/D03: lock inversion và unknown outcome bị che | Review recovery đã đóng trên source và bound regression receipts; trạng thái unknown vẫn cần đối soát dù source bị ẩn. |
| UI R1…5 | Pending UUID giữ qua mở history; rejected409 có đường bỏ lựa chọn; cancel/resume theo server capability; reconcile không được coi là terminal để tạo mới. Browser recovery/rejected409 đã có final PASS evidence. |
| D04 | Chỉ thông báo provider uncertainty khi durable reason thật là unknown; stale-source browser đã PASS. |
| Request-builder delta | Independent Luna/high review tại `c2117be7`: không thấy P0/P1/P2 trong ba file. Pure helper chưa được nối vào provider mặc định; review không nghiệm thu integration của helper. |

Hai chỉnh sửa UX cuối chỉ thêm waiting status có `role=status` và làm rõ route của phần hội thoại. Không đổi policy, timeout/retry, engine hay quyền ghi. T1 trực tiếp kiểm diff và QA delta; không gọi đó là review độc lập.

T1 tạo run restart `0ea2ebb3-4c92-4ce8-98d3-96e4d3ca8df2` trong lúc worker còn chạy scenario 6. Run hiện trong shared synthetic history khiến worker dừng đúng ranh giới không thao tác run chưa biết chủ. Đây là lỗi phối hợp QA của T1, không phải bằng chứng product defect. Run đã được T1 hoàn tất sau restart thật; delta riêng giữ matrix cũ nguyên trạng.

Scenario 6 cuối: chọn Task ở tab Mimi đang mounted, xoá đúng Task đó bằng UI ở tab thứ hai, gửi lựa chọn cũ. Backend thật trả `public_source_required`; nút bỏ lựa chọn/tải lại trả selection về 0. Không intercept task-list response hay mock backend rejection. Script capture toàn bộ headers/body trước đó bị automatic approval review từ chối trước execution và đã được bỏ; cách hai tab không thu thập dữ liệu đó.

Worker scenario 5 delta chỉ chứng minh POST 200 và direct GET cùng UUID. T1 bác nhãn PASS cho recovery UI, report được sửa thành `PARTIAL_UI_NOT_RUN`. T1 sau đó chạy đúng một attempt cuối: POST 200 được forward thật rồi mất response; mở history khác; bấm nút **Tải lại trạng thái** của ứng dụng; UI trở về UUID `11e68d1e-2851-4bca-aa6d-c2909043d63c`, xoá pending identity, không có POST thứ hai. Huỷ run qua UI và đọc lại DB xác nhận cancelled, zero write receipt, title nguồn không đổi. Run worker `f3437099-36e4-465e-9742-170bebd56c67` cũng được T1 huỷ đúng scope. Tổng matrix có 8 attempted UUIDs trong cap; các lỗi fixture/locator không gửi POST không được đếm là completed journey.

Hai worker cuối pin `gpt-6-luna`/high qua transport hỗ trợ và được đối chiếu latest `turn_context`; đây là runtime metadata, không phải upstream provider attestation. Không native resume sau cảnh báo đổi model. Worker không có quyền acceptance; T1 đối chiếu source/diff, raw receipts, DB readback và sửa verdict trước khi chấp nhận.

## Model và harness

GLM draft kém trong một route/case không đủ kết luận GLM kém tiếng Việt. Harness đã có lỗi cụ thể: prompt nói cố định hai nhóm trong khi kết quả có thể chỉ một, và schema cho phép strings không phải Task IDs. Request contract mới dùng enum của selection, xác minh partition trước prose và dùng số nhóm thực tế.

MiMo với prose tự nhiên đã trả bản nháp ngắn, đầy đủ tiếng Việt và phù hợp luồng; lượt live cuối giữ một nhóm gồm hai Task, sau đó chỉ ghi khi T1 xác nhận exact preview. Prompt, format và token cap đã thay đổi cùng nhau, nên chưa có phép so causal. GLM matched schema/JSON-object pair chưa hoàn tất: một arm bị chặn trước dispatch. Không lấy OpenRouter/AA index làm điểm task Mimi.

Xem [research đã biên tập](2026-09-30-mimi-research/harness-model-parity-2026-10-01.md). Raw research, source links, request/usage ledgers và returned text được giữ local để đối chiếu. SDK/framework không tự sửa prompt, grounding, route hoặc UI recovery. Khuyến nghị hiện tại: giữ HTTPX và tiếp tục pilot LangGraph trong B16 đã duyệt; chọn model bằng task Mimi/D10/MIDEX-mini khi có scope cụ thể.

## Ngân sách

22 recorded calls/attempts trong tổng ledger: confirmed **USD0.00643043565**; unknown holds **USD0.064526**; conservative accounted **USD0.07095643565**; còn **USD0.92904356435** trong Owner cap USD1. Hai unknown calls không được retry hay giải phóng hold khi thiếu receipt. USD0.50 buffer của key không được tiêu. Đây là ledger của scope này, khác key lifetime usage; không khẳng định hai số phải bằng nhau.

Không gọi provider mới để chạy lại các case recovery/restart. Paid server 8015 đã dừng; preview 8014 dùng provider deterministic. Worker không đọc/use key. T1 giữ toàn bộ credential ngoài prompt/log/commit.

## Cách dogfood sau khi gate đóng

Full local preview tại `http://127.0.0.1:8014`; synthetic QA login qua `/auth/dev-session`. Mở Mimi → Hội thoại → một hội thoại standard → Quy trình Task Mimi. Chọn 1–16 Task công khai, đổi LangGraph/Control để đối chiếu, đọc bản nháp và duyệt hướng, rồi kiểm toàn bộ before/after trước khi xác nhận. Không dùng dữ liệu thật ở preview này.

Lịch sử lưu run live `f079b8a9-e654-4134-97bb-e41a147c6bb9` đã hoàn tất: 2 provider calls, 2 Task đổi, digest `c2a632cea53c3d349e631d1867e76646e196afae7791d76832ce7c92efc4789a`. Đây là sample live được giữ để xem, không phải provider đang chạy. Các run REJECTED/reconcile cũ cũng giữ nguyên, không biến thành sample PASS.

## Khuyến nghị và giới hạn quyết định

T1 khuyến nghị dogfood đúng slice này: browser/restart/build cuối đã đóng trong phạm vi local. Preview đang dùng provider deterministic; sample live đã được giữ trong history, không tự bật paid provider cho lượt Owner thử. Giá trị cần đánh giá là continuity, sửa lỗi, chia domain và khả năng thay phiên bản, không chỉ vài chục ms của probe nhỏ. LangGraph chuẩn hoá orchestration có tiềm năng khi workflows tăng, nhưng vẫn cần owner-bound state, transaction, retention và ứng xử provider do ứng dụng thiết kế.

Phản biện mạnh nhất: custom runner hiện tại ít dependency và đơn giản hơn; với workflow hẹp, chi phí checkpoint/upgrade có thể chưa đem lại lợi ích tương xứng. Phương án gần nhất là giữ runner hiện tại nhưng chuẩn hoá cùng interfaces, replay và lifecycle. Pilot giữ Control để Owner so cùng thao tác và quyết định; T1 không tự chọn framework/model mặc định hay tuyên bố vận hành nhiều năm đã được chứng minh.

Raw receipts và reports lưu trong thư mục private `pilot073`, gồm browser-qa, review reports, RED/GREEN, source-binding, restart và budget ledgers. Chỉ promote bản tổng hợp đã biên tập vào repo; không commit screenshots, credentials, raw billing hay toàn bộ log. Git/CI/runtime/device/production là các lớp riêng.
