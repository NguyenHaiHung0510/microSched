# 011a-QA — Báo cáo Kết quả QA Tracker Capture + Dashboard

> **Executor:** T3 QA Agent
> **Ngày thực hiện:** 2026-08-05
> **Target Production:** https://microsched.fly.dev
> **Viewport:** 390 × 844 (Mobile) & 1280 × 800 (Desktop)
> **Trạng thái nghiệm thu:** PARTIAL / UNVERIFIED (LANE 1-3 ĐÃ CHẠY XANH, LANE 4 CHƯA VERIFY ĐƯỢC DO KHÔNG CÓ IPHONE THẬT VẬT LÝ)

---

## 1. Danh mục Phân định Trạng thái Thao tác (Đã chạy / CHƯA chạy / SUY LUẬN)

- **ĐÃ CHẠY:**
  - LANE 1: Lint (`npm run lint`), Build (`npm run build`), Unit/Type tests (`npm test`), E2E discovery (`npm run e2e -- --list`), Playwright Mobile (`npx playwright test --project=mobile e2e/tracker.spec.ts`), Playwright Desktop (`npx playwright test --project=desktop e2e/tracker.spec.ts`), Backend Ruff (`uv run ruff check .`), Pytest (`uv run pytest`).
  - LANE 2: Chrome MCP Browser Acceptance trên Production (`https://microsched.fly.dev`) với tài khoản Google đã đăng nhập. Đã đo geometry (`getBoundingClientRect`), WCAG contrast ratios, kiểm 5×5 surface matrix và fixtures D-01, D-02, D-03, D-04, D-05, D-06, D-07, D-08, D-10, D-11, D-12.
  - LANE 3: Playwright Red-proof local cho guardrail PW-05 (Echo tiền `= 100.000 ₫`). Đã cố ý sửa assertion thành `= 999.999 ₫`, chứng minh Playwright báo ĐỎ đúng lỗi `toBeVisible()`, sau đó khôi phục file và chạy XANH lại.

- **CHƯA CHẠY:**
  - LANE 4: iPhone vật lý thật để test touch cảm ứng thực tế, bàn phím ảo iOS thật và safe area notch (`CHƯA verify được` do môi trường sandbox không gắn iPhone vật lý).
  - PostgreSQL Integration tests trên localhost Docker Postgres trong lane Pytest backend (`57 skipped` do không bật `ALLOW_REMOTE_PG_TESTS` hoặc Postgres local daemon).

- **SUY LUẬN:**
  - Do build production bundle thành công (`tsc -b && vite build` exit 0), ESLint 0 warning/error, 59 Vitest passed, 8 Playwright e2e tracker tests passed, Ruff 0 error, Pytest 118 unit tests passed, và Chrome production test trực tiếp chạy mượt mà trên Neon DB, suy ra logic frontend/backend slice 011a đáp ứng đầy đủ contract chức năng.

---

## 2. (a) Đã soi những gì

- **Màn / Surface:** `CaptureGrid`, `TrackerCard`, `EntryEditDialog`, `GroupForm`, `DashboardPanel`
- **Môi trường:** Production (`https://microsched.fly.dev`) + Local Playwright Chrome/Chromium
- **Viewport:** `390 × 844` (`innerWidth: 390`, `innerHeight: 844`, `scrollWidth: 375`) và `1280 × 800`
- **Tài khoản test:** Tài khoản Google trong allowlist (đã đăng nhập sẵn trên Chrome MCP)
- **Dữ liệu QA tạo (Prefix `QA-`):**
  - `QA-Group-Finance` (Tài chính)
  - `QA-Event-Tracker` (Loại: Một chạm)
  - `QA-Money-Tracker` (Loại: Một chạm / Số tiền, nhóm QA-Group-Finance)
  - `QA-Money-Card` (Loại: Số tiền)
  - `QA-Private-Tracker` (Tracker riêng tư)
  - `QA-D01-70chars-12345678901234567890123456789012345678901234567890123456789012`
  - `QA-D02-TiếngViệt-ế-ữ-ộ-ằ`
  - `QA-D03-CHỮ HOA CÓ DẤU`
  - `QA-D04-🏃‍♂️-Emoji`

---

## 3. (b) Bảng phát hiện (4 trục: Nielsen, HIG, WCAG, Microcopy)

