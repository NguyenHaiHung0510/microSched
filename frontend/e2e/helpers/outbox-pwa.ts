import { appendFile, mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { expect, type BrowserContext, type Page, type Request } from '@playwright/test'

export const RUN_ID = 'QA017_' + (process.env.QA017_RUN_TAG ?? 'unscoped').replace(/[^A-Za-z0-9_-]/g, '-')
export const RECEIPT_DIR = process.env.QA017_RECEIPT_DIR
  ?? '../output/outbox-pwa'

export type OutboxReceipt = {
  operation_id: number
  operation_kind: string
  entity_id: string | null
  parent_id: string | null
  state: string
  attempts: number
  next_attempt_at: number | null
  last_error_code: string | null
  payload_sha256: string
  payload_byte_length: number
}

export type OutboxRawByteReceipt = Pick<OutboxReceipt,
  'operation_id' | 'operation_kind' | 'entity_id' | 'parent_id' | 'state' | 'attempts' | 'last_error_code'> & {
  resource: string
  dependency_operation_id: number | null
  requires_private: boolean
  payload_sha256: string
  payload_byte_length: number
  stored_payload_sha256: string
  stored_payload_byte_length: number
}

export async function record(event: string, data: Record<string, unknown> = {}) {
  await mkdir(RECEIPT_DIR, { recursive: true })
  await appendFile(path.join(RECEIPT_DIR, 'events.jsonl'), `${JSON.stringify({ at: new Date().toISOString(), run_id: RUN_ID, source_head: process.env.QA017_BUILD_SHA, event, ...data })}\n`, 'utf8')
}

export function attachApiCounter(context: BrowserContext) {
  const counts = new Map<string, number>()
  const statuses = new Map<string, number>()
  const onRequest = (request: Request) => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/')) {
      const key = `${request.method()} ${url.pathname}`
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
  }
  const onResponse = (response: import('@playwright/test').Response) => {
    const url = new URL(response.url())
    if (url.pathname.startsWith('/api/')) {
      const key = `${response.request().method()} ${url.pathname} ${response.status()}`
      statuses.set(key, (statuses.get(key) ?? 0) + 1)
    }
  }
  context.on('request', onRequest)
  context.on('response', onResponse)
  return {
    counts,
    statuses,
    close: () => { context.off('request', onRequest); context.off('response', onResponse) },
  }
}

export async function signInSynthetic(page: Page, timeout = 20_000) {
  const response = await page.goto('/auth/dev-session', { waitUntil: 'domcontentloaded' })
  if (!response || response.status() >= 400) throw new Error(`Synthetic loopback session failed (${response?.status() ?? 'no response'})`)
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.getByTestId('quick-add-input').waitFor({ state: 'visible', timeout })
  await record('synthetic-session-ready', { status: response.status(), app: 'owner@test.local QA session; no cookie captured' })
}

export type PrebootFault = 'indexeddb-open-blocked' | 'outbox-first-write-quota' | 'web-locks-absent' | 'existing-queue-second-write-quota'

/** Install one bounded browser-boundary fault before navigation; no API or identity mocking. */
export async function installPrebootFault(page: Page, fault: PrebootFault) {
  await page.addInitScript((faultKind) => {
    const state = { kind: faultKind, openAttempts: 0, outboxWriteAttempts: 0, injectedFailures: 0 }
    Object.defineProperty(window, '__qa072PrebootFault', { configurable: false, value: state })
    if (faultKind === 'indexeddb-open-blocked') {
      IDBFactory.prototype.open = function () {
        state.openAttempts += 1
        throw new DOMException('QA017 synthetic IndexedDB open blocked', 'SecurityError')
      }
    } else if (faultKind === 'outbox-first-write-quota' || faultKind === 'existing-queue-second-write-quota') {
      const originalAdd = IDBObjectStore.prototype.add
      IDBObjectStore.prototype.add = function (...args: Parameters<typeof originalAdd>) {
        if (this.transaction.db.name === 'microsched-outbox' && this.name === 'outbox') {
          state.outboxWriteAttempts += 1
          const faultOnAttempt = faultKind === 'outbox-first-write-quota' ? 1 : 2
          if (state.outboxWriteAttempts === faultOnAttempt && state.injectedFailures === 0) {
            state.injectedFailures += 1
            throw new DOMException('QA017 synthetic outbox quota failure', 'QuotaExceededError')
          }
        }
        return originalAdd.apply(this, args)
      }
      if (faultKind === 'existing-queue-second-write-quota') {
        Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined })
      }
    } else {
      Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined })
    }
  }, fault)
}

