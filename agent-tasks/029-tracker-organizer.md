# Task 029 — Organizer nhóm và tracker trước “Nhịp ghi gần đây”

> Trạng thái: 📋 READY — owner chốt hướng sản phẩm 2026-08-24; chưa implement
> Executor đề xuất: T2 Terra · Bậc: medium · Effort: high · Skill gợi ý: Playwright · MCP cần: không có

## 1. Mục tiêu người dùng

Tracker screen phải ưu tiên việc tổ chức và sửa dữ liệu trước phần phân tích:

1. group management, tracker management và “Bản ghi gần đây” đều nằm **trước**
   `Nhịp ghi gần đây` trong visual/DOM order;
2. group thật và tracker chưa có group nằm trong cùng một organizer có thể gập/mở;
3. `Chưa phân nhóm` chỉ là nhóm ảo an toàn, không tạo row hay ID giả;
4. hành vi capture/sort động đang khóa vẫn giữ nguyên trong phase an toàn này;
5. hút thuốc, rượu/bia, billiards hoặc hoạt động người dùng thấy “xấu” vẫn chỉ là tracker cấu
   hình bình thường — không có entity/flag/label nhạy cảm hard-code.

## 2. Bằng chứng hiện trạng và quyết định an toàn

- [QUAN SÁT] `frontend/src/TrackerScreen.tsx:80-112` tải riêng groups, trackers và 20 entries
  gần nhất. `:349-431` đặt subscription + `CaptureGrid` + `DashboardPanel`; `:433-507` mới tới
  recent records, `:509-575` tracker management và `:577-631` group management.
- [QUAN SÁT] chuỗi `Nhịp ghi gần đây` nằm trong `frontend/src/DashboardPanel.tsx:285`, nên
  DashboardPanel hiện đang đứng trước cả ba vùng owner muốn ưu tiên.
- [QUAN SÁT] `frontend/src/TrackerScreen.tsx:131-145` dùng frozen membership order;
  `frontend/src/tracker-ui.ts:100-110` xếp theo `entry_count_30d DESC`, `last_entry_at DESC`,
  rồi `name`; regression tests ở `frontend/src/tracker-ui.test.ts:41-58`.
- [QUAN SÁT] `docs/tracking-brief.md:151` khóa dynamic grid theo tần suất + gần đây. Model
  `backend/app/domain/models.py:324-396` có `tracker_group.position`, `tracker.group_id` nullable,
  nhưng không có `tracker.position`.
- [QUAN SÁT] `backend/app/domain/tracker.py:494-501` xếp group theo `position, created_at`;
  `:564-572` xóa group và FK đưa tracker về `group_id=NULL`; `:576-583` trả tracker đang thấy.
- [QUAN SÁT] `_group_counts()` ở `backend/app/domain/tracker.py:516-529` cố ý áp privacy +
  soft-delete gate vì count đi vào confirmation; khi khóa private, count không gồm tracker riêng
  tư. Nhưng route DELETE ở `backend/app/web/routers/tracker.py:125-130` nhận `session` rồi không
  truyền nó xuống `TrackerStore.delete_group()`, nên backend hiện vẫn có thể detach hidden private
  tracker bằng FK `ON DELETE SET NULL`.
- [QUAN SÁT] `backend/app/domain/models.py:324-351` giữ `TrackerGroup` ở `Gate.NONE`, còn `Tracker`
  là `Gate.APPLIES`. `docs/tracking-brief.md:61-64` khóa private thành auth/display gate theo
  session: phải unlock trước thao tác ghi vào dữ liệu private; đây không phải encryption key.
- [SUY LUẬN] “Phải unlock trước khi xóa group” là safety guarantee, không chỉ affordance UI: action
  này thay `group_id` của mọi member, gồm member đang bị ẩn. Gate phải chặn **mọi** group DELETE
  khi khóa đóng, trước lookup group/member. Chặn có điều kiện theo “group có private tracker” sẽ
  biến `403`/`204` thành side channel; trade-off được chấp nhận là group chỉ có public tracker cũng
  phải unlock để xóa.
