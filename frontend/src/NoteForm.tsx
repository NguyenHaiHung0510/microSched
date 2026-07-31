import { type FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  canSubmitNote,
  type NoteFormState,
  type NoteWritePayload,
  notePayload,
} from '@/note-ui'

type InitialNote = {
  title: string | null
  body_md: string | null
  is_private: boolean
}

export function NoteForm({
  initial,
  submitLabel,
  pending,
  onSubmit,
  onCancel,
}: {
  initial?: InitialNote
  submitLabel: string
  pending: boolean
  onSubmit: (payload: NoteWritePayload) => void
  onCancel?: () => void
}) {
  const [title, setTitle] = useState(initial?.title ?? '')
  const [body, setBody] = useState(initial?.body_md ?? '')
  const [isPrivate, setIsPrivate] = useState(initial?.is_private ?? false)
  const state: NoteFormState = { title, body, isPrivate }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmitNote(state, pending)) return
    onSubmit(notePayload(state))
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Tiêu đề (không bắt buộc)</span>
        <Input
          className="h-10 bg-card"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>

      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Nội dung</span>
        <Textarea
          className="min-h-32 bg-card font-normal"
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
      </label>

      <label className="flex min-h-9 items-center gap-3 text-sm font-semibold">
        <Checkbox
          className="size-5 rounded-md"
          checked={isPrivate}
          onCheckedChange={(checked) => setIsPrivate(checked === true)}
        />
        <span>Riêng tư</span>
      </label>

      <div className="flex flex-wrap gap-2 pt-1">
        <Button size="lg" type="submit" disabled={!canSubmitNote(state, pending)}>
          {pending ? 'Đang lưu…' : submitLabel}
        </Button>
        {onCancel ? (
          <Button size="lg" variant="outline" type="button" onClick={onCancel}>
            Huỷ
          </Button>
        ) : null}
      </div>
    </form>
  )
}
