import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { CalendarTask } from './calendar-scroll'
import { assertCalendarMoveOnline, moveCalendarTask, waitForCalendarTaskAck } from './calendar-move'

const h = vi.hoisted(() => ({
  state: { context: { verified: true, expires: 0, principal: 'synthetic' }, authRequired: false,
    rows: [] as Array<{ aggregate: string; principal: string; state: string }>, reconciling: [] as string[] },
  listeners: new Set<() => void>(), open: true, barrier: vi.fn(), write: vi.fn(), read: vi.fn(),
}))
vi.mock('@/outbox/core', () => ({
  barrier: h.barrier, getSnapshot: () => h.state, unlocked: () => h.open,
  subscribe: (fn: () => void) => { h.listeners.add(fn); return () => h.listeners.delete(fn) },
}))
vi.mock('@/outbox/adapters', () => ({ taskRequest: h.write }))
vi.mock('@/api', () => ({ apiRequest: h.read }))
const schedule = { due_precision: 'datetime' as const, due_on: null, due_at: '2026-10-27T09:30:45.123+07:00' }
const task = { id: 'own-task', is_private: false } as CalendarTask
const emit = () => { for (const fn of [...h.listeners]) fn() }
beforeEach(() => {
  vi.stubGlobal('window', new EventTarget())
  vi.stubGlobal('navigator', { onLine: true })
  h.state.context = { verified: true, expires: Date.now() + 60000, principal: 'synthetic' }
  h.state.authRequired = false; h.state.rows = []; h.state.reconciling = []; h.open = true
  h.barrier.mockReset().mockResolvedValue(undefined)
  h.write.mockReset().mockResolvedValue({ local_acceptance: true })
  h.read.mockReset().mockResolvedValue({ ...task, ...schedule })
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); h.listeners.clear() })

it('refuses offline/private-locked/unverified admission before any typed write', async () => {
  vi.stubGlobal('navigator', { onLine: false })
  await expect(moveCalendarTask(task, schedule)).rejects.toThrow('Kết nối mạng')
  vi.stubGlobal('navigator', { onLine: true }); h.open = false
  await expect(moveCalendarTask({ ...task, is_private: true }, schedule)).rejects.toThrow('Mở khoá')
  h.open = true; h.state.context.verified = false
  expect(() => assertCalendarMoveOnline(false)).toThrow('Đăng nhập lại')
  expect(h.write).not.toHaveBeenCalled()
})
it('retains existing same-object ordering by refusing the core barrier', async () => {
  h.barrier.mockRejectedValue(Error('Đối tượng còn thay đổi đang chờ.'))
  await expect(moveCalendarTask(task, schedule)).rejects.toThrow('đang chờ')
  expect(h.write).not.toHaveBeenCalled()
})
it('keeps local acceptance pending through both durable queue and reconciliation', async () => {
  h.state.rows = [{ aggregate: 'task:own-task', principal: 'synthetic', state: 'queued' }]
  const promise = waitForCalendarTaskAck(task.id, false)
  let done = false; void promise.then(() => { done = true })
  await Promise.resolve(); expect(done).toBe(false)
  h.state.rows = []; h.state.reconciling = ['task:own-task']; emit()
  await Promise.resolve(); expect(done).toBe(false)
  h.state.reconciling = []; emit(); await promise
  expect(done).toBe(true); expect(h.listeners.size).toBe(0)
})
it('preserves unknown durable commands and refuses to claim confirmation', async () => {
  h.state.rows = [{ aggregate: 'task:own-task', principal: 'synthetic', state: 'unknown' }]
  await expect(waitForCalendarTaskAck(task.id, false)).rejects.toThrow('chưa được xác minh')
  expect(h.state.rows).toHaveLength(1)
  expect(h.write).not.toHaveBeenCalled()
})
it('requires canonical time after ACK instead of treating local acceptance as saved', async () => {
  await expect(moveCalendarTask(task, schedule)).resolves.toMatchObject(schedule)
  expect(h.read).toHaveBeenCalledWith('/api/tasks/own-task')
  h.read.mockResolvedValue({ ...task, ...schedule, due_precision: 'date', due_at: null })
  await expect(moveCalendarTask(task, schedule)).rejects.toThrow('Lịch đã thay đổi')
})
it('ends a private wait on lock without deleting its queued command', async () => {
  h.state.rows = [{ aggregate: 'task:own-task', principal: 'synthetic', state: 'queued' }]
  const promise = waitForCalendarTaskAck(task.id, true)
  h.open = false; window.dispatchEvent(new Event('microsched:visibility'))
  await expect(promise).rejects.toThrow('Mở khoá')
  expect(h.state.rows).toHaveLength(1)
})
it('bounds waiting without adding polling or automatic retries', async () => {
  vi.useFakeTimers()
  h.state.rows = [{ aggregate: 'task:own-task', principal: 'synthetic', state: 'queued' }]
  const result = expect(waitForCalendarTaskAck(task.id, false)).rejects.toThrow('Chưa xác minh được lưu')
  await vi.advanceTimersByTimeAsync(30000); await result
  expect(h.state.rows).toHaveLength(1); expect(h.write).not.toHaveBeenCalled()
})
