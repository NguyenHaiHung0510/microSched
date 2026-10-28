# Current UI behavior reference

Contract kỹ thuật của các UI096/097/098 và Mimi feedback hiện có; [App](../../frontend/src/App.tsx), [Note reader](../../frontend/src/NotesScreen.tsx), [MimiScreen](../../frontend/src/MimiScreen.tsx) và existing tests là source anchors. Đây không phải user manual hoặc grant redesign.

## Shell, content và reader

Responsive five-domain navigation, một accessible app menu, compact header/private/queue và bốn vùng Tracker. Safe automatic PWA update không thêm routine banner; defer cho draft/mutation/admission/storage/transport boundaries, không clear/persist private drafts hoặc đổi outbox protocol bytes.

Notes hai cột desktop/một mobile, pinned-first trong filter/sort/local find; body/checklist/reflection preview có full expansion/detail. Preview body6lines, first reflection4, first3 unfinished items×4lines; disclosed completed items vẫn clamp; full collapse reset disclosure. Stored text giữ nguyên.

Reader B là full-region detail lifecycle: safe-area header/back/edit, body→checklist→reflections, section navigation. Close khôi phục actual opener viewport offset và filter context dù preview height đổi. Checklist toolbar Pencil/ArrowUpToLine/Trash; top disabled ở item đầu mỗi completion group. Atomic move-to-top so full content-free snapshot dưới parent lock, chỉ permute group's slots; unchanged replay no-op, stale membership/completion/ranks409 zero writes. Persisted child delete có explicit confirmation.

Task title wrap/autogrow có measured-height fallback; Enter theo enabled submit/IME và CR/LF contract. Legacy unedited title/body giữ nguyên. Dialog long unbroken content phải shrink/wrap, không đẩy controls khỏi viewport; không thêm arbitrary hard card height.

## Reminder History

Selection khác saved-handled state; basic/advanced/help/device controls giữ bulk API/count/cutoff/private semantics. ACK chỉ patch existing scoped cache bằng server timestamp, giữ pages/row DOM/disclosure/current-next-previous anchors qua background refetch. Old settlement không xóa newer anchor; filter/auth/private purge discard anchors.

Sau dispatched commit, timeout/network/server-ACK loss/invalid ACK giữ explicit uncertainty và original prepared batch ID. Dialog pending/unknown không cho close/cancel làm mất snapshot; offline retry giữ uncertainty và same-ID intent. Pre-send refusal khác ambiguous dispatch; không auto retry. Fresh dialog chỉ hiện error của batch mình; scope purge vẫn clear theo contract.

## Mimi feedback và observational metrics

Positive/negative detail và optional expected outcome mỗi field8000Unicode codepoints; comment envelope10000 gồm polarity/reasons, expected có API envelope riêng10000. Over-limit editable, IME không cắt, codepoint counter, submit đợi composition kết thúc. Unknown-result retry giữ original key/body/target; stale ACK không clear newer draft. Draft memory-only; encryption/causal evidence unchanged.

Browser E2E là client observation từ accepted UI action trước fetch đến canonical DOM + visible paint opportunity, khác provider TTFT/server duration/billing. Preview và Confirm là segments riêng, không tính human wait. Hidden/offscreen/closed/history/reload không bịa monotonic start; missing/pending/failed/cancelled/unknown tách khỏi successful averages. Một bounded observation POST/phase, không token polling; failed metric ACK không fail answer/restart model/auto retry. Cost per run không cộng lặp theo segment.

Per-response timing line dưới system notices/Mimi replies đã được bỏ theo current source delta sau QA26–27Oct. Các observational backend records/conversation statistics còn trong source không phải performance benchmark hoặc physical display proof. Không dùng ảnh frozen trước delta để claim dòng mới đã được runtime-tested. [Verification](../verification/README.md) giữ provenance/limits và required checks.
