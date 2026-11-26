# Conversation creation and rename

Current source at the [indexed baseline](README.md): `frontend/src/MimiControlCenter.tsx:87`, `:225` and `:347`, `frontend/src/MimiDock.tsx:59`. Runtime **NOT_RUN**.

## Sub-features

STANDARD conversation create, rename, archive and restore. Reopen the same conversation after reload.

## How to get to it (user POV)

In Workspace choose **Cuộc trò chuyện mới**. The dock’s **Tùy chọn side-chat** menu has **Hội thoại mới**. In Workspace scope the row’s **Tùy chọn …** menu to the owned title, choose **Đổi tên**, fill **Tên hội thoại** and choose **Lưu tên**. Archive in **Đang dùng** and restore from **Đã lưu**.

## Driving it in a current synthetic candidate

Bind an owned synthetic session and unique client ID/title. Observe `POST /api/mimi/conversations`, `PATCH /api/mimi/conversations/{id}` and separately permitted `POST` archive/restore paths. Reopen the owned ID, check one durable record/title/archive state and zero new chat run or provider call. [History](history-workspace.md) covers workspace aliases.

## Gotchas

Ambiguous legacy client IDs return 409 under the [Owner workspace contract](../../../../docs/mimi/owner-workspace.md). History remains openable by exact ID. Metadata writes still require the current grant.
