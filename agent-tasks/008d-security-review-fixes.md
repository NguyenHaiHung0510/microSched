# 008d — Ba mục tồn từ security review toàn dự án (2026-07-23)

> **Trạng thái:** 📋 SPEC — sẵn sàng giao (2026-07-23). **Không còn mục nào chờ chủ quyết.**
> Executor: **Agent Claude/Opus (T1)** · Effort: **MAX** · **Skill gợi ý:** không cần · **MCP cần:** không cần (không có phần nào phải nhìn bằng mắt trên trình duyệt)
>
> **📝 2026-07-24 — đổi executor + effort so với dòng gốc (T2 Codex / Terra-Sol / thấp).** Cả ba mục là security-critical (Mục 1 đụng migration + bất biến mã hoá, Mục 3 đụng đường auth, Mục 2 đụng hàng rào secret), mà `CLAUDE.md` §7 giao **T1** viết code security-critical — Codex vào việc thật ở **008** (CRUD slice), không phải ở đây. Effort **MAX** vì migration là chỗ lỗi đắt (CHECK sai = rò tiêu đề private âm thầm; migration không round-trip = Migration QA gãy), chi phí MAX trên task nhỏ không đáng kể. Quyết bởi Claude-điều-phối, khớp khuôn 008a.

## Bối cảnh (đọc được ở session 0-context)

Ngày 2026-07-23 chạy security review **toàn bộ `develop`** thay vì chỉ diff nhánh — lý do: lệnh review mặc định lấy scope `git diff main...develop`, mà từ 2026-07-22 `main` không còn nghĩa "phần đã soi" (nó là nhãn release đang tụt, `devops-brief.md` §2.1). Scope đó soi 11/47 file code và **bỏ sót đúng tầng bảo mật lõi**.

Đọc lại toàn bộ `backend/app/**` (~1.311 dòng) + scripts + migration + workflow + frontend. Kết quả: **không có lỗ hổng cho phép chiếm quyền hay rò dữ liệu người dùng.** Session/OAuth/phân quyền route/phân quyền DB/tham số hoá SQL đều sạch. Ba mục dưới đây là phần còn lại — hai mục là khe hở phòng thủ, một mục là **quyết định thiết kế chưa từng được quyết**.

Mục ⓐ `/api/readyz` chạy SQL không cần auth **đã được chủ xử lý 2026-07-23**, không nằm trong spec này.

---

## Mục 1 — Bất biến `private ⇒ ciphertext` áp không đồng đều

### ✅ CHỦ ĐÃ QUYẾT 2026-07-23 — executor thi hành, không mở lại

> **Chốt: phương án A — `note.title` mã hóa theo cờ, bằng `task`.** Lý do đầy đủ đã ghi vào `docs/tracking-brief.md` §6 (note 2026-07-23) — đọc ở đó, không chép lại vào PR.
> **Bảng con `note_item`/`task_item`: app-layer canh, KHÔNG phải DB.** Cũng ở §6.
>
> Phần nền dưới đây giữ nguyên để đọc được ở session 0-context — nó giải thích *vì sao* hai bảng lệch nhau, thứ mà chỉ nhìn diff sẽ không thấy.

Hai bảng cùng loại dữ liệu đang mã hoá hai câu trả lời khác nhau cho cùng một câu hỏi.

`Task` — [`backend/app/domain/models.py:98`](../backend/app/domain/models.py) ràng buộc **cả title lẫn body**:

```python
"NOT is_private OR ("
"title LIKE 'enc:v1:%' "
"AND (body_md IS NULL OR body_md LIKE 'enc:v1:%'))",
name="private_ciphertext",
```

`Note` — [`backend/app/domain/models.py:157`](../backend/app/domain/models.py) ràng buộc **chỉ body**; `note.title` (dòng 164) không có ràng buộc nào:

```python
"NOT is_private OR body_md IS NULL OR body_md LIKE 'enc:v1:%'",
name="private_body_ciphertext",
```

**Không bên nào "quên", và không bên nào sai spec.** Dòng phán quyết ở `tracking-brief.md` §6 viết nguyên văn:

> `note.body_md`, **`task.*`** khi `is_private=true` │ 🔐 mã hóa **theo cờ**

`task.*` = **mọi cột text của task**; `note` thì chỉ nêu đúng một cột. ⇒ **Cả hai DDL đều thi hành trung thực.** Bất đối xứng nằm **bên trong một dòng của brief**, viết trong cùng một lượt, ở hai mức chi tiết khác nhau.

Điều đó đổi bản chất câu hỏi: **không có quyết định nào để tôn trọng ở cả hai phía.** Câu hỏi *"tiêu đề note private có phải secret không"* chưa bao giờ được đặt ra — chứ không phải được quyết rồi bị làm sai. Cùng họ sự cố Neon 22/07.

**Vì sao đáng quyết bây giờ, không để sau:**
- **008 là task đặt khuôn**, 009–012 chép lại. Sai khuôn ở đây là sai 5 lần.
- Sửa CHECK constraint sau khi đã có dữ liệu private thật = migration có backfill (phải giải mã/mã hoá lại). Sửa bây giờ khi bảng còn rỗng = một migration thuần DDL.
- `note.embedding` nằm **cùng bảng** ([`models.py:166`](../backend/app/domain/models.py)). Ruleset R1–R7 cấm cột mã hoá vào pgvector; nếu `title` là plaintext thì **không có gì chặn** nó bị embed — tức câu trả lời cho mục này quyết luôn một nhánh của phiên AI Bước 1.

**Có một tiền lệ mạnh trong chính repo** — `tracking-brief.md:76`:

> *"tên tracker `'Hút thuốc'` rò gần hết thông tin dù mọi entry mã hóa. Mã hóa entry mà để tên tracker trần = bảo mật hình thức."*

Lập luận đó áp cho `tracker.name` (⇒ mã hoá **vô điều kiện**). Tiêu đề note private là cùng hình dạng: tiêu đề thường mang gần hết thông tin của note.

### Hai lựa chọn đã cân — ✅ chọn A

| | **A — siết `note` cho bằng `task`** | B — nới `task` cho bằng `note` |
|---|---|---|
| Làm gì | thêm `title` vào CHECK của `note` | bỏ `title` khỏi CHECK của `task` |
| Được | bất biến đồng nhất; khớp tiền lệ `tracker.name` | tiêu đề task private còn sort/tìm được trong SQL |
| Mất | tiêu đề note private phải giải mã app-side để sort/hiển thị | tiêu đề task private nằm plaintext trong Neon; **và phải sửa một DDL đã deploy** |
| Ghi chú | ✅ **khuyến nghị** (lý do bên dưới) | chỉ chọn nếu chủ xác nhận tiêu đề **không** nhạy |

**Bốn lý do nghiêng A:**

1. **§6 đã lập luận sẵn, chỉ là không mang qua.** Lời của chính brief: *"tên tracker `'Hút thuốc'` rò gần hết thông tin dù mọi entry mã hóa. Mã hóa entry mà để tên tracker trần = **bảo mật hình thức**."* Tiêu đề note cùng hình dạng với tên tracker — nhãn người-đọc-được nén nội dung lại. §6 hành động theo lập luận đó cho `tracker.name` (mã hoá **vô điều kiện**), rồi dừng ở đó.
2. **B làm chính câu biện minh của §6 thành sai.** §6 giải thích vì sao mã hoá nội dung private: *"Nội dung private vốn đã không vào FTS/embedding nên không mất gì thêm."* Dưới B, `note.title` vẫn trần khi private ⇒ **đủ điều kiện** vào FTS/embedding ⇒ tiêu đề note private chảy được vào pgvector. Mâu thuẫn trực tiếp với luật §6 (*"không-embed/FTS trên cột mã hóa"*) và với R1–R7. Dưới A không có lỗ này.
3. **Chi phí của A ≈ 0, và là chi phí đã chấp nhận rồi.** §6 đã chốt *"sort/hiển thị ở app-side"* cho `tracker.name`; **K19** đã chuyển chống-trùng-tên lên app-layer cho cột tên mã hoá; **K18** chốt nguyên tắc *"PG không nhìn được thì app lo"*. A không thêm **loại** việc nào mới — dùng lại đúng bộ máy 008a bắt buộc phải dựng. Quy mô: 49 note.
4. **B đắt hơn A** — đòi sửa một DDL đã chạy production, để khớp một cách viết nhiều khả năng là sơ suất soạn thảo.