export async function readPrebootFault(page: Page) {
  return page.evaluate(() => {
    const state = (window as Window & { __qa072PrebootFault?: { kind: string; openAttempts: number; outboxWriteAttempts: number; injectedFailures: number } }).__qa072PrebootFault
    return state ? { ...state, locksAvailable: Boolean(navigator.locks) } : null
  })
}

export async function createOnlineTaskAndReadResponse(page: Page, title: string, ids: string[]) {
  const responseWait = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/tasks',
    { timeout: 15_000 },
  ).catch(() => null)
  await page.getByTestId('quick-add-input').fill(title)
  await page.getByTestId('quick-add-submit').click()
  const response = await responseWait
  let id: string | null = null
  if (response?.ok()) {
    const body = await response.json() as { id?: string }
    if (typeof body.id === 'string') {
      id = body.id
      ids.push(id)
    }
  }
  await record('preboot-fault-online-task-response', {
    title,
    status: response?.status() ?? null,
    entityId: id,
    method: 'POST',
    path: '/api/tasks',
  })
  return { response, id }
}

export async function createTask(page: Page, title: string) {
  await page.getByTestId('quick-add-input').fill(title)
  await page.getByTestId('quick-add-submit').click()
  await page.getByTestId('task-title').filter({ hasText: title }).waitFor({ state: 'visible', timeout: 15_000 })
  return page.getByTestId('task-title').filter({ hasText: title })
}

export async function waitForServiceWorker(page: Page) {
  const state = await page.evaluate(async () => {
    if (!('serviceWorker' in navigator)) return { supported: false, ready: false, controlled: false, scriptURL: null }
    const registration = await navigator.serviceWorker.ready
    const until = Date.now() + 15_000
    while (!navigator.serviceWorker.controller && Date.now() < until) {
      await new Promise((resolve) => setTimeout(resolve, 50))
    }
    return {
      supported: true,
      ready: Boolean(registration.active),
      controlled: Boolean(navigator.serviceWorker.controller),
      scriptURL: navigator.serviceWorker.controller?.scriptURL ?? registration.active?.scriptURL ?? null,
      secureContext: isSecureContext,
    }
  })
  await record('service-worker-ready-controller', state)
  if (!state.supported || !state.ready || !state.controlled) throw new Error(`PWA controller not ready: ${JSON.stringify(state)}`)
  return state
}

export async function readOutbox(page: Page): Promise<OutboxReceipt[]> {
  return page.evaluate(async () => {
    const databases = await indexedDB.databases()
    if (!databases.some((database) => database.name === 'microsched-outbox')) return []
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('microsched-outbox')
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    try {
      if (!db.objectStoreNames.contains('outbox')) return []
      const rows = await new Promise<Record<string, unknown>[]>((resolve, reject) => {
        const request = db.transaction('outbox', 'readonly').objectStore('outbox').getAll()
        request.onsuccess = () => resolve(request.result as Record<string, unknown>[])
        request.onerror = () => reject(request.error)
      })
      return rows.map((row) => ({
        operation_id: Number(row.operation_id),
        operation_kind: String(row.operation_kind),
        entity_id: row.entity_id == null ? null : String(row.entity_id),
        parent_id: row.parent_id == null ? null : String(row.parent_id),
        state: String(row.state),
        attempts: Number(row.attempts),
        next_attempt_at: row.next_attempt_at == null ? null : Number(row.next_attempt_at),
        last_error_code: row.last_error_code == null ? null : String(row.last_error_code),
        payload_sha256: String(row.payload_sha256),
        payload_byte_length: Number(row.payload_byte_length),
      }))
    } finally {
      db.close()
    }
  })
}

/** Recompute receipts from the actual stored UTF-8 bytes; never return or log payload text. */
export async function readOutboxRawByteReceipts(page: Page): Promise<OutboxRawByteReceipt[]> {
  return page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('microsched-outbox')
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    try {
      if (!db.objectStoreNames.contains('outbox')) return []
      const rows = await new Promise<Record<string, unknown>[]>((resolve, reject) => {
        const request = db.transaction('outbox', 'readonly').objectStore('outbox').getAll()
        request.onsuccess = () => resolve(request.result as Record<string, unknown>[])
        request.onerror = () => reject(request.error)
      })
      const receipts = await Promise.all(rows.map(async (row) => {
        const bytes = new TextEncoder().encode(String(row.payload_json ?? ''))
        const digest = await crypto.subtle.digest('SHA-256', bytes)
        const payload_sha256 = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
        return {
          operation_id: Number(row.operation_id),
          operation_kind: String(row.operation_kind),
          entity_id: row.entity_id == null ? null : String(row.entity_id),
          parent_id: row.parent_id == null ? null : String(row.parent_id),
          state: String(row.state),
          attempts: Number(row.attempts),
          last_error_code: row.last_error_code == null ? null : String(row.last_error_code),
          resource: String(row.resource),
          dependency_operation_id: row.dependency_operation_id == null ? null : Number(row.dependency_operation_id),
          requires_private: row.requires_private === true,
          payload_sha256,
          payload_byte_length: bytes.byteLength,
          stored_payload_sha256: String(row.payload_sha256),
          stored_payload_byte_length: Number(row.payload_byte_length),
        }
      }))
      return receipts
    } finally {
      db.close()
    }
  })
}

