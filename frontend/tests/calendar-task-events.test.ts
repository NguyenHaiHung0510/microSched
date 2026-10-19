import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { QueryClient, QueryObserver } from '@tanstack/react-query'
import { apiRequest } from '../src/api'
import { decideMimiChangeSet, recoverMimiReceipt, type MimiChangeSet, type MimiReceipt } from '../src/mimi-api'
import { publishMimiTaskCommit, subscribeCalendarTaskCommits } from '../src/calendar-task-events'
import { calendarTasksQuerySpec, monthEventsQuerySpec, sourcesQuerySpec, annotationsQuerySpec } from '../src/calendar-queries'

vi.mock('../src/api', () => ({ apiRequest: vi.fn(), ApiError: class extends Error {} }))
const CHANNEL = 'microsched:task-commit:v1'
const EVENT = 'microsched-tasks-committed'
const clients: QueryClient[] = []
const cleanup: (() => void)[] = []
let sequence = 0
const token = () => `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}`

class Channel {
  static open = new Set<Channel>()
  static posted: unknown[] = []
  static blocked = false
  onmessage: ((event: { data: unknown }) => void) | null = null
  constructor(readonly name: string) {
    if (Channel.blocked) throw new Error('channel blocked')
    Channel.open.add(this)
  }
  postMessage(data: unknown) {
    Channel.posted.push(data)
    for (const other of Channel.open) {
      if (other !== this && other.name === this.name) other.onmessage?.({ data })
    }
  }
  close() { Channel.open.delete(this) }
}
class Browser extends EventTarget {
  BroadcastChannel = Channel
  navigator = { onLine: true }
  localStorage = { setItem: vi.fn<(key: string, value: string) => void>(), getItem: vi.fn(() => null) }
}
class Document extends EventTarget { visibilityState = 'visible' }
let browser: Browser
let doc: Document

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(apiRequest).mockReset()
  Channel.open.clear(); Channel.posted = []; Channel.blocked = false
  browser = new Browser(); doc = new Document()
  vi.stubGlobal('window', browser); vi.stubGlobal('document', doc)
})
afterEach(() => {
  cleanup.splice(0).forEach((dispose) => dispose())
  clients.splice(0).forEach((client) => client.clear())
  vi.unstubAllGlobals(); vi.useRealTimers()
})
function fixture(tool: 'task.create.v1' | 'task.collection.v1' = 'task.collection.v1') {
  const id = `synthetic-change-${++sequence}`
  const change = { id, digest: 'synthetic-digest', operation: { tool, operation_id: id + '-operation', args: { title: 'PRIVATE_PROSE_NEVER_BROADCAST' } } } as unknown as MimiChangeSet
  const receipt: MimiReceipt = { id: id + '-receipt', change_set_id: id, digest: change.digest, operation_id: change.operation.operation_id, task_id: null, result: { private: 'PRIVATE_RESULT_NEVER_BROADCAST' }, executed_at: '2026-10-19T01:00:00Z' }
  return { change, receipt }
}
function client() {
  const value = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  clients.push(value)
  return value
}
function observe(cache: QueryClient, queryKey: readonly unknown[], value: () => unknown) {
  const queryFn = vi.fn(async () => value())
  const observer = new QueryObserver(cache, { queryKey, queryFn, refetchInterval: false, staleTime: Infinity })
  cleanup.push(observer.subscribe(() => undefined))
  return queryFn
}
function subscribe(cache: QueryClient) {
  const dispose = subscribeCalendarTaskCommits(cache)
  cleanup.push(dispose)
  return dispose
}
function local(signal = { version: 1, token: token() }) {
  browser.dispatchEvent(new CustomEvent(EVENT, { detail: signal }))
  return signal
}
function storage(value: string, key = CHANNEL) {
  browser.dispatchEvent(Object.assign(new Event('storage'), { key, newValue: value }))
}
const settle = () => vi.advanceTimersByTimeAsync(60)