**Kèm theo (bắt buộc, dù chọn A hay B):** sửa dòng §6 cho hết mơ hồ — liệt kê **đủ tên cột** cho cả hai bảng thay vì `task.*`, kèm dated note ghi rõ *đây là vá bất đối xứng soạn thảo, không phải đảo quyết định*. Cách viết `*` là thứ đã sinh ra cả mục này.

### Mục con: bảng `*_item`

`note_item.content` ([`models.py:193`](../backend/app/domain/models.py)) và `task_item` **không có cờ `is_private`, cũng không có ràng buộc nào** — tức hiện tại **không có cách nào diễn đạt** "item này thuộc một cha private". Checklist con của một note private đang nằm plaintext không ràng buộc.

Đây là câu hỏi thứ hai, quyết cùng lúc — nhưng **hai luật đã khoá sẵn phần lớn không gian**, đọc trước khi cân:

- **K11** (`tracking-brief.md` §10) chốt: *"`is_private` đặt ở cấp **cha** (task/note/tracker), **không rải từng** entry"* ⇒ phương án "nhân bản cờ xuống bảng con + CHECK có điều kiện" **hết cửa** — nó chính là thứ K11 cấm.
- **Posture §6 = "B-hẹp"**: *"mã hóa đúng nhóm 'lộ = nguyên liệu pretext', **KHÔNG mã hóa rộng** vì đánh chết AI-first"* ⇒ mã hoá `content` vô điều kiện (kiểu `message.content`, [`models.py:440`](../backend/app/domain/models.py)) đi ngược posture, vì item **non-private là vật liệu retrieval**. Nó còn phá một tính chất đã ghi ở `agent-tasks/README.md`: *"dữ liệu migrate không chạm cột mã hóa nào ⇒ rủi ro backfill ≈ 0"* — chính lý do 008a xếp được sớm và rẻ. Chọn nó thì 97 `task_item` + 81 `note_item` phải mã hoá lúc cutover.

Còn lại đúng hai — ✅ **chủ chọn (b) app-layer**:

| | (a) trigger tra cha | **(b) enforce ở app-layer** |
|---|---|---|
| Cưỡng chế ở | DB (không phạm K11 vì không thêm cột) | seam crypto của 008 |
| Được | bất biến không thể lách kể cả ghi từ ngoài app | không thêm cơ chế mới; đúng nguyên tắc **K8/K18** repo tự đặt (*"PG không nhìn được thì app lo"*) |
| Mất | thêm một loại cơ chế (hiện repo chỉ có `set_updated_at`) | bất biến **chỉ tốt bằng seam ở 008** |
| Đáng chọn khi | có đường ghi từ ngoài app | ✅ single app, single writer — đúng dự án này |

**⚠️ Cảnh báo đi kèm nếu chọn (b):** 009–012 sẽ **chép lại** khuôn của 008, nên test cho bất biến này ở 008 quan trọng hơn bình thường và **bắt buộc chứng minh được biết đỏ**. Ghi nó vào docs như một **bất biến KHÔNG được DB cưỡng chế** — nói thẳng ra, đừng để người đọc sau tưởng có CHECK đứng gác.

### Phải làm

1. **`Note` trong `backend/app/domain/models.py`:** thêm `title` vào `CheckConstraint`, cho khớp hình dạng của `Task`. `title` là `nullable=True` nên phải chịu NULL:
   ```
   NOT is_private OR (
     (title IS NULL OR title LIKE 'enc:v1:%')
     AND (body_md IS NULL OR body_md LIKE 'enc:v1:%')
   )
   ```
   Đổi luôn `name=` cho hết sai lệch (`private_body_ciphertext` → `private_ciphertext`, bằng `Task`).
   **KHÔNG đụng `Task`** — nó đã đúng.