/** Read only synthetic entity IDs from the real public collection endpoints. */
export async function apiCollectionHasId(page: Page, path: '/api/tracker/groups' | '/api/tracker/trackers' | '/api/tracker/entries', id: string) {
  return page.evaluate(async ({ collectionPath, entityId }) => {
    const response = await fetch(collectionPath, { credentials: 'include' })
    if (!response.ok) return { status: response.status, present: false }
    const body = await response.json() as { items?: Array<{ id?: string }> }
    return { status: response.status, present: Boolean(body.items?.some((item) => item.id === entityId)) }
  }, { collectionPath: path, entityId: id })
}

/** Keep only status and a machine-readable code from a real API error response. */
export async function normalizeApiErrorResponse(response: import('@playwright/test').APIResponse) {
  let code: string | null = null
  try {
    const body = await response.json() as { detail?: unknown }
    if (body.detail && typeof body.detail === 'object' && 'code' in body.detail) {
      code = String((body.detail as { code?: unknown }).code)
    }
  } catch { /* Non-JSON validation details are deliberately not retained. */ }
  return { status: response.status(), code }
}

export async function observeOutboxInFinally(page: Page, caseId: string, apiCounts?: { requests: Record<string, number>; responses: Record<string, number> }) {
  try {
    const rows = await readOutbox(page)
    const observation = {
      at: new Date().toISOString(),
      case_id: caseId,
      run_id: RUN_ID,
      source_head: process.env.QA017_BUILD_SHA,
      phase: 'finally-before-cleanup',
      row_count: rows.length,
      rows,
      api_counts: apiCounts ?? null,
    }
    await record(`${caseId}-finally-outbox-observation`, observation)
    const manifestPath = path.join(RECEIPT_DIR, 'manifest.json')
    const manifestText = (await readFile(manifestPath, 'utf8')).replace(/^\uFEFF/, '')
    const manifest = JSON.parse(manifestText) as Record<string, unknown>
    const observations = Array.isArray(manifest.queue_observations) ? manifest.queue_observations : []
    observations.push(observation)
    manifest.queue_observations = observations
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')
    return observation
  } catch (error) {
    const failure = { case_id: caseId, phase: 'finally-before-cleanup', error: error instanceof Error ? error.message : String(error) }
    await record(`${caseId}-finally-outbox-observation-error`, failure).catch(() => undefined)
    return { ...failure, row_count: null, rows: null }
  }
}

export async function apiTask(page: Page, id: string) {
  const response = await page.evaluate(async (taskId) => {
    const result = await fetch(`/api/tasks/${taskId}`, { credentials: 'include' })
    return { status: result.status, body: result.ok ? await result.json() : null }
  }, id)
  return response as { status: number; body: { id: string; title: string; items?: Array<{ id: string; content: string; is_completed: boolean }> } | null }
}

export async function capture(page: Page, name: string) {
  const target = path.join(RECEIPT_DIR, 'artifacts', `${name}.png`)
  await mkdir(path.dirname(target), { recursive: true })
  await page.screenshot({ path: target, fullPage: true, animations: 'disabled' })
  await record('screenshot', { file: target, visibleTitle: await page.title() })
  return target
}

export async function waitForQueueEmpty(page: Page, entityIds: string[], timeout = 20_000) {
  // Poll the awaited readonly storage result in Node; an async page predicate
  // must never count a still-pending Promise as evidence that the queue drained.
  await expect.poll(async () => {
    const rows = await readOutbox(page)
    return rows.filter((row) => entityIds.includes(String(row.entity_id)) || entityIds.includes(String(row.parent_id)))
  }, { timeout, intervals: [100, 200, 500] }).toHaveLength(0)
}
export async function cleanupSyntheticTasks(page: Page, ids: string[]) {
  await page.context().setOffline(false)
  const results: Array<{ id: string; status: number }> = []
  for (const id of [...new Set(ids)]) {
    const result = await page.evaluate(async (taskId) => {
      const response = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE', credentials: 'include' })
      return response.status
    }, id).catch(() => 0)
    results.push({ id, status: result })
  }
  await record('cleanup-exact-synthetic-task-ids', { results, scope: 'API DELETE exact run-created IDs only' })
  return results
}
