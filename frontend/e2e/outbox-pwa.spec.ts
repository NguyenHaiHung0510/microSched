import { createHash } from 'node:crypto'
import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import {
  RUN_ID,
  apiTask,
  attachApiCounter,
  capture,
  cleanupSyntheticTasks,
  createTask,
  createOnlineTaskAndReadResponse,
  installPrebootFault,
  readOutbox,
  readPrebootFault,
  record,
  observeOutboxInFinally,
  signInSynthetic,
  waitForQueueEmpty,
  waitForServiceWorker,
  apiCollectionHasId,
  normalizeApiErrorResponse,
  readOutboxRawByteReceipts,
} from './helpers/outbox-pwa'

test.setTimeout(90_000)

test('J1 production PWA reloads public cache offline and retains an offline-created task UUID', async ({ page }) => {
  const ids: string[] = []
  const api = attachApiCounter(page.context())
  const servedAssetHashes: Array<{ filename: string; sha256: string; status: number }> = []
  const pendingAssetHashes: Promise<void>[] = []
  const onAssetResponse = (response: import('@playwright/test').Response) => {
    const url = new URL(response.url())
    const filename = path.posix.basename(url.pathname)
    if (url.pathname === '/' || filename === 'index.html' || (url.pathname.startsWith('/assets/') && filename.endsWith('.js'))) {
      pendingAssetHashes.push((async () => {
        try {
          const body = await response.body()
          servedAssetHashes.push({ filename: url.pathname === '/' ? 'index.html' : filename, sha256: createHash('sha256').update(body).digest('hex'), status: response.status() })
        } catch {
          servedAssetHashes.push({ filename: url.pathname === '/' ? 'index.html' : filename, sha256: 'body-unavailable', status: response.status() })
        }
      })())
    }
  }
  page.on('response', onAssetResponse)
  const diagnostic = async (phase: string) => {
    const runtime = await page.evaluate(() => {
      const live = document.querySelector('[data-testid="app-live-status"]')
      const banner = [...document.querySelectorAll('[role="status"]')]
        .map((node) => ({ state: node.getAttribute('data-state'), text: (node.textContent ?? '').trim() }))
        .filter(({ text }) => /ngoại tuyến|không kết nối|cập nhật bị gián đoạn/i.test(text))
      const active = navigator.serviceWorker?.controller
      return {
        navigatorOnLine: navigator.onLine,
        visibilityState: document.visibilityState,
        appLiveState: live?.getAttribute('data-state') ?? null,
        appLiveText: (live?.textContent ?? '').trim(),
        relevantStatusBanners: banner,
        scriptFilenames: [...document.scripts].map((script) => {
          try { return new URL(script.src).pathname.split('/').pop() ?? '' } catch { return '' }
        }).filter(Boolean),
        serviceWorkerControlled: Boolean(active),
        serviceWorkerScriptFilename: active ? new URL(active.scriptURL).pathname.split('/').pop() ?? null : null,
        serviceWorkerState: active?.state ?? null,
      }
    })
    const receiptRoot = process.env.QA017_RECEIPT_DIR ?? '../output/outbox-pwa'
    const buildSha = process.env.QA017_BUILD_SHA
    if (!buildSha) throw new Error('QA017_BUILD_SHA is not set by the exact-head Playwright config')
    const artifactDir = path.join(receiptRoot, 'artifacts', 'builds', buildSha, 'dist')
    const index = await readFile(path.join(artifactDir, 'index.html'))
    const jsFiles = (index.toString('utf8').match(/(?:src|href)="([^"]+\.js)"/g) ?? [])
      .map((match) => match.match(/"([^"]+\.js)"/)?.[1])
      .filter((value): value is string => Boolean(value))
    const frozenArtifactHashes = [{ filename: 'index.html', sha256: createHash('sha256').update(index).digest('hex') }]
    for (const file of jsFiles) {
      const filename = path.posix.basename(file)
      const body = await readFile(path.join(artifactDir, file.replace(/^\//, '').replaceAll('/', path.sep)))
      frozenArtifactHashes.push({ filename, sha256: createHash('sha256').update(body).digest('hex') })
    }
    const sw = await readFile(path.join(artifactDir, 'sw.js'))
    frozenArtifactHashes.push({ filename: 'sw.js', sha256: createHash('sha256').update(sw).digest('hex') })
    await Promise.allSettled(pendingAssetHashes)
    await record('J1-offline-runtime-diagnostic', { phase, ...runtime, servedAssetHashes: [...servedAssetHashes], frozenArtifactHashes })
  }
  try {
    await signInSynthetic(page)
    const publicTitle = `${RUN_ID}_J1_PUBLIC_CACHE`
    await createTask(page, publicTitle)
    const id = await page.getByTestId('task-card').filter({ hasText: publicTitle }).getAttribute('data-task-id')
    if (id) ids.push(id)
    expect(id).toMatch(/^[0-9a-f-]{36}$/i)
    await expect.poll(async () => (await readOutbox(page)).filter((row) => row.entity_id === id).length).toBe(0)
    const onlineQueue = await readOutbox(page)
    await record('J1-online-seed-api-and-queue', {
      entityId: id,
      apiRequestCounts: Object.fromEntries(api.counts),
      apiResponseCounts: Object.fromEntries(api.statuses),
      outboxRowCount: onlineQueue.length,
      outboxRows: onlineQueue.map(({ operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length }) => ({ operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length })),
    })
    const sw = await waitForServiceWorker(page)
    await page.context().setOffline(true)
    await diagnostic('immediately-after-context-offline-before-reload').catch((error) => record('J1-offline-runtime-diagnostic-error', { phase: 'immediately-after-context-offline-before-reload', message: error instanceof Error ? error.message : String(error) }))
    await page.reload({ waitUntil: 'domcontentloaded' })
    await diagnostic('after-offline-reload-before-live-state-assertion').catch((error) => record('J1-offline-runtime-diagnostic-error', { phase: 'after-offline-reload-before-live-state-assertion', message: error instanceof Error ? error.message : String(error) }))
    await expect(page.getByTestId('app-live-status')).toHaveAttribute('data-state', 'offline')
    await expect(page.getByTestId('task-title').filter({ hasText: publicTitle })).toBeVisible()
    await expect(page.getByRole('status').filter({ hasText: 'Đang ngoại tuyến' })).toBeVisible()
    await expect(page.getByText('Không kết nối được API')).toHaveCount(0)
    const offlineTitle = `${RUN_ID}_J1_OFFLINE_CREATE`
    await createTask(page, offlineTitle)
    const row = (await readOutbox(page)).find((candidate) => candidate.operation_kind === 'task.create' && candidate.entity_id)
    expect(row).toBeTruthy()
    expect(['pending', 'outcome_unknown']).toContain(row?.state)
    expect(row?.entity_id).toMatch(/^[0-9a-f-]{36}$/i)
    ids.push(row!.entity_id!)
    await expect(page.getByTestId('task-card').filter({ hasText: offlineTitle })).toBeVisible()
    await expect(page.getByTestId('task-card').filter({ hasText: offlineTitle }).getByTestId('outbox-entity-state').filter({ hasText: 'Đang chờ gửi' })).toHaveCount(0)
    await expect(page.getByTestId('outbox-indicator')).toHaveCount(1)
    await expect(page.getByTestId('outbox-indicator')).toContainText('1 đang chờ gửi')
    await capture(page, 'J1-offline-shell-and-pending-task')
    await record('J1-pass', { serviceWorker: sw, publicCanary: publicTitle, queuedEntityId: row!.entity_id, state: row!.state, attempts: row!.attempts, apiRequestCounts: Object.fromEntries(api.counts), apiResponseCounts: Object.fromEntries(api.statuses) })
  } finally {
    await diagnostic('finally-at-J1-failure-or-completion').catch((error) => record('J1-offline-runtime-diagnostic-error', { message: error instanceof Error ? error.message : String(error) }))
    page.off('response', onAssetResponse)
    api.close()
    await observeOutboxInFinally(page, 'J1', { requests: Object.fromEntries(api.counts), responses: Object.fromEntries(api.statuses) })
    if (ids.length) await cleanupSyntheticTasks(page, ids)
  }
})

test('J2 offline task, dependent checklist create and tick survive reload then flush to API', async ({ page }) => {
  const ids: string[] = []
  try {
    await signInSynthetic(page)
    const seed = `${RUN_ID}_J2_PUBLIC_CACHE`
    await createTask(page, seed)
    const seedId = await page.getByTestId('task-card').filter({ hasText: seed }).getAttribute('data-task-id')
    if (seedId) ids.push(seedId)
    expect(seedId).toMatch(/^[0-9a-f-]{36}$/i)
    await waitForQueueEmpty(page, [seedId!])
    const seedApi = await apiTask(page, seedId!)
    expect(seedApi.status).toBe(200)
    expect(seedApi.body?.id).toBe(seedId)
    const seedQueue = await readOutbox(page)
    await record('J2-confirmed-online-seed-before-offline', {
      entityId: seedId,
      apiStatus: seedApi.status,
      apiEntityId: seedApi.body?.id,
      outboxRowCount: seedQueue.length,
      outboxRows: seedQueue.map(({ operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length }) => ({ operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length })),
    })
    const sw = await waitForServiceWorker(page)
    await page.context().setOffline(true)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('app-live-status')).toHaveAttribute('data-state', 'offline')
    await expect(page.getByTestId('task-title').filter({ hasText: seed })).toBeVisible()

    const title = `${RUN_ID}_J2_OFFLINE_PARENT`
    const taskTitle = await createTask(page, title)
    await taskTitle.click()
    const childText = `${RUN_ID}_J2_CHILD`
    await page.getByTestId('task-detail-dialog').getByTestId('task-item-add-input').fill(childText)
    await page.getByTestId('task-detail-dialog').getByTestId('task-item-add-submit').click()
    const childCheckbox = page.getByTestId('task-detail-dialog').getByRole('checkbox', { name: `Đánh dấu ${childText} hoàn thành` })
    await expect(childCheckbox).toBeVisible()
    await childCheckbox.click()
    await expect(childCheckbox).toHaveAttribute('data-state', 'checked')
    const taskCard = page.getByTestId('task-card').filter({ hasText: title })
    const id = await taskCard.getAttribute('data-task-id')
    expect(id).toMatch(/^[0-9a-f-]{36}$/i)
    ids.push(id!)
    const queued = await readOutbox(page)
    expect(queued.map((row) => row.operation_kind)).toEqual(['task.create', 'task_item.create', 'task_item.update'])
    expect(queued[1].parent_id).toBe(id)
    expect(queued[2].parent_id).toBe(id)
    await expect(page.getByTestId('task-card').filter({ hasText: title })).toBeVisible()
    await expect(page.getByTestId('task-card').filter({ hasText: title }).getByTestId('outbox-entity-state').filter({ hasText: 'Đang chờ gửi' })).toHaveCount(0)
    await expect(page.getByTestId('outbox-indicator')).toHaveCount(1)
    await expect(page.getByTestId('outbox-indicator')).toContainText('3 đang chờ gửi')
    const beforeReload = queued.map(({ operation_id, operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length }) => ({ operation_id, operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length }))
    await capture(page, 'J2-before-pending-state-reload')
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('task-title').filter({ hasText: title })).toBeVisible()
    await expect(page.getByTestId('task-card').filter({ hasText: title }).getByRole('checkbox', { name: `Đánh dấu ${childText} hoàn thành` })).toHaveAttribute('data-state', 'checked')
    await expect(page.getByTestId('outbox-indicator')).toHaveCount(1)
    await expect(page.getByTestId('outbox-indicator')).toContainText('3 đang chờ gửi')
    const afterReloadRows = await readOutbox(page)
    const afterReload = afterReloadRows.map(({ operation_id, operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length }) => ({ operation_id, operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length }))
    expect(afterReload).toEqual(beforeReload)
    await capture(page, 'J2-after-offline-reload-pending-child-tick')
    await record('J2-offline-state-survived-reload', { serviceWorker: sw, taskId: id, beforeReload, afterReload })

    await page.context().setOffline(false)
    await expect.poll(async () => (await readOutbox(page)).filter((row) => row.entity_id === id || row.parent_id === id).length).toBe(0)
    const server = await apiTask(page, id!)
    expect(server.status).toBe(200)
    expect(server.body?.id).toBe(id)
    const itemsResponse = await page.evaluate(async (taskId) => {
      const response = await fetch(`/api/tasks/${taskId}/items`, { credentials: 'include' })
      return { status: response.status, items: response.ok ? await response.json() : [] }
    }, id!) as { status: number; items: Array<{ id: string; content: string; is_completed: boolean }> }
    expect(itemsResponse.status).toBe(200)
    expect(itemsResponse.items).toHaveLength(1)
    expect(itemsResponse.items[0]).toMatchObject({ content: childText, is_completed: true })
    await expect(page.getByTestId('outbox-indicator')).toHaveCount(0)
    await capture(page, 'J2-online-flushed-server-task-and-child')
    await record('J2-pass', { taskId: id, apiTaskStatus: server.status, exactTaskIdCount: server.body?.id === id ? 1 : 0, itemsStatus: itemsResponse.status, apiItems: itemsResponse.items, pendingForTask: 0 })
  } finally {
    await observeOutboxInFinally(page, 'J2')
    await cleanupSyntheticTasks(page, ids)
  }
})

test('J3 two pages sharing one context send one queued public command under Web Lock', async ({ context, page }) => {
  const ids: string[] = []
  const api = attachApiCounter(context)
  let second: import('@playwright/test').Page | undefined
  let j3Passed = false
  try {
    await signInSynthetic(page)
    const seed = `${RUN_ID}_J3_PUBLIC_CACHE`
    await createTask(page, seed)
    const seedId = await page.getByTestId('task-card').filter({ hasText: seed }).getAttribute('data-task-id')
    if (seedId) ids.push(seedId)
    expect(seedId).toMatch(/^[0-9a-f-]{36}$/i)
    await waitForQueueEmpty(page, [seedId!])
    const seedApi = await apiTask(page, seedId!)
    expect(seedApi.status).toBe(200)
    expect(seedApi.body?.id).toBe(seedId)
    const seedQueue = await readOutbox(page)
    await record('J3-confirmed-online-seed-before-offline', {
      entityId: seedId,
      apiStatus: seedApi.status,
      apiEntityId: seedApi.body?.id,
      outboxRowCount: seedQueue.length,
      outboxRows: seedQueue.map(({ operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length }) => ({ operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length })),
    })
    await waitForServiceWorker(page)
    await context.setOffline(true)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('app-live-status')).toHaveAttribute('data-state', 'offline')
    second = await context.newPage()
    await second.goto('/', { waitUntil: 'domcontentloaded' })
    await expect(second.getByTestId('quick-add-input')).toBeVisible()
    await expect(second.getByTestId('app-live-status')).toHaveAttribute('data-state', 'offline')
    const title = `${RUN_ID}_J3_ONE_COMMAND`
    await createTask(page, title)
    const taskId = await page.getByTestId('task-card').filter({ hasText: title }).getAttribute('data-task-id')
    expect(taskId).toMatch(/^[0-9a-f-]{36}$/i)
    ids.push(taskId!)
    const queued = (await readOutbox(page)).find((row) => row.operation_kind === 'task.create' && row.entity_id === taskId)
    expect(queued).toBeTruthy()
    expect(['pending', 'outcome_unknown']).toContain(queued?.state)
    expect(queued?.attempts).toBeGreaterThanOrEqual(0)
    expect(queued?.payload_sha256).toMatch(/^[0-9a-f]{64}$/i)
    expect(queued?.payload_byte_length).toBeGreaterThan(0)
    let matchingPosts = 0
    const matchingPostStatuses: number[] = []
    let reconnectStarted = false
    const countMatchingPost = (request: import('@playwright/test').Request) => {
      if (request.method() !== 'POST' || new URL(request.url()).pathname !== '/api/tasks') return
      try { if (reconnectStarted && (request.postDataJSON() as { id?: string }).id === taskId) matchingPosts += 1 } catch { /* Ignore non-JSON requests. */ }
    }
    const countMatchingPostResponse = (response: import('@playwright/test').Response) => {
      const request = response.request()
      if (!reconnectStarted || request.method() !== 'POST' || new URL(request.url()).pathname !== '/api/tasks') return
      try { if ((request.postDataJSON() as { id?: string }).id === taskId) matchingPostStatuses.push(response.status()) } catch { /* Ignore non-JSON requests. */ }
    }
    context.on('request', countMatchingPost)
    context.on('response', countMatchingPostResponse)
    await expect(page.getByTestId('task-card').filter({ hasText: title })).toBeVisible()
    await expect(page.getByTestId('task-card').filter({ hasText: title }).getByTestId('outbox-entity-state').filter({ hasText: 'Đang chờ gửi' })).toHaveCount(0)
    await expect(page.getByTestId('outbox-indicator')).toHaveCount(1)
    await expect(page.getByTestId('outbox-indicator')).toContainText('1 đang chờ gửi')
    await expect.poll(async () => (await readOutbox(second!)).filter((row) => row.entity_id === taskId).length).toBe(1)
    await expect(second.getByTestId('task-title').filter({ hasText: title })).toBeVisible()
    await expect(second.getByTestId('task-card').filter({ hasText: title }).getByTestId('outbox-entity-state').filter({ hasText: 'Đang chờ gửi' })).toHaveCount(0)
    await expect(second.getByTestId('outbox-indicator')).toHaveCount(1)
    await expect(second.getByTestId('outbox-indicator')).toContainText('1 đang chờ gửi')
    await capture(page, 'J3-two-pages-shared-offline-queue')

    const beforeReconnectRow = (await readOutbox(page)).find((row) => row.entity_id === taskId)
    expect(beforeReconnectRow).toBeTruthy()
    expect(beforeReconnectRow?.payload_sha256).toBe(queued?.payload_sha256)
    expect(beforeReconnectRow?.payload_byte_length).toBe(queued?.payload_byte_length)
    const postsBeforeReconnect = api.counts.get('POST /api/tasks') ?? 0
    await record('J3-queued-command-before-reconnect', {
      entityId: taskId,
      state: beforeReconnectRow?.state,
      attempts: beforeReconnectRow?.attempts,
      payload_sha256: beforeReconnectRow?.payload_sha256,
      payload_byte_length: beforeReconnectRow?.payload_byte_length,
      totalTaskPostRequestsBeforeReconnect: postsBeforeReconnect,
    })
    reconnectStarted = true
    await context.setOffline(false)
    await waitForQueueEmpty(page, [taskId!])
    await expect.poll(() => matchingPosts).toBe(1)
    await expect.poll(() => matchingPostStatuses.length).toBe(1)
    await expect.poll(() => api.counts.get('POST /api/tasks') ?? 0).toBe(postsBeforeReconnect + 1)
    expect([200, 201]).toContain(matchingPostStatuses[0])
    const server = await apiTask(page, taskId!)
    expect(server.status).toBe(200)
    expect(server.body?.id).toBe(taskId)
    await expect(page.getByTestId('outbox-indicator')).toHaveCount(0)
    await expect(second.getByTestId('outbox-indicator')).toHaveCount(0)
    await record('J3-pass', { taskId, postRequestCountForQueuedUuidAfterReconnect: matchingPosts, postResponseStatusesAfterReconnect: matchingPostStatuses, allPostRequests: api.counts.get('POST /api/tasks') ?? 0, preReconnectPostBaseline: postsBeforeReconnect, apiGetStatus: server.status, apiExactIdCount: server.body?.id === taskId ? 1 : 0, pageCount: context.pages().length, webLocksAvailable: await page.evaluate(() => Boolean(navigator.locks)), attemptsBeforeReconnect: beforeReconnectRow?.attempts, payloadSha256: beforeReconnectRow?.payload_sha256, payloadByteLength: beforeReconnectRow?.payload_byte_length })
    j3Passed = true
    context.off('request', countMatchingPost)
    context.off('response', countMatchingPostResponse)
  } finally {
    api.close()
    if (!j3Passed && second) {
      const diagnostic = await second.evaluate(() => ({
        href: location.href,
        origin: location.origin,
        visibilityState: document.visibilityState,
        serviceWorkerSupported: 'serviceWorker' in navigator,
        serviceWorkerControlled: Boolean(navigator.serviceWorker?.controller),
        serviceWorkerScript: navigator.serviceWorker?.controller?.scriptURL ?? null,
        webLocksAvailable: Boolean(navigator.locks),
        broadcastChannelAvailable: typeof BroadcastChannel === 'function',
        taskTabCount: document.querySelectorAll('[role="tab"]').length,
        selectedTaskTab: [...document.querySelectorAll('[role="tab"]')].some((tab) => tab.getAttribute('aria-selected') === 'true' && /task/i.test(tab.textContent ?? '')),
        tabpanelCount: document.querySelectorAll('[role="tabpanel"]').length,
        allIndicatorCount: document.querySelectorAll('[data-testid="outbox-indicator"]').length,
        indicatorTexts: [...document.querySelectorAll('[data-testid="outbox-indicator"]')].map((node) => node.textContent?.trim() ?? ''),
        quickAddVisible: Boolean(document.querySelector('[data-testid="quick-add-input"]')),
        offlineBannerTexts: [...document.querySelectorAll('[role="status"]')].map((node) => node.textContent?.trim() ?? '').filter((text) => text.includes('ngoại tuyến')),
        signedInControlVisible: [...document.querySelectorAll('button')].some((button) => /đăng xuất/i.test(button.textContent ?? '')),
        taskErrorTexts: [...document.querySelectorAll('[role="alert"]')].map((node) => node.textContent?.trim() ?? ''),
      }))
      const secondPageRows = await readOutbox(second).catch((error) => ({ error: error instanceof Error ? error.message : String(error) }))
      await record('J3-second-page-failure-diagnostic', {
        ...diagnostic,
        secondPageOutboxRowCount: Array.isArray(secondPageRows) ? secondPageRows.length : null,
        secondPageOutboxRows: Array.isArray(secondPageRows) ? secondPageRows : null,
        secondPageOutboxReadError: !Array.isArray(secondPageRows) ? secondPageRows.error : null,
        primaryPageApiRequestCounts: Object.fromEntries(api.counts),
        primaryPageApiResponseCounts: Object.fromEntries(api.statuses),
        note: 'Read-only diagnostic; no IndexedDB writes, cleanup, or synthetic event dispatch.',
      })
      await capture(second, 'J3-second-page-failure-diagnostic')
    }
    await observeOutboxInFinally(page, 'J3')
    if (ids.length) await cleanupSyntheticTasks(page, ids)
    await second?.close()
  }
})