2. Sinh migration Alembic mới (**không sửa `0001_initial_schema.py`** — nó đã chạy trên production). Đổi tên constraint = `drop` + `create`, viết cả `downgrade`.
3. Test ở `backend/tests/test_schema_models.py`: `is_private=true` + `title` trần phải **bị DB từ chối**; `title IS NULL` + body ciphertext phải **được nhận**. Test phải **chứng minh được biết đỏ** (bỏ constraint → đỏ; hoàn nguyên → xanh), dán output cả hai chiều.
4. `docs/tracking-brief.md` §6 **đã có** note quyết định 2026-07-23 — đọc, đừng viết lại. Chỉ bổ sung nếu thi công phát hiện điều §6 chưa lường.
5. **`*_item`: không đụng schema.** Quyết định là app-layer (§6). Ở task này chỉ ghi bất biến đó vào `docs/tracking-brief.md` §6 nếu chưa đủ rõ — **việc cài đặt thuộc seam crypto của 008**, không thuộc 008d.

---

## Mục 2 — gitleaks không phủ hai biến quyền cao nhất dự án

[`.gitleaks.toml:28`](../.gitleaks.toml) — rule `microsched-db-env-var-value` chỉ liệt kê `DATABASE_URL` và `PGPASSWORD`:

```
regex = '''(?i)(DATABASE_URL|PGPASSWORD)\s*=\s*['"]?[A-Za-z0-9_\-:/.@]{4,}[0-9][A-Za-z0-9_\-:/.@]{2,}['"]?'''
```

Nhưng bảng cấp phát ở [`backend/.env.example`](../backend/.env.example) nói rõ `NEON_MIGRATOR_URL` và `NEON_OWNER_URL` là hai chuỗi **quyền cao nhất** (đổi schema, tạo role — hai dấu ⛔ "không bao giờ lên Fly"). Cả hai **không có trong rule này**, nên chỉ còn rule `microsched-db-connection-string` che — mà rule đó bắt buộc password chứa **chữ số** đúng vị trí (`[A-Za-z0-9_\-]{4,}[0-9][A-Za-z0-9_\-]{2,}@`).

⇒ Password không có chữ số → **cả hai rule trượt**, `useDefault` cũng không có rule postgres URI. Chuỗi owner lọt vào commit trên repo public, hook báo xanh.

**Tính bất đối xứng là điểm chính:** credential *ít quyền nhất* (`DATABASE_URL`, CRUD-only) được hai rule che; credential *nhiều quyền nhất* được một rule kèm điều kiện bypass được.

### Phải làm

1. Thêm vào nhóm tên biến của rule 2: `NEON_OWNER_URL`, `NEON_MIGRATOR_URL`, `ENCRYPTION_MASTER_KEY`, `CRON_TOKEN`, `OAUTH_STATE_SECRET`. Cập nhật `keywords` tương ứng.
2. **Giữ nguyên điều kiện "trông thật"** — nó là đánh đổi có chủ đích để `.env.example` (dùng literal `password`/`host`) không báo nhầm. Nếu placeholder mới bị bắt, dùng `gitleaks:allow` **tại đúng dòng đó**, không allowlist rộng tay (tiền lệ `agent-tasks/002`).
3. **Test hai chiều bằng binary gitleaks thật**, đúng cách 002 đã làm — đây là hàng rào bảo mật, không được tin suông:
   - chuỗi giả **có** chữ số → bị chặn (exit 1)
   - chuỗi giả **không có** chữ số, gán cho `NEON_OWNER_URL=` → bị chặn (đây là lỗ đang vá)
   - `.env.example` hiện tại + `postgresql+asyncpg://` trơn → **không** báo nhầm
4. Chạy `pre-commit run --all-files` sạch toàn repo.
5. Ghi kết quả kiểm chứng vào `docs/devops-brief.md` §3 (nối tiếp mục "Lỗ đã bịt 2026-07-19").