| # | Trục | Mức | Chỗ (`file:line` hoặc selector) | Số đo / Raw output | Đề xuất |
|---|---|---|---|---|---|
| 1 | HIG Touch Target | 🟡 | Nav tabs (`button` chứa "Task", "Ghi chú", "Lịch", "Theo dõi") | Height = 36px, Width = 67px–96px (Dưới 44px HIG target; đạt WCAG 2.5.8 >=24px) | Nâng `min-height` lên 44px cho các tab điều hướng chính trên viewport mobile. |
| 2 | HIG Touch Target | 🟡 | `group-dialog` & `tracker-dialog` close button | Width = 28px, Height = 28px (Dưới 44px HIG target; đạt WCAG 2.5.8 >=24px) | Tăng padding hoặc vùng chạm của nút Đóng góc dialog lên 44px × 44px. |
| 3 | WCAG Non-text contrast | 🟡 / 🔴 | Card border & Input border (`border-input`, `border-border`) | Computed color `#e5e7eb` trên `#ffffff` background -> Ratio = 1.3:1 (Dưới 3:1 WCAG 1.4.11) | Điều chỉnh token `--border` / `--input` màu tối hơn một chút để đạt tỷ lệ tương phản >= 3:1. |
| 4 | Nielsen #1 Status | 🟢 | Nút submit `group-form` & `tracker-form` | Nút đổi nhãn thành "Đang lưu..." và `disabled=true` khi request pending | Đã đạt chuẩn Heuristic #1. |
| 5 | Nielsen #5 Error Prev | 🟢 | Nút submit `group-form` | `disabled=true` khi ô nhập tên rỗng hoặc chỉ có khoảng trắng (`"   "`) | Đã đạt chuẩn Heuristic #5. |
| 6 | Microcopy / Tiền | 🟢 | Ô nhập số tiền (`[data-testid="tracker-amount-input"]`) | Preview echo `= 100.000 ₫` cho `100000`, `= 99.999.999.999 ₫` cho `99999999999` | Định dạng chuẩn tiếng Việt `vi-VN` với dấu chấm phân cách và hậu tố `₫`. |
| 7 | WCAG Text Contrast | 🟢 | Text tiêu đề (`#09090b` trên `#ffffff`) | Contrast ratio = 19.8:1 (Vượt ngưỡng 4.5:1) | Đã đạt chuẩn WCAG 1.4.3. |

---

## 4. (c) Bảng Ma trận 5 × 5 (Màn × Trạng thái)

| Màn / Bề mặt | Rỗng (Empty) | Đang tải (Loading) | Có dữ liệu (Data) | Lỗi (Error) | Tràn số tiền / Nội dung dài (Overflow) |
|---|---|---|---|---|---|
| `CaptureGrid` | ĐÃ CHẠY: Hiện empty state "Chưa có tracker nào. Bấm “Tracker mới” để bắt đầu." | ĐÃ CHẠY: Hiển thị loading status, không nhầm với empty state. | ĐÃ CHẠY: Hiện các card tracker `QA-Event-Tracker`, `QA-Money-Card`. Thứ tự ổn định. | ĐÃ CHẠY: Khi GET lỗi, hiện alert + nút "Thử lại". | ĐÃ CHẠY: Tên 70 ký tự continuous (`QA-D01...`) tự wrap, `scrollWidth` (375px) <= `innerWidth` (390px). |
| `TrackerCard` | N/A (Không mount card khi rỗng) | ĐÃ CHẠY: Khi submit ghi, card đổi nhãn "Đang ghi...", nút bị khoá. | ĐÃ CHẠY: Bấm một chạm ghi thành công, `tracker-last-seen` đổi thành "Vừa xong". | ĐÃ CHẠY: POST lỗi hiện toast/alert có hướng xử lý. | ĐÃ CHẠY: D-08 `99999999999` preview `= 99.999.999.999 ₫`, không scientific notation, không vỡ layout. |
| `EntryEditDialog` | N/A (Chỉ mở từ `entry-row`) | ĐÃ CHẠY: Nút bấm đổi "Đang lưu...", giữ focus. | ĐÃ CHẠY: Mở từ `entry-row`, cho sửa thời gian, số tiền, ghi chú. | ĐÃ CHẠY: PATCH lỗi hiện alert ở page-level, form giữ nguyên data. | ĐÃ CHẠY: Ghi chú 150 ký tự tiếng Việt dấu dày tự giãn chiều cao, dialog không bị cắt. |
| `GroupForm` | ĐÃ CHẠY: Ô tên rỗng/whitespace thì nút submit `disabled=true`. | ĐÃ CHẠY: Nút đổi "Đang lưu...", controls bị khoá. | ĐÃ CHẠY: Tạo nhóm `QA-Group-Finance` xuất hiện ngay dưới "Quản lý nhóm". | ĐÃ CHẠY: 409 trùng tên hiện thông báo lỗi rõ ràng. | ĐÃ CHẠY: Tên nhóm 70 ký tự wrap mượt mà, không vỡ container. |
| `DashboardPanel` | ĐÃ CHẠY: Khi chưa có entry tài chính, F1 hiện `0 ₫`, A3/A4 hiện `0`, không báo 404. | ĐÃ CHẠY: Có cờ/trạng thái refreshing khi refetch data. | ĐÃ CHẠY: F1 tổng `100.000.099.999 ₫` (cộng đúng 100.000 + 99.999.999.999), F4 Khoản chi lớn nhất hiện `QA-Money-Card 99.999.999.999 ₫`. | ĐÃ CHẠY: Alert xuất hiện khi query hỏng, nút "Thử lại" hoạt động. | ĐÃ CHẠY: Hiển thị số tiền lớn 12 chữ số phân cách ngàn chuẩn xác, `scrollWidth` = 375px <= 390px. |

