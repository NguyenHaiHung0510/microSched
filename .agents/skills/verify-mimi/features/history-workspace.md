# Workspace rails and conversation history

Current source at the [indexed baseline](README.md): `frontend/src/MimiControlCenter.tsx:209`, `:232` and `:279`, `frontend/src/MimiDock.tsx:63`. Runtime **NOT_RUN**.

## Sub-features

History search and pagination, active/archived lists, local pinning, left and data rails, and Owner workspace history across authorized synthetic logins.

## How to get to it (user POV)

Open **Mimi** Workspace, then **Hội thoại** or the small-screen dialog. Choose **Đang dùng** or **Đã lưu**, and search using **Tìm cuộc trò chuyện**. Side-chat’s **Lịch sử hội thoại** provides the alternate path. Open the data rail from **Thống kê hội thoại**.

## Driving it in a current synthetic candidate

Use `mimi-workspace` and `mimi-left-rail` on wide layout, or scope to the small-screen **Hội thoại** dialog. Scope the named conversation row and compare its exact ID with `GET /api/mimi/conversations` and `GET /api/mimi/conversations/{id}`. Keep the matching session/cursor, and confirm opening or rearranging rails adds no run. Pin ordering in this UI is local.

Oracle: At the same login the selected ID and transcript survive the documented transitions. Shared Owner mode requires explicitly modeled allowlisted synthetic identities, shared and legacy STANDARD fixtures and a foreign/PRIVATE negative fixture. Use `backend/tests/test_mimi_owner_workspace.py` and `backend/tests/test_mimi_owner_workspace_pg.py`. Test flag off/on independently per the [Owner workspace contract](../../../../docs/mimi/owner-workspace.md).

## Gotchas

A synthetic single identity with an empty allowlist cannot prove alias sharing. No identity/key changes, allowlist operations or data rebind follow from this recipe.
