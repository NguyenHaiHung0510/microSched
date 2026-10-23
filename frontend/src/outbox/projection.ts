import type { Fields, Command } from './protocol'
export function taskFrom(command:Pick<Command,'entity'|'payload'|'created_at'>):Fields {
  const p=JSON.parse(command.payload) as Fields
  const children=(p.items as string[]??[]).map((content,index) => ({
    id:(p.item_ids as string[])[index],content,is_completed:false,position:index,created_at:command.created_at,updated_at:command.created_at,
  }))
  return {id:command.entity,title:'',body_md:null,status:'open',priority:null,pinned:false,is_private:false,
    due_precision:'none',due_on:null,due_at:null,created_at:command.created_at,updated_at:command.created_at,
    ...p,items:children}
}
export function projectTasks<T>(baseline:T[],commands:Command[],status='all'):T[] {
  const rows=new Map<string,Fields>(baseline.map(raw => { const r=raw as Fields;return [String(r.id),{...r,items:[...(r.items as Fields[]??[])]}] }))
  for (const command of commands) {
    if (command.kind.startsWith('entry.')) continue
    const p=JSON.parse(command.payload) as Fields, id=command.entity
    if (command.kind==='task.create') {
      const existing=rows.get(id)
      rows.set(id,existing?{...taskFrom(command),...existing}:taskFrom(command));continue
    }
    if (command.kind==='task.delete') { rows.delete(id);continue }
    const task=rows.get(command.parent)
    if (!task) continue // Restore with no authorized baseline remains visibly pending.
    if (command.kind==='task.update') rows.set(id,{...task,...p,updated_at:command.created_at})
    if (command.kind.startsWith('task_item.')) {
      const items=[...(task.items as Fields[]??[])], index=items.findIndex(i => i.id===id)
      if (command.kind==='task_item.delete') { if(index>=0)items.splice(index,1) }
      else if (command.kind==='task_item.create') {
        if(index<0)items.push({is_completed:false,...p})
      } else if(index>=0) items[index]={...items[index],...p}
      rows.set(command.parent,{...task,items:items.sort((a,b) => Number(a.position)-Number(b.position))})
    }
  }
  return [...rows.values()].filter(r => status==='all'||r.status===status) as T[]
}
export function entryFrom(command:Pick<Command,'entity'|'parent'|'payload'|'created_at'>):Fields {
  return {id:command.entity,tracker_id:command.parent,occurred_at:command.created_at,quantity:null,amount:null,list_amount:null,note_md:null,
    created_at:command.created_at,updated_at:command.created_at,...JSON.parse(command.payload)}
}
export function projectEntries<T>(baseline:T[],commands:Command[],url:string):T[] {
  const rows=new Map(baseline.map(raw => {const r=raw as Fields;return [String(r.id),r]}))
  for(const command of commands) {
    if(!command.kind.startsWith('entry.'))continue
    const p=JSON.parse(command.payload) as Fields
    if(command.kind==='entry.create') rows.set(command.entity,{...entryFrom(command),...rows.get(command.entity)})
    if(command.kind==='entry.update' && rows.has(command.entity))rows.set(command.entity,{...rows.get(command.entity),...p})
    if(command.kind==='entry.delete')rows.delete(command.entity)
  }
  const params=new URL(url,'http://localhost').searchParams
  const from=params.get('from'),to=params.get('to'),tracker=params.get('tracker_id')
  const compare=(a:Fields,b:Fields) => (params.get('order')==='asc'?1:-1)*String(a.occurred_at).localeCompare(String(b.occurred_at))||String(a.id).localeCompare(String(b.id))
  let filtered=[...rows.values()].filter(r => (!tracker||r.tracker_id===tracker) &&
    (!from||Date.parse(String(r.occurred_at))>=Date.parse(from)) && (!to||Date.parse(String(r.occurred_at))<Date.parse(to)))
  filtered=filtered.sort(compare)
  return filtered.slice(0,Number(params.get('limit')??100)) as T[]
}
