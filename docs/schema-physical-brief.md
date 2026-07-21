# Schema vật lý (physical schema) — microSched

> **Trạng thái:** ✅ **CHỐT 2026-07-19** cho toàn bộ Nhóm 2, **trừ 2 mục DEFER** về tracking (C2, D1-tracker → §7).
> Decision record **tự-chứa** (đọc được ở phiên 0-context). Nối tiếp `schema-v1-brief.md` (mức **khái niệm**) → file này là tầng **vật lý**: kiểu cột chính xác, cách sinh khoá, index, ràng buộc, công cụ đúc (ORM/migration), role DB.
> ⚠️ **Cửa một-chiều:** sau khi có data thật trong Neon, đổi các quyết định này (kiểu khoá chính, mã hoá enum, thêm cột NOT NULL) đều cần migration + backfill → chốt đúng ngay bây giờ rẻ hơn nhiều.

---

## 0. "Schema vật lý" là gì (đọc trước nếu 0-context)

Postgres + Neon (đã chốt ở `db-and-data-model-brief.md`) mới trả lời **"chạy engine gì, ở đâu"**. Nó **chưa** nói các bảng *thực sự được đúc ra sao* bên trong engine đó. Ba tầng:

| Tầng | Trả lời | File |
|---|---|---|
| **Khái niệm** | Có thực thể nào, nghĩa gì, quan hệ ra sao (tiếng người) | `schema-v1-brief.md` ✅ |
| **Logic** | Bảng/cột/khoá, chuẩn hoá tới đâu | gộp trong file này |
| **Vật lý** | *Chính xác* kiểu mỗi cột, cách sinh khoá chính, index nào, ràng buộc nào, DDL thật + công cụ | **file này** ✅ |

**Ẩn dụ:** Neon = đã chọn mảnh đất + vật liệu. Schema vật lý = bản vẽ thi công (tường chịu lực đặt đâu, đường điện đi lối nào). Cùng "danh sách phòng", hai bản vẽ khác nhau cho ra hai căn nhà **ở khác nhau, sửa khác nhau**.

---

## 1. Bảng trạng thái tổng hợp

| Mã | Quyết định | Kết quả | Cửa 1 chiều? |
|---|---|---|---|
| A1 | ORM | ✅ **SQLModel** | không (tụt xuống SQLAlchemy được) |
| A2 | Migration | ✅ **Alembic + hàng rào QA** (§2) | không |
| A3 | Cô lập DB | ✅ **role riêng `microsched_app` + schema `microsched`** | không |
| B1 | Khoá chính | ✅ **UUIDv7** | **có** |
| B2 | Thời gian | ✅ **`timestamptz` + trigger `updated_at`, áp ĐỒNG ĐỀU mọi bảng** | không (thêm cột dễ) |
| C1 | Enum | ✅ **`TEXT` + `CHECK`** | **có** (đổi cách mã hoá sau = migration) |
| C2 | Kiểu số `entry.value` | ✅ **ĐÃ GIẢI 2026-07-19** — tách `quantity NUMERIC(10,2)` + cột tiền VND `NUMERIC(14,0)` (`tracking-brief.md` §3/§7; VND-only v1) | **có** |
| C3 | Thứ tự item | ✅ **`int position`** (cả `task_item` + `note_item`) | không |
| C4 | Cột `vector` | ✅ **nullable ngay, dimension + index HNSW để Bước 1** | không |
| D1 | FK cascade | ✅ **calendar = CASCADE; `tracker→entry` = RESTRICT + soft-delete (chốt 2026-07-19, `tracking-brief.md` §7)** | **có** |
| D2 | Index | ✅ **bộ tối thiểu** (FK + cột thời gian) (§5) | không |
| D3 | Log AI + xoá | ✅ **log 3 tầng + soft-delete** (§5) | không |
| D4 | Full-text search | ⏸ **DEFER → Bước 1** (chỉ áp cho cột KHÔNG mã hóa — xem E1) | không |
| E1 | Mã hóa cột | ✅ **ĐÃ GIẢI 2026-07-20** — app-level AES-GCM trên `tracker.name`/`subscription.name`/`entry.note`/tiền(`amount`,`list_amount`,`orig_amount`)/`note.body_md`+`task.*` khi private (`tracking-brief.md` §6) | **có** (chỉ bật cột, không phải cơ chế/khóa) |
| BUILD-006 | DDL thật | ✅ **ĐÃ ĐÚC 2026-07-21** — Alembic revision **`0001`**, schema `microsched` trên Neon PG18 | — |

---

## 2. Cụm A — Công cụ đúc schema

### A1. ORM = SQLModel ✅
Chốt món `architecture-brief.md` §11 để lại. **SQLModel** (Pydantic + SQLAlchemy hợp nhất, cùng tác giả FastAPI): ít boilerplate, type-hint đẹp, **khớp thẳng tool-schema Pydantic của Bước 2**.
- **Lý do:** quy mô single-user không có query đủ phức tạp để chạm trần SQLModel; nó tiết kiệm đúng loại "plumbing phi-AI" cần tránh.
- **Chốt an toàn (vì sao rủi ro "kém chín" ≈ 0):** SQLModel *chạy trên* SQLAlchemy 2.0 → khi cần query khó, **tụt xuống SQLAlchemy thuần** cho riêng chỗ đó. Không phải cửa một chiều.
- **Driver:** async — `postgresql+asyncpg://`. ASGI = Uvicorn.

