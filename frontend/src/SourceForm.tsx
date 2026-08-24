import { type FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { SOURCE_COLOR_KEYS, SOURCE_COLOR_LABELS, SOURCE_COLORS } from '@/calendar-ui'

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
        <span>Màu nguồn</span>
        <Select value={color} onValueChange={setColor}>
          <SelectTrigger className="h-11 w-full bg-card" aria-label="Màu nguồn">
            <span className="flex items-center gap-2">
              <span
                className="inline-block size-3 rounded-full shrink-0"
                style={{ backgroundColor: SOURCE_COLORS[color] ?? SOURCE_COLORS.slate }}
                aria-hidden="true"
              />
              <span>{SOURCE_COLOR_LABELS[color] ?? color}</span>
            </span>
          </SelectTrigger>
          <SelectContent>
            {SOURCE_COLOR_KEYS.map((key) => (
              <SelectItem key={key} value={key}>
                <span className="flex items-center gap-2">
                  <span
                    className="inline-block size-3 rounded-full shrink-0"
                    style={{ backgroundColor: SOURCE_COLORS[key] }}
                    aria-hidden="true"
                  />
                  <span>{SOURCE_COLOR_LABELS[key] ?? key}</span>
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <p className="text-sm text-muted-foreground">
        {kind === 'ics'
          ? 'File được đọc trong trình duyệt rồi nhập vào nguồn này.'
          : 'Nguồn thủ công dùng để tạo buổi không thuộc file nhập.'}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button size="lg" type="submit" disabled={!name.trim() || pending}>
          {pending ? 'Đang lưu…' : kind === 'ics' ? 'Tạo nguồn' : 'Tạo nguồn'}
        </Button>
        <Button size="lg" variant="outline" type="button" onClick={onCancel}>
          Huỷ
        </Button>
      </div>
    </form>
  )
}
