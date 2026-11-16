import { useState, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { MimiCollectionEntry, MimiCollectionPlan, MimiSelection } from '@/mimi-api'
import { collectionFieldDiff, collectionPage } from '@/mimi-collection'
import { MimiCollectionEntryDetails } from '@/MimiCollectionEntryDetails'
import { checklistSummary, collectionActionLabel, reminderEffectLabel, reviewFieldLabel } from '@/mimi-review-readable'

export function MimiCollectionFrame({ title, actions, children, testId = 'mimi-change-set' }: {
  title: string; actions?: ReactNode; children: ReactNode; testId?: string
}) {
  return <section className="shrink-0 rounded-xl border bg-card p-3" data-testid={testId}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm font-semibold">{title}</p>
      <div className="flex gap-1">{actions}</div>
    </div>
    {children}
  </section>
}

type TableState = { query: string; classification: string; page: number; expanded: string | null }

export function MimiCollectionTable({ plan, selection, executed = false, state, onStateChange }: {
  plan: MimiCollectionPlan; selection?: MimiSelection; executed?: boolean
  state?: TableState; onStateChange?: Dispatch<SetStateAction<TableState>>
}) {
  const [localState, setLocalState] = useState<TableState>({ query: '', classification: 'all', page: 0, expanded: null })
  const { query, classification, page, expanded } = state ?? localState
  const setState = onStateChange ?? setLocalState
  const view = collectionPage(plan, query, classification, selection, page)
  return <div className="space-y-3 min-w-0">
    <div className="flex flex-wrap items-center gap-2">
      <Input className="min-w-0 flex-1 text-base md:text-sm" aria-label={executed ? 'Tìm trong thay đổi đã áp dụng' : 'Tìm trong preview'} placeholder="Tìm tiêu đề hoặc ID…" value={query} onChange={(e) => { const value = e.target.value; setState(previous => ({ ...previous, query: value, page: 0 })) }} />
      {!executed ? <Select value={classification} onValueChange={(value) => setState(previous => ({ ...previous, classification: value, page: 0 }))}><SelectTrigger aria-label="Lọc phân loại" className="w-40"><SelectValue /></SelectTrigger><SelectContent>{[['all','Tất cả'],['included','Bao gồm'],['excluded','Loại trừ'],['uncertain','Chưa chắc']].map(([value,label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select> : null}
    </div>
    <div className="max-h-[50dvh] overflow-auto rounded-lg border"><table className="w-full text-left text-xs">
      <caption className="sr-only">{executed ? 'Thay đổi Task đã áp dụng' : 'Thay đổi Task đã chốt'}, tối đa 100 dòng mỗi trang</caption>
      <thead className="sticky top-0 bg-muted"><tr><th className="p-2">Tiêu đề trước</th><th className="p-2">Task / thao tác</th><th className="p-2">Tóm tắt</th><th className="p-2">Chi tiết</th></tr></thead>
      <tbody>{view.entries.map((entry) => <Row key={entry.id} entry={entry} executed={executed} expanded={expanded === entry.id} onToggle={() => setState(previous => ({ ...previous, expanded: previous.expanded === entry.id ? null : entry.id }))} />)}</tbody>
    </table></div>
    {!view.visibleCount ? <p className="text-sm text-muted-foreground">{executed ? 'Không có dòng khớp bộ lọc.' : `Không có dòng khớp bộ lọc; phạm vi xác nhận vẫn là ${plan.entries.length} Task.`}</p> : null}
    <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs">Trang {view.currentPage + 1}/{view.pageCount} · {view.visibleCount}/{plan.entries.length} dòng khớp</span><div className="flex gap-1">
      <Button size="icon" variant="outline" aria-label="Trang trước" disabled={view.currentPage === 0} onClick={() => setState(previous => ({ ...previous, page: view.currentPage - 1 }))}><ChevronLeft /></Button>
      <Button size="icon" variant="outline" aria-label="Trang sau" disabled={view.currentPage + 1 >= view.pageCount} onClick={() => setState(previous => ({ ...previous, page: view.currentPage + 1 }))}><ChevronRight /></Button>
    </div></div>
  </div>
}

function Row({ entry, executed, expanded, onToggle }: { entry: MimiCollectionEntry; executed: boolean; expanded: boolean; onToggle: () => void }) {
  return <><tr className="border-t align-top" data-testid="mimi-review-row">
    <td className="max-w-64 break-words p-2">{entry.before ? String(entry.before.fields.title ?? 'Chưa có tiêu đề') : '— (Task mới)'}</td>
    <td className="max-w-64 p-2"><p className="break-words font-semibold">{String(entry.after.fields.title ?? entry.before?.fields.title ?? 'Task')}</p><p className="text-muted-foreground">{collectionActionLabel(entry.command.action)}</p></td>
    <td className="p-2"><p>{collectionFieldDiff(entry).length ? collectionFieldDiff(entry).map((field) => reviewFieldLabel(field.key)).join(', ') : 'Các trường Task giữ nguyên'}</p><p className="text-muted-foreground">{checklistSummary(entry)}</p><p className="text-muted-foreground">{reminderEffectLabel(entry)}</p></td>
    <td className="p-2"><Button size="sm" variant="ghost" aria-expanded={expanded} onClick={onToggle}><ChevronDown className="size-4" />{expanded ? 'Thu gọn' : 'Xem đủ'}</Button></td>
  </tr>{expanded ? <tr className="border-t"><td colSpan={4}><MimiCollectionEntryDetails entry={entry} executed={executed} /></td></tr> : null}</>
}
