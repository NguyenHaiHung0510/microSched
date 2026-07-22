# harness-reports/ — output của các phiên đối soát harness

Thư mục này nhận **báo cáo do agent sinh ra về chính bộ máy làm việc** (Claude ↔ Codex ↔ Jules), không phải về sản phẩm microSched. Spec sinh ra chúng nằm ở `agent-tasks/harness-audit/`.

## Luật git — đọc trước khi thêm gì

```gitignore
harness-reports/*
!harness-reports/README.md
```

**Thư mục và README này có trong git; nội dung báo cáo thì KHÔNG.** Cố ý:

- Repo này **public by deliberate choice** (`docs/devops-brief.md` §1) và threat model của chủ là **social engineering**, không phải người đọc tình cờ.
- Báo cáo ở đây mô tả **thói quen làm việc, sở thích, và bộ nhớ cá nhân** của một người thật — đúng loại vật liệu dùng để dựng pretext. Nó không phải secret (gitleaks sẽ không chặn), nên **cơ chế duy nhất giữ nó lại là dòng `.gitignore` trên**.
- Giữ README trong git để thư mục **hiện diện và tự giải thích** — người mới (hoặc agent mới) nhìn repo là biết chỗ này tồn tại và biết luật, thay vì thấy một thư mục trống bí ẩn hoặc không thấy gì.

Muốn commit một mảnh nào đó ⇒ **không dùng `git add -f`**. Chép đúng phần cần vào `docs/` hoặc `AGENTS.md` sau khi đã đọc lại bằng mắt.

## Vòng đời — đây là chỗ tạm ứng, không phải kho

Báo cáo ở đây **hết vai trò** khi phát hiện của nó đã được nhập vào nơi có thẩm quyền:

| Loại phát hiện | Nhập vào |
|---|---|
| Luật riêng dự án microSched | `AGENTS.md` (gốc repo) |
| Cách làm việc xuyên dự án với chủ | `C:\Users\os\.codex\AGENTS.md` |
| Quyết định + lý do | `docs/*-brief.md` |
| Thứ Claude cần nhớ giữa các phiên | memory của Claude |

Nhập xong thì **dọn**. Mục tiêu là **giảm** số nơi chứa sự thật — cùng nguyên tắc chống split-brain mà `CLAUDE.md` đặt ra cho tầng dữ liệu, chỉ ở tầng chỉ dẫn. Một thư mục báo cáo không ai dọn sẽ tự biến thành kho luật thứ ba, và đó đúng là thứ nó sinh ra để tránh.

## Bố cục

```
harness-reports/
├── README.md                     (trong git)
├── 01-codex-self-audit/          run-A.md, run-B.md
└── 02-memory-crossaudit/         report.md, proposed-repo-AGENTS.md, proposed-global-AGENTS.md
```
