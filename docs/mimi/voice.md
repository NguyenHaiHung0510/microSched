# Mimi giọng nói

## Voice v1 (mặc định)

Trong hội thoại STANDARD đang mở, chọn **Giọng nói** để mở micro và nói chuyện với
Mimi. Bạn có thể nói tiếp trong khi Mimi đang trả lời. Khi provider báo lượt bị ngắt,
ứng dụng dừng ngay phần âm thanh còn chờ phát. **Tắt mic** giải phóng mic nhưng vẫn
nghe được câu trả lời; **Bật mic** xin lại quyền capture khi cần. **Kết thúc** dừng
capture và playback ngay, sau đó đóng phiên. Đổi hội thoại, đăng xuất hoặc mất kết
nối cũng dừng phiên. Bản nháp text được giữ khi voice lỗi hoặc kết thúc bình thường.
Phiên mới luôn cần một thao tác rõ ràng của người dùng.

Voice chỉ đọc lịch đã lưu, với cùng STANDARD/visibility rules của [Calendar reads](calendar-read.md).
Có thể hỏi một ngày, danh sách ngày, khoảng ngày hoặc chi tiết một event/dấu ngày.
Để chỉnh dữ liệu, kết thúc phiên và quay lại chat text. Voice không tạo preview, không
gọi text model, và không bật Google Search. Thao tác trên mic gửi audio đến Google;
app không lưu PCM. Bản chép lời do provider trả về được mã hóa trong chính hội thoại.
Lượt provider hoàn tất vẫn có thể chưa phát hết âm thanh, ví dụ khi bạn bấm **Kết thúc**.
Nếu provider sinh câu trả lời dở dang, bản đã lưu có nhãn **Bản chép lời chưa đầy đủ**.
Input transcription không có ID để khẳng định provider đã ghép từng đoạn input với
một câu trả lời cụ thể.
Các câu trả lời từ run đọc Calendar có cùng quy tắc đọc lại dữ liệu khi đưa vào lịch sử model.

Mimi kiểm lại các mục lịch ngay trước khi gửi kết quả. Nếu phát hiện mục đã gửi thay đổi
hoặc không còn hiển thị, Mimi kết thúc phiên giọng nói. Một phiên mới có thể đọc lịch
hiện tại; dữ liệu đã gửi hợp lệ trong phiên trước không thể thu hồi.

Để dùng trên một app instance đã được cho phép, đặt `MIMI_VOICE_ENABLED=true` và
`MIMI_CALENDAR_READ_ENABLED=true` trong cấu hình backend, cùng `MIMI_GEMINI_API_KEY`
của instance. Giữ key ở backend, không đặt dưới `VITE_`. Cả hai flag mặc định `false`.
Browser cần HTTPS hoặc loopback, quyền mic, WebAudio/AudioWorklet và WebSocket cùng
origin. Local Vite proxy hỗ trợ WebSocket. Frontend chỉ phát hiện khả năng voice từ
`/api/mimi/capabilities`; cấu hình model text hiện tại vẫn dùng cho chat text.

