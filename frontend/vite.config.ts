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
