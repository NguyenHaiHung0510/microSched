# 039 — Deferred follow-ups sau baseline QA đầu tiên

> Trạng thái: **DEFER — Owner chốt 2026-08-29.** Đây là backlog permanent, không phải receipt QA,
> không tự mở implementation và không chặn Task 037 trừ khi một finding được nâng thành P0/P1 bởi
> spec/review mới.

## 0. Mục đích

Giữ các phần đã biết là chưa hoàn thiện nhưng không thuộc đường ngắn tới baseline QA đầu tiên. Mỗi mục
ở đây phải tiếp tục mang nhãn `DEFER`, `NOT_RUN` hoặc `PARTIAL`; việc có tên trong backlog không biến nó
thành `PASS` và cũng không cấp authority merge/deploy/Neon/production/device.

Các blocker đang hoạt động **không** nằm ở đây: hoàn tất 035A/PR #185, triển khai 035B notification
batching, dựng QA037 runner và chạy Tầng 1 vẫn là hard-start hiện hành.

## 1. Private visibility boundary — DEFER

Nguồn: scope reconciliation sau PR #186. Các seam dưới đây đã tồn tại trước Task 036 hoặc nằm ngoài
spec UI/UX của Task 036; chúng không phải regression blocker của PR #186 nhưng phải được kiểm lại trong
Task 037:

- lock/TTL local override có thể đi trước `session.private_until` khi `/api/me` chậm hoặc lỗi; screen
  đang mở không được giữ private dialog trong khoảng lệch đó;
- toast và callback mutation đang in-flight không được hiện lại tên/nội dung private sau lock;
- Notes và Subscription phải đóng/reset dialog/draft có thể chứa private data khi visibility đóng;
- xác định contract cho TanStack mutation cache trong RAM sau lock; không được suy `removeQueries` đã
  xoá mutation state;
- test immediate lock/TTL cần path pointer thật hoặc giải thích overlay, delayed/failed `/api/me`,
  in-flight callback và sentinel trong dialog/toast.

Khi mở lại, tách thành spec riêng cho global private boundary; không nhét tiếp vào một PR UI dogfooding.

## 2. Physical device và Web Push thật — NOT_RUN/PARTIAL

- Viewport Chromium 390×844 không chứng minh iPhone/Safari/PWA thật.
- Sau khi 035B live, Owner vẫn phải quan sát notification thực: title/body, một provider delivery theo
  active subscription endpoint, private/generic copy, tap/deep-link và OS attribution. Dòng
  `from microSched` do OS/browser cung cấp không được claim có thể xoá từ payload.
- Real Web Push, iPhone/Safari và device notification chỉ được nâng `PASS` bằng receipt riêng; thiếu
  authority hoặc chưa chạy giữ `NOT_RUN`.

## 3. Offline outbox đầy đủ — giữ Task 017 làm source of truth

Không copy lại scope/acceptance. `agent-tasks/017-offline-outbox.md` vẫn là spec canonical cho Dexie
outbox mọi write domain và persisted read cache. Trạng thái chưa chạy trên iPhone/PWA thật giữ nguyên
`PARTIAL / NOT_RUN` theo `docs/qa-framework.md`; Task 039 chỉ giữ liên kết để việc này không biến mất
sau baseline 037.

## 4. External-model file handoff protocol — EXPERIMENT, chưa thành policy

Pilot hiện nằm ở `agent-tasks/temp/qa037-tier2-external-model-handoff-v0/`: Owner chuyển `prompt.md`
một lần, sau đó T1 và model ngoài trao đổi qua `control.json`, `status.json`, `blocker.md` và
`report.md` dưới một heartbeat duy nhất.

Chưa được promote vào harness vì:

- pilot QA037 chưa chạy end-to-end;
- native subagent tới provider ngoài đã quan sát lỗi `unreadable_encrypted_agent_task`;
- native Sol/Terra/Luna cũng từng gặp `stream disconnected`, nên cần phân biệt transport failure với
  task failure và bảo toàn checkpoint trên đĩa.

Chỉ promote sau retrospective có receipt: một manual handoff ban đầu, ít nhất một blocker round-trip,
terminal report được T1 xác minh độc lập, stop condition xoá heartbeat và không có secret/personal data
trong channel. Mỗi provider/route mới vẫn phải probe riêng; không suy Gemini pass thì Opus/DeepSeek/GLM
cũng pass.

## 5. Cách cập nhật sau QA037

Sau baseline, T1 chỉ thêm vào file này các finding thỏa cả ba điều:

1. không phải P0/P1 đang chặn candidate hoặc làm receipt baseline sai;
2. có Case ID/evidence hoặc ghi rõ `[CHƯA VERIFY]`;
3. Owner chấp nhận defer, hoặc spec hiện hành đã đánh dấu optional/NOT_RUN.

Không gom mọi P2 thành mega-PR. Khi Owner có thời gian/token, chọn từng cụm độc lập, viết child spec,
ad-review rồi mới implementation. Hoàn tất cụm nào thì cập nhật trạng thái tại đây và liên kết PR/receipt;
không xoá lịch sử chỉ vì code đã merge.