- [SUY LUẬN] Group trực tiếp capture grid trong phase này sẽ thay thứ tự global dynamic đã khóa.
  Vì vậy organizer mới chỉ tổ chức/điều hướng/management cells; capture grid hiện tại vẫn là vùng
  nhập duy nhất và giữ nguyên thuật toán.
- [KHÔNG BIẾT] Người dùng có muốn lưu trạng thái fold qua thiết bị hay không. Phase này cố ý
  không tạo preference vì chưa có quyết định đó và không cần DB/API.

## 3. Visual và DOM order đã khóa

`TrackerScreen` sau task này có đúng thứ tự:

```text
1. Header + action tạo tracker
2. Subscription card hiện hành
3. CaptureGrid hiện hành (một input/capture surface duy nhất)
4. Organizer “Nhóm & tracker”
5. “Bản ghi gần đây”
6. DashboardPanel, bắt đầu bằng “Nhịp ghi gần đây”
```

Điều này không đổi query, analytics hay capture semantics. Không render bản sao input trong
organizer; một tracker management cell có action “Ghi” để focus/scroll tới cell tương ứng trong
CaptureGrid bằng `tracker.id`.

## 4. Organizer thống nhất

### 4.1 Sections

- Một Card duy nhất, heading `Nhóm & tracker`; không còn hai card rời `Quản lý tracker` và
  `Quản lý nhóm` bên dưới dashboard.
- Mỗi group thật là một section/accordion theo order API `position, created_at`.
- Section cuối luôn là **`Chưa phân nhóm`**, lấy các visible trackers có `group_id === null`.
- Mỗi section có header với tên, số tracker **đang thấy**, disclosure button và group actions.
  Tracker cells bên trong đi theo **existing frozen global order rồi filter theo membership**;
  tuyệt đối không alpha-sort hoặc thêm `tracker.position`.
- Empty state của group thật vẫn có actions rename/delete và text “Chưa có tracker”. Empty state
  nhóm ảo có text “Tracker chưa thuộc nhóm sẽ xuất hiện ở đây”.
- Fold state chỉ ở React memory của screen, key bằng group UUID và sentinel UI nội bộ; mặc định
  expanded khi mount, reset khi reload. Không ghi localStorage, IndexedDB, `app_setting` hay API.

### 4.2 Tracker management cell

Mỗi cell hiển thị tên, kind/input mode bằng nhãn generic, privacy state và các action:

- `Ghi`: focus capture cell hiện hành; không tạo entry;
- `Sửa`: mở form hiện hành;
- `Chuyển nhóm`: chọn group thật hoặc `Chưa phân nhóm`;
- `Xóa`: dùng soft-delete/undo contract hiện hành.

Cell không có fixed height; tên dài wrap. Không lộ raw IDs. Actions vẫn chạm được trên iPhone,
không sống bằng hover/kebab không có accessible trigger.

### 4.3 Nhóm ảo `Chưa phân nhóm`

Đây là view projection, không phải domain object:

- không có UUID; sentinel chỉ tồn tại trong TypeScript và không được serialize;
- không xuất hiện trong group create/update/reorder/delete API;
- chọn nó khi move tracker gửi đúng `{"group_id": null}`;
- không rename, delete, reorder hoặc hiển thị `position`;
- luôn render cuối, bất kể group order;
- count và membership chỉ tính từ tracker rows API đang cho phép đọc. Không lấy `total_count`
  hoặc suy ra số private tracker bị khóa.

### 4.4 Group management và thao tác phá hủy

- `Tạo nhóm` là action ở header organizer. Rename/reorder/delete nằm trong header group thật.
- Reorder chỉ đổi `tracker_group.position` bằng API hiện có; dùng move up/down hoặc accessible
  menu, không thêm drag-and-drop trong phase này.
- Xóa group phải nói rõ “Các tracker trong nhóm sẽ chuyển sang Chưa phân nhóm”; không xóa
  tracker/entry. Sau success invalidate groups + trackers một lần và giữ order động hiện hành.
