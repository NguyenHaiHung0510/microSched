# 006 — Neon + role riêng + đúc DDL thật (SQLModel + Alembic 0001 + QA gates)

> **Trạng thái:** 📋 TODO (chạy sau 005)
> **Executor dự kiến:** T2 — Codex · **Bậc model: Sol (bậc cao)** · **Effort:** high · **Skill gợi ý:** (không) · **MCP cần:** (không — Postgres MCP đọc-ghi DB thật KHÔNG được dùng ở task này; ranh giới dữ liệu `devops-brief` §7)
> *Lý do bậc: schema vật lý là CỬA MỘT CHIỀU sau khi có data — đây là task giá trị nhất và rủi ro nhất của cả chuỗi scaffold. Đọc kỹ, làm chậm, escalate sớm.*

## Bối cảnh (đọc trước — bắt buộc, nhiều file)

Đọc `CLAUDE.md`, rồi **toàn bộ** các brief sau — chúng LÀ spec của schema, file này chỉ là khung việc:

- `docs/schema-physical-brief.md` — house-rules: A1 SQLModel · A2 Alembic + hàng rào QA · A3 role riêng `microsched_app` + schema namespace `microsched` · B1 PK UUIDv7 · B2 `timestamptz` + trigger `updated_at` đồng đều · C1 enum TEXT+CHECK · C3 `position` int · **C4 cột `vector` (đọc kỹ — dimension thuộc phiên AI Bước 1, KHÔNG tự quyết)** · D1 cascade · D2 index tối thiểu · D3 log AI 3 tầng + soft-delete · §7.1 kết luận encryption (cột nào là ciphertext).
- `docs/schema-v1-brief.md` — danh sách entity + quan hệ.
- `docs/tracking-brief.md` — `tracker`/`entry`/`tracker_group`/`subscription` + §10 (**K1–K21**, gồm composite-FK tracker↔group) + §11/§12. **Đặc biệt K18–K21 (rà-soát tiền-DDL 2026-07-20):** các mâu thuẫn encryption↔schema đã được hòa giải sẵn ở đó (kiểu cột 🔐 = TEXT `enc:v1:`, CHECK tiền → app-layer, bỏ unique DB trên tên mã hóa, tiền subscription cũng 🔐, session theo B2, cột tối thiểu bảng message) — làm theo, **đừng tự hòa giải lại**.
- `docs/auth-brief.md` §2/§6 — bảng `session` (cột dự kiến), cờ `is_private` trên message tầng-1, key `app_setting` cho TTL private-unlock.
- `docs/db-and-data-model-brief.md` — Neon; `docs/migration-mapping-brief.md` — chỉ để biết data sẽ đổ vào sau (task này KHÔNG cutover).

**Sự thật môi trường đã xác minh 2026-07-20 (đừng tra lại, đừng đoán):**
- Neon project **đã tạo**: region **AWS Asia Pacific 1 (Singapore)** — khớp Fly `sin` ✅ · **Postgres 18** → `uuidv7()` **native có sẵn**, dùng thẳng theo B1, **không** cần đường sinh UUID phía app · Free tier: 0.5 GB storage, 100 CU-hrs, history retention 6h.
- Compute Neon **tự ngủ khi idle (~5 phút) và dậy ~1s** — đây là hành vi **đã chấp nhận có ý thức** (`db-and-data-model-brief.md` §31), KHÔNG phải sự cố, KHÔNG được "sửa" bằng cách đổi provider/plan. Nhưng **hãy đo thật** và ghi vào PR: thời gian query đầu tiên sau khi compute ngủ. Nếu vượt ~3s thì báo cáo — chủ cần biết vì cold-start là dealbreaker của dự án này ở read-path tương tác.

**Việc của CHỦ trước khi chạy task:**
- [x] ~~Tạo Neon project~~ — **XONG 2026-07-20** (region Singapore đã xác nhận).
- [x] ~~Đặt connection string owner vào `.env` local~~ — **XONG 2026-07-20** (chuỗi `neondb_owner`).
- [ ] Sau khi task tạo role app: đặt `DATABASE_URL` (role `microsched_app`) vào `.env` + `fly secrets set DATABASE_URL=...` — **chủ tự chạy, sau khi merge**.

**⚠️ Hai chuỗi kết nối, hai vai — KHÔNG được trộn (làm rõ 2026-07-20):**

