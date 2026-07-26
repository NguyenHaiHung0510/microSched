# 015 — secret-scan nhìn được LỊCH SỬ, không chỉ cây làm việc

> Executor: T2 Codex (`gpt-5.6-sol`, `--write`) · Bậc: L2 · Effort: small · **Skill gợi ý:** không cần · **MCP cần:** không cần

**Trạng thái:** ⚠️ OPEN — chủ đã đồng ý tách task riêng (2026-07-26), chưa duyệt nội dung.

---

## Bối cảnh — đọc trước, đừng làm lại từ đầu

Task 013 (đã live, prod `7cceb1a`) dựng job `secret-scan` trong `.github/workflows/ci.yml`:

```
./gitleaks dir . --config .gitleaks.toml --redact -v --exit-code 1
```

`gitleaks dir` quét **cây làm việc sau checkout**. Nó **không nhìn lịch sử git**.

Phản biện T3 sau khi 013 xong bắt đúng chỗ này, và **đã kiểm chứng sống ngay trên repo này**: lúc chạy nghi thức nghiệm thu 013, `gitleaks git` quét ra 4 finding trong lịch sử nhánh trong khi `gitleaks dir` báo xanh — **cùng một repo, cùng một lúc, hai câu trả lời ngược nhau**.

### Kịch bản hỏng, cụ thể

1. Ai đó commit một dòng `NEON_OWNER_URL=postgresql://user:<PW>@ep-x.neon.tech/db` (với `<PW>` là mật khẩu thật) ở commit **A** trên nhánh `feat/...`.

   *(Spec cố ý không viết chuỗi hoàn chỉnh — hook gitleaks sẽ chặn chính commit của spec này. Bài học đã ghi ở `013-devsecops.md`: đừng đặt fixture hoàn chỉnh vào tài liệu được commit.)*
2. Nhận ra sai, xoá dòng đó ở commit **B**, push cả hai.
3. CI checkout commit B ⇒ `gitleaks dir` thấy cây sạch ⇒ **XANH**.
4. Merge. Secret nằm trong lịch sử `develop` của một repo **public**, vĩnh viễn.

Hook `pre-commit` chặn được ở bước 1 — **nhưng chỉ khi** máy đó đã chạy `pre-commit install` và người dùng không `--no-verify`. Chính lỗ đó là lý do 013 tồn tại; 013 mới bịt một nửa.

## Việc phải làm

Thêm **một step nữa** vào job `secret-scan` đang có. **Không** bỏ step `dir` hiện tại — hai step trả lời hai câu hỏi khác nhau (cây hiện tại có secret không / lịch sử có secret không).

### Ràng buộc kỹ thuật, mỗi cái là một cách hỏng im lặng

1. 🔒 **`actions/checkout@v4` mặc định `fetch-depth: 1`.** Quét lịch sử trên một shallow clone chỉ soi đúng 1 commit rồi báo xanh — **hỏng im lặng, đúng họ lỗi mà 013 vừa đi vá**. Phải đặt `fetch-depth: 0` **trên checkout của riêng job `secret-scan`** (không ảnh hưởng job khác — mỗi job một runner riêng).

2. 🔒 **Phạm vi quét phải tính bằng SHA từ event payload, KHÔNG dùng tên nhánh.** Đây là chỗ dễ hỏng nhất, và hỏng theo hai kiểu khác nhau:
   - Trên **push**, `github.base_ref` **rỗng** ⇒ `origin/${{ github.base_ref }}..HEAD` nở thành `origin/..HEAD` ⇒ `fatal: bad revision`, **đỏ mọi lần push vào `develop`**. Không phải hỏng im lặng, nhưng là hỏng ngay lập tức.
   - Trên **pull_request**, checkout lấy **commit merge tổng hợp** (`refs/pull/N/merge`), không phải head của PR ⇒ dải theo tên nhánh kéo thêm cả commit merge đó vào. Với PR từ fork thì việc phân giải tên ref còn mong manh hơn.

   ⇒ Dùng SHA tường minh, xác định trong một step riêng:
   ```yaml
   - name: Xác định dải commit cần quét
     id: range
     run: |
       if [ "${{ github.event_name }}" = "pull_request" ]; then
         echo "opts=${{ github.event.pull_request.base.sha }}..${{ github.event.pull_request.head.sha }}" >> "$GITHUB_OUTPUT"
       elif [ "${{ github.event.before }}" = "0000000000000000000000000000000000000000" ]; then
         echo "opts=HEAD~1..HEAD" >> "$GITHUB_OUTPUT"
       else
         echo "opts=${{ github.event.before }}..${{ github.event.after }}" >> "$GITHUB_OUTPUT"
       fi
   ```
   Nhánh `0000…` là lần push đầu tiên của một ref (không có "before"). **Không** để rơi vào quét toàn bộ lịch sử: một secret lịch sử (nếu có) sẽ thành CI đỏ vĩnh viễn mà `git revert` không gỡ được.

