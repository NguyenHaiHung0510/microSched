import assert from 'node:assert/strict'
import { test } from 'vitest'

import {
  canSubmitTask,
  taskInvalidationKey,
  taskPayload,
  taskQueryKey,
  toggledStatus,
} from '../src/task-ui.ts'

test('task form normalizes optional values at the API boundary', () => {
  assert.deepEqual(
    taskPayload({
      title: 'Chuẩn bị họp',
      body: '',
      priority: '',
      dueAt: '',
      isPrivate: true,
    }),
    {
      title: 'Chuẩn bị họp',
      body_md: null,
      priority: null,
      due_at: null,
      is_private: true,
    },
  )
})

test('task query keys separate filters while mutations invalidate the family', () => {
  assert.deepEqual(taskQueryKey('open'), ['tasks', 'open'])
  assert.deepEqual(taskQueryKey('completed'), ['tasks', 'completed'])
  assert.deepEqual(taskInvalidationKey, ['tasks'])
})

test('pending submit is disabled so a fast second click cannot duplicate a task', () => {
  assert.equal(canSubmitTask('Việc mới', false), true)
  assert.equal(canSubmitTask('Việc mới', true), false)
  assert.equal(canSubmitTask('', false), false)
})

test('completion checkbox maps to the two API status values', () => {
  assert.equal(toggledStatus(true), 'completed')
  assert.equal(toggledStatus(false), 'open')
})
