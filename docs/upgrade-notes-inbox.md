# Upgrade notes — inbox (chưa triage)

> **Trạng thái: RAW CAPTURE — KHÔNG có tính thời gian.** Đây là các ghi chú "nâng cấp microSched" chép lại từ 2 ảnh chụp note app cũ (parse ngày 2026-07-19). Các ý này **không có mốc thời gian** — có thể cũ, có thể đã lỗi thời, **nhiều ý đã được chốt/loại** ở các brief khác. Cột "Trạng thái" bên dưới là đối chiếu của Claude với docs hiện tại, **không phải** một phần của ghi chú gốc.
> **Mục đích:** giữ nguyên văn để không rơi ý (provenance). **Lưu ý:** `forward-spec.md` ĐÃ là bản triaged của chính các note này (viết 18/07 từ cùng nguồn) — file này chỉ là bản thô nguyên văn để đối chiếu. Đa số ý đã nằm trong `forward-spec.md` / `architecture-brief.md`.

## Chú giải trạng thái
- ✅ **absorbed/chốt** — đã có quyết định trong docs (kèm nguồn)
- ❌ **đã loại** — đã cân nhắc và bỏ
- 🆕 **mới** — chưa có trong docs → cần triage vào `forward-spec.md`
- 🔷 **UI/frontend** — để phiên frontend-scaffold

## Danh sách (nguyên văn, gộp 2 ảnh theo thứ tự cuộn)

| # | Ghi chú gốc (nguyên văn) | Trạng thái | Đối chiếu |
|---|---|---|---|
| 1 | refactor + thiết kế lại toàn bộ | ✅ | Chính là dự án rewrite này |
| 2 | Nâng speed + scalable + Agent helper | ✅ | Định hướng chung: modular monolith + tầng Agent (`architecture-brief.md` §3) |
| 3 | Chuyển đổi kiến trúc thành multi app + delpoy? | ❌ | Đã loại — **modular monolith, KHÔNG microservices** (`architecture-brief.md` §3) |
| 4 | 1 app trên desktop + 1 app mobile (có đồng bộ) | ✅ | Giải bằng **PWA** — 1 codebase cài được cả desktop+mobile, offline-first sync (`architecture-brief.md` §4) |
| 5 | Tính năng nhắc uống thuốc (rất cần) | ✅ | Đã chốt cơ chế: cron (GitHub Actions) → đánh thức app → web-push (`architecture-brief.md` §3) |
| 6 | Trong tab lịch tháng, có một tooltip để nhập task nhanh, sau đó kéo thả vào các ô date cell để thêm task vào ngày | 🔷 | UI lịch — phiên frontend |
| 7 | Tăng chiều dài hiển thị của tooltip của date cell | 🔷 | UI — phiên frontend; liên quan #9 |
| 8 | ghi chú cho task tự đặt hiển thị được nhiều dòng | 🔷 | UI/viewability — phiên frontend |
| 9 | Khi thiết kế app cần quan tâm đến độ dài max thiết kế của các trường, tooltip datecell lịch ngày + tooltip notecell đều bị giới hạn. Chỉ có thể xem full = sửa? | ✅ | Đây chính là *vấn đề* mà nguyên tắc **"lưu full text, chỉ cắt lúc hiển thị, luôn có nút xem full"** giải (`db-and-data-model-brief.md` §4) |
| 10 | Tính năng "Lời nhắn từ tương lai" đối với note cell khi xem lại và hoàn thành hoặc muốn nói gì đó với note cũ. Thay vì chỉ discard | 🆕 | Feature mới, thú vị → triage vào `forward-spec.md` |
| 11 | Tính năng "ẩn" hoặc cắt bí mật task hoặc note | 🆕 | Mới cho task/note. Lưu ý: `calendar_event` đã có cột `is_hidden` trong schema — có thể mở rộng nguyên tắc |
| 12 | Tính năng di chuyển task trễ hạn (hoặc task thường) nhanh với lựa chọn chuyển về hôm nay, ngày mai, ngày kia v.v | 🆕 | UX "quick reschedule" → `forward-spec.md` |
| 13 | Note cần được hiển thị để rõ tính "thời gian" hơn. Hiện tại xem note thì chúng sinh bình đẳng, không có note nào mới/cũ, hoặc chí ít là không hiển thị | ✅ | Chính là nguyên tắc **"mọi entity có created_at/updated_at, tính thời gian"** (`db-and-data-model-brief.md` §4) + quyết định timestamp đồng đều mọi bảng (Nhóm 2) |
| 14 | memory cho Agent (dynamic AI feature in AI eng book) | 🆕 | AI feature (agent memory) → lộ trình Bước 1+; ghi vào backlog AI |
| 15 | A2A agent, a little Model when need, bigger bud when it's hard, a routing model at the core? | ✅ | Đã có khái niệm: **OpenRouter cascade** (model rẻ → escalate frontier), "routing model at core" = cascade (`architecture-brief.md` §8) |
| 16 | Log all to fine-tune later? Like acceptance from AI's suggesting features | ✅ | `audit_log` + "log để fine-tune" đã chốt (`schema-v1-brief.md` §2). "acceptance from AI's suggesting" = tín hiệu eval cần log (Nhóm 2 / D3) |
| 17 | Tính năng đánh dấu ngày - ví dụ ngày về quê | 🆕 | "Day annotation / special day" → `forward-spec.md`; cân nhắc map vào `calendar_event` hay bảng nhẹ riêng |
| 18 | Tính năng ghi lại và quản lý các "hoạt động xấu" ví dụ như hút thuốc/bia rượu/bi a v.v | ✅ | Chính là **`tracker`/`entry`** (kind=health) đã chốt (`schema-v1-brief.md` §2). Cần phiên thiết kế chi tiết tính năng tracking |
| 19 | Để ý rằng mình có free credit của Goole AI studio (nhiều acc qua openrouter) + OpenAI + | ✅ | Đã ghi: OpenRouter cascade tận dụng credit sẵn (Google AI Studio, OpenAI) (`architecture-brief.md` §8) |

## Tổng hợp triage

- **Đã absorbed/chốt (9):** #1, #2, #4, #5, #9, #13, #15, #16, #19 — không cần làm gì, chỉ xác nhận ý cũ đã nằm trong quyết định.
- **Đã loại (1):** #3 (multi-app/microservices).
- **UI/frontend (3):** #6, #7, #8 — dồn về phiên frontend-scaffold.
- **Mới, cần triage vào `forward-spec.md` (6):** #10 (lời nhắn từ tương lai), #11 (ẩn/bí mật task-note), #12 (quick reschedule task trễ), #14 (agent memory), #17 (đánh dấu ngày đặc biệt).
- **Cần phiên thiết kế tính năng tracking (1):** #18 — coupling với các quyết định đang parked ở Nhóm 2 (kiểu số `entry.value` = C2, cascade `tracker→entry` = D1-tracker).

## Bước tiếp
1. 6 ý UX/AI mới đã có trong `forward-spec.md` §B/§D (reschedule nhanh, quick-add lịch, đánh dấu ngày, ẩn/khoá riêng tư, agent memory, lời-nhắn-tương-lai) — không cần làm lại, chỉ xếp ưu tiên khi tới phiên frontend/AI.
2. Mở **phiên thiết kế tính năng tracking** (giải #18 + C2 + D1-tracker cùng cụm) — xem `schema-physical-brief.md` §7.