Backend dùng [Google Live v1beta](https://aistudio.google.com/api-reference/live/bidi-generate-content)
với [`gemini-3.8-live`](https://aistudio.google.com/docs/models/gemini-3.8-live) và
giọng dựng sẵn [Kore](https://aistudio.google.com/docs/live-api/capabilities#change-voice-and-language).
Phiên trả lời bằng audio, tối đa 2.048 token cho mỗi response; mặc định nói tiếng Việt
và theo ngôn ngữ của người dùng khi đổi ngôn ngữ. Google nhận biết lượt nói tự động.
Browser gửi PCM mono 16 kHz và phát PCM mono 24 kHz. Audio còn chờ phát có giới hạn.
Ticket sống 30 giây và dùng một lần; phiên mặc định tối đa 300 giây, có thể cấu hình
`MIMI_VOICE_MAX_SECONDS` trong khoảng 30–600. Voice gửi một cửa sổ nhỏ gồm các tin
nhắn gần đây; không đưa nguyên lịch sử dài sang Google. Có giới hạn PCM, số tool
calls, kích thước Calendar result và bản chép lời. Nếu một Calendar result vượt giới
hạn, Mimi cần đọc ít ngày/nhóm hơn. Sau khi kết nối bị ngắt, receipt giữ trạng thái
chưa xác định khi thiếu kết quả cuối; usage Google được lưu theo mẫu nhận được và
không được cộng đoán thành chi phí. Voice không có text Resume/Reconcile.

Tắt `MIMI_VOICE_ENABLED` để rút tính năng. Bản chép lời đã lưu vẫn đọc được, không cần
migration. Browser có thể phát hiện giới hạn quyền mic hay mạng khác nhau theo thiết
bị; kết quả đối với model thật và thiết bị vật lý cần được kiểm riêng.

## Voice v2 (B1+B2, bật riêng)

Voice v2 dùng `MIMI_VOICE_V2_ENABLED=true` cùng các điều kiện của v1.
Preset production của đợt này bật v2; local/test mặc định tắt. Tắt flag để ticket mới dùng v1. Không cần
migration. Ticket vẫn chỉ dùng một lần, gắn với login session đã tạo nó, kể cả
khi hai login được phép cùng đọc một hội thoại. Deadline 90 phút tính một lần
từ lúc cấp ticket, không tăng khi reconnect. `MIMI_VOICE_V2_MAX_SECONDS` nhận
30–5.400 để thử deadline ngắn. Giọng Kore và provider của v1 giữ nguyên.

Nếu upstream Google đóng hoặc gửi GoAway khi browser và mic vẫn hoạt động, backend
thử kết nối lại trong cùng cuộc gọi. [Native Live resumption](https://aistudio.google.com/docs/live-api/session-management)
chỉ dùng handle mới nhất đủ điều kiện trong bộ nhớ. Khi không còn handle an toàn
hoặc dữ liệu nguồn đã đổi, một kết nối mới có thể tiếp tục cuộc gọi nhưng không
mang theo ngữ cảnh model cũ. Backend không gửi lại audio, seed hay thao tác cũ.
Giới hạn: tối đa 13 lần mở upstream trong cuộc gọi và 3 lỗi liên tiếp. Mic bị
mất, browser disconnect, logout, đổi hội thoại hoặc Stop dừng cuộc gọi. Không tự
gắn lại browser. Chủ động mute có thể nghe tiếp, nhưng không tự mở upstream mới
khi mic đang mute. PCM đi trong cửa sổ quyền ngắn còn hiệu lực; reconnect, nguồn,
preview và ghi dữ liệu được kiểm lại tại các ranh giới tương ứng.

Đọc và đếm Task, đọc nội dung/checklist, chọn Task và đọc Calendar dùng tool
STANDARD sẵn có. Tool chỉ có quyền đề xuất. Một lệnh nói đủ rõ và khớp toàn bộ
transcript hiện tại có thể áp dụng tối đa 5 Task tạo/sửa có thể hoàn tác trong
một giao dịch, ví dụ: “Tạo việc nộp bài hạn ngày mai” hoặc “Hoàn thành việc A và B”.
Lệnh 6 Task trở lên tạo một preview cho toàn bộ tập được xác định. Nếu thiếu bằng
chứng ghép lượt, nội dung khó đối chiếu, nguồn đổi hoặc thao tác có hiệu ứng như
xóa/khôi phục/nhắc, Mimi không tự ghi; xem preview hợp lệ và Confirm trong app.
Nếu đề xuất thiếu một phần của danh sách hay sai Task được gọi tên, Mimi yêu cầu
làm rõ; không tạo preview cho phần thiếu. Luồng nhanh đối chiếu các lệnh nói trực
tiếp có đích và thay đổi rõ (tên, ngày đơn giản, hoàn thành/mở lại, ưu tiên, đổi
tên). Những thay đổi cần suy diễn hoặc soạn nội dung vẫn đi qua preview.
Lệnh “hoàn tác cái vừa làm” chọn receipt mới nhất trong chính hội thoại, kể cả
receipt Chat hoặc receipt từ cuộc gọi trước. Nếu receipt đó không đủ điều kiện,
Mimi báo chưa hoàn tác và không tìm lùi. Voice chỉ tự hoàn tác thay đổi an toàn,
có đích rõ, không có side effect reminder và phiên bản nguồn còn khớp; trường
hợp cần quyền tay tạo preview. Lệnh Undo rõ ràng trong Chat luôn tạo preview dùng
cùng receipt; không gọi provider để đoán phương án ngược.

`GET/PATCH /api/mimi/voice-preferences` dùng session và CSRF khi ghi, với
`{"fast_apply": true|false}`. Mặc định true; tắt thì thao tác đề xuất đi qua
preview và Confirm. Cài đặt là của Voice; Chat giữ quy trình xác nhận hiện tại.
Transcript vẫn lưu mã hóa trong hội thoại. Phiên mới dùng một cửa sổ giới hạn
gồm lời nói/tin nhắn, phản hồi hoàn chỉnh không dựa trên tool và trạng thái
preview/receipt. Phản hồi dựa trên nguồn và transcript dở dang dùng marker
yêu cầu đọc lại. Setup giới hạn riêng 64 KiB, lịch sử 32 KiB; chỉ gửi message
đầy đủ. Context compression mặc định bật (25.000 xuống 8.000 token); có thể tắt qua
`MIMI_VOICE_V2_COMPRESSION_ENABLED`.

WebSocket báo `reconnecting`, `resumed` (có thêm `context_retained`) và
`action_updated` với `status`, mã `reason` và `message` cố định. Các trạng thái
`preview`, `applied` và `undone` chỉ đến sau commit; `rejected` và
`needs_clarification` giải thích vì sao ứng dụng không thể báo thành công.
Lượt tự ghi yêu cầu VAD bắt đầu/kết thúc trong PCM mới và final
`inputTranscription` của toàn câu. Các sự kiện có thể đến độc lập. Final không
cần offsets hay `finished`; offsets nếu có phải khớp. Interim, lượt đã hết
cửa sổ, final chồng lấn, lời mới, hủy hoặc replay không cấp quyền ghi.
Action tools khai báo `BLOCKING`: một `toolResponse` với call ID đúng chỉ
được gửi sau khi Server xác định kết quả; Gemini có thể nói ngắn theo kết quả
đó. Nếu commit làm dữ liệu đã gửi không còn khớp, Server cập nhật UI bằng trạng
thái thật, đổi upstream và chỉ gửi trạng thái scalar làm context. Nó không
chèn một lượt nói mới đè lên micro.
Browser gửi `{"type":"microphone_lost"}` nếu mất capture ngoài ý muốn.
Ca v1 dừng sau 34,263 giây có mã gộp browser/provider nên không xác định được
nguyên nhân vật lý. V2 ghi riêng lý do browser, upstream, mic, deadline và Stop.
Khả năng tương quan lời nói của Gemini thật, chất lượng câu trả lời và mic thật
cần được Owner nghiệm thu riêng; kết quả provider giả chỉ xác minh hợp đồng app.

### Receipt, diff và dấu ngày

Mỗi commit ghi một Server message được liên kết với run, change set và receipt
chính xác. `messages[].applied_receipt_id` dùng để mở
`GET /api/mimi/receipts/{receipt_id}/diff`. Kết quả chứa
`{receipt_id, plan, undo_available, executed_at}`; plan là snapshot thực tế
trước/sau commit, kể cả khi một chỉnh sửa STANDARD sau đó làm Undo không còn
khớp phiên bản. Với Task STANDARD đã soft-delete, diff vẫn đọc được nếu snapshot
hiện tại khớp đúng một lần xóa đã commit bằng receipt trong cùng hội thoại, gồm cả
receipt gốc và Undo. PRIVATE, nguồn mất hoặc lần xóa không có chứng cứ khớp vẫn bị
chặn. Receipt cũ thiếu recovery trả lỗi rõ ràng; không dựng lại inverse
từ trạng thái hiện tại. `POST /api/mimi/receipts/{receipt_id}/undo-preview`
giữ bước Confirm và CAS. Có thể đọc diff trong lúc gọi; kết thúc Voice trước
khi mở Undo preview từ UI hoặc gửi lệnh Chat.

Calendar Voice v2 trả thêm `day_milestones` là trang annotation riêng cho
truy vấn gồm annotation, kể cả khi trang chính đã đầy Task. Day marker độc lập
có thể là kết quả duy nhất. Trang lịch gốc, cursor và nghĩa của coverage vẫn
giữ nguyên; `day_milestones` có coverage và cursor riêng.

## B1 grant71 — local implementation record

2026-nov-16, source: PM task handoff, stable ID grant71-B1. B1 owns backend core,
focused tests and this contract; B2 owns settings, context_builder, owner_context
and its final voice_v2_protocol append. Provider dispatch, production, migration,
PR and deploy are outside this builder grant.

PM clarification, verbatim (2026-nov-16):
> PM source check baseline ordinary Chat has no explicit model Undo tool, only UI POST receipt undo-preview; please ensure approved 'Mimi thường can revert same receipt' is actually reachable from typed request (deterministic transparent route for clear latest Undo or scoped undo candidate permitted) not just endpoint sharing. Do not rely on model rebuilding inverse from title. This was initial approved requirement, no extra scope. Coupled core yours; T1 PM keeps UI contract stable.

B1 clarification grant71-B1-NAMING, source PM (2026-nov-16), verbatim:
> New contract note from approved B2/71: known stable naming can transform spoken formatting e.g user synthetic 'tạo task training alpha' -> candidate '[TRAINING] alpha'; current normalized equality forbids any punctuation/bracket difference. Please support safe structural title comparison (case/whitespace/canonical bracket prefix) generically, no real private subject dictionary in repo. Explicit supplied literal remains exact; avoid full arbitrary semantic rewrite/relaxation. For unsupported transformation keep visible preview (not phantom missing) rather than false applied; B2 semantic QA Owner will assess. Parent specB12 includes one conventional normalization case. B2 private block persists as short text only, not structured catalog.

B1 correction grant71-B1-DIFF, source PM (2026-nov-16), verbatim:
> PM review receipt_history WIP: receipt_diff currently throws410 when current snapshot differs recovery.after. For selected historical receipt diff, ordinary STANDARD later edit should still display its exact historical committed before/after; only Undo becomes unavailable on CAS drift. That was in review/acceptance 'actual diff at execution, not current guessed state'. Preserve now-PRIVATE/deleted source privacy guard. Please add actual PG case applyA→applyB sameTask→open diffA shows original actualA with undo_availablefalse; do not reject just changed version. This is scope correction before freeze, not relaxed write CAS.


### B1 builder handback — 2026-nov-16

**Builder checks complete; independent QA and real provider/device acceptance NOT_RUN.**
Branch `feat/103-mimi-b1-voice-core`, base
`0e0ed187abc39439331a4a244d2c8fa733b2dff8`. The commit containing this record is
the immutable handback candidate; obtain it with `git rev-parse HEAD`.

Implementation session: branch created 2026-11-16 17:50:06 +07:00
(Asia/Saigon); final builder reconciliation 2026-11-16 18:36 +07:00.
All examples and fixtures are synthetic. Actual external provider calls: **0**,
provider tokens **0**, provider USD **0**. Local assistant/tool usage and billed
assistant cost are not exposed by this runtime; do not infer them from test timing.

| Builder evidence | Result |
|---|---|
| Offline B1/Voice v1/v2/Calendar/Confirm/context/compaction batch | 92/92 PASS, 5.45s pytest |
| PG B1/Voice v1/v2/Calendar/message provenance/Chat API batch | 60/60 PASS, 72.13s pytest |
| Affected PG B1 + Voice v2 after final timer guard | 30/30 PASS, 50.44s pytest; overlaps full PG batch |
| Focused B1 after intended guard-bypass witness restored | 11/11 PASS, 0.92s pytest; overlaps offline batch |
| Ruff check + format check on 13 changed Python files | PASS |
| `git diff --check` and unchanged B2 files | PASS |
| Live Gemini / full app UI / physical device / CI / production | NOT_RUN |

Unique final builder coverage is **152/152 (100%)** offline + PG cases, using
valid unaffected receipts from the full PG freeze plus the affected final rerun.
The original PG 21-case batch preceded additional cases; it is not a separate
unique denominator. The 60-case batch exposed no product failures. A preceding
offline batch found a missing default action timer in the cancellation fixture;
the guard was corrected and its affected checks passed.

Observed RED -> GREEN witnesses:

- Baseline SpeechWindow loaded in memory from the exact base commit: actual
  `inputTranscription={"text":"Tạo việc A."}` with observed VAD offsets returned
  no proof; the final test returns the whole utterance. No disk checkout swap.
- Disabling only the concurrent event reader in memory made the new-speech
  during commit test fail at `action_cancelled == False`. Restored source passed
  new-speech/cancel/upstream-disconnect cases. No real provider was contacted.
- The structural bracket convention test first rejected
  `training alpha` -> `[TRAINING] alpha`; final test passes with explicit literal
  and unsupported-rewrite preview checks retained.
- PG apply A -> committed edit B -> diff A first returned 410
  `receipt_sources_stale`. Final diff A returns actual historical A with
  `undo_available=false`, diff B returns actual B, and Undo A still returns 409.

The PG cases include offsetless 1/5 exactly-once apply and 6-item preview, default
fast-apply off, manual Confirm/idempotency, Chat single-create -> new Voice Undo,
Voice -> typed Chat Undo (HTTP and SSE), latest stale refusal, ABA, private/missing
source suppression, old message marker beyond the recent-runs window, legacy
receipt without recovery, Stop -> new Voice with stable source-free decisions,
pending state and text, source-backed history withheld, marker-only day and a
40-Task page with an independent annotation page. Existing rollback/source
selection/session/90-minute absolute-deadline/reconnect fail-safe cases remain.

Reproduce from `backend` with the existing authorized venv and
`MIMI_P0_DISABLE_DOTENV=1`; the PG batch also needs the synthetic
`NEON_MIGRATOR_URL` and `CI_APP_DATABASE_URL` targeting only the DB below.
No owner dotenv is required. Offline command:
`python -m pytest tests/test_mimi_b1_contracts.py tests/test_mimi_voice_v2.py tests/test_mimi_voice_bridge.py tests/test_mimi_calendar.py tests/test_mimi_confirm_commit.py tests/test_mimi_context.py tests/test_mimi_compaction.py -q -p no:cacheprovider`.
PG command:
`python -m pytest tests/test_mimi_b1_receipts_pg.py tests/test_mimi_voice_v2_pg.py tests/test_mimi_voice_pg.py tests/test_mimi_calendar_pg.py tests/test_mimi_message_provenance_pg.py tests/test_mimi_p1_api.py -q -m pg -p no:cacheprovider`.

Resource freeze/release: exact container
`c6321aaec07f4dec2983340c4a744993457ef23c5c2aa8a8c4f299328b835c89`,
`127.0.0.1:51582/mimi103_v2_check`, schema `0020`. Final read-only reconciliation
found **0 sessions, 0 Tasks, 0 Mimi conversations, 0 day annotations, 0 other
connections**. Existing scalar audit and app-setting fixtures are retained.
The container/database is retained; B1 releases its sole writer lease at handback.
No independent-QA DB or Owner DB, original source, remote, migration or deploy
was touched.

PM integration seams and limitations:

- Actual Voice setup uses `voice_context.configure_voice_setup` after
  `setup_v2`: action declarations are explicitly `BLOCKING`, compensating for
  Gemini 3.8's async default. B2's private final system append remains intact
  and last; B1 inserts its public contract before it. No B2 file was modified.
- PM must wire B2's `messages_for_evidence(envelope,messages)` into both stored
  request snapshot sites and its composed-prefix hash into native prompt-cache
  observation. B1 deliberately does not import B2 helpers on the base commit.
- API shapes match the UI handback: exact verified Server-message
  `applied_receipt_id`, historical `plan`, `undo_available` and `executed_at`.
  Diff works during Voice. UI manual Undo preview and typed Chat require ending
  the active Voice call first (explicit 409 contract, covered by PG).
- Source-free complete model responses provide continuity. A tool-exposed
  Voice context keeps source-backed prose withheld for fresh reads.
- A source-invalidating own commit can retire the upstream before its tool
  response; UI has the durable outcome, while the new model context receives
  only scalar status with `turnComplete=false`. It never forces speech over
  fresh input. A lost commit acknowledgement remains unknown and stops the
  action path for receipt reconciliation; it does not send false failure.
- Final ASR has no provider utterance ID. Conservative local VAD/window checks
  and a short duplicate-final replay guard cannot establish actual provider
  transcription quality; live semantic/ordering acceptance belongs to PM/Owner.
- Legacy receipts lacking captured recovery remain 409. Soft-deleted/private/
  missing sources return unavailable diff. No invented historical inverse.
- Runtime Undo/visibility/provider safety and real 90-minute transport acceptance
  remain independent of deterministic builder checks.

Official wire references checked read-only:
[Live transcript/voice activity API](https://aistudio.google.com/api-reference/live),
[Gemini 3.8 asynchronous default and content interruption](https://aistudio.google.com/docs/models/gemini-3.8-live#migrating),
[Live tool results](https://aistudio.google.com/docs/live-api/tools).

### Kiểm chứng bổ sung — 2026-nov-16

Diff của Undo-create giữ đúng before/after đã commit, kể cả batch có cả Task còn
hoạt động và tombstone. Việc xem diff không khôi phục hay ghi đè Task. Một lần
xóa thủ công sau đó, ABA, nguồn mất, đổi PRIVATE hoặc sai hội thoại vẫn không
cấp quyền đọc. Undo tiếp tục dùng CAS hiện tại.

Input transcription không có thứ tự bảo đảm so với VAD và phản hồi model.
Nếu một lượt đã đóng còn thiếu final, final không có offsets trong cửa sổ mới
chỉ cho phép preview đầy đủ, không tự ghi. Final đã thấy ở lượt cũ được giữ dấu
bằng hash trong phạm vi socket; native resume giữ guard, không hết hiệu lực
sau một giây. Không có VAD_START không tự chứng minh final cũ nếu PCM mới đã tới.
Final tới khi chưa có thêm PCM, hoặc offsets xác định đúng cửa sổ cũ, có thể
giải quyết final còn thiếu. Sau preview mơ hồ, backend dùng nhánh reconnect sẵn
có để mở upstream mới, nạp lịch sử đã qua source/history guard và trạng thái
preview; không phát lại audio hay proposal. Socket mới giải phóng debt và
duplicate guard của socket đã đóng nên lệnh offsetless riêng biệt tiếp theo
vẫn có thể fast apply. Giới hạn 13 upstream opens và deadline 90 phút giữ nguyên.

Trong cùng socket, một lệnh offsetless giống hệt lệnh cũ vẫn có thể cần preview
tay: gồm câu Undo lặp lại sau một receipt mới. Preview chọn đúng receipt mới
nhất, không tự ghi; sau reconnect và Confirm, đường nhanh dùng được cho lượt
mới. Đây là giới hạn quan sát được, không phải bảo đảm phân biệt nhân quả từ
ASR không có utterance ID.

Các witness mới dùng bridge/store thật trên PostgreSQL tổng hợp và provider
double: late final A trong B; replay final cũ; đường offsetless bình thường;
Undo-create gốc/inverse; mixed batch; PRIVATE/missing/scope và deletion ABA.
Producer test kiểm đúng số callsite theo file, function và producer code, bao
gồm callsite thông báo typed Undo. Bằng chứng này chưa xác nhận Gemini thật sẽ
phát chuỗi sự kiện đối nghịch; actual-provider reachability vẫn UNVERIFIED.

Builder affected checks: **34/34 offline PASS** và **42 ca PG đã đối chiếu**:
41 ca pass trong batch cuối, một oracle cũ còn chờ tool response từ socket đã
đóng được sửa sang kiểm durable scalar status ở context mới; retest 3/3 PASS
(bao gồm recovery và Undo lặp). Ruff, format và diff checks PASS. Đây là builder
evidence; independent QA, browser, Gemini thật và device vẫn nghiệm thu riêng.
