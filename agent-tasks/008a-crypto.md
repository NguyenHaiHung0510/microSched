# 008a — `app/core/crypto.py`: AES-GCM seam cho cột 🔐

> Executor: **Agent Claude/Opus (T1)** — security-critical, `CLAUDE.md` §7 giao T1 viết code loại này · Bậc: — · Effort: **high** · **Skill gợi ý:** không · **MCP cần:** không (test thuần Python, không cần trình duyệt/DB)

**Trạng thái:** 📋 SẴN SÀNG GIAO
**Branch:** `feat/008a-crypto` → PR nhỏ vào `develop`
**Blast radius / triage:** L1 — mọi CRUD private sau này gọi đúng seam này; diff do Claude-điều-phối + chủ soi.

---

## 0. Đây KHÔNG phải phiên thiết kế

Cơ chế, format, vị trí khóa **đã chốt** — executor **chép ra code**, không tự quyết lại:
- Cơ chế: app-level **AES-GCM** qua thư viện `cryptography` (KHÔNG `pgcrypto` — khóa không bao giờ đi qua SQL tới Neon). Nguồn: `docs/schema-physical-brief.md` §7.1.
- Format ciphertext: prefix version **`enc:v1:`** (K18). Đây là **hằng số cứng** — migration `0001` đã ràng `CHECK (... LIKE 'enc:v1:%')` trên `message.content`, `note.body_md`, `note.title`, `task.title`, `task.body_md`, `tracker.name`, `subscription.name`/`amount`, `entry.note`… (xem `backend/alembic/versions/0001_initial_schema.py`). Sai prefix ⇒ **mọi INSERT private bị DB từ chối**.
- Khóa: đọc từ env **`ENCRYPTION_MASTER_KEY`** = `base64.urlsafe_b64encode(os.urandom(32))` (32 byte raw ⇒ AES-256). Đã sinh + cất 3 nơi (`.env.example` dòng 114–129, `db-and-data-model-brief.md` §6).

Task này **chỉ dựng seam** (hàm mã hoá/giải mã + test). **KHÔNG** đụng model/router/CRUD — đó là việc của 008.

## 1. Việc của CHỦ trước khi chạy

- [x] `ENCRYPTION_MASTER_KEY` đã có trong `backend/.env` local và Fly secrets — **không cần làm gì**.
- ⚠️ **Nếu chạy trong git worktree:** worktree KHÔNG mang theo `.env` (file untracked). **Không sao** — test tự sinh khóa tạm (mục 3), không phụ thuộc `.env`. Đây là ràng buộc thiết kế, không phải lỗi môi trường.

## 2. Phải làm

### 2.1 Thêm dependency
- Thêm **`cryptography`** vào `[project] dependencies` của `backend/pyproject.toml` (đang thiếu — hiện chỉ có mặt gián tiếp qua `authlib`). Dùng `uv add cryptography` để cập nhật cả `pyproject.toml` lẫn lockfile; commit lockfile.
- ⚠️ CI có check bắt buộc **`Production dependency check`** — `cryptography` là **prod dependency thật** (chạy runtime, không phải test tooling), nên đặt ở `[project] dependencies`, KHÔNG ở `[dependency-groups] dev`.

### 2.2 `backend/app/core/settings.py`
- Thêm đúng **một** field vào class `Settings`: `encryption_master_key: str | None = None` (đặt cạnh `cron_token`, cùng phong cách các field env khác).
- KHÔNG thêm validator, KHÔNG thêm property. Việc kiểm/giải mã khóa nằm ở `crypto.py`.

### 2.3 `backend/app/core/crypto.py` (file mới)
Phong cách bám sát `app/core/sessions.py`: docstring module giải thích *tại sao*, hàm nhỏ, comment nói *lý do* chứ không thuật lại code.

**API công khai (đúng 3 hàm + 1 hằng — không hơn):**
```
CIPHERTEXT_PREFIX = "enc:v1:"

def encrypt(plaintext: str) -> str
def decrypt(ciphertext: str) -> str
def is_encrypted(value: str) -> bool
```

**Hợp đồng từng hàm:**
- `encrypt(plaintext)` → `"enc:v1:" + urlsafe_b64encode(nonce ‖ ciphertext_tag)`.
  - nonce = **12 byte** ngẫu nhiên mỗi lần gọi (`os.urandom(12)`) — chuẩn GCM.
  - `ciphertext_tag = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)`.
  - Không xác định (non-deterministic): cùng plaintext ra ciphertext khác nhau mỗi lần → **đúng và bắt buộc** cho GCM (đây cũng là lý do K19 bỏ unique index trên tên, để dành `name_hmac`). Test KHÔNG được assert output cố định.
