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

## Voice v2 (bật riêng)

Voice v2 dùng `MIMI_VOICE_V2_ENABLED=true` cùng các điều kiện của v1.
Tắt flag để ticket mới dùng v1; không cần migration và không đảo các thay đổi
đã commit. Ticket dùng một lần, gắn đúng login session đã cấp. Deadline 90 phút
tính từ lúc cấp ticket, không tăng khi reconnect.
`MIMI_VOICE_V2_MAX_SECONDS` nhận 30–5.400. Gemini 3.8 Live và giọng Kore giữ nguyên.

### Yêu cầu tự nhiên, một phương án trọn nhóm

Mimi diễn giải lời nói tự nhiên và gửi đúng một typed proposal cho toàn bộ yêu
cầu. Khi cần sửa Task đã có, Mimi đọc dữ liệu và đóng băng lựa chọn trước.
Server đóng băng một preview bất biến và dùng cùng executor với nút Confirm.

| Điều kiện | Kết quả |
|---|---|
| Auto ON, 1–5 Task STANDARD khác nhau; tạo/sửa/xóa mềm có thể Undo; đủ nguồn và không thay reminder hay gây tác động ra ngoài | Tự áp dụng toàn bộ trong một transaction |
| Auto OFF, từ 6 Task, hoặc thay reminder/tác động cần duyệt | Một preview trọn nhóm để Confirm thủ công |
| Thiếu hoặc mơ hồ về đích/thay đổi/lượt audio | Hỏi lại, không tự chọn phần còn lại |
| Nguồn stale, PRIVATE, quyền/phiên không hợp lệ | Từ chối; cần đọc/chọn lại |

Không chia yêu cầu lớn thành các nhóm nhỏ để tự ghi. Hai proposal trong cùng
lượt không được ghép hay chỉ áp dụng một phần. Câu hỏi chỉ đọc, trích dẫn,
phủ định và giả định không phải yêu cầu ghi; model phải phân biệt chúng trước
khi đề xuất. Server kiểm schema, scope, nguồn, snapshot/version, giới hạn đích,
idempotency và transaction; kết quả hiểu đúng ý của model cần nghiệm thu riêng.

`GET/PATCH /api/mimi/voice-preferences` dùng session và CSRF khi ghi:
`{"fast_apply":true|false}`. Mặc định true. Preference này chỉ điều khiển Voice;
Chat giữ quy trình xác nhận riêng.

### Undo bằng receipt

Undo dùng cùng một typed tool trong cuộc gọi hiện có. `latest` chọn đúng receipt
mới nhất của hội thoại, gồm Chat và Voice ở các cuộc gọi trước. Nếu receipt đó
stale, thiếu recovery hoặc đã là inverse, `latest` từ chối và không tìm lùi.
Undo một inverse chỉ có thể qua receipt được chỉ rõ, với cùng CAS như nút và Chat.

Khi người dùng chỉ rõ một thay đổi cũ, model có thể dùng `receipt_ref` chính xác
đã được Server đưa vào context/status của hội thoại. Context gần đây chỉ có handle
mờ, số Task và thời điểm; không đưa raw receipt/Task ID, payload lịch sử hay recovery.
Nếu không phân biệt được các nhóm hoặc handle không còn trong cửa sổ gần đây,
Mimi hỏi lại thay vì đoán. Tham chiếu từ hội thoại khác không hợp lệ.

Server ràng buộc receipt với commit trong cùng hội thoại, kiểm recovery rồi đóng
băng exact inverse. Undo giữ CAS của snapshot sau commit; không đè thay đổi mới hơn.
Inverse cho 1–5 Task đủ điều kiện có thể tự áp dụng, kể cả khôi phục một lần xóa mềm
được receipt chứng minh. Nhóm lớn, Auto OFF hoặc reminder effect vẫn dùng một preview
trọn nhóm. Không phát lại reminder hay tác động ra ngoài theo lịch sử.