test('J4 real API commits create, lost browser response replays same UUID with 200 and one exact row', async ({ page }) => {
  const ids: string[] = []
  let firstCommitStatus: number | null = null
  const postStatuses: number[] = []
  const postIds: string[] = []
  const postBodies: string[] = []
  let capturedId: string | null = null
  const onCreateRequest = (request: import('@playwright/test').Request) => {
    if (request.method() !== 'POST' || new URL(request.url()).pathname !== '/api/tasks') return
    try {
      postIds.push(String((request.postDataJSON() as { id?: string }).id ?? ''))
      postBodies.push(request.postData() ?? '')
    } catch { /* Ignore non-JSON requests. */ }
  }
  try {
    await signInSynthetic(page)
    const seed = `${RUN_ID}_J4_PUBLIC_CACHE`
    await createTask(page, seed)
    const seedId = await page.getByTestId('task-card').filter({ hasText: seed }).getAttribute('data-task-id')
    if (seedId) ids.push(seedId)
    expect(seedId).toMatch(/^[0-9a-f-]{36}$/i)
    await waitForQueueEmpty(page, [seedId!])
    const seedApi = await apiTask(page, seedId!)
    expect(seedApi.status).toBe(200)
    expect(seedApi.body?.id).toBe(seedId)
    const seedQueue = await readOutbox(page)
    await record('J4-confirmed-online-seed-before-offline', {
      entityId: seedId,
      apiStatus: seedApi.status,
      apiEntityId: seedApi.body?.id,
      outboxRowCount: seedQueue.length,
      outboxRows: seedQueue.map(({ operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length }) => ({ operation_kind, entity_id, parent_id, state, attempts, payload_sha256, payload_byte_length })),
    })
    await waitForServiceWorker(page)
    await page.context().route('**/api/tasks', async (route, request) => {
      if (request.method() !== 'POST' || firstCommitStatus !== null) return route.continue()
      const upstream = await route.fetch()
      firstCommitStatus = upstream.status()
      const requestBody = request.postDataJSON() as { id?: string }
      capturedId = requestBody.id ?? null
      if (capturedId) ids.push(capturedId)
      await record('J4-real-api-first-commit-before-browser-abort', { status: firstCommitStatus, entityId: capturedId, transport: 'route.fetch to preview proxy and real API' })
      await upstream.dispose()
      await route.abort('failed')
    })
    page.context().on('request', onCreateRequest)
    const title = `${RUN_ID}_J4_RESPONSE_LOST`
    await page.getByTestId('quick-add-input').fill(title)
    await page.getByTestId('quick-add-submit').click()
    await expect.poll(async () => (await readOutbox(page)).find((row) => row.entity_id === capturedId)?.state).toBe('outcome_unknown')
    const unknown = (await readOutbox(page)).find((row) => row.entity_id === capturedId)
    expect(unknown?.attempts).toBe(1)
    expect(capturedId).toMatch(/^[0-9a-f-]{36}$/i)
    await expect(page.getByTestId('task-title').filter({ hasText: title })).toBeVisible()
    await expect(page.getByTestId('task-card').filter({ hasText: title }).getByTestId('outbox-entity-state').filter({ hasText: 'Đang chờ gửi' })).toHaveCount(0)
    await expect(page.getByTestId('outbox-indicator')).toHaveCount(1)
    await expect(page.getByTestId('outbox-panel')).toHaveCount(0)
    await page.context().unroute('**/api/tasks')
    page.on('response', (response) => {
      const request = response.request()
      if (request.method() === 'POST' && new URL(response.url()).pathname === '/api/tasks') postStatuses.push(response.status())
    })
    await page.context().setOffline(true)
    await page.waitForTimeout(1_200)
    await page.context().setOffline(false)
    await expect.poll(async () => {
      const row = (await readOutbox(page)).find((candidate) => candidate.entity_id === capturedId)
      return row?.attempts ?? 0
    }, { timeout: 20_000, intervals: [100, 250, 500, 1000] }).toBeGreaterThan(1)
    await expect.poll(async () => (await readOutbox(page)).some((row) => row.entity_id === capturedId)).toBe(false)
    const server = await apiTask(page, capturedId!)
    expect(server.status).toBe(200)
    expect(server.body?.id).toBe(capturedId)
    expect(server.body?.title).toBe(title)
    expect(firstCommitStatus).toBe(201)
    expect(postStatuses).toEqual([200])
    expect(postIds).toEqual([capturedId, capturedId])
    expect(postBodies).toHaveLength(2)
    expect(postBodies[1]).toBe(postBodies[0])
    await capture(page, 'J4-idempotent-replay-confirmed')
    await record('J4-pass', { entityId: capturedId, firstCommitStatus, replayStatuses: postStatuses, replayRequestIds: postIds, replaySameUuid: postIds.length === 2 && postIds.every((id) => id === capturedId), sameSerializedBody: postBodies.length === 2 && postBodies[0] === postBodies[1], payloadSha256: createHash('sha256').update(postBodies[0] ?? '').digest('hex'), payloadByteLength: Buffer.byteLength(postBodies[0] ?? ''), requestCount: postIds.length, finalOutboxRowCountForId: 0, exactIdGetStatus: server.status, exactIdRowCount: server.body?.id === capturedId ? 1 : 0, attemptsBeforeReplay: unknown?.attempts, attemptsAfterReplay: (await readOutbox(page)).filter((row) => row.entity_id === capturedId).length })
  } finally {
    await page.context().unrouteAll({ behavior: 'wait' }).catch(() => undefined)
    page.context().off('request', onCreateRequest)
    await observeOutboxInFinally(page, 'J4')
    await cleanupSyntheticTasks(page, ids)
  }
})