- Khi private lock đóng, UI không render active delete action; cùng vị trí là CTA “Mở private để
  xóa nhóm”. Tap chỉ mở unlock flow, không mở confirmation và không gửi DELETE; đây là lớp UX.
  Backend **bắt buộc** từ chối mọi group DELETE bằng gate ở §6, kể cả request trực tiếp, stale tab,
  outbox replay và group chỉ có public tracker. Người dùng phải unlock để thấy đủ impact.
- Count trong confirmation chỉ fetch/render sau unlock và lúc đó gồm mọi live member public +
  private. Không query, hiển thị hay log số hidden trước đó. Nếu gate relock khi dialog đang mở,
  đóng dialog/purge private projection; request lỡ gửi vẫn bị backend trả `403` và không detach gì.
- Error phải giữ dialog/state để retry; optimistic move/rename/delete rollback về đúng group và
  focus action đã bấm.

## 5. Không tạo phân loại “hoạt động xấu”

Các ví dụ như hút thuốc, uống rượu/bia, chơi billiards được tạo bằng đúng form/config hiện hành:

```text
Tracker(kind hiện có, input_mode hiện có, group_id nullable, is_private hiện có)
Entry(value/amount/note theo kind hiện có)
```

Cấm trong scope 029 và follow-up trực tiếp:

- `bad_activity`, `vice`, `sensitive_activity` table/column/enum;
- danh sách tên hard-code, seed, regex hay nhánh UI dựa trên “thuốc”, “rượu”, “billiards”;
- telemetry/analytics riêng, cảnh báo đạo đức, badge đỏ hoặc mặc định private theo label;
- gửi tên tracker vào notification/log để suy luận thói quen.

Người dùng vẫn có thể tự đặt tên, group và bật `is_private`. Nếu một kind cấu hình hiện có không
đủ cho use case, đó là proposal generic riêng, không phải lý do thêm sensitive entity ở task này.

## 6. API/DB/migration

- **Không migration. Không model/endpoint mới.** Giữ `TrackerGroupRead`, `TrackerRead`, group CRUD,
  tracker PATCH và list entries hiện hành. Scope backend duy nhất của 029 là harden endpoint
  DELETE group đang có; không đổi `TrackerGroup.__privacy_gate__ = Gate.NONE`.
- `DELETE /api/tracker/groups/{group_id}` phải truyền verified session xuống domain/store. Khi
  private chưa unlock, domain gate chạy **trước mọi query existence/group/member** và trả:

  ```text
  HTTP 403
  {"detail":{"code":"PRIVATE_UNLOCK_REQUIRED","message":"Unlock private mode to delete a tracker group"}}
  ```

  Mọi group ID existing/missing và public-only/mixed-private có cùng status/body shape; transaction
  không xóa group và không đổi bất kỳ `tracker.group_id`/Entry nào. Router/UI không được là lớp
  bảo vệ duy nhất. Sau unlock, flow cũ giữ row lock → delete group → FK đưa member về NULL → `204`.
- Group DELETE outbox command được tạo sau confirmation phải có `requires_private=true`. Nếu gate
  hết hạn trước flush, exact code trên đi vào `private_hold` theo 017; unlock rồi replay nguyên
  command. Create/rename/reorder group không detach hidden member nên không bị gate mới này.
- Dùng `group_id: UUID | null` đang có. Không thêm group sentinel vào Pydantic/SQL.
- Không đổi limit 20 hoặc ordering của recent entries; chỉ di chuyển component lên trước
  DashboardPanel.
- Không đổi computation/copy/chart trong `DashboardPanel` và không đổi subscription card.
- Nếu implementation phát hiện API hiện hành không hỗ trợ `group_id:null`, dừng và ghi receipt;
  không mở thêm backend scope ngoài DELETE gate đã khai ở trên.

## 7. Accessibility, responsive và privacy

- Dùng `@/components/ui/*` và token trong `index.css`; không raw button/input/select, màu
  hard-code, fixed card height, chữ dưới 12 px, hover-only hoặc dark mode.
