# Conversation creation and rename

Source: `frontend/src/MimiControlCenter.tsx:9` (`createMimiConversation`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Create STANDARD, rename, reload/reopen selected conversation.

## How to get to it (user POV)

Synthetic login → Mimi → Hội thoại → Cuộc trò chuyện mới → Tùy chọn → Đổi tên.

Real prerequisites: First approved Mimi case: exact680b7f9b binding; provider/context/pilot/collection/notifications false, real-chat metadata shell true.

## Driving it with H14 isolated browser/CLI

mimi-input; textbox Tên hội thoại; Lưu tên; title H14 synthetic conversation; reload and reselect.

Observable oracle: New thread title persists through reload/reopen; no send/run/decision/provider route; synthetic app logout and owned-context close.

## Gotchas

Metadata proof is not conversation quality or latest Owner product acceptance.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
