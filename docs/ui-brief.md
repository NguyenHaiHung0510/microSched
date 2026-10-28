# UI contract microSched

Các quyết định hiện hành được gom từ brief và các amendment đã chấp nhận. Source control cho biết implementation; các quy tắc dưới không tự chứng nhận mọi surface đã được QA. Significant UI changes cần Owner-selected visual method và explicit batch grant; preview, implementation và runtime/device acceptance là các gate riêng.

## Visual system

- Light-only, hồng ấm, neutral ngả ấm. CSS tokens trong [index.css](../frontend/src/index.css) là source màu/spacing/radius; không hardcode hex hoặc neutral palette trong component.
- Self-hosted Nunito Variable, latin/latin-ext/Vietnamese và italic theo imports đang dùng; không Google Fonts network call. [Brand](brand-identity.md) giữ artwork/identity.
- Dùng existing shadcn/ui components ở [components/ui](../frontend/src/components/ui); không raw button/input/select. Kiểm alias `@/`, file thực và dependencies sau khi thêm component; CLI thành công không chứng minh viết đúng thư mục.
- Card không hard height; chữ ít nhất12px. Không n-400 cho text; secondary text phải đạt contrast. Normal text4.5:1, large3:1, focus/non-text3:1. Brand rose-500 không dùng cho text trên nền sáng; popover sáng, tooltip token riêng.
- Input giữ text-base trên mobile để tránh iOS focus zoom; toast light explicit. Touch target AA tối thiểu24×24, ưu tiên44px và spacing phù hợp. Không dùng một trạng thái hệ điều hành/default library để lén thêm dark mode.
- Hover chỉ là shortcut; mọi thông tin/action có touch/keyboard alternative. Focus, Escape/outside dismissal, opener restoration và accessible labels cần kiểm đúng surface. Không dựa riêng animation/màu để truyền trạng thái; hỗ trợ reduced motion.

## Interaction/data behavior

Quick-add/Enter, focus retention, pin trong phạm vi filter, inline checklist, overdue state và soft-delete/undo giữ domain semantics. Long text chỉ thu gọn để hiển thị; detail/reader có đường đọc đầy đủ. Calendar không có “Don't care” soft-delete event. Private styling không cấp quyền hoặc nới unlock/cache boundary.

Shared API calls có finite timeout; default20s, import/heavy caller dùng explicit override. Không giữ mutation pending chỉ để đợi background invalidate/refetch. Timeout không đồng nghĩa không commit; outbox/ACK unknown theo contract riêng. Errors giữ editable draft khi contract cho phép; private/auth purge vẫn thắng.

[Current UI behavior](reference/ui-behavior.md) mô tả responsive shell, compact/reader/checklist/History và Mimi feedback hiện hành. [Outbox](reference/offline-outbox.md) mô tả local admission/pending/ACK; không quay về HTTP fallback để che lỗi storage.

Reminder center giữ Upcoming/Attention/History; source editor làm việc trên saved object. Date-only reminder cần clock rõ ràng. Browser/device permission chỉ hỏi từ explicit user action, không từ lưu schedule; zero-device state phải giải thích. Physical iPhone/Safari và actual Push là acceptance riêng.

## Verification

Dữ liệu phải gồm long unbroken string (~70chars), Vietnamese nhiều dấu (~150chars), uppercase dấu, emoji,1char, leading/trailing spaces, all-whitespace rejection và body/checklist dài. Nêu đúng wrap/ellipsis/overflow/clipping/action reachability thay vì chỉ nói “chạy”.

[QA framework](qa-framework.md) giữ các trục Nielsen/mobile/WCAG/microcopy/taste, state matrix, ảnh và measurements. Dùng full local app với synthetic/approved QA data khi cần preview. Viewport không phải physical device; Owner taste acceptance không thay CI/runtime gates.
