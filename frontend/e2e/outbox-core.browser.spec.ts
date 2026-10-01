import { expect, test } from '@playwright/test'

test('real IndexedDB persists claims, atomic dependencies and unsent coalescing', async ({ page }) => {
  // Core diagnostic lane only: no app shell, PWA or API acceptance claim.
  await page.goto('/denied.html')
  const result = await page.evaluate(async () => {
    const moduleUrl = '/src/lib/outbox-db.ts'
    const db = await import(moduleUrl)
    const command = (id: string, body: Record<string, unknown>, parent: string | null = null) => ({
      operation_kind: parent ? 'task_item.create' : 'task.create', resource: parent ? 'task_item' : 'task',
      method: 'POST', path: parent ? `/api/tasks/${parent}/items` : '/api/tasks',
      body, entity_id: id, parent_id: parent, requires_private: false, idempotency_mode: 'client_uuid',
      dependency_operation_id: null, group_id: null, affected_query_keys: [['tasks']],
      state: 'pending', attempts: 0, next_attempt_at: null, created_at: Date.now(), last_error_code: null,
    })
    const parent = await db.enqueueOutbox(command('parent', { id: 'parent', title: 'synthetic' }))
    const child = await db.enqueueOutbox(command('child', { id: 'child', content: 'synthetic child' }, 'parent'))
    const patch = await db.enqueueOutbox({ ...command('parent', { title: 'edited' }),
      operation_kind: 'task.update', method: 'PATCH', path: '/api/tasks/parent', idempotency_mode: 'absolute' })
    const first = await db.listOutbox()
    const cancellation = await db.enqueueOutbox({ ...command('parent', null as unknown as Record<string, unknown>),
      operation_kind: 'task.delete', method: 'DELETE', path: '/api/tasks/parent', idempotency_mode: 'postcondition' })
    const afterCancellation = await db.listOutbox()
    const original = await db.enqueueOutbox({ ...command('existing', { title: 'first' }),
      operation_kind: 'task.update', method: 'PATCH', path: '/api/tasks/existing', idempotency_mode: 'absolute' })
    const merged = await db.enqueueOutbox({ ...command('existing', { pinned: true }),
      operation_kind: 'task.update', method: 'PATCH', path: '/api/tasks/existing', idempotency_mode: 'absolute' })
    const mergedRows = await db.listOutbox()
    const claimed = await db.claimOutbox(merged.operation_id)
    await db.updateOutbox(claimed.operation_id, { body: { title: 'illegal mutation' }, payload_json: 'illegal mutation', attempts: 1 })
    const reloaded = await db.listOutbox()
    const discarded = []
    const claimedOperation = claimed.operation_id
    return { dependencies: [child.dependency_operation_id, patch.dependency_operation_id], parentId: parent.operation_id,
      initialCount: first.length, cancelledOperation: cancellation.operation_id ?? null,
      afterCancellation: afterCancellation.length, oldOperation: original.operation_id, newOperation: merged.operation_id,
      mergedCount: mergedRows.length, mergedBody: merged.body, claimedState: claimed.state, claimedAttempts: claimed.attempts,
      reloadedState: reloaded[0]?.state, immutable: reloaded[0]?.payload_sha256 === merged.payload_sha256 && reloaded[0]?.payload_json === merged.payload_json,
      claimedOperation, confirmedDigest: merged.payload_sha256, discarded: discarded.length, remaining: (await db.listOutbox()).length }
  })
  expect(result.dependencies).toEqual([result.parentId, result.parentId])
  expect(result.initialCount).toBe(3)
  expect(result.cancelledOperation).toBeNull()
  expect(result.afterCancellation).toBe(0)
  expect(result.newOperation).not.toBe(result.oldOperation)
  expect(result.mergedCount).toBe(1)
  expect(result.mergedBody).toEqual({ title: 'first', pinned: true })
  expect(result.claimedState).toBe('outcome_unknown')
  expect(result.claimedAttempts).toBe(1)
  expect(result.reloadedState).toBe('outcome_unknown')
  expect(result.immutable).toBe(true)
  await page.reload()
  const reopened = await page.evaluate(async ({ operationId, digest }) => {
    const moduleUrl = '/src/lib/outbox-db.ts'
    const db = await import(moduleUrl)
    const rows = await db.listOutbox()
    const immutable = rows[0]?.payload_sha256 === digest &&
      (await db.payloadReceipt(rows[0].body)).payload_sha256 === digest
    let unknownDiscardRejected = false
    try { await db.discardOutboxTree(operationId) } catch { unknownDiscardRejected = true }
    const retained = await db.listOutbox()
    // Core fixture only: simulate a known business rejection, not a server ACK.
    await db.updateOutbox(operationId, { state: 'failed', last_error_code: 'HTTP_422' })
    const child = await db.enqueueOutbox({ ...retained[0], operation_id: undefined,
      operation_kind: 'task_item.create', resource: 'task_item', method: 'POST',
      path: '/api/tasks/existing/items', body: { id: 'discard-child', content: 'synthetic' },
      entity_id: 'discard-child', parent_id: 'existing', state: 'suppressed', attempts: 0,
      dependency_operation_id: operationId, last_error_code: 'PARENT_FAILED' })
    const discarded = await db.discardOutboxTree(operationId)
    return { state: rows[0]?.state, attempts: rows[0]?.attempts, immutable,
      unknownDiscardRejected, retained: retained.length,
      retainedDigest: retained[0]?.payload_sha256 === digest,
      descendantLinked: child.dependency_operation_id === operationId,
      discarded: discarded.length, remaining: (await db.listOutbox()).length }
  }, { operationId: result.claimedOperation, digest: result.confirmedDigest })
  expect(reopened).toEqual({ state: 'outcome_unknown', attempts: 1, immutable: true, unknownDiscardRejected: true, retained: 1, retainedDigest: true, descendantLinked: true, discarded: 2, remaining: 0 })
  console.log(JSON.stringify({ lane: 'real-indexeddb-core-only', result, reopened }))
})

