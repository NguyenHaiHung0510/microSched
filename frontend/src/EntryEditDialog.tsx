import { type FormEvent, useState } from 'react'

import { toVietnamDateTimeInput, vietnamInputToIso } from '@/calendar-ui'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  decimalInput,
  digitsOnly,
  quantityToNumber,
  type Entry,
  type Tracker,
} from '@/tracker-ui'

export type EntryEditPayload = {
  occurred_at?: string
  quantity?: number | null
  amount?: number | null
  list_amount?: number | null
  note_md?: string | null
}

export function EntryEditDialog({
  entry,
  tracker,
  pending,
  onClose,
  onSubmit,
}: {
  entry: Entry | null
  tracker: Tracker | null
  pending: boolean
  onClose: () => void
  onSubmit: (entryId: string, payload: EntryEditPayload) => void
}) {
  const [occurredAt, setOccurredAt] = useState(toVietnamDateTimeInput(entry?.occurred_at ?? null))
  const [amount, setAmount] = useState(entry?.amount != null ? String(entry.amount) : '')
  const [listAmount, setListAmount] = useState(
    entry?.list_amount != null ? String(entry.list_amount) : '',
  )
  const [quantity, setQuantity] = useState(
    entry?.quantity != null ? String(entry.quantity) : '',
  )
  const [note, setNote] = useState(entry?.note_md ?? '')

  if (!entry) return null

  const isMoney = tracker?.input_mode === 'money'
  const isQuantity = tracker?.input_mode === 'quantity'
  const amountRequired = isMoney && amount.length === 0
  const quantityRequired = isQuantity && quantity.length === 0
  const canSubmit = !pending && !amountRequired && !quantityRequired

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!entry || !canSubmit) return
    const payload: EntryEditPayload = {}
    if (occurredAt) payload.occurred_at = vietnamInputToIso(occurredAt)
    if (isMoney) {
      payload.amount = amount ? Number(digitsOnly(amount)) : null
      payload.list_amount = listAmount ? Number(digitsOnly(listAmount)) : null
    }
    if (isQuantity) payload.quantity = quantity ? quantityToNumber(quantity) : null
    payload.note_md = note.trim() || null
    onSubmit(entry.id, payload)
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !pending && onClose()}>
      <DialogContent data-testid="entry-edit-dialog">
        <DialogHeader>
          <DialogTitle>Sửa bản ghi</DialogTitle>
          <DialogDescription>
            {tracker ? `Bản ghi của “${tracker.name}”` : 'Sửa thời gian, số liệu và ghi chú.'}
          </DialogDescription>
        </DialogHeader>
        <form data-testid="entry-edit" className="space-y-4" onSubmit={submit}>
          <label className="block space-y-1.5 text-sm font-semibold">
            <span>Thời điểm</span>
            <Input
              className="h-10 bg-card"
              type="datetime-local"
              value={occurredAt}
              onChange={(event) => setOccurredAt(event.target.value)}
            />
          </label>
          {isMoney ? (
            <>
              <label className="block space-y-1.5 text-sm font-semibold">
                <span>Số tiền</span>
                <Input
                  className="h-10 bg-card"
                  inputMode="numeric"
                  value={amount}
                  onChange={(event) => setAmount(digitsOnly(event.target.value))}
                />
              </label>
              <label className="block space-y-1.5 text-sm font-semibold">
                <span>Giá gốc (nếu có)</span>
                <Input
                  className="h-10 bg-card"
                  inputMode="numeric"
                  value={listAmount}
                  onChange={(event) => setListAmount(digitsOnly(event.target.value))}
                />
              </label>
            </>
          ) : null}
          {isQuantity ? (
            <label className="block space-y-1.5 text-sm font-semibold">
              <span>Số lượng ({tracker?.unit ?? 'đơn vị'})</span>
                <Input
                  className="h-10 bg-card"
                  inputMode="numeric"
                  value={quantity}
                  onChange={(event) => setQuantity(decimalInput(event.target.value))}
                />
              </label>
          ) : null}
          <label className="block space-y-1.5 text-sm font-semibold">
            <span>Ghi chú</span>
            <Textarea
              className="min-h-24 bg-card font-normal"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button size="lg" className="min-h-11" type="submit" disabled={!canSubmit}>
              {pending ? 'Đang lưu…' : 'Lưu'}
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="min-h-11"
              type="button"
              disabled={pending}
              onClick={onClose}
            >
              Huỷ
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
