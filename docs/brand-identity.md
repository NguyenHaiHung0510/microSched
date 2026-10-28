# Brand references — microSched, Mimi, Orbit

Origami/giấy Washi, màu ivory/sakura/berry và gold dùng tokens trong [index.css](../frontend/src/index.css). Artwork identity dùng SVG trong suốt; không raster crop concept image hoặc generic Bot/Sparkles/Cpu thay nhân vật. Product UI dùng [UI contract](ui-brief.md); source/tests là bằng chứng component API hiện hành.

| Identity | Component/API | Live artwork |
|---|---|---|
| microSched Calendar Bloom | BrandLogo: mark/wordmark/full; sm/md/lg; full có optional tagline | [mark](../frontend/public/brand/microsched-mark.svg), [wordmark](../frontend/public/brand/microsched-wordmark.svg), [app icon](../frontend/public/brand/microsched-app-icon.svg) |
| Mimi | MimiAvatar: idle/thinking/executing/ready labels, xs/sm/md/lg/xl, optional ariaLabel | **Một identity cố định:** [principal logo](../frontend/public/brand/principal-mimi-logo.svg) cho mọi state; status nằm ở surrounding UI/accessible label |
| Orbit | OrbitIndicator: standby/pulse/active/complete, sm/md/lg, status role/ariaLabel | [orbit blossom](../frontend/public/brand/orbit-blossom.svg) |

MimiAvatar không đổi artwork theo state và không dùng bốn state SVG cũ; showGlow là compatibility prop, không có current rendering effect. [MimiBackdrop](../frontend/src/MimiBackdrop.tsx) dùng CSS/vector artwork hiện hành, không phải bộ state SVG đó. Giữ dynamic [showcase assets](../frontend/public/showcase) và các npm preview commands đang dùng.

Motion cho Orbit nằm trong [brand-motion.css](../frontend/src/brand-motion.css): breathe/pulse/orbit/complete và prefers-reduced-motion override. Không claim MimiAvatar import/motion mà source không có. Không đổi identity/status API để làm cleanup pass.

[Components](../frontend/src/components/brand) và [brand regression](../frontend/tests/brand-identity.test.tsx) là consumer/tests chính. Historical concept images dưới [assets/brand-concepts](assets/brand-concepts/README.md) là dated visual references, không thay artwork runtime.
