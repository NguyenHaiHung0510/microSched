# Mimi authority, evidence và feedback

Contract của các biên hiện có, không tự cấp lease/provider budget/export/private rights. Source: [contracts](../../backend/app/agent/contracts.py), [models](../../backend/app/agent/models.py), [service](../../backend/app/agent/service.py), [collection](task-collection.md).

## Authority và transaction

Server cấp lease/capability gắn owner/run/sensitivity/source/frontier/deadline/limits/revocation. Model/UI không tự điền quyền, SQL/Store/shell/URL hoặc policy override. API/session/same-origin controls và từng tool capability vẫn là cổng bắt buộc.

Change set đóng băng typed args, ordered operations, IDs/versions, digest/nonce/expiry và idempotency binding. Preview/revision chưa mutate domain. Confirm kiểm current permission/source/frontier/all targets trước transaction; same binding trả original receipt, khác binding conflict. Receipt/recovery/refresh marker theo transaction contract; mất ACK không được replay mù.

Soft private lock che/purge read/callback theo gate; hard logout/revoke xóa volatile WIP và ngăn bước tiếp theo, không rollback commit. STANDARD không đọc/ghi PRIVATE hoặc tự promote sensitivity. [R1–R7](../auth-brief.md) là policy ceiling, không chứng minh PRIVATE slice đã triển khai.

## Application-visible evidence

Chỉ application-visible input/output, tool args/results, route/config/usage/cost và truthful completeness/provenance. Không hidden provider reasoning, secrets, auth headers, cookie/access/refresh tokens. Reasoning effort là config; raw reasoning không được đổi tên thành evidence.

Feedback gắn stable client identity, target/type, owner/conversation/run và causal range do server suy ra. Kiểm cross-run/cross-owner attachment; không tin bundle client tùy gắn. Nội dung mã hóa với resource-bound AAD; metadata chỉ IDs/hashes/counts/completeness. Missing/truncated material là INCOMPLETE/FAILED, không fabricated COMPLETE.

Collection contract giữ cap 1MiB/bundle, logical expiry90days và không automatic physical purge; durable execution recovery có lifecycle riêng. ACK chứng minh server nhận feedback, không tự thành triaged/fixed/Owner satisfied. Không plaintext persistent retry queue; failure giữ unsaved/draft theo UI contract.

Export/retention/destructive deletion cần scope/quyền và verified destination/integrity riêng. Không đưa transcript vào global memory/public report/fixture. Reset synthetic domain không xóa acceptance/recovery evidence. Local P0 substrate và dated QA stores không đặt production retention policy; Git history không tự khôi phục grants/counters hết hạn.

Unknown provider/commit giữ uncertainty/accounting liability; reconnect quan sát cùng durable run, retry chỉ sau reconcile đúng contract. Per-attempt usage khác tool-loop turns; missing cost không bằng zero. Freeze và independent QA theo [Verification](../verification/README.md).