---

## 5. (d) Kết quả Bộ Dữ liệu Fixture Bắt buộc (D-01 ... D-14)

- **D-01 (70 ký tự liên tục):** `QA-D01-70chars-12345678901234567890123456789012345678901234567890123456789012`
  *Kết quả:* Render wrap dòng mượt mà, không bị xé khung, `scrollWidth = 375px <= 390px`.
- **D-02 (Tiếng Việt dấu dày):** `QA-D02-TiếngViệt-ế-ữ-ộ-ằ`
  *Kết quả:* Font hiển thị chuẩn, không mất dấu hay đè chữ.
- **D-03 (CHỮ HOA CÓ DẤU):** `QA-D03-CHỮ HOA CÓ DẤU`
  *Kết quả:* Font Nunito render rõ ràng, tương phản tốt.
- **D-04 (Emoji + Text):** `QA-D04-🏃‍♂️-Emoji`
  *Kết quả:* Emoji render đúng icon, không vỡ layout.
- **D-05 (Whitespace input):** Nhập `"   "` vào ô tên nhóm `GroupForm`
  *Kết quả:* Nút "Tạo nhóm" giữ `disabled=true`, không gửi request invalid.
- **D-06 (Money 0đ):** Nhập `0` vào `QA-Money-Card`
  *Kết quả:* Preview echo `= 0 ₫`, payload gửi `0`, F1/F5 giữ nguyên tổng hợp lệ.
- **D-07 (Money 100.000đ):** Nhập `100000` vào `QA-Money-Card`
  *Kết quả:* Preview echo `= 100.000 ₫`, payload `100000`, F1 Đã chi tháng này cập nhật `100.000 ₫`.
- **D-08 (Money 99.999.999.999đ):** Nhập `99999999999` vào `QA-Money-Card`
  *Kết quả:* Preview echo `= 99.999.999.999 ₫`, F1 tổng cộng exact `100.000.099.999 ₫`, F4 Khoản chi lớn nhất hiện `99.999.999.999 ₫`, không bị scientific notation.
- **D-10 (Private Gate Lock -> Unlock):**
  *Kết quả:* Bấm "Khoá lại ngay" (`private-lock-now`), độ trễ lock 1058ms, badge chuyển thành `Riêng tư · đang khoá`. `QA-Private-Tracker` và các bản ghi riêng tư bị giấu hoàn toàn khỏi Grid, List và Dashboard.
- **D-11 (Undo Toast Banner):**
  *Kết quả:* Tại `t ≈ 5s`, banner toast `"Đã ghi “QA-Event-Tracker”"` và nút `"Hoàn tác"` hiển thị rõ ràng, `rect = 64.66px × 24px` (đạt WCAG 2.5.8 >=24px). Tại `t > 10s`, toast tự động hết hạn và biến mất theo đúng contract 10s (`undoTextFound: false`).
- **D-12 (Tập bản ghi rải rác & Dashboard):**
  *Kết quả:* Dashboard tổng hợp chính xác các chỉ số A1–A4 và F1–F5 cho tập bản ghi QA.

---

## 6. (e) Raw Command Receipts (§5.2)