test('API publishes only after matching Confirm/recovery receipts, never while pending/Reject/unknown; replay is deduped', async () => {
  const { change, receipt } = fixture()
  const received = vi.fn()
  browser.addEventListener(EVENT, received)
  let commit!: (value: MimiReceipt) => void
  vi.mocked(apiRequest).mockReturnValueOnce(new Promise((resolve) => { commit = resolve }))
  const pending = decideMimiChangeSet(change, 'confirm', 'original-key')
  expect(received).not.toHaveBeenCalled()
  commit(receipt)
  expect(await pending).toBe(receipt)
  expect(received).toHaveBeenCalledTimes(1)
  vi.mocked(apiRequest).mockResolvedValueOnce(receipt)
  expect(await recoverMimiReceipt('synthetic-conversation', change, 'original-key')).toBe(receipt)
  expect(received).toHaveBeenCalledTimes(1)
  expect(apiRequest).toHaveBeenLastCalledWith(expect.stringContaining('/receipt?'), { headers: { 'Idempotency-Key': 'original-key' } })
  vi.mocked(apiRequest).mockResolvedValueOnce({ change_set_id: change.id, state: 'rejected' })
  await decideMimiChangeSet(change, 'reject', 'reject-key')
  vi.mocked(apiRequest).mockRejectedValueOnce(new Error('UNKNOWN outcome'))
  await expect(decideMimiChangeSet(change, 'confirm', 'unknown-key')).rejects.toThrow('UNKNOWN')
  vi.mocked(apiRequest).mockRejectedValueOnce(new Error('receipt absent'))
  await expect(recoverMimiReceipt('synthetic-conversation', change, 'unknown-key')).rejects.toThrow('absent')
  expect(received).toHaveBeenCalledTimes(1)
  expect(Channel.posted).toEqual([{ version: 1, token: expect.any(String) }])
  expect(JSON.stringify(Channel.posted)).not.toMatch(/PRIVATE|synthetic|digest|receipt|task_id/)
  expect(Channel.open.size).toBe(0) // Publisher never leaks its short-lived channel.
})

test('single-create and recovered collection receipts publish; mismatched/incomplete bindings never do', async () => {
  const received = vi.fn()
  browser.addEventListener(EVENT, received)
  const { change, receipt } = fixture('task.create.v1')
  for (const wrong of [{ ...receipt, digest: 'wrong' }, { ...receipt, operation_id: 'wrong' }, { ...receipt, change_set_id: 'wrong' }, { ...receipt, executed_at: '' }]) publishMimiTaskCommit(change, wrong)
  expect(received).not.toHaveBeenCalled()
  publishMimiTaskCommit(change, receipt)
  const recovered = fixture()
  vi.mocked(apiRequest).mockResolvedValueOnce(recovered.receipt)
  await recoverMimiReceipt('synthetic-conversation', recovered.change, 'preserved-key')
  expect(received).toHaveBeenCalledTimes(2)
})

test('same-app commit re-reads only Task projections, coalesces duplicates, and idles without polling or cache feedback loops', async () => {
  const cache = client()
  let serverDay = '2026-10-19'
  const taskSpec = calendarTasksQuerySpec('all', { from: '2026-10-01', to: '2026-10-31' })
  const tasks = observe(cache, taskSpec.queryKey, () => ({ due_on: serverDay }))
  const detail = observe(cache, ['tasks', 'overdue-before', '2026-10-20', true], () => [])
  const unrelated = [sourcesQuerySpec, annotationsQuerySpec('2026-10-01', '2026-10-31'), ...Array.from({ length: 13 }, (_, n) => monthEventsQuerySpec(2026, n + 1))]
  const unrelatedReads = unrelated.map((spec) => observe(cache, spec.queryKey, () => []))
  const inactive = calendarTasksQuerySpec('all', { from: '2027-01-01', to: '2027-01-31' }).queryKey
  cache.setQueryDefaults(inactive, { gcTime: Infinity })
  cache.setQueryData(inactive, [])
  subscribe(cache)
  await settle()
  expect(cache.getQueryData(taskSpec.queryKey)).toEqual({ due_on: '2026-10-19' })
  serverDay = '2026-10-21'
  const { change, receipt } = fixture()
  publishMimiTaskCommit(change, receipt)
  publishMimiTaskCommit(change, receipt)
  local(); local() // Different receipts in a logical burst still share one read.
  await settle()
  expect(cache.getQueryData(taskSpec.queryKey)).toEqual({ due_on: '2026-10-21' })
  expect(tasks).toHaveBeenCalledTimes(2)
  expect(detail).toHaveBeenCalledTimes(2)
  expect(cache.getQueryState(inactive)?.isInvalidated).toBe(true)
  unrelatedReads.forEach((read) => expect(read).toHaveBeenCalledTimes(1))
  await vi.advanceTimersByTimeAsync(60_000)
  expect(tasks).toHaveBeenCalledTimes(2)
  expect(vi.getTimerCount()).toBe(0)
})

test('same-origin channel reaches independent caches; receiving or replaying a signal only performs GET query functions', async () => {
  const first = client(), second = client()
  const reads = [observe(first, calendarTasksQuerySpec('all').queryKey, () => []), observe(second, calendarTasksQuerySpec('all').queryKey, () => [])]
  subscribe(first); subscribe(second)
  await settle()
  const sender = new Channel(CHANNEL)
  const signal = { version: 1, token: token() }
  sender.postMessage(signal); sender.postMessage(signal)
  storage(JSON.stringify(signal)) // Same token through fallback must not re-fetch twice.
  await settle()
  reads.forEach((read) => expect(read).toHaveBeenCalledTimes(2))
  expect(apiRequest).not.toHaveBeenCalled() // Subscriber cannot replay any mutation.
  sender.close()
})

