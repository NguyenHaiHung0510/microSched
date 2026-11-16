# Mimi giọng nói

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
