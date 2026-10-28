# Mimi — PARTIAL technical README

Mimi là module AI đang phát triển trong microSched. Năng lực **Task/checklist** đã được triển khai: bounded query/aggregate/inspect/content, selection có provenance, create/edit/delete/restore/checklist proposals, review/revision và explicit Confirm/compensating undo. Delivery này không có nghĩa mọi domain, PRIVATE AI, attachments, memory, skills/jobs hay toàn bộ roadmap agent đã hoàn tất.

## Luồng hiện hành

1. Authenticated STANDARD conversation tạo run có identity/frontier/source/capability và finite limits do server quản lý.
2. Context lắp policy, history/summary, tool/reference state và provenance. Model read/propose; external content và model output không cấp quyền.
3. Server validate selection/versions/args, tạo frozen preview cho review/revise/reject/Confirm. Chat thường không tự làm mất preview hợp lệ.
4. Confirm kiểm frozen operations, current authority/source/CAS và all targets trước một transaction với receipt/refresh marker. Timeout/unknown cần reconcile, không replay mù.
5. Reload/reconnect đọc durable run/events/receipts; usage/cost/cache chỉ claim theo attributable receipt. Feedback gắn target/cause và encrypted evidence.

Source: [service](../../backend/app/agent/service.py), [tool registry](../../backend/app/agent/tools/registry.py), [LangGraph](../../backend/app/agent/langgraph_runner.py), [models](../../backend/app/agent/models.py), [MimiScreen](../../frontend/src/MimiScreen.tsx), [authenticated router](../../backend/app/web/routers/mimi.py).

| Chủ đề | Maintained contract |
|---|---|
| Selection, Task/checklist commands, CAS/Confirm/undo, notifications | [Task collection](task-collection.md) |
| Gateway policy, bounded retry, unknown/accounting | [Native routing](native-routing.md) |
| Collection/context/Resume semantics và required qualification | [Operating contract](operating-contract.md) |
| Context composition/telemetry và dated illustrations | [Context](context.md) |
| Authority, application-visible evidence và feedback | [Evidence](evidence.md) |
| Case inputs, selectors, evidence layers | [Verification](../verification/README.md) |

Native routing supersedes local provider roster/certificate admission. [fly.toml](../../fly.toml) là source preset: collection/context/live enabled, LangGraph + OpenAI SDK/native gateway, notifications **off**. Nó không chứng minh flags production thực tế. Model/effort, manual price caps, privacy/precision và limits phải đối chiếu config/source, không lấy từ receipt cũ. README không cấp quyền provider call.

## Resource/recovery boundaries

Default admission là 2 active runs; finite turn/read/deadline/payload/no-progress/overflow guards theo run persisted. App process và DB pool dùng chung; admission không chứng minh load isolation hay bảo vệ hoàn toàn khỏi OOM/event-loop stalls. Unknown giữ cost liability và cần reconcile. Production không dùng private local paid-QA ledger.

Native main/helper dùng provider output defaults theo operating contract. 8192 là context planning reserve, không phải universal generation cap. Soft compact272K, operating target400K, model capacity và 2MiB resource bound có nghĩa khác nhau. Không suy token count từ bytes hoặc bịa per-category usage.

[Auth R1–R7](../auth-brief.md) là policy ceiling; STANDARD Task capability hiện loại PRIVATE, không suy PRIVATE slice đã được cấp/triển khai. In-app attention/per-device notification có contract riêng; implementation không chứng minh actual Push/physical-device delivery.

## Verification và giới hạn

Unit/SDK double, disposable PG, synthetic browser, actual model và physical device là các lớp khác nhau. Ordinary history có 6 case accepted với recovery; HARD benchmark giữ riêng gồm failures/limitations. Không claim whole-Mimi/all-green universal. Required cases/denominators và acceptance chưa prove vẫn giữ scope ở [Verification](../verification/README.md).

[Development](../engineering/development.md) giữ setup/test; [Operations](../operations/runbook.md) giữ deploy/migration/backup/recovery. Không tự enable provider, replay paid QA, đổi policy, migrate hoặc reset retained QA DB theo docs.
