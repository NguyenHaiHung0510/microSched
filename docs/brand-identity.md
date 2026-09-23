# Quy chuẩn bộ nhận diện: microSched · Mimi · Orbit

> Tài liệu quy chuẩn chính thức về mỹ thuật, tạo hình, màu sắc và các thành phần nhận diện của hệ sinh thái microSched.
> Owner phê duyệt ngày 2026-09-20. Áp dụng cho mọi lập trình viên và AI agent tham gia phát triển dự án.

## 1. Triết lý thiết kế

- **Vector, không raster crop:** Logo, Mimi và Orbit dùng artwork SVG nền trong suốt. Không lấy ảnh crop từ bảng concept làm logo hoặc biểu tượng.
- **Zen origami và giấy Washi:** Hình khối gợi giấy gấp thủ công, các lớp có chiều sâu mềm, đường cong hữu cơ và điểm nhấn vàng kim. Chuyển động nhỏ mô phỏng nhịp thở tự nhiên.
- Chuyển động chỉ bổ trợ trạng thái; trạng thái phải được biểu đạt bằng artwork và nội dung truy cập được, không phụ thuộc riêng vào animation.

## 2. Màu nhận diện

Các token được khai báo trong `frontend/src/index.css`:

| Token | Giá trị | Vai trò |
| --- | --- | --- |
| `--brand-ivory` | `#FBF8F3` | Giấy Washi ngà, mặt sáng của nếp gấp và thân Mimi. |
| `--brand-sakura-soft` | `#F5B8BA` | Hồng sakura nhẹ trên tai Mimi và cánh Orbit. |
| `--brand-sakura-deep` | `#DE7A85` | Nếp gấp hồng đậm và điểm nhấn chữ Sched. |
| `--brand-gold-leaf` | `#CFA348` | Nếp dát vàng, nhụy hoa, quỹ đạo và huy hiệu hoàn tất. |
| `--brand-deep-berry` | `#4A1521` | Mắt Mimi và phần chữ micro có tương phản cao. |

## 3. Các trụ cột nhận diện

### 3.1 microSched — Layered Calendar Bloom

Biểu tượng là bông hoa origami năm cánh xếp lớp, gợi một lịch kế hoạch mở ra liên tục. Tâm hoa có ba điểm vàng tượng trưng cho **Plan · Progress · Bloom**. Wordmark giữ tương phản màu Deep Berry và Sakura Deep.

`BrandLogo` từ `@/components/brand` là component chuẩn. Component hỗ trợ `variant="mark" | "wordmark" | "full"`, `size="sm" | "md" | "lg"`; biến thể `full` mặc định hiện tagline và có thể tắt bằng `showTagline={false}`.

- Mark: `frontend/public/brand/microsched-mark.svg`
- Wordmark: `frontend/public/brand/microsched-wordmark.svg`
- App icon artwork: `frontend/public/brand/microsched-app-icon.svg`

### 3.2 Mimi — Zen Origami Spirit

Mimi là người bạn đồng hành hình búp hoa giấy origami. Khuôn mặt tối giản có hai mắt tròn màu berry; không thêm lông mày, miệng hoặc mắt xếch.

`MimiAvatar` hỗ trợ các trạng thái `idle`, `thinking`, `executing`, `ready` và kích thước `xs`, `sm`, `md`, `lg`, `xl`. Mỗi trạng thái có nhãn truy cập tiếng Việt mặc định; có thể ghi đè bằng `ariaLabel`. `showGlow` bật quầng sáng trang trí.

| State | Ý nghĩa | Motion class | Artwork |
| --- | --- | --- | --- |
| `idle` | Búp hoa yên tĩnh, đang lắng nghe. | `brand-breathe` | `frontend/public/brand/mimi-idle.svg` |
| `thinking` | Ý tưởng hé mở; ánh sáng biểu đạt hoạt động suy nghĩ. | `brand-pulse-glow` | `frontend/public/brand/mimi-thinking.svg` |
| `executing` | Đang biến kế hoạch thành tiến độ. | `brand-orbit-rotor` | `frontend/public/brand/mimi-executing.svg` |
| `ready` | Đã sẵn sàng; huy hiệu hoàn tất nảy nhẹ. | `brand-ready-badge` | `frontend/public/brand/mimi-ready.svg` |

### 3.3 Orbit — Origami Blossom in Orbit

Orbit đại diện cho hoạt động tự động hóa nền như cron jobs, đồng bộ ghi chú và nhắc nhở định kỳ. Artwork là Calendar Bloom nằm giữa các quỹ đạo vàng, với chiều sâu tạo bởi các lớp và vệ tinh.

`OrbitIndicator` hỗ trợ trạng thái `standby`, `pulse`, `active`, `complete` và kích thước `sm`, `md`, `lg`. Component có vai trò truy cập `status`; nhãn tiếng Việt mặc định có thể ghi đè bằng `ariaLabel`.

| Status | Ý nghĩa | Motion class |
| --- | --- | --- |
| `standby` | Tự động hóa sẵn sàng. | `brand-breathe` |
| `pulse` | Nhịp heartbeat đang được gửi. | `brand-pulse-glow` |
| `active` | Tự động hóa đang chạy; quỹ đạo chuyển động. | `brand-orbit-rotor` |
| `complete` | Tự động hóa hoàn tất; hiệu ứng huy hiệu ngắn. | `brand-ready-badge` |

Artwork dùng chung: `frontend/public/brand/orbit-blossom.svg`.

## 4. Chuyển động và reduced motion

Các quy tắc nằm trong `frontend/src/brand-motion.css` và được `MimiAvatar`/`OrbitIndicator` import.

- Nhịp thở: chu kỳ 4.2 giây, gồm hít vào 2.2 giây, giữ 0.4 giây và thở ra 1.6 giây.
- Quỹ đạo/vệ tinh: chu kỳ 8 giây; vệ tinh thay đổi tỷ lệ, độ sáng và opacity để tạo chiều sâu.
- Pulse: chu kỳ 2.4 giây, phát sáng theo nhịp heartbeat.
- Hiệu ứng ready/complete: chuyển động nảy 760 ms và không lặp vô hạn.
- Với `prefers-reduced-motion: reduce`, các animation do `brand-motion.css` điều khiển bị tắt, transform/filter được đưa về trạng thái tĩnh; độ mờ tĩnh vẫn phân biệt pulse và vệ tinh, còn trạng thái ready/complete giữ opacity đầy đủ. Glow tùy chọn của `MimiAvatar` hiện dùng utility `animate-pulse` riêng và chưa thuộc override này.

## 5. Quy tắc sử dụng

1. Dùng các component chuẩn `BrandLogo`, `MimiAvatar`, `OrbitIndicator` từ `@/components/brand` khi hiển thị nhận diện trong React.
2. Không dùng icon generic như Bot, Sparkles hoặc Cpu từ `lucide-react` để thay Mimi hay Orbit.
3. Không dùng ảnh raster crop làm logo hoặc biểu tượng; dùng artwork SVG trong `frontend/public/brand/`.
4. Giữ màu nhận diện theo các token trong `frontend/src/index.css`. Không tự tạo biến thể trạng thái khác với API hiện tại của component.

## 6. Nguồn triển khai và kiểm chứng

- Components: `frontend/src/components/brand/BrandLogo.tsx`, `frontend/src/components/brand/MimiAvatar.tsx`, `frontend/src/components/brand/OrbitIndicator.tsx`.
- Motion: `frontend/src/brand-motion.css`.
- Regression test: `frontend/tests/brand-identity.test.tsx`.
- SVG artwork: `frontend/public/brand/`.
