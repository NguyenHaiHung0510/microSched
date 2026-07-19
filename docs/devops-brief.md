# DevOps / repo & CI — microSched

> **Trạng thái:** ✅ CHỐT phần nền (2026-07-19). Phần auto-review PR = ⏸ DEFER tới khi có code.
> **Tra cứu giá/chính sách: 2026-07-19** — mục §4 phụ thuộc chính sách vendor, **soi lại ~3 tháng** (giống `cost-brief.md`; không để pricing drift làm hỏng quyết định).
> Decision record tự-chứa. Nguyên tắc: **DevOps bắt đầu nhẹ từ sớm**, dựng hàng rào *trước* khi có thứ để rò rỉ.

---

## 1. Repo — ✅ CHỐT PUBLIC (2026-07-19)

`github.com/NguyenHaiHung0510/microSched` — **public, cố ý giữ public.**

**Threat model của chính chủ (quan trọng — chi phối mọi quyết định bảo mật sau này):**
- **KHÔNG ngại:** người vào đọc code (*"biết đâu lại là nhà tuyển dụng"* — repo còn là portfolio cho mục tiêu AI-eng), hay AI crawl nội dung (không có động cơ khai thác).
- **NGẠI:** **social engineering** — đây mới là lý do thật đằng sau private mode (`tracking-brief.md` §5) và noti nhắc thuốc kín đáo (§12). Nói cách khác: rủi ro không nằm ở *ai đọc được repo*, mà ở *thông tin cá nhân bị dùng để dựng pretext*.
- **Đánh đổi đã biết khi giữ public:** secret scanning + push protection **free** (private repo cần GitHub Advanced Security trả phí) + giữ được giá trị portfolio. Đổi lại: `docs/tracking-brief.md` §12 có ví dụ noti nêu tên một loại thuốc thật → chính chủ đã cân nhắc và **chấp nhận**; nếu đổi ý, sửa ví dụ thành trung tính (git history vẫn còn, muốn sạch hẳn phải rewrite).

## 2. Git workflow — ✅ CHỐT

- **Nhánh:** làm việc trên `develop` → PR vào `main`. `main` = trạng thái đã duyệt.
- **Ruleset `protect-main`** (đã bật trên GitHub): chặn xóa nhánh, chặn force-push, **bắt buộc PR** để vào `main`.
  - **`required_approving_review_count: 0` là CỐ Ý** — dự án một người; đòi 1 approval sẽ tự khóa chính mình (không ai tự duyệt PR của mình được). Rule vẫn có giá trị: ép mọi thay đổi đi qua PR (có chỗ để đọc lại diff) + chặn tai nạn force-push.
- **Quy ước commit:** **1 commit = 1 phiên quyết định** → history đọc được như nhật ký thiết kế. Message tiếng Việt, mô tả *tại sao* chứ không chỉ *cái gì*, kèm `Co-Authored-By:`.
- PR đầu tiên: [#1](https://github.com/NguyenHaiHung0510/microSched/pull/1) — gộp 3 phiên thiết kế (kiến trúc, schema vật lý, tracking).

## 3. Hàng rào secret — ✅ 2 lớp

| Lớp | Ở đâu | Chặn lúc nào | Trạng thái |
|---|---|---|---|
| GitHub **secret scanning** + **push protection** | server | lúc `git push` | ✅ đã bật (free vì repo public) |
| **pre-commit + gitleaks** | máy local | lúc `git commit` — sớm hơn | ⏳ spec `agent-tasks/001` |

Lý do cần cả hai: push protection chỉ cứu ở phút chót và chỉ với pattern provider biết; hook local chặn sớm hơn và bắt được cả secret tự chế. **`.env` đã nằm trong `.gitignore` từ commit đầu** (ràng buộc cứng ở `CLAUDE.md`).

**Kiểm chứng thật 2026-07-19** (không tin suông vào việc "đã cài xong"):
- ✅ gitleaks **chặn được**: GitHub PAT (`github-pat`), Stripe key (`stripe-access-token`) → exit 1.
- ⚠️ **LỖ ĐÃ PHÁT HIỆN:** chuỗi `postgresql://user:pass@host:5432/db` **KHÔNG bị bắt** bởi rule mặc định — trong khi **connection string Neon chính là secret số một của dự án này**. `.env` đã bị `.gitignore` chặn nên đường rò chính đã bịt; rủi ro còn lại là dán nhầm chuỗi vào file code/doc/log. → **`agent-tasks/002`** bịt lỗ này bằng rule riêng.
- 📝 Bài học quy trình: chuỗi key *mẫu* trong tài liệu AWS **không** kích hoạt gitleaks (có allowlist cho giá trị ví dụ nổi tiếng) → test hàng rào bảo mật phải dùng pattern **giống thật**, nếu không sẽ tưởng nhầm là công cụ hỏng, hoặc tệ hơn: tưởng nhầm là công cụ chạy tốt.

## 4. Auto-review PR — ⏸ DEFER (tra 2026-07-19)

**Chưa cắm bây giờ, có lý do:** repo hiện **chưa có code** — auto-review chỉ đọc được văn bản tiếng Việt, giá trị thấp. **Cắm sau khi scaffold app.**

| Lựa chọn | Thực tế 2026-07-19 |
|---|---|
| **Claude Code GitHub Action** | ✅ **ưu tiên 1** — chính chủ đã trả tiền Claude Code, không tốn thêm subscription. Cài bằng `/install-github-app` |
| **Jules** (Google) | ✅ phương án free song song — 15 task/ngày, có action chính thức `google-labs-code/jules-action` |
| **Copilot Free** | ❌ **không** review PR trên github.com (chỉ review vùng chọn trong IDE) — dễ hiểu nhầm |
| **Copilot Pro $10/th** | ❌ không mua — 2 phương án trên đã phủ |
| **GitHub Student Pack** | ⚠️ GitHub **tạm dừng đăng ký mới** Copilot student từ 4/2026; verify *trước* mốc đó thì còn. **Chính chủ nên tự kiểm tra tài khoản** |

## 5. Giao việc cho agent — ✅ quy ước mới

`agent-tasks/NNN-<slug>.md` = spec tự-chứa giao cho agent chạy độc lập. Mỗi spec bắt buộc có: bối cảnh đủ để đọc ở session 0-context · việc phải làm · **việc KHÔNG được làm** · acceptance kiểm chứng được · **model tier + effort đề xuất** (để không đốt token thừa). Chi tiết: `agent-tasks/README.md`.

## 6. Chưa làm (không phải quên)
- **CI workflow** (GitHub Actions) — đợi có code. Khi làm, ghép luôn **hàng rào QA cho Alembic** đã chốt ở `schema-physical-brief.md` §2 (round-trip test, drift-check, chặn drop ngầm) + thử migration trên bản restore (`db-and-data-model-brief.md`).
- **Dependabot** — đợi có package manifest.
- **Deploy pipeline** (`fly deploy` qua GitHub Actions) — đã ghi hướng ở `architecture-brief.md`.

---
*Cập nhật khi: bật auto-review, dựng CI, hoặc đổi repo visibility. Soi lại §4 sau ~3 tháng (chính sách vendor đổi nhanh). Thêm note có ngày — không xóa kết luận cũ.*
