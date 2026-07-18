# Schema v1 (mức sơ đồ) — microSched

> **Trạng thái:** A/B/C ✅ **CHỐT 18/07/2026**; chi tiết cột/kiểu làm ở bước sau. Mức **khái niệm**, không phải SQL.
> **Nguồn:** dữ liệu thật v1 + học từ v2 (tham chiếu) + `forward-spec.md` (viewability, AI-first) + retrieval Bước 1.

## 1. Sơ đồ quan hệ

```mermaid
erDiagram
    task ||--o{ task_item : "có"
    note ||--o{ note_item : "có"
    calendar_source ||--o{ calendar_event : "sinh ra"
    tracker ||--o{ entry : "ghi"

    task {
        uuid id
        text title
        text body_md "markdown, lưu FULL"
        text status "open/completed"
        text priority
        timestamptz due_at "nullable, có timezone"
        timestamptz created_at
        timestamptz updated_at
    }
    task_item {
        uuid id
        uuid task_id FK
        text content
        bool is_completed
        int position
    }
    note {
        uuid id
        text title
        text body_md "markdown, lưu FULL"
        vector embedding "placeholder Bước 1"
        timestamptz created_at
        timestamptz updated_at
    }
    note_item {
        uuid id
        uuid note_id FK
        text content
        bool is_completed
    }
    calendar_source {
        uuid id
        text name "vd: TKB kỳ 2025.2"
        text kind "ics/excel/manual"
        text color
        timestamptz created_at
    }
    calendar_event {
        uuid id
        uuid source_id FK
        text title
        text location
        timestamptz starts_at "có timezone"
        timestamptz ends_at
        bool is_hidden
    }
    tracker {
        uuid id
        text name "vd: Bia rượu / Hút thuốc / Sub AI"
        text kind "health / finance"
        text unit "VND / count / minutes"
        text color
        timestamptz created_at
    }
    entry {
        uuid id
        uuid tracker_id FK
        numeric value
        timestamptz occurred_at
        text note_md "markdown"
        timestamptz created_at
    }
    app_setting {
        text key
        jsonb value
    }
    audit_log {
        uuid id
        text action
        text tool
        jsonb payload
        timestamptz created_at
    }
```

## 2. Thực thể — nói bằng tiếng người

- **task** (+ **task_item**) = việc có deadline + subtask. Xoá task → xoá kèm item (sửa bug mồ côi v1). `body_md` = markdown.
- **note** (+ **note_item**) = ghi chú tự do, có mốc thời gian ("tính thời gian"). `body_md` markdown. `embedding` để Bước 1 cắm semantic search.
- **calendar_source → calendar_event** = nguồn lịch (file TKB/lịch thi) sinh ra các buổi. Re-import = **thay sạch không nhân đôi**. `starts_at/ends_at` **có timezone** (sửa bug v1).
- **tracker → entry** = 🆕 theo dõi **sức khỏe + tài chính** chung một mô hình. tracker định nghĩa "thứ theo dõi" (đơn vị VND hay count); entry là mỗi lần ghi (value + thời điểm). "Chi bia tháng này" / "hút mấy điếu tuần này" = cùng kiểu query, `GROUP BY tracker, khoảng thời gian`.
- **app_setting** = cấu hình `jsonb`. **audit_log** = nhật ký hành động, sẵn cho tool ghi AI (Bước 2) + "log to fine-tune".

## 3. Quyết định đã chốt (A/B/C + markdown)

- **A — Lịch:** ✅ đường giữa — có `calendar_source` + dedup khi re-import, **bỏ** version-history đầy đủ của v2.
- **B — Tracker:** ✅ **làm ngay**, gộp **health + finance** thành `tracker`/`entry` (một mô hình). *Làm phần ghi-log trước; AI phân tích giữ đúng thứ tự sau. Dữ liệu nhạy cảm → bar bảo mật nổi lên khi AI đọc qua LLM bên thứ ba (bookmark Bước 1).*
- **C — task vs note:** ✅ tách riêng.
- **Markdown:** ✅ nguyên tắc — **cấu trúc ở chỗ cần query, markdown ở chỗ viết văn xuôi.** Body/prose (`task.body_md`, `note.body_md`, `entry.note_md`) = markdown; status/deadline/category/unit = cột riêng.

## 4. Đã cố định theo quyết định trước
- Timezone thật ở mọi mốc; text lưu full; FK cascade cho subtask; `pgvector` cho note; `audit_log` dựng sẵn; bỏ "Don't care" event.

## 5. ✅ note_item — đã chốt
- **Gốc lưu dạng bảng/cột** (tick/query được). Markdown chỉ là **lớp trung gian lưu/tương tác**, không phải nơi lưu gốc. Nhất quán với `task_item`.
