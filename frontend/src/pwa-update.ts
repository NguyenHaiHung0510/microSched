type UpdateBoundary = {dirty: boolean; composing: boolean; mutating: boolean; admitting: number; storageReady: boolean; sending: boolean}

/** Durable idle pending commands survive reload; uncertain/in-flight work does not. */
export function safeAutomaticUpdate(state: UpdateBoundary): boolean {
  return state.storageReady && !state.dirty && !state.composing && !state.mutating && state.admitting === 0 && !state.sending
}

/** Saved feedback may retain its selected reasons; only unsent intent blocks. */
export function hasUnsentFeedback(text: string, expected: string, reasons: readonly string[], acknowledged: boolean): boolean {
  return !!(text || expected || reasons.length && !acknowledged)
}
