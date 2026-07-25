import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      workbox: {
        // Mặc định service worker trả index.html cho MỌI điều hướng, nên nó nuốt
        // luôn /auth/login và /auth/callback: request không bao giờ tới FastAPI và
        // nút đăng nhập im lặng không làm gì. Route nào do server xử lý phải được
        // loại khỏi fallback để đi thẳng ra mạng.
        navigateFallbackDenylist: [/^\/auth\//, /^\/api\//],
        // Mặc định của plugin KHÔNG gồm woff2, nên font tự host không được
        // precache và mở offline sẽ rơi về font hệ thống — đúng kịch bản PWA
        // sinh ra để phục vụ. Bỏ cyrillic: unicode-range đã bảo đảm trình duyệt
        // không bao giờ tải chúng, precache thì lại tải hết bất kể unicode-range.
        // Cố ý KHÔNG kê `svg` và `webmanifest`: plugin đã tự thêm icon + manifest,
        // kê lại là precache cùng một file hai lần (đã đo: 10 mục / 9 địa chỉ).
        globPatterns: ['**/*.{js,css,html,ico,png,woff2}'],
        globIgnores: ['**/*cyrillic*'],
      },
      manifest: {
        name: 'microSched',
        short_name: 'microSched',
        display: 'standalone',
        icons: [
          {
            src: 'microsched.svg',
            sizes: 'any',
            type: 'image/svg+xml',
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