test('API acknowledgment survives a cache reconciliation failure', async ({ page }) => {
  // A fixture transport proves this cache-failure boundary, not real API/PG/PWA.
  let requests = 0
  await page.route('**/api/tasks/confirmed-target', route => {
    requests += 1
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"id":"confirmed-target","title":"saved"}' })
  })
  await page.goto('/denied.html')
  const result = await page.evaluate(async () => {
    const fixtureUrl = '/e2e/outbox-core-fixture.ts'
    const fixture = await import(fixtureUrl)
    const client = new fixture.QueryClient()
    let recoveries = 0
    client.invalidateQueries = async () => { recoveries += 1 }
    fixture.outboxAdapters['task.update'].reconcileSuccess = async () => { throw new Error('synthetic cache failure') }
    await fixture.enqueueOutbox({ operation_kind: 'task.update', resource: 'task', method: 'PATCH',
      path: '/api/tasks/confirmed-target', body: { title: 'saved' }, entity_id: 'confirmed-target', parent_id: null,
      requires_private: false, idempotency_mode: 'absolute', dependency_operation_id: null, group_id: null,
      affected_query_keys: [['tasks']], state: 'pending', attempts: 0, next_attempt_at: null,
      created_at: Date.now(), last_error_code: null })
    await fixture.flushOutbox(client)
    return { rows: (await fixture.listOutbox()).map((row: { state: string }) => row.state), recoveries }
  })
  expect(requests).toBe(1)
  expect(result).toEqual({ rows: [], recoveries: 1 })
  console.log(JSON.stringify({ lane: 'fixture-transport-cache-boundary', result, requests }))
})

