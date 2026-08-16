# Task 023 — Apple touch icon

> Trạng thái: ✅ APPROVED 2026-08-16. Phạm vi nhỏ, không mở rộng sang redesign hoặc physical-device QA.

## Mục tiêu

iPhone/iOS **Add to Home Screen** phải có icon rõ ràng từ đúng visual identity hiện có của microSched. Dùng `frontend/public/microsched.svg` làm nguồn, rasterize thành PNG vuông **180×180**, và composite nền kín để PNG có alpha opaque.

## Phải làm

- Thêm đúng link `apple-touch-icon` 180×180 trong `frontend/index.html`.
- Commit `frontend/public/apple-touch-icon-180x180.png`.
- Giữ Vite build copy PNG vào `frontend/dist/` và thêm automated guard kiểm tra link, asset built, kích thước chính xác và alpha opaque.
- Chứng minh guard RED bằng cách phá đúng contract rồi khôi phục GREEN.
- Chạy npm ci nếu cần, test/lint/build, diff-check, pre-commit/gitleaks.

## Không làm

- Không redesign logo, không AI-generate asset mới.
- Không thêm manifest icons 192/512 nếu không có contract hiện tại yêu cầu.
- Không chạm Task 017, README, migration, production deploy hoặc merge.
- Physical iPhone Home Screen visual QA là **CHƯA VERIFY / deferred post-cutover**.

## Acceptance

1. Source và built PNG đều là RGBA 8-bit 180×180, mọi alpha byte = 255.
2. `npm run build` chạy guard tự động và in receipt PASS.
3. Guard đỏ khi thiếu/sai link hoặc asset/PNG contract bị phá, sau đó xanh lại.
