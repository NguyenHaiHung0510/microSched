# Conversation creation and rename

Source: `frontend/src/MimiControlCenter.tsx:9` (`createMimiConversation`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Create STANDARD, rename, reload/reopen selected conversation.

## How to get to it (user POV)

Synthetic login → Mimi → ensure conversation rail is open (keep an already-visible create button; open Hội thoại (N) only when closed) → Cuộc trò chuyện mới → the new conversation’s Tùy chọn menu → Đổi tên.

Real prerequisites: First approved Mimi case: exact 680b7f9b binding; provider/context/pilot/collection/notifications false, real-chat metadata shell true.

## Driving it with H14 isolated browser/CLI

mimi-left-rail and its Cuộc trò chuyện mới; open-state Thu gọn hội thoại / closed-state Hội thoại (N); mimi-input; textbox Tên hội thoại; Lưu tên; run-unique H14 synthetic conversation title bound to the created synthetic ID; reload and reselect that exact row.

Observable oracle: New thread title persists through reload/reopen; no send/run/decision/provider route; synthetic app logout and owned-context close.

## Gotchas

Metadata proof is not conversation quality/latest Owner product acceptance. The desktop rail defaults open: preserve a visible create button; only open the closed Hội thoại(N) toggle when needed. Actual independent case observed already-open state; the closed-state branch is source-supported, not separately runtime-exercised. Only the three observed local Nunito normal wght fonts (latin,latin-ext,vietnamese) are admitted at the exact frontend origin.

Task-owned synthetic MIMI_PUBLIC_ORIGIN=http://127.0.0.1:5173 matches the browser across Vite proxying; product CSRF enforcement is unchanged, no fake Origin header. The original selector/font failure and first T1 Origin-refused smoke remain immutable. After Main's corrected wrapper restart, T1 smoke passed 4/4; distinct independent attempt2 then passed 4/4 with zero blocked. The unique title binds to the newly created synthetic ID so a later run cannot pass against an older thread. No send/turn/run/provider route was admitted or recorded; provider-wire evidence remains NOT_CAPTURED.

Status: OBSERVED_ACCEPTED for this STANDARD metadata recipe only, exact 680b7f9b, H14-N1/R9 attempt2. Evidence locator: mimi-attempt2/receipt.json and before/after pixels, final-mimi-handback, final-grouped-retest-handback, final-runtime-cleanup and R6 final-technical-signoff in the private task record. Logout/context close and Main runtime cleanup observed, evidence retained. Other eleven mapped features NOT_RUN; no latest-product/conversation-quality/CI/device/production claim.
