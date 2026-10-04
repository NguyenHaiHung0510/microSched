import { describe, expect, it } from 'vitest'
import { activityLevel, periodBounds, recordsUrl, type RecordsSelection } from '../src/tracker-records'
describe('Vietnam record periods', () => {
  it('uses half-open +07 midnight across leap days and year boundaries', () => {
    expect(periodBounds('day','2024-02-29')).toEqual({from:'2024-02-29T00:00:00+07:00',to:'2024-03-01T00:00:00+07:00'})
    expect(new Date(periodBounds('day','2024-02-29')!.from).toISOString()).toBe('2024-02-28T17:00:00.000Z')
    expect(periodBounds('month','2024-12-13')!.to).toBe('2025-01-01T00:00:00+07:00')
    expect(periodBounds('quarter','2024-05-31')).toEqual({from:'2024-04-01T00:00:00+07:00',to:'2024-07-01T00:00:00+07:00'})
    expect(periodBounds('year','2024-02-29')!.to).toBe('2025-01-01T00:00:00+07:00')
  })
  it('rejects rolled-over/invalid dates and years without querying', () => {
    for (const date of ['2023-02-29','2024-02-30','2024-13-01','','0000-01-01','9999-01-01']) expect(periodBounds('day',date)).toBeNull()
    expect(periodBounds('year','0004-02-29')!.from).toBe('0004-01-01T00:00:00+07:00')
  })
  it('recent is always20, periods use bounded lookahead and encoded filters', () => {
    const s: RecordsSelection={mode:'recent',trackerId:'all',anchor:'2024-02-29',order:'desc',page:7,expanded:true}
    const recent=new URL(recordsUrl(s)!, 'http://localhost').searchParams
    expect(recent.get('limit')).toBe('20');expect(recent.get('offset')).toBe('0');expect(recent.has('from')).toBe(false)
    const paged=new URL(recordsUrl({...s,mode:'day',trackerId:'sample',page:1,order:'asc'})!, 'http://localhost').searchParams
    expect(paged.get('limit')).toBe('51');expect(paged.get('offset')).toBe('50');expect(paged.get('from')).toBe('2024-02-29T00:00:00+07:00');expect(paged.get('order')).toBe('asc');expect(paged.get('tracker_id')).toBe('sample')
    expect(recordsUrl({...s,mode:'month',anchor:'invalid'})).toBeNull()
  })
})
describe('fixed rare-activity heatmap scale',()=>{
  it('uses0/1/2/>=3 independently of report maximum',()=>{
    expect([0,1,2,3,4,100].map(activityLevel)).toEqual([0,1,2,3,3,3])
  })
})