### Lượt audio, hủy và kết quả đã lưu

Quyền ghi không phụ thuộc nội dung caption, exact phrase, so tên Task với lời nói
hoặc hash câu nói. Server bind proposal bằng activity/audio offset đã quan sát,
turn, transport epoch và tool call ID. Cần ít nhất một sample PCM khác 0 đã gửi
trong cửa sổ VAD hiện tại; chỉ giữ dấu có tín hiệu trong cửa sổ giới hạn ở RAM.
Đây là kiểm tra tín hiệu, không xác thực người nói. Caption đến muộn, thiếu caption
hoặc nói lại cùng câu không tự cấp hay thu hồi quyền.

Gemini Live không đưa input turn ID vào tool call. Ghép theo trật tự sự kiện
quan sát được khi epoch sạch. Nếu lượt trước bị gián đoạn, bỏ dở hoặc chồng lấn,
hoặc resumption có dấu hiệu replay, không gán tool ID mới thấy cho lượt kế tiếp;
Mimi hỏi lại và dùng context mới. Sau tool blocking cần provider terminal sạch
trước activity tiếp theo. Không thể chứng minh một reorder mà transport không bộc lộ.

Stop, mất mic, disconnect, mute, barge-in và tool cancellation được fence trên
event loop ngay trước khi gửi COMMIT, sau flush. Sự kiện quan sát trước mốc đó
làm rollback; sau mốc đó, xác nhận dựa trên receipt, hoặc báo cần đối soát nếu
ACK không rõ. Tool ID replay/đã hủy không được dùng lại; mixed replay không làm
phần còn lại trở thành yêu cầu mới. Không tự chạy lại một thao tác chưa rõ kết quả.

Action tools dùng `BLOCKING`. Sau commit mới gửi `applied/undone` cùng receipt về
browser và kết quả scalar với handle mờ về Gemini. `preview_required` ở tool response
là preview đang chờ duyệt; browser giữ wire status `preview` để tương thích.
Confirm thủ công trong cùng cuộc gọi được đồng bộ sau khi đọc thấy receipt đã
commit. HTTP Confirm đánh thức đúng bridge sau commit; watchdog hiện có vẫn là
fallback. Khi bridge xác thực receipt, nó chặn output generation cũ, gửi event
dừng playback và nối context mới với scalar committed status. Âm thanh đã nghe
trước mốc quan sát không thể thu hồi. Lệnh mới cần PCM/VAD mới sau resumed; không
gửi lại proposal hoặc tool response của preview đã ACK. Nếu rớt upstream sau commit nhưng
trước tool ACK, context mới nhận trạng thái scalar và handle của receipt đã lưu,
không gửi lại PCM, proposal hoặc payload nguồn. Mất ACK từ DB kết thúc với
`voice_action_outcome_unknown`; cần đối chiếu receipt trước khi làm lại.

Rejection có `detail.code` và `detail.next_step` theo vocabulary scalar hữu hạn:
shape/thiếu dữ kiện phương án/nhiều proposal, receipt missing/not-exposed/stale/
latest-inverse, timing/signal/tainted-epoch/cancel. Thiếu field của proposal không
tự chứng minh người dùng đã bỏ sót dữ kiện. Không gửi raw input, exception hay
caption vào detail và không tự sửa/gửi lại plan. Lượt không write bị tainted chỉ
reset chủ động sau terminal sạch; BLOCKING tool vẫn nhận kết quả trước terminal
khi cần, không đợi terminal để gây deadlock. Thiếu boundary vẫn fail-safe.

Scalar status gửi thành công chỉ chứng minh transport write; nếu ACK không rõ,
delivery là unknown và context mới có thể nhận lại cùng logical status. Không
cam kết provider nhận exactly-once; domain mutation/receipt vẫn idempotent và
không retry write.

### Kết nối và context

