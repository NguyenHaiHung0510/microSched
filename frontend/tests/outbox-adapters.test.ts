import { describe, expect, it } from 'vitest'
import { adapterFor } from '../src/lib/outbox-adapters'

describe('typed domain command encoding', () => {
  it('keeps a task create UUID and server route/body with task query keys', () => {
    const command = adapterFor('task.create').encodeCommand({
      operationKind: 'task.create',
      path: '/api/tasks',
      body: { id: '0199abc0-0000-7000-8000-000000000001', title: 'Việc', status: 'open', items: [] },
    })
    expect(command).toMatchObject({
      operation_kind: 'task.create',
      resource: 'task',
      method: 'POST',
      path: '/api/tasks',
      entity_id: '0199abc0-0000-7000-8000-000000000001',
      parent_id: null,
      requires_private: false,
      idempotency_mode: 'client_uuid',
      affected_query_keys: [['tasks'], ['calendar', 'tasks']],
    })
    expect(command.body).toEqual({ id: '0199abc0-0000-7000-8000-000000000001', title: 'Việc', status: 'open', items: [] })
    expect(Object.keys(command).sort()).toEqual([
      'affected_query_keys', 'body', 'dependency_operation_id', 'entity_id', 'group_id',
      'idempotency_mode', 'method', 'operation_kind', 'parent_id', 'path', 'requires_private', 'resource',
    ].sort())
  })

  it('encodes atomic note-item reorder as one absolute command', () => {
    const input = {
      operationKind: 'note_item.reorder' as const,
      path: '/api/notes/0199abc0-0000-7000-8000-000000000002/items/positions',
      body: { items: [{ id: '0199abc0-0000-7000-8000-000000000003', position: 1 }, { id: '0199abc0-0000-7000-8000-000000000004', position: 0 }] },
      parentId: '0199abc0-0000-7000-8000-000000000002',
    }
    const command = adapterFor('note_item.reorder').encodeCommand(input)
    expect(command).toMatchObject({
      method: 'PATCH',
      path: '/api/notes/0199abc0-0000-7000-8000-000000000002/items/positions',
      body: input.body,
      parent_id: '0199abc0-0000-7000-8000-000000000002',
      idempotency_mode: 'absolute',
      affected_query_keys: [['notes']],
    })
  })

  it('rejects an operation paired with a different route and retains private metadata', () => {
    expect(() => adapterFor('task.delete').encodeCommand({
      operationKind: 'task.delete',
      path: '/api/notes/0199abc0-0000-7000-8000-000000000005',
      entityId: 'task-1',
    })).toThrow(/Invalid route/)
    const command = adapterFor('note.update').encodeCommand({
      operationKind: 'note.update',
      path: '/api/notes/0199abc0-0000-7000-8000-000000000005',
      body: { title: 'Riêng tư' },
      entityId: '0199abc0-0000-7000-8000-000000000005',
      requiresPrivate: true,
      dependencyOperationId: 7,
      groupId: 'group-2',
    })
    expect(command).toMatchObject({
      entity_id: '0199abc0-0000-7000-8000-000000000005',
      requires_private: true,
      dependency_operation_id: 7,
      group_id: 'group-2',
    })
  })

  it('accepts existing RFC UUIDv4 entity and parent IDs while keeping create IDs UUIDv7-only', () => {
    const existingId = '550e8400-e29b-41d4-a716-446655440000'
    expect(adapterFor('task.update').encodeCommand({
      operationKind: 'task.update',
      path: `/api/tasks/${existingId}`,
      entityId: existingId,
      body: { title: 'Existing task' },
    })).toMatchObject({ entity_id: existingId, path: `/api/tasks/${existingId}` })

    expect(adapterFor('task_item.create').encodeCommand({
      operationKind: 'task_item.create',
      path: `/api/tasks/${existingId}/items`,
      parentId: existingId,
      body: { id: '0199abc0-0000-7000-8000-000000000009', content: 'child' },
    })).toMatchObject({ parent_id: existingId, entity_id: '0199abc0-0000-7000-8000-000000000009' })

    expect(() => adapterFor('task.update').encodeCommand({
      operationKind: 'task.update',
      path: '/api/tasks/not-a-uuid',
      entityId: 'not-a-uuid',
      body: { title: 'Malformed' },
    })).toThrow(/Invalid entity UUID/)
    expect(() => adapterFor('task.create').encodeCommand({
      operationKind: 'task.create',
      path: '/api/tasks',
      body: { id: '550e8400-e29b-41d4-a716-446655440000', title: 'Old ID on create' },
    })).toThrow(/UUIDv7/)
  })

  it('preserves reminder PUT freshness tokens and exact revisioned DELETE route', () => {
    const sourceId = '550e8400-e29b-41d4-a716-446655440000'
    const reminderId = '550e8400-e29b-41d4-a716-446655440001'
    const body = {
      id: '0199abc0-0000-7000-8000-000000000021',
      mode: 'absolute',
      due_at: '2026-10-02T03:00:00Z',
      expected_id: reminderId,
      expected_revision: 7,
      expected_source_updated_at: '2026-10-01T01:00:00Z',
    }
    expect(adapterFor('reminder.save').encodeCommand({
      operationKind: 'reminder.save',
      path: `/api/reminders/task/${sourceId}`,
      body,
      entityId: body.id,
      parentId: sourceId,
      requiresPrivate: true,
    })).toMatchObject({ method: 'PUT', body, entity_id: body.id, parent_id: sourceId, requires_private: true, idempotency_mode: 'client_uuid' })
    const cancelPath = `/api/reminders/${reminderId}?revision=7`
    expect(adapterFor('reminder.cancel').encodeCommand({
      operationKind: 'reminder.cancel',
      path: cancelPath,
      entityId: reminderId,
      parentId: sourceId,
      requiresPrivate: true,
    })).toMatchObject({ method: 'DELETE', path: cancelPath, entity_id: reminderId, parent_id: sourceId, requires_private: true })
  })
})