---

## Mục 3 — `compare_digest` ném `TypeError` với header non-ASCII

[`backend/app/web/deps.py:71`](../backend/app/web/deps.py):

```python
scheme, _, presented = (authorization or "").partition(" ")
if scheme.lower() != "bearer" or not secrets.compare_digest(presented, expected):
    raise _unauthenticated()
```

`secrets.compare_digest` với đối số `str` yêu cầu **ASCII-only**. `Authorization: Bearer é` → `TypeError` chưa bắt → **500** thay vì 401.

**Không phá ranh giới xác thực** (không rò gì về `expected`, không bypass) — nhưng biến một đường từ chối sạch thành exception trong log production, và endpoint này là bề mặt duy nhất gọi được từ ngoài mà không cần session.

### Phải làm

1. So sánh trên bytes: `secrets.compare_digest(presented.encode(), expected.encode())`.
2. Thêm test: `Authorization: Bearer é` → **401**, không phải 500. Chứng minh test biết đỏ (hoàn nguyên fix → test fail).

---

## KHÔNG được làm

- **Không mở lại Mục 1.** Chủ đã quyết 2026-07-23 (A + app-layer), lý do ở `tracking-brief.md` §6. Thấy có vẻ nên làm khác → **dừng, ghi nhận, đẩy lên T1** (`AGENTS.md`), đừng tự đổi.
- **Không cài đặt phần `*_item` ở task này.** Nó thuộc seam crypto của 008. Ở đây chỉ đụng `note`.
- **Không sửa `0001_initial_schema.py`** — migration đã chạy trên production, sửa tại chỗ là làm lệch giữa DB thật và lịch sử migration.
- **Không nới điều kiện "trông thật" của gitleaks** để cho dễ bắt hơn — sẽ báo nhầm `.env.example` và dạy người ta bỏ qua hook, đúng thứ `devops-brief.md` §3 đã tránh.
- **Không gộp ba mục vào một PR.** Mục 1 đụng schema + migration, mục 2 đụng hàng rào secret, mục 3 đụng auth — ba blast radius khác nhau. Tách ít nhất: `feat/008d-schema-private-invariant` và `feat/008d-security-polish` (gộp mục 2+3 được).
- **Không đụng `docs/` ngoài hai chỗ được nêu** (tracking-brief §6, devops-brief §3).

## Acceptance (kiểm chứng được)

**Mục 1:**
- [ ] `uv run alembic upgrade head` rồi `uv run python -m scripts.check_migration_drift` → diff rỗng
- [ ] round-trip `downgrade base` / `upgrade head` xanh (job `Migration QA` sẵn có)
- [ ] test vi phạm constraint **fail đúng ở tầng DB**, và đã chứng minh biết đỏ — dán output cả hai chiều
- [ ] `tracking-brief.md` §6 có dòng quyết định kèm ngày

**Mục 2:**
- [ ] dán output gitleaks cho **cả ba** trường hợp test ở trên (chặn / chặn / không báo nhầm)
- [ ] `pre-commit run --all-files` sạch
- [ ] `devops-brief.md` §3 có ghi kết quả

**Mục 3:**
- [ ] `pytest` xanh, có test mới cho header non-ASCII
- [ ] dán output chứng minh test biết đỏ

**Chung:** báo cáo tách rõ **đã CHẠY** vs **chỉ SUY LUẬN** (quy ước `agent-tasks/README.md` §"Quy ước BÁO CÁO"). CI xanh mới được báo xong (`gh pr checks <PR> --watch`).

## Việc của CHỦ trước khi chạy task

- [x] **Quyết Mục 1** — xong 2026-07-23 (A + app-layer, `tracking-brief.md` §6). **Không còn gì chặn task này.**
- [ ] Không cần Docker/DB local cho Mục 2+3. **Mục 1 cần Postgres** để chạy Migration QA local — hoặc để CI chạy (job `Migration QA` đã có container `pgvector/pgvector:pg18`).
