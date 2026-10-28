import { useEffect, useMemo, useRef, useState, type SetStateAction } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

type Fields = Record<string, unknown>
const key = (id: string | null | undefined) => ['mimi-feedback-draft', 'negative-flow', id ?? 'current']

export function hasUnsentRetainedMimiFeedback(fields: Fields | undefined): boolean {
  return !!(fields?.draft || fields?.expected || fields?.intent
    || (Array.isArray(fields?.reasons) && fields.reasons.length && !fields.acknowledgment))
}

export function useRetainedMimiFeedback(id: string | null | undefined) {
  // Same memory-only lifecycle as positive supplements. Nothing is written to
  // storage or sent on opening/closing a surface. Logout replaces the client.
  useQuery({ queryKey: key(id), queryFn: (): Fields => ({}), initialData: {}, enabled: false, gcTime: Infinity })
}

export function useMimiFeedbackField<T>(id: string | null | undefined, field: string, initial: T): [T, (next: SetStateAction<T>) => void] {
  const client = useQueryClient()
  const read = () => {
    const fields = client.getQueryData<Fields>(key(id))
    return fields && Object.hasOwn(fields, field) ? fields[field] as T : initial
  }
  const [value, setValue] = useState<T>(read)
  const live = useRef(value)
  // A late ACK from the old dock instance can settle this same draft after a
  // workspace/remount. Controlled edits still update React synchronously.
  useEffect(() => client.getQueryCache().subscribe(event => {
    if (event.type !== 'updated' || JSON.stringify(event.query.queryKey) !== JSON.stringify(key(id))) return
    const fields = client.getQueryData<Fields>(key(id))
    if (!fields || !Object.hasOwn(fields, field)) return
    const next = fields[field] as T
    if (next !== live.current) { live.current = next; setValue(next) }
  }), [client, id, field])
  return [value, action => {
    const previous = read()
    const next = typeof action === 'function' ? (action as (old: T) => T)(previous) : action
    live.current = next
    setValue(next)
    client.setQueryData<Fields>(key(id), old => ({ ...old, [field]: next }))
  }]
}

export function useMimiFeedbackRevision(id: string | null | undefined) {
  const client = useQueryClient()
  // Read the latest revision even when a previous instance receives an ACK.
  return useMemo(() => ({
    read: () => (client.getQueryData<Fields>(key(id))?.revision as number | undefined) ?? 0,
    bump: () => client.setQueryData<Fields>(key(id), old => ({ ...old, revision: ((old?.revision as number | undefined) ?? 0) + 1 })),
  }), [client, id])
}