test('N1 blocked preboot IndexedDB open still allows an online task write without a false queue receipt', async ({ page }) => {
  const ids: string[] = []
  const api = attachApiCounter(page.context())
  await installPrebootFault(page, 'indexeddb-open-blocked')
  const title = `${RUN_ID}_N1_IDB_OPEN_BLOCKED`
  try {
    await signInSynthetic(page)
    const faultBeforeWrite = await readPrebootFault(page)
    expect(faultBeforeWrite?.kind).toBe('indexeddb-open-blocked')
    expect(faultBeforeWrite?.openAttempts).toBeGreaterThan(0)
    expect(api.counts.get('POST /api/tasks') ?? 0).toBe(0)
    await expect(page.getByRole('status').filter({ hasText: 'Lưu ngoại tuyến chưa khả dụng trên thiết bị này.' })).toBeVisible()

    const { response, id } = await createOnlineTaskAndReadResponse(page, title, ids)
    expect(response?.status()).toBe(201)
    expect(id).toMatch(/^[0-9a-f-]{36}$/i)
    await expect(page.getByTestId('task-title').filter({ hasText: title })).toBeVisible()
    const server = await apiTask(page, id!)
    expect(server.status).toBe(200)
    expect(server.body).toMatchObject({ id, title })
    expect(api.counts.get('POST /api/tasks') ?? 0).toBe(1)
    await expect(page.getByTestId('outbox-indicator')).toHaveCount(0)
    await expect(page.getByTestId('task-card').filter({ hasText: title }).getByTestId('outbox-entity-state')).toHaveCount(0)
    await capture(page, `${RUN_ID}-N1-open-blocked-online-api-task`)
    await record('N1-pass', { fault: faultBeforeWrite, taskId: id, taskPostCount: 1, taskPostStatus: response?.status() ?? null, exactApiGetStatus: server.status, exactApiRow: server.body?.id === id, visibleUnavailableWarning: true, falseQueueUi: false })
  } finally {
    const queue = await readOutbox(page).then((rows) => ({ available: true, rowCount: rows.length })).catch(() => ({ available: false, rowCount: null }))
    const fault = await readPrebootFault(page).catch(() => null)
    await record('N1-final-state', { fault, queue, taskPostCount: api.counts.get('POST /api/tasks') ?? 0, taskPostStatuses: Object.fromEntries(api.statuses) })
    await capture(page, `${RUN_ID}-N1-open-blocked-final`).catch(() => undefined)
    api.close()
    if (ids.length) await cleanupSyntheticTasks(page, ids)
  }
})

