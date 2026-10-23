import { useSyncExternalStore } from 'react'
import { getSnapshot, subscribe, visibleCommands, unlocked, known } from './core'
import { projectTasks, projectEntries } from './projection'
export function useOutbox() { return useSyncExternalStore(subscribe,getSnapshot,getSnapshot) }
export function useTaskProjection<T>(baseline:T[],status='all'):T[] {
  useOutbox()
  const commands=visibleCommands()
  const restored=commands.filter(r => r.kind==='task.restore').map(r => known('task',r.entity)).filter(Boolean) as T[]
  const merged=[...new Map([...baseline,...restored].map(r => [(r as {id:string}).id,r])).values()]
  return projectTasks(merged,commands,status).filter(row => !(row as {is_private?:boolean}).is_private||unlocked())
}
export function useEntryProjection<T>(baseline:T[],url:string):T[] {
  useOutbox()
  const commands=visibleCommands()
  const restored=commands.filter(r => r.kind==='entry.restore').map(r => known('entry',r.entity)).filter(Boolean) as T[]
  return projectEntries([...new Map([...baseline,...restored].map(r => [(r as {id:string}).id,r])).values()],commands,url).filter(row => unlocked() || known('tracker',String((row as {tracker_id:string}).tracker_id))?.is_private===false)
}

export function useDerivedPending():boolean {
  const state=useOutbox()
  return state.rows.some(r => r.principal===state.context.principal&&r.kind.startsWith('entry.'))||state.reconciling.some(a => a.startsWith('tracker:'))
}
