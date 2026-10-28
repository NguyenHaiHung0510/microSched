import type { MimiOperatingPolicy } from '@/mimi-api'

export function unicodeCodepoints(text: string): number { return Array.from(text).length }
export function operatingPolicyErrors(policy: MimiOperatingPolicy): string[] {
  const errors: string[] = []
  if (!Number.isInteger(policy.input_codepoints) || policy.input_codepoints < 1000 || policy.input_codepoints > 100000) errors.push('Giới hạn nhập cần là số nguyên từ 1.000 đến 100.000.')
  for (const [model, caps] of Object.entries(policy.prices)) for (const [kind, value] of Object.entries(caps)) {
    if (!/^(?:\d+(?:\.\d{1,8})?|\.\d{1,8})$/.test(value) || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 1000) errors.push(`${model} · ${kind}: nhập giá hữu hạn từ 0 đến 1.000, tối đa 8 chữ số thập phân.`)
  }
  return errors
}