test('N2 first outbox object-store write quota failure falls back to the real online task API', async ({ page }) => {
  const ids: string[] = []
  const api = attachApiCounter(page.context())
  await installPrebootFault(page, 'outbox-first-write-quota')
  const title = `${RUN_ID}_N2_OUTBOX_QUOTA`
  try {
    await signInSynthetic(page)
    const faultBeforeWrite = await readPrebootFault(page)
    expect(faultBeforeWrite?.kind).toBe('outbox-first-write-quota')
    expect(faultBeforeWrite?.injectedFailures).toBe(0)
    expect(api.counts.get('POST /api/tasks') ?? 0).toBe(0)

    const { response, id } = await createOnlineTaskAndReadResponse(page, title, ids)
    expect(faultBeforeWrite?.injectedFailures).toBe(0)
    const faultAfterWrite = await readPrebootFault(page)
    expect(faultAfterWrite?.outboxWriteAttempts).toBe(1)
    expect(faultAfterWrite?.injectedFailures).toBe(1)
    expect(response?.status()).toBe(201)
    expect(id).toMatch(/^[0-9a-f-]{36}$/i)
    await expect(page.getByTestId('task-title').filter({ hasText: title })).toBeVisible()
    const server = await apiTask(page, id!)
    expect(server.status).toBe(200)
    expect(server.body).toMatchObject({ id, title })
    expect(api.counts.get('POST /api/tasks') ?? 0).toBe(1)
    await expect(page.getByRole('status').filter({ hasText: 'Lưu ngoại tuyến chưa khả dụng trên thiết bị này.' })).toBeVisible()
    expect(await readOutbox(page)).toHaveLength(0)
    await expect(page.getByTestId('outbox-indicator')).toHaveCount(0)
    await expect(page.getByTestId('task-card').filter({ hasText: title }).getByTestId('outbox-entity-state')).toHaveCount(0)
    await capture(page, `${RUN_ID}-N2-quota-online-api-task`)
    await record('N2-pass', { fault: faultAfterWrite, taskId: id, taskPostCount: 1, taskPostStatus: response?.status() ?? null, exactApiGetStatus: server.status, exactApiRow: server.body?.id === id, queueRowCount: 0, visibleUnavailableWarning: true, falseQueueUi: false })
  } finally {
    const queue = await readOutbox(page).then((rows) => ({ available: true, rowCount: rows.length, rows: rows.map(({ operation_kind, entity_id, state, attempts, payload_sha256, payload_byte_length }) => ({ operation_kind, entity_id, state, attempts, payload_sha256, payload_byte_length })) })).catch((error) => ({ available: false, error: error instanceof Error ? error.message : String(error) }))
    const fault = await readPrebootFault(page).catch(() => null)
    await record('N2-final-state', { fault, queue, taskPostCount: api.counts.get('POST /api/tasks') ?? 0, taskPostStatuses: Object.fromEntries(api.statuses) })
    await capture(page, `${RUN_ID}-N2-quota-final`).catch(() => undefined)
    api.close()
    if (ids.length) await cleanupSyntheticTasks(page, ids)
  }
})

test('N3 missing Web Locks retains durable task command without sending it', async ({ page }) => {
  const api = attachApiCounter(page.context())
  await installPrebootFault(page, 'web-locks-absent')
  const title = `${RUN_ID}_N3_WEB_LOCKS_ABSENT`
  let taskId: string | null = null
  try {
    await signInSynthetic(page)
    const faultBeforeWrite = await readPrebootFault(page)
    expect(faultBeforeWrite).toMatchObject({ kind: 'web-locks-absent', locksAvailable: false })
    expect(api.counts.get('POST /api/tasks') ?? 0).toBe(0)

    await createTask(page, title)
    taskId = await page.getByTestId('task-card').filter({ hasText: title }).getAttribute('data-task-id')
    expect(taskId).toMatch(/^[0-9a-f-]{36}$/i)
    await expect(page.getByTestId('outbox-lock-warning')).toContainText('Thay đổi vẫn được lưu trên thiết bị')
    const rows = await readOutbox(page)
    const row = rows.find((candidate) => candidate.entity_id === taskId)
    expect(row).toBeTruthy()
    expect(row).toMatchObject({ operation_kind: 'task.create', state: 'pending', attempts: 0 })
    expect(row?.payload_sha256).toMatch(/^[0-9a-f]{64}$/)
    expect(row?.payload_byte_length).toBeGreaterThan(0)
    await expect(page.getByTestId('outbox-indicator')).toContainText('1 đang chờ gửi')
    expect(api.counts.get('POST /api/tasks') ?? 0).toBe(0)
    const server = await apiTask(page, taskId!)
    expect(server.status).toBe(404)
    await capture(page, `${RUN_ID}-N3-locks-absent-durable-queue`)
    await record('N3-pass', { fault: faultBeforeWrite, taskId, state: row?.state, attempts: row?.attempts, payloadSha256: row?.payload_sha256, payloadByteLength: row?.payload_byte_length, taskPostCount: 0, exactApiGetStatus: server.status, durableRows: rows.length, lockWarningVisible: true })
  } finally {
    const queue = await readOutbox(page).then((rows) => ({ available: true, rowCount: rows.length, rows: rows.map(({ operation_kind, entity_id, state, attempts, payload_sha256, payload_byte_length }) => ({ operation_kind, entity_id, state, attempts, payload_sha256, payload_byte_length })) })).catch((error) => ({ available: false, error: error instanceof Error ? error.message : String(error) }))
    const fault = await readPrebootFault(page).catch(() => null)
    await record('N3-final-state', { fault, taskId, queue, taskPostCount: api.counts.get('POST /api/tasks') ?? 0, taskPostStatuses: Object.fromEntries(api.statuses) })
    await capture(page, `${RUN_ID}-N3-locks-absent-final`).catch(() => undefined)
    api.close()
    // Deliberately retain the unsent row in this disposable isolated browser context; do not clear it to force green.
  }
})

test('N4 quota failure on a later write retains the existing queued command and sends neither task', async ({ page }) => {
  const api = attachApiCounter(page.context())
  await installPrebootFault(page, 'existing-queue-second-write-quota')
  const parentTitle = `${RUN_ID}_N4_EXISTING_QUEUED_PARENT`
  const rejectedTitle = `${RUN_ID}_N4_QUOTA_REJECTED_WRITE`
  let parentId: string | null = null
  let originalRow: Awaited<ReturnType<typeof readOutbox>>[number] | undefined
  try {
    await signInSynthetic(page)
    const faultBeforeWrite = await readPrebootFault(page)
    expect(faultBeforeWrite).toMatchObject({ kind: 'existing-queue-second-write-quota', locksAvailable: false, injectedFailures: 0 })
    expect(api.counts.get('POST /api/tasks') ?? 0).toBe(0)

    await createTask(page, parentTitle)
    parentId = await page.getByTestId('task-card').filter({ hasText: parentTitle }).getAttribute('data-task-id')
    expect(parentId).toMatch(/^[0-9a-f-]{36}$/i)
    const before = await readOutbox(page)
    expect(before).toHaveLength(1)
    originalRow = before[0]
    expect(originalRow).toMatchObject({ operation_kind: 'task.create', entity_id: parentId, state: 'pending', attempts: 0 })
    expect(originalRow.payload_sha256).toMatch(/^[0-9a-f]{64}$/)
    expect(originalRow.payload_byte_length).toBeGreaterThan(0)
    const originalDigest = originalRow.payload_sha256
    const originalLength = originalRow.payload_byte_length
    expect(api.counts.get('POST /api/tasks') ?? 0).toBe(0)

    await page.getByTestId('quick-add-input').fill(rejectedTitle)
    await page.getByTestId('quick-add-submit').click()
    await expect(page.getByTestId('quick-add-error')).toBeVisible()
    await expect(page.getByTestId('quick-add-error')).not.toHaveText('')
    await expect(page.getByTestId('task-title').filter({ hasText: rejectedTitle })).toHaveCount(0)

    const faultAfterWrite = await readPrebootFault(page)
    expect(faultAfterWrite).toMatchObject({ outboxWriteAttempts: 2, injectedFailures: 1, locksAvailable: false })
    const after = await readOutbox(page)
    expect(after).toHaveLength(1)
    expect(after[0]).toMatchObject({
      operation_id: originalRow.operation_id,
      operation_kind: originalRow.operation_kind,
      entity_id: originalRow.entity_id,
      state: originalRow.state,
      attempts: originalRow.attempts,
      payload_sha256: originalDigest,
      payload_byte_length: originalLength,
    })
    expect(api.counts.get('POST /api/tasks') ?? 0).toBe(0)
    const server = await apiTask(page, parentId!)
    expect(server.status).toBe(404)
    await expect(page.getByTestId('outbox-lock-warning')).toContainText('Thay đổi vẫn được lưu trên thiết bị')
    await expect(page.getByTestId('outbox-indicator')).toContainText('1 đang chờ gửi')
    await capture(page, `${RUN_ID}-N4-quota-rejected-existing-row-retained`)
    await record('N4-ready-case-pass', {
      fault: faultAfterWrite,
      existingQueuedTaskId: parentId,
      originalState: originalRow.state,
      originalAttempts: originalRow.attempts,
      originalPayloadSha256: originalDigest,
      originalPayloadByteLength: originalLength,
      retainedRowCount: after.length,
      taskPostCount: 0,
      exactApiGetStatus: server.status,
      rejectedWriteVisible: true,
      noSecondOptimisticTask: true,
      lockWarningVisible: true,
    })
  } finally {
    const queue = await readOutbox(page).then((rows) => ({ available: true, rowCount: rows.length, rows: rows.map(({ operation_id, operation_kind, entity_id, state, attempts, payload_sha256, payload_byte_length }) => ({ operation_id, operation_kind, entity_id, state, attempts, payload_sha256, payload_byte_length })) })).catch((error) => ({ available: false, error: error instanceof Error ? error.message : String(error) }))
    const fault = await readPrebootFault(page).catch(() => null)
    await record('N4-final-state', { fault, existingQueuedTaskId: parentId, queue, taskPostCount: api.counts.get('POST /api/tasks') ?? 0, taskPostStatuses: Object.fromEntries(api.statuses) })
    await capture(page, `${RUN_ID}-N4-final`).catch(() => undefined)
    api.close()
    // Keep the original unsent row and digest intact; no queue clear and no API cleanup.
  }
})

