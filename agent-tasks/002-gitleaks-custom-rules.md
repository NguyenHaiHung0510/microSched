# 002 — gitleaks: rule riêng cho connection string DB

> **Trạng thái:** ✅ DONE (2026-07-19) — đã kiểm chứng thật
> **Model tier đề xuất:** Sonnet (tầng giữa) · **Effort:** low-medium
> *Lý do: phạm vi hẹp (một file config + test), nhưng cần viết regex đúng và test cả hai chiều (bắt được thật / không báo nhầm).*

## Bối cảnh

Đọc `CLAUDE.md` + `docs/devops-brief.md` §3 trước.

Task `001` đã dựng pre-commit + gitleaks và **hoạt động thật** — đã kiểm chứng 2026-07-19: gitleaks chặn được GitHub PAT (`github-pat`) và Stripe key (`stripe-access-token`).

**Nhưng kiểm chứng cũng phát hiện một lỗ:** chuỗi kết nối Postgres dạng
`postgresql://user:password@host:5432/dbname` **KHÔNG bị bắt** bởi rule mặc định.

**Vì sao đây là lỗ nghiêm trọng với riêng dự án này:** kiến trúc đã chốt dùng **Neon Postgres** làm store duy nhất, và credential nằm trong `.env` (`CLAUDE.md` mục "Hard boundaries"). Connection string Neon **chính là secret số một** của microSched — mà hàng rào hiện tại lại không nhận ra nó. `.env` đã được `.gitignore` chặn, nên đường rò chính đã bịt; lỗ còn lại là khi chuỗi kết nối bị **dán nhầm vào file code/doc/script** (rất dễ xảy ra lúc debug, hoặc khi dán log lỗi có chứa URL).

Repo là **public** → rò là công khai tức thì.

## Mục tiêu

Thêm rule riêng cho gitleaks để bắt connection string có nhúng mật khẩu.

## Phải làm

1. Tạo `.gitleaks.toml` ở gốc repo:
   - `[extend] useDefault = true` — **giữ nguyên toàn bộ rule mặc định**, chỉ bổ sung.
   - Thêm rule bắt URI có credential cho ít nhất: `postgresql://` / `postgres://`, `mysql://`, `mongodb+srv://`, `redis://` — dạng `scheme://user:password@host`.
   - Cân nhắc thêm rule cho biến môi trường hay bị dán thẳng: `DATABASE_URL=`, `PGPASSWORD=` kèm giá trị non-placeholder.
2. Trỏ hook trong `.pre-commit-config.yaml` dùng file config này (kiểm tra tài liệu gitleaks phiên bản đang pin để biết cách truyền `--config`; **đừng đoán cờ dòng lệnh**).
3. **Test hai chiều** (bắt buộc — regex sai một chiều là vô dụng, sai chiều kia là phiền phát điên):
   - **Phải bắt:** `postgresql://appuser:SomeRealLookingPass123@ep-xyz.ap-southeast-1.aws.neon.tech:5432/microsched` <!-- gitleaks:allow — chuỗi ví dụ bịa trong spec, không phải secret thật; rule mới cố tình bắt được chuỗi này khi test, allow tại đây để không tự chặn chính spec -->
   - **KHÔNG được báo nhầm** (false positive) với các chuỗi vô hại đang có/sắp có trong repo: `postgresql+asyncpg://` trong doc kiến trúc (`schema-physical-brief.md` §2 có nhắc driver), placeholder kiểu `postgresql://user:password@host/db`, `postgres://localhost/dbname` (không có mật khẩu).
   - Chạy `pre-commit run --all-files` → **toàn repo hiện tại phải sạch**, không có cảnh báo giả trên các file `.md` đã commit.
4. Xóa sạch mọi file tạm dùng để test.
5. Cập nhật `docs/devops-brief.md` §3: ghi rằng lỗ connection-string đã bịt, kèm ngày.
6. Cập nhật `agent-tasks/README.md`: đổi trạng thái 002.

## KHÔNG được làm

- **Không** tắt/ghi đè rule mặc định (`useDefault = true` phải giữ).
- **Không** thêm `allowlist` rộng tay để cho qua cảnh báo giả — sửa regex cho đúng, đừng bịt miệng công cụ. Nếu buộc phải allowlist, giới hạn đúng file/dòng cụ thể kèm comment giải thích.
- **Không** commit connection string thật (kể cả của local Postgres `microschedule_v2`) vào bất kỳ file test nào — dùng giá trị bịa.
- **Không** đụng ruleset/secret scanning phía GitHub.
- **Không** rewrite git history.

## Acceptance

- [ ] `.gitleaks.toml` tồn tại, `useDefault = true`.
- [ ] Chuỗi Neon giả (có mật khẩu) → **bị chặn**, exit code khác 0.
- [ ] Placeholder + `postgresql+asyncpg://` trong doc → **không** bị báo.
- [ ] `pre-commit run --all-files` pass sạch toàn repo.
- [ ] Không còn file tạm nào trong working tree.
- [ ] `devops-brief.md` §3 đã ghi nhận, có ngày.

## Bàn giao

Commit lên `develop` (main có ruleset bắt buộc PR). Message tiếng Việt, mô tả *tại sao*, kèm `Co-Authored-By:`.