- `decrypt(ciphertext)` → plaintext `str`.
  - Nếu **không** bắt đầu bằng `CIPHERTEXT_PREFIX` → **raise `ValueError`** (không bao giờ lặng lẽ trả plaintext về — dữ liệu hỏng/nhầm phải kêu to).
  - Tách prefix → `urlsafe_b64decode` → 12 byte đầu = nonce, phần còn lại = ciphertext_tag → `AESGCM(key).decrypt(...)` → `.decode("utf-8")`.
  - Khóa sai / ciphertext bị sửa → `cryptography.exceptions.InvalidTag` **để nó nổ ra** (đừng nuốt — chống giả mạo).
- `is_encrypted(value)` → `value.startswith(CIPHERTEXT_PREFIX)`. Dùng để caller quyết định có cần giải mã không.

**Nạp khóa — LAZY, không nạp lúc import:**
- Đọc `settings.encryption_master_key`; `urlsafe_b64decode`; **kiểm đúng 32 byte** (nếu không → `RuntimeError` với thông báo rõ "ENCRYPTION_MASTER_KEY missing/invalid (need 32-byte urlsafe-base64)").
- Cache đối tượng `AESGCM` sau lần dựng đầu (module-level lazy, ví dụ hàm `_cipher()` giữ biến module, hoặc `@lru_cache`).
- **Bắt buộc: `import app.core.crypto` phải THÀNH CÔNG khi CHƯA có khóa.** Chỉ khi *gọi* `encrypt`/`decrypt` mới cần khóa. (Lý do: test import module rồi mới set khóa; và app phải import được ở môi trường chưa cấu hình đủ.)

### 2.4 `backend/tests/test_crypto.py` (file mới)
**Test phải tự-chứa — tự sinh khóa tạm, KHÔNG phụ thuộc `.env` thật.** Gợi ý: `monkeypatch.setenv("ENCRYPTION_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())` rồi `get_settings.cache_clear()` (và clear cache khóa của `crypto` nếu có) trong fixture. Cover tối thiểu:
1. **Round-trip:** `decrypt(encrypt(x)) == x` cho: ASCII thường, **tiếng Việt có dấu**, chuỗi rỗng `""`, chuỗi rất dài, chuỗi trông như tiền `"1500000"`.
2. **Format:** `encrypt(x).startswith("enc:v1:")` và toàn ký tự ASCII (khớp `LIKE 'enc:v1:%'` của DB).
3. **Non-determinism:** `encrypt(x) != encrypt(x)` nhưng cả hai `decrypt` về `x`.
4. **`is_encrypted`:** True cho output đã mã hoá, False cho plaintext trơn.
5. **Giả mạo:** đổi 1 byte trong phần b64 → `decrypt` raise `InvalidTag`.
6. **Sai prefix:** `decrypt("khong-phai-ciphertext")` raise `ValueError`.
7. **(khuyến khích)** import `app.core.crypto` khi env chưa có khóa → không raise; chỉ khi gọi `encrypt` mới raise `RuntimeError`.

## 3. KHÔNG được làm
- KHÔNG đụng bất kỳ model/router/service/migration nào. Task này dừng ở seam + test.
- KHÔNG đổi prefix, KHÔNG đổi `enc:v1:` thành gì khác, KHÔNG bịa `enc:v2:`.
- KHÔNG thêm hàm ngoài 3 hàm + hằng đã liệt kê (không `encrypt_optional`, không xử lý `None` — logic cột nullable là việc của 008; giữ primitive tối giản đúng chủ đích).
- KHÔNG nạp khóa lúc import; KHÔNG để test đọc khóa thật từ `.env`.
- KHÔNG dùng `pgcrypto`, KHÔNG dùng chế độ AES khác (CBC/ECB…), KHÔNG tự chế KDF — khóa đã là 32 byte ngẫu nhiên, dùng thẳng.
- KHÔNG in/log plaintext hay khóa ở bất kỳ đâu.

## 4. Acceptance (chạy được, không phải "làm cho tốt")
Chạy trong `backend/`:
```
uv add cryptography
uv run pytest tests/test_crypto.py -v      # tất cả pass
uv run ruff check app/core/crypto.py app/core/settings.py tests/test_crypto.py   # sạch
uv run pytest                               # toàn bộ suite vẫn xanh (không hồi quy)
```
- `grep cryptography pyproject.toml` thấy nó ở `[project] dependencies`.
- PR `feat/008a-crypto` → `develop`; **`gh pr checks` xanh cả 5 required check** (đặc biệt `Production dependency check` + `Backend checks`).

## 5. Báo cáo (quy ước sau 007 — tách ĐÃ CHẠY khỏi SUY LUẬN)
Trong PR description ghi rõ:
> **Đã chạy:** `pytest tests/test_crypto.py` (N pass) · `pytest` toàn suite (M pass) · `ruff` sạch · `gh pr checks` xanh
> **CHƯA chạy:** (nếu có gì chỉ suy luận thì nói thẳng)
> **Biên lai:** số PR + link.

Claude-điều-phối sẽ **không nhận prose làm bằng chứng** — chỉ nhận PR# + `gh pr checks` xanh + diff đọc được.