async function openTrackerTab(page: import('@playwright/test').Page) {
  page.setDefaultTimeout(15_000)
  const tabs = page.getByRole('tablist', { name: 'Chọn nội dung' })
  const before = await tabs.ariaSnapshot()
  expect(before).toContain('tab "Theo dõi"')
  const trackerTab = page.getByRole('tab', { name: 'Theo dõi', exact: true })
  await trackerTab.click({ timeout: 15_000 })
  await expect(trackerTab).toHaveAttribute('aria-selected', 'true', { timeout: 15_000 })
  const panelSnapshot = await page.getByRole('tabpanel').ariaSnapshot()
  expect(panelSnapshot).toContain('button "Tracker mới"')
  await expect(page.getByTestId('tracker-create')).toBeVisible({ timeout: 15_000 })
}

async function reselectTrackerAfterOffline(page: import('@playwright/test').Page) {
  await expect(page.getByTestId('app-live-status')).toHaveAttribute('data-state', 'offline', { timeout: 15_000 })
  const tabs = page.getByRole('tablist', { name: 'Chọn nội dung' })
  const before = await tabs.ariaSnapshot()
  expect(before).toContain('tab "Theo dõi"')
  const trackerTab = page.getByRole('tab', { name: 'Theo dõi', exact: true })
  const wasSelected = /tab "Theo dõi" \[selected\]/.test(before)
  if (!wasSelected) await trackerTab.click({ timeout: 15_000 })
  await expect(trackerTab).toHaveAttribute('aria-selected', 'true', { timeout: 15_000 })
  const panelSnapshot = await page.getByRole('tabpanel').ariaSnapshot()
  expect(panelSnapshot).toContain('button "Tracker mới"')
  await expect(page.getByTestId('tracker-create')).toBeVisible({ timeout: 15_000 })
  await record('P-tracker-tab-after-offline-bootstrap', {
    selectedBeforeReselect: wasSelected,
    selectedAfterReselect: await trackerTab.getAttribute('aria-selected'),
    trackerCreateVisible: await page.getByTestId('tracker-create').isVisible(),
  })
}

async function createQueuedTrackerGroup(page: import('@playwright/test').Page, name: string) {
  const panelSnapshot = await page.getByRole('tabpanel').ariaSnapshot()
  const observedActions = ['Nhóm mới', 'Thêm nhóm'].filter((label) => panelSnapshot.includes(`button "${label}"`))
  const createLabel = observedActions.includes('Nhóm mới') ? 'Nhóm mới' : observedActions.includes('Thêm nhóm') ? 'Thêm nhóm' : null
  if (!createLabel) throw new Error(`No group-create control in current Tracker panel snapshot; known actions observed: ${observedActions.join(',') || 'none'}`)
  await record('P-tracker-group-create-control-observed', { label: createLabel, observedActions })
  await page.getByRole('button', { name: createLabel, exact: true }).click({ timeout: 15_000 })
  const dialog = page.getByTestId('group-dialog').first()
  await dialog.getByLabel('Tên nhóm').fill(name, { timeout: 15_000 })
  await dialog.getByRole('button', { name: 'Tạo nhóm' }).click({ timeout: 15_000 })
  await expect(page.getByTestId('tracker-group-title').filter({ hasText: name })).toBeVisible({ timeout: 15_000 })
  await expect.poll(async () =>
    (await readOutboxRawByteReceipts(page)).some((item) => item.operation_kind === 'tracker_group.create'),
    { timeout: 15_000 },
  ).toBe(true)
  return (await readOutboxRawByteReceipts(page)).find((item) => item.operation_kind === 'tracker_group.create')!
}

async function createQueuedTracker(page: import('@playwright/test').Page, groupName: string, name: string, isPrivate = false) {
  await page.getByTestId('tracker-create').click()
  const form = page.getByTestId('tracker-form')
  await form.getByTestId('tracker-name-input').fill(name)
  await form.getByRole('combobox').last().click()
  await page.getByRole('option', { name: groupName, exact: true }).click()
  if (isPrivate) await form.getByRole('checkbox', { name: 'Riêng tư' }).click()
  await form.getByRole('button', { name: 'Tạo tracker' }).click()
  const card = page.getByTestId('tracker-card').filter({ hasText: name })
  await expect(card).toBeVisible()
  return card
}

async function acquireOutboxFlushLock(page: import('@playwright/test').Page) {
  await page.evaluate(() => {
    type LockWindow = Window & { __qa072FlushHeld?: boolean; __qa072ReleaseFlush?: () => void }
    const target = window as LockWindow
    void navigator.locks.request('microsched-outbox-flush', async () => {
      target.__qa072FlushHeld = true
      await new Promise<void>((resolve) => { target.__qa072ReleaseFlush = resolve })
    })
  })
  await expect.poll(() => page.evaluate(() => (window as Window & { __qa072FlushHeld?: boolean }).__qa072FlushHeld === true)).toBe(true)
}

async function releaseOutboxFlushLock(page: import('@playwright/test').Page) {
  await page.evaluate(() => (window as Window & { __qa072ReleaseFlush?: () => void }).__qa072ReleaseFlush?.())
}

async function waitForExistingPrivateUnlock(page: import('@playwright/test').Page) {
  page.setDefaultTimeout(15_000)
  const badge = page.getByTestId('private-badge')
  if (!(await badge.textContent())?.includes('Riêng tư · còn')) {
    await page.getByTestId('private-unlock-open').click({ timeout: 15_000 })
    await page.getByTestId('private-pin-input').waitFor({ state: 'visible', timeout: 15_000 })
    // A human authorized operator enters the already-configured synthetic PIN in the headed UI.
    // The test never reads, supplies, stores, or reports the PIN.
    await expect(badge).toContainText('Riêng tư · còn', { timeout: 15_000 })
  }
  await expect(badge).toContainText('Riêng tư · còn')
}

async function createQueuedEntry(page: import('@playwright/test').Page, trackerName: string) {
  const card = page.getByTestId('tracker-card').filter({ hasText: trackerName })
  await card.getByTestId('tracker-button').click()
  await expect.poll(async () =>
    (await readOutboxRawByteReceipts(page)).some((item) => item.operation_kind === 'entry.create'),
  ).toBe(true)
  return (await readOutboxRawByteReceipts(page)).find((item) => item.operation_kind === 'entry.create')!
}

