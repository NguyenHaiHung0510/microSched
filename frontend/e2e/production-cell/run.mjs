import { createHash } from 'node:crypto'
import http from 'node:http'
import { once } from 'node:events'
import { chromium } from 'playwright'

let step = 'stdin'
const unexpectedHostHashes = new Set()

function assert(condition, message) {
  if (!condition) {
    throw new Error(message)
  }
}

async function readPayload() {
  const chunks = []
  for await (const chunk of process.stdin) chunks.push(chunk)
  const payload = JSON.parse(Buffer.concat(chunks).toString('utf8'))
  const expected = ['candidate_sha', 'email', 'fixture_labels', 'pin', 'prefix', 'run_id', 'session_token']
  assert(Object.keys(payload).sort().join(',') === expected.join(','), 'stdin fields')
  assert(/^msqa025-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}$/.test(payload.run_id), 'run id')
  assert(/^[0-9a-f]{40}$/.test(payload.candidate_sha), 'candidate sha')
  assert(payload.email.endsWith('@example.invalid'), 'synthetic email')
  assert(/^[0-9]{6}$/.test(payload.pin), 'synthetic pin')
  assert(payload.session_token.length >= 32, 'synthetic session token')
  assert(payload.prefix === `[QA025:${payload.run_id}]`, 'fixture prefix')
  const expectedFixtureLabels = [
    `${payload.prefix} denied-private`,
    `${payload.prefix} denied-item`,
    `${payload.prefix} public-task`,
    `${payload.prefix} private-task`,
    `${payload.prefix} public-note`,
    `${payload.prefix} public-item`,
    `${payload.prefix} private-item`,
    `${payload.prefix} note-item`,
    `${payload.prefix} synthetic body`,
  ]
  assert(
    Array.isArray(payload.fixture_labels) &&
      JSON.stringify(payload.fixture_labels) === JSON.stringify(expectedFixtureLabels),
    'fixture label ledger',
  )
  return payload
}

function startLoopbackProxy() {
  const server = http.createServer((request, response) => {
    const upstream = http.request(
      {
        hostname: 'app',
        port: 8000,
        method: request.method,
        path: request.url,
        headers: { ...request.headers, host: 'app:8000' },
      },
      (upstreamResponse) => {
        response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers)
        upstreamResponse.pipe(response)
      },
    )
    upstream.on('error', () => {
      if (!response.headersSent) response.writeHead(502)
      response.end('proxy unavailable')
    })
    request.pipe(upstream)
  })
  server.listen(0, '127.0.0.1')
  return server
}

async function api(page, path, options = {}) {
  return page.evaluate(
    async ({ requestPath, requestOptions }) => {
      const response = await fetch(requestPath, requestOptions)
      return {
        status: response.status,
        text: await response.text(),
      }
    },
    { requestPath: path, requestOptions: options },
  )
}

