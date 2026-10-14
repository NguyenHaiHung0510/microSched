# Workspace rails and conversation history

Source: `frontend/src/MimiControlCenter.tsx:208` (`mimi-left-rail`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

History/list/search/filter, pin, archive/restore, selection and rail width/collapse.

## How to get to it (user POV)

Mimi workspace → Hội thoại/rail; side-chat menu → Lịch sử hội thoại; select actual fixture title.

Real prerequisites: Synthetic active/archived thread fixtures and metadata versions; archive/restore writes not included in first recipe.

## Driving it with H14 isolated browser/CLI

mimi-left-rail/mimi-right-rail; Tìm cuộc trò chuyện; Tùy chọn TITLE; inspect actual menuitems and MimiRailResize.tsx.

Observable oracle: Selected ID/thread agrees across history/dock/workspace; search/filter/paging maintain visible identity; authorized archive/restore survives reload.

## Gotchas

Pinned IDs are local UI storage, not durable server state. Keep real browser storage untouched.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
