# microSched frontend

Static React/TypeScript PWA, build bằng Vite; production được FastAPI phục vụ cùng origin. Node chỉ cần lúc development/build.

Từ thư mục này: `npm ci`, `npm run dev`. Vite proxy API/auth về backend mặc định ở `http://localhost:8000`. Các checks: `npm run lint`, `npm test`, `npm run build`, `npm run e2e`; build gồm Apple icon/PWA verification và precompression.

[Development](../docs/engineering/development.md) giữ setup/test chuẩn; [UI contract](../docs/ui-brief.md) và [brand](../docs/brand-identity.md) giữ quy tắc trình bày. [Outbox](../docs/reference/offline-outbox.md) hỗ trợ 11 Task/checklist/Entry commands; các domain còn lại vẫn online. [Verification](../docs/verification/README.md) phân biệt source/unit/build, browser, device và production evidence.
