import { type FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { TrackerGroup, TrackerKind } from '@/tracker-ui'

export function GroupForm({
  pending,
  onSubmit,
  onCancel,
  initial = null,
}: {
  pending: boolean
  onSubmit: (payload: { name: string; kind: TrackerKind }) => void
  onCancel?: () => void
  initial?: TrackerGroup | null
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [kind, setKind] = useState<TrackerKind>(initial?.kind ?? 'health')
  const canSubmit = name.trim().length > 0 && !pending
  // GroupUpdate intentionally has no `kind` field (composite FK trap 4), so an
  // edited group keeps its original kind — only the name is editable here.
  const editing = initial !== null

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    onSubmit({ name: name.trim(), kind })
  }

  return (
    <form data-testid="group-form" className="space-y-4" onSubmit={submit}>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Tên nhóm</span>
        <Input
          className="h-10 bg-card"
          value={name}
          maxLength={150}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Loại</span>
        <Select
          value={kind}
          disabled={editing}
          onValueChange={(value) => setKind(value as TrackerKind)}
        >
          <SelectTrigger className="w-full bg-card">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="health">Sức khoẻ</SelectItem>
            <SelectItem value="finance">Tài chính</SelectItem>
            <SelectItem value="general">Chung</SelectItem>
          </SelectContent>
        </Select>
      </label>
      <div className="flex flex-wrap gap-2 pt-1">
        <Button size="lg" className="min-h-11" type="submit" disabled={!canSubmit}>
          {pending ? 'Đang lưu…' : editing ? 'Lưu thay đổi' : 'Tạo nhóm'}
        </Button>
        {onCancel ? (
          <Button size="lg" variant="outline" className="min-h-11" type="button" onClick={onCancel}>
            Huỷ
          </Button>
        ) : null}
      </div>
    </form>
  )
}