Nếu upstream đóng/GoAway khi browser và mic còn hoạt động, backend có thể nối lại
trong cùng cuộc gọi. Native resumption dùng handle mới nhất đủ điều kiện trong
bộ nhớ. Khi handle hoặc nguồn không còn an toàn, dùng context mới; không replay
audio hay thao tác cũ. Tối đa 13 lần mở upstream và 3 lỗi liên tiếp. Mic mất,
browser disconnect, logout, đổi hội thoại hoặc Stop dừng cuộc gọi. Mute không tự
mở upstream mới.

Transcript vẫn được lưu mã hóa trong hội thoại. Phiên mới chỉ nhận cửa sổ bounded
của lịch sử được phép và scalar preview/receipt status; nguồn đã thay đổi phải đọc
lại. Setup tối đa 64 KiB, history tối đa 32 KiB, chỉ giữ message đầy đủ.
Context compression mặc định 25.000 xuống 8.000 token; tắt bằng
`MIMI_VOICE_V2_COMPRESSION_ENABLED=false`.

### Tiếng Việt và tiếng Anh

Prompt V2 yêu cầu chỉ trả lời Việt/Anh theo ngôn ngữ hiện tại, giữ từ trộn và tên
riêng, không tự dịch. Nếu nghe không rõ, hỏi ngắn bằng tiếng Việt. Giọng Kore giữ
nguyên; không đặt cứng speech language code.

Input transcription mặc định giữ shape đã dùng `{}`.
Opt-in `MIMI_VOICE_V2_INPUT_LANGUAGE_HINTS=true` gửi
`{"languageCodes":["vi-VN","en-US"]}` chỉ cho V2.
Đặt `false` hoặc bỏ biến để phiên mới trở lại `{}`; không replay audio khi rollback.
Nếu setup trả từ chối có nêu rõ field hint trước khi nhận audio, cùng cuộc gọi thử
đúng một setup với `{}`, vẫn Gemini/Kore. Không fallback khi lỗi khác hoặc đã có
audio; không đổi provider và không phát lại âm thanh. Theo
[API reference](https://aistudio.google.com/api-reference/live#AudioTranscriptionConfig),
đây là hint, không phải whitelist.
[Native audio](https://aistudio.google.com/docs/live-api/capabilities#change-voice-and-language)
chọn ngôn ngữ qua audio và instruction. Khả năng route cụ thể chấp nhận hint, chất
lượng transcript, âm thanh Việt/Anh và mixed language cần Owner thử trong phiên
được cấp; test synthetic không chứng minh các kết quả đó. V1 setup không đổi.

### Receipt, diff và Calendar

Mỗi commit có Server message với `applied_receipt_id` đúng receipt.
`GET /api/mimi/receipts/{receipt_id}/diff` trả
`{receipt_id,plan,undo_available,executed_at}`: snapshot thực tế trước/sau commit.
Chỉnh sửa STANDARD mới hơn có thể làm Undo hết hiệu lực mà diff lịch sử vẫn đọc
được. Với Task soft-delete, diff chỉ đọc khi lần xóa hiện tại có receipt cùng hội
thoại chứng minh. PRIVATE, nguồn mất và lần xóa không có binding hợp lệ vẫn bị chặn.
Receipt cũ thiếu recovery trả lỗi, không dựng inverse từ dữ liệu hiện tại.

`POST /api/mimi/receipts/{receipt_id}/undo-preview` vẫn giữ Confirm và CAS.
Diff có thể đọc khi gọi Voice. Kết thúc Voice trước khi mở Undo preview từ UI
hoặc gửi lệnh Chat.

Calendar V2 trả thêm `day_milestones` là trang annotation độc lập, kể cả khi trang
Task đã đầy hoặc ngày chỉ có marker. Mỗi trang giữ coverage và cursor riêng.
Viewport emulation, mic thật và thiết bị thật là các lớp nghiệm thu riêng.
