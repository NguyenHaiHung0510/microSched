# Migration mapping brief — dữ liệu cũ → microSched mới

> Decision record **tự-chứa**. Dựa trên inventory read-only chạy 18/07/2026 (SQLite `todo.db` copy tạm rồi xoá; Postgres `microschedule_v2` mở session read-only, chỉ SELECT). Script tái dùng: `../scripts/inventory_old_stores.py`.

## 1. Kết luận: bản thật nằm ở đâu
| Store | Sửa lần cuối | Trạng thái |
|---|---|---|
| **PostgreSQL `microschedule_v2`** (local) | 18/07/2026 00:08 (tasks), 17:41 (notes) | 🟢 **SỐNG — nguồn thật** |
| SQLite `todo.db` | 03/06/2026 | 🔴 chết — tập con cũ, đã migrate 1 lần hồi 05/2026 |

**→ Migrate từ Postgres v2, bỏ qua SQLite.**

Số liệu thật trong Postgres v2: **163 tasks, 97 task_items, 49 notes, 81 note_items, 479 calendar_events, 4 calendar_sources, 8 app_settings, 6 priorities**; `agent_action_log` rỗng.

## 2. Mapping bảng cũ (v2) → schema mới (mức khái niệm)
| v2 (nguồn) | mới (`schema-v1-brief`) | Ghi chú |
|---|---|---|
| `tasks` | `task` | + cột `body_md` (markdown) |
| `task_items` | `task_item` | gần 1:1 |
| `notes` | `note` | + `body_md`, để trống `embedding` (Bước 1 mới tính) |
| `note_items` | `note_item` | gần 1:1 (giữ dạng cột) |
| `calendar_sources` + `calendar_source_versions` | `calendar_source` | **rút gọn** — bỏ version-history (Fork A), giữ source hiện hành |
| `calendar_events` | `calendar_event` | ép timezone thật khi copy |
| `app_settings` + `priorities` | `app_setting` (jsonb) | gộp đơn giản |
| `agent_action_log` | `audit_log` | rỗng, schema mới định nghĩa lại |
| — | `tracker` / `entry` | **mới hoàn toàn**, tạo rỗng |

## 3. ✅ 121 dòng lịch lệch — chốt bỏ qua (18/07/2026)
SQLite có 600 dòng `schedule` (tới 09/08/2026) nhưng Postgres v2 chỉ 479 `calendar_events` — vài buổi có thể chỉ còn ở SQLite. **Bỏ qua:** lúc cutover **import lại file TKB/lịch thi gốc** (.ics/.xlsx) vào app mới — sạch hơn đối chiếu tay 2 nguồn.

## 4. Vệ sinh vận hành (chống lặp split-brain)
Bài học app cũ: dùng **cả SQLite lẫn Postgres cùng lúc** → không rõ bản nào thật. microSched mới:
- ✅ **Một store duy nhất: Neon Postgres.** Không SQLite, không Postgres-local song song.
- ✅ **microSched có DB role riêng, quyền giới hạn** — KHÔNG dùng chung superuser `postgres` local (superuser đó host nhiều project của chính chủ, vd `Fang`).
- ✅ **Credentials chỉ trong `.env`, không commit;** `.gitignore` chặn `.env` từ commit đầu tiên.
- Postgres local `microschedule_v2` sau migrate → giữ làm archive tạm, không xoá ngay, không dùng làm nguồn sống song song.

## 5. Cutover checklist (chưa phải bây giờ)
1. `pg_dump` từ Postgres v2 local.
2. Transform theo mapping §2 (script một lần, T2 viết theo brief này).
3. Load vào Neon.
4. Verify: đếm dòng khớp, spot-check vài task/note (dùng `inventory_old_stores.py` làm mẫu).
5. Import lại file lịch gốc (giải quyết §3).
6. VC cũ (`main` branch) là đường lùi tới khi tự tin cutover.
