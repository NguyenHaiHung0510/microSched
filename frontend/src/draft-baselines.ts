/** A visibility change may remove private forms; connected public forms keep their baseline. */
export function pruneDraftBaselines<T extends { isConnected: boolean }>(drafts: Map<T, string>) {
  for (const form of drafts.keys()) if (!form.isConnected) drafts.delete(form)
}

export function formValue(form: HTMLFormElement): string {
  return JSON.stringify([...form.querySelectorAll('input,textarea,select,[role="checkbox"],[role="combobox"]')].map(element => {
    if(element instanceof HTMLInputElement) return [element.name,element.type,['checkbox','radio'].includes(element.type)?element.checked:element.value]
    if(element instanceof HTMLTextAreaElement||element instanceof HTMLSelectElement)return [element.name,element.value]
    return [element.getAttribute('role'),element.getAttribute('aria-checked'),element.textContent]
  }))
}

export const activeDraftBaselines = new Map<HTMLFormElement,string>()
export function hasUnsavedFormChanges(): boolean {
  return !!document.querySelector('[data-update-dirty="true"]') || [...activeDraftBaselines].some(([form,initial])=>form.isConnected&&!form.hasAttribute('data-draft-owner')&&formValue(form)!==initial)
}