| Biến env | Vai | Ai dùng | Lên Fly secrets? |
|---|---|---|---|
| `NEON_OWNER_URL` | `neondb_owner` — quyền cao | **chỉ** script bootstrap ở mục 1, chạy **từ máy chủ** | ❌ **KHÔNG BAO GIỜ** |
| `DATABASE_URL` | `microsched_app` — least-privilege (A3) | app runtime + Alembic | ✅ (chủ tự set sau) |

*Lý do (chốt A3): app cầm quyền owner thì nếu bị khai thác, kẻ tấn công `DROP SCHEMA` / tạo-xoá role tuỳ ý — toàn bộ ý nghĩa của role least-privilege mất sạch. Owner chỉ tồn tại trong bootstrap một lần, từ máy chủ, không bao giờ rời máy đó.*

→ **Việc của agent:** đổi script bootstrap đọc `NEON_OWNER_URL` (không phải `DATABASE_URL`); cập nhật `backend/.env.example` có **cả hai** biến kèm placeholder an toàn + comment một dòng nói rõ biến nào lên Fly, biến nào không. Nếu code chạy được mà nhầm hai biến này thì đó vẫn là **lỗi nghiêm trọng**, không phải chi tiết nhỏ.

## Giao thức quyết định — HITL (bổ sung 2026-07-20, áp riêng cho task này)

Task này có **blast-radius lớn nhất chuỗi** (cửa một chiều sau khi có data), nên đổi luật mặc định: gặp fork thật thì **KHÔNG tự chọn rồi ghi vào PR** — **DỪNG và trình bày cho chủ quyết trước khi code tiếp**.

**Fork thật** = thứ ảnh hưởng hình dạng schema hoặc không đảo ngược được rẻ. **Không phải fork thật** = tên biến, thứ tự import, cách chia file — cứ tự quyết, đừng hỏi.

**Trình bày theo đúng khuôn này** (đây là cách chủ yêu cầu mọi tư vấn, không phải format tuỳ hứng):
1. **Quyết định là gì** — một câu, và *tại sao nó không đảo ngược được rẻ*.
2. **Các phương án** kèm trade-off **khách quan** (không "tốt hơn" chung chung — nêu đánh đổi cụ thể).
3. **Tại sao KHÔNG chọn từng phương án bị loại** — phần này bắt buộc, quan trọng ngang phần đề xuất.
4. **Khuyến nghị của bạn + lý do**, nêu rõ mức tự tin.
5. Nếu quyết định phụ thuộc dữ kiện ngoài (giá, benchmark, hỗ trợ ngôn ngữ…) → **nói rõ cần tra gì**, đừng đoán từ trí nhớ.

**Escalate NGAY (không thử tự giải) khi:** hai brief mâu thuẫn nhau · một quyết định trong brief không áp được vào thực tế Postgres/Neon · phát hiện thứ khiến một quyết định đã ✅ CHỐT trở nên sai.

## Mục tiêu

Toàn bộ schema đã khép thành SQLModel models + **một migration Alembic `0001`** chạy sạch trên Neon (schema `microsched`, role `microsched_app`) và trên Postgres CI; hàng rào QA migration chạy trong CI.

## Phải làm

