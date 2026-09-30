import { afterEach, describe, expect, it } from 'vitest'
import { ApiError, apiRequest, TimeoutError, UnauthenticatedError } from '../src/api'
import { payloadReceipt, type Json, type OutboxRow } from '../src/lib/outbox-db'
import { classifyOutboxError } from '../src/lib/outbox-flush'
const realFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = realFetch })
function row(changes: Partial<OutboxRow> = {}): OutboxRow {
  return { operation_id: 1, operation_kind: 'task.update', resource: 'task', method: 'PATCH', path: '/api/tasks/id', body: {}, payload_json: '{}', payload_sha256: '', payload_byte_length: 2, entity_id: 'id', parent_id: null, requires_private: false, idempotency_mode: 'absolute', dependency_operation_id: null, group_id: null, affected_query_keys: [['tasks']], state: 'pending', attempts: 0, next_attempt_at: null, created_at: 0, last_error_code: null, ...changes }
}
describe('canonical durable command payload', () => {
  it('canonicalizes object order, preserves array order and Unicode without normalization', async () => {
    expect(await payloadReceipt({ b: 2, a: 1 })).toEqual(await payloadReceipt({ a: 1, b: 2 }))
    expect((await payloadReceipt([1, 2])).payload_sha256).not.toBe((await payloadReceipt([2, 1])).payload_sha256)
    expect((await payloadReceipt('é')).payload_sha256).not.toBe((await payloadReceipt('e\u0301')).payload_sha256)
    expect((await payloadReceipt({ at: '2026-09-30T16:00:00.000Z' })).payload_json).toBe('{"at":"2026-09-30T16:00:00.000Z"}')
  })
  it.each([undefined, BigInt(1), NaN, Infinity, new Date()])('rejects non-JSON input %s', async (value) => {
    await expect(payloadReceipt(value as Json)).rejects.toThrow()
  })
  it('rejects sparse arrays instead of changing them into a different payload', async () => {
    await expect(payloadReceipt(new Array(1) as Json[])).rejects.toThrow()
  })
})
describe('route-aware retry decisions', () => {
  it('distinguishes private-gated DELETE from achieved public DELETE postcondition', () => {
    const error = new ApiError(404, 'hidden')
    expect(classifyOutboxError(row({ method: 'DELETE', requires_private: true }), error, false).state).toBe('private_hold')
    expect(classifyOutboxError(row({ method: 'DELETE' }), error, false).state).toBe('success')
    expect(classifyOutboxError(row({ operation_kind: 'task.restore', method: 'POST' }), error, true).state).toBe('failed')
  })
  it('never treats create conflict as success and resumes only after authorization', () => {
    expect(classifyOutboxError(row({ method: 'POST' }), new ApiError(409, 'conflict'), true).state).toBe('failed')
    expect(classifyOutboxError(row(), new UnauthenticatedError(), false).state).toBe('auth_hold')
    expect(classifyOutboxError(row(), new ApiError(403, 'locked', { detail: { code: 'PRIVATE_UNLOCK_REQUIRED' } }), false).state).toBe('private_hold')
    expect(classifyOutboxError(row(), new ApiError(422, 'invalid'), true).state).toBe('failed')
  })
  it.each([408, 425, 429, 500, 503])('retains uncertain operation for retry on HTTP %i', (status) => {
    expect(classifyOutboxError(row(), new ApiError(status, 'retry'), true, 0)).toMatchObject({ state: 'outcome_unknown', retryAt: 1000 })
  })
  it('retains uncertain operation on lost response or timeout', () => {
    expect(classifyOutboxError(row(), new TypeError('network'), true, 0).state).toBe('outcome_unknown')
    expect(classifyOutboxError(row(), new TimeoutError(), true, 0).state).toBe('outcome_unknown')
  })
  it('honors the HTTP Retry-After header rather than a synthetic JSON body field', async () => {
    globalThis.fetch = async () => new Response('{}', { status: 429, headers: { 'Content-Type': 'application/json', 'Retry-After': '5' } })
    let error: unknown
    try { await apiRequest('/api/tasks/id') } catch (caught) { error = caught }
    expect(error).toBeInstanceOf(ApiError)
    expect(classifyOutboxError(row(), error, true, 0).retryAt).toBe(5000)
  })
})
