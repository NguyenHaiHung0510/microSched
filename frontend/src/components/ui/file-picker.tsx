import { useRef } from 'react'

import { Button } from '@/components/ui/button'

export function FilePicker({
  accept,
  label = 'Chọn file ICS',
  onPick,
  disabled = false,
  testId,
}: {
  accept?: string
  label?: string
  onPick: (file: File) => void
  disabled?: boolean
  testId?: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <>
      <input
        ref={inputRef}
        className="sr-only"
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0]
          if (file) onPick(file)
          event.currentTarget.value = ''
        }}
      />
      <Button
        type="button"
        data-testid={testId}
        size="lg"
        variant="outline"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        {label}
      </Button>
    </>
  )
}