### A2. Migration = Alembic + hàng rào QA ✅
Alembic sinh migration bằng `--autogenerate` (so model với DB rồi đoán diff), nhưng nó **mù** với vài thứ → **bắt buộc hàng rào QA** (đây chính là một mẩu CI/CD đáng học — Track B):

**Cái autogenerate hay bỏ sót:** đổi **kiểu cột**; đổi **`CHECK` constraint** (= enum của C1!); đổi **server default**; **rename** cột/bảng → nó dịch thành DROP+ADD = **mất data** (nguy hiểm nhất).

**Hàng rào (đưa vào quy trình + GitHub Actions):**
1. **Không apply thẳng** — mỗi PR đổi schema phải kèm file migration được **đọc lại bằng mắt**.
2. **Round-trip test trong CI:** Postgres tạm (Docker) → `upgrade head` → `downgrade` → `upgrade` lại.
3. **Drift check:** sau `upgrade head`, chạy autogenerate lần nữa → còn sinh diff = model/migration lệch → **fail CI**.
4. **Chặn DROP ngầm:** grep migration cho `drop_column`/`drop_table` → phải có nhãn `# reviewed: intentional drop` mới cho qua (chặn rename-thành-drop).
5. **Thử migration trên bản restore từ backup thật** trước khi lên prod — **ghép vào khâu verify-restore của 3-2-1** (`db-and-data-model-brief.md` §6).

### A3. Cô lập DB = role riêng + schema namespace ✅
Superuser `postgres` local host nhiều project khác của chủ (vd `micareer_lite_db`, `Fang`) → microSched **không dùng chung**.
- **Role riêng** `microsched_app` — chỉ quyền CRUD trên bảng app, **không superuser**.
- **Schema riêng** `microsched` (không đặt vào `public`) → cô lập sạch. GRANT hẹp: `USAGE` trên schema + `SELECT/INSERT/UPDATE/DELETE` trên bảng app, không hơn.
- Credentials chỉ trong `.env` (đã chốt CLAUDE.md); `.gitignore` chặn `.env` từ commit đầu.

**📝 2026-07-20 — MỞ RỘNG A3: ba role, không phải hai** (chủ duyệt trong lúc chạy 006). Tách thêm **`microsched_migrator`** = role **sở hữu schema `microsched`** và là danh tính chạy Alembic:

| Role | Vai | Biến env | Dùng ở đâu |
|---|---|---|---|
| `neondb_owner` | role cấp tài khoản Neon — **chỉ bootstrap** (tạo schema/role/extension) | `NEON_OWNER_URL` | **chỉ máy chủ**, không bao giờ rời máy |
| `microsched_migrator` | **sở hữu** schema + chạy migration (DDL) | `NEON_MIGRATOR_URL` | máy chủ; **sau này là CI-deploy** |
| `microsched_app` | least-privilege, chỉ CRUD (DML) | `DATABASE_URL` | app runtime · **biến duy nhất lên Fly secrets** |

**Lý do tách migrator khỏi owner** (giá trị thật, không phải nghi thức): `neondb_owner` là role quản trị **toàn Neon project**. Nếu nó vừa sở hữu bảng vừa chạy migration thì danh tính thi công DDL trùng danh tính quản trị hạ tầng — và tới lúc bật **CI-deploy tự chạy migration** (`devops-brief.md` §6, đang treo) bạn sẽ buộc phải nhét credential *owner* vào GitHub Actions. Có role migrator thì chỉ nhét credential migrator. Giá phải trả: một role + một chuỗi chỉ sống ở máy chủ và CI.

⚠️ **Bẫy PostgreSQL 16+ phải xử lý trong script bootstrap** (đã đâm thật lúc chạy 006, xác minh bằng `pg_auth_members` trên Neon): khi một role **không phải superuser** (`neondb_owner` trên Neon chính là vậy) tạo role mới, PG tự cấp membership `ADMIN TRUE` nhưng **`INHERIT FALSE, SET FALSE`** — cố ý, để "tạo role" không âm thầm thành "có quyền của role đó". Hệ quả: owner **không `SET ROLE microsched_migrator` được**, nên không tạo nổi object thuộc sở hữu migrator. Cách gỡ (owner đã có `ADMIN` nên đủ thẩm quyền tự cấp):

```sql
GRANT microsched_migrator TO neondb_owner WITH SET TRUE;
```

**Lệnh này BẮT BUỘC nằm trong script bootstrap được commit**, không chạy tay — chạy tay thì lần dựng lại Neon project sau sẽ đâm đúng bức tường này và không ai nhớ tại sao.

---

## 3. Cụm B — Danh tính & thời gian (chạm *mọi* bảng)

