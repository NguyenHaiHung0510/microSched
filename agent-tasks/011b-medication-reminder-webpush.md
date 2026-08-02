# 011b — Nhắc thuốc + nhắc hết hạn sub: hạ tầng Web Push + cron 3-khe

> **Trạng thái: DRAFT — viết bởi T1 (Opus 5) 2026-08-01, phối hợp trực tiếp với chủ (không tự quyết
> một mình).** Đã qua phản biện **T3** (`gemini-3.1-pro-high`) + **T2 Codex**; T1 kiểm tay từng
> finding, sửa các finding thật và ghi rõ chỗ T2 kết luận đúng nhưng lý do/phạm vi sai. Chưa được chủ
> duyệt.
>
> **📝 Cập nhật cùng ngày, sau khi `011a` được viết: `011` tách làm BA lô, không phải hai.**
> `011a` = `tracker_group`/`tracker`/`entry` + lưới ghi + dashboard A1–A4/F1–F5
> (`agent-tasks/011a-tracker-capture-dashboard.md`). `011c` = entity `subscription` + luồng gia hạn
> + F6 + `app_setting` + seam định tuyến (**đã viết 2026-08-01**:
> `agent-tasks/011c-subscription-renewal-settings.md`). **Thứ tự thi công: `011a` → `011c` → `011b`**
> — file này nhắc cả thuốc lẫn sub, mà phần nhắc sub (§3.4 điểm 4) cần `subscription` đã tồn tại;
> làm cuối thì không phải ship một nửa rồi quay lại. Trong file này, mọi tham chiếu tới CRUD
> tracker/entry là `011a`; mọi tham chiếu tới `subscription`/F6/`app_setting` là `011c`.

## 0. Vì sao tách khỏi `011a`, và vì sao file này viết trước

`tracking-brief.md` §12 đã chốt mô hình dữ liệu (tracker thường + `reminder_time`/`reminder_text`,
đã nằm sẵn trong `models.py:339-340` + migration `0001` — **không cần migration cho hai cột này**).
Cái CHƯA từng được thiết kế là **cơ chế bắn nhắc nhở thật**: web push chưa tồn tại một dòng code nào
trong repo, và hạ tầng cron hiện tại (`devops-brief.md` §10) chỉ có **một** job cố định 20:00.

`011a` (CRUD tracker/entry + dashboard) và `011c` (subscription + F6 + `app_setting`) là phần
**cơ học**: mirror `tasks.py`/`notes.py`, phần lớn quyết định đã nằm sẵn trong schema và trong chính
`tracking-brief.md`. `011b` (file này) là phần **có phát sinh quyết định thiết kế mới** trong chính
phiên này (khe cron, giới hạn iOS, bucket theo khe) — đúng loại việc đáng dùng nốt cửa sổ Opus còn
lại. Viết trước, chấp nhận file tham chiếu vài đường ống của `011a` chưa tồn tại.

**Phạm vi file này:** hạ tầng Web Push (VAPID, subscription, service worker) + cron 3-khe + nhắc
thuốc (tracker có `reminder_time`) + nhắc sắp hết hạn subscription (`tracking-brief.md` §9, §11 —
**cùng một đường ống**, không xây hai lần).

## 1. Quyết định đã chốt trong phiên này (2026-08-01, chủ + T1)

### 1.1 Bỏ "một job mãi mãi" — nâng lên **3 job cố định**, KHÔNG scan-liên-tục

`devops-brief.md` §10 (23/07) chốt "MỘT job duy nhất, mãi mãi" khi bài toán còn tưởng chỉ có **một**
giờ nhắc (20:00, một loại thuốc). Nhu cầu thật của chủ đã đổi: toa tạm thời làm phát sinh **nhiều giờ
nhắc khác nhau trong cùng ngày** (ví dụ chủ nêu: thuốc A 8h+16h, thuốc B 20h). Một job cố định ép mọi
giờ dồn về một mốc — thuốc buổi sáng bị nhắc trễ 12 tiếng là hỏng đúng thứ tính năng này tồn tại để
làm. **Đây là note-có-ngày sửa `devops-brief.md` §10, không phải xoá kết luận cũ** — kết luận cũ đúng
với giả định lúc đó (đúng 1 giờ nhắc); giả định đó nay sai.

**Chốt: 3 job Cloud Scheduler cố định, giờ = `08:00` / `15:00` / `19:00` (Asia/Ho_Chi_Minh)** — đúng
đề xuất của chủ. Mỗi job gọi **cùng một endpoint**, khác nhau ở query string:

```
POST /api/cron/reminder?slot=08:00
POST /api/cron/reminder?slot=15:00
POST /api/cron/reminder?slot=19:00
```

Header `Authorization: Bearer <CRON_TOKEN>` giống hệt heartbeat hiện tại (`cron.py:14`,
`require_cron_token`). Server không tự suy ra khe từ giờ hệ thống — khe là tham số tường minh trong
URL, để một người đọc GCP console thấy ngay 3 URL khớp 3 khe mà không cần đọc code.

**Chi phí — kiểm sống 2026-08-01:** Cloud Scheduler cho **3 job free/billing account**; billable job
= **\$0.10/job/31 ngày**, tính theo *job đã định nghĩa*, không theo số lần chạy
([Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing)). Billing account của chủ
đang dùng đúng 1 job (heartbeat) — nâng lên 3 vẫn **\$0, đúng biên free-tier**, nhưng **hết sạch dư
địa**: job thứ 4 bất kỳ (ở bất kỳ dự án nào trong cùng billing account) từ nay tính phí \$0.10/tháng.
Số nhỏ, nhưng đây là lần đầu vượt qua ranh giới "mọi thứ đang free" — đáng một dòng trong
`cost-brief.md` khi thi công.

**⚠️ Rủi ro ghép cặp (cùng họ với sự cố "hai quyết định đúng không tham chiếu nhau" đã bị bắt nhiều
lần trong dự án):** danh sách khe sống ở **hai nơi tách biệt** — hằng số trong code
(`app/domain/reminder.py`, §3) và cấu hình 3 job trên **GCP console** (ngoài repo, không version
control). Đổi khe (thêm/bớt/dời giờ) mà chỉ sửa một bên là hỏng âm thầm: sửa code mà quên sửa job thì
job cũ vẫn gọi `slot=` cũ (không lỗi, chỉ sai giờ); sửa job mà quên sửa code thì `slot=` mới không
khớp `REMINDER_SLOTS` nào ⇒ endpoint trả rỗng, không nhắc gì, cũng không lỗi. **Luật bắt buộc khi thi
công:** endpoint `GET /api/cron/reminder/slots` trả về `REMINDER_SLOTS` hiện tại của code, để một lần
soi tay đối chiếu với GCP console là đủ; ghi rõ trong runbook (`agent-tasks/README.md` hoặc chính PR)
rằng đổi khe phải sửa **cả hai** trong cùng một phiên.

> 📝 **Sửa 2026-08-01 sau phản biện T3.** Bản trước ghi endpoint này *"công khai, không cần
> `require_cron_token`"*. **Sai và không tự thi hành được:** `cron.py:18-22` gắn
> `dependencies=[Depends(require_cron_token)]` ở **cấp router**, nên mọi route đặt trong file đó tự
> động bị gác — endpoint sẽ trả `401` cho đúng cái lần soi tay mà nó sinh ra để phục vụ. **Chốt: nó
> đi chung `require_cron_token` với các job nó đối chiếu** (đối chiếu bằng `curl -H "Authorization:
> Bearer $CRON_TOKEN"`). Đừng "sửa" bằng cách gỡ dependency cấp router hay tạo router thứ hai không
> gác — lịch nhắc thuốc là dữ liệu sức khoẻ, không có lý do gì để trần.

