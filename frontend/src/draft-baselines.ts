/** A visibility change may remove private forms; connected public forms keep their baseline. */
export function pruneDraftBaselines<T extends { isConnected: boolean }>(drafts: Map<T, string>) {
  for (const form of drafts.keys()) if (!form.isConnected) drafts.delete(form)
}