test('P1 real API flush orders a public tracker group, tracker and entry dependency chain', async ({ page }) => {
  page.setDefaultTimeout(15_000)
  const api = attachApiCounter(page.context())
  const ids: { group: string; tracker: string; entry: string; operationIds: number[] } = {
    group: '', tracker: '', entry: '', operationIds: [],
  }
  let drained = false
  const responseOrder: string[] = []
  const onResponse = (response: import('@playwright/test').Response) => {
    const url = new URL(response.url())
    if (response.request().method() === 'POST' && [
      '/api/tracker/groups', '/api/tracker/trackers', '/api/tracker/entries',
    ].includes(url.pathname)) responseOrder.push(`${url.pathname} ${response.status()}`)
  }
  page.context().on('response', onResponse)
  const groupName = `${RUN_ID}_P1_GROUP`
  const trackerName = `${RUN_ID}_P1_TRACKER`
  try {
    await signInSynthetic(page, 15_000)
    await openTrackerTab(page)
    await waitForServiceWorker(page)
    await page.context().setOffline(true)
    await expect.poll(() => page.evaluate(() => navigator.onLine)).toBe(false)
    await reselectTrackerAfterOffline(page)

    const group = await createQueuedTrackerGroup(page, groupName)
    ids.group = group.entity_id!
    ids.operationIds.push(group.operation_id)
    const trackerCard = await createQueuedTracker(page, groupName, trackerName)
    ids.tracker = await trackerCard.getAttribute('data-tracker-id') ?? ''
    const tracker = (await readOutboxRawByteReceipts(page)).find((item) => item.operation_kind === 'tracker.create')!
    ids.operationIds.push(tracker.operation_id)
    const entry = await createQueuedEntry(page, trackerName)
    ids.entry = entry.entity_id!
    ids.operationIds.push(entry.operation_id)

    const beforeReconnect = await readOutboxRawByteReceipts(page)
    expect(beforeReconnect).toHaveLength(3)
    expect(beforeReconnect.map((row) => row.operation_kind)).toEqual([
      'tracker_group.create', 'tracker.create', 'entry.create',
    ])
    expect(beforeReconnect.map((row) => row.dependency_operation_id)).toEqual([
      null, group.operation_id, tracker.operation_id,
    ])
    expect(beforeReconnect.every((row) => !row.requires_private)).toBe(true)
    for (const row of beforeReconnect) {
      expect(row.payload_sha256).toMatch(/^[0-9a-f]{64}$/)
      expect(row.payload_sha256).toBe(row.stored_payload_sha256)
      expect(row.payload_byte_length).toBe(row.stored_payload_byte_length)
      expect(row.payload_byte_length).toBeGreaterThan(0)
    }
    await record('P1-tracker-chain-before-reconnect', {
      ids, rows: beforeReconnect.map(({ operation_id, operation_kind, entity_id, parent_id, dependency_operation_id, requires_private, state, attempts, payload_sha256, payload_byte_length }) =>
        ({ operation_id, operation_kind, entity_id, parent_id, dependency_operation_id, requires_private, state, attempts, payload_sha256, payload_byte_length })),
    })

    await page.context().setOffline(false)
    await waitForQueueEmpty(page, [ids.group, ids.tracker, ids.entry], 15_000)
    drained = true
    expect(responseOrder).toEqual([
      '/api/tracker/groups 201', '/api/tracker/trackers 201', '/api/tracker/entries 201',
    ])
    expect(await apiCollectionHasId(page, '/api/tracker/groups', ids.group)).toEqual({ status: 200, present: true })
    expect(await apiCollectionHasId(page, '/api/tracker/trackers', ids.tracker)).toEqual({ status: 200, present: true })
    expect(await apiCollectionHasId(page, '/api/tracker/entries', ids.entry)).toEqual({ status: 200, present: true })
    await capture(page, `${RUN_ID}-P1-public-tracker-chain-flushed`)
    await record('P1-tracker-chain-pass', { ids, responseOrder, queueCountAfterDrain: (await readOutboxRawByteReceipts(page)).length })
  } finally {
    const cleanup: Array<{ path: string; status: number }> = []
    if (drained) for (const [kind, id] of [['entry', ids.entry], ['tracker', ids.tracker], ['group', ids.group]] as const) {
      if (!id) continue
      const path = kind === 'entry' ? `/api/tracker/entries/${id}` : kind === 'tracker' ? `/api/tracker/trackers/${id}` : `/api/tracker/groups/${id}`
      const status = await page.evaluate(async (target) => (await fetch(target, { method: 'DELETE', credentials: 'include' })).status, path).catch(() => 0)
      cleanup.push({ path: `/api/tracker/${kind === 'group' ? 'groups' : kind === 'tracker' ? 'trackers' : 'entries'}/:owned-id`, status })
    }
    const finalRows = await readOutboxRawByteReceipts(page).catch(() => [])
    await record('P1-final-outbox-state', { rows: finalRows })
    await record('P1-exact-synthetic-tracker-cleanup', { cleanup, skippedBecauseNotDrained: !drained })
    page.context().off('response', onResponse)
    api.close()
  }
})

test('P3 real 422 parent suppresses tracker descendants, public task proceeds and discard rolls back only the failed tree', async ({ page }) => {
  page.setDefaultTimeout(15_000)
  const api = attachApiCounter(page.context())
  const ids = { group: '', tracker: '', entry: '', task: '' }
  const responseOrder: string[] = []
  let groupRejection: { status: number; code: string | null } | null = null
  const onResponse = (response: import('@playwright/test').Response) => {
    const url = new URL(response.url())
    if (response.request().method() === 'POST' && [
      '/api/tracker/groups', '/api/tracker/trackers', '/api/tracker/entries', '/api/tasks',
    ].includes(url.pathname)) responseOrder.push(`${url.pathname} ${response.status()}`)
  }
  page.context().on('response', onResponse)
  const groupName = `${RUN_ID}_P3_INVALID_PARENT`
  const trackerName = `${RUN_ID}_P3_SUPPRESSED_TRACKER`
  const taskTitle = `${RUN_ID}_P3_INDEPENDENT_PUBLIC_TASK`
  let discarded = false
  try {
    await signInSynthetic(page, 15_000)
    await openTrackerTab(page)
    await waitForServiceWorker(page)
    await page.context().setOffline(true)
    await expect.poll(() => page.evaluate(() => navigator.onLine)).toBe(false)
    await reselectTrackerAfterOffline(page)

    const group = await createQueuedTrackerGroup(page, groupName)
    ids.group = group.entity_id!
    const trackerCard = await createQueuedTracker(page, groupName, trackerName)
    ids.tracker = await trackerCard.getAttribute('data-tracker-id') ?? ''
    const entry = await createQueuedEntry(page, trackerName)
    ids.entry = entry.entity_id!
    await page.getByRole('tab', { name: 'Task' }).click()
    await createTask(page, taskTitle)
    const taskRow = (await readOutboxRawByteReceipts(page)).find((item) => item.operation_kind === 'task.create')
    expect(taskRow).toBeDefined()
    ids.task = taskRow!.entity_id!
    const before = await readOutboxRawByteReceipts(page)
    expect(before).toHaveLength(4)
    expect(before.map((row) => row.dependency_operation_id)).toEqual([null, group.operation_id, (await readOutboxRawByteReceipts(page)).find((row) => row.operation_kind === 'tracker.create')!.operation_id, null])

    // This route sends the altered parent request to the actual API with route.fetch;
    // the real 422 response is relayed back to the PWA. No fulfilled fake response is used.
    await page.route('**/api/tracker/groups', async (route) => {
      const request = route.request()
      if (request.method() !== 'POST' || groupRejection) return route.continue()
      const body = request.postDataJSON() as Record<string, unknown>
      const response = await route.fetch({ postData: JSON.stringify({ ...body, kind: 'qa-invalid-kind' }) })
      groupRejection = await normalizeApiErrorResponse(response)
      await record('P3-real-api-parent-rejection', groupRejection)
      await route.fulfill({ response })
    })

    await page.context().setOffline(false)
    await expect.poll(() => groupRejection).toMatchObject({ status: 422 })
    await expect.poll(async () => {
      const rows = await readOutboxRawByteReceipts(page)
      return rows.filter((row) => [ids.group, ids.tracker, ids.entry].includes(row.entity_id ?? '')).map((row) => row.state)
    }).toEqual(['failed', 'suppressed', 'suppressed'])
    await expect.poll(async () => (await apiTask(page, ids.task)).status).toBe(200)
    const failedTree = await readOutboxRawByteReceipts(page)
    expect(failedTree).toHaveLength(3)
    expect(failedTree.map((row) => row.state)).toEqual(['failed', 'suppressed', 'suppressed'])
    expect(api.statuses.get('POST /api/tracker/groups 422')).toBe(1)
    expect(api.counts.get('POST /api/tracker/trackers') ?? 0).toBe(0)
    expect(api.counts.get('POST /api/tracker/entries') ?? 0).toBe(0)
    expect(api.statuses.get('POST /api/tasks 201')).toBe(1)
    expect(responseOrder).toContain('/api/tracker/groups 422')
    expect(responseOrder).toContain('/api/tasks 201')
    expect(await apiTask(page, ids.task)).toMatchObject({ status: 200, body: { id: ids.task } })

    await page.getByTestId('outbox-indicator').click()
    const panel = page.getByTestId('outbox-panel')
    await expect(panel.getByTestId('outbox-item')).toHaveCount(3)
    await expect(panel.getByTestId('outbox-item').first()).toContainText('Dữ liệu không vượt qua kiểm tra nghiệp vụ')
    await panel.getByTestId('outbox-item').first().getByTestId('outbox-item-discard').click()
    await expect.poll(async () => (await readOutboxRawByteReceipts(page)).length).toBe(0)
    discarded = true
    await expect(page.getByTestId('tracker-group-title').filter({ hasText: groupName })).toHaveCount(0)
    await expect(page.getByTestId('tracker-card').filter({ hasText: trackerName })).toHaveCount(0)
    await expect(page.getByTestId('task-title').filter({ hasText: taskTitle })).toBeVisible()
    expect(await apiTask(page, ids.task)).toMatchObject({ status: 200, body: { id: ids.task } })
    await capture(page, `${RUN_ID}-P3-parent-rejected-public-independent-rollback`)
    await record('P3-parent-suppression-discard-pass', { ids, groupRejection, responseOrder, discardedTreeRows: failedTree.length, independentTaskStillOnServer: true })
  } finally {
    const finalRows = await readOutboxRawByteReceipts(page).catch(() => [])
    await record('P3-final-outbox-state', { rows: finalRows, failedTreePreserved: finalRows.some((row) => row.state === 'failed' || row.state === 'suppressed') })
    const taskStatus = ids.task ? (await apiTask(page, ids.task).catch(() => ({ status: 0, body: null }))).status : 0
    if (discarded && taskStatus === 200) await cleanupSyntheticTasks(page, [ids.task])
    await record('P3-exact-synthetic-task-cleanup', { cleaned: discarded && taskStatus === 200 ? [ids.task] : [], skipped: !discarded || taskStatus !== 200 })
    await page.unroute('**/api/tracker/groups').catch(() => undefined)
    page.context().off('response', onResponse)
    api.close()
    // Keep the original failed queue tree if assertions stop before UI discard; never bulk-clear it.
  }
})