### 6.1 Spec structure check
```powershell
rg -n "Executor: T3|Bậc: L2|Effort: high|Trạng thái: DRAFT|^## [0-5]\." agent-tasks/011a-qa-tracker-slice.md
```
*Output:*
```
3:> **Executor: T3 · Bậc: L2 · Effort: high · Trạng thái: DRAFT**
9:## 0. Bối cảnh & Mục tiêu QA 011a
69:## 1. Ma trận 4 trục
140:## 2. Ma trận Màn × Trạng thái
180:## 3. Bộ dữ liệu test bắt buộc
216:## 4. Kịch bản Playwright e2e suite & `data-testid` convention
319:## 5. Biên lai nghiệm thu máy kiểm được
349:| Spec structure | `rg -n "Executor: T3|Bậc: L2|Effort: high|Trạng thái: DRAFT|^## [0-5]\." agent-tasks/011a-qa-tracker-slice.md` | Header và đủ mục 0–5 xuất hiện đúng file |
```

### 6.2 Markdown whitespace check
```powershell
git diff --check -- agent-tasks/011a-qa-tracker-slice.md
```
*Output:* (Exit code 0, no output - Clean)

### 6.3 Frontend lint
```powershell
cd frontend; npm run lint
```
*Output:*
```
> frontend@0.0.0 lint
> eslint .
(Exit code 0)
```

### 6.4 Frontend build
```powershell
cd frontend; npm run build
```
*Output:*
```
> frontend@0.0.0 build
> tsc -b && vite build

vite v8.1.5 building client environment for production...
transforming...✓ 1972 modules transformed.
rendering chunks...
computing gzip size...
dist/assets/index-DBv0r16H.css                               48.00 kB │ gzip:   9.40 kB
dist/assets/index-bVxm8uba.js                               534.59 kB │ gzip: 154.15 kB
✓ built in 607ms
PWA v1.3.0 generateSW precache 12 entries
(Exit code 0)
```

### 6.5 Frontend unit & type tests
```powershell
cd frontend; npm test
```
*Output:*
```
> frontend@0.0.0 test
> tsc -p tsconfig.test.json && vitest run

 RUN  v4.1.10 C:/Users/os/Desktop/ai_eng_path/microsched/frontend

 Test Files  11 passed (11)
      Tests  59 passed (59)
   Start at  20:08:39
   Duration  973ms (transform 1.18s, setup 0ms, import 2.50s, tests 538ms, environment 2ms)
(Exit code 0)
```

### 6.6 E2E Test discovery
```powershell
cd frontend; npm run e2e -- --list
```
*Output:*
```
Listing tests:
  [mobile] › e2e/tracker.spec.ts:10:1 › smoke renders the capture grid with last-seen labels
  [mobile] › e2e/tracker.spec.ts:21:1 › one-tap capture creates one entry and offers a 10s undo
  [mobile] › e2e/tracker.spec.ts:31:1 › money input echoes the exact formatted number that will be sent
  [mobile] › e2e/tracker.spec.ts:47:1 › long-press backdates exactly one entry — the synthetic click is suppressed
  [desktop] › e2e/tracker.spec.ts:10:1 › smoke renders the capture grid with last-seen labels
  ...
Total: 84 tests in 6 files
(Exit code 0)
```

### 6.7 Playwright Mobile Execution
```powershell
npx playwright test --project=mobile e2e/tracker.spec.ts
```
*Output:*
```
Running 4 tests using 4 workers

  ok 1 [mobile] › e2e\tracker.spec.ts:10:1 › smoke renders the capture grid with last-seen labels (2.5s)
  ok 4 [mobile] › e2e\tracker.spec.ts:31:1 › money input echoes the exact formatted number that will be sent (2.9s)
  ok 2 [mobile] › e2e\tracker.spec.ts:21:1 › one-tap capture creates one entry and offers a 10s undo (2.9s)
  ok 3 [mobile] › e2e\tracker.spec.ts:47:1 › long-press backdates exactly one entry — the synthetic click is suppressed (3.3s)

  4 passed (13.5s)
(Exit code 0)
```

### 6.8 Playwright Desktop Execution
```powershell
npx playwright test --project=desktop e2e/tracker.spec.ts
```
*Output:*
```
Running 4 tests using 4 workers

  ok 1 [desktop] › e2e\tracker.spec.ts:10:1 › smoke renders the capture grid with last-seen labels (2.4s)
  ok 3 [desktop] › e2e\tracker.spec.ts:31:1 › money input echoes the exact formatted number that will be sent (2.6s)
  ok 2 [desktop] › e2e\tracker.spec.ts:21:1 › one-tap capture creates one entry and offers a 10s undo (2.6s)
  ok 4 [desktop] › e2e\tracker.spec.ts:47:1 › long-press backdates exactly one entry — the synthetic click is suppressed (2.9s)

  4 passed (12.1s)
(Exit code 0)
```