test('known loss of connectivity before dispatch restores attempts and pending payload', async ({ page }) => {
  let requests = 0
  await page.route('**/api/tasks/not-dispatched', route => { requests += 1; return route.abort() })
  await page.goto('/denied.html')
  const result = await page.evaluate(async () => {
    const fixtureUrl = '/e2e/outbox-core-fixture.ts'
    const fixture = await import(fixtureUrl)
    const client = new fixture.QueryClient()
    let predispatchEvents = 0
    window.addEventListener('microsched:outbox-not-attempted', () => { predispatchEvents += 1 })
    // The deterministic transition occurs during cancellation, before API transport.
    client.cancelQueries = async () => { Object.defineProperty(navigator, 'onLine', { configurable: true, value: false }) }
    const original = await fixture.enqueueOutbox({ operation_kind: 'task.update', resource: 'task', method: 'PATCH',
      path: '/api/tasks/not-dispatched', body: { title: 'retained' }, entity_id: 'not-dispatched', parent_id: null,
      requires_private: false, idempotency_mode: 'absolute', dependency_operation_id: null, group_id: null,
      affected_query_keys: [['tasks']], state: 'pending', attempts: 0, next_attempt_at: null,
      created_at: Date.now(), last_error_code: null })
    await fixture.flushOutbox(client)
    const rows = await fixture.listOutbox()
    return { state: rows[0]?.state, attempts: rows[0]?.attempts,
      retained: rows[0]?.payload_sha256 === original.payload_sha256, predispatchEvents }
  })
  expect(requests).toBe(0)
  expect(result).toEqual({ state: 'pending', attempts: 0, retained: true, predispatchEvents: 1 })
  console.log(JSON.stringify({ lane: 'known-not-attempted-core-boundary', result, requests }))
})


test('restores cancelled command trees atomically with fresh ordered dependencies and immutable payloads', async ({ page }) => {
  await page.goto('/denied.html')
  const result = await page.evaluate(async () => {
    const moduleUrl = '/src/lib/outbox-db.ts'
    const db = await import(moduleUrl)
    const command = (id: string, parent: string | null = null) => ({
      operation_kind: parent ? 'note_item.create' : 'note.create', resource: parent ? 'note_item' : 'note',
      method: 'POST', path: parent ? `/api/notes/${parent}/items` : '/api/notes',
      body: { id, ...(parent ? { content: 'private child', position: 0 } : { title: 'private parent', is_private: true }) },
      entity_id: id, parent_id: parent, requires_private: true, idempotency_mode: 'client_uuid',
      dependency_operation_id: null, group_id: null, affected_query_keys: [['notes']],
      state: 'pending', attempts: 0, next_attempt_at: null, created_at: Date.now(), last_error_code: null,
    })
    const parent = await db.enqueueOutbox(command('parent'))
    await db.enqueueOutbox(command('child', 'parent'))
    await db.enqueueOutbox({ ...command('child', 'parent'), operation_kind: 'note_item.update',
      method: 'PATCH', path: '/api/notes/parent/items/child', body: { is_completed: true }, idempotency_mode: 'absolute' })
    const cancellation = await db.enqueueOutbox({ ...command('parent'), operation_kind: 'note.delete',
      method: 'DELETE', path: '/api/notes/parent', body: null, idempotency_mode: 'postcondition' })
    const cancelled = cancellation.cancelled_rows
    const countAfterCancellation = (await db.listOutbox()).length
    let corruptionRejected = false
    try { await db.restoreCancelledOutbox(cancelled.map((row: { body: unknown }, index: number) => index ? row : { ...row, body: { id: 'parent', title: 'tampered' } })) }
    catch { corruptionRejected = true }
    const countAfterCorruption = (await db.listOutbox()).length
    const metadata = cancelled[1].requires_private
    cancelled[1].requires_private = false
    let metadataRejected = false
    try { await db.restoreCancelledOutbox(cancelled) } catch { metadataRejected = true }
    cancelled[1].requires_private = metadata
    let partialRejected = false
    try { await db.restoreCancelledOutbox(cancelled.slice(0, 1)) } catch { partialRejected = true }
    const restored = await db.restoreCancelledOutbox(cancelled)
    let duplicateRejected = false
    try { await db.restoreCancelledOutbox(cancelled) } catch { duplicateRejected = true }
    const countAfterDuplicate = (await db.listOutbox()).length
    const immutable = restored.every((row: { payload_sha256: string; payload_json: string; requires_private: boolean }, index: number) =>
      row.payload_sha256 === cancelled[index].payload_sha256 && row.payload_json === cancelled[index].payload_json && row.requires_private)
    return { parentOldId: parent.operation_id, cancelledCount: cancelled.length, countAfterCancellation,
      corruptionRejected, countAfterCorruption, metadataRejected, partialRejected, duplicateRejected, countAfterDuplicate, immutable,
      newIds: restored.map((row: { operation_id: number }) => row.operation_id),
      dependencies: restored.map((row: { dependency_operation_id: number | null }) => row.dependency_operation_id) }
  })
  expect(result.cancelledCount).toBe(3)
  expect(result.countAfterCancellation).toBe(0)
  expect(result.metadataRejected).toBe(true)
  expect(result.partialRejected).toBe(true)
  expect(result.corruptionRejected).toBe(true)
  expect(result.countAfterCorruption).toBe(0)
  expect(result.duplicateRejected).toBe(true)
  expect(result.countAfterDuplicate).toBe(3)
  expect(result.immutable).toBe(true)
  expect(result.newIds[0]).toBeGreaterThan(result.parentOldId)
  expect(result.dependencies).toEqual([null, result.newIds[0], result.newIds[1]])
  console.log(JSON.stringify({ lane: 'real-indexeddb-cancelled-undo', result }))
})