### B1. Khoá chính = UUIDv7 ✅ (cửa một chiều)
Sơ đồ đã dùng `uuid` khắp nơi; đây là chốt **version + lý do**.
- **Vì sao UUID chứ không `bigint`:** đã chốt **offline-first capture** (`architecture-brief.md` §4) — ghi note land vào IndexedDB *tức thì, kể cả offline*. Muốn vậy **client phải tự sinh ID khi chưa có mạng** → `bigint serial` (server cấp) không dùng được; UUID sinh ở client được. Đây là ràng buộc kiến trúc, không phải sở thích.
- **Vì sao v7 chứ không v4:** UUIDv7 gắn tiền tố thời gian (Unix ms) → insert liên tiếp rơi cùng trang index → index **nhỏ hơn ~26%**, truy vấn theo thứ tự nhanh ~3× so với v4 (v4 ngẫu nhiên hoàn toàn → phân mảnh index). Cây quyết định 2026: *"v7 nếu runtime hỗ trợ, v4 nếu không."*
- **Vì sao không ULID/NanoID:** ULID = "UUIDv7 bản chuỗi" nhưng UUIDv7 nay đã chuẩn hoá **RFC 9562** + là **kiểu `uuid` native của Postgres** (ULID phải lưu text/bytea, kém hơn) → UUIDv7 nuốt trọn lý do dùng ULID. NanoID không time-ordered → phân mảnh như v4.
- **Sinh ở đâu:** Neon chạy PG 18.4 → row tạo ở **server** dùng default `uuidv7()` native; row tạo **offline ở client** dùng lib JS uuidv7 — **cả hai đều v7, nhất quán**.

