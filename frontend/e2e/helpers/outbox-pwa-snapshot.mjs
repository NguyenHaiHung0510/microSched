import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { cp, mkdir, readdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

const dirty = execFileSync('git', ['status', '--porcelain', '--', 'src', 'public', 'package.json', 'package-lock.json', 'vite.config.ts', 'tsconfig.app.json'], { encoding: 'utf8' })
if (dirty.trim()) throw new Error('Commit the product/build inputs before creating an exact-head PWA receipt')
const head = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
const root = path.resolve(process.env.QA017_RECEIPT_DIR ?? '../output/outbox-pwa')
const source = path.resolve('dist')
const destination = path.join(root, 'artifacts', 'builds', head, 'dist')
async function hashes(directory, relative = '') {
  const result = {}
  for (const entry of await readdir(path.join(directory, relative), { withFileTypes: true })) {
    const name = path.posix.join(relative, entry.name)
    if (entry.isDirectory()) Object.assign(result, await hashes(directory, name))
    else result[name] = createHash('sha256').update(await readFile(path.join(directory, name))).digest('hex')
  }
  return Object.fromEntries(Object.entries(result).sort(([a], [b]) => a.localeCompare(b)))
}
const built = await hashes(source)
if (!built['index.html'] || !built['sw.js']) throw new Error('Missing production PWA build; use the package runner')
let existing
try { existing = await hashes(destination) } catch (error) { if (error.code !== 'ENOENT') throw error }
if (existing && JSON.stringify(existing) !== JSON.stringify(built)) throw new Error('Existing immutable build differs; retain it and choose a separate receipt directory')
if (!existing) { await mkdir(path.dirname(destination), { recursive: true }); await cp(source, destination, { recursive: true, errorOnExist: true, force: false }) }
const manifestPath = path.join(root, 'manifest.json')
let manifest = { queue_observations: [] }
try { manifest = JSON.parse((await readFile(manifestPath, 'utf8')).replace(/^\uFEFF/, '')) } catch (error) { if (error.code !== 'ENOENT') throw error }
await writeFile(manifestPath, JSON.stringify({ ...manifest, source_head: head, build_sha256: built, built_via: 'npm run e2e:outbox-pwa; production build then immutable snapshot' }, null, 2) + '\n')
console.log(`Frozen PWA build ${head}; ${Object.keys(built).length} files; ${destination}`)