test('cross-tab undo attaches a new orphan child to its restored private parent before dispatch', async ({ context, page }) => {
  await page.goto('/denied.html')
  await page.evaluate(async () => {
    const fixtureUrl = '/e2e/outbox-core-fixture.ts'
    const fixture = await import(fixtureUrl)
    const parent = await fixture.enqueueOutbox({ operation_kind: 'note.create', resource: 'note', method: 'POST',
      path: '/api/notes', body: { id: 'parent', title: 'private', is_private: true }, entity_id: 'parent', parent_id: null,
      requires_private: true, idempotency_mode: 'client_uuid', dependency_operation_id: null, group_id: null,
      affected_query_keys: [['notes']], state: 'pending', attempts: 0, next_attempt_at: null, created_at: Date.now(), last_error_code: null })
    const receipt = await fixture.enqueueOutbox({ ...parent, operation_id: undefined, operation_kind: 'note.delete', method: 'DELETE',
      path: '/api/notes/parent', body: null, idempotency_mode: 'postcondition' })
    ;(window as unknown as { undoRows: unknown }).undoRows = receipt.cancelled_rows
  })
  const other = await context.newPage()
  await other.goto('/denied.html')
  await other.evaluate(async () => {
    const moduleUrl = '/src/lib/outbox-db.ts'
    const db = await import(moduleUrl)
    await db.enqueueOutbox({ operation_kind: 'note_item.create', resource: 'note_item', method: 'POST',
      path: '/api/notes/parent/items', body: { id: 'new-child', content: 'stale tab' }, entity_id: 'new-child', parent_id: 'parent',
      requires_private: false, idempotency_mode: 'client_uuid', dependency_operation_id: null, group_id: null,
      affected_query_keys: [['notes']], state: 'pending', attempts: 0, next_attempt_at: null, created_at: Date.now(), last_error_code: null })
  })
  let requests = 0
  await page.route('**/api/**', route => { requests += 1; return route.abort() })
  const result = await page.evaluate(async () => {
    const fixtureUrl = '/e2e/outbox-core-fixture.ts'
    const moduleUrl = '/src/lib/outbox-db.ts'
    const fixture = await import(fixtureUrl), db = await import(moduleUrl)
    const restored = await db.restoreCancelledOutbox((window as unknown as { undoRows: unknown }).undoRows)
    const client = new fixture.QueryClient()
    await fixture.flushOutbox(client)
    const rows = await db.listOutbox(), child = rows.find((row: { entity_id: string }) => row.entity_id === 'new-child')
    return { dependency: child.dependency_operation_id, parentId: restored[0].operation_id,
      private: child.requires_private, attempts: child.attempts, parentState: rows.find((row: { entity_id: string }) => row.entity_id === 'parent').state }
  })
  expect(requests).toBe(0)
  expect(result).toEqual({ dependency: result.parentId, parentId: result.parentId, private: true, attempts: 0, parentState: 'private_hold' })
  await other.close()
})


