/** Match the CR/LF sanitization of an HTML input[type=text], without trimming text. */
export function singleLineTitle(value: string): string {
  return value.replace(/[\r\n]/g, '')
}
