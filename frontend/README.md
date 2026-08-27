# Frontend microSched

Frontend là static PWA của microSched, viết bằng React + TypeScript và build bằng Vite. Node chỉ cần ở development/CI/build; production được FastAPI phục vụ cùng origin.

## Development

```powershell
cd frontend
npm ci
npm run dev
```

Backend chạy riêng ở `http://localhost:8000`; xem hướng dẫn env và database tại [`../backend/README.md`](../backend/README.md).

## Scripts

```powershell
npm run lint
npm test
npm run build
npm run e2e
```

`build` cũng kiểm tra Apple touch icon và PWA surface. E2E cần Playwright browser dependencies; không dùng dữ liệu cá nhân thật trong fixture hoặc screenshot.

## UI và offline boundary

- UI dùng Tailwind v4 + shadcn/ui theo design rules của [`../docs/ui-brief.md`](../docs/ui-brief.md).
- TanStack Query quản lý server state; Dexie là local storage boundary.
- Service worker hỗ trợ precache và notification paths.
- Full offline outbox cho mọi write domain vẫn là roadmap, chưa mô tả như đã hoàn tất.
