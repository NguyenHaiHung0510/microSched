import { describe, expect, it } from 'vitest'
import { QueryClient, dehydrate } from '@tanstack/react-query'
import { canonical, decode, KINDS, validatePayload, type Command } from './protocol'
import { legacyV1 } from './legacy-v1-fixtures'
import { fundingReference, needsFunding } from './funding'
import { maskPrivateQueries } from './private-visibility'
import { sanitizeSnapshot } from './public-cache'

const source='019a0000-0000-7000-8000-000000000006'
describe('funding compatibility/privacy boundaries',()=>{
 it('decodes all11 immutable old payload/digest/envelope bytes with no new null default',async()=>{
   expect(KINDS).toHaveLength(11)
   expect(legacyV1.map(r=>r.kind).sort()).toEqual([...KINDS].sort())
   for(const row of legacyV1){
     const before=JSON.stringify(row)
     const body=await decode(row as Command)
     expect(canonical(body)).toBe(row.payload)
     expect(body).not.toHaveProperty('funding_entry_id')
     expect(JSON.stringify(row)).toBe(before)
     expect(needsFunding(row as Command)).toBe(false)
   }
 })
 it('capability-gates the new field including explicit unlink; rejects non-UUID references',()=>{
   const row=legacyV1.find(r=>r.kind==='entry.create') as Command
   validatePayload('entry.create',row.entity,row.parent,{...JSON.parse(row.payload),funding_entry_id:source})
   expect(()=>validatePayload('entry.create',row.entity,row.parent,{...JSON.parse(row.payload),funding_entry_id:'bad'})).toThrow()
   expect(needsFunding({...row,payload:canonical({funding_entry_id:null})})).toBe(true)
   expect(fundingReference({...row,payload:canonical({funding_entry_id:source})})).toBe(source)
 })
 it('strips nested private source from public expense RAM/disk and drops options/report without altering public draft fields',()=>{
   const client=new QueryClient()
   client.setQueryData(['tracker','trackers'],{items:[{id:'public',is_private:false}]})
   const row={id:'expense',tracker_id:'public',amount:500000,note_md:'public dirty owner',funding_entry_id:source,funding:{status:'available',source:{id:source,tracker_name:'private-source-canary',amount:987654,is_private:true}}}
   client.setQueryData(['tracker','entries','list'],{items:[row]},{updatedAt:1})
   client.setQueryData(['tracker','entries','detail'],row,{updatedAt:1})
   client.setQueryData(['tracker','funding-candidates'],{items:[row.funding.source]})
   client.setQueryData(['tracker','funding-report'],{buckets:[{source:row.funding.source}]})
   const disk=sanitizeSnapshot({timestamp:Date.now(),buster:'public-v1',clientState:dehydrate(client)})
   expect(JSON.stringify(disk)).not.toContain('private-source-canary')
   expect(JSON.stringify(disk)).not.toContain(source)
   maskPrivateQueries(client)
   expect(client.getQueryData(['tracker','entries','list'])).toMatchObject({items:[{id:'expense',amount:500000,note_md:'public dirty owner'}]})
   expect(client.getQueryData(['tracker','entries','detail'])).not.toHaveProperty('funding')
   expect(client.getQueryData(['tracker','funding-report'])).toBeUndefined()
   expect(JSON.stringify(client.getQueryCache().getAll().map(q=>q.state.data))).not.toContain('private-source-canary')
   expect(row.funding.source.tracker_name).toBe('private-source-canary')
   client.clear()
 })
})
