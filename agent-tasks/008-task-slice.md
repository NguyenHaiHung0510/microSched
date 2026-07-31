# 008 — task slice: đi trọn entity `task` (API + UI + test) — **TASK ĐẶT KHUÔN**

> Executor: **nhiều tầng** (xem §3 Ladder) · Effort: theo phase · **Skill gợi ý:** không · **MCP cần:** Google MCP browser-QA (Phase 2, T3)
> **Trạng thái:** 📋 SPEC **v2** — đã fold 7 finding từ `adversarial_review` khác-họ (`gemini-3.1-pro-high`, 2026-07-24). Chờ chủ duyệt lần cuối → Codex.
> **Branch:** hai PR tách — `feat/008-invariant-trigger` (Agent-Opus) rồi `feat/008-task-slice` (Codex) → `develop`
> **Blast radius / triage:** **L1 TOÀN PHẦN.** 008 là task đặt khuôn; mọi convention ở đây 009–012 chép lại (kể cả quy trình nghiệm thu). Theo [[harness-triage-ladder]]: trên task đặt khuôn, **L2 → L1**.

> **📝 v2 (2026-07-24) — 7 finding đã fold:** #1 đua transaction (§2.5 khoá dòng) · #2 đọc item con qua cha (§2.3/§2.6) · #3 hai hình mã hoá (§2.2) · #4 soft-delete rò con (§2.3) · #5 session theo request (§2.1) · #6 `encrypt(None)` (§2.2) · #7 cấm đổi `task_id` (§2.1/§4). Chủ đã gật #1 + #5 (đổi convention khuôn).

---

## 0. Đây là task ĐẶT KHUÔN — đọc trước khi làm

Đây là **lát cắt dọc** đầu tiên: xỏ một entity `task` xuyên trọn 5 tầng (màn hình → API → store → seam crypto → Neon) và ngược lên. Sau 008, app **quản lý task thật** end-to-end trên `microsched.fly.dev`.

Cái chính không phải `task`, mà là **hình dạng**: đăng ký router, hình lỗi, phân trang, gọi seam crypto, tầng đọc-sạch, cách test, cách nghiệm thu. **009–012 chép y hình dạng này** — sai khuôn ở đây là sai 5 lần. Spec nêu **cả cơ chế lẫn lý do**; executor gặp tình huống ngoài spec phải xử theo lý do.

Nguồn (đọc, đừng tự chế lại): `CLAUDE.md`, `docs/schema-physical-brief.md` §7.1, `docs/tracking-brief.md` §6, `docs/auth-brief.md` §3–§4 (R1–R7), `backend/app/core/crypto.py`, `backend/app/web/routers/me.py` + `backend/app/main.py`, `backend/tests/test_auth.py`.

## 1. Việc của CHỦ trước khi chạy task
- [ ] **Docker PG local.** Test slice chạy trên Postgres thật (§2.7). Chưa bật Docker Desktop → `alembic`/`pytest` bản PG báo `connection refused` — đó là daemon chưa chạy, không phải môi trường hỏng.
- [x] `ENCRYPTION_MASTER_KEY` — đã có (008a); test tự sinh khoá tạm nếu chạy trong worktree.
- [ ] Google MCP cho T3 (Phase 2) — theo `AGENTS.md` "Lái trình duyệt" + `devops-brief.md` §7.2.

## 2. Quyết định đã KHOÁ (executor chép ra code, không mở lại)