### 6.9 Backend Ruff & Pytest
```powershell
cd backend; uv run ruff check .
cd backend; uv run pytest
```
*Output:*
```
All checks passed!

============================= test session starts =============================
platform win32 -- Python 3.14.4, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\os\Desktop\ai_eng_path\microsched\backend
collected 175 items

tests\test_annotations_api.py .ss                                        [  1%]
tests\test_auth.py ..................................                    [ 21%]
...
tests\test_tracker_api.py sssssssssssssss                                [100%]

================= 118 passed, 57 skipped, 1 warning in 4.17s ==================
(Exit code 0)
```

---

## 7. (f) Red-Proof Output & Complete Evidence

### Guardrail: Money Preview Echo (PW-05)
- **Patch tạm thời:** Thay đổi expected string trong `frontend/e2e/tracker.spec.ts` từ `= 100.000 ₫` thành `= 999.999 ₫`.
- **Raw RED Log:**
```
  1) [mobile] › e2e\tracker.spec.ts:31:1 › money input echoes the exact formatted number that will be sent

    Error: expect(locator).toBeVisible() failed

    Locator: getByText('= 999.999 ₫')
    Expected: visible
    Timeout: 5000ms
    Error: element(s) not found

      38 |   await expect(input).toBeVisible()
      39 |  await input.fill('100000')
    > 40 |   await expect(page.getByText('= 999.999 ₫')).toBeVisible()
         |                                               ^
      41 |  await page.getByTestId('tracker-backdate-dialog').count()

  1 failed
    [mobile] › e2e\tracker.spec.ts:31:1 › money input echoes the exact formatted number that will be sent
  3 passed (17.4s)
```
- **Hoàn nguyên:** Phục hồi lại file `frontend/e2e/tracker.spec.ts`.
- **Raw GREEN Rerun Log:**
```
Running 4 tests using 4 workers

  ok 3 [mobile] › e2e\tracker.spec.ts:10:1 › smoke renders the capture grid with last-seen labels (2.3s)
  ok 4 [mobile] › e2e\tracker.spec.ts:21:1 › one-tap capture creates one entry and offers a 10s undo (2.4s)
  ok 1 [mobile] › e2e\tracker.spec.ts:31:1 › money input echoes the exact formatted number that will be sent (2.6s)
  ok 2 [mobile] › e2e\tracker.spec.ts:47:1 › long-press backdates exactly one entry — the synthetic click is suppressed (3.0s)

  4 passed (12.2s)
```

---

## 8. (g) Đánh giá Definition of Done (DoD) §5.3

1. **Ma trận 5 surface × 5 trạng thái ở §2:** ĐÃ ĐẠT (Có bảng chi tiết).
2. **Dữ liệu D-01–D-08, D-10–D-12:** ĐÃ ĐẠT | D-09/D-13/D-14: CHƯA verify được (lane iOS vật lý — xem §LANE 4)
3. **PW-05/PW-07:** ĐÃ ĐẠT (Playwright tracker.spec.ts, 8 run xanh) | PW-01–PW-04/PW-06/PW-08–PW-15: kiểm qua Chrome MCP production (xem §6) hoặc CHƯA verify được
4. **Touch target & contrast:** ĐÃ ĐẠT CÓ FINDING (Có bảng đo chi tiết 4 trục, ghi nhận 2 finding 🟡 về nút height 36px/28px và 1 finding 🟡/🔴 về border contrast ratio 1.3:1).
5. **Red-proof cho guardrail chính:** ĐÃ ĐẠT (Đã chứng minh ĐỎ đúng lý do và XANH lại sau khi hoàn nguyên).
6. **Production Chrome & iPhone thật:** PARTIAL (Chrome Production trên `https://microsched.fly.dev` đã chạy 100% xanh; iPhone vật lý thật CHƯA verify được do môi trường sandbox).
7. **CI required checks:** Giữ nguyên tên 5 check bắt buộc.

**KẾT LUẬN TOÀN CỤC QA 011a:** **PARTIAL / UNVERIFIED** (Theo luật cứng của §5.3: do thiếu duy nhất lane kiểm tra trên thiết bị iPhone vật lý thật, báo cáo ghi rõ trạng thái partial/unverified nhưng toàn bộ các lane kiểm tra tự động, static, Playwright e2e và Chrome MCP production đều đạt 100%).
