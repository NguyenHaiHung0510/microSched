import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MimiCheckpointContents } from '../src/MimiCheckpointViewer'
import type { MimiCheckpointView } from '../src/mimi-api'

describe('checkpoint user view', () => {
  it('separates current constraints from superseded history and preserves quoted Vietnamese sources', () => {
    const view: MimiCheckpointView = {
      conversation_id: 'synthetic-conversation', checkpoint_id: 'snapshot', frontier: 18, checkpoint_sha256: 'verified-hash', activated_at: '2026-10-02T08:00:00Z',
      checkpoint: {
        summary: 'Học tối thứ sáu; ![ảnh](https://untrusted.invalid/track) <script>unsafe()</script>', summary_kind: 'semantic_model',
        decisions: [], unresolved: [], source_refs: [{ id: 'message-17', sequence: 17, sha256: 'source-hash' }],
        constraint_ledger: [
          { id: 'new', text: '20:00–20:45', kind: 'decision', status: 'active', source: { sequence: 17, quote: 'Đổi sang 20:00', sha256: 'source-hash' } },
          { id: 'old', text: '19:00–20:00', kind: 'decision', status: 'superseded' },
        ],
      },
    }
    const html = renderToStaticMarkup(<MimiCheckpointContents view={view} />)
    expect(html).toContain('tin nhắn 18')
    expect(html).toContain('Được kích hoạt lúc')
    expect(html).toContain('GMT+7')
    expect(html).toContain('20:00–20:45')
    expect(html).toContain('Đổi sang 20:00')
    expect(html).toContain('Ràng buộc đã thay thế hoặc giải quyết (1)')
    expect(html).toContain('không cấp quyền thực thi')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('<img')
    expect(html).toContain('source-hash')
  })
  it('does not manufacture a summary when no checkpoint is active', () => {
    const html = renderToStaticMarkup(<MimiCheckpointContents view={{ conversation_id: 'empty', checkpoint_id: null, frontier: 0, checkpoint_sha256: null, activated_at: null, checkpoint: null }} />)
    expect(html).toContain('Chưa có bản tóm tắt được kích hoạt')
    expect(html).not.toContain('Tóm tắt bằng model')
  })
})
