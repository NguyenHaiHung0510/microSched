import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { MimiCollectionEntry } from '@/mimi-api'
import { MimiCollectionEntryDetails } from './MimiCollectionEntryDetails'
import { checklistChanges, checklistSummary, collectionActionLabel, reminderEffectLabel, reviewValue } from './mimi-review-readable'

const child = (id: string, content: string, position: number, deleted_at: string | null = null) => ({ id, content, position, is_completed: false, deleted_at })
function fixture(): MimiCollectionEntry {
  const children = Array.from({ length: 25 }, (_, i) => child(`child-${i}`, `Mục đầy đủ ${i}`, i))
  return { id: '107-task-uuid', command: { action: 'edit', expected_collection_version: 7, fields: { priority: 'p1' }, children: [], reminder: { action: 'keep' } }, before: { fields: { title: 'Task', body_md: 'Nội dung giữ nguyên', priority: null }, children }, after: { fields: { title: 'Task', body_md: 'Nội dung giữ nguyên', priority: 'p1' }, children: structuredClone(children) }, reminder_effect: { action: 'keep', before: null } }
}
const render = (entry: MimiCollectionEntry) => renderToStaticMarkup(<MimiCollectionEntryDetails entry={entry} />)
const primary = (html: string) => html.slice(0, html.lastIndexOf('<details'))

describe('readable frozen collection content', () => {
  it('shows established labels, true scalar effect and unchanged summaries, with raw ID/version/JSON secondary and collapsed', () => {
    const html = render(fixture())
    expect(primary(html)).toContain('Độ ưu tiên'); expect(primary(html)).toContain('Không đặt'); expect(primary(html)).toContain('P1')
    expect(primary(html)).toContain('Checklist giữ nguyên · 25 mục đang dùng'); expect(primary(html)).toContain('Không có lời nhắc · giữ nguyên')
    expect(primary(html)).not.toContain('107-task-uuid'); expect(primary(html)).not.toContain('expected_collection_version')
    expect(html).toContain('Chi tiết kỹ thuật'); expect(html).toContain('107-task-uuid'); expect(html).not.toContain('<details open')
    expect(collectionActionLabel('create')).toBe('Tạo Task'); expect(collectionActionLabel('soft_delete')).toBe('Xóa mềm')
    expect(collectionActionLabel('restore')).toBe('Khôi phục'); expect(collectionActionLabel('edit')).toBe('Sửa')
  })
  it('keeps full ordered before/after children readable, including tombstones, without confusing unchanged completion metadata', () => {
    const e = fixture(); e.before!.children.reverse(); e.after.children.push(child('removed', 'Mục đã xóa giữ để phục hồi', 30, '2026-10-01'))
    e.before!.children.push(structuredClone(e.after.children.at(-1)!))
    const html = render(e)
    expect(checklistChanges(e)).toHaveLength(0); expect(checklistSummary(e)).toContain('25 mục đang dùng')
    expect(html).toContain('Mục đầy đủ 24'); expect(html).toContain('Mục đã xóa giữ để phục hồi'); expect(html).toContain('Đã xóa mềm')
    expect(html.indexOf('Mục đầy đủ 0')).toBeLessThan(html.indexOf('Mục đầy đủ 24'))
  })
  it('distinguishes add/edit/completion/order/remove/restore by identity with complete old/new text, not array order', () => {
    const e = fixture(); e.before!.children = [child('a', 'Trùng nội dung', 0), child('b', 'Trùng nội dung', 1), child('c', 'Khôi phục', 2, '2026-10-01')]
    e.after.children = [{ ...child('a', 'Nội dung sửa đầy đủ', 1), is_completed: true }, child('b', 'Trùng nội dung', 0, '2026-10-02'), child('c', 'Khôi phục', 2), child('d', 'Mục thêm', 3)]
    expect(checklistChanges(e)).toHaveLength(4)
    const html = primary(render(e))
    for (const text of ['Thêm mục', 'Sửa nội dung', 'Đổi trạng thái hoàn thành', 'Đổi thứ tự', 'Xóa mềm mục', 'Khôi phục mục', 'Nội dung sửa đầy đủ', 'Trùng nội dung', 'Mục thêm', 'Hoàn thành', 'vị trí 2']) expect(html).toContain(text)
  })
  it.each([['keep', 'Lời nhắc giữ nguyên'], ['configure', 'Thiết lập lời nhắc'], ['reschedule', 'Đổi thời điểm nhắc theo lịch mới'], ['needs_reschedule', 'Cần đặt lại giờ nhắc'], ['cancel', 'Hủy lời nhắc']])('shows frozen %s reminder effect rather than trusting command keep', (action, label) => {
    const e = fixture(); e.before!.reminder = { mode: 'relative', status: 'pending', due_at: '2026-10-10T23:30:00Z', offset_minutes: -15, anchor_time: '09:00:00' }
    e.reminder_effect = { action, before: e.before!.reminder, due_at: '2026-10-11T00:30:00Z' }
    expect(reminderEffectLabel(e)).toBe(label)
    const html = primary(render(e))
    for (const text of [label, 'Đang chờ', 'Theo lịch Task', '15 phút trước mốc lịch', 'giờ Việt Nam', '11/10/2026']) expect(html).toContain(text)
  })
  it('retains readable configure mode/time and explicit clear values without reinterpreting omission', () => {
    const e = fixture(); e.before!.fields.priority = 'p1'; e.after.fields.priority = null
    e.command.reminder = { action: 'configure', configuration: { mode: 'absolute', due_at: '2026-10-11T00:30:00Z' } }
    e.reminder_effect = { action: 'configure', before: null, due_at: '2026-10-11T00:30:00Z' }
    const html = primary(render(e)); expect(html).toContain('Không đặt'); expect(html).toContain('Thời điểm cụ thể')
    expect(html).not.toContain('Nội dung giữ nguyên'); expect(reviewValue('due_on', '2026-10-11')).toBe('11/10/2026')
  })
  it('does not turn absent or unknown reminder effect into a promise of unchanged state', () => {
    const e = fixture(); e.reminder_effect = {}
    expect(reminderEffectLabel(e)).toContain('Chưa nhận diện')
    e.reminder_effect = { action: 'none' }; expect(reminderEffectLabel(e)).toBe('Không có lời nhắc')
  })
  it('keeps full hostile/long plain text escaped and preserves the exact frozen plan while rendering', () => {
    const e = fixture(); e.after.fields.body_md = '<script>alert(1)</script>' + 'ế🏃'.repeat(12000) + 'END107'
    e.after.children[24].content = '<img src=x onerror=alert(1)> CHECKLIST_END107'
    const frozen = JSON.stringify(e); Object.freeze(e.before!.children); Object.freeze(e.after.children)
    const html = primary(render(e))
    expect(html).toContain('&lt;script&gt;'); expect(html).toContain('END107'); expect(html).toContain('&lt;img'); expect(html).toContain('CHECKLIST_END107')
    expect(html).not.toContain('<script>'); expect(html).not.toContain('<img'); expect(JSON.stringify(e)).toBe(frozen)
  })
})
