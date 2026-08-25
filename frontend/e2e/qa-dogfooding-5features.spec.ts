import { expect, test } from './fixtures/tracker'

test.describe('QA Dogfooding UI/UX Verification', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/tracker/dashboard**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          f1_total: 1500000,
          f2_current: 1500000,
          f2_previous: 1200000,
          f5_net: -1500000,
          f6: { subscriptions: [], total_fixed: 0, corrupted_subscription_count: 0 },
          corrupted_entry_count: 0,
          a4_trend: { trend: 'stable' },
        }),
      })
    })
    await page.route('**/api/notes**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [
          {
            id: 'note-001',
            title: 'Ghi chú kiểm thử QA',
            body_md: 'Nội dung ghi chú ban đầu\n\n---\n> 💬 **Lời nhắn từ tương lai** (10:00 · 25/08/2026):\n> Lời nhắn gửi tới tương lai 1',
            is_private: false,
            created_at: '2026-08-25T10:00:00Z',
            updated_at: '2026-08-25T11:00:00Z',
            pinned: false,
            priority: 0,
            items: [],
          }
        ] }),
      })
    })
    await page.route('**/api/calendar/sources**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [
          { id: 'src-1', name: 'Nguồn Lịch Mẫu', kind: 'manual', color: 'rose', is_visible: true, event_count: 0 }
        ] }),
      })
    })
    await page.route('**/api/calendar/events**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
    })
    await page.route('**/api/calendar/annotations**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
    })
  })

  test('Feature 1: Calendar View Date Cell border reverted & Sticky Header 2 tiers intact', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()

    // Verify Sticky Weekday 7-column header is visible with T2..CN
    await expect(page.getByText('T2', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('T3', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('CN', { exact: true }).first()).toBeVisible()

    // Verify 'Hôm nay' button is visible in header
    await expect(page.getByRole('button', { name: 'Hôm nay' })).toBeVisible()

    // Verify date cells render with REVERTED border (border-transparent on non-today cells)
    const dayCells = page.locator('[data-testid="calendar-day-cell"]')
    await expect(dayCells.first()).toBeVisible()
    const nonTodayCell = dayCells.filter({ hasNotText: 'Hôm nay' }).first()
    const classAttr = await nonTodayCell.getAttribute('class')
    expect(classAttr).toContain('border-transparent')
    expect(classAttr).not.toContain('border-border/60')
  })

  test('Feature 2: Note Speech Bubble callout and Edit/Delete message buttons', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('tab', { name: 'Ghi chú' }).click()

    // Verify Note card is rendered
    await expect(page.getByTestId('note-card')).toBeVisible()

    // Verify Speech Bubble Callout in amber tone on note card
    const speechBubble = page.getByTestId('note-reflection-box')
    await expect(speechBubble.first()).toBeVisible()
    await expect(speechBubble.first()).toContainText('Lời nhắn gửi tới tương lai 1')

    // Verify Edit (Pencil) and Delete (Trash2) buttons on message bubble
    await expect(speechBubble.first().getByRole('button', { name: 'Sửa lời nhắn' })).toBeVisible()
    await expect(speechBubble.first().getByRole('button', { name: 'Xoá lời nhắn' })).toBeVisible()

    // Verify friendly button label '💬 Gửi lời nhắn tương lai'
    await expect(page.getByTestId('note-future-reflection-trigger')).toBeVisible()
    await expect(page.getByTestId('note-future-reflection-trigger')).toContainText('💬 Gửi lời nhắn tương lai')
  })

  test('Feature 3: Calendar Source 1-touch Color Swatches and Edit button', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await page.getByTestId('calendar-view-toggle-list').click()

    // Verify Edit button on Calendar Source card
    await expect(page.getByTestId('calendar-source-edit')).toBeVisible()

    // Open Source Form (Add Source)
    await page.getByTestId('calendar-manual-source-button').click()

    // Verify 1-touch color swatches picker exists (replacing dropdown Select)
    await expect(page.getByTestId('source-color-swatch-picker')).toBeVisible()
    await expect(page.getByTestId('source-color-swatch-rose')).toBeVisible()
    await expect(page.getByTestId('source-color-swatch-teal')).toBeVisible()
    await expect(page.getByTestId('source-color-swatch-indigo')).toBeVisible()
    await expect(page.getByTestId('source-color-swatch-orange')).toBeVisible()
    await expect(page.getByTestId('source-color-swatch-emerald')).toBeVisible()
  })

  test('Feature 4: Tracker Enhanced Top Finance Card with monthly spend & compare', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('tab', { name: 'Theo dõi' }).click()

    // Verify Tracker top finance card is visible
    const financeCard = page.getByTestId('tracker-finance-overview')
    await expect(financeCard).toBeVisible()
    await expect(financeCard.getByText('Tài chính')).toBeVisible()
    await expect(financeCard.getByTestId('tracker-finance-total')).toBeVisible()
    await expect(financeCard.getByTestId('tracker-finance-total')).toContainText('1.500.000 ₫')
    await expect(financeCard.getByTestId('subscription-entry')).toBeVisible()

    // Verify Capture Grid is visible and grouped
    await expect(page.getByTestId('tracker-grid')).toBeVisible()
    await expect(page.getByTestId('tracker-button').first()).toBeVisible()
  })
})