### B2. `timestamptz` + trigger `updated_at`, áp ĐỒNG ĐỀU mọi bảng ✅
- **Kiểu:** mọi mốc thời gian = `timestamptz` (có timezone thật — sửa bug naive-time của app cũ, `v1-reference.md`).
- **`updated_at` do trigger DB** (`BEFORE UPDATE`) tự set — đúng dù ai ghi (app, tool AI Bước 2, sửa tay lúc migrate), không lệ thuộc code nhớ set.
- **Áp đồng đều `created_at` + `updated_at` cho TẤT CẢ bảng** (kể cả bảng con `task_item`/`note_item`/`calendar_event` và `entry`/`audit_log`) — vá chỗ ERD khái niệm vẽ thiếu, đúng nguyên tắc "mọi entity có tính thời gian" (`db-and-data-model-brief.md` §4; note gốc #13 của chủ).
- **Chi phí đã đo thật ≈ 0:** 16 byte/dòng. Data hiện tại ~887 dòng → **~14 KB**. Kể cả tăng 100× (~89k dòng) → **~1.4 MB = 0.28%** của gói Neon 0.5 GB. Trigger = vài micro-giây/UPDATE, 0 ảnh hưởng compute. Value cao (mọi thực thể có "tính thời gian") → chốt.

---

## 4. Cụm C — Mã hoá kiểu

### C1. Enum = `TEXT` + `CHECK` constraint ✅ (cửa một chiều)
Áp cho `task.status`, `task.priority`, `tracker.kind`, `calendar_source.kind`.
- **Không dùng native `ENUM`:** `ALTER TYPE` để thêm/xoá/đổi giá trị rất phiền.
- **`TEXT` + `CHECK`:** thêm status mới = đổi 1 constraint (migration nhẹ); AI-tool (Bước 2) đọc/ghi text dễ hơn OID của enum. Best-practice cho schema còn tiến hoá.

### C2. Kiểu số `entry.value` — ⏸ DEFER → phiên tracking (§7)
Cần thiết kế chi tiết tính năng tracking trước (VND không phần lẻ vs đơn vị sức khoẻ có thể lẻ). Nghiêng `NUMERIC` (không `float` — tránh sai số tiền); precision/scale chốt ở phiên tracking.

### C3. Thứ tự item = `int position` ✅
Subtask một người dùng số lượng nhỏ → `int` + đánh số lại khi cần là đủ, **không cần fractional indexing** (LexoRank). Áp cho cả `task_item` **và** `note_item` (checklist có thứ tự — nhất quán).

### C4. Cột `vector` — nullable ngay, chi tiết để Bước 1 ✅ (chiến lược)
Dimension coupling với embedding model → chốt **chiến lược vật lý**, không chốt con số:
- Để cột `vector` **nullable, CHƯA tạo index**. Thêm dimension + index **HNSW** ở migration Bước 1 (khi đã chốt embedding model).
- Ghi chú Bước 1: cân nhắc `halfvec` (nửa storage). Ở quy mô 49 note hiện tại, index vector còn *chưa cần thiết* cho tốc độ.
- **⚠️ OPEN 2026-07-21 — PHIÊN BƯỚC 1 BẮT BUỘC CHẠM MỤC NÀY TRƯỚC KHI CHỌN EMBEDDING.** Chủ chất vấn luật "cột mã hoá không bao giờ có embedding" và lập luận đáng cân nhắc lại:
  1. Luật viết như một **tuyệt đối**, nhưng mối đe doạ nó chặn (rò-nghĩa-qua-vector) chỉ khai thác được bởi kẻ **đã có credential DB** — nằm **ngoài threat model** đã ghi của dự án (social engineering, không phải dump DB; repo vốn public có chủ đích).
  2. Nội dung thật phần lớn vô hại (hút thuốc, bia rượu, sub, việc cần làm). Thứ thật sự nhạy (mật khẩu, số điện thoại) **không nên nằm trong app này ngay từ đầu**. Rò "lờ mờ ý nghĩa" cho kẻ đã chiếm được DB không đổi kết cục gì.
  3. Nếu cần kín, chủ có thể **tự đặt tên chỉ mình hiểu** — rẻ hơn nhiều so với hy sinh tính năng lõi.
  4. Nguyên tắc chủ nêu: *"bảo mật đi từ tối thiểu lên tăng cường tuỳ thời gian và năng lực dư"* — nâng bar bằng rất nhiều công sức cho một app AI-first là **last-mile theo nghĩa xấu**, đúng thứ microSched sinh ra để tránh.

  **Giá phải trả nếu giữ luật:** lịch sử chat + note private **vĩnh viễn không tìm được theo ngữ nghĩa**. (Tìm **từ khoá** thì vẫn được — app giải mã rồi tự quét, R2 đã chốt; ~49 note = mili-giây. Chỉ mất tìm-theo-ý-nghĩa.)

  **Chưa quyết, và cố ý chưa quyết:** cột `vector` đang không dimension/không index, **chưa có gì bị chặn trên thực tế** — quyết bây giờ là quyết mù. **Hướng có thể xoá luôn bài toán:** thay vì embedding toàn bộ lịch sử, dựng **memory có chọn lọc** (chủ chủ động bảo "nhớ cái này", kiểu Claude Code) — nhỏ, có cấu trúc, chủ kiểm soát nội dung nên để **trần** được mà không lấn vùng riêng tư. T1 đánh giá hướng này **mạnh hơn** việc nới luật. **Giữ nguyên:** mã hoá-lúc-lưu (rẻ, chặn kịch bản thật: nhân viên Neon, backup rơi ra ngoài) — chỉ luật *cấm embedding* mới là thứ đem ra cân.

- **📝 2026-07-20 (encryption-review):** luật cứng — **cột đã mã hóa (§7.1) không bao giờ có embedding**, kể cả `note.body_md` khi `is_private=true`. Tránh hẳn "rò nghĩa qua vector" thay vì cân đo % chấp nhận được. Embedding provider Bước 1 (bên thứ ba, chưa chọn) phải đạt bar "no retention/no training" — điều kiện chọn thầu, xem `tracking-brief.md` §6.

---

## 5. Cụm D — Toàn vẹn & truy cập

### D1. FK cascade ✅ (calendar) / ⏸ DEFER (tracker)
- **`calendar_source → calendar_event` = `ON DELETE CASCADE`** ✅. Khớp quyết định "re-import = thay sạch không nhân đôi, bỏ version-history" (`schema-v1-brief.md` §3-A): xoá nguồn → xoá buổi; re-import = xoá buổi cũ của nguồn đó + chèn mới.
- **`task → task_item`, `note → note_item` = `ON DELETE CASCADE`** ✅ (đã chốt — sửa bug mồ côi v1).
- **`tracker → entry` = ⏸ DEFER** → phiên tracking (§7). Nghiêng **RESTRICT / soft-delete** (xoá nhầm 1 tracker mất sạch lịch sử log sức khoẻ/tiền = đau).

### D2. Index — bộ tối thiểu ✅
*Index = cấu trúc phụ (B-tree) sắp sẵn giá trị 1 cột → trỏ vị trí dòng, như mục lục cuối sách. Đổi lại: tốn storage + làm ghi chậm hơn (mỗi INSERT/UPDATE phải cập nhật mọi index).*
- **Sự thật quy mô này:** vài trăm–nghìn dòng → Postgres full-scan trong micro-giây → index **gần như chưa cần cho tốc độ đọc** → **không over-index**.
- **Vẫn tạo sẵn (lý do thật):** khoá chính **tự có index** (miễn phí); **cột FK** nên có index (giúp join + kiểm ràng buộc); **vector** *bắt buộc* index nhưng để Bước 1.
- **Bộ đề xuất:** mọi cột FK + `task.due_at` + `entry.occurred_at` + `calendar_event.starts_at`. Rẻ, đủ, không thừa.

### D3. Log AI 3 tầng + soft-delete ✅
Tách 2 nhu cầu hay bị gộp:

**(a) An toàn dữ liệu quý** (task/note/tracker) → **soft-delete** (cột `deleted_at`), *không* phải audit từng CRUD. Soft-delete = lỡ xoá khôi phục được, rẻ (1 cột). Query thường thêm `WHERE deleted_at IS NULL`. **KHÔNG audit mỗi lần user sửa note** (vừa thừa vừa phình DB).

**(b) Sức khoẻ hệ thống + eval/observability AI** → *đây* mới là chỗ log căng. Chia **3 tầng, không trùng lặp:**

| Tầng | Chứa gì | Ở đâu | Cỡ |
|---|---|---|---|
| 1. Messages | nội dung hội thoại (là tính năng sản phẩm; **chính là log "cái đã nói"**) | **DB** | nhỏ |
| 2. Trace metadata | tool gọi + tham số, retrieval hits, **model cascade nào**, token, **cost**, latency, **user accept/reject gợi ý AI** — keyed `trace_id` trỏ về message | **DB, `audit_log` gọn** | nhỏ, tăng chậm → **eval gold** |
| 3. Raw replay blob | *prompt đã ráp* (system + context RAG nhồi + history) + completion thô | **OFF-DB** (Google Drive / local, hàng TB free) hoặc bảng riêng rotation drop-partition | **to** (gấp 10–50× message) |

- **Không double-store:** message text ở tầng 1 là nguồn thật; tầng 2 chỉ giữ "phong bì" tham chiếu. Tầng 3 (cái phình) đẩy ra ngoài DB → phần trong Neon tăng rất chậm.
- **`audit_log` cần thêm:** `trace_id`/`turn_id` (nối tầng 1↔2) + tham chiếu entity bị đụng. Đây là nền cho note gốc #16 ("log all to fine-tune", "acceptance from AI's suggesting").
- **📝 2026-07-20 (encryption-review):** tầng 1 (message text) mã hóa cùng cơ chế cột (§7.1 dưới); **tầng 3 bắt buộc mã hóa file-level** (`age`) trước khi rời máy — off-DB không có nghĩa là off mã hóa, nếu không thì blob prompt-đã-giải-mã dựng lại đúng đường rò vừa bịt ở nơi khác. `audit_log.payload`: field đã mã hóa → chỉ ghi marker + entity id, không bao giờ ghi plaintext.

### D4. Full-text search — ⏸ DEFER → Bước 1
`tsvector`/`pg_trgm` phục vụ hybrid retrieval (structured + semantic + keyword) = Bước 1. Không provision bây giờ. **📝 2026-07-20:** chỉ áp cho cột KHÔNG mã hóa (§7.1) — đã mã hóa thì không tsvector, hết, không cân đo tỉ lệ rò.

---

## 6. Cỡ DB thực đo & đối chiếu Neon (grounding — đo thật, không ước tính)

Đo trực tiếp local Postgres `microschedule_v2` (nguồn migration thật, ~1 năm dùng) ngày 2026-07-19 bằng `COUNT(*)` chính xác (KHÔNG dùng `n_live_tup` — đó là ước tính, từng cho số sai lệch):

- **Tổng DB:** 10 MB. **Nội dung thật (schema `public`):** 163 task, 97 task_item, **49 note**, 81 note_item, 479 calendar_event, 4 source, 8 setting, 6 priority = **~887 dòng**; `agent_action_log` rỗng. Byte dòng thật < 1 MB — 10 MB gần như toàn overhead/index/schema test rỗng.
- **Đối chiếu:** dự án khác nặng hơn (`micareer_lite_db`) = 79 MB — vẫn ~6× dưới trần.

**Kết luận vs Neon free (0.5 GB = 500 MB/project, trần cứng):**
- **Nội dung người dùng là chuyện vặt nhiều năm.** Kể cả embedding (49 note → gần 0; 5000 note × 6KB = 30 MB) vẫn dư ~10×+.
- **Biến số DUY NHẤT** có thể đụng 0.5 GB = **log AI verbose không giới hạn** → chính vì vậy chiến lược 3 tầng D3 (giữ tầng 1–2 gọn, đẩy tầng 3 off-DB) không chỉ là kiến trúc sạch mà là **điều kiện ở lại free tier**.
- **Chi phí dôi dư có kiểm soát:** trên free, 0.5 GB là **trần cứng (chặn ghi khi đầy), KHÔNG phải hoá đơn bất ngờ**; vượt = **chủ động** nâng Launch (~$5). Blob nặng đã off-DB → không có kịch bản "cháy túi ngầm".
- **Trục compute:** Neon free cũng giới hạn **100 CU-h/tháng**. App always-on trên Fly nhưng single-user → Neon **autosuspend khi DB rảnh** → CU-h thấp; chỉ cần **cron đừng ping DB quá dày**.

---

## 7. ⏸ DEFER — Phiên thiết kế tính năng TRACKING (mục tiêu chiến lược, session sau)

**Chưa quyết ở Nhóm 2 vì cần thiết kế tính năng trước, KHÔNG phải quên.** Đây là một **phiên chiến lược + chi tiết riêng**, gom 3 thứ cùng một cụm:
1. **C2** — kiểu số `entry.value` (precision/scale: VND vs đơn vị sức khoẻ lẻ).
2. **D1-tracker** — cascade `tracker → entry` (nghiêng RESTRICT/soft-delete).
3. **Feature design** — theo dõi "hoạt động xấu" (thuốc/bia/bi-a) + chi tiêu, mô hình `tracker`/`entry` hợp nhất (note gốc #18; `forward-spec.md` §E).

Ràng buộc mang sang: xây **phần ghi-log trước**, AI phân tích thói quen/chi tiêu **giữ đúng thứ tự sau** (đừng để UI tracker nuốt thời gian 2 tính năng AI). Health/finance nhạy cảm → cân nhắc privacy khi AI đọc qua LLM bên thứ ba (bookmark Bước 1).

> **📌 2026-07-19 — phiên tracking ĐANG CHẠY** (`tracking-brief.md`): hướng giải đã ghi — **C2**: tách `entry.value` → `quantity` + bộ cột tiền VND (`amount`/`list_amount`/`orig_amount`+`orig_currency`), precision đề xuất `NUMERIC(14,0)` cho VND (⚠️ chờ gật cuối phiên); **D1-tracker**: giữ nghiêng RESTRICT + soft-delete (chưa chốt riêng). Phát sinh mới: **subscription = entity riêng** (✅ chốt, ngoài ERD v1) + **phiên encryption-review toàn DB** (ràng buộc: AI phải đọc được; điểm nóng: embedding rò nghĩa — chạm C4/D4). Khi phiên tracking kết thúc → cập nhật bảng §1 + mục này.

### 7.1 ✅ 2026-07-20 — PHIÊN ENCRYPTION-REVIEW ĐÃ ĐÓNG (E1, bảng §1)

Chi tiết đầy đủ + bảng phán quyết từng cột + lý do: `tracking-brief.md` §6 (mục "ĐÓNG ENCRYPTION REVIEW"). Tóm tắt neo vào file này (tầng vật lý):

- **Cơ chế:** app-level AES-GCM (`cryptography`), **không `pgcrypto`** (khóa không đi qua SQL tới Neon). Ciphertext version-prefix `enc:v1:…` để xoay khóa không cần touch mọi hàng.
- **Cột mã hóa:** `tracker.name` (toàn bộ), `subscription.name`, `entry.note`, `note.body_md`+`task.*` khi `is_private=true`, và **cột tiền** `amount`/`list_amount`/`orig_amount` (đánh đổi: mất `SUM`/`ORDER BY`/CHECK trực tiếp trong SQL, dashboard §8.2 tracking-brief kéo entry về app cộng bằng Python).
- **Cột giữ trần:** `note`/`task` không private (lõi retrieval Bước 1), `tracker_group.name`, `tracker.reminder_text` (bề mặt công khai có chủ đích), `calendar_event.*`/`app_setting`/timestamps/enum/id.
- **Hệ quả vật lý:** D4 (FTS) + C4 (embedding) chỉ áp cho cột KHÔNG mã hóa (đã ghi ngược ở từng mục trên); D3 tầng-3 blob bắt buộc mã hóa file-level (`age`) trước khi rời máy.
- **Khóa:** master key AES-GCM (Fly secrets + `.env` local) + private key `age` (mã hóa dump/blob tầng 3) — vị trí lưu cụ thể: `db-and-data-model-brief.md` §6.
- **Cửa một chiều thật sự:** chỉ có *bật mã hóa cột*. Cơ chế/vị trí khóa/thêm-bớt cột không phải cửa một chiều.

**📝 2026-07-20 (muộn) — Rà-soát tiền-DDL trước khi chạy `agent-tasks/006` (chi tiết + lý do: `tracking-brief.md` §10 mục K18–K21):** encryption-review lật cột sang 🔐 *sau* khi K1–K17 và §11 đã viết → quét chéo phát hiện và hòa giải sẵn 4 điểm: **K18** — mọi cột 🔐 có kiểu vật lý `TEXT` prefix `enc:v1:` (kể cả tiền; NUMERIC/CHECK của C2/K5 chuyển thành validate app-layer trước mã hóa, `quantity` trần giữ CHECK DB); **K19** — unique `lower(name)` (K2) chết im lặng trên ciphertext AES-GCM → bỏ index DB ở `tracker.name`/`subscription.name`, chống-trùng chuyển lên app (cửa nâng cấp: cột `name_hmac`); **K20** — tiền của `subscription` mã hóa cùng bộ với tiền entry; **K21** — bảng `session` theo đúng B2, bảng message tầng-1 có bộ cột tối thiểu ghi sẵn. Executor 006 làm theo K18–K21, không tự hòa giải lại.

---

> **✅ 2026-07-19 (muộn) — PHIÊN TRACKING ĐÃ ĐÓNG, §7 GIẢI TRỌN.** C2 + D1 như bảng §1 (lưu ý VND-only v1: `orig_amount`/`orig_currency` bị cắt). Phát sinh chốt thêm: **+2 bảng** `tracker_group` (nhóm 2 tầng; không soft-delete, hard-delete + FK `SET NULL`) và `subscription` (DATE cho `started_on`/`expires_on` — ngoại lệ có lý với B2; không cột `status` — suy ra từ `expires_on`+`canceled_at`); **cột mới `tracker`**: `direction` in/out, `input_mode` event/money/quantity, `group_id`, `reminder_time TIME`/`reminder_text` (nhắc thuốc), `unit` thu hẹp nghĩa; **cột mới `entry`**: `quantity`/`amount`/`list_amount`/`subscription_id`; **enum C1 mở rộng**: `direction`, `input_mode`; **index D2 cập nhật**: `entry(tracker_id, occurred_at DESC)` composite thay cặp rời + `entry(occurred_at)` + `subscription(expires_on)`; **seed danh mục** = Alembic data-migration lúc cutover (khớp kỷ luật A2). Toàn bộ chi tiết + lý do + rà soát chuẩn hóa (3NF, K1–K17): **`tracking-brief.md`** (đặc biệt §10). **Schema toàn dự án khép từ đây.**

---

### 7.2 ✅ 2026-07-20 — RÀ-SOÁT TIỀN-DDL VÒNG 2 (K22–K25), phát sinh từ escalation của 006

**Bối cảnh:** executor 006 (Sol/xhigh) dừng **trước khi viết DDL** theo giao thức HITL và báo 4 điểm brief chưa cho đáp án duy nhất. T1 kiểm chứng: **cả 4 có thật**. Chủ quyết cùng ngày. Đây là bằng chứng giao thức HITL hoạt động — 4 lỗ này nếu để executor tự lấp thì chỉ lộ ra sau khi đã có data.

| # | Chốt | Lý do |
|---|---|---|
| **K22** | **`task.priority` = TEXT + CHECK `('p1','p2','p3')`, `p1` cao nhất.** NULL = chưa đặt ưu tiên (không ép mọi task phải có). Không seed, không bảng lookup. | Hệ ưu tiên 6-mức của app cũ **chủ thực tế không dùng** → đơn giản hoá còn 3. Chọn dạng viết `'p1'/'p2'/'p3'` thay vì `'1'/'2'/'3'` hay `'high'/'medium'/'low'`: **sắp xếp đúng thứ tự tự nhiên** (text `p1<p2<p3`) **và** AI hiểu được sau một lần giải thích. `'high'/'low'` sắp xếp sai theo alphabet; `'1'/'2'/'3'` thì AI không tự biết chiều nào là cao. |
| **K23** | **Phạm vi mã hoá của `task` khi private = CHỈ cột chữ:** `task.title`, `task.body_md`, `task_item.content`. **Giữ trần:** `status`, `priority`, `due_at`, `is_private`, mọi khoá và timestamp. Giải toả dấu `*` mơ hồ trong §7.1. | Ngày + `'p1'` gần như không rò gì theo threat-model (§1 `devops-brief`). Mã hoá cột cấu trúc sẽ (a) **xung đột trực tiếp với CHECK** của C1 — không thể vừa mã hoá vừa kiểm giá trị, (b) buộc **mọi** truy vấn task phải kéo về app giải mã rồi mới lọc/sắp, đổi lấy gần như không thêm quyền riêng tư. `is_private` bắt buộc để trần vì chính nó là cột dùng để lọc. |
| **K24** | **`app_setting` theo đúng B1: `id` UUIDv7 PK + `key` TEXT UNIQUE NOT NULL.** Không ngoại lệ. | Ban đầu T1 nghiêng `key` làm PK cho gọn, **đã đổi ý sau khi soi hệ quả code**: B1+B2 hàm ý một **lớp cơ sở dùng chung** (id + timestamps + trigger); bảng nào không có `id` thì không dùng được lớp đó → phải nuôi một ngoại lệ trong mọi thứ đụng tới bảng, **vĩnh viễn**. Cột thừa = giá **một lần**; ngoại lệ = giá **lặp lại**. Đổi tên key cũng thành thao tác thường thay vì đổi danh tính dòng. |
| **K25** | **Ranh giới uỷ quyền cho executor** (chi tiết còn thiếu: nullability, default, hình dạng trace metadata): executor **được tự quyết**, đổi lại **bắt buộc liệt kê mọi lựa chọn đã tự quyết thành một bảng trong PR** để T1 duyệt một lượt. Vẫn giữ nguyên luật escalate khi gặp *mâu thuẫn* giữa 2 brief. | Chốt tay hàng trăm cột là đốt một buổi cho thứ phần lớn không có ý nghĩa sản phẩm. Đổi mô hình từ "quyết trước" sang "**duyệt sau theo danh sách**" — giữ kiểm soát, bỏ tắc nghẽn. Cùng tinh thần mandate K1–K17. |

| **K26** | **Sửa lại uỷ quyền K25 sau khi T1 duyệt danh sách (2026-07-21):** `note.title`, `note.body_md`, `task.body_md` → **nullable**. `task.title` giữ NOT NULL. CHECK ciphertext viết tường minh `... IS NULL OR ... LIKE 'enc:v1:%'` thay vì dựa ngầm vào logic ba-giá-trị của SQL. | Executor để cả bốn cột NOT NULL — hợp lý về mặt dữ liệu nhưng **va thẳng vào nguyên tắc capture-một-chạm**: không tạo nổi note nếu chưa nghĩ ra tiêu đề. App sẽ buộc phải nhét `''`, và từ đó "chưa đặt" với "đặt rỗng" không phân biệt được nữa. Sửa lúc DB rỗng = miễn phí; sau cutover = migration + backfill. Một việc thì phải có tên gọi nên `task.title` giữ nguyên. **Đã kiểm chứng thật trên Neon:** note NULL/NULL insert được, task chỉ-tiêu-đề insert được, task NULL-title bị chặn. |

**📌 Ghi chú mở đường (chưa phải quyết định):** chủ nêu ý muốn sau này thêm mức kiểu `'Cố định'` / `'Trọng đại'`. Theo khung quản lý danh mục (`tracking-brief.md` §10 — tiêu chí *"code có cần hiểu giá trị để rẽ nhánh không?"*), `priority` thuộc **enum cứng** → thêm giá trị = **một migration nhỏ**, hoàn toàn rẻ, không phải sửa từ UI. ⚠️ Nhưng lưu ý mô hình: *"Cố định"* và *"Trọng đại"* nghe như **trục khác** với độ-gấp — nếu sau này một task cần **vừa** `p1` **vừa** "cố định" thì một cột không diễn đạt nổi, lúc đó thêm cột/cờ riêng (migration cộng thêm, vẫn rẻ). Ghi lại để sau này không ai nhồi hai trục vào một cột.

---

## 8. Ngoài phạm vi Nhóm 2 (vẫn OPEN ở nơi khác — không phải việc file này)
- **Auth implementation** — ✅ chốt 2026-07-20 (`auth-brief.md`): Authlib + bảng **`session`** mới (server-side, theo house-rules B1/B2; cột đúc lúc scaffold/Alembic) + cờ `is_private` trên message tầng-1 (luật R4 AI×private) + key TTL trong `app_setting`. Không phạm "schema khép" — mục này vốn để dành cho phiên auth.
- **Frontend UI stack** — ✅ chốt 2026-07-20 (`frontend-brief.md`): React 19 + TS + Vite 8 + Tailwind/shadcn + TanStack Query + Dexie/outbox tự viết; web-push chi tiết + router/chart để scaffold/build.
- **Embedding model cụ thể + dimension cột `vector`** + LLM mặc định — Bước 1 (coupling C4). Ràng buộc mới từ encryption-review: chỉ chọn provider đạt bar no-retention/no-training (§7.1).

---

## 9. Giải nghĩa nhanh (glossary — cho chỗ dày thuật ngữ)

- **ORM** (Object-Relational Mapping): thư viện cho viết class Python thay vì SQL thô; nó dịch class ↔ bảng. SQLModel/SQLAlchemy là ORM.
- **DDL** (Data Definition Language): các câu SQL *định nghĩa cấu trúc* (`CREATE TABLE`, `ALTER TABLE`), khác DML (`INSERT/UPDATE` dữ liệu).
- **Migration / Alembic**: file phiên bản hoá thay đổi schema (như "git cho cấu trúc DB"); Alembic = công cụ migration của SQLAlchemy. **Autogenerate** = Alembic tự đoán diff giữa model và DB (tiện nhưng hay sót → cần QA §2).
- **UUID / UUIDv7**: mã định danh 128-bit *toàn cục duy nhất*, sinh được không cần server điều phối. **v7** = biến thể có tiền tố thời gian → sắp thứ tự được, index tốt. **RFC 9562** = chuẩn IETF (2024) định nghĩa các version UUID.
- **`bigint serial`**: khoá chính số tăng dần **do server cấp** → không sinh offline được (lý do loại cho app này).
- **`timestamptz`**: kiểu thời gian *có* timezone (khác `timestamp` naive không timezone).
- **Trigger**: đoạn logic DB tự chạy khi có sự kiện (vd `BEFORE UPDATE` để set `updated_at`).
- **`CHECK` constraint**: ràng buộc "giá trị cột phải thoả điều kiện" (vd `status IN ('open','completed')`) — cách làm enum bằng `TEXT`.
- **Index / B-tree**: cấu trúc phụ tăng tốc tìm kiếm (như mục lục sách); B-tree = loại index mặc định. **HNSW** = loại index cho tìm kiếm vector (semantic), dựng ở Bước 1.
- **`pgvector` / `vector` / `halfvec`**: extension Postgres cho lưu + tìm vector embedding; `halfvec` = vector nửa độ chính xác (2 byte/chiều thay 4) → nửa storage.
- **`ON DELETE CASCADE` / RESTRICT**: khi xoá dòng cha → CASCADE xoá luôn dòng con; RESTRICT chặn xoá nếu còn con.
- **Soft-delete**: không xoá thật, chỉ đánh dấu `deleted_at` → khôi phục được.
- **`JSONB`**: kiểu cột lưu JSON nhị phân, query được (dùng cho `app_setting.value`, `audit_log.payload`).
- **Trace / audit_log**: nhật ký hành động (đặc biệt của AI) để eval/observability + fine-tune.
- **`trace_id`**: mã nối các bản ghi cùng một lượt tương tác AI (message ↔ metadata ↔ blob).
- **CU-h** (Compute Unit-hour): đơn vị tính compute của Neon; free = 100 CU-h/tháng.
- **Autosuspend / scale-to-zero**: DB tự ngủ khi rảnh (tiết kiệm CU-h), dậy khi có query.
- **Fractional indexing / LexoRank**: kỹ thuật đánh thứ tự bằng số thực để chèn giữa không phải đánh lại — *không dùng* ở đây (đã chọn `int` đơn giản).

---
*Cập nhật khi: đổi ORM/DB/khoá chính, hoặc sau phiên tracking (§7). Thêm ghi chú có ngày — không xoá trắng kết luận cũ.*