1. **Bootstrap Neon** (script SQL/`psql` đặt trong repo, chạy bằng owner-connection từ `.env`): tạo schema `microsched`, role `microsched_app` **least-privilege** đúng A3 (không owner; đủ quyền CRUD trên schema app). Bật extension `pgvector` (cần cho C4 dù cột vector chưa chốt dimension — làm đúng theo C4).
2. **SQLModel models** cho **toàn bộ bảng đã khép**: `task`, `task_item`, `note`, `note_item`, `calendar_source`, `calendar_event`, `tracker`, `entry`, `tracker_group`, `subscription`, `app_setting`, `audit_log`, `session`, + bảng log AI theo D3 (tầng message + tầng trace; tầng 3 là blob off-DB — không có bảng). Áp **đồng đều** house-rules B1/B2/C1/C3/D1/D2 + các K-item của tracking-brief §10. DB đang rỗng → 1 migration lớn là an toàn và đúng chủ đích ("đúc một lần từ schema đã khép").
3. **UUIDv7 (B1):** kiểm tra version Postgres thực tế trên Neon — PG18 có `uuidv7()` native; nếu Neon chưa cho PG18 thì sinh UUIDv7 phía app (lib Python) + default phía app, ghi rõ đường đã chọn vào PR (brief đã lường cả hai).
4. **Cột mã hóa (§7.1):** đúc đúng kiểu cột ciphertext cho các cột đã kết luận (tên tracker/subscription, note của entry, cột tiền, body private…) — **code mã hóa AES-GCM KHÔNG thuộc task này**, chỉ đúc chỗ chứa. Cột đã mã hóa thì không index nội dung, không tsvector (luật cứng).
5. **Alembic**: init + migration `0001` từ models; lệnh chạy ghi vào `backend/README.md`.
6. **Hàng rào QA (A2) vào CI**: job `migration-qa` — Postgres service container: `alembic upgrade head` → **drift-check** (autogenerate lần 2 phải ra diff RỖNG) → **round-trip** (`downgrade base` → `upgrade head` lại sạch) → chặn thao tác drop ngầm ngoài ý muốn theo đúng A2. Job này chạy bằng container CI, **không cần secret Neon**.
7. **Healthz mở rộng**: thêm check kết nối DB (fail-soft: báo `db: "down"` chứ không sập app) — để Fly health-check vẫn phản ánh đúng.
8. **Ghi nhận**: `agent-tasks/README.md` trạng thái 006; note có ngày vào `schema-physical-brief.md` §1 (bảng trạng thái: đã đúc DDL, ngày, migration id) — **không sửa nội dung quyết định nào**.

## KHÔNG được làm

- **Không** tự quyết bất kỳ chi tiết schema nào chưa chốt hoặc mâu thuẫn giữa các brief — **DỪNG và escalate T1** kèm trích dẫn 2 đoạn mâu thuẫn. Schema là cửa một chiều; một cột sai âm thầm hôm nay là nợ vĩnh viễn.
- **Không** chốt dimension cột `vector`, **không** chọn embedding model, **không** tạo index HNSW — kể cả khi thấy "có vẻ hợp lý" hoặc được hỏi tới. C4 đã cố ý tách rời: cột `vector` **nullable, KHÔNG dimension, KHÔNG index**; dimension + HNSW đi ở **migration riêng của Bước 1**. *Lý do tách (đọc kỹ trước khi định làm khác): chọn embedding model là quyết định NGHIÊN CỨU — phụ thuộc leaderboard tại thời điểm chọn, mức hỗ trợ tiếng Việt, bar no-retention của R3, và hạn mức free-tier đang có. Gắn nó vào task DDL sẽ (a) đốt mất option value vì leaderboard đổi từng quý, (b) trộn nghiên cứu vào thi công khiến PR không review nổi. Đây là phiên quyết định riêng với T1, KHÔNG phải hạng mục của 006.*
- **Không** đổ data / cutover / đụng vào Postgres local `microschedule_v2` hay SQLite cũ (hard boundary trong `CLAUDE.md`).
- **Không** viết code mã hóa, CRUD, API endpoints (ngoài healthz mở rộng).
- **Không** dùng superuser `postgres` local cho bất kỳ việc gì của app.
- **Không** commit connection string thật (gitleaks đang canh — rule 002 bắt cả URI có password). **Không** rewrite history.

## Acceptance (kiểm chứng được)

- [ ] `alembic upgrade head` sạch trên Neon (qua role `microsched_app`) **và** trên Postgres container CI.
- [ ] Autogenerate lần 2 → diff rỗng (drift-check pass); round-trip downgrade/upgrade pass.
- [ ] `psql \dt microsched.*` liệt kê đúng danh sách bảng ở mục 2.
- [ ] Trigger `updated_at` hoạt động (UPDATE thử một row → cột đổi).
- [ ] Role `microsched_app` không tạo được bảng ngoài schema `microsched` (thử và bị từ chối — chứng minh least-privilege).
- [ ] CI 4 job xanh (backend, frontend, hooks, migration-qa); gitleaks sạch.

## Bàn giao

Branch **`feat/006-neon-alembic-ddl`** → PR vào `develop`. PR bắt buộc có: bảng tóm tắt "mỗi bảng → mục brief nào quyết nó" (để T1 review đối chiếu nhanh), các quyết định thi hành nhỏ đã chọn, output verify. Người merge = chủ sau khi T1 review kỹ (đây là PR đáng review chậm nhất chuỗi). Commit message tiếng Việt *tại sao*, kèm `Co-Authored-By:` của agent thực thi.