3. 🔒 **Thứ tự step là bắt buộc, không phải sở thích: `dir` TRƯỚC, lịch sử SAU.** GitHub Actions dừng job ở step đỏ đầu tiên. Nếu để step lịch sử chạy trước, nó đỏ và step `dir` **bị SKIP** ⇒ bảng CI ra ĐỎ + SKIPPED, **không bao giờ tạo được cặp lệch** vốn là toàn bộ bằng chứng của task này. Thêm `if: always()` cho step lịch sử để nó vẫn chạy kể cả khi `dir` đỏ.

4. **Vẫn phải `--config .gitleaks.toml`** — thiếu là mất 2 rule riêng của 008d.
5. **Vẫn phải `-v`** — 013 đã học: đỏ mà không in RuleID/file/dòng thì người đọc bảng CI không hành động được.
6. Dùng `gitleaks git`, **không** `gitleaks detect` (deprecated từ v8.19.0).

⚠️ **Đừng đụng** 5 job cũ, `deploy.yml`, hay `.gitleaks.toml` (rule là task riêng — xem §Liên quan).

## Acceptance — phải có một lần ĐỎ có chủ ý

Nguyên tắc của 013 giữ nguyên: **một job bảo mật chưa bao giờ đỏ là job chưa được chứng minh đang chạy.** Và lần này phải đỏ **đúng vì lịch sử**, chứ không phải vì cây làm việc — nếu không thì chỉ đang thử lại step cũ.

Trên nhánh `feat/015-...`:

1. Commit **A**: thêm file chứa connection string giả.
2. Commit **B**: **xoá** file đó.
3. Push cả hai cùng lúc, mở PR.
4. **Kết quả phải thấy:** step `dir` **XANH** (cây đã sạch ở B) trong khi step quét lịch sử **ĐỎ** (secret nằm ở commit A). *Chính cặp lệch này là bằng chứng, không phải chỉ "job đỏ".* Nếu thấy ĐỎ + SKIPPED thay vì XANH + ĐỎ thì thứ tự step đang sai — xem ràng buộc 3.
5. Dán output đỏ có RuleID + commit SHA vào PR.
6. Commit **C**: đưa dải quét về sạch (ví dụ: `git revert` commit A, hoặc đơn giản là để commit B đã xoá file rồi mở một PR mới trên nền sạch). Xác nhận CI **XANH**.
7. **Merge bằng squash** — squash gộp thành một commit mang **cây cuối**, nên fixture không vào lịch sử `develop`. Đây cũng là cách 013 đã làm và đã verify (`gitleaks git` trên `develop` sau merge: 104 commit, `no leaks found`).

> 📝 **Bản v1 của spec này bắt force-push xoá hai commit fixture ở bước 6 RỒI vẫn squash ở bước 7 — thừa và tự mâu thuẫn** (phản biện T3 bắt): nếu bước 6 đã xoá sạch commit khỏi nhánh thì lý do "squash để fixture không vào develop" ở bước 7 không còn nghĩa. Nay chỉ giữ **một** cơ chế: squash. Cùng bài học với 013 — đừng chồng hai lớp bảo vệ rồi tưởng cả hai đang làm việc.

⚠️ **Fixture phải là connection string giả, KHÔNG dùng `AKIA…`.** Repo public + push protection đang bật; provider pattern bị chặn lúc push và để lại alert vĩnh viễn. `non_provider_patterns` đang tắt nên chuỗi DB giả đi lọt push protection mà rule riêng vẫn nổ (đo thật 26/07).

## Cố ý KHÔNG làm

- **Bỏ step `dir`** — hai step khác mục đích.
- **Quét toàn bộ lịch sử ở mọi lần chạy** — xem ràng buộc 2.
- **Sửa regex trong `.gitleaks.toml`** — task riêng.
- **Đổi ruleset / required checks** — executor không chạm repo settings. Job xanh rồi thì báo T1.
- **Viết lại lịch sử `develop`** để dọn 4 finding của fixture 013 — chúng **không còn** sau squash merge; đã xác minh 26/07: `gitleaks git` trên `develop` quét 104 commit ⇒ `no leaks found`.

## Liên quan

- Lỗ **không-chữ-số** trong `.gitleaks.toml`: mật khẩu không chứa chữ số lọt **cả hai** rule riêng (đo thật 26/07). Task **riêng** — 015 làm rule chạy **rộng hơn về phạm vi**, task kia làm rule **bắt đúng hơn**. Đừng gộp: gộp vào thì một bản vá regex sai sẽ làm hỏng luôn bằng chứng của 015.
- `docs/devops-brief.md` §3 — vì sao connection string Neon là secret số một của dự án.
- Note 2026-07-26 trong `CLAUDE.md` (phiên 013) — toàn bộ lý do lớp này từng là lớp ma.

## Báo cáo

Tách rõ **đã chạy** và **chỉ suy luận** theo `agent-tasks/README.md` §"Quy ước BÁO CÁO". Executor **không verify được** GitHub Actions/push/`gh` trong sandbox — nói thẳng ra, đừng suy luận rồi khẳng định; T1 sẽ chạy lại.