**Bắt buộc khi merge:** thêm **dated note vào `devops-brief.md` §10** ghi rằng "MỘT job duy nhất,
mãi mãi" đã bị thay bởi 3 khe của `011b` và vì sao (giả định gốc là *đúng một giờ nhắc*, nay sai).
Không làm bước này thì hai file cùng đang là "quyết định hiện hành" mà nói ngược nhau — đúng cái bẫy
`CLAUDE.md` bắt phải tránh.

### 1.2 Thuật toán gán khe — khoảng cách tuyệt đối gần nhất, không phải làm tròn xuống

`tracker.reminder_time` là giờ tuỳ ý do chủ gõ (ví dụ 16:00), không nhất thiết trùng khe. Quy tắc gán:

```python
REMINDER_SLOTS = [time(8, 0), time(15, 0), time(19, 0)]

def assign_slot(reminder_time: time) -> time:
    return min(REMINDER_SLOTS, key=lambda slot: abs(
        datetime.combine(date.min, reminder_time) - datetime.combine(date.min, slot)
    ))
```

Khớp đúng ví dụ chủ nêu: 8h→8h (đúng khe), 16h→15h (lệch 1h, gần hơn khe 19h lệch 3h), 20h→19h (lệch
1h). **Không wrap qua nửa đêm** — một `reminder_time` như 02:00 vẫn gán về khe 08:00 (lệch 6h), không
so với khe 19:00 hôm trước; trường hợp này không có trong nhu cầu thật hiện tại, để đơn giản.
**Hoà giải khi cách đều hai khe** (ví dụ 11:30 giữa 8h và 15h — lệch 3.5h cả hai): chọn khe **sớm
hơn** — thà nhắc sớm còn hơn nhắc trễ cho một việc liên quan sức khoẻ. `assign_slot` là hàm thuần, đặt
trong `app/domain/reminder.py`, test bằng bảng ví dụ ở trên — không cần DB để test.

> 🔒 **Mô hình v1 cho thuốc uống nhiều lần/ngày — chốt 2026-08-01 sau phản biện T2.** T2 bắt đúng:
> schema đã khoá chỉ có **một** `tracker.reminder_time`, nên một tracker tên "Thuốc A" không thể giữ
> đồng thời 08:00 và 16:00. **Không thêm entity schedule con**: `tracking-brief.md` §12 đã chốt
> *"KHÔNG entity mới"* + cadence daily-only. Mô hình v1 là **một tracker = một lần uống lặp hàng
> ngày**, không phải một hoạt chất:
>
> | Tracker | `reminder_time` | Khe thật |
> |---|---:|---:|
> | `Thuốc A — sáng` | 08:00 | 08:00 |
> | `Thuốc A — chiều` | 16:00 | 15:00 |
> | `Thuốc B — tối` | 20:00 | 19:00 |
>
> Ba tracker có thể nằm trong cùng group `Toa hiện tại`; dashboard vẫn gom chúng cạnh nhau, còn mỗi
> lần uống có lịch sử tuân thủ riêng — có ích hơn một chuỗi entry không biết thuộc liều sáng hay
> chiều. Tên phải khác nhau (`011a` chống trùng tên), suffix theo buổi là chủ đích chứ không phải
> workaround ngầm. Form đặt nhắc ghi helper: *"Uống nhiều lần/ngày? Tạo một tracker cho mỗi lần
> uống, ví dụ ‘Thuốc A — sáng’ và ‘Thuốc A — chiều’."* Đây là giới hạn v1 chủ có thể veto; nếu sau
> dùng thật thấy phiền mới mở lại schema thành `tracker_reminder`, không lén thêm nó trong lô này.

> 📝 **Thêm 2026-08-01 sau phản biện T3 — lượng tử hoá khe phải NHÌN THẤY ĐƯỢC, đừng im lặng.**
> T3 bắt đúng một ca xấu: `reminder_time = 23:00` gán về khe 19:00, tức **nhắc sớm 4 tiếng**, và với
> thuốc thì nhắc sớm nguy hơn nhắc trễ (bấm ✓ rồi uống sớm, hoặc gạt đi rồi quên hẳn). Đổi thuật
> toán không giải được: mọi luật khác ("khe kế tiếp ≥ giờ nhắc") đều làm **xấu đi** đúng toa thật của
> chủ (16h sẽ thành 19h, trễ 3 tiếng thay vì sớm 1 tiếng). Vấn đề không nằm ở công thức mà ở chỗ chủ
> **không biết là có lượng tử hoá**. ⇒ **Giữ nguyên nearest-slot, nhưng form đặt giờ nhắc phải hiện
> ngay khe thật sẽ bắn, và cảnh báo khi lệch > 2 giờ**: *"Sẽ nhắc lúc **19:00** — lệch 4 tiếng so với
> 23:00. Đặt giờ gần 08:00 / 15:00 / 19:00 hơn nếu cần đúng giờ."* Tính bằng chính `assign_slot`,
> nên logic chỉ có một bản (hiện ở §4.3 bước 4).

**Tại sao không chọn "quét mọi tracker có `reminder_time` ≤ giờ chạy, dồn late-list vào cuối ngày"**
(phương án tôi từng đề xuất trước khi chủ mô tả toa tạm thời): nó chấp nhận trễ vô hạn cho khung sáng
nếu chỉ có 1 job tối — đúng cái toa tạm thời của chủ (uống 2 lần cách nhau 8 tiếng) không chịu được.
3-khe-gần-nhất tốn thêm đúng 2 job Cloud Scheduler (miễn phí, §1.1) để đổi lấy sai số tối đa **~3.5
giờ** thay vì tối đa ~16 giờ.

### 1.3 Giới hạn thật của iOS — noti KHÔNG thể có nút ✓ trên lock-screen

