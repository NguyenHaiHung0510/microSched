import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { matchesImportAcknowledgement, validateImportReport } from '../src/CalendarScreen'

describe('calendar import acknowledgement', () => {
  const request = { sourceId: 'source-1', startedAt: 100 }
  const row = {
    operation_kind: 'calendar.import',
    entity_id: 'source-1',
    created_at: 100,
  }

  it('correlates only the expected import, source, and request time', () => {
    expect(matchesImportAcknowledgement(request, row)).toBe(true)
    expect(matchesImportAcknowledgement(request, { ...row, operation_kind: 'calendar_source.update' })).toBe(false)
    expect(matchesImportAcknowledgement(request, { ...row, entity_id: 'other-source' })).toBe(false)
    expect(matchesImportAcknowledgement(request, { ...row, created_at: 99 })).toBe(false)
  })

  it('accepts only a complete, internally consistent server report', () => {
    expect(validateImportReport({
      parsed: 4,
      inserted: 2,
      removed: 18,
      duplicates: 1,
      skipped: ['unsupported recurrence'],
    })).toEqual({
      parsed: 4,
      inserted: 2,
      removed: 18,
      duplicates: 1,
      skipped: ['unsupported recurrence'],
    })
    expect(validateImportReport({ inserted: 2, skipped: [] })).toBeNull()
    expect(validateImportReport({ parsed: 4, inserted: 2, removed: 1, duplicates: 0, skipped: [] })).toBeNull()
    expect(validateImportReport({ parsed: 1, inserted: 1, removed: 0, duplicates: 0, skipped: [4] })).toBeNull()
    expect(validateImportReport({ parsed: 1, inserted: 1, removed: -1, duplicates: 0, skipped: [] })).toBeNull()
    expect(validateImportReport({ parsed: 1, inserted: 1, removed: Infinity, duplicates: 0, skipped: [] })).toBeNull()
  })
})

describe('owned calendar source coverage', () => {
  const files = ['CalendarScrollView.tsx', 'CalendarScreen.tsx', 'ReminderSourceDialog.tsx']
  const sources = files.map((file) => readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8'))

  it('has no direct apiRequest write or callback invalidation in the owned surfaces', () => {
    for (const [index, source] of sources.entries()) {
      const ast = ts.createSourceFile(files[index], source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
      const visit = (node: ts.Node) => {
        if (ts.isCallExpression(node) && node.expression.getText(ast) === 'apiRequest') {
          expect(node.arguments[1]?.getText(ast) ?? '').not.toMatch(/method\s*:/)
        }
        if (ts.isPropertyAccessExpression(node)) expect(node.name.text).not.toBe('invalidateQueries')
        ts.forEachChild(node, visit)
      }
      visit(ast)
    }
  })

  it('covers both calendar creates and both task patches with typed queued commands', () => {
    const kinds: string[] = []
    const ast = ts.createSourceFile(files[0], sources[0], ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node) && node.expression.getText(ast) === 'queuedRequest') {
        const kind = node.arguments[1]
        if (kind && ts.isStringLiteral(kind)) kinds.push(kind.text)
      }
      ts.forEachChild(node, visit)
    }
    visit(ast)
    expect(kinds).toEqual(['task.create', 'task.update', 'task.update', 'task.create'])
  })
})
