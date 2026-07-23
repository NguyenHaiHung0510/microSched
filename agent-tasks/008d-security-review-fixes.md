# 008d — Ba mục tồn từ security review toàn dự án (2026-07-23)

> **Trạng thái:** 📋 SPEC (chưa chạy) — viết 2026-07-23
> Executor: **T2 Codex** · Bậc: **Terra** (mục 2+3) / **Sol** (mục 1, sau khi chủ đã quyết) · Effort: thấp
> **Skill gợi ý:** không cần · **MCP cần:** không cần (không có phần nào phải nhìn bằng mắt trên trình duyệt)

## Bối cảnh (đọc được ở session 0-context)

Ngày 2026-07-23 chạy security review **toàn bộ `develop`** thay vì chỉ diff nhánh — lý do: lệnh review mặc định lấy scope `git diff main...develop`, mà từ 2026-07-22 `main` không còn nghĩa "phần đã soi" (nó là nhãn release đang tụt, `devops-brief.md` §2.1). Scope đó soi 11/47 file code và **bỏ sót đúng tầng bảo mật lõi**.

Đọc lại toàn bộ `backend/app/**` (~1.311 dòng) + scripts + migration + workflow + frontend. Kết quả: **không có lỗ hổng cho phép chiếm quyền hay rò dữ liệu người dùng.** Session/OAuth/phân quyền route/phân quyền DB/tham số hoá SQL đều sạch. Ba mục dưới đây là phần còn lại — hai mục là khe hở phòng thủ, một mục là **quyết định thiết kế chưa từng được quyết**.

Mục ⓐ `/api/readyz` chạy SQL không cần auth **đã được chủ xử lý 2026-07-23**, không nằm trong spec này.

---

## Mục 1 — Bất biến `private ⇒ ciphertext` áp không đồng đều

### ⚠️ ĐÂY LÀ QUYẾT ĐỊNH, KHÔNG PHẢI LỖI — CHỦ/T1 QUYẾT TRƯỚC, EXECUTOR KHÔNG TỰ CHỌN

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

**Không bên nào "quên".** `tracking-brief.md` §6 chốt nguyên văn *"private note/task **bodies**"* ⇒ **`Note` đúng spec, `Task` chặt hơn spec.** Câu hỏi *"tiêu đề note private có phải secret không"* chưa bao giờ được quyết một lần — nó bị quyết ngầm hai lần theo hai hướng, ở hai chỗ không tham chiếu nhau. Cùng họ sự cố Neon 22/07.

**Vì sao đáng quyết bây giờ, không để sau:**
- **008 là task đặt khuôn**, 009–012 chép lại. Sai khuôn ở đây là sai 5 lần.
- Sửa CHECK constraint sau khi đã có dữ liệu private thật = migration có backfill (phải giải mã/mã hoá lại). Sửa bây giờ khi bảng còn rỗng = một migration thuần DDL.
- `note.embedding` nằm **cùng bảng** ([`models.py:166`](../backend/app/domain/models.py)). Ruleset R1–R7 cấm cột mã hoá vào pgvector; nếu `title` là plaintext thì **không có gì chặn** nó bị embed — tức câu trả lời cho mục này quyết luôn một nhánh của phiên AI Bước 1.

**Có một tiền lệ mạnh trong chính repo** — `tracking-brief.md:76`:

> *"tên tracker `'Hút thuốc'` rò gần hết thông tin dù mọi entry mã hóa. Mã hóa entry mà để tên tracker trần = bảo mật hình thức."*

Lập luận đó áp cho `tracker.name` (⇒ mã hoá **vô điều kiện**). Tiêu đề note private là cùng hình dạng: tiêu đề thường mang gần hết thông tin của note.

### Hai lựa chọn (chủ chọn một, ghi lý do vào `tracking-brief.md` §6)

| | A — siết `Note` cho bằng `Task` | B — nới `Task` cho bằng spec |
|---|---|---|
| Làm gì | thêm `title` vào CHECK của `note` | bỏ `title` khỏi CHECK của `task` |
| Được | bất biến đồng nhất; khớp tiền lệ `tracker.name` | khớp đúng chữ đã chốt ở §6 |
| Mất | tiêu đề note private không sort/tìm được ở DB (phải giải mã app-side) | tiêu đề task private nằm plaintext trong Neon |
| Ghi chú | **nghiêng phương án này** — nhất quán với lập luận §76 | chỉ chọn nếu chủ xác nhận tiêu đề không nhạy |

### Mục con: bảng `*_item`

`note_item.content` ([`models.py:193`](../backend/app/domain/models.py)) và `task_item` **không có cờ `is_private`, cũng không có ràng buộc nào** — tức hiện tại **không có cách nào diễn đạt** "item này thuộc một cha private". Checklist con của một note private đang nằm plaintext không ràng buộc.

Đây là câu hỏi thứ hai, quyết cùng lúc: (i) bỏ qua có chủ đích (ghi lý do), (ii) thêm CHECK tham chiếu cha qua trigger/hàm, hay (iii) mã hoá `content` vô điều kiện như `message.content` đang làm ([`models.py:440`](../backend/app/domain/models.py)).

### Phải làm (sau khi chủ đã chọn)

1. Sửa `CheckConstraint` tương ứng trong `backend/app/domain/models.py`.
2. Sinh migration Alembic mới (**không sửa `0001_initial_schema.py`** — nó đã chạy trên production).
3. Thêm test ở `backend/tests/test_schema_models.py`: insert vi phạm phải **bị DB từ chối**. Test phải được **chứng minh là biết đỏ** (bỏ constraint → test fail), theo `learnings-applied.md`.
4. Ghi quyết định + lý do vào `docs/tracking-brief.md` §6 kèm ngày.

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

- **Không tự chọn phương án cho Mục 1.** Đây là quyết định thiết kế thuộc chủ/T1 (`AGENTS.md`: thấy 2 brief mâu thuẫn → dừng, báo, không tự phát minh kiến trúc). Nếu spec tới tay mà chủ chưa ghi lựa chọn → **làm Mục 2+3, dừng ở Mục 1 và báo**.
- **Không sửa `0001_initial_schema.py`** — migration đã chạy trên production, sửa tại chỗ là làm lệch giữa DB thật và lịch sử migration.
- **Không nới điều kiện "trông thật" của gitleaks** để cho dễ bắt hơn — sẽ báo nhầm `.env.example` và dạy người ta bỏ qua hook, đúng thứ `devops-brief.md` §3 đã tránh.
- **Không gộp ba mục vào một PR.** Mục 1 đụng schema + migration, mục 2 đụng hàng rào secret, mục 3 đụng auth — ba blast radius khác nhau. Tách ít nhất: `feat/008d-schema-private-invariant` và `feat/008d-security-polish` (gộp mục 2+3 được).
- **Không đụng `docs/` ngoài hai chỗ được nêu** (tracking-brief §6, devops-brief §3).

## Acceptance (kiểm chứng được)

**Mục 1** (nếu chủ đã quyết):
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

- [ ] **Quyết Mục 1**: phương án A hay B, và hướng xử lý `*_item` — ghi thẳng vào spec này hoặc vào `tracking-brief.md` §6. Không quyết thì executor chỉ làm được Mục 2+3.
- [ ] Không cần Docker/DB local cho Mục 2+3. **Mục 1 cần Postgres** để chạy Migration QA local — hoặc để CI chạy (job `Migration QA` đã có container `pgvector/pgvector:pg18`).