**2.1 Tầng store — session THEO REQUEST (không theo method).** `backend/app/domain/tasks.py` chứa `TaskStore`; nhưng **KHÔNG** cầm `sessionmaker` như `PostgresSessionStore`. Thêm một dependency `get_session` (yield một `AsyncSession`, `commit`/`rollback` bao quanh request); store method **nhận `session: AsyncSession`**. ⇒ cả một request HTTP là **một transaction** (tạo task + item, hay toggle, hỏng giữa chừng thì rollback trọn). *(Auth store giữ nguyên kiểu cũ vì op đơn bước; CRUD dùng kiểu request-scoped — đây là khuôn 009–012 chép. Finding #5.)* CRUD + crypto + đọc-sạch nằm trong store; router mỏng. **`task_item.task_id` bất biến** — store từ chối đổi (đổi từ task private sang public làm lộ ciphertext, finding #7).

**2.2 Gọi seam crypto — chỉ ở store, đúng ranh giới ghi/đọc.**
- **Ghi:** nếu `is_private` → mã hoá `title`, `body_md`, mọi `task_item.content` *trước khi* ghi. **None-guard bắt buộc:** `crypto.encrypt(v) if v is not None else None` — `body_md` nullable, `crypto.encrypt` không nhận `None` (008a cố ý để 008 lo, finding #6).
- **Đọc:** field nào `crypto.is_encrypted()` → `crypto.decrypt()`.
- **KHÔNG** gọi crypto ở router/DTO/frontend.
- **⚠️ HAI HÌNH MÃ HOÁ — khuôn cho 009–012 (finding #3):**
  - **(a) có-điều-kiện** — `task`, `note`: mã hoá **iff `is_private`**. CHECK ở DB là `NOT is_private OR ... LIKE 'enc:v1:%'`. **008 dùng hình này.**
  - **(b) vô-điều-kiện** — `tracker.name` ([models.py:271](../backend/app/domain/models.py)), `subscription.name`/`amount` ([:322](../backend/app/domain/models.py)), `message.content` ([:442](../backend/app/domain/models.py)), tiền `entry`: **luôn** mã hoá, CHECK `LIKE 'enc:v1:%'` **không điều kiện**. **011 dùng hình này** — chép nhầm hình (a) sang tracker = tạo tracker public ghi tên trần = **vỡ CHECK**.

**2.3 Tầng đọc-sạch — MỘT chỗ, lọc CẢ private LẪN soft-delete (R1 "một cổng").** `backend/app/domain/reading.py`:
```python
def can_see_private(session: AuthSession) -> bool:
    return session.private_until is not None and session.private_until > now_utc()

def readable(stmt, model, session):   # cho MỌI list/get của entity CHA (có is_private + deleted_at)
    stmt = stmt.where(model.deleted_at.is_(None))            # soft-delete (finding #4)
    return stmt if can_see_private(session) else stmt.where(model.is_private.is_(False))
```
- **Chỉ dùng cho entity CHA** (`task`/`note`/`tracker`… — có `is_private` + `deleted_at`). **`task_item` KHÔNG có hai cột đó** — gọi `readable(..., TaskItem, ...)` sẽ **nổ**. Con gác **qua cha** (xem 2.6, finding #2/#4).
- Private-unlock (passphrase) **hoãn** ⇒ `private_until` luôn NULL ⇒ task private **tạm thời luôn ẩn** — đúng, an toàn. Unlock ship sau chỉ bật cột này, **không sửa 5 slice**. **KHÔNG rải điều kiện `is_private`/`deleted_at` ra chỗ khác.**

**2.4 Bất biến `private ⇒ ciphertext` cho `task_item` — GÁC BẰNG TRIGGER (zero-trust).** `task.title/body_md` đã có CHECK (0001). `task_item.content` không CHECK được (không nhìn được cha; K11 cấm thêm cột `is_private` xuống con). Chốt 2026-07-24: **trigger** (không app-only) — bất biến không vỡ âm thầm vì bug, 5 slice sau thừa hưởng bảo đảm DB. *(Đảo posture "app-layer" của `tracking-brief.md` §6 — Phase 0 thêm dated note vào §6.)*

**2.5 Toggle private + ghi item — thứ tự + KHOÁ DÒNG (finding #1).**
- Mọi đường **toggle** và **ghi/thêm item** mở bằng **`SELECT … FOR UPDATE` dòng task cha** → serialize hai transaction cùng chạm một task, đóng đua-transaction (hai ghi cùng lúc lách trigger vì READ COMMITTED không thấy việc chưa-commit của nhau).
- Thứ tự trong transaction toggle (trigger ép):
  - **public → private:** mã hoá `title/body/mọi item` **TRƯỚC**, rồi set `is_private=true`.
  - **private → public:** set `is_private=false` **TRƯỚC**, rồi giải mã item.
- Cả toggle trong **một transaction** (đã atomic nhờ 2.1).

**2.6 Convention API (009–012 chép).**
- **Router:** `app/web/routers/tasks.py`, `APIRouter(tags=["task"])`; include vào `protected_api` ở `main.py`. Handler khai `session: AuthSession = Depends(require_session)` + `db: AsyncSession = Depends(get_session)`.
- **Đường dẫn:** `/api/tasks`, `/api/tasks/{id}`, item **lồng** `/api/tasks/{id}/items` + `/api/tasks/{id}/items/{item_id}`.
- **Đọc/ghi item PHẢI qua cha (finding #2/#4):** mỗi thao tác item **resolve task cha qua `readable(...)` trước** — không thấy (private-khoá **hoặc** đã soft-delete) → **404**, không đụng item. Con thừa hưởng privacy + soft-delete của cha; `readable` không bao giờ gọi trên `task_item`.
- **Hình lỗi:** giữ `{"detail": ...}` (FastAPI mặc định). 404 cho không-thấy (kể cả bị lọc — không tiết lộ "có nhưng private"). 422 validation.
- **List envelope:** `{"items": [...]}`. Query `limit` (mặc định 100), `offset`, `status` (`open|completed|all`). Sort `due_at NULLS LAST, created_at DESC`. `total`/cursor hoãn tới 011.
- **Soft-delete:** DELETE = set `deleted_at`; đọc lọc qua `readable`.
- **DTO tách table model:** `TaskCreate`/`TaskUpdate`(optional)/`TaskRead`; `TaskItem*`. Pydantic `BaseModel`.

**2.7 Test slice trên Postgres THẬT** (không double). Bài test nặng ký nhất (trigger + CHECK) chỉ thật khi chạm DB thật. CI: chạy trong job có service `pgvector/pgvector:pg18` (tái dùng `Migration QA` hoặc thêm service vào job backend; Phase 0 lo). Test auth cũ giữ double.

**2.8 Phạm vi UI (online-only).** List + form tạo/sửa + tick xong + checklist + toggle private. KHÔNG outbox/Dexie, KHÔNG search/sort nâng cao ngoài `status`. React Query + fetch layer kiểu `App.tsx` (401 → `UnauthenticatedError`; mutation → **invalidate query** đúng key — ổ lỗi cache sâu, xem QA).

## 3. Ladder thi công

| Phase | Ai | Effort | Việc | PR |
|---|---|---|---|---|
| **0** | **Agent-Opus (T1)** | MAX | trigger 2 chiều + khoá-dòng-nhận-thức trong test + test bất biến trên PG + CI-PG | `feat/008-invariant-trigger` |
| **1** | **Codex / Sol / `--write`** | high | store (session-theo-request) + reading + router + DTO + UI + test CRUD; làm test Phase 0 **xanh** | `feat/008-task-slice` |
| **2** | **T3 (Google MCP)** | — | browser-QA diện rộng theo kịch bản T1 + ghi quan sát CIA | báo cáo |
| **3** | **T1** | — | biên lai code + đọc QA + đích thân soi 1 kịch bản bảo mật lõi | nghiệm thu |

---

## PHASE 0 — Agent-Opus/MAX: bất biến ở DB + test (`feat/008-invariant-trigger`)

### 0.1 Migration `0003_task_item_privacy_trigger.py`
Alembic mới (**KHÔNG sửa 0001/0002**). `op.execute` raw SQL, đủ `downgrade`. Hai trigger:
```sql
-- Chiều 1: chặn ghi item trần dưới task cha private
CREATE FUNCTION microsched.enforce_task_item_privacy() RETURNS trigger AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM microsched.task WHERE id = NEW.task_id AND is_private) THEN
    IF NEW.content NOT LIKE 'enc:v1:%' THEN
      RAISE EXCEPTION 'task_item.content must be ciphertext when parent task is private';
    END IF;
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_task_item_privacy
  BEFORE INSERT OR UPDATE ON microsched.task_item
  FOR EACH ROW EXECUTE FUNCTION microsched.enforce_task_item_privacy();

-- Chiều 2: chặn lật task sang private khi còn item con trần
CREATE FUNCTION microsched.enforce_task_children_privacy() RETURNS trigger AS $$
BEGIN
  IF NEW.is_private AND NOT OLD.is_private THEN
    IF EXISTS (SELECT 1 FROM microsched.task_item
               WHERE task_id = NEW.id AND content NOT LIKE 'enc:v1:%') THEN
      RAISE EXCEPTION 'cannot make task private while it has plaintext task_item children';
    END IF;
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_task_children_privacy
  BEFORE UPDATE OF is_private ON microsched.task
  FOR EACH ROW EXECUTE FUNCTION microsched.enforce_task_children_privacy();
```
- ⚠️ **Trigger KHÔNG tự đủ dưới concurrency** (finding #1): READ COMMITTED cho hai transaction không thấy việc chưa-commit của nhau → app **phải** `SELECT … FOR UPDATE` dòng task cha ở đường toggle/ghi-item (2.5). Trigger là lưới cuối, khoá-dòng là lưới chính.
- `downgrade`: DROP 2 trigger + 2 function.
- Sau áp: `alembic upgrade head` trên Neon (`NEON_MIGRATOR_URL`) rồi **query `pg_trigger` thật** xác nhận — *"merge ≠ migration applied"*.

### 0.2 `backend/tests/test_task_item_trigger.py` — DB-level, PG thật, chứng minh biết đỏ
Dán output hai chiều (bỏ trigger → đỏ; hoàn nguyên → xanh):
1. INSERT item **trần** dưới task private → **từ chối**.
2. INSERT item **ciphertext** dưới task private → nhận.
3. INSERT item trần dưới task **public** → nhận.
4. UPDATE task `false→true` khi còn item con trần → **từ chối**.
5. UPDATE task `false→true` khi item con toàn ciphertext → nhận.
6. **Đua concurrency (finding #1):** hai session song song — A toggle→private, B thêm item trần — **KHÔNG** khoá dòng ⇒ tái hiện được bất biến vỡ (chứng minh vì sao cần khoá); **CÓ** `SELECT … FOR UPDATE` ⇒ B đợi, bất biến giữ. *(Nếu khó dựng 2 connection trong test, tối thiểu test rằng đường ghi có phát `FOR UPDATE` + ghi assertion mô tả cơ chế.)*
7. Round-trip `downgrade base` / `upgrade head` xanh.

### 0.3 `backend/tests/test_tasks_store.py` — hợp đồng store, viết ĐỎ (Codex làm xanh)
1. Tạo task private (title/body/2 item plaintext) → DB: mọi cột `enc:v1:%`; `TaskRead`: plaintext đúng.
2. Toggle `public→private→public` **×3 vòng**: nội dung mỗi vòng đúng gốc (kể cả tiếng Việt có dấu), DB luôn thoả trigger.
3. **Session khoá** (`private_until=None`): `list`/`get` **không** trả task private; **mở**: trả + giải mã.
4. **Đọc item con qua cha (finding #2):** session khoá → `GET /tasks/{id}/items` của task private → **404**, không rò item.
5. **Soft-delete con (finding #4):** xoá mềm task → `get`/`list` task **và** `items` của nó đều không thấy (gác qua cha).
6. **`encrypt(None)` (finding #6):** tạo task private `body_md=None` → không nổ; đọc lại `body_md=None`.
7. **Cấm reparent (finding #7):** đổi `task_id` của item → store **từ chối**.
8. Soft-delete task: hàng vẫn trong DB với `deleted_at`.

### 0.4 Hạ tầng CI-PG
Test PG (0.2/0.3 + Phase 1) chạy trên CI với service `pgvector/pgvector:pg18`. Chọn cách ít trùng lặp, ghi lý do PR. Convention 009–012 chép.

---

## PHASE 1 — Codex/Sol/`--write`: cả slice (`feat/008-task-slice`)
Điều kiện vào: Phase 0 đã merge. Mục tiêu: làm test Phase 0 **xanh** + build trọn slice + test CRUD/UI riêng.
- **1.1 `app/domain/reading.py`** — đúng 2.3.
- **1.2 `app/core/db.py` / `deps.py`** — thêm dependency `get_session` (yield `AsyncSession`, commit/rollback theo request), đúng 2.1.
- **1.3 `app/domain/tasks.py`** — `TaskStore` nhận `session`: `list`/`get`/`create`/`update`(gồm toggle 2.5)/`soft_delete` + CRUD item lồng. Crypto 2.2, thứ tự+khoá-dòng 2.5, đọc qua `readable` 2.3, item qua cha 2.6, `task_id` bất biến.
- **1.4 DTO** (2.6).
- **1.5 `app/web/routers/tasks.py`** + include vào `protected_api` (`main.py`, cạnh `me_router`).
- **1.6 Frontend** — màn task thay placeholder `SignedIn` (giữ login/logout): list, form tạo/sửa, tick xong, checklist, toggle private. React Query keys `['tasks', ...]`; **mutation → invalidate đúng key**. Fetch layer + `UnauthenticatedError` kiểu `App.tsx`.
- **1.7 Test CRUD/UI** — happy + nhánh từ chối (401/404/422) trên PG thật; `vite build` xanh. Không trùng test bất biến Phase 0.

---

## PHASE 2 — T3 (Google MCP): browser-QA trên bản deploy
Chạy trên `develop` đã deploy. T3 thực thi kịch bản T1 định (phần diện rộng, ngốn quota), không quyết, không code.

### 2.1 Tiêu chí QA cho dự án này (chuẩn-QA — T1 chọn) — 4 trục
- **B — Breadth:** mỗi endpoint, nhánh happy **và** từ chối.
- **D — Depth (stateful/interleaved):** chuỗi chồng chéo + rời-rồi-quay-lại + lặp vòng. **Trục hay bị bỏ** (chủ nêu; tiền lệ B4/007 = cache cũ sống sau một chuỗi).
- **C — CIA:** xem 2.3.
- **R — Resilience:** refresh giữa chừng, back/forward, double-submit, phiên hết hạn giữa lúc dùng, mạng chậm.

### 2.2 Kịch bản (T1 định; T3 chạy tuần tự, ghi lại)
**Breadth:** tạo→thấy list; sửa title/body/priority/due→phản ánh; tick xong; thêm/tick/xoá item; toggle private; xoá task. Từ chối: chưa login→401; id không có→404; title rỗng→422.
**Depth (bắt buộc — note 1 của chủ):**
1. **Vòng lặp CRUD:** thêm→sửa→xoá **cùng task 10 lần** — lag dồn? UI cũ? state mồ côi?
2. **Rời-rồi-quay-lại:** CRUD → sang màn khác → quay lại list. List có **tươi** không, có phải reload tay, có data cũ cạnh mới (hình B4)?
3. **Round-trip toggle private ×≥3 vòng:** task có title/body/2 item → nội dung mỗi vòng đúng gốc, không nuốt dấu tiếng Việt, không 500.
4. **Mutation xen phân trang:** list >1 trang → sửa ở trang 2 → về trang 1 → thứ tự/đếm đúng.
5. **Double-submit:** bấm "Tạo" 2 lần thật nhanh → **không** nhân đôi.

### 2.3 T3 ghi quan sát CIA (note 2 của chủ — "tuỳ năng lực + tool cấp")
Dùng khả năng đọc network/console/DOM/storage của MCP, báo kèm vị trí chính xác:
- **Confidentiality:** field private/`enc:v1:` nào lộ **plaintext** ở response/DOM/`localStorage`/`IndexedDB`/URL/body lỗi? Task private lọt ra khi phiên **đang khoá** không? *(bất biến bảo mật lõi.)*
- **Integrity:** giá trị lệch server↔UI? Đếm/thứ tự sai sau chuỗi? Optimistic phân kỳ?
- **Availability:** thời gian phản hồi **dồn** qua vòng lặp (đo đầu vs cuối)? Treo, console error lặp, dấu hiệu rò bộ nhớ?
- Cái **không soi được** → **khai rõ "không kiểm được"**, đừng suy đoán là sạch.

---

## PHASE 3 — T1 nghiệm thu
1. **Sau mỗi PR:** biên lai — PR# + `gh pr checks` xanh (5) + **đọc diff tay** + deploy verify **SHA sống** (`/api/readyz`) + (Phase 0) **query `pg_trigger` trên Neon**.
2. **Đọc report QA T3** — kiểm ranh giới "đã chạy / chưa soi được" trung thực không.
3. **Đích thân soi 1 kịch bản bảo mật lõi (must-do-personally):** task private **không lộ** khi khoá, **không rò plaintext** ở bất kỳ bề mặt nào. T1 tự tay, không uỷ.

## 4. KHÔNG được làm
- KHÔNG sửa `0001`/`0002`. Trigger là `0003` mới.
- KHÔNG thêm cột `is_private` xuống `task_item` (K11).
- KHÔNG gọi crypto ngoài `domain/tasks.py`; KHÔNG rải `is_private`/`deleted_at` ngoài `reading.py`.
- KHÔNG cho đổi `task_id` của item; KHÔNG để đọc/ghi item bỏ qua task cha.
- KHÔNG toggle/ghi-item mà thiếu `SELECT … FOR UPDATE` dòng cha.
- KHÔNG outbox/Dexie, search/sort nâng cao, private-unlock passphrase (ngoài phạm vi).
- KHÔNG test slice bằng double in-memory — PG thật.
- KHÔNG gộp Phase 0 và Phase 1 vào một PR.
- KHÔNG in/log plaintext hay khoá.

## 5. Acceptance (kiểm chứng được)
**Phase 0:** `alembic upgrade head` + query `pg_trigger` thấy 2 trigger · `test_task_item_trigger.py` xanh, dán output biết-đỏ (gồm case đua #6) · round-trip migration xanh · `test_tasks_store.py` tồn tại và **đỏ**.
**Phase 1:** `test_tasks_store.py` **xanh** · test CRUD/UI xanh · `ruff` sạch · `vite build` ok · `gh pr checks` 5/5.
**Phase 2:** report T3 phủ đủ 4 trục B/D/C/R + CIA + khai rõ cái không soi được.
**Phase 3:** biên lai đủ · T1 xác nhận kịch bản bảo mật lõi bằng mắt.

## 6. Báo cáo (khuôn sau 007)
Mỗi PR tách **ĐÃ CHẠY** vs **CHỈ SUY LUẬN**; CI xanh mới báo xong. Không nhận prose làm bằng chứng — chỉ PR# + `gh pr checks` xanh + diff + (deploy) SHA sống + (migration) query trigger thật.
