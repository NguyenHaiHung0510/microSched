# Responsive side-chat and pop-out

Source: `frontend/src/MimiDock.tsx:21` (`mimi-dock-toggle`) in exact `680b7f9b0dc18e3fc04141fbdcd18c86ffb22b37`; source root `harness-b-mimi-qa/microsched`. Harness/map lives on the separate source branch; Mimi QA snapshot remains Main-owned.

## Sub-features

Dock toggle/close, desktop width, narrow viewport dialog, workspace pop-out.

## How to get to it (user POV)

Non-Mimi app tab → Chat với Mimi → Tùy chọn side-chat → Pop-out chat / Workspace.

Real prerequisites: mimi_available synthetic session and selected conversation; freeze >=1280 desktop and <1280 modal viewports for a separate UI batch.

## Driving it with H14 isolated browser/CLI

mimi-dock-toggle, mimi-side-chat, Đóng side-chat, Đổi độ rộng side-chat separator and menuitem Pop-out chat / Workspace.

Observable oracle: Open/close and focus remain usable; same conversation transfers to workspace; bounded width and narrow-dialog layout match actual source.

## Gotchas

Closing side-chat does not cancel a run. No viewport coverage from metadata smoke; physical device remains NOT_RUN.

Status: source-mapped, NOT_RUN. No runtime/CI/device/production acceptance follows from this recipe.
