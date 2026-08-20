import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const dist = join(root, 'dist')
const expectedCanvas = '#f3eeef'
const primitiveFiles = ['badge.tsx', 'button.tsx', 'checkbox.tsx', 'input.tsx', 'select.tsx', 'textarea.tsx']

const manifest = JSON.parse(await readFile(join(dist, 'manifest.webmanifest'), 'utf8'))
const index = await readFile(join(dist, 'index.html'), 'utf8')
const cssFiles = (await readdir(join(dist, 'assets'))).filter((file) => file.endsWith('.css'))
const builtCss = (await Promise.all(cssFiles.map((file) => readFile(join(dist, 'assets', file), 'utf8')))).join('\n')
const source = await Promise.all(
  primitiveFiles.map((file) => readFile(join(root, 'src', 'components', 'ui', file), 'utf8')),
)

const failures = []
if (manifest.theme_color !== expectedCanvas) failures.push(`manifest.theme_color=${manifest.theme_color}`)
if (manifest.background_color !== expectedCanvas) {
  failures.push(`manifest.background_color=${manifest.background_color}`)
}
if (!index.includes(`<meta name="theme-color" content="${expectedCanvas}"`)) {
  failures.push('index.html missing exact theme-color meta')
}
if (/42b883|#42b883/i.test(JSON.stringify(manifest) + index)) failures.push('green manifest/index color found')
if (source.some((contents) => contents.includes('dark:'))) failures.push('dark:* found in light-only primitive source')
if (/prefers-color-scheme\s*:\s*dark/i.test(builtCss)) {
  failures.push('prefers-color-scheme: dark found in built CSS')
}

if (failures.length > 0) {
  console.error('PWA surface guard FAILED')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exitCode = 1
} else {
  console.log(`PWA surface guard PASS: canvas=${expectedCanvas}; no green/dark styling`)
}