test('P2 held private tracker chain does not block later public command', async ({ page }) => {
  page.setDefaultTimeout(15_000)
  const api = attachApiCounter(page.context())
  const ids = { group: '', tracker: '', entry: '', task: '' }
  const groupName = `${RUN_ID}_P2_PUBLIC_GROUP`
  const trackerName = `${RUN_ID}_P2_PRIVATE_TRACKER`
  const taskTitle = `${RUN_ID}_P2_PUBLIC_TASK_AFTER_PRIVATE`
  let releaseLock = false
  try {
    await signInSynthetic(page, 15_000)
    await waitForExistingPrivateUnlock(page)
    await openTrackerTab(page)
    await acquireOutboxFlushLock(page)

    const group = await createQueuedTrackerGroup(page, groupName)
    ids.group = group.entity_id!
    const trackerCard = await createQueuedTracker(page, groupName, trackerName, true)
    ids.tracker = await trackerCard.getAttribute('data-tracker-id') ?? ''
    const entry = await createQueuedEntry(page, trackerName)
    ids.entry = entry.entity_id!
    const privateBeforeLock = (await readOutboxRawByteReceipts(page)).filter((row) => [ids.tracker, ids.entry].includes(row.entity_id ?? ''))
    expect(privateBeforeLock).toHaveLength(2)
    expect(privateBeforeLock.every((row) => row.requires_private)).toBe(true)
    expect(privateBeforeLock.every((row) => row.payload_sha256 === row.stored_payload_sha256 && row.payload_byte_length === row.stored_payload_byte_length)).toBe(true)

    await page.getByTestId('private-lock-now').click()
    await expect(page.getByTestId('private-badge')).toContainText('Khoá')
    await page.getByRole('tab', { name: 'Task' }).click()
    await createTask(page, taskTitle)
    ids.task = (await readOutboxRawByteReceipts(page)).find((row) => row.operation_kind === 'task.create')!.entity_id!
    releaseLock = true
    await releaseOutboxFlushLock(page)

    await expect.poll(async () => (await apiTask(page, ids.task)).status).toBe(200)
    await expect.poll(async () => {
      const rows = await readOutboxRawByteReceipts(page)
      return rows.find((row) => row.entity_id === ids.tracker)?.state
    }).toBe('private_hold')
    const held = await readOutboxRawByteReceipts(page)
    const privateRows = held.filter((row) => [ids.tracker, ids.entry].includes(row.entity_id ?? ''))
    expect(privateRows).toHaveLength(2)
    expect(privateRows.every((row) => row.requires_private && row.attempts === 0)).toBe(true)
    expect(privateRows.map((row) => row.payload_sha256)).toEqual(privateBeforeLock.map((row) => row.payload_sha256))
    expect(api.statuses.get('POST /api/tracker/groups 201')).toBe(1)
    expect(api.counts.get('POST /api/tracker/trackers') ?? 0).toBe(0)
    expect(api.counts.get('POST /api/tracker/entries') ?? 0).toBe(0)
    expect(api.statuses.get('POST /api/tasks 201')).toBe(1)
    expect(await apiCollectionHasId(page, '/api/tracker/groups', ids.group)).toEqual({ status: 200, present: true })
    await record('P2-private-hold-does-not-block-public', {
      groupId: ids.group, privateEntityIds: [ids.tracker, ids.entry], publicTaskId: ids.task,
      privateRows: privateRows.map(({ operation_id, operation_kind, entity_id, parent_id, dependency_operation_id, state, attempts, payload_sha256, payload_byte_length }) =>
        ({ operation_id, operation_kind, entity_id, parent_id, dependency_operation_id, state, attempts, payload_sha256, payload_byte_length })),
      publicTaskGetStatus: 200, trackerPostCount: 0, entryPostCount: 0,
    })
  } finally {
    if (!releaseLock) await releaseOutboxFlushLock(page).catch(() => undefined)
    const finalRows = await readOutboxRawByteReceipts(page).catch(() => [])
    await record('P2-final-outbox-state', { rows: finalRows })
    if (ids.task && (await apiTask(page, ids.task).catch(() => ({ status: 0, body: null }))).status === 200) await cleanupSyntheticTasks(page, [ids.task])
    if (ids.group && (await apiCollectionHasId(page, '/api/tracker/groups', ids.group).catch(() => ({ status: 0, present: false }))).present) {
      const status = await page.evaluate(async (id) => (await fetch(`/api/tracker/groups/${id}`, { method: 'DELETE', credentials: 'include' })).status, ids.group).catch(() => 0)
      await record('P2-exact-public-group-cleanup', { ownedGroupId: ids.group, status })
    }
    api.close()
  }
})

test('P4 revoked synthetic session 401 retains private payload bytes then same UUID resumes after login and unlock', async ({ page }) => {
  page.setDefaultTimeout(15_000)
  const api = attachApiCounter(page.context())
  let trackerId = ''
  let lockHeld = false
  try {
    await signInSynthetic(page, 15_000)
    await waitForExistingPrivateUnlock(page)
    await openTrackerTab(page)
    await acquireOutboxFlushLock(page)
    lockHeld = true

    const trackerName = `${RUN_ID}_P4_PRIVATE_TRACKER`
    await page.getByTestId('tracker-create').click()
    const form = page.getByTestId('tracker-form')
    await form.getByTestId('tracker-name-input').fill(trackerName)
    await form.getByRole('checkbox', { name: 'Riêng tư' }).click()
    await form.getByRole('button', { name: 'Tạo tracker' }).click()
    const queued = await expect.poll(async () => (await readOutboxRawByteReceipts(page)).find((row) => row.operation_kind === 'tracker.create' && row.requires_private) ?? null).not.toBeNull()
    void queued
    const rowBefore = (await readOutboxRawByteReceipts(page)).find((row) => row.operation_kind === 'tracker.create' && row.requires_private)!
    trackerId = rowBefore.entity_id!
    const digestBefore = { payload_sha256: rowBefore.payload_sha256, payload_byte_length: rowBefore.payload_byte_length, attempts: rowBefore.attempts }
    expect(rowBefore.payload_sha256).toBe(rowBefore.stored_payload_sha256)
    expect(rowBefore.payload_byte_length).toBe(rowBefore.stored_payload_byte_length)

    const logoutStatus = await page.evaluate(async () => (await fetch('/auth/logout', { method: 'POST', credentials: 'include' })).status)
    expect(logoutStatus).toBe(204)
    const unauthorizedStatus = await page.evaluate(async () => (await fetch('/api/me', { credentials: 'include' })).status)
    expect(unauthorizedStatus).toBe(401)
    await releaseOutboxFlushLock(page)
    lockHeld = false
    await expect.poll(async () => (await readOutboxRawByteReceipts(page)).find((row) => row.entity_id === trackerId)?.state).toBe('auth_hold')
    const after401 = (await readOutboxRawByteReceipts(page)).find((row) => row.entity_id === trackerId)!
    expect(after401).toMatchObject({
      state: 'auth_hold', attempts: digestBefore.attempts,
      payload_sha256: digestBefore.payload_sha256, payload_byte_length: digestBefore.payload_byte_length,
      stored_payload_sha256: digestBefore.payload_sha256, stored_payload_byte_length: digestBefore.payload_byte_length,
    })
    expect(api.statuses.get('POST /api/tracker/trackers 401')).toBe(1)
    await record('P4-after-auth-401-retained', {
      trackerId, state: after401.state, attempts: after401.attempts,
      payload_sha256: after401.payload_sha256, payload_byte_length: after401.payload_byte_length,
      actualApi401: true,
    })

    await signInSynthetic(page, 15_000)
    await waitForExistingPrivateUnlock(page)
    await expect.poll(async () => (await readOutboxRawByteReceipts(page)).some((row) => row.entity_id === trackerId)).toBe(false)
    expect(api.counts.get('POST /api/tracker/trackers')).toBe(2)
    expect(api.statuses.get('POST /api/tracker/trackers 201')).toBe(1)
    expect(await apiCollectionHasId(page, '/api/tracker/trackers', trackerId)).toEqual({ status: 200, present: true })
    await record('P4-same-uuid-resumed-after-new-session', {
      trackerId, payload_sha256: digestBefore.payload_sha256, payload_byte_length: digestBefore.payload_byte_length,
      requestStatuses: { first401: api.statuses.get('POST /api/tracker/trackers 401') ?? 0, resumed201: api.statuses.get('POST /api/tracker/trackers 201') ?? 0 },
      exactTrackerPresent: true,
    })
  } finally {
    if (lockHeld) await releaseOutboxFlushLock(page).catch(() => undefined)
    const finalRows = await readOutboxRawByteReceipts(page).catch(() => [])
    await record('P4-final-outbox-state', { trackerId, rows: finalRows.map(({ operation_id, operation_kind, entity_id, state, attempts, payload_sha256, payload_byte_length }) =>
      ({ operation_id, operation_kind, entity_id, state, attempts, payload_sha256, payload_byte_length })) })
    let cleanupStatus: number | null = null
    if (trackerId && !finalRows.some((row) => row.entity_id === trackerId) && (await apiCollectionHasId(page, '/api/tracker/trackers', trackerId).catch(() => ({ status: 0, present: false }))).present) {
      cleanupStatus = await page.evaluate(async (id) => (await fetch(`/api/tracker/trackers/${id}`, { method: 'DELETE', credentials: 'include' })).status, trackerId).catch(() => 0)
    }
    await record('P4-exact-synthetic-cleanup', { trackerId: trackerId || null, cleanupStatus,
      attempted: cleanupStatus !== null, success: cleanupStatus === 204 })
    api.close()
    if (cleanupStatus !== null) expect(cleanupStatus).toBe(204)
  }
})

