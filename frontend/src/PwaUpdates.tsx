import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { registerSW } from 'virtual:pwa-register'
import { getSnapshot, subscribe } from '@/outbox/core'
import { activeDraftBaselines, formValue, hasUnsavedFormChanges, pruneDraftBaselines } from '@/draft-baselines'
import { hasMimiComposerDrafts } from '@/mimi-selection'
import { hasUnsentSupplement } from '@/mimi-positive-supplement'
import { hasUnsentRetainedMimiFeedback } from '@/mimi-feedback-state'
import { safeAutomaticUpdate } from '@/pwa-update'

export function PwaUpdates() {
  const client = useQueryClient()
  useEffect(() => {
    let waiting = false, activated = false, applying = false, failed = false, stopped = false, composing = false, scheduled = false
    let controller = navigator.serviceWorker?.controller
    const drafts = activeDraftBaselines
    const captureForms = () => {
      pruneDraftBaselines(drafts)
      for (const form of document.querySelectorAll<HTMLFormElement>('form:not([data-draft-owner])')) if (!drafts.has(form)) drafts.set(form, formValue(form))
    }
    const safe = () => {
      const state = getSnapshot()
      const feedback = client.getQueryCache().getAll().some(query => {
        if (query.queryKey[0] !== 'mimi-feedback-draft') return false
        if (query.queryKey[1] === 'negative-flow') return hasUnsentRetainedMimiFeedback(query.state.data as Record<string, unknown> | undefined)
        return hasUnsentSupplement(query.state.data as Parameters<typeof hasUnsentSupplement>[0])
      })
      return safeAutomaticUpdate({
        dirty: hasUnsavedFormChanges() || hasMimiComposerDrafts() || feedback || !!document.querySelector('[data-update-dirty="true"]'),
        composing, mutating: client.isMutating() > 0 || !!document.querySelector('[data-update-busy="true"]'),
        admitting: state.admitting, storageReady: state.revision > 0 && !state.error,
        sending: state.rows.some(row => row.state === 'sending' || row.state === 'unknown'),
      })
    }
    const apply = () => {
      if (stopped || !waiting || failed || !safe()) return
      if (activated) {
        waiting = false
        window.location.reload()
      } else if (!applying) {
        applying = true
        // Activation does not own reload: controllerchange rechecks this tab's
        // current drafts. Another tab may safely activate while this one edits.
        void update(false).catch(() => { failed = true; applying = false })
      }
    }
    const schedule = () => {
      if (scheduled || stopped) return
      scheduled = true
      queueMicrotask(() => { scheduled = false; apply() })
    }
    const beforeEdit = () => { captureForms() }
    const changed = () => { captureForms(); schedule() }
    const startComposition = () => { composing = true }
    const endComposition = () => { composing = false; schedule() }
    const controlled = () => {
      const next = navigator.serviceWorker.controller
      if (controller && next !== controller) { activated = true; waiting = true }
      controller = next
      schedule()
    }
    captureForms()
    document.addEventListener('focusin', beforeEdit, true)
    document.addEventListener('beforeinput', beforeEdit, true)
    document.addEventListener('input', changed, true)
    document.addEventListener('change', changed, true)
    document.addEventListener('compositionstart', startComposition, true)
    document.addEventListener('compositionend', endComposition, true)
    window.addEventListener('microsched:visibility', changed)
    window.addEventListener('mimi-composer-changed', changed)
    window.addEventListener('focus', changed)
    navigator.serviceWorker?.addEventListener('controllerchange', controlled)
    const dom = new MutationObserver(changed)
    dom.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['data-update-dirty', 'data-update-busy']})
    const unsubscribe = subscribe(schedule)
    const mutations = client.getMutationCache().subscribe(schedule)
    const queries = client.getQueryCache().subscribe(schedule)
    const update = registerSW({immediate: true, onNeedRefresh: () => { waiting = true; schedule() }, onNeedReload: () => { activated = true; waiting = true; schedule() }})
    schedule()
    return () => {
      stopped = true; dom.disconnect(); unsubscribe(); mutations(); queries()
      document.removeEventListener('focusin', beforeEdit, true)
      document.removeEventListener('beforeinput', beforeEdit, true)
      document.removeEventListener('input', changed, true)
      document.removeEventListener('change', changed, true)
      document.removeEventListener('compositionstart', startComposition, true)
      document.removeEventListener('compositionend', endComposition, true)
      window.removeEventListener('microsched:visibility', changed)
      window.removeEventListener('mimi-composer-changed', changed)
      window.removeEventListener('focus', changed)
      navigator.serviceWorker?.removeEventListener('controllerchange', controlled)
    }
  }, [client])
  return null
}