test('publishes the real public side-effect acknowledgement once and never publishes a held private result', async ({ page }) => {
  const report = { inserted: 2, skipped: [], duplicates: 1, removed: 3 }
  await page.route('**/api/calendar/sources/source/import', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(report) }))
  await page.goto('/denied.html')
  const result = await page.evaluate(async () => {
    const fixtureUrl = '/e2e/outbox-core-fixture.ts'
    const fixture = await import(fixtureUrl), client = new fixture.QueryClient()
    const events: unknown[] = []
    window.addEventListener('microsched:outbox-acknowledged', ((event: CustomEvent) => events.push({ operation: event.detail.row.operation_kind, response: event.detail.response })) as EventListener)
    const row = { operation_kind: 'calendar.import', resource: 'calendar', method: 'POST', path: '/api/calendar/sources/source/import',
      body: { content: 'BEGIN:VCALENDAR' }, entity_id: 'source', parent_id: 'source', requires_private: false,
      idempotency_mode: 'side_effect', dependency_operation_id: null, group_id: null, affected_query_keys: [['calendar']],
      state: 'pending', attempts: 0, next_attempt_at: null, created_at: Date.now(), last_error_code: null }
    await fixture.enqueueOutbox(row)
    await fixture.flushOutbox(client)
    await fixture.enqueueOutbox({ ...row, requires_private: true })
    await fixture.flushOutbox(client)
    const rows = await fixture.listOutbox()
    return { events, remaining: rows.map((entry: { state: string; attempts: number }) => ({ state: entry.state, attempts: entry.attempts })) }
  })
  expect(result.events).toEqual([{ operation: 'calendar.import', response: report }])
  expect(result.remaining).toEqual([{ state: 'private_hold', attempts: 0 }])
})


test('undo uses the authenticated snapshot across asynchronous caller metadata mutation', async ({ page }) => {
  await page.goto('/denied.html')
  const result = await page.evaluate(async () => {
    const moduleUrl = '/src/lib/outbox-db.ts'
    const db = await import(moduleUrl)
    const row = { operation_kind: 'note.create', resource: 'note', method: 'POST', path: '/api/notes',
      body: { id: 'snapshot-parent', title: 'private', is_private: true }, entity_id: 'snapshot-parent', parent_id: null,
      requires_private: true, idempotency_mode: 'client_uuid', dependency_operation_id: null, group_id: null,
      affected_query_keys: [['notes']], state: 'pending', attempts: 0, next_attempt_at: null, created_at: Date.now(), last_error_code: null }
    await db.enqueueOutbox(row)
    const cancelled = await db.enqueueOutbox({ ...row, operation_kind: 'note.delete', method: 'DELETE', path: '/api/notes/snapshot-parent', body: null, idempotency_mode: 'postcondition' })
    const restoring = db.restoreCancelledOutbox(cancelled.cancelled_rows)
    cancelled.cancelled_rows[0].requires_private = false
    cancelled.cancelled_rows[0].path = '/api/public-route'
    const restored = await restoring
    return { private: restored[0].requires_private, path: restored[0].path }
  })
  expect(result).toEqual({ private: true, path: '/api/notes' })
})

test('private annotation delete waits for live unlock and retains its original command', async ({ page }) => {
  let requests = 0
  const id = '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f5501'
  await page.route(`**/api/calendar/annotations/${id}`, route => {
    requests += 1
    return route.fulfill({ status: 204 })
  })
  await page.goto('/denied.html')
  const held = await page.evaluate(async (id) => {
    const fixtureUrl = '/e2e/outbox-core-fixture.ts'
    const fixture = await import(fixtureUrl)
    const client = new fixture.QueryClient()
    const encoded = fixture.outboxAdapters['day_annotation.delete'].encodeCommand({
      ...fixture.annotationDeleteInput({ id, is_private: true }), operationKind: 'day_annotation.delete',
    })
    const original = await fixture.enqueueOutbox({ ...encoded, state: 'pending', attempts: 0,
      next_attempt_at: null, created_at: Date.now(), last_error_code: null })
    await fixture.flushOutbox(client)
    const rows = await fixture.listOutbox()
    return { originalId: original.operation_id, digest: original.payload_sha256,
      rows: rows.map((row: { operation_id: number; state: string; attempts: number; requires_private: boolean; payload_sha256: string }) =>
        ({ id: row.operation_id, state: row.state, attempts: row.attempts, private: row.requires_private, digest: row.payload_sha256 })) }
  }, id)
  expect(requests).toBe(0)
  expect(held.rows).toEqual([{ id: held.originalId, state: 'private_hold', attempts: 0, private: true, digest: held.digest }])
  const remaining = await page.evaluate(async () => {
    const fixtureUrl = '/e2e/outbox-core-fixture.ts'
    const fixture = await import(fixtureUrl), client = new fixture.QueryClient()
    client.setQueryData(['session'], { private_until: new Date(Date.now() + 60_000).toISOString() })
    await fixture.flushOutbox(client)
    return (await fixture.listOutbox()).length
  })
  expect(requests).toBe(1)
  expect(remaining).toBe(0)
})

