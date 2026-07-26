# 008f — hoàn tác xoá: khôi phục ở server + toast undo ở client

> **Executor: Codex (T2).** Nhánh `feat/008f-undo-delete` → PR nhỏ vào `develop`.
> Spec tự-chứa. Đọc `CLAUDE.md` + `AGENTS.md` trước; `docs/ui-brief.md` là luật cho phần giao diện.
> **KHÔNG có migration trong task này** — cột `deleted_at` đã tồn tại từ `0001`.

## 0. Bối cảnh — vì sao có task này

Xoá task hiện tại là **soft delete**: `TaskStore.soft_delete` (`backend/app/domain/tasks.py:290`) chỉ đặt `deleted_at`, và cửa đọc `readable()` lọc dòng đó ra. Nghĩa là **dữ liệu vẫn còn nguyên trong DB, chỉ không có đường nào lấy lại**.

Đó là trạng thái tệ nhất trong ba trạng thái: xoá cứng thì người dùng biết là mất; xoá mềm có hoàn tác thì an toàn; xoá mềm **không** có hoàn tác thì người dùng tin là đã mất, dữ liệu vẫn chiếm chỗ, và không ai được lợi. Task này đóng khoảng đó.

Nút xoá hiện nằm ngay trên thẻ, **một chạm, không hỏi lại** (`TasksScreen.tsx`, nút `Xoá {task.title}`). Trên iPhone đó là một chạm nhầm. Hoàn tác là cách chữa đúng — **không** phải thêm dialog xác nhận, vì xác nhận bắt trả giá ở *mọi* lần xoá đúng để phòng lần xoá sai.

## 1. Đã KHOÁ — chép ra code, không mở lại

1. **Hoàn tác, không phải hộp thoại xác nhận.** Không thêm bước xác nhận nào cho nút xoá.
2. **Cửa sổ hoàn tác gắn với toast, không gắn với server.** Server cho khôi phục **không giới hạn thời gian**; cái hết hạn là *lời mời* trên màn hình, không phải *quyền*. Lý do: hết hạn ở server nghĩa là phải có job dọn, mà mọi job nền trong dự án này chạy qua cron ngoài (`CLAUDE.md`) — thêm một đường phụ thuộc để đổi lấy đúng một tính năng UX là lỗ vốn.
3. **Cổng riêng tư vẫn áp cho khôi phục.** Một task riêng tư bị xoá trong lúc private mode đang mở, rồi private mode khoá lại ⇒ **không khôi phục được**, y như không đọc được. Khôi phục là một dạng đọc.
4. **Con `task_item` theo cha.** `readable()` cho con gác qua cha, nên khôi phục cha là con trở lại đủ. **Không** đụng gì tới `deleted_at` của con.
5. **Toast dùng `sonner` đã cài** (`frontend/src/components/ui/sonner.tsx`). Không thêm thư viện toast khác.

## 2. Phải làm

### 2.1 Backend — `TaskStore.restore`

Thêm vào `backend/app/domain/tasks.py`:

```
async def restore(self, db, auth, task_id) -> TaskRead | None
```

- Tìm dòng `task` theo `id`, **bỏ qua bộ lọc `deleted_at`** nhưng **giữ nguyên bộ lọc riêng tư** của `readable()`. Đừng viết một câu truy vấn trần bỏ cả hai — đó là chỗ rò rỉ.
- Không tìm thấy, hoặc tìm thấy nhưng session không được đọc ⇒ trả `None`.
- Tìm thấy và `deleted_at IS NULL` (chưa từng bị xoá) ⇒ **vẫn trả về task đó**, không lỗi. Khôi phục phải **idempotent**: người dùng bấm "Hoàn tác" hai lần, hoặc bấm sau khi đã hoàn tác ở tab khác, không được ăn lỗi.
- Đặt `deleted_at = None`, commit, trả `TaskRead` **đã kèm `items`** (dùng lại đúng đường ráp mà `get()` đang dùng — đừng chép lại logic giải mã).

⚠️ **Cách tách bộ lọc là phần khó nhất của task này.** `readable()` (`backend/app/domain/reading.py`) hiện gộp *cả hai* điều kiện. Đừng sửa `readable()` theo hướng làm nó nhận cờ bật/tắt lọc `deleted_at` cho **mọi** lời gọi — một hàm bảo vệ mà có công tắc tắt là một hàm bảo vệ đang chờ bị tắt nhầm. Cách đúng: tách phần *điều kiện riêng tư* ra thành một mảnh dùng lại được, rồi `restore` tự ghép mảnh đó với điều kiện của riêng nó. Nếu bạn thấy cách gọn hơn mà **không** tạo công tắc, cứ làm và giải thích trong PR.

### 2.2 Backend — endpoint

`POST /api/tasks/{task_id}/restore` → `200` + `TaskRead`, hoặc `404` (dùng `_not_found()` đang có).

Đặt trong `backend/app/web/routers/tasks.py`, **trên** route `/tasks/{task_id}/items` để không bị nuốt bởi khớp đường dẫn. Không đổi bất kỳ endpoint nào đang có.

