import path from 'node:path'
import { execFileSync } from 'node:child_process'
import tailwindcss from '@tailwindcss/vite'
import { configDefaults, defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

const backendOrigin = process.env.VITE_BACKEND_ORIGIN ?? 'http://localhost:8000'

const buildSha = process.env.VITE_GIT_SHA || (() => {
  try { return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim() }
  catch { return 'development' }
})()

// https://vite.dev/config/
export default defineConfig({
  define: { 'import.meta.env.VITE_GIT_SHA': JSON.stringify(buildSha) },
  test: {
    exclude: [...configDefaults.exclude, '**/e2e/**'],
  },
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'autoUpdate',
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,ico,png,woff2}'],
        globIgnores: ['**/*cyrillic*'],
      },
      manifest: {
        name: 'microSched',
        short_name: 'microSched',
        display: 'standalone',
        theme_color: '#f3eeef',
        background_color: '#f3eeef',
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
  build: {
    rolldownOptions: {
      input: {
        app: path.resolve(__dirname, 'index.html'),
        denied: path.resolve(__dirname, 'denied.html'),
      },
    },
  },
  server: {
    proxy: {
      '/api': backendOrigin,
      '/auth': backendOrigin,
    },
  },
})
