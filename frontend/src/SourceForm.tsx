import { type FormEvent, useState } from 'react'
import { Check } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { CURATED_COLOR_SWATCHES, SOURCE_COLOR_LABELS } from '@/calendar-ui'
import { cn } from '@/lib/utils'

export function SourceForm({
  kind,
  initialName = '',
  initialColor = 'sky',
  pending,
  onSubmit,
  onCancel,
}: {
  kind: 'ics' | 'manual'
  initialName?: string
  initialColor?: string | null
  pending: boolean
  onSubmit: (value: { name: string; color: string }) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initialName)
  const [color, setColor] = useState(initialColor ?? 'slate')

  function submit(event: FormEvent) {
    event.preventDefault()
    const cleanName = name.trim()
    if (!cleanName || pending) return
    onSubmit({ name: cleanName, color })
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      <label className="block space-y-1.5 text-sm font-semibold">
        <span>Tên nguồn lịch</span>
        <Input
          autoFocus
          className="h-11 bg-card"
          value={name}
          required
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <div className="space-y-1.5 text-sm font-semibold">
        <span>Màu nhận diện</span>
        <div data-testid="source-color-swatch-picker" className="flex flex-wrap items-center gap-3 pt-1">
          {CURATED_COLOR_SWATCHES.map((swatch) => {
            const isSelected = color === swatch.key
            return (
              <button
                type="button"
                key={swatch.key}
                data-testid={`source-color-swatch-${swatch.key}`}
                aria-label={swatch.label}
                onClick={() => setColor(swatch.key)}
                className={cn(
                  'flex size-8 cursor-pointer items-center justify-center rounded-full border-2 transition-all hover:scale-110',
                  isSelected
                    ? 'border-foreground ring-2 ring-primary/40 ring-offset-1 scale-105'
                    : 'border-transparent hover:border-border',
                )}
                style={{ backgroundColor: swatch.hex }}
              >
                {isSelected ? <Check className="size-4 stroke-[3] text-white" /> : null}
              </button>
            )
          })}
        </div>
        <p className="text-xs text-muted-foreground">
          {SOURCE_COLOR_LABELS[color] ?? color}
        </p>
      </div>
      <p className="text-sm text-muted-foreground">
        {kind === 'ics'
          ? 'File được đọc trong trình duyệt rồi nhập vào nguồn này.'
          : 'Nguồn thủ công dùng để tạo buổi không thuộc file nhập.'}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button size="lg" type="submit" disabled={!name.trim() || pending}>
          {pending ? 'Đang lưu…' : initialName ? 'Lưu thay đổi' : 'Tạo nguồn'}
        </Button>
        <Button size="lg" variant="outline" type="button" onClick={onCancel}>
          Huỷ
        </Button>
      </div>
    </form>
  )
}
