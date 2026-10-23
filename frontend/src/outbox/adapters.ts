/** Explicit Task and Entry mutation surfaces. Reads keep the existing API path. */
import { apiRequest } from '@/api'
import { uuidv7 } from '@/lib/uuidv7'
import { admit, barrier, getSnapshot, known, cancelledParent, visibleCommands } from './core'
import { taskFrom, entryFrom, projectTasks, projectEntries } from './projection'
import { route, type Fields, type Kind } from './protocol'
type Init = RequestInit & {timeoutMs?:number}
function payload(init:Init):Fields {
  if(!init.body)return {}
  if(typeof init.body!=='string')throw new Error('Unsupported command body')
  const p:unknown=JSON.parse(init.body)
  if(!p||typeof p!=='object'||Array.isArray(p))throw new Error('Invalid command body')
  return p as Fields
}
export async function taskRequest<T>(path:string,init?:Init):Promise<T> {
  const method=(init?.method??'GET').toUpperCase()
  if(method==='GET')return apiRequest<T>(path,init)
  const match=/^\/api\/tasks(?:\/([0-9a-f-]+)(?:\/(restore|items)(?:\/([0-9a-f-]+))?)?)?$/.exec(path)
  if(!match)throw new Error('Unsupported Task write surface')
  const p=payload(init??{}),parent=match[1]??String(p.id??uuidv7()),item=match[2]==='items'
  let kind:Kind
  if(item)kind=method==='POST'?'task_item.create':method==='PATCH'?'task_item.update':'task_item.delete'
  else kind=match[2]==='restore'?'task.restore':!match[1]?'task.create':method==='PATCH'?'task.update':'task.delete'
  const entity=item?(match[3]??String(p.id??uuidv7())):parent
  if(kind==='task.create') {
    p.id=entity;p.items??=[];p.item_ids??=(p.items as string[]).map(() => uuidv7())
  }
  if(kind==='task_item.create')p.id=entity
  const before=known('task',parent)
  if(route({kind,entity,parent}).method!==method||route({kind,entity,parent}).path!==path)throw new Error('Invalid typed method')
  const command=await admit(kind,entity,parent,p)
  if(kind==='task.create')return {...taskFrom(command),local_acceptance:true} as T
  const projected=projectTasks(before?[before]:[],visibleCommands())
  const task=projected.find(t => t.id===parent)
  if(item)return ((task?.items as Fields[]??[]).find(i => i.id===entity)??{...known('item',entity),...p,id:entity}) as T
  return ({...before,...task,...p,id:entity,local_acceptance:true}) as T
}
export async function entryRequest<T>(path:string,init?:Init):Promise<T> {
  const method=(init?.method??'GET').toUpperCase()
  if(method==='GET')return apiRequest<T>(path,init)
  const match=/^\/api\/tracker\/entries(?:\/([0-9a-f-]+)(?:\/(restore))?)?$/.exec(path)
  if(!match)throw new Error('Unsupported Entry write surface')
  const p=payload(init??{}),entity=match[1]??String(p.id??uuidv7())
  const pending=getSnapshot().rows.find(r => r.entity===entity && r.kind==='entry.create')
  const baseline=known('entry',entity)
  const parent=String(p.tracker_id??baseline?.tracker_id??pending?.parent??cancelledParent(entity)??'')
  const kind:Kind=match[2]?'entry.restore':!match[1]?'entry.create':method==='PATCH'?'entry.update':'entry.delete'
  if(kind==='entry.create'){p.id=entity;p.occurred_at??=new Date().toISOString()}
  const command=await admit(kind,entity,parent,p)
  if(kind==='entry.create')return {...entryFrom(command),local_acceptance:true} as T
  return (projectEntries(baseline?[baseline]:[],visibleCommands(),'/api/tracker/entries?limit=500').find(e => e.id===entity)??{id:entity,local_acceptance:true}) as T
}
export async function onlineTrackerRequest<T>(path:string,init?:Init):Promise<T> {
  const match=/^\/api\/tracker\/trackers\/([0-9a-f-]+)/.exec(path)
  if(init?.method && init.method!=='GET' && match)await barrier('tracker:'+match[1])
  const group=/^\/api\/tracker\/groups\/([0-9a-f-]+)/.exec(path)
  if(init?.method && init.method!=='GET' && group)
    for(const row of getSnapshot().rows)
      if(row.principal===getSnapshot().context.principal && row.kind.startsWith('entry.') &&
        (!known('tracker',row.parent) || known('tracker',row.parent)?.group_id===group[1]))await barrier(row.aggregate)
  return apiRequest<T>(path,init)
}
