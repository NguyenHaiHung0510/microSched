// Test-only browser module; production entrypoints do not import this file.
export { QueryClient } from '@tanstack/react-query'
export { outboxAdapters } from '../src/lib/outbox-adapters'
export { enqueueOutbox, listOutbox } from '../src/lib/outbox-db'
export { flushOutbox } from '../src/lib/outbox-flush'

export { annotationDeleteInput } from '../src/annotation-write'
