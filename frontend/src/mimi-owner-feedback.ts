/** Owner action polarity is explicit; preserve the existing server comment contract. */
export function feedbackComment(mood: 'positive' | 'negative', reasons: string[], issue: string): string {
  if (issue.length > 500) throw new Error('Feedback field exceeds500characters')
  if (mood === 'negative' && !issue.trim()) throw new Error('Negative feedback requires an issue')
  const prefix = mood === 'positive' ? 'Phản hồi tích cực: Hữu ích.' : 'Phản hồi chưa tốt.'
  return [prefix, reasons.length ? `Lý do: ${reasons.join(', ')}.` : '', issue.trim()].filter(Boolean).join('\n')
}
