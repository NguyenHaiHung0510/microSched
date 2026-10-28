import type { MimiCollectionEntry } from '@/mimi-api'
import { collectionFieldDiff } from '@/mimi-collection'
import { checklistChanges, checklistSummary, orderedReviewChildren, reminderEffectLabel, reminderRows, reviewFieldLabel, reviewValue, type ReviewChild } from '@/mimi-review-readable'

function Value({ value }: { value: string }) {
  return <pre className="whitespace-pre-wrap break-words font-sans text-xs">{value}</pre>
}
function Child({ child }: { child: ReviewChild | undefined }) {
  return child ? <div className="min-w-0 text-xs"><p className="whitespace-pre-wrap break-words">{child.content}</p><p className="text-muted-foreground">{child.is_completed ? 'Hoàn thành' : 'Chưa hoàn thành'} · vị trí {child.position + 1}{child.deleted_at ? ' · Đã xóa mềm' : ''}</p></div> : <p className="text-xs">Không có mục</p>
}
function Children({ children }: { children: ReviewChild[] }) {
  return children.length ? <ol className="mt-2 space-y-2">{orderedReviewChildren(children).map((child) => <li key={child.id}><Child child={child} /></li>)}</ol> : <p className="mt-2 text-xs">Không có mục</p>
}
function Reminder({ value }: { value: Record<string, unknown> | null | undefined }) {
  return value ? <dl className="mt-2 space-y-2 text-xs">{reminderRows(value).map((row) => <div key={row.label}><dt className="text-muted-foreground">{row.label}</dt><dd className="whitespace-pre-wrap break-words">{row.value}</dd></div>)}</dl> : <p className="mt-2 text-xs">Không có lời nhắc</p>
}
export function MimiCollectionEntryDetails({ entry }: { entry: MimiCollectionEntry }) {
  const diff = collectionFieldDiff(entry)
  const children = checklistChanges(entry)
  const configuration = entry.command.reminder.configuration as Record<string, unknown> | undefined
  return <div className="space-y-3 p-3" data-testid="mimi-entry-details">
    {diff.length ? <div className="grid gap-3 sm:grid-cols-2">{diff.map(({ key, before, after }) => <section key={key} className="min-w-0 rounded-lg border p-3"><h5 className="font-semibold">{reviewFieldLabel(key)}</h5><div className="mt-2 grid gap-2"><div><p className="text-xs text-muted-foreground">Trước</p><Value value={reviewValue(key, before)} /></div><div><p className="text-xs text-muted-foreground">Sau</p><Value value={reviewValue(key, after)} /></div></div></section>)}</div> : <p className="text-xs text-muted-foreground">Các trường của Task giữ nguyên.</p>}
    <section className="rounded-lg border p-3"><h5 className="font-semibold">{checklistSummary(entry)}</h5>{children.length ? <ul className="mt-3 space-y-3">{children.map((change) => <li key={change.id}><p className="text-xs font-semibold">{change.changes.join(' · ')}</p><div className="mt-2 grid gap-3 sm:grid-cols-2"><section><h6 className="text-xs text-muted-foreground">Trước</h6><Child child={change.before} /></section><section><h6 className="text-xs text-muted-foreground">Sau</h6><Child child={change.after} /></section></div></li>)}</ul> : null}
      <details className="mt-3"><summary className="cursor-pointer text-xs font-semibold">Checklist đầy đủ trước / sau</summary><div className="mt-3 grid gap-3 sm:grid-cols-2"><section><h6 className="font-semibold">Trước</h6><Children children={entry.before?.children ?? []} /></section><section><h6 className="font-semibold">Sau</h6><Children children={entry.after.children} /></section></div></details>
    </section>
    <section className="rounded-lg border p-3"><h5 className="font-semibold">{reminderEffectLabel(entry)}</h5><div className="mt-2 grid gap-3 sm:grid-cols-2"><section><h6 className="text-xs text-muted-foreground">Lời nhắc trước</h6><Reminder value={entry.before?.reminder ?? entry.reminder_effect.before as Record<string, unknown> | null | undefined} /></section><section><h6 className="text-xs text-muted-foreground">Hiệu ứng sau khi xác nhận</h6><p className="mt-2 text-xs">{reminderEffectLabel(entry)}</p>{configuration ? <Reminder value={configuration} /> : null}{entry.reminder_effect.due_at != null ? <p className="mt-2 text-xs">Thời điểm đã chốt: {reviewValue('due_at', entry.reminder_effect.due_at)}</p> : null}</section></div></section>
    {entry.command.action === 'soft_delete' || entry.command.action === 'restore' ? <p className="text-sm">{entry.command.action === 'soft_delete' ? 'Xóa mềm: giữ dữ liệu phục hồi; reminder bị hủy theo hiệu ứng đã chốt.' : 'Khôi phục: theo đúng snapshot và phiên bản đã chốt.'}</p> : null}
    <details className="rounded-lg border p-3 text-xs" data-testid="mimi-entry-technical"><summary className="cursor-pointer font-semibold">Chi tiết kỹ thuật · ID, phiên bản và JSON</summary><p className="mt-2 break-all">ID: {entry.id} · phiên bản chờ xác nhận: {entry.command.expected_collection_version ?? 'Task mới'}</p><pre className="mt-2 whitespace-pre-wrap break-words font-sans text-xs">{JSON.stringify(entry, null, 2)}</pre></details>
  </div>
}