test('hidden/offline tabs mark Task ranges stale, defer reads and reconcile on visible/focus/reconnect even after missed events', async () => {
  const cache = client(), spec = calendarTasksQuerySpec('all')
  const reads = observe(cache, spec.queryKey, () => [])
  subscribe(cache); await settle()
  doc.visibilityState = 'hidden'; local(); await settle()
  expect(cache.getQueryState(spec.queryKey)?.isInvalidated).toBe(true)
  expect(reads).toHaveBeenCalledTimes(1)
  doc.visibilityState = 'visible'
  doc.dispatchEvent(new Event('visibilitychange')); browser.dispatchEvent(new Event('focus'))
  await settle(); expect(reads).toHaveBeenCalledTimes(2)
  browser.navigator.onLine = false; local(); await settle()
  expect(reads).toHaveBeenCalledTimes(2)
  browser.navigator.onLine = true; browser.dispatchEvent(new Event('online'))
  await settle(); expect(reads).toHaveBeenCalledTimes(3)
  browser.dispatchEvent(new Event('focus')) // Reconcile even when no signal was delivered.
  await settle(); expect(reads).toHaveBeenCalledTimes(4)
  local(); doc.visibilityState = 'hidden'; await settle() // Hide during debounce.
  expect(reads).toHaveBeenCalledTimes(4)
  doc.visibilityState = 'visible'; doc.dispatchEvent(new Event('visibilitychange'))
  await settle(); expect(reads).toHaveBeenCalledTimes(5)
})

test('channel unavailable uses a tiny storage fallback; blocked storage never changes a successful API outcome', async () => {
  Channel.blocked = true
  const cache = client(), reads = observe(cache, calendarTasksQuerySpec('all').queryKey, () => [])
  subscribe(cache); await settle()
  const { change, receipt } = fixture()
  vi.mocked(apiRequest).mockResolvedValueOnce(receipt)
  expect(await decideMimiChangeSet(change, 'confirm', 'synthetic-key')).toBe(receipt)
  const [key, value] = browser.localStorage.setItem.mock.calls[0]
  expect(key).toBe(CHANNEL)
  expect(value.length).toBeLessThan(128)
  expect(JSON.parse(value)).toEqual({ version: 1, token: expect.any(String) })
  await settle(); expect(reads).toHaveBeenCalledTimes(2)
  storage(JSON.stringify({ version: 1, token: token() }))
  await settle(); expect(reads).toHaveBeenCalledTimes(3)
  browser.localStorage.setItem.mockImplementation(() => { throw new Error('storage blocked') })
  const next = fixture()
  vi.mocked(apiRequest).mockResolvedValueOnce(next.receipt)
  expect(await decideMimiChangeSet(next.change, 'confirm', 'next-key')).toBe(next.receipt)
  await settle(); expect(reads).toHaveBeenCalledTimes(4)
})

test('invalid signals are ignored and unmount cancels pending reads, closes channels and removes lifecycle listeners', async () => {
  const cache = client(), reads = observe(cache, calendarTasksQuerySpec('all').queryKey, () => [])
  const dispose = subscribe(cache); await settle()
  storage('not JSON'); storage(JSON.stringify({ version: 2, token: token() }))
  storage(JSON.stringify({ version: 1, token: token(), private: 'no' }))
  storage(JSON.stringify({ version: 1, token: token() }), 'unrelated-key')
  local({ version: 1, token: 'invalid-token' })
  await settle(); expect(reads).toHaveBeenCalledTimes(1)
  local(); dispose(); await settle()
  expect(Channel.open.size).toBe(0)
  local(); browser.dispatchEvent(new Event('focus')); browser.dispatchEvent(new Event('online')); doc.dispatchEvent(new Event('visibilitychange'))
  await settle(); expect(reads).toHaveBeenCalledTimes(1)
})

test('an inflight pre-commit initial read cannot overwrite the committed projection', async () => {
  const cache = client(), spec = calendarTasksQuerySpec('all')
  let finishOld!: (value: { due_on: string }) => void
  const queryFn = vi.fn()
    .mockImplementationOnce(() => new Promise<{ due_on: string }>((resolve) => { finishOld = resolve }))
    .mockResolvedValue({ due_on: '2026-10-21' })
  const observer = new QueryObserver(cache, { ...spec, queryFn })
  cleanup.push(observer.subscribe(() => undefined))
  subscribe(cache)
  expect(queryFn).toHaveBeenCalledTimes(1)
  local(); await settle()
  expect(queryFn).toHaveBeenCalledTimes(2)
  expect(cache.getQueryData(spec.queryKey)).toEqual({ due_on: '2026-10-21' })
  finishOld({ due_on: '2026-10-19' }); await settle()
  expect(cache.getQueryData(spec.queryKey)).toEqual({ due_on: '2026-10-21' })
  await vi.advanceTimersByTimeAsync(60_000)
  expect(queryFn).toHaveBeenCalledTimes(2)
})