### 2.3 Backend — test (`backend/tests/`)

Bắt buộc có, và **phải chứng minh biết đỏ** (`AGENTS.md`): phá đúng hành vi nó canh → thấy đỏ đúng lý do → hoàn nguyên → xanh. Ghi lại trong PR description bạn đã phá cái gì và thấy đỏ ở đâu.

| Test | Phải khẳng định |
|---|---|
| Khôi phục sau xoá | Task quay lại `list`, **và các `task_item` của nó quay lại đủ** |
| Idempotent | Gọi `restore` hai lần liên tiếp → cả hai lần `200`, không lỗi |
| Chưa từng xoá | `restore` một task đang sống → `200`, không đổi gì |
| Không tồn tại | `404` |
| 🔒 **Cổng riêng tư** | Task riêng tư đã xoá, session **khoá** private ⇒ `404`, và `deleted_at` trong DB **vẫn nguyên** |
| Cần session | Không có session ⇒ `401` (route nằm dưới `require_session`, test để chốt là nó không lọt ra ngoài) |

Test cổng riêng tư là test quan trọng nhất ở đây — nó là chỗ duy nhất task này có thể tạo lỗ bảo mật.

### 2.4 Frontend — toast hoàn tác

Trong `frontend/src/TasksScreen.tsx`:

- Mutation `remove` thành công ⇒ gọi `toast(...)` với **hành động `Hoàn tác`**, thời lượng **8000ms** (mặc định 4s của sonner quá ngắn cho một quyết định).
- Nội dung toast: `Đã xoá "<tiêu đề>"` — tiêu đề dài phải **cắt bằng CSS**, không cắt chuỗi trong JS (`ui-brief.md`: cắt ở tầng hiển thị, giữ nguyên dữ liệu). Nhắc lại bài học vừa vá ở `008k`: một tiêu đề 70 ký tự **liền không dấu cách** sẽ phá vỡ hộp nếu thiếu `min-w-0` + `break-words`.
- Bấm `Hoàn tác` ⇒ gọi `POST /api/tasks/{id}/restore`, xong thì `void queryClient.invalidateQueries(...)`.
- 🔒 **`onSuccess` KHÔNG được `await invalidateQueries`.** React Query giữ mutation ở `isPending` cho tới khi `onSuccess` resolve — đây đúng là lỗi `008i` vừa sửa, đừng chép lại. Xem chú thích tại `TasksScreen.tsx` chỗ `refresh()`.
- Hoàn tác **thất bại** (mạng hỏng, `TimeoutError`, `404`) ⇒ hiện `toast.error` với lời báo lấy từ `errorMessage(error)`. **Không được im lặng.** Một nút hoàn tác bấm xong không có gì xảy ra là tệ hơn không có nút hoàn tác.
- Dùng lại `errorMessage()` đang có; **không** viết bảng lỗi thứ hai.

### 2.5 Frontend — test

Thêm vào `frontend/tests/`. Ít nhất: gọi `restore` đúng đường dẫn và đúng method; và nhánh lỗi có gọi `toast.error`. Nếu mock `sonner` là cách gọn nhất thì cứ mock.

## 3. KHÔNG được làm

- **Không** migration, **không** đổi model, **không** thêm cột. `deleted_at` đã có.
- **Không** thêm dialog xác nhận cho nút xoá (xem §1.1).
- **Không** thêm job dọn dữ liệu đã xoá, không đụng `cron.py`.
- **Không** cho `readable()` một tham số bật/tắt lọc `deleted_at` (xem §2.1).
- **Không** đụng `frontend/src/api.ts` — hợp đồng `apiRequest` vừa được vá ở `008i`, giữ nguyên.
- **Không** thêm dependency. `sonner` đã cài.
- **Không** đụng `pinned` / `localStorage` — đó là `008g`, một PR khác.
- **Không** đổi tên required check trong CI.

## 4. Acceptance — kiểm chứng được

1. `uv run ruff check` sạch; `uv run pytest` xanh (kể cả lane `-m pg`).
2. `npm run lint` sạch, `npm test` xanh, `npm run build` xanh.
3. Test cổng riêng tư ở §2.3 **đã được chứng minh biết đỏ**, có ghi lại trong PR.
4. `gh pr checks <PR>` xanh 5/5 — chờ thật, không suy đoán (`AGENTS.md`).
5. PR description nêu rõ: cách tách bộ lọc ở §2.1, và bạn đã phá gì để thấy đỏ.

## 5. Báo cáo

Theo khuôn `AGENTS.md`: số PR + `gh pr checks` xanh + diff đọc được. **Lời khai không đóng được task.**

Sandbox của bạn chặn Docker và `.git` ⇒ **không chạy được lane `-m pg` và không tự tạo PR được**. Đó là bình thường: **báo đúng là chưa verify được**, đừng báo đạt. T1 sẽ chạy lại tay toàn bộ.

## 6. Sau khi merge

⚠️ **Task này KHÔNG có migration** — merge xong **đừng** chạy `alembic upgrade` theo quán tính.
