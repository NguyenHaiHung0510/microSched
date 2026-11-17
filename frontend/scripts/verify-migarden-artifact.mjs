import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'

const dist = fileURLToPath(new URL('../dist', import.meta.url))
const marker = Buffer.from('N01_' + 'QA_ARTIFACT_CANARY')
const denied = /(?:^|[/\\])(?:tests|test-results|fixtures|integrated|e2e|\.local)(?:[/\\]|$)|(?:^|[/\\])n01-qa-|\.token$/i

async function scan(directory, prefix = '') {
  const failures = []
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = join(directory, entry.name)
    const relative = prefix + entry.name
    if (denied.test(relative)) failures.push(relative)
    else if (entry.isDirectory()) failures.push(...await scan(file, relative + '/'))
    else if (/\.(?:js|mjs|json|html|webmanifest|gz)$/i.test(entry.name)) {
      const bytes = await readFile(file)
      const content = entry.name.endsWith('.gz') ? gunzipSync(bytes) : bytes
      if (content.includes(marker)) failures.push(relative)
    }
  }
  return failures
}

const failures = await scan(dist)
if (failures.length) {
  console.error('N01 PWA guard FAIL: ' + failures.join(', '))
  process.exitCode = 1
} else {
  console.log('N01 PWA guard PASS: release assets contain no N01 fixture or credential file')
}
