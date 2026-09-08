import { readdir, readFile, writeFile } from 'node:fs/promises'
import { gzipSync } from 'node:zlib'

// Run after Vite/PWA generation: compressed alternatives keep original URLs and
// do not add duplicate entries to the service worker's precache manifest.
const assets = new URL('../dist/assets/', import.meta.url)
let originalBytes = 0
let compressedBytes = 0
let files = 0
for (const entry of await readdir(assets, { withFileTypes: true })) {
  if (!entry.isFile() || !/\.(js|css)$/.test(entry.name)) continue
  const original = await readFile(new URL(entry.name, assets))
  const compressed = gzipSync(original, { level: 9 })
  if (compressed.length >= original.length) continue
  await writeFile(new URL(`${entry.name}.gz`, assets), compressed)
  originalBytes += original.length
  compressedBytes += compressed.length
  files += 1
}
console.log(`Precompressed ${files} assets: ${originalBytes} -> ${compressedBytes} bytes`)