async function jsonApi(page, path, method, body) {
  return api(page, path, {
    method,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
}

async function main() {
  const payload = await readPayload()
  const proxy = startLoopbackProxy()
  await once(proxy, 'listening')
  const address = proxy.address()
  assert(address && typeof address === 'object', 'proxy address')
  const origin = `http://127.0.0.1:${address.port}`
  let browser
  let context
  let result
  try {
    step = 'launch'
    browser = await chromium.launch({ headless: true })
    context = await browser.newContext({ serviceWorkers: 'allow' })
    context.on('request', (request) => {
      const url = new URL(request.url())
      if (url.origin !== origin) {
        unexpectedHostHashes.add(createHash('sha256').update(url.host).digest('hex'))
      }
    })
    await context.route('**/*', async (route) => {
      const url = new URL(route.request().url())
      if (url.origin !== origin) {
        unexpectedHostHashes.add(createHash('sha256').update(url.host).digest('hex'))
        await route.abort('blockedbyclient')
        return
      }
      await route.continue()
    })
    const page = await context.newPage()

    step = 'anonymous'
    await page.goto(origin, { waitUntil: 'domcontentloaded' })
    const ready = await api(page, '/api/readyz')
    assert(ready.status === 200, 'candidate /api/readyz must be 200')
    const readyBody = JSON.parse(ready.text)
    assert(readyBody.status === 'ok', 'candidate /api/readyz status mismatch')
    assert(readyBody.db === 'up', 'candidate /api/readyz database mismatch')
    assert(readyBody.commit === payload.candidate_sha, 'candidate /api/readyz commit mismatch')
    const anonymous = await api(page, '/api/me')
    assert(anonymous.status === 401, 'anonymous /api/me must be 401')

    step = 'session'
    await context.addCookies([
      {
        name: 'ms_session',
        value: payload.session_token,
        url: origin,
        httpOnly: true,
        sameSite: 'Lax',
      },
    ])
    await page.reload({ waitUntil: 'domcontentloaded' })
    const me = await api(page, '/api/me')
    assert(me.status === 200, 'synthetic /api/me must be 200')
    assert(JSON.parse(me.text).email === payload.email, 'synthetic identity mismatch')

    step = 'pin'
    const setPin = await jsonApi(page, '/api/private/pin', 'POST', {
      current_pin: null,
      new_pin: payload.pin,
    })
    assert(setPin.status === 204, 'protected PIN setup failed')

    const [
      deniedTitle,
      deniedItem,
      publicTitle,
      privateTitle,
      noteTitle,
      publicItem,
      privateItem,
      noteItem,
      noteBody,
    ] = payload.fixture_labels
    const deniedPrivate = await jsonApi(page, '/api/tasks', 'POST', {
      title: deniedTitle,
      is_private: true,
      items: [deniedItem],
    })
    assert(deniedPrivate.status === 403, 'locked private create must be 403')
    assert(!deniedPrivate.text.includes(deniedTitle), 'locked response leaked private title')

    step = 'unlock-and-create'
    const unlock = await jsonApi(page, '/api/private/unlock', 'POST', { pin: payload.pin })
    assert(unlock.status === 200, 'protected private unlock failed')
    const publicTask = await jsonApi(page, '/api/tasks', 'POST', {
      title: publicTitle,
      is_private: false,
      items: [publicItem],
    })
    const privateTask = await jsonApi(page, '/api/tasks', 'POST', {
      title: privateTitle,
      is_private: true,
      items: [privateItem],
    })
    const note = await jsonApi(page, '/api/notes', 'POST', {
      title: noteTitle,
      body_md: noteBody,
      is_private: false,
      items: [noteItem],
    })
    assert(publicTask.status === 201, 'public task create failed')
    assert(privateTask.status === 201, 'private task create failed')
    assert(note.status === 201, 'note create failed')

    step = 'ui-and-service-worker'
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('[data-testid="task-title"]', { hasText: publicTitle }).waitFor()
    await page.locator('[data-testid="task-title"]', { hasText: privateTitle }).waitFor()
    await page.getByRole('tab', { name: 'Ghi chú' }).click()
    await page.locator('[data-testid="note-title"]', { hasText: noteTitle }).waitFor()
    await page.evaluate(async () => navigator.serviceWorker.ready)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null)

    step = 'lock'
    const lock = await api(page, '/api/private/lock', { method: 'POST' })
    assert(lock.status === 204, 'protected private lock failed')
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.locator('[data-testid="task-title"]', { hasText: publicTitle }).waitFor()
    assert(
      (await page.locator('[data-testid="task-title"]', { hasText: privateTitle }).count()) === 0,
      'private task remained visible after lock',
    )
    const lockedMe = await api(page, '/api/me')
    assert(lockedMe.status === 200, 'session disappeared after private lock')
    const visibleNotes = await api(page, '/api/notes')
    assert(visibleNotes.status === 200 && visibleNotes.text.includes(noteTitle), 'public note hidden')

    step = 'logout'
    const logout = await api(page, '/auth/logout', { method: 'POST' })
    assert(logout.status === 204, 'real logout failed')
    const loggedOut = await api(page, '/api/me')
    assert(loggedOut.status === 401, 'logout did not invalidate the session')
    assert(unexpectedHostHashes.size === 0, 'browser attempted a non-loopback origin')

    result = {
      status: 'PASS',
      ready_commit: readyBody.commit,
      task_count: 2,
      note_count: 1,
      service_worker_controlled: true,
      outbound_requests: 0,
      context_closed: false,
      fixture_ids: {
        public_task: JSON.parse(publicTask.text).id,
        private_task: JSON.parse(privateTask.text).id,
        note: JSON.parse(note.text).id,
      },
    }
  } finally {
    if (context) await context.close()
    if (browser) await browser.close()
    await new Promise((resolve) => proxy.close(resolve))
  }
  assert(result, 'browser result missing')
  result.context_closed = true
  console.log(JSON.stringify(result))
}

main().catch(() => {
  console.error(
    JSON.stringify({
      browser: 'FAIL',
      step,
      unexpected_host_sha256: [...unexpectedHostHashes].sort(),
    }),
  )
  process.exitCode = 20
})
