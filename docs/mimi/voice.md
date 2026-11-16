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

## Voice v2-A (ứng viên local, bật riêng)

Bật thử trên instance được cấp quyền bằng `MIMI_VOICE_V2_ENABLED=true` cùng các
điều kiện của v1. Flag mặc định tắt; tắt lại để ticket mới dùng v1. Không cần
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
Lệnh “hoàn tác cái vừa làm” chỉ tự áp dụng cho receipt Voice mới nhất đủ điều kiện
trong cuộc gọi này nếu phiên bản Task chưa đổi; không tìm lùi sang receipt cũ.

`GET/PATCH /api/mimi/voice-preferences` dùng session và CSRF khi ghi, với
`{"fast_apply": true|false}`. Mặc định true; tắt thì thao tác đề xuất đi qua
preview và Confirm. Cài đặt là của Voice; Chat giữ quy trình xác nhận hiện tại.
Transcript vẫn lưu mã hóa trong hội thoại. Phần trả lời Voice được giữ ngoài
ngữ cảnh model ở cuộc gọi mới hoặc Chat mới để tránh dùng lại nguồn đã đổi.
Context compression mặc định bật (25.000 xuống 8.000 token); có thể tắt qua
`MIMI_VOICE_V2_COMPRESSION_ENABLED`.

WebSocket báo `reconnecting`, `resumed` (có thêm `context_retained`) và
`action_updated` với trạng thái `preview`, `applied`, hoặc `undone` sau commit.
Browser gửi `{"type":"microphone_lost"}` nếu mất capture ngoài ý muốn.
Ca v1 dừng sau 34,263 giây có mã gộp browser/provider nên không xác định được
nguyên nhân vật lý. V2 ghi riêng lý do browser, upstream, mic, deadline và Stop.
Khả năng tương quan lời nói của Gemini thật, chất lượng câu trả lời và mic thật
cần được Owner nghiệm thu riêng; kết quả provider giả chỉ xác minh hợp đồng app.