test('held parent propagates exact private/auth state to its child and independent public work still flushes', async ({ browser }) => {
  for (const hold of ['private_hold', 'auth_hold'] as const) {
    const context = await browser.newContext()
    const page = await context.newPage()
    const requests: string[] = []
    let released = false
    await page.route('**/api/**', async route => {
      const req = route.request(), path = new URL(req.url()).pathname
      requests.push(path)
      await route.fulfill({ status: path === '/api/tasks/held-parent' && !released ? 401 : 200,
        contentType: 'application/json', body: JSON.stringify(path === '/api/tasks/held-parent' && !released
          ? { detail: 'Not authenticated' } : { id: path.split('/').pop(), title: 'public', is_private: false }) })
    })
    await page.goto('/denied.html')
    const result = await page.evaluate(async (hold) => {
      const fixture = await import('/e2e/outbox-core-fixture.ts')
      const client = new fixture.QueryClient()
      Reflect.set(window, '__qaHoldClient', client)
      const command = (id: string, priv: boolean) => ({
        operation_kind: 'task.update', resource: 'task', method: 'PATCH', path: '/api/tasks/' + id,
        body: { title: id }, entity_id: id, parent_id: null, requires_private: priv,
        idempotency_mode: 'absolute', dependency_operation_id: null, group_id: null,
        affected_query_keys: [['tasks']], state: 'pending', attempts: 0, next_attempt_at: null,
        created_at: Date.now(), last_error_code: null,
      })
      const parent = await fixture.enqueueOutbox(command('held-parent', hold === 'private_hold'))
      const child = await fixture.enqueueOutbox({ ...command('held-child', hold === 'private_hold'),
        parent_id: 'held-parent', dependency_operation_id: parent.operation_id })
      await fixture.enqueueOutbox(command('independent', false))
      const before = await fixture.listOutbox()
      await fixture.flushOutbox(client)
      const after = await fixture.listOutbox()
      return { parentId: parent.operation_id, childId: child.operation_id,
        before: before.map(row => ({ id: row.operation_id, hash: row.payload_sha256, bytes: row.payload_byte_length })),
        after: after.map(row => ({ id: row.operation_id, state: row.state, hash: row.payload_sha256, bytes: row.payload_byte_length, attempts: row.attempts })) }
    }, hold)
    console.log(JSON.stringify({ scenario: 'exact-parent-hold-cascade', hold, requests, result }))
    expect(requests).not.toContain('/api/tasks/held-child')
    expect(requests.filter(path => path === '/api/tasks/independent')).toHaveLength(1)
    expect(result.after).toHaveLength(2)
    expect(result.after.map(row => row.state)).toEqual([hold, hold])
    for (const row of result.after) {
      expect(row.hash).toBe(result.before.find(before => before.id === row.id)?.hash)
      expect(row.bytes).toBe(result.before.find(before => before.id === row.id)?.bytes)
      expect(row.attempts).toBe(0)
    }
    const replayStart = requests.length
    released = true
    const resumed = await page.evaluate(async () => {
      const fixture = await import('/e2e/outbox-core-fixture.ts')
      const client = Reflect.get(window, '__qaHoldClient')
      client.setQueryData(['session'], { private_until: new Date(Date.now() + 60_000).toISOString() }, { updatedAt: Date.now() + 1 })
      await fixture.flushOutbox(client)
      return (await fixture.listOutbox()).map(row => row.operation_id)
    })
    expect(requests.slice(replayStart)).toEqual(['/api/tasks/held-parent', '/api/tasks/held-child'])
    expect(resumed).toEqual([])
    console.log(JSON.stringify({ scenario: 'exact-parent-hold-release', hold, replayOrder: requests.slice(replayStart), finalQueue: resumed.length }))
    await context.close()
  }
})
