import { expect, it } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { maskPrivateQueries } from './private-visibility'
import { pruneDraftBaselines } from '../draft-baselines'

it('masks private reminder/source/entry responses and retains public object identity and draft owners', () => {
  const client = new QueryClient()
  const publicTask = {id:'public',is_private:false,title:'public draft owner'}
  client.setQueryData(['tasks','all'], {items:[publicTask,{id:'private',is_private:true,title:'canary'}],total:2})
  client.setQueryData(['tracker','trackers'], {items:[{id:'public-tracker',is_private:false},{id:'private-tracker',is_private:true}]})
  client.setQueryData(['tracker','entries','recent'], {items:[{id:'yes',tracker_id:'public-tracker'},{id:'no',tracker_id:'private-tracker'},{id:'unknown',tracker_id:'absent'}]})
  client.setQueryData(['reminders','center'], {items:[{id:'private',is_private:true,source_title:'canary'},{id:'public',is_private:false,source_title:'public'}],total:2})
  client.setQueryData(['reminders','detail','task','private'], {is_private:true,title:'canary'})
  client.setQueryData(['reminders','detail','task','public'], publicTask)
  client.setQueryData(['calendar','tasks'], {items:[publicTask,{is_private:true,title:'canary'}]})
  maskPrivateQueries(client)
  expect(client.getQueryData<{items:unknown[]}>(['tasks','all'])?.items[0]).toBe(publicTask)
  expect(client.getQueryData(['tasks','all'])).not.toHaveProperty('total')
  expect(client.getQueryData(['tracker','entries','recent'])).toMatchObject({items:[{id:'yes'}]})
  expect(client.getQueryData(['reminders','detail','task','private'])).toBeUndefined()
  expect(client.getQueryData(['reminders','detail','task','public'])).toBe(publicTask)
  expect(JSON.stringify(client.getQueryCache().getAll().map(q=>q.state.data))).not.toContain('canary')
  client.clear()
})

it('prunes only disconnected forms across visibility changes, preserving the original connected dirty baseline', () => {
  const publicForm={isConnected:true},discardedPrivateForm={isConnected:false}
  const baselines=new Map([[publicForm,'original public value'],[discardedPrivateForm,'private value']])
  pruneDraftBaselines(baselines)
  pruneDraftBaselines(baselines)
  expect(baselines.size).toBe(1)
  expect(baselines.get(publicForm)).toBe('original public value')
})

it('lets an authoritative session error settle when it triggers privacy masking', async () => {
  const client=new QueryClient()
  await expect(client.fetchQuery({queryKey:['session'],retry:false,queryFn:async()=>{
    maskPrivateQueries(client)
    throw new Error('authoritative 401')
  }})).rejects.toThrow('authoritative 401')
  expect(client.getQueryState(['session'])?.status).toBe('error')
  client.clear()
})
