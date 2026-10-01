import assert from 'node:assert/strict'
import { afterEach, test } from 'vitest'

import {
  advanceWorkflowPilotRun,
  createWorkflowPilotRun,
  getWorkflowPilotRun,
  listWorkflowPilotRuns,
  listWorkflowPilotTasks,
  type WorkflowPilotStatus,
} from '../src/workflow-pilot-api.ts'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })

test('task and run recovery reads use only the frozen GET routes', async () => {
  const requests: Array<{ path: RequestInfo | URL; init?: RequestInit }> = []
  globalThis.fetch = async (path, init) => {
    requests.push({ path, init })
    return new Response(JSON.stringify({ items: [] }), { status: 200 })
  }

  await listWorkflowPilotTasks()
  await listWorkflowPilotRuns()
  await getWorkflowPilotRun('run id/1')

  assert.deepEqual(requests.map(({ path, init }) => [path, init?.method ?? 'GET']), [
    ['/api/mimi/workflow-pilot/tasks', 'GET'],
    ['/api/mimi/workflow-pilot/runs', 'GET'],
    ['/api/mimi/workflow-pilot/runs/run%20id%2F1', 'GET'],
  ])
})

test('start sends the retained UUID, selected Task IDs, engine, and CSRF once', async () => {
  let captured: { path: RequestInfo | URL; init?: RequestInit } | undefined
  let calls = 0
  globalThis.fetch = async (path, init) => {
    calls += 1
    captured = { path, init }
    return new Response(JSON.stringify({ run_id: 'run-1' }), { status: 200 })
  }

  await createWorkflowPilotRun('run-1', ['task-1', 'task-2'], 'graph')

  assert.equal(calls, 1)
  assert.equal(captured?.path, '/api/mimi/workflow-pilot/runs')
  assert.equal((captured?.init?.headers as Record<string, string>)['X-Mimi-CSRF'], '1')
  assert.deepEqual(JSON.parse(String(captured?.init?.body)), {
    run_id: 'run-1', task_ids: ['task-1', 'task-2'], engine: 'graph',
  })
})

test('advance sends exactly one generation-bound direction, confirmation, cancel, or resume action', async () => {
  const captured: RequestInit[] = []
  globalThis.fetch = async (_path, init) => {
    captured.push(init ?? {})
    return new Response(JSON.stringify({ run_id: 'run-1' }), { status: 200 })
  }
  const run = { run_id: 'run-1', generation: 7 } as WorkflowPilotStatus
  const actions = [
    { direction: 'apply_prefix' },
    { preview_digest: 'digest-1' },
    { cancel: true },
    { resume: true },
  ] as const

  for (const action of actions) await advanceWorkflowPilotRun(run, action)

  assert.equal(captured.length, actions.length)
  captured.forEach((init, index) => {
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    assert.equal(init.method, 'POST')
    assert.equal((init.headers as Record<string, string>)['X-Mimi-CSRF'], '1')
    assert.equal(body.generation, 7)
    assert.deepEqual(Object.keys(body).filter((key) => key !== 'generation'), [Object.keys(actions[index])[0]])
  })
})

test('a failed POST is surfaced once without a blind network retry', async () => {
  let calls = 0
  globalThis.fetch = async () => {
    calls += 1
    throw new TypeError('offline')
  }

  await assert.rejects(createWorkflowPilotRun('same-run-id', ['task-1'], 'control'))
  assert.equal(calls, 1)
})
