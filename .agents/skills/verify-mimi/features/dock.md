# Responsive side-chat and pop-out

Current source at the [indexed baseline](README.md): `frontend/src/App.tsx:97`, `:195` and `frontend/src/MimiDock.tsx:61`. Runtime **NOT_RUN**.

## Sub-features

Desktop side panel, small-screen dialog, guarded shortcut, focus return and workspace handoff.

## How to get to it (user POV)

From another domain choose **Chat với Mimi** in **Ứng dụng** or the quick-access control. **Alt+A** works at allowed focus points. In **Tùy chọn side-chat**, use **Pop-out chat / Workspace**, **Lịch sử hội thoại** or **Cấu hình Mimi**.

## Driving it in a current synthetic candidate

Use `mimi-dock-open`, `mimi-quick-access` and `mimi-side-chat`. Scope **Đóng side-chat** and **Tùy chọn side-chat** to that surface. At ≥1280px the dock is a panel and exposes **Đổi độ rộng side-chat**. Below that it is a dialog. Compare menu/shortcut/Escape and return focus with `frontend/e2e/mimi-access-priority.spec.ts` and a bound draft/owned conversation.

Oracle: The same chosen ID, draft and run survive switching presentation. Opening or closing the dock creates no second send/cancel. Verify the ineligible keyboard, overlay and capability-off paths independently.

## Gotchas

The live shell does not mount the old toggle component. Desktop/small-screen viewport evidence does not exercise physical devices.
