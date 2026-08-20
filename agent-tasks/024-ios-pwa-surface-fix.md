# Task 024 — iOS PWA surface fix

> Trạng thái: ⚠️ IN PROGRESS (owner approved 2026-08-20)
> Executor: T2 Luna · Bậc: high · Effort: high · Skill gợi ý: Playwright · MCP cần: không có

## Mục tiêu

Sửa hai root cause đã đo trên iPhone XS Max installed PWA: iOS đang nhận màu mặc định xanh
`#42b883` từ manifest cho status/overscroll; và các primitive light-only còn nhánh `dark:*`
để hệ điều hành dark làm giao diện bị muddy gray. Đồng thời triển khai Option B “hồng ấm nhẹ”
đã được owner duyệt: state/control được chọn dùng rose-100/accent + rose-700 foreground +
rose-600 boundary; control outline thụ động dùng rose-50 hoặc nền sáng với boundary đạt WCAG.

## Phạm vi bắt buộc

- Manifest + HTML: `theme_color` và `background_color` đúng `#f3eeef`; có meta
  `theme-color` cùng giá trị; outer canvas full-height nhất quán trên `html`, `body`, `#root`
  và `main`, không tự thêm `viewport-fit=cover`.
- Gỡ toàn bộ `dark:*` khỏi `badge`, `button`, `checkbox`, `input`, `select`, `textarea`;
  built CSS không còn `prefers-color-scheme: dark` từ light-only primitives.
- Thêm typed variants dùng qua component: selected active tab/filter; soft rose cho private
  unlock và quick-reschedule. Không đổi global `--border`, `--input`, `--ring`; không biến mọi
  button thành hồng; default/destructive semantics giữ nguyên.
- Regression Playwright mobile 390×844: emulate light và dark rồi so computed background/border
  của `private-unlock-open`, `quick-add-input`, `task-reschedule-today`, `task-checkbox`;
  styles phải giống nhau, không muddy gray. Có desktop 1280×800 smoke/overflow và contrast/focus.
- Build guard kiểm generated manifest/index exact colors, không xanh, không `prefers-color-scheme`
  dark; có RED→GREEN receipt bằng cách chạy guard trước rồi sau patch.
- Scope chỉ frontend + spec/tests; không backend/DB/012/017/022; không update
  `agent-tasks/README.md`; không Chrome MCP/account/production browser.

## Không làm

- Không hạ các token contrast numeric; không thêm dark mode; không thay semantic default,
  destructive, disabled; không hardcode màu trong screen/component ngoài token classes.
- Không thêm safe-area/viewport-fit trừ khi layout evidence hiện tại bắt buộc.
- Không verify bằng physical iPhone trong task này; owner làm post-deploy verification.

## Acceptance

1. `npm run lint`, unit tests, `npm run build` pass.
2. Guard script pass và output exact `#f3eeef` cho manifest/index; `rg` source/UI và built CSS
   không còn `dark:`/`prefers-color-scheme: dark` trong phạm vi light-only.
3. Playwright mobile + desktop relevant/full lane pass; computed style light/dark equality,
   touch targets, contrast, focus ring, no horizontal overflow được đo bằng số.
4. `git diff --check`, pre-commit, gitleaks pass; commit tiếng Việt qua UTF-8 file có
   `Co-Authored-By`, push branch `feat/024-ios-pwa-surface-fix`, mở PR vào `develop`; không merge.
5. Báo cáo tách rõ `[ĐÃ CHẠY]`, `[CHƯA VERIFY]`, và hướng dẫn owner reinstall/cache clear
   cho post-deploy iPhone PWA.