**Đã tra sống 2026-08-01** (do chủ dùng iPhone XS Max, iOS 18.7.9): Safari/iOS **không hỗ trợ mảng
`actions` của Notification API** — nút hành động tuỳ biến trên banner chỉ có ở Chrome/Firefox
([Safari notification actions bị bỏ qua — WebKit forum thảo luận](https://developer.apple.com/forums/tags/wwdc2022-10098),
tổng hợp tại
[MagicBell — PWA iOS limitations](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide)).
Push nói chung hoạt động từ iOS 16.4+ **chỉ khi app đã cài vào Home Screen** (standalone), không chạy
từ tab Safari thường — thứ này app đã đủ điều kiện (`manifest.display: 'standalone'`,
`vite.config.ts:35`). Safari 18.4 thêm "Declarative Web Push" (noti không cần service worker để dựng
nội dung) nhưng đây là tối ưu độ tin cậy, **không** cấp thêm khả năng nút hành động — không cần dùng
ở v1, giữ một luồng imperative Push API (`push` event + `showNotification`) chạy đúng trên mọi trình
duyệt mục tiêu, đỡ phải bảo trì hai nhánh.

**Hệ quả — sửa lại giả định "1 chạm trên lock-screen" từ đầu phiên:** không có nút ✓ trực tiếp trên
banner. Cơ chế thay thế, **tái dùng nguyên xi triết lý "ghi ngay + hoàn tác" đã chốt ở
`tracking-brief.md` §8.1** (không phát minh luồng UX mới):

1. Chạm vào noti (thân noti, không phải nút) → `notificationclick` trong service worker → mở/focus
   PWA tại route `/reminder-confirm?dispatch=<reminder_dispatch.id>`.
2. App tải route đó → gọi endpoint confirmation **idempotent theo dispatch** (§3.6) → chuyển sang màn
   ghi chính, hiện toast 10 giây. Cảm giác vẫn là "ghi ngay"; khác biệt kỹ thuật là hai thiết bị không
   thể tạo hai Entry.
3. Nếu session hết hạn ⇒ login bình thường nhưng phải giữ `return_to=/reminder-confirm?dispatch=...`;
   login xong route chạy tiếp. Nếu private gate khoá ⇒ unlock riêng tư rồi retry (§3.6), không bypass.
   > 🔴 **`return_to` hiện KHÔNG tồn tại ở bất kỳ đâu — T2 bắt 2026-08-01, và việc này thuộc `011b`.**
   > Kiểm tay: UI luôn trỏ `/auth/login` cứng (`App.tsx:59`) và callback OAuth luôn
   > `RedirectResponse(url="/")` (`auth.py:148`). `011c` chỉ dựng seam định tuyến phía client, không
   > đụng auth. Nghĩa là kịch bản thật — noti lúc 8h sáng, session đã hết hạn — sẽ **nuốt mất lượt
   > nhắc**: đăng nhập xong rơi về trang chủ, `dispatch` mất, không ai ghi Entry.
   > ⇒ `011b` phải làm, **đủ ba lớp**: (a) client đính `return_to` (đường dẫn **tương đối**, bắt đầu
   > bằng đúng một `/`, **không** `//` và không có scheme/host) khi chuyển sang login; (b) server
   > giữ nó trong **OAuth `state` đã ký**, không phải query trần — `state` là chỗ duy nhất không bị
   > sửa giữa đường; (c) callback validate lại **same-origin, đường dẫn tương đối** trước khi
   > redirect, không khớp ⇒ về `/`. Test bắt buộc: `return_to=https://evil.example` và
   > `return_to=//evil.example` đều **phải** rơi về `/` (open-redirect là lỗ kinh điển của đúng
   > tính năng này).
4. Nếu offline ⇒ Dexie queue **request confirmation** (dispatch id + stable entry id + thời điểm tap),
   không queue generic create-entry. Hành động vẫn chạy trong tab app, không fetch trần từ service
   worker; auth/private gate vẫn do server thi hành khi outbox flush.

Đây là phát hiện làm **đơn giản hoá** bài toán so với lo ngại ban đầu: không cần thiết kế đường xác
thực riêng cho hành động chạy trong service worker, vì hành động thật chạy trong tab app đã mở.

### 1.4 Idempotency — bảng `reminder_dispatch`

Cloud Scheduler cấu hình được retry (`devops-brief.md` §10) — job có thể gọi lại đúng khe trong cùng
ngày. Không được bắn push hai lần. Bảng mới, dùng chung cho cả nhắc thuốc lẫn nhắc sub:

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | UUIDv7 PK | B1 |
| `subject_type` | `TEXT CHECK IN ('tracker', 'subscription')` | phân biệt hai nguồn nhắc |
| `subject_id` | `UUID NOT NULL` | id của `tracker` hoặc `subscription`; không FK cứng (subject có thể bị xoá mềm, vẫn muốn giữ log) |
| `dispatched_on` | `DATE NOT NULL` | ngày Việt Nam (`+07:00`), không phải UTC — cùng quy ước K14 (`subscription.started_on`/`expires_on`) |
| `status` | `TEXT CHECK IN ('pending','sent','no_device')` | default `pending`; retry dùng lại chính row/id này |
| `attempt_count` | `INTEGER NOT NULL DEFAULT 0 CHECK >= 0` | tăng sau mỗi lượt gửi thật |
| `last_attempt_at` | `timestamptz NULL` | quan sát retry/stuck pending |
| `confirmed_entry_id` | `UUID NULL UNIQUE FK entry(id)` | chỉ tracker-reminder dùng; stable link chống hai thiết bị/tap tạo hai Entry |
| `confirmed_at` | `timestamptz NULL` | thời điểm server chốt confirmation; bất biến sau lần đầu |
| `created_at` | `timestamptz` | B2; không cần `updated_at`/`deleted_at` — chỉ hai cột confirmation đổi đúng một lần |

`UNIQUE (subject_type, subject_id, dispatched_on)`. Bảng này vừa là claim chống hai cron chồng nhau,
vừa là log "đã nhắc ngày nào", vừa cấp **dispatch id ổn định** cho confirmation.

> 🔴 **State machine cuối cùng — sửa qua hai vòng T3 rồi T2/T1.** Bản đầu giữ row dù lỗi tạm ⇒ mất
> nhắc cả ngày (T3 bắt). Bản vá đầu xoá row để retry ⇒ retry sinh **dispatch id mới**; nếu push cũ thật
> ra đã tới thiết bị nhưng response mạng bị mất, notification cũ trỏ tới row đã xoá và không confirm
> được. Sau khi T2 bắt confirmation phải dùng dispatch id, T1 kiểm chéo mới lộ ra khe này. **Không xoá
> row khi retry nữa.**
>
> 1. `INSERT ... ON CONFLICT DO NOTHING` row `status='pending'`, rồi `SELECT ... FOR UPDATE` đúng unique
>    key. Hai cron chồng nhau tuần tự trên cùng row; không có hai lượt gửi đồng thời.
> 2. `status IN ('sent','no_device')` ⇒ đã terminal, bỏ qua. `pending` ⇒ gửi tới mọi subscription,
>    đếm ba `PushResult` (§3.3), tăng `attempt_count`, set `last_attempt_at`.
> 3. **≥1 `SENT`** ⇒ `status='sent'`, commit, `2xx`.
> 4. **0 `SENT` + ≥1 `TEMPORARY_FAILURE`** ⇒ **giữ `status='pending'` và cùng `id`**, commit rồi
>    endpoint trả `5xx` để Cloud Scheduler retry. Một response-lost có thể bắn push trùng, nhưng mọi
>    bản trùng mang **cùng dispatch id**, nên §3.6 vẫn chỉ tạo một Entry.
> 5. **0 `SENT` + chỉ `DEAD_SUBSCRIPTION`, hoặc không có subscription ngay từ đầu** ⇒
>    `status='no_device'`, commit, `2xx`; retry không cứu được.
>
> Crash trước commit để row `pending`; retry dùng lại cùng id. Crash sau push nhưng trước commit có thể
> gửi trùng — chiều đánh đổi đã chọn: thà noti trùng còn hơn mất, và confirmation-idempotency làm phần
> dữ liệu không trùng. **Không giữ transaction DB mở trong khi gọi mạng nếu implementation không thể
> chịu lock dài:** được phép claim/commit `pending` trước rồi acquire advisory lock theo dispatch id
> quanh lượt gửi; nhưng không được đổi id hay cho hai worker gửi song song.

> 🔴 **Dispatch-id cũng là khoá idempotency của hành động XÁC NHẬN — thêm sau T2.** Chống cron gửi
> lặp **không** tự chống Entry lặp: cùng notification có thể bị tap hai lần, hoặc cùng dispatch được
> gửi tới iPhone + desktop rồi tap ở cả hai; nếu URL chỉ mang `tracker` + `slot`, mỗi tab sinh UUIDv7
> mới và `011a` hợp lệ hoá cả hai. Vì vậy payload thuốc phải mang `dispatch_id`, URL là
> `/reminder-confirm?dispatch=<id>` (không còn `tracker`/`slot`), và API confirmation khoá chính dòng
> dispatch đó (§3.6). `confirmed_entry_id` là nguồn sự thật: một dispatch thuốc tạo **tối đa một
> Entry**, kể cả offline, retry, nhiều thiết bị. Notification subscription-expiry không tạo Entry qua
> đường này — nó mở màn subscription để chủ xử lý ở ngoài, đúng S2.

## 2. Migration mới — kiểm `ls backend/alembic/versions/` để lấy đúng số, ĐỪNG tin con số ở đây

Tại thời điểm viết file này head là `0004` — nhưng `011a` (nếu thi công trước) hoặc phiên `010`
(song song) có thể đã thêm `0005`/`0006`. File mới: hai bảng `push_subscription` + `reminder_dispatch`.

```python
# push_subscription — một dòng / một thiết bị đã cấp quyền noti (đơn user, đa thiết bị)
id: UUIDv7 PK
endpoint: TEXT NOT NULL, UNIQUE          # URL endpoint của push service — khoá tự nhiên của 1 thiết bị
p256dh: TEXT NOT NULL                    # public key phía trình duyệt, base64url
auth: TEXT NOT NULL                      # auth secret, base64url
user_agent: TEXT NULL                    # chỉ để chủ tự nhận ra "cái nào là điện thoại" khi dọn tay
created_at, last_seen_at: timestamptz    # last_seen_at cập nhật mỗi lần gửi push THÀNH CÔNG

# reminder_dispatch — xem bảng §1.4; ngoài UNIQUE(subject_type, subject_id, dispatched_on):
status: TEXT NOT NULL DEFAULT 'pending' CHECK IN ('pending','sent','no_device')
attempt_count: INTEGER NOT NULL DEFAULT 0 CHECK >= 0
last_attempt_at: timestamptz NULL
confirmed_entry_id: UUID NULL UNIQUE FK entry(id)
confirmed_at: timestamptz NULL
```

**Không `user_id`** — app một-người-dùng, `session` đã là nguồn sự thật duy nhất về "ai"; phân biệt
theo **thiết bị** (endpoint), không theo người. `push_subscription` không mã hoá — `endpoint`/khoá
public không phải nội dung nhạy cảm theo posture B-hẹp (`tracking-brief.md` §6), và cần `WHERE` được
để dọn theo `endpoint` khi push service trả 410.

Áp bằng tay (`cd backend && uv run alembic upgrade head`, `NEON_MIGRATOR_URL`), xác minh bằng
`information_schema.columns` — luật cứng `CLAUDE.md`, không có ngoại lệ cho migration "nhỏ".

## 3. Backend

### 3.1 VAPID keys

Sinh một lần bằng `py-vapid` (thêm vào `backend/pyproject.toml`): `public_key` + `private_key` (cả
hai là **Fly secret / `.env` local**, không commit — cùng lớp `CRON_TOKEN`). Contact email bắt buộc
theo chuẩn VAPID (`mailto:`, để push service liên hệ nếu app bị lạm dụng gửi spam — không áp dụng
thực tế cho app 1-người-dùng nhưng chuẩn đòi có).

**Public key phục vụ qua API, KHÔNG embed lúc build.** *(Sửa 2026-08-01 sau phản biện T3 — bản trước
ghi "embed vào frontend lúc build".)* Thêm `GET /api/push/vapid-public-key` (sau `require_session`,
cùng router §3.5) trả `{"public_key": "..."}`. Ba lý do: build-time embed khoá cứng frontend vào
**một** cặp khoá, nên local dev và production buộc phải dùng chung khoá hoặc phải build hai bản;
xoay khoá thành một lần build lại + deploy lại thay vì đổi một secret; và `VITE_*` env đi vào bundle
tĩnh nên giá trị cũ còn nằm trong service worker đã precache của thiết bị cũ. Khoá công khai gọi qua
mạng mỗi lần bật nhắc là một request/đời-thiết-bị — rẻ hơn cả ba vấn đề trên.

### 3.2 `app/domain/reminder.py` — thuần, không chạm DB

Chứa `REMINDER_SLOTS`, `assign_slot()` (§1.2), và hàm build payload noti:

```python
def build_medication_payload(
    *, dispatch_id: UUID, tracker_name: str, reminder_text: str | None, is_private: bool
) -> dict:
    # URL = f"/reminder-confirm?dispatch={dispatch_id}".
    # reminder_text là bề mặt công khai CÓ CHỦ ĐÍCH (tracking-brief §6/§12), dùng nếu chủ đã nhập.
    # Fallback: private ⇒ generic "Mở microSched để xem lời nhắc"; public ⇒ tracker_name.
    # TUYỆT ĐỐI không fallback tracker_name khi is_private=True.
    ...

def build_subscription_payload(
    subscription_name: str, expires_on: date, subscription_id: UUID, is_private: bool
) -> dict:
    # URL CHÍNH XÁC: f"/subscription?highlight={subscription_id}" (hợp đồng 011c §9 mục 1).
    # KHÔNG đi reminder-confirm và KHÔNG tự tạo Entry.
    # Parent Tracker private ⇒ generic "Một đăng ký sắp hết hạn", KHÔNG có subscription_name.
    # Public ⇒ "Sắp hết hạn: {name} — còn {n} ngày"; n tính từ VN-today.
    ...
```

> 📝 **Kiểm tay finding riêng tư của T2:** kết luận *"không được fallback tên private ra lock-screen"*
> là **đúng**; phần T2 đề nghị cấm luôn `reminder_text` là **sai với quyết định đã khoá**.
> `tracking-brief.md:97` và §12 ghi `reminder_text` trần **có chủ đích**, chính là câu kín đáo chủ tự
> chọn cho lock-screen (ví dụ `taken micardis?`). Vì vậy thứ tự đúng là:
> `reminder_text` nếu có → nếu thiếu và private thì generic → nếu thiếu và public mới dùng
> `tracker_name`. Subscription không có public `reminder_text`: join parent Tracker; private ⇒ generic,
> public mới dùng `subscription_name`. Test payload phải phủ đủ hai họ và khẳng định
> ciphertext/plain private name không xuất hiện trong JSON.

### 3.3 `app/domain/push.py` — gửi push, dọn subscription chết

Thư viện `pywebpush`. **Không trả `bool`** — T2 bắt đúng rằng `False` đã xoá mất thông tin mà thuật
toán §1.4 cần. Khai enum/result tường minh:

```python
class PushResult(StrEnum):
    SENT = "sent"
    TEMPORARY_FAILURE = "temporary_failure"
    DEAD_SUBSCRIPTION = "dead_subscription"

async def send_push(subscription: PushSubscription, payload: dict) -> PushResult: ...
```

- Gọi `webpush()` với `vapid_private_key`, bắt `WebPushException`.
- **`410 Gone` hoặc `404 Not Found`** từ push service ⇒ subscription đã chết (trình duyệt tự huỷ, ví
  dụ chủ gỡ-cài-lại PWA) ⇒ `DELETE FROM push_subscription WHERE id = ...` ngay trong cùng lượt, trả
  `DEAD_SUBSCRIPTION`.
- Lỗi khác (mạng, 5xx tạm thời) ⇒ log, trả `TEMPORARY_FAILURE`, **không xoá**.
- Thành công ⇒ cập nhật `last_seen_at = now()`, trả `SENT`.

Dispatcher đếm ba enum riêng. **0 `SENT` + ≥1 `TEMPORARY_FAILURE`** ⇒ giữ row/id ở `pending` và trả
5xx để Scheduler retry; **0 `SENT` + chỉ `DEAD_SUBSCRIPTION` hoặc danh sách ban đầu rỗng** ⇒ chuyển
`no_device`. Không suy
nguyên nhân từ việc bảng subscription rỗng *sau* khi gửi — lúc đó không phân biệt được "rỗng từ đầu"
với "vừa dọn hết 410".

### 3.4 `app/web/routers/cron.py` — thêm endpoint `reminder`

```
POST /api/cron/reminder?slot={HH:MM}     require_cron_token, giống heartbeat
GET  /api/cron/reminder/slots            require_cron_token (router-level) — §1.1 đối chiếu tay
```

Luồng `POST /api/cron/reminder`:
1. Parse `slot` **một lần** từ chuỗi `HH:MM` thành `datetime.time`, rồi validate giá trị đã parse thuộc
   `REMINDER_SLOTS` — sai format hoặc không thuộc danh sách ⇒ `422`, không làm gì thêm. Từ đây trở đi
   chỉ so `time == time`; **không** so `assign_slot(...)` với query string. (T2 bắt ambiguity này:
   implement literal `time(8,0) == "08:00"` luôn `False` và mọi job vẫn `200` với 0 reminder.)
2. Tính `today = VN hôm nay` (cùng ép `timezone(timedelta(hours=7))`, **không** `zoneinfo` — đúng lý
   do đã ghi ở `agent-tasks/010a` §2 mục 6: image Python slim trên Fly không đảm bảo tzdata).
3. **Nhắc thuốc:** `SELECT` mọi `tracker` còn sống (`deleted_at IS NULL`) có `reminder_time IS NOT
   NULL`, `kind='health'`, `input_mode='event'`, **và** `assign_slot(reminder_time) == parsed_slot`.
   Với mỗi tracker: **insert-if-absent rồi luôn load row theo unique key**
   `(subject_type='tracker', subject_id, dispatched_on)`; `status='pending'` ⇒ acquire lock + gửi,
   `sent/no_device` ⇒ skip. **Không được viết `có dòng INSERT mới ⇒ gửi`**: retry sau lỗi tạm gặp row
   pending cũ, `ON CONFLICT DO NOTHING` trả 0 rows nhưng vẫn phải gửi lại (§1.4). Sau đó giải mã
   `tracker.name` → build payload theo ba nhánh
   riêng tư §3.2 (payload mang `dispatch_id`, **không** mang tracker id/name trong URL) → gửi tới mọi
   `push_subscription`. Nếu DB có `reminder_time` trên tracker không phải health/event (dữ liệu cũ
   hoặc ghi ngoài API), **skip + `logger.error` kèm tracker.id**, không gửi một notification mà route
   confirm chắc chắn vi phạm K8. Khi `011b` mở rộng `TrackerUpdate`, setting `reminder_time` trên
   tracker không phải health/event phải `422` nên đây chỉ là safety net.
4. **Nhắc sub sắp hết hạn — chỉ chạy ở khe `19:00`** (một lần/ngày là đủ, tránh nhắc 3 lần/ngày cho
   cùng một sub sắp hết hạn; chọn khe cuối ngày vì không gấp theo giờ như thuốc). `SELECT`
   `subscription` còn sống, `canceled_at IS NULL`, `expires_on - today <= 3` (ngưỡng
   `app_setting` — **key `subscription_expiry_lead_days`, mặc định 3, đọc qua
   `expiry_lead_days(db)` của `011c` §4.4**: hàm đó trả mặc định + `logger.error` khi hàng JSON
   hỏng, cố ý **không ném**, để một dòng cấu hình sai không giết luôn lượt nhắc thuốc buổi sáng
   chạy cùng endpoint. Đừng đọc thẳng `AppSetting` ở đây, và đừng hard-code số 3 — nguồn gốc con
   số: `tracking-brief.md` §11 S2) **và** `expires_on >= today` (đã hết hạn thì thôi, đừng
   nhắc số âm), **JOIN parent Tracker** để biết `is_private` và build payload generic khi private
   (§3.2); không lọc private ra khỏi cron vì lời nhắc generic vẫn là chức năng sức khoẻ/tài chính chủ
   đã bật. Cùng cơ chế `reminder_dispatch` (`subject_type='subscription'`) chống lặp, **áp đúng
   5 bước chiếm-chỗ-rồi-trả-lại ở §1.4** — không có biến thể riêng cho sub. Sub còn 3 ngày sẽ tự được
   nhắc lại vào ngày mai với `dispatched_on` mới.
5. Trả ít nhất `{"tracker_reminders_sent": n, "subscription_reminders_sent": m,
   "temporary_push_failures": t, "dead_subscriptions_pruned": k, "dispatches_without_device": d}`
   — số thật, không phải `{"status": "ok"}` trần; `t > 0` đồng thời phải làm endpoint trả **5xx**
   sau khi transaction đã lưu row ở `pending` (§1.4), để Cloud Scheduler thật sự kích retry. Chỉ log warning mà
   vẫn `200` thì cơ chế "retry kế tiếp" trong §1.4 không bao giờ xảy ra.
6. **Giữ nguyên hành vi ghi RSS/uptime của heartbeat cũ ở CẢ BA khe** (không chỉ khe có nhắc) — rẻ,
   và tăng tần suất mẫu canh rò rỉ bộ nhớ của tiến trình always-on từ 1 lần/ngày lên 3 lần/ngày.
   `suspend` không còn là lý do, nhưng tiến trình 256MB sống dài giữa các lần deploy vẫn cần cùng mẫu
   quan sát (`devops-brief.md` §10).

### 3.5 `app/web/routers/push.py` — CRUD subscription, sau `require_session`

```
POST   /api/push/subscribe          body {endpoint, keys: {p256dh, auth}, user_agent?}
DELETE /api/push/subscribe          body {endpoint}   — bấm tắt nhắc, hoặc trước khi đăng ký lại
GET    /api/push/vapid-public-key   → {"public_key": "..."}   — §3.1
```

> 🔒 **Validate `endpoint` trước khi lưu — thêm 2026-08-01 sau phản biện T3.** `endpoint` là chuỗi do
> **client gửi lên** và server sau đó tự `POST` tới nó mỗi lần nhắc ⇒ đúng khuôn SSRF: lưu
> `http://169.254.169.254/...` hay `http://localhost:8080/...` thì cron biến thành công cụ gọi vào
> mạng nội bộ của Fly. Luật: chỉ nhận `https://`, host phải phân giải ra **địa chỉ public** — chặn
> loopback, link-local (`169.254.0.0/16`), private ranges (RFC1918), `.internal` (Fly dùng
> `*.internal` cho mạng riêng). Sai ⇒ `422`.
>
> **Ghi trung thực mức nghiêm trọng:** T3 chấm CRITICAL; ở đây **thấp hơn thế** — endpoint này nằm
> sau `require_session` + allowlist Google một-người-dùng, và khoá VAPID **private** không bao giờ rời
> server (chỉ JWT đã ký đi ra). Kẻ tấn công phải đăng nhập được bằng tài khoản chủ trước đã, lúc đó
> đã có thứ đáng giá hơn. Nhận bản vá vì nó **rẻ** (một hàm ~15 dòng + test), không vì nó chặn một
> đường tấn công đang mở — phòng thủ theo lớp, đúng threat model social-engineering ở
> `devops-brief.md`.

`POST` idempotent theo `endpoint` (`ON CONFLICT (endpoint) DO UPDATE SET p256dh=…, auth=…,
last_seen_at=now()`) — trình duyệt có thể trả subscription cũ y hệt khi gọi lại `subscribe()`, không
được tạo dòng trùng. **Không cần endpoint riêng để "bật nhắc cho tracker X"** — `011b` mở rộng
`TrackerUpdate` của `011a` bằng `reminder_time`/`reminder_text`; chỉ cho set giờ khi
`kind='health' AND input_mode='event'`, ngược lại `422`. `push_subscription` là hạ tầng thiết bị,
tách khỏi cấu hình từng tracker.

### 3.6 `POST /api/reminder-dispatch/{dispatch_id}/confirm` — đúng một Entry / occurrence

Router mới nằm dưới `protected_api` (`require_session`), body:

```json
{"entry_id": "<client UUIDv7>", "occurred_at": "2026-08-01T19:02:11+07:00"}
```

`occurred_at` là **thời điểm tap do client chụp**, không phải lúc outbox cuối cùng gửi được — offline
qua đêm vẫn phải ghi đúng lúc chủ bấm. Bắt buộc tz-aware và reuse validator của `011a`.

Transaction:
1. `SELECT reminder_dispatch WHERE id=:id AND subject_type='tracker' FOR UPDATE`; không thấy ⇒ `404`.
2. Nếu `confirmed_entry_id IS NOT NULL` ⇒ đọc Entry đó kể cả soft-delete và trả `200
   {created:false, entry:...}`; **không restore, không tạo dòng mới**. Undo trước đó là quyết định của
   chủ, tap lặp không được tự đảo Undo.
3. Load Tracker vật lý từ `subject_id`, rồi áp **write gate của `011a`**. Tracker private mà gate đang
   khoá ⇒ `403` với machine code `PRIVATE_UNLOCK_REQUIRED`, message generic không có tên/id tracker;
   không set confirmation. Không được bypass gate chỉ vì request tới từ notification.
4. Xác nhận tracker còn sống, `kind=health`, `input_mode=event`; sai ⇒ `409` generic (cấu hình đã đổi
   sau khi push được gửi), không tạo Entry.
5. Gọi đúng helper create-entry của `011a` với UUID/timestamp từ body, rồi set
   `confirmed_entry_id=entry.id`, `confirmed_at=now()`, commit. Hai thiết bị đua sẽ tuần tự ở
   `FOR UPDATE`; thiết bị thua đi nhánh 2.

API create Entry trực tiếp của `011a` vẫn idempotent theo `entry_id`; endpoint này thêm idempotency
**theo occurrence**. Cả hai lớp đều cần: outbox có thể gửi lại cùng body, còn hai thiết bị có hai UUID
khác nhau.

Frontend gặp `PRIVATE_UNLOCK_REQUIRED` ⇒ mở flow `PrivateGate` hiện có, giữ nguyên body trong outbox,
sau unlock retry **cùng `dispatch_id` + `entry_id` + `occurred_at`**. Nếu offline thì cứ queue; không
có "unlock offline" và không tự ghi public. Notification body/name vẫn generic theo §3.2 nên trước
unlock không rò nội dung.

## 4. Frontend

### 4.1 Đổi chiến lược `vite-plugin-pwa`: `generateSW` → `injectManifest`

`vite.config.ts:15-44` hiện dùng `generateSW` (Workbox tự sinh toàn bộ service worker, không cho chèn
code). Xử lý `push`/`notificationclick` bắt buộc tự viết service worker. Đổi:

```ts
VitePWA({
  strategies: 'injectManifest',
  srcDir: 'src',
  filename: 'sw.ts',
  injectManifest: { /* giữ globPatterns/globIgnores hiện có, chuyển vào đây */ },
  registerType: 'autoUpdate',
  manifest: { /* không đổi */ },
})
```

File mới `frontend/src/sw.ts`: giữ nguyên phần precache (Workbox `precacheAndRoute(self.__WB_MANIFEST)`
— placeholder bắt buộc của `injectManifest`, mất placeholder này = build lỗi ngay, không lỗi ngầm) +
thêm:

```ts
self.addEventListener('push', (event) => {
  // ⚠️ event.data CÓ THỂ null — push service cho phép gửi push RỖNG, và bản nháp trước
  // (`event.data?.json()` rồi dùng thẳng `data.title`) sẽ ném TypeError trong luồng service
  // worker: không có màn hình nào hiện lỗi, chỉ là "hôm nay không thấy nhắc". Fallback bắt buộc.
  let data: { title?: string; body?: string; url?: string } = {}
  try { data = event.data?.json() ?? {} } catch { data = {} }
  event.waitUntil(self.registration.showNotification(data.title ?? 'microSched', {
    body: data.body ?? 'Bạn có một lời nhắc.',
    icon: '/microsched.svg',
    data: { url: data.url ?? '/' },   // '/reminder-confirm?dispatch=<reminder_dispatch.id>'
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(self.clients.matchAll({ type: 'window' }).then((clients) => {
    const existing = clients.find((c) => 'focus' in c)
    if (existing) { existing.navigate(event.notification.data.url); return existing.focus() }
    return self.clients.openWindow(event.notification.data.url)
  }))
})
```

> 🔴 **`navigateFallbackDenylist` KHÔNG tồn tại dưới `injectManifest` — kiểm tay 2026-08-01 sau
> phản biện T2, và đây là bẫy nặng nhất của §4.1.** Option đó thuộc `GeneratePartial`
> (`workbox-build/build/types.d.ts:286`, trong khối `178-348`), còn
> `InjectManifestOptions = BasePartial & GlobPartial & InjectPartial & …` (`types.d.ts:487`) **không
> gồm `GeneratePartial`**. Nghĩa là "giữ nguyên option cũ" ở `vite.config.ts:22` là **không làm được**
> — nó sẽ bị bỏ qua (im lặng, hoặc lỗi type), và cùng lúc `/auth/*` + `/api/*` mất hàng rào. Đúng
> cái sự cố mà comment ngay tại `vite.config.ts` mô tả: nút đăng nhập câm.
> ⇒ **Chuyển sang code trong `sw.ts`**, không phải config:
> ```ts
> import { createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
> import { NavigationRoute, registerRoute } from 'workbox-routing'
> precacheAndRoute(self.__WB_MANIFEST)
> registerRoute(new NavigationRoute(createHandlerBoundToURL('index.html'), {
>   denylist: [/^\/auth\//, /^\/api\//],
> }))
> ```
> Nghiệm thu phải kiểm **bốn** đường trên bản build thật: `/auth/login` (đi tới server, không bị SW
> nuốt) · `/api/*` · và hai deep link `/reminder-confirm`, `/subscription` (phải trả `index.html`).

**Rủi ro thi công thật cần đo tay trước khi tin spec này**: `injectManifest` đổi cách Workbox build
service worker — cần chạy `npm run build` xong kiểm `dist/sw.js` có đúng cả route-caching cũ (nay là
`NavigationRoute` + denylist viết tay theo hộp trên) lẫn hai listener mới. Đây thuộc "thử trước khi code" mà chủ đã nói
sẽ làm — ghi vào Definition of Done, không chặn viết spec này.

### 4.2 Route `/reminder-confirm` — ghi ngay, idempotent theo dispatch

> 🔴 **Vá 2026-08-01 (T1, lúc viết `011c`) — file này giả định một router chưa từng tồn tại.**
> Đo tay cùng ngày: `App.tsx:104-125` chuyển màn bằng `useState`, `package.json` **không có**
> `react-router`. Nghĩa là cả hai deep link của lô này (`/reminder-confirm?dispatch=…` ở đây và URL
> màn subscription ở §3.2) không có đường nào để tới, và `navigate('/')` dưới kia không có hàm nào
> để gọi. Lỗ nằm **giữa** `011a` (không cần route) và file này (cần, nhưng tưởng đã có) — không spec
> nào nhận.
> **Đã vá bằng cách giao cho `011c`** (`agent-tasks/011c-subscription-renewal-settings.md` §5.1):
> seam tự viết ~40 dòng ở `frontend/src/lib/route.ts` (`usePath()` + `navigate()` trên
> `history.pushState`/`popstate`), **không thêm `react-router`**; `App.tsx` rẽ nhánh theo path.
> `011c` chạy trước lô này nên tới đây seam đã có sẵn. **Việc của `011b` chỉ là thêm một nhánh
> `/reminder-confirm`** — không dựng router, không đổi cơ chế tab. Nếu vì lý do nào đó `011c` bị bỏ
> qua, **dừng lại và báo T1**, đừng tự dựng router thứ hai.
> Backend đã sẵn sàng cho tải nguội: `SPAStaticFiles` trả `index.html` cho path không khớp file
> (`main.py:28-37, 102`) — đã kiểm, không phải giả định. Nhưng §4.1 đổi sang `injectManifest` thì
> phải giữ `navigateFallbackDenylist` như cũ, nếu vỡ thì deep link chết chung với nút đăng nhập.

Component `ReminderConfirm.tsx` đọc **chỉ** `dispatch` từ query; lúc mount sinh một UUIDv7 + chụp
`occurred_at` +07 một lần, giữ ổn định qua mọi render/retry, rồi gọi
`POST /api/reminder-dispatch/{dispatch}/confirm` (§3.6). **Không** gọi thẳng generic create-entry và
không nhận `tracker`/`slot` từ URL — đó là bản nháp trước T2, tạo duplicate khi tap ở hai thiết bị.

- `201 created=true` hoặc `200 created=false` ⇒ `navigate('/')`, hiện cùng toast 10 giây. Với
  `created=false`, toast ghi *"Lần uống này đã được ghi"*; nút Hoàn tác trỏ đúng `confirmed_entry_id`
  server trả về, không trỏ UUID client thua cuộc.
- `PRIVATE_UNLOCK_REQUIRED` ⇒ mở `PrivateGate`; unlock xong retry nguyên request ổn định. Không hiện
  tên tracker trước unlock.
- Dispatch không tồn tại / subject đã đổi/xoá ⇒ toast lỗi generic rồi `/`; không trắng màn hình.
- Offline ⇒ queue **endpoint confirmation này** trong Dexie, không queue generic create-entry. Đây là
  seam bắt buộc để idempotency nhiều thiết bị còn đúng sau reconnect.

Push subscription-expiry dùng URL màn subscription (011c), không mount route này và không tự ghi
Entry — chủ còn phải trả tiền ở ngoài theo S2.

### 4.3 Đăng ký nhắc — nằm trong form sửa tracker của `011a`

Toggle "Bật nhắc nhở" + input giờ chỉ hiện khi tracker `kind='health'` + `input_mode='event'` — đây là
đường duy nhất mà tap notification có thể tạo Entry không cần hỏi thêm field (§3.6/K8). Tracker
finance/money/quantity không hiện toggle; muốn nhắc kiểu khác là scope tương lai, không tạo một push
mà bấm xong chắc chắn `422`. Bật lần đầu (chưa có
`push_subscription` nào trên thiết bị này):
1. **Chỉ trên iOS**, kiểm `window.matchMedia('(display-mode: standalone)').matches` — `false` ⇒ dừng,
   hiện hướng dẫn *"Cài microSched vào Màn hình chính trước khi bật nhắc — Safari không cho web
   thường gửi thông báo"* (đúng giới hạn iOS §1.3, không phải bug).
   > 📝 **Sửa 2026-08-01 sau phản biện T3.** Bản trước bắt điều kiện này cho **mọi** nền tảng. Sai:
   > Chrome/Edge desktop và Chrome Android gửi push được trong **tab thường**, không cần cài PWA — áp
   > chung sẽ từ chối oan đúng cái máy chủ dùng để ngồi làm việc. Điều kiện iOS-only:
   > `/iP(hone|ad|od)/.test(navigator.platform) || (navigator.platform === 'MacIntel' &&
   > navigator.maxTouchPoints > 1)` — nhánh sau bắt iPad iOS 13+ tự nhận là Mac. Nếu không phải iOS
   > ⇒ bỏ qua bước 1, đi thẳng bước 2; `Notification.requestPermission()` tự báo lỗi nếu trình duyệt
   > thật sự không hỗ trợ. Test bắt buộc: cùng luồng bật nhắc chạy được trên Chrome desktop tab
   > thường (chính là môi trường `frontend/e2e/` chạy Playwright — áp luật cũ thì e2e không test nổi
   > luồng này).
2. `Notification.requestPermission()` — `denied` ⇒ hiện hướng dẫn mở lại quyền trong Cài đặt iOS,
   không tự ý thử lại (iOS không cho JS re-prompt sau khi bị từ chối).
3. `granted` ⇒ `GET /api/push/vapid-public-key` (§3.1 — **không** đọc từ `import.meta.env`) →
   `registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey:
   urlBase64ToUint8Array(key) })` → `POST /api/push/subscribe`. `applicationServerKey` nhận
   `BufferSource`, chuỗi base64url phải chuyển sang `Uint8Array` — bỏ bước này thì `subscribe()` ném
   `InvalidCharacterError`, một bẫy kinh điển của Web Push.
4. Chỉ SAU khi có subscription mới `PATCH` `reminder_time`/`reminder_text` lên tracker — tránh trạng
   thái "đã đặt giờ nhắc nhưng không có thiết bị nào để nhắc" mà chủ không biết.

**Nếu `011a` build trước và đã tồn tại form sửa tracker** khi thi công `011b`: chèn đúng khối trên vào
form đó, không tạo màn riêng. **Nếu `011b` bị buộc build trước `011a`** (đảo thứ tự thi công): cần một
form tối giản độc lập chỉ có `reminder_time`/`reminder_text`/toggle, gọi thẳng `PATCH
/api/tracker/{id}` của domain tracker (giả định domain đã tồn tại dù chưa có UI CRUD đầy đủ) — không
nên xảy ra nếu theo đúng thứ tự đề xuất ở §0.

## 5. Cấu hình GCP thủ công (runbook, chủ tự tay làm hoặc giao T2 có ảnh chụp từng bước)

1. Sửa job hiện có (`0 20 * * *` → giữ nguyên làm job `19:00`? hay xoá tạo lại) — **khuyến nghị: xoá
   job cũ, tạo mới 3 job** để tên job phản ánh đúng khe (`reminder-08`, `reminder-15`, `reminder-19`)
   thay vì thừa kế tên/lịch sử của job heartbeat gốc — dễ đọc hơn khi có sự cố, không thay đổi ý
   nghĩa chức năng.
2. Mỗi job: **Target = HTTP** (không phải Pub/Sub — bẫy đã ghi ở `devops-brief.md` §10), URL đúng
   §1.1 (kiểm khoảng trắng đuôi — bẫy đã gặp lúc tạo job đầu tiên), method `POST`, **HTTP headers**
   custom `Authorization: Bearer <CRON_TOKEN>` (KHÔNG dùng mục "Auth header" của Scheduler — đè mất
   header tự viết, bẫy đã ghi cùng chỗ).
3. Timezone job = `Asia/Ho_Chi_Minh` cho cả 3 (không phải UTC rồi tự trừ giờ trong cron expression).
4. Force-run thử cả 3 job, kiểm response body có `tracker_reminders_sent`/`subscription_reminders_sent`
   hợp lý (0 nếu chưa có tracker nào đặt `reminder_time` — đúng, không phải lỗi).
5. Đối chiếu `GET /api/cron/reminder/slots` với đúng 3 URL vừa tạo trên console (§1.1 luật bắt buộc).

## 6. Không được làm

- Không quét DB theo chu kỳ ngắn hơn cửa sổ idle 5 phút của Neon (`cost-brief.md` §7 — bất biến toàn
  dự án, sự cố 22/07).
- Không thêm job Cloud Scheduler thứ 4 trở lên mà không xét lại `cost-brief.md` (§1.1 — đã hết
  free-tier).
- Không dùng mảng `actions` của Notification API làm đường chính — không chạy trên iOS (§1.3); có thể
  thêm như progressive enhancement cho Chrome/Android **sau**, không phải v1.
- Không xây đường xác thực riêng cho `notificationclick` — nó chạy trong ngữ cảnh app đã đăng nhập
  (§1.3 điểm 3), thêm cơ chế riêng là giải một vấn đề không tồn tại.
- Không tạo bảng `push_subscription` gắn `user_id` — app một người dùng, phân biệt theo thiết bị.
- Không xoá `push_subscription` khi push lỗi tạm thời (mạng, 5xx) — chỉ xoá khi push service xác nhận
  410/404 (§3.3).
- Không nhắc sub hết hạn ở cả 3 khe — chỉ khe `19:00`, tránh trùng lặp vô ích (§3.4 điểm 4).
- Không dùng `tracker.name` làm fallback payload khi tracker private; `reminder_text` vẫn được phép vì
  đã khoá là bề mặt public do chủ tự viết (§3.2).
- Không cho `/reminder-confirm` gọi generic create-entry trực tiếp; bắt buộc đi endpoint confirmation
  khoá `reminder_dispatch` (§3.6), nếu không hai thiết bị tạo hai Entry.
- Không thêm entity lịch con trong v1; thuốc nhiều lần/ngày dùng một tracker/mỗi lần uống (§1.2).
- Không dùng `zoneinfo` cho phép tính "hôm nay VN" — cùng lý do offset cố định đã ghi ở `010a` §2.6.

## 7. Nghiệm thu — test tự động + ba phép đo tay

**Test bắt buộc, mỗi bài phải biết đỏ khi gỡ luật:**

- `assign_slot`: ba khe, tie chọn sớm, `23:00→19:00`; router parse `"08:00"` thành `time(8,0)` và
  ba URL thật đều match ít nhất một tracker fixture.
- `PushResult` + dispatch state: sent/temp/dead; hỗn hợp dead+temp giữ **cùng row/id** ở `pending` +
  endpoint 5xx; chỉ dead hoặc bảng rỗng chuyển `no_device`; ≥1 sent chuyển `sent`. Retry/crash phải
  reuse đúng dispatch id.
- Private payload: tracker có `reminder_text` dùng đúng text public; thiếu text thì **không chứa
  tracker.name** và dùng generic; public thiếu text mới fallback name. Subscription có parent private
  cũng không chứa `subscription.name`.
- Hai request confirm cùng dispatch nhưng hai `entry_id` khác nhau (mô phỏng hai thiết bị, chạy đồng
  thời) ⇒ đúng một Entry + cùng `confirmed_entry_id`; gửi lại qua outbox ⇒ vẫn một dòng.
- Private gate khoá ⇒ confirm `403 PRIVATE_UNLOCK_REQUIRED`, 0 Entry, 0 confirmation; unlock rồi retry
  cùng body ⇒ một Entry.
- Tracker reminder không phải health/event ⇒ PATCH `422`; safety-net cron skip + log, không gửi.
- Build `injectManifest` giữ `navigateFallbackDenylist`; push payload rỗng vẫn hiện fallback, không ném.

**Ba phép đo tay đã nói trước với chủ, không chặn khoá spec nhưng chặn merge:**

1. **Test thật trên iPhone XS Max / iOS 18.7.9 của chủ**: cài PWA → xin quyền → nhận 1 push thật →
   bấm vào → xác nhận mở đúng route. Nên làm **trước** khi viết code phần push thật, ngay sau khi
   `injectManifest` build được (§4.1) — rẻ nhất là test cái khung rỗng trước khi lắp logic nhắc thuốc
   lên trên.
2. **`injectManifest` có giữ đúng hành vi `navigateFallbackDenylist` hiện tại không** — nếu vỡ, nút
   đăng nhập câm lại y hệt sự cố đã từng gặp và được ghi lại trong chính file `vite.config.ts`.
3. Ngưỡng "sắp hết hạn 3 ngày" thuộc `app_setting`; **`011c`** phải tạo CRUD + seed/default cho nó
   (`tracking-brief.md` §11 S2 nói "hằng số `app_setting`, chưa cần per-sub"). `011a` cấm chạm
   `app_setting`; bản nháp trước giao việc này cho `011a` là mâu thuẫn scope, T2 đã bắt và sửa ở đây.
   📝 **2026-08-01: `011c` đã viết xong** (`agent-tasks/011c-subscription-renewal-settings.md` §4.4)
   — key là `subscription_expiry_lead_days`, mặc định 3, biên 0–30, và **CRUD `app_setting` chạy qua
   allowlist hằng số**. Lý do allowlist quan trọng với chính lô này: `private_gate.py:19-21` dùng
   chung bảng đó cho `private_pin` (chứa hash Argon2id của PIN 6 chữ số), `private_unlock_throttle`
   và `private_unlock_ttl_minutes`; một CRUD tổng quát sẽ đẩy hash PIN ra client. Nếu `011b` cần đọc
   thêm bất kỳ setting nào, **thêm key vào allowlist của `011c`**, đừng mở đường đọc tự do.

## 8. Hai judgment call chủ veto được trước khi giao executor

1. **Một tracker = một lần uống hằng ngày** (§1.2), nên thuốc A sáng/chiều là hai tracker cùng group;
   không thêm `tracker_reminder` child ở v1. Đây là cách duy nhất vừa phục vụ toa thật vừa giữ quyết
   định khoá "không entity mới" trong `tracking-brief.md` §12.
2. **Reminder chỉ bật cho health/event** (§3.4/§4.3), vì confirm một chạm không thể tự bịa amount hay
   quantity. Schema vật lý rộng hơn nhưng API/UI v1 cố ý hẹp.

T3 chưa soi hai judgment call này vì chúng phát sinh từ review T2. Trước thi công, chủ chỉ cần veto
nếu muốn *một tracker chứa nhiều lịch*; nếu không, cả hai mặc định được chấp nhận như quyết định v1.
