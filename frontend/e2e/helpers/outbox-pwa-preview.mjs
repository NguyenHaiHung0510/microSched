import { preview } from 'vite'

if (process.env.QA017_SYNTHETIC_ACK !== '1') throw new Error('Verify the authorized synthetic DB/session and set QA017_SYNTHETIC_ACK=1')
const backend = new URL(process.env.QA017_BACKEND_URL ?? 'http://127.0.0.1:8003')
if (backend.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(backend.hostname) || backend.username || backend.password) {
  throw new Error('Outbox PWA QA requires an explicitly authorized synthetic loopback backend')
}
const readyResponse = await fetch(new URL('/api/readyz', backend), { signal: AbortSignal.timeout(5000) })
const ready = await readyResponse.json()
if (!readyResponse.ok || ready.db !== 'up') throw new Error('Synthetic backend is not database-ready')
if (!process.env.QA017_BACKEND_SHA || ready.commit !== process.env.QA017_BACKEND_SHA) throw new Error('Unexpected synthetic backend commit')
const buildDir = process.env.QA017_BUILD_DIR
if (!buildDir) throw new Error('Use npm run e2e:outbox-pwa to snapshot the production build first')
const server = await preview({
  configFile: false,
  build: { outDir: buildDir },
  preview: {
    host: '127.0.0.1', port: Number(process.env.QA017_PORT ?? 4174), strictPort: true,
    proxy: { '/api': backend.origin, '/auth': backend.origin },
  },
})
server.printUrls()
console.log(`Synthetic backend ready: commit=${ready.commit}; db=${ready.db}`)
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => { void server.close().finally(() => process.exit(0)) })
}
