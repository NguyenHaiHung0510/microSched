import { describe,it,expect } from 'vitest'
import { canonical,decode,hash,retryDelay,route,validatePayload,type Command } from './protocol'
import { projectTasks,projectEntries } from './projection'
const task='019a0000-0000-7000-8000-000000000001', child='019a0000-0000-7000-8000-000000000002'
const tracker='019a0000-0000-7000-8000-000000000003', entry='019a0000-0000-7000-8000-000000000004'
async function command(kind:Command['kind'],entity=task,parent=task,body:Record<string,unknown>={}):Promise<Command>{
 const payload=canonical(body)
 const row = {version:1,id:'019a0000-0000-7000-8000-000000000005',principal:'verified',kind,entity,parent,aggregate:kind.startsWith('entry.')?'tracker:'+parent:'task:'+parent,
  predecessor:null,dependency:null,created_at:'2026-10-23T01:00:00Z',expires_at:Date.now()+10000,payload,digest:await hash(payload),
  byte_length:new TextEncoder().encode(payload).length,requires_private:false,state:'pending',attempted:false,attempt:0,next_due:0,reason:''} as Command
 row.envelope_digest=await hash(canonical({version:row.version,id:row.id,principal:row.principal,kind:row.kind,entity:row.entity,parent:row.parent,aggregate:row.aggregate,payload:row.payload}))
 return row
}
describe('V1 typed protocol',()=>{
 it('retains exact Unicode and canonical bytes',async()=>{
  const row=await command('task.create',task,task,{id:task,title:'Đọc sách',items:['Một'],item_ids:[child],is_private:false})
  expect((await decode(row)).title).toBe('Đọc sách')
  await expect(decode({...row,payload:row.payload+' '})).rejects.toThrow()
  await expect(decode({...row,version:2 as 1})).rejects.toThrow()
 })
 it('rejects route injection, malformed/unknown fields and child identity drift',()=>{
  expect(()=>route({kind:'task.update',entity:'../../admin',parent:task})).toThrow()
  expect(()=>validatePayload('task.update',task,task,{url:'/evil'})).toThrow()
  expect(()=>validatePayload('task.create',task,task,{id:task,title:'x',items:['one'],item_ids:[]})).toThrow()
  expect(route({kind:'task_item.update',entity:child,parent:task})).toEqual({path:'/api/tasks/'+task+'/items/'+child,method:'PATCH'})
 })
 it('honors RetryAfter beyond local cap and HTTP dates',()=>{
  expect(retryDelay(99,'120',0)).toBe(120000)
  expect(retryDelay(1,new Date(90000).toUTCString(),0)).toBe(90000)
  expect(retryDelay(2,null)).toBe(2000)
 })
})
describe('pure canonical plus pending projection',()=>{
 it('projects initial children and absolute edits, status and date without mutating baseline',async()=>{
  const create=await command('task.create',task,task,{id:task,title:'A',items:['one'],item_ids:[child],is_private:false})
  const edit=await command('task_item.update',child,task,{content:'two',is_completed:true})
  const moved=await command('task.update',task,task,{due_precision:'date',due_on:'2026-10-24',due_at:null,status:'completed'})
  const baseline:Record<string,unknown>[]=[]
  const result=projectTasks(baseline,[create,edit,moved],'completed')
  expect(result).toHaveLength(1)
  expect(result[0].items).toEqual([expect.objectContaining({id:child,content:'two',is_completed:true})])
  expect(result[0].due_on).toBe('2026-10-24')
  expect(projectTasks(baseline,[create,moved],'open')).toEqual([])
  expect(baseline).toEqual([])
 })
 it('does not double append an Entry already returned before ACK and keeps original time',async()=>{
  const original='2026-10-20T02:10:00Z'
  const create=await command('entry.create',entry,tracker,{id:entry,tracker_id:tracker,occurred_at:original,quantity:2})
  const baseline=[{id:entry,tracker_id:tracker,occurred_at:original,quantity:2}]
  expect(projectEntries(baseline,[create],'/api/tracker/entries')).toEqual(baseline.map(row=>expect.objectContaining(row)))
  expect(projectEntries(baseline,[create],'/api/tracker/entries?from=2026-10-21T00:00:00Z')).toEqual([])
 })
 it('applies updates after create/poll and delete without poisoning canonical objects',async()=>{
  const baseline=[{id:entry,tracker_id:tracker,occurred_at:'2026-10-20T00:00:00Z',quantity:2}]
  const update=await command('entry.update',entry,tracker,{quantity:3})
  const remove=await command('entry.delete',entry,tracker)
  expect(projectEntries(baseline,[update],'/api/tracker/entries')[0].quantity).toBe(3)
  expect(projectEntries(baseline,[update,remove],'/api/tracker/entries')).toEqual([])
  expect(baseline[0].quantity).toBe(2)
 })
})