- Disclosure có `aria-expanded`, `aria-controls`; heading level liên tục. Move action có label
  gồm tên tracker/group; focus trả về trigger sau dialog và sang section đích sau move.
- Touch target tối thiểu 44×44 px; test 320×568, 390×844 và desktop 1280×800, không horizontal
  overflow. Collapsed section không để descendant focusable trong tab order.
- Private lock không persist private name/count/fold state. Khi lock/refetch, cell private biến mất,
  selection/dialog liên quan đóng và query cache purge theo lifecycle hiện hành.

## 8. Acceptance matrix

| ID | Tình huống | Kết quả/biên lai bắt buộc |
|---|---|---|
| T1 | Screen có groups, loose trackers, recent data | DOM order đúng 1→6; `Nhịp ghi gần đây` sau organizer và recent |
| T2 | Group thật + ungrouped | cùng một organizer; virtual section cuối; không request CRUD chứa sentinel |
| T3 | Fold/unfold | ARIA/focus đúng; reload reset; không localStorage/IndexedDB/API write |
| T4 | Dynamic rank | frozen order và fixtures 30 ngày giữ nguyên; filter vào group không alpha-sort |
| T5 | Move sang virtual group | PATCH `group_id:null`; rollback đúng khi 4xx/5xx/offline |
| T6a | Delete group khi unlocked | confirmation count gồm đủ live public/private member; 204; tracker/entry còn nguyên, mọi member về NULL |
| T6b | Delete group khi locked | existing/missing và public-only/mixed đều exact 403/code/body shape; zero group/tracker/entry mutation; stale dialog/outbox vào unlock/private_hold |
| T7 | Tracker “Hút thuốc”/“Billiards” | dùng generic kind/input; source/API/DB không có hard-coded branch/flag |
| T8 | Long/empty/30+ trackers | wrap, fold, focus-to-capture, không fixed height/overflow; thao tác mobile ổn |
| T9 | Private lock giữa lúc dialog mở | dialog đóng, dữ liệu private purge, không lộ count/name |
| T10 | Regression | capture, undo, recent record, dashboard và subscription tests hiện hành vẫn xanh |

Test bắt buộc:

- Backend API/integration cho DELETE group: locked existing/missing/public-only/mixed-private trả
  cùng `403 + PRIVATE_UNLOCK_REQUIRED` trước lookup và zero mutation; unlocked mixed group trả 204,
  mọi member về NULL nhưng tracker/entry giữ nguyên; hai request/replay giữ transaction an toàn.
- Vitest cho projection group/virtual group, frozen order, no-sentinel serialization, DOM order,
  mutation rollback, lock lifecycle, `requires_private=true` và generic-name fixtures.
- Playwright desktop + mobile cho fold, move, delete warning, focus capture cell, 44 px target,
  keyboard order, no overflow và screenshot đủ long-name/empty/30+ dataset.
- Static guard `rg`/test chứng minh không thêm forbidden entity/label list và không thêm browser
  persistence cho fold state.
- Guardrail mới có RED → GREEN receipt: tạm alpha-sort grouped cells/serialize sentinel **hoặc**
  bỏ domain delete gate để locked request detach member, thấy đúng test đỏ; hoàn nguyên rồi xanh.

## 9. Sequencing và không làm

1. **Gate cứng:** task 017 merge trước vì cùng sửa `TrackerScreen`, query cache và outbox.
2. Sau rebase lên 017, task 029 gồm frontend organizer + một backend action gate hẹp trên DELETE
   group. Có thể chạy song song với 028/030 chỉ khi writers không cùng sửa tracker router/store,
   central privacy normalizer hoặc outbox classifier.
3. Không chỉnh task/status index rộng trong PR; integration owner cập nhật sau khi merge.

Không làm: grouped CaptureGrid, thay dynamic ranking, tracker position, drag-and-drop, persisted
fold preference, new analytics/chart, sensitive activity entity, reminder change, DB/API migration,
AI, production deploy hoặc physical-iPhone acceptance. UI tests local/CI không thay thế device
verification sau deploy.