async function readQueuedTrackerReminderSnapshot(page: import('@playwright/test').Page, entityId: string) {
  return page.evaluate(async (id) => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('microsched-outbox')
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    try {
      const rows = await new Promise<Array<Record<string, unknown>>>((resolve, reject) => {
        const request = db.transaction('outbox', 'readonly').objectStore('outbox').getAll()
        request.onsuccess = () => resolve(request.result as Array<Record<string, unknown>>)
        request.onerror = () => reject(request.error)
      })
      const row = rows.find((candidate) => candidate.operation_kind === 'tracker.create' && candidate.entity_id === id)
      if (!row) return null
      const body = JSON.parse(String(row.payload_json ?? '{}')) as Record<string, unknown>
      return {
        operation_id: Number(row.operation_id),
        operation_kind: String(row.operation_kind),
        entity_id: String(row.entity_id),
        state: String(row.state),
        attempts: Number(row.attempts),
        reminder_time: body.reminder_time ?? null,
        reminder_mode: body.reminder_mode ?? null,
        reminder_interval_days: body.reminder_interval_days ?? null,
        reminder_action: body.reminder_action ?? null,
        is_private: body.is_private ?? null,
        payload_sha256: String(row.payload_sha256),
        payload_byte_length: Number(row.payload_byte_length),
      }
    } finally {
      db.close()
    }
  }, entityId)
}

test('R1 offline public tracker reminder defers device registration then replays the same UUID', async ({ page }) => {
  page.setDefaultTimeout(15_000)
  const api = attachApiCounter(page.context())
  const trackerName = `${RUN_ID}_R1_REMINDER_TRACKER`
  let trackerId = ''
  let serverAcknowledged = false
  let queueDrained = false
  try {
    await signInSynthetic(page, 15_000)
    await openTrackerTab(page)
    const sw = await waitForServiceWorker(page)
    const instrumentation = await page.evaluate(async () => {
      const probe = { permissionCalls: 0, pushSubscribeCalls: 0, permissionInstrumented: false, pushSubscribeInstrumented: false }
      Object.defineProperty(window, '__qa072ReminderProbe', { configurable: false, value: probe })
      if (!('Notification' in window) || typeof Notification.requestPermission !== 'function') {
        throw new Error('Notification.requestPermission is unavailable; cannot prove zero calls')
      }
      Object.defineProperty(Notification, 'requestPermission', {
        configurable: true,
        value: () => {
          probe.permissionCalls += 1
          return Promise.reject(new Error('QA observer blocked an unexpected permission prompt'))
        },
      })
      probe.permissionInstrumented = true
      const registration = await navigator.serviceWorker.ready
      const pushPrototype = Object.getPrototypeOf(registration.pushManager)
      if (typeof registration.pushManager.subscribe !== 'function' || !pushPrototype) {
        throw new Error('PushManager.subscribe is unavailable; cannot prove zero calls')
      }
      Object.defineProperty(pushPrototype, 'subscribe', {
        configurable: true,
        value: () => {
          probe.pushSubscribeCalls += 1
          return Promise.reject(new Error('QA observer blocked an unexpected PushSubscription'))
        },
      })
      probe.pushSubscribeInstrumented = true
      return { ...probe, pushManagerAvailable: true }
    })
    expect(instrumentation.permissionInstrumented).toBe(true)
    expect(instrumentation.pushSubscribeInstrumented).toBe(true)
    expect(await readOutboxRawByteReceipts(page)).toHaveLength(0)

    await page.context().setOffline(true)
    await expect.poll(() => page.evaluate(() => navigator.onLine)).toBe(false)
    await reselectTrackerAfterOffline(page)

    await page.getByTestId('tracker-create').click()
    const form = page.getByTestId('tracker-form')
    await form.getByTestId('tracker-name-input').fill(trackerName)
    await form.getByTestId('tracker-reminder-enabled').click()
    await form.getByTestId('tracker-reminder-time').fill('09:15')
    await form.getByTestId('tracker-reminder-interval').fill('3')
    await form.getByRole('button', { name: 'Tạo tracker' }).click()

    const card = page.getByTestId('tracker-card').filter({ hasText: trackerName })
    await expect(card).toBeVisible()
    trackerId = (await card.getAttribute('data-tracker-id')) ?? ''
    expect(trackerId).toMatch(/^[0-9a-f-]{36}$/i)
    await expect.poll(async () =>
      (await readOutboxRawByteReceipts(page)).filter((row) => row.operation_kind === 'tracker.create'),
    ).toHaveLength(1)
    const queuedRows = await readOutboxRawByteReceipts(page)
    expect(queuedRows).toHaveLength(1)
    expect(queuedRows[0]).toMatchObject({
      operation_kind: 'tracker.create', entity_id: trackerId, state: 'pending', attempts: 0,
      requires_private: false, payload_sha256: queuedRows[0].stored_payload_sha256,
      payload_byte_length: queuedRows[0].stored_payload_byte_length,
    })
    const queuedReminder = await readQueuedTrackerReminderSnapshot(page, trackerId)
    expect(queuedReminder).toMatchObject({
      operation_kind: 'tracker.create', entity_id: trackerId, state: 'pending', attempts: 0,
      reminder_time: '09:15', reminder_mode: 'fixed', reminder_interval_days: 3,
      reminder_action: 'confirm_event', is_private: false,
    })
    await expect(page.getByText(
      'Đăng ký thông báo của thiết bị cần kết nối mạng. Thay đổi đang chờ đồng bộ; chỉ thiết bị đã đăng ký mới nhận được thông báo.',
      { exact: true },
    )).toBeVisible()
    const probeOffline = await page.evaluate(() => (window as Window & {
      __qa072ReminderProbe: { permissionCalls: number; pushSubscribeCalls: number }
    }).__qa072ReminderProbe)
    expect(probeOffline).toMatchObject({ permissionCalls: 0, pushSubscribeCalls: 0 })
    expect([...api.counts.entries()].filter(([key]) => key.startsWith('POST /api/tracker/trackers'))).toEqual([])
    expect([...api.counts.entries()].filter(([key]) => key.split(' ')[1]?.startsWith('/api/push/'))).toEqual([])
    await record('R1-offline-reminder-queued', {
      trackerId, operationId: queuedReminder?.operation_id, queueState: queuedReminder?.state,
      reminder: { time: queuedReminder?.reminder_time, mode: queuedReminder?.reminder_mode,
        intervalDays: queuedReminder?.reminder_interval_days, action: queuedReminder?.reminder_action },
      payloadSha256: queuedReminder?.payload_sha256, payloadByteLength: queuedReminder?.payload_byte_length,
      registrationProbe: probeOffline, pushApiRequestCount: 0,
    })
    await capture(page, `${RUN_ID}-R1-offline-reminder-queued`)

    const createAckPromise = page.waitForResponse((response) =>
      response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/tracker/trackers',
      { timeout: 15_000 },
    )
    await page.context().setOffline(false)
    const createAck = await createAckPromise
    expect(createAck.status()).toBe(201)
    const createBody = await createAck.json() as { id?: string }
    expect(createBody.id).toBe(trackerId)
    expect(createAck.request().postDataJSON()).toMatchObject({ id: trackerId, reminder_time: '09:15' })
    serverAcknowledged = true
    await waitForQueueEmpty(page, [trackerId], 15_000)
    queueDrained = true
    const persisted = await page.evaluate(async (id) => {
      const response = await fetch(`/api/tracker/trackers/${id}`, { credentials: 'include' })
      return { status: response.status, body: response.ok ? await response.json() as Record<string, unknown> : null }
    }, trackerId)
    expect(persisted.status).toBe(200)
    expect(persisted.body).toMatchObject({
      id: trackerId, reminder_time: '09:15:00', reminder_mode: 'fixed',
      reminder_interval_days: 3, reminder_action: 'confirm_event', is_private: false,
    })
    const probeOnline = await page.evaluate(() => (window as Window & {
      __qa072ReminderProbe: { permissionCalls: number; pushSubscribeCalls: number }
    }).__qa072ReminderProbe)
    expect(probeOnline).toMatchObject({ permissionCalls: 0, pushSubscribeCalls: 0 })
    expect([...api.counts.entries()].filter(([key]) => key.split(' ')[1]?.startsWith('/api/push/'))).toEqual([])
    expect(api.statuses.get('POST /api/tracker/trackers 201')).toBe(1)
    await record('R1-reminder-replay-ack-persisted', {
      trackerId, responseStatus: createAck.status(), responseId: createBody.id,
      persisted: { status: persisted.status, reminder_time: persisted.body?.reminder_time,
        reminder_mode: persisted.body?.reminder_mode,
        reminder_interval_days: persisted.body?.reminder_interval_days,
        reminder_action: persisted.body?.reminder_action },
      queueCount: (await readOutboxRawByteReceipts(page)).length,
      registrationProbe: probeOnline, pushApiRequestCount: 0,
    })
    await capture(page, `${RUN_ID}-R1-reminder-replayed`)
  } finally {
    const finalRows = await readOutboxRawByteReceipts(page).catch(() => [])
    await record('R1-final-outbox-observation', {
      rowCount: finalRows.length,
      rows: finalRows.map(({ operation_id, operation_kind, entity_id, state, attempts, payload_sha256, payload_byte_length }) =>
        ({ operation_id, operation_kind, entity_id, state, attempts, payload_sha256, payload_byte_length })),
      serverAcknowledged, queueDrained,
    })
    let cleanupStatus: number | null = null
    if (trackerId && serverAcknowledged && queueDrained) {
      cleanupStatus = await page.evaluate(async (id) =>
        (await fetch(`/api/tracker/trackers/${id}`, { method: 'DELETE', credentials: 'include' })).status,
      trackerId).catch(() => 0)
    }
    await record('R1-exact-synthetic-cleanup', {
      trackerId: trackerId || null, cleanupStatus,
      skippedUntilServerAckAndQueueDrain: !trackerId || !serverAcknowledged || !queueDrained,
    })
    api.close()
  }
})
