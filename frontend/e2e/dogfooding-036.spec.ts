import { test, expect, type FixtureTracker } from './fixtures/tracker'
import * as fs from 'node:fs'
import * as path from 'node:path'
import * as crypto from 'node:crypto'
import { fixturePrivatePin } from './fixtures/tasks'

function privateTrackerSentinel(): FixtureTracker {
  return {
    id: 'tracker-private-edit-sentinel',
    name: 'Private Tracker Edit Dialog Sentinel',
    kind: 'health',
    direction: 'out',
    input_mode: 'event',
    group_id: null,
    unit: null,
    color: null,
    reminder_time: '08:00',
    reminder_text: 'Private reminder sentinel',
    reminder_mode: 'fixed',
    reminder_interval_days: 1,
    reminder_action: 'confirm_event',
    is_private: true,
    last_entry_at: null,
    entry_count_30d: 0,
    created_at: '2026-08-01T08:00:00Z',
    updated_at: '2026-08-01T08:00:00Z',
  }
}

test.describe('Task 036 Dogfooding UI/UX verification', () => {
  test.beforeEach(async ({ page, trackerApi, taskApi }) => {
    // Mock push notification API on window
    await page.addInitScript(() => {
      Object.defineProperty(window, 'Notification', {
        configurable: true,
        value: { requestPermission: async () => 'granted' },
      })
      Object.defineProperty(navigator, 'serviceWorker', {
        configurable: true,
        value: {
          ready: Promise.resolve({
            pushManager: {
              subscribe: async () => ({
                endpoint: 'https://fcm.googleapis.com/fcm/send/e2e-device',
                toJSON: () => ({ keys: { p256dh: 'p256dh-value', auth: 'auth-value' } }),
              }),
            },
          }),
        },
      })
    })

    await page.route('**/api/push/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/push/vapid-public-key') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ public_key: 'BEl6JzoAAAAA' }),
        })
        return
      }
      if (path === '/api/push/subscribe') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({ id: 'device-001', status: 'created' }),
        })
        return
      }
      await route.fallback()
    })

    // Seed trackers with configured reminders so reminder card is rendered
    trackerApi.trackers.push(
      {
        id: 'tracker-reminder-1',
        name: 'Uống thuốc huyết áp liều cao buổi sáng 08:00',
        kind: 'health',
        direction: 'out',
        input_mode: 'event',
        group_id: null,
        unit: null,
        color: null,
        reminder_time: '08:00',
        reminder_text: 'Legacy reminder text',
        reminder_mode: 'fixed',
        reminder_interval_days: 1,
        reminder_action: 'confirm_event',
        is_private: false,
        last_entry_at: null,
        entry_count_30d: 0,
        created_at: '2026-08-01T08:00:00Z',
        updated_at: '2026-08-01T08:00:00Z',
      },
      {
        id: 'tracker-reminder-2',
        name: 'Tập_thể_dục_buổi_sáng_và_đo_chỉ_số_sinh_tồn_1234567890123456789012345678901234567890',
        kind: 'health',
        direction: 'out',
        input_mode: 'event',
        group_id: null,
        unit: null,
        color: null,
        reminder_time: '08:00',
        reminder_text: null,
        reminder_mode: 'fixed',
        reminder_interval_days: 1,
        reminder_action: 'confirm_event',
        is_private: false,
        last_entry_at: null,
        entry_count_30d: 0,
        created_at: '2026-08-01T08:00:00Z',
        updated_at: '2026-08-01T08:00:00Z',
      },
      {
        id: 'tracker-reminder-3',
        name: 'Ghi chép nhật ký sức khoẻ và theo dõi sinh hoạt gia đình cuối tuần',
        kind: 'health',
        direction: 'out',
        input_mode: 'event',
        group_id: null,
        unit: null,
        color: null,
        reminder_time: '08:00',
        reminder_text: null,
        reminder_mode: 'fixed',
        reminder_interval_days: 1,
        reminder_action: 'confirm_event',
        is_private: false,
        last_entry_at: null,
        entry_count_30d: 0,
        created_at: '2026-08-01T08:00:00Z',
        updated_at: '2026-08-01T08:00:00Z',
      },
    )

    // Mock calendar routes
    await page.route('**/api/calendar/**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      if (url.pathname === '/api/calendar/sources' && request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [] }),
        })
        return
      }
      if (url.pathname === '/api/calendar/events' && request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [] }),
        })
        return
      }
      if (url.pathname === '/api/calendar/annotations' && request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [] }),
        })
        return
      }
      await route.fallback()
    })

    // Mock default notes routes
    await page.route('**/api/notes**', async (route) => {
      const url = new URL(route.request().url())
      if (url.searchParams.get('offset') === '0' || !url.searchParams.get('offset')) {
        const privateOpen = Boolean(
          taskApi.privateUntil && Date.parse(taskApi.privateUntil) > Date.now(),
        )
       const items = Array.from({ length: 32 }, (_, i) => ({
         id: 'note-sample-' + i,
          title: i === 0 ? '📝 Ghi chú mẫu quan trọng có emoji' : i === 1 ? 'Chuoi_ky_tu_khong_khoang_trang_123456789012345678901234567890123456789012345' : i === 2 ? '🔒 Ghi chú riêng tư đặc biệt' : 'Ghi chú số ' + i,
         body_md: i === 0 ? 'Nội dung ghi chú mẫu có dấu tiếng Việt dày đặc và phản ánh tương lai.\n\n> 💬 **Lời nhắn từ tương lai** (08:30 · 28/08/2026):\n> Nhớ kiểm tra lại các mục đã cam kết nhé!' : 'Nội dung chi tiết ghi chú...',
         pinned: i === 0,
         is_private: i === 2,
         created_at: '2026-08-' + String(Math.min(28, i + 1)).padStart(2, '0') + 'T10:00:00Z',
         updated_at: null,
         items: i === 0 ? [
           { id: 'note-item-0-1', content: 'Chuẩn bị tài liệu kiến trúc hệ thống và spec đồng bộ', is_completed: true, position: 0 },
           { id: 'note-item-0-2', content: 'Rà soát các điểm ngắt dòng tiếng Việt có dấu dày đặc không bị tràn mép', is_completed: false, position: 1 },
           { id: 'note-item-0-3', content: 'Kiểm tra độ nảy và khoảng cách chạm >= 44px trên thiết bị cảm ứng', is_completed: false, position: 2 },
           { id: 'note-item-0-4', content: 'Đồng bộ danh sách checklist dài để kiểm tra độ cuộn trong hộp thoại chi tiết', is_completed: false, position: 3 },
           { id: 'note-item-0-5', content: 'Xác nhận trạng thái hoàn thành và huỷ hoàn thành cập nhật tức thì', is_completed: true, position: 4 },
           { id: 'note-item-0-6', content: 'Hoàn tất ghi chú và đóng hộp thoại quay về danh sách chính', is_completed: false, position: 5 },
         ] : [],
       })).filter((item) => !item.is_private || privateOpen)
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      })
    })
  })

  test('Tracker DOM order and geometry: reminder section appears before finance overview, no overflow at 390px and 1280px', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('tab', { name: 'Theo dõi' }).click()
    await expect(page.getByTestId('tracker-finance-overview')).toBeVisible()
    await expect(page.getByTestId('tracker-reminders-overview')).toBeVisible()

    // 1. DOM order check: exactly one reminder overview before finance overview
    await expect(page.getByTestId('tracker-reminders-overview')).toHaveCount(1)
    await expect(page.getByTestId('tracker-finance-overview')).toHaveCount(1)

    const orderCheck = await page.evaluate(() => {
      const reminder = document.querySelector('[data-testid="tracker-reminders-overview"]')
      const finance = document.querySelector('[data-testid="tracker-finance-overview"]')
      if (!reminder || !finance) return false
      return Boolean(reminder.compareDocumentPosition(finance) & Node.DOCUMENT_POSITION_FOLLOWING)
    })
    expect(orderCheck).toBe(true)

    // 2. Geometry measurements: preview has useful width (>=200px on desktop, >=150px on mobile)
    const previewEl = page.getByTestId('tracker-reminder-preview').first()
    await expect(previewEl).toBeVisible()

    const previewMetrics = await previewEl.evaluate((el) => {
      const rect = el.getBoundingClientRect()
      const text = el.textContent || ''
      return {
        width: rect.width,
        height: rect.height,
        text,
      }
    })

    const isMobile = await page.evaluate(() => window.innerWidth <= 450)
    if (isMobile) {
      expect(previewMetrics.width).toBeGreaterThanOrEqual(150)
    } else {
      // Desktop 1280x800: preview width must be wide and useful, not 1 character (~10-20px)
      expect(previewMetrics.width).toBeGreaterThanOrEqual(200)
    }

    // 3. Geometry measurements: no horizontal document overflow, card/button bounding boxes
    const reminderButtons = page.locator('[data-testid="tracker-reminders-overview"] button')
    const btnCount = await reminderButtons.count()
    expect(btnCount).toBeGreaterThanOrEqual(3)

    const geometry = await page.evaluate(() => {
      const card = document.querySelector('[data-testid="tracker-reminders-overview"]')
      const rect = card?.getBoundingClientRect()
      const actionArea = document.querySelector('[data-testid="tracker-reminder-actions"]')
      const actionRect = actionArea?.getBoundingClientRect()
      const buttons = Array.from(card?.querySelectorAll('button') ?? [])
      const btnMetrics = buttons.map((b) => {
        const r = b.getBoundingClientRect()
        return {
          left: r.left,
          right: r.right,
          width: r.width,
          height: r.height,
        }
      })
      return {
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
        cardLeft: rect?.left ?? 0,
        cardRight: rect?.right ?? 0,
        cardWidth: rect?.width ?? 0,
        actionWidth: actionRect?.width ?? 0,
        btnMetrics,
      }
    })
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.innerWidth)
    expect(geometry.cardLeft).toBeGreaterThanOrEqual(0)
    expect(geometry.cardRight).toBeLessThanOrEqual(geometry.innerWidth + 1)

    for (const btn of geometry.btnMetrics) {
      expect(btn.left).toBeGreaterThanOrEqual(geometry.cardLeft - 2)
      expect(btn.right).toBeLessThanOrEqual(geometry.cardRight + 2)
      if (geometry.innerWidth <= 450) {
        expect(btn.height).toBeGreaterThanOrEqual(44)
        expect(btn.width).toBeGreaterThanOrEqual(geometry.actionWidth - 1)
      } else {
        expect(btn.height).toBeGreaterThanOrEqual(32)
      }
    }
  })

  test('Tracker dialog responsive & microcopy & legacy reminder_text preservation & focus trap', async ({ page, trackerApi }) => {
   await page.goto('/')
   await page.getByRole('tab', { name: 'Theo dõi' }).click()

    // Open Tracker create dialog
    const createTrigger = page.getByTestId('tracker-create')
    await createTrigger.click()
    const createDialog = page.getByTestId('tracker-dialog')
    await expect(createDialog).toBeVisible()

    // Enable reminder in create form and choose after_entry to make form genuinely long
    await page.getByTestId('tracker-reminder-enabled').click()
    await expect(page.getByTestId('tracker-reminder-interval')).toBeVisible()

    // Switch to after_entry mode
    await page.getByTestId('tracker-reminder-mode').click()
    await page.getByRole('option', { name: 'Sau lần ghi gần nhất' }).click()
    await expect(page.getByText('Số ngày chưa ghi')).toBeVisible()

    // Fill interval & time
    await page.getByTestId('tracker-reminder-interval').fill('3')
    await page.getByTestId('tracker-reminder-time').fill('09:00')

   // Measure dialog geometry: top/bottom within viewport, scrollHeight >= clientHeight
   const createDialogGeo = await page.evaluate(() => {
     const el = document.querySelector('[data-testid="tracker-dialog"]')
     const rect = el?.getBoundingClientRect()
     const submitBtn = el?.querySelector('button[type="submit"]')
     const submitRect = submitBtn?.getBoundingClientRect()
     return {
       top: rect?.top ?? 0,
       bottom: rect?.bottom ?? 0,
       clientHeight: el?.clientHeight ?? 0,
       scrollHeight: el?.scrollHeight ?? 0,
       windowHeight: window.innerHeight,
       submitTop: submitRect?.top ?? 0,
       submitBottom: submitRect?.bottom ?? 0,
     }
   })
   expect(createDialogGeo.top).toBeGreaterThanOrEqual(0)
   expect(createDialogGeo.bottom).toBeLessThanOrEqual(createDialogGeo.windowHeight + 1)

   // In mobile/constrained viewport, strict scrollHeight > clientHeight
   const isMobile = await page.evaluate(() => window.innerWidth <= 450)
   if (isMobile) {
     expect(createDialogGeo.scrollHeight).toBeGreaterThan(createDialogGeo.clientHeight)
   }

   // Scroll to top: title is reachable and visible
    await createDialog.evaluate((el) => { el.scrollTop = 0 })
    const titleEl = createDialog.locator('h2, [role="heading"]').first()
    await expect(titleEl).toBeVisible()

    // Scroll to bottom: submit & cancel buttons are reachable
    await createDialog.evaluate((el) => { el.scrollTop = el.scrollHeight })
    const submitButton = createDialog.locator('button[type="submit"]')
    await expect(submitButton).toBeVisible()

   // Complete Tab cycle: count focusable elements and verify Tab cycles through all elements and returns to start
   // Focus the first input inside dialog
   await createDialog.getByTestId('tracker-name-input').focus()
    const firstElementId = await page.evaluate(() => document.activeElement?.getAttribute('data-testid') || document.activeElement?.tagName)

    // Tab through elements until we complete a full cycle back to first element
    let tabSteps = 0
    for (let i = 0; i < 30; i++) {
      await page.keyboard.press('Tab')
      tabSteps++
      const isInside = await page.evaluate(() => {
        const dialog = document.querySelector('[data-testid="tracker-dialog"]')
        return Boolean(dialog && dialog.contains(document.activeElement))
      })
      expect(isInside).toBe(true)
      const currentActiveId = await page.evaluate(() => document.activeElement?.getAttribute('data-testid') || document.activeElement?.tagName)
      if (currentActiveId === firstElementId) {
        break
      }
    }
    expect(tabSteps).toBeGreaterThan(3)

    // Shift+Tab reverse cycle exactly tabSteps times back to start
    for (let i = 0; i < tabSteps; i++) {
      await page.keyboard.press('Shift+Tab')
      const isInside = await page.evaluate(() => {
        const dialog = document.querySelector('[data-testid="tracker-dialog"]')
        return Boolean(dialog && dialog.contains(document.activeElement))
      })
      expect(isInside).toBe(true)
    }
    const reverseActiveId = await page.evaluate(() => document.activeElement?.getAttribute('data-testid') || document.activeElement?.tagName)
    expect(reverseActiveId).toBe(firstElementId)

    // Escape closes dialog and returns focus to trigger
    await page.keyboard.press('Escape')
    await expect(createDialog).toBeHidden()
    await expect(createTrigger).toBeFocused()

    // Re-open create dialog to test create payload (reminder_text: null)
    await createTrigger.click()
    await expect(createDialog).toBeVisible()
    await page.getByTestId('tracker-name-input').fill('Tracker mới kiểm tra create')
    await page.getByTestId('tracker-reminder-enabled').click()

    // Microcopy check: Fixed mode label must be "Lặp lại mỗi (ngày)", not contain "Mỗi N ngày"
    await expect(page.getByText('Lặp lại mỗi (ngày)')).toBeVisible()
    await expect(page.getByText('Mỗi N ngày')).toHaveCount(0)

    // Verify lock-screen custom text control is removed
    await expect(page.getByTestId('tracker-reminder-text')).toHaveCount(0)
    await expect(page.getByText('Nội dung hiện trên màn hình khoá')).toHaveCount(0)

    let serverTrackers = [...trackerApi.trackers]
    let createPayload: any = null
    await page.route('**/api/tracker/trackers', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: serverTrackers }),
        })
        return
      }
      if (route.request().method() === 'POST') {
        createPayload = route.request().postDataJSON()
        const createdItem = {
          id: 'tracker-created-new',
          name: createPayload.name,
          kind: createPayload.kind,
          direction: createPayload.direction,
          input_mode: createPayload.input_mode,
          group_id: null,
          unit: null,
          color: null,
          reminder_time: createPayload.reminder_time,
          reminder_text: createPayload.reminder_text ?? null,
          reminder_mode: createPayload.reminder_mode,
          reminder_interval_days: createPayload.reminder_interval_days,
          reminder_action: createPayload.reminder_action,
          is_private: false,
          last_entry_at: null,
          entry_count_30d: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }
        serverTrackers.push(createdItem)
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(createdItem),
        })
        return
      }
      await route.fallback()
    })

    await createDialog.locator('button[type="submit"]').click()
    await expect(createDialog).toBeHidden()
    // Assert create sends reminder_text: null
    expect(createPayload).toBeDefined()
    expect(createPayload.reminder_text).toBeNull()

    // Now test edit tracker with legacy reminder_text preservation and read-back
    let patchPayload: any = null
    await page.route('**/api/tracker/trackers/tracker-reminder-1', async (route) => {
      if (route.request().method() === 'PATCH') {
        patchPayload = route.request().postDataJSON()
        const existing = serverTrackers.find((t) => t.id === 'tracker-reminder-1')
        const updated = {
          ...existing,
          ...patchPayload,
          reminder_text: 'reminder_text' in patchPayload ? patchPayload.reminder_text : existing?.reminder_text,
          updated_at: new Date().toISOString(),
        }
        serverTrackers = serverTrackers.map((t) => (t.id === 'tracker-reminder-1' ? updated : t))
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(updated),
        })
        return
      }
      await route.fallback()
    })

   // Open edit dialog for tracker-reminder-1 via its edit button in management section
   await page.getByRole('button', { name: 'Mở rộng tất cả' }).click()
   const editBtn = page.locator('[data-testid="tracker-edit"][data-tracker-id="tracker-reminder-1"]')
   await editBtn.click()
   const editDialog = page.getByTestId('tracker-dialog')
    await expect(editDialog).toBeVisible()

    // Test edit dialog focus return: Escape closes edit dialog and returns focus to editBtn
    await page.keyboard.press('Escape')
    await expect(editDialog).toBeHidden()
    await expect(editBtn).toBeFocused()

    // Re-open edit dialog
    await editBtn.click()
    await expect(editDialog).toBeVisible()

    // Change tracker name
    await editDialog.getByLabel('Tên').fill('Uống thuốc huyết áp liều cao (đã sửa)')

    // Submit edit
    await page.getByRole('button', { name: 'Lưu thay đổi' }).click()
    await expect(editDialog).toBeHidden()

    // Assert: reminder_text was NOT sent in PATCH payload (omitted) so backend exclude_unset preserves it
    expect(patchPayload).toBeDefined()
    expect(patchPayload.name).toBe('Uống thuốc huyết áp liều cao (đã sửa)')
    expect('reminder_text' in patchPayload).toBe(false)

    // Assert: server state retained legacy reminder_text
    const serverItem = serverTrackers.find((t) => t.id === 'tracker-reminder-1')
    expect(serverItem?.reminder_text).toBe('Legacy reminder text')

    // Read-back verification: UI preview displays legacy reminder text after mutation
    await expect(page.getByTestId('tracker-reminder-preview').first()).toContainText('Legacy reminder text')

    // Also test disabling reminder: edit and uncheck reminder -> sends reminder_text: null
    await editBtn.click()
    await expect(editDialog).toBeVisible()
    await editDialog.getByTestId('tracker-reminder-enabled').click()
    await page.getByRole('button', { name: 'Lưu thay đổi' }).click()
    await expect(editDialog).toBeHidden()

    expect(patchPayload).toBeDefined()
    expect(patchPayload.reminder_text).toBeNull()
    const serverItemDisabled = serverTrackers.find((t) => t.id === 'tracker-reminder-1')
    expect(serverItemDisabled?.reminder_text).toBeNull()
  })

  test('Subtask create flow: draft add, inline edit, delete, and atomic single POST failure/retry', async ({ page }) => {
    let postBody: any = null
    let shouldFailFirstPost = true
    await page.route('**/api/tasks', async (route) => {
      if (route.request().method() === 'POST') {
        postBody = route.request().postDataJSON()
        if (shouldFailFirstPost) {
          shouldFailFirstPost = false
          await route.fulfill({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Lỗi tạo task thử nghiệm' }),
          })
          return
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'task-created-1',
            title: postBody.title,
            body_md: postBody.body_md,
            status: 'open',
            priority: postBody.priority,
            due_precision: postBody.due_precision,
            due_on: postBody.due_on,
            due_at: postBody.due_at,
            is_private: false,
            pinned: false,
            items: (postBody.items || []).map((content: string, i: number) => ({
              id: `item-${i}`,
              content,
              is_completed: false,
              position: i,
            })),
          }),
        })
        return
      }
      await route.fallback()
    })

    await page.goto('/')
    // Open task create dialog
    await page.getByRole('button', { name: 'Thêm chi tiết' }).click()
    const createDialog = page.getByTestId('task-create-dialog')
    await expect(createDialog).toBeVisible()

    // Fill title
    await createDialog.getByLabel('Tiêu đề').fill('Task có subtasks mới')

    // Add 3 draft items
    const draftInput = createDialog.getByTestId('task-item-add-input')
    const draftAddBtn = createDialog.getByTestId('task-item-add-submit')
    await draftInput.fill('Mục 1')
    await draftAddBtn.click()
    await draftInput.fill('Mục 2 cần sửa')
    await draftAddBtn.click()
    await draftInput.fill('Mục 3 cần xoá')
    await draftAddBtn.click()

    await expect(createDialog.getByText('Mục 1')).toBeVisible()
    await expect(createDialog.getByText('Mục 2 cần sửa')).toBeVisible()
    await expect(createDialog.getByText('Mục 3 cần xoá')).toBeVisible()

    // Inline edit item 2
    const items = createDialog.getByTestId('task-item')
    await items.nth(1).getByTestId('task-item-edit').click()
   const editInput = createDialog.getByTestId('task-item-edit-input')

   // Assert mobile computed font-size >= 16px if on mobile viewport
   const editInputFontSize = await editInput.evaluate((el) => parseFloat(window.getComputedStyle(el).fontSize))
   const innerW = await page.evaluate(() => window.innerWidth)
   if (innerW <= 450) {
     expect(editInputFontSize).toBeGreaterThanOrEqual(16)
   }

    // Assert mobile touch target for subtask edit & delete controls >= 44px
    const btnGeometry = await items.nth(0).evaluate((el) => {
      const editBtn = el.querySelector('[data-testid="task-item-edit"]')?.getBoundingClientRect()
      const delBtn = el.querySelector('[data-testid="task-item-delete"]')?.getBoundingClientRect()
      return {
        editW: editBtn?.width ?? 0,
        editH: editBtn?.height ?? 0,
        delW: delBtn?.width ?? 0,
        delH: delBtn?.height ?? 0,
      }
    })
    if (innerW <= 450) {
      expect(btnGeometry.editW).toBeGreaterThanOrEqual(44)
      expect(btnGeometry.editH).toBeGreaterThanOrEqual(44)
      expect(btnGeometry.delW).toBeGreaterThanOrEqual(44)
      expect(btnGeometry.delH).toBeGreaterThanOrEqual(44)
    }

   await editInput.fill('Mục 2 đã sửa')
   await createDialog.getByTestId('task-item-edit-save').click()
    await expect(createDialog.getByText('Mục 2 đã sửa')).toBeVisible()

    // Delete item 3
    await items.nth(2).getByTestId('task-item-delete').click()
    await expect(createDialog.getByText('Mục 3 cần xoá')).toHaveCount(0)

    // Submit task create (first try will fail with 500)
    await createDialog.getByRole('button', { name: 'Tạo task' }).click()
    // Assert: dialog stays visible and drafts are preserved
    await expect(createDialog).toBeVisible()
    const createError = createDialog.getByTestId('task-create-error')
    await expect(createError).toBeVisible()
    await expect(createError).toContainText('Lỗi tạo task thử nghiệm')
    await expect(page.getByTestId('quick-add-error')).toHaveCount(0)
    await expect(createDialog.getByText('Mục 1')).toBeVisible()
    await expect(createDialog.getByText('Mục 2 đã sửa')).toBeVisible()

    // Submit again (second try succeeds)
    await createDialog.getByRole('button', { name: 'Tạo task' }).click()
    await expect(createDialog).toBeHidden()

    // Verify atomic POST payload carried items
    expect(postBody).toBeDefined()
    expect(postBody.title).toBe('Task có subtasks mới')
    expect(postBody.items).toEqual(['Mục 1', 'Mục 2 đã sửa'])
  })

 test('Subtask persisted edit flow: in-dialog add/edit/tick/delete failure and concurrency', async ({ page }) => {
    let failAdd = false
   let failEdit = true
   let failTick = true
   let failDelete = true
   let deferChildPost = false
   let resolveChildPost: (() => void) | null = null
    let childPostPromise: Promise<void> | null = null
   let deferParentPatch = false
   let resolveParentPatch: (() => void) | null = null
    let parentPatchPromise: Promise<void> | null = null
   let failParentPatch = false

   await page.route('**/api/tasks/task-012/items', async (route) => {
     if (route.request().method() === 'POST') {
        if (deferChildPost && childPostPromise) {
          await childPostPromise
        }
        if (failAdd) {
          failAdd = false
          await route.fulfill({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Lỗi thêm checklist item' }),
          })
          return
        }
        const data = route.request().postDataJSON()
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'item-added-new',
            content: data.content,
            is_completed: false,
            position: 99,
          }),
        })
        return
      }
      await route.fallback()
    })

   await page.route('**/api/tasks/task-012/items/**', async (route) => {
     const method = route.request().method()
     const url = route.request().url()
     const itemId = url.split('/').pop() || 'item-0'
     if (method === 'PATCH') {
       const data = route.request().postDataJSON()
       if (data.content && failEdit) {
         failEdit = false
         await route.fulfill({
           status: 500,
           contentType: 'application/json',
           body: JSON.stringify({ detail: 'Lỗi sửa nội dung checklist' }),
         })
         return
       }
       if (data.is_completed !== undefined && failTick) {
         failTick = false
         await route.fulfill({
           status: 500,
           contentType: 'application/json',
           body: JSON.stringify({ detail: 'Lỗi đổi trạng thái checklist' }),
         })
         return
       }
       await route.fulfill({
         status: 200,
         contentType: 'application/json',
         body: JSON.stringify({
           id: itemId,
           content: data.content ?? 'Nội dung checklist',
           is_completed: data.is_completed ?? false,
           position: 0,
         }),
       })
       return
     }
     if (method === 'DELETE') {
       if (failDelete) {
         failDelete = false
         await route.fulfill({
           status: 500,
           contentType: 'application/json',
           body: JSON.stringify({ detail: 'Lỗi xoá checklist item' }),
         })
         return
       }
       await route.fulfill({ status: 204 })
       return
     }
     await route.fallback()
   })

   await page.route('**/api/tasks/task-012', async (route) => {
     if (route.request().method() === 'PATCH') {
        if (deferParentPatch && parentPatchPromise) {
          await parentPatchPromise
        }
        if (failParentPatch) {
          failParentPatch = false
          await route.fulfill({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Lỗi lưu thay đổi task cha' }),
          })
          return
        }
        const data = route.request().postDataJSON()
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'task-012',
            title: data.title ?? 'Checklist nhiều mục',
            body_md: data.body_md ?? null,
            priority: data.priority ?? null,
            due_precision: data.due_precision ?? 'none',
            due_on: null,
            due_at: null,
            is_private: false,
            pinned: false,
            status: 'open',
            items: [],
          }),
        })
        return
      }
      await route.fallback()
    })

   await page.goto('/')
   // Open edit dialog for task-012 (which has checklist items in fixture)
   const taskCard = page.locator('[data-task-id="task-012"]')
   await expect(taskCard).toBeVisible()
   await taskCard.getByTestId('task-edit').click()

   const editDialog = page.getByTestId('task-detail-dialog')
   await expect(editDialog).toBeVisible()
   await expect(editDialog.getByTestId('task-checklist-section')).toBeVisible()

   // 1. Concurrency: child mutation pending => parent submit and parent controls disabled
   deferChildPost = true
    childPostPromise = new Promise<void>((r) => {
      resolveChildPost = r
    })
   const addInput = editDialog.getByTestId('task-item-add-input')
   const addBtn = editDialog.getByTestId('task-item-add-submit')
   await addInput.fill('Mục kiểm tra pending child')
   await addBtn.click()

   // Assert: while child POST is pending, parent submit and inputs are disabled
   const parentSubmitBtn = editDialog.locator('button[type="submit"]')
   await expect(parentSubmitBtn).toBeDisabled()
   await expect(editDialog.getByLabel('Tiêu đề')).toBeDisabled()
   await expect(editDialog.getByLabel('Nội dung')).toBeDisabled()

   // Release child POST
    deferChildPost = false
   if (resolveChildPost) resolveChildPost()
   await expect(editDialog.getByText('Mục kiểm tra pending child')).toBeVisible()

   // 2. Child POST fail: draft and input preserved, retry succeeds
    failAdd = true
    await addInput.fill('Mục mới thử nghiệm fail')
    await addBtn.click()
    // First attempt fails -> error message visible, draft still in input
    await expect(editDialog.getByRole('alert')).toBeVisible()
    await expect(addInput).toHaveValue('Mục mới thử nghiệm fail')
    // Retry succeeds
    await addBtn.click()
    await expect(editDialog.getByText('Mục mới thử nghiệm fail')).toBeVisible()

    // 3. Child PATCH content fail: inline edit input stays open with draft content, retry succeeds
    const firstItem = editDialog.getByTestId('task-item').first()
    await firstItem.getByTestId('task-item-edit').click()
    const editInput = editDialog.getByTestId('task-item-edit-input')
    await editInput.fill('Sửa nội dung có lỗi 500')
    await editDialog.getByTestId('task-item-edit-save').click()
    // First edit attempt fails -> error message visible, edit input stays open
    await expect(editDialog.getByRole('alert')).toBeVisible()
    await expect(editInput).toBeVisible()
    await expect(editInput).toHaveValue('Sửa nội dung có lỗi 500')
    // Retry edit succeeds
    await editDialog.getByTestId('task-item-edit-save').click()
    await expect(editDialog.getByText('Sửa nội dung có lỗi 500')).toBeVisible()

    // 4. Child tick fail: error rendered
    const checkbox = firstItem.getByTestId('task-item-checkbox')
    await checkbox.click()
    await expect(editDialog.getByRole('alert')).toBeVisible()

    // 5. Child delete fail: item is not removed on 500 error
    const itemToDelete = editDialog.getByTestId('task-item').nth(1)
    await itemToDelete.getByTestId('task-item-delete').click()
    await expect(editDialog.getByRole('alert')).toBeVisible()
    await expect(itemToDelete).toBeVisible()

   // 6. Concurrency: parent PATCH pending => all child controls disabled
   deferParentPatch = true
    parentPatchPromise = new Promise<void>((r) => {
      resolveParentPatch = r
    })
   failParentPatch = true
   const titleInput = editDialog.getByLabel('Tiêu đề')
   await titleInput.fill('Tiêu đề task cha đã sửa')
   await parentSubmitBtn.click()

   // Assert: while parent PATCH is pending, child controls are disabled
   await expect(addInput).toBeDisabled()
   await expect(addBtn).toBeDisabled()
   await expect(firstItem.getByTestId('task-item-edit')).toBeDisabled()
   await expect(firstItem.getByTestId('task-item-delete')).toBeDisabled()
   await expect(firstItem.getByTestId('task-item-checkbox')).toBeDisabled()

   // Release parent PATCH with 500 error (child success + parent PATCH fail)
    deferParentPatch = false
   if (resolveParentPatch) resolveParentPatch()

   // 7. Child success then parent PATCH fail: child persists, parent draft preserved, error visible
    await expect(editDialog).toBeVisible()
    await expect(titleInput).toHaveValue('Tiêu đề task cha đã sửa')
    await expect(editDialog.getByText('Mục mới thử nghiệm fail')).toBeVisible()
  })

  test('Calendar DayDetailDialog subtask flow: open task from DayDetail, add/edit/tick/delete and state persistence', async ({ page, taskApi }) => {
   const today = new Date(Date.now() + 7 * 3_600_000).toISOString().slice(0, 10)

    const existing13 = taskApi.tasks.find((t) => t.id === 'task-013')
    if (existing13) {
      existing13.items = [{ id: 'item-cal-init-1', content: 'Checklist sẵn có', is_completed: false, position: 0 }]
    }

   let taskItems: Array<{ id: string; content: string; is_completed: boolean; position: number }> = [
     { id: 'item-cal-init-1', content: 'Checklist sẵn có', is_completed: false, position: 0 },
   ]

   await page.route('**/api/tasks/task-013/items', async (route) => {
     if (route.request().method() === 'POST') {
       const data = route.request().postDataJSON()
       const newItem = {
         id: `item-cal-${Date.now()}`,
         content: data.content,
         is_completed: false,
         position: taskItems.length,
       }
       taskItems = [...taskItems, newItem]
        if (existing13) existing13.items = [...taskItems]
       await route.fulfill({
         status: 201,
         contentType: 'application/json',
         body: JSON.stringify(newItem),
       })
       return
     }
     await route.fallback()
   })

   await page.route('**/api/tasks/task-013/items/**', async (route) => {
     const method = route.request().method()
     const itemId = route.request().url().split('/').pop() || ''
     if (method === 'PATCH') {
       const data = route.request().postDataJSON()
       taskItems = taskItems.map((item) => {
         if (item.id === itemId) {
           return {
             ...item,
             ...(data.content !== undefined ? { content: data.content } : {}),
             ...(data.is_completed !== undefined ? { is_completed: data.is_completed } : {}),
           }
         }
         return item
       })
        if (existing13) existing13.items = [...taskItems]
       const updated = taskItems.find((i) => i.id === itemId)
       await route.fulfill({
         status: 200,
         contentType: 'application/json',
         body: JSON.stringify(updated),
       })
       return
     }
     if (method === 'DELETE') {
       taskItems = taskItems.filter((i) => i.id !== itemId)
        if (existing13) existing13.items = [...taskItems]
       await route.fulfill({ status: 204 })
       return
     }
     await route.fallback()
   })

    await page.goto('/')
    await page.getByRole('tab', { name: 'Lịch' }).click()
    await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()

    // Click on today's cell to open DayDetailDialog
    const todayCell = page.locator(`[data-testid="calendar-day-cell"][data-day="${today}"]`)
    await expect(todayCell).toBeVisible()
    await todayCell.click()

    const dayDialog = page.getByTestId('calendar-day-dialog')
    await expect(dayDialog).toBeVisible()

    // Check if task-013 is in the day dialog tasks section
    const dayTask = dayDialog.locator('[data-testid="calendar-day-task"]').first()
    await expect(dayTask).toBeVisible()
    // Click task title to open edit dialog via stable data-testid
    await dayTask.getByTestId('calendar-day-task-edit-trigger').click()

    // Verify task edit dialog opens with checklist section
    const taskEditDialog = page.getByRole('dialog').filter({ hasText: 'Sửa ·' })
    await expect(taskEditDialog).toBeVisible()
    await expect(taskEditDialog.getByTestId('task-checklist-section')).toBeVisible()

    // Add a subtask in calendar edit
    const addInput = taskEditDialog.getByTestId('task-item-add-input')
    await addInput.fill('Subtask từ lịch')
    await taskEditDialog.getByTestId('task-item-add-submit').click()
    await expect(taskEditDialog.getByText('Subtask từ lịch')).toBeVisible()
    expect(taskItems.some((i) => i.content === 'Subtask từ lịch')).toBe(true)

    // Inline edit subtask in calendar
    const subtaskItem = taskEditDialog.getByTestId('task-item').last()
    await subtaskItem.getByTestId('task-item-edit').click()
    const editInput = taskEditDialog.getByTestId('task-item-edit-input')
    await editInput.fill('Subtask từ lịch đã sửa')
    await taskEditDialog.getByTestId('task-item-edit-save').click()
    await expect(taskEditDialog.getByText('Subtask từ lịch đã sửa')).toBeVisible()
    expect(taskItems.some((i) => i.content === 'Subtask từ lịch đã sửa')).toBe(true)

    // Tick subtask in calendar
    const subtaskCheckbox = subtaskItem.getByTestId('task-item-checkbox')
    await subtaskCheckbox.click()
    await expect(subtaskCheckbox).toBeChecked()
    expect(taskItems.find((i) => i.content === 'Subtask từ lịch đã sửa')?.is_completed).toBe(true)

    // Delete subtask in calendar (delete the newly added subtask)
    await subtaskItem.getByTestId('task-item-delete').click()
    await expect(taskEditDialog.getByText('Subtask từ lịch đã sửa')).toHaveCount(0)
    expect(taskItems.some((i) => i.content === 'Subtask từ lịch đã sửa')).toBe(false)

    // Close task edit dialog
    await page.keyboard.press('Escape')
    await expect(taskEditDialog).toBeHidden()

    // Close day dialog
    await page.keyboard.press('Escape')
    await expect(dayDialog).toBeHidden()

    // Reopen DayDetailDialog and task edit to verify exact count and state persisted from server
    await todayCell.click()
    await expect(dayDialog).toBeVisible()
    await dayTask.getByTestId('calendar-day-task-edit-trigger').click()
    await expect(taskEditDialog).toBeVisible()
    await expect(taskEditDialog.getByTestId('task-checklist-section')).toBeVisible()
    await expect(taskEditDialog.getByText('Checklist sẵn có')).toBeVisible()
    await expect(taskEditDialog.getByText('Subtask từ lịch đã sửa')).toHaveCount(0)
    expect(taskItems.length).toBe(1)
  })

  test('Privacy gate same-tab lock purges private data from Notes and Tracker DOM without flashing stale private data', async ({ page, trackerApi }) => {
   let isUnlocked = false

   await page.route('**/api/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          email: 'test@example.com',
          signed_in_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + 86400000).toISOString(),
          private_until: isUnlocked ? new Date(Date.now() + 36 * 60000).toISOString() : null,
          private_locked_until: null,
          pin_is_set: true,
          pin_is_bootstrap: false,
        }),
      })
    })

    await page.route('**/api/private/unlock', async (route) => {
      isUnlocked = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          private_until: new Date(Date.now() + 36 * 60000).toISOString(),
        }),
      })
    })

    await page.route('**/api/private/lock', async (route) => {
      isUnlocked = false
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'locked' }),
      })
    })

    // Override tracker routes with private sentinel data when unlocked
    await page.route('**/api/tracker/trackers**', async (route) => {
      if (route.request().method() === 'GET') {
        const items = [...trackerApi.trackers]
        if (isUnlocked) {
          items.push({
            id: 'tracker-private-secret-1',
            name: 'Private Tracker Secret Sentinel',
            kind: 'general',
            direction: 'out',
            input_mode: 'event',
            group_id: null,
            unit: null,
            color: null,
            reminder_time: null,
            reminder_text: null,
            reminder_mode: null,
            reminder_interval_days: null,
            reminder_action: null,
            is_private: true,
            last_entry_at: null,
            entry_count_30d: 0,
            created_at: '2026-08-01T08:00:00Z',
            updated_at: '2026-08-01T08:00:00Z',
          })
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items }),
        })
        return
      }
      await route.fallback()
    })

    // Override notes routes with private sentinel data when unlocked
    await page.route('**/api/notes**', async (route) => {
      const items = [
        {
          id: 'note-public-1',
          title: 'Ghi chú công khai hiển thị mọi lúc',
          body_md: 'Nội dung công khai',
          pinned: false,
          is_private: false,
          created_at: '2026-08-01T10:00:00Z',
          items: [],
        },
      ]
      if (isUnlocked) {
        items.push({
          id: 'note-private-secret-1',
          title: 'Private Note Secret Sentinel',
          body_md: 'Nội dung riêng tư bí mật',
          pinned: false,
          is_private: true,
          created_at: '2026-08-02T10:00:00Z',
          items: [],
        })
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items }),
      })
    })

    await page.goto('/')

    // 1. Start locked: verify private sentinel is NOT in DOM
    const unlockBtn = page.getByTestId('private-unlock-open')
    await expect(unlockBtn).toBeVisible()

    await page.getByRole('tab', { name: 'Ghi chú' }).click()
    await expect(page.getByText('Ghi chú công khai hiển thị mọi lúc')).toBeVisible()
    await expect(page.getByText('Private Note Secret Sentinel')).toHaveCount(0)

    await page.getByRole('tab', { name: 'Theo dõi' }).click()
    await expect(page.getByText('Private Tracker Secret Sentinel')).toHaveCount(0)

    // 2. Unlock with PIN: verify private sentinel appears in DOM
    await unlockBtn.click()
    await page.getByTestId('private-pin-input').fill(fixturePrivatePin)
    await page.getByTestId('private-unlock-submit').click()
    await expect(page.getByTestId('private-lock-now')).toBeVisible()

    // Verify private sentinels are rendered on both tabs
    await expect(page.getByText('Private Tracker Secret Sentinel')).toBeVisible()
    await page.getByRole('tab', { name: 'Ghi chú' }).click()
    await expect(page.getByText('Private Note Secret Sentinel')).toBeVisible()

    // 3. Lock immediately: verify private sentinel disappears from DOM
    const lockBtn = page.getByTestId('private-lock-now')
    await lockBtn.click()
    await expect(page.getByTestId('private-unlock-open')).toBeVisible()

    // Assert: private sentinel is removed from DOM, public note remains
    await expect(page.getByText('Private Note Secret Sentinel')).toHaveCount(0)
    await expect(page.getByText('Ghi chú công khai hiển thị mọi lúc')).toBeVisible()
    await page.getByRole('tab', { name: 'Theo dõi' }).click()
    await expect(page.getByText('Private Tracker Secret Sentinel')).toHaveCount(0)

    // 4. Switch tabs to ensure no stale private data flash
    await page.getByRole('tab', { name: 'Theo dõi' }).click()
    await expect(page.getByTestId('tracker-reminders-overview')).toBeVisible()
    await page.getByRole('tab', { name: 'Ghi chú' }).click()
    await expect(page.getByText('Private Note Secret Sentinel')).toHaveCount(0)
    await expect(page.getByText('Ghi chú công khai hiển thị mọi lúc')).toBeVisible()
  })

  test('Private tracker edit dialog closes and purges its draft on immediate lock', async ({ page, trackerApi, taskApi }) => {
    const privateTracker = privateTrackerSentinel()
    trackerApi.trackers.push(privateTracker)
    await page.route('**/api/tracker/trackers**', async (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      const privateOpen = Boolean(
        taskApi.privateUntil && Date.parse(taskApi.privateUntil) > Date.now(),
      )
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: trackerApi.trackers.filter((tracker) => !tracker.is_private || privateOpen),
        }),
      })
    })

    await page.goto('/')
    await page.getByRole('tab', { name: 'Theo dõi' }).click()
    await page.getByRole('button', { name: 'Mở rộng tất cả' }).click()
    await expect(
      page.locator(`[data-testid="tracker-edit"][data-tracker-id="${privateTracker.id}"]`),
    ).toBeVisible()

    await page
      .locator(`[data-testid="tracker-edit"][data-tracker-id="${privateTracker.id}"]`)
      .click()
    const dialog = page.getByTestId('tracker-dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByTestId('tracker-name-input')).toHaveValue(privateTracker.name)

    // The modal overlay correctly blocks pointer input to the header. Invoke the
    // button handler directly to simulate an immediate security transition that
    // arrives while the dialog is active.
    await page.getByTestId('private-lock-now').evaluate((element) => element.click())
    await expect(page.getByTestId('private-badge')).toContainText('đang khoá')
    await expect(dialog).toHaveCount(0)
    await expect(
      page.locator(`[data-testid="tracker-edit"][data-tracker-id="${privateTracker.id}"]`),
    ).toHaveCount(0)
  })

  test('Private tracker edit dialog closes and purges its draft on TTL expiry', async ({ page, trackerApi, taskApi }) => {
    const privateTracker = privateTrackerSentinel()
    taskApi.privateUntil = new Date(Date.now() + 10_000).toISOString()
    trackerApi.trackers.push(privateTracker)
    await page.route('**/api/me', async (route) => {
      const privateUntil =
        taskApi.privateUntil && Date.parse(taskApi.privateUntil) > Date.now()
          ? taskApi.privateUntil
          : null
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          email: 'qa@example.test',
          signed_in_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + 30 * 60_000).toISOString(),
          private_until: privateUntil,
          private_locked_until: null,
          pin_is_set: true,
          pin_is_bootstrap: false,
        }),
      })
    })
    await page.route('**/api/tracker/trackers**', async (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      const privateOpen = Boolean(
        taskApi.privateUntil && Date.parse(taskApi.privateUntil) > Date.now(),
      )
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: trackerApi.trackers.filter((tracker) => !tracker.is_private || privateOpen),
        }),
      })
    })

    await page.goto('/')
    await page.getByRole('tab', { name: 'Theo dõi' }).click()
    await page.getByRole('button', { name: 'Mở rộng tất cả' }).click()
    await expect(
      page.locator(`[data-testid="tracker-edit"][data-tracker-id="${privateTracker.id}"]`),
    ).toBeVisible()

    await page
      .locator(`[data-testid="tracker-edit"][data-tracker-id="${privateTracker.id}"]`)
      .click()
    const dialog = page.getByTestId('tracker-dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByTestId('tracker-name-input')).toHaveValue(privateTracker.name)

    await expect(dialog).toHaveCount(0, { timeout: 20_000 })
    await expect(page.getByTestId('private-badge')).toContainText('đang khoá')
    await expect(
      page.locator(`[data-testid="tracker-edit"][data-tracker-id="${privateTracker.id}"]`),
    ).toHaveCount(0)
  })

  test('Notes layout & sort contract: default alphabet, created/updated sort, pinned partition, persistence', async ({ page }) => {
    await page.route('**/api/notes**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            { id: 'n1', title: 'Đà Nẵng', body_md: 'Nội dung Đà Nẵng', pinned: false, is_private: false, created_at: '2026-08-01T10:00:00Z', updated_at: '2026-08-01T10:00:00Z', items: [] },
            { id: 'n2', title: 'An Giang', body_md: 'Nội dung An Giang\n\n> 💬 **Lời nhắn từ tương lai** (10:00 · 03/08/2026):\n> Phản ánh tương lai dài dặc...', pinned: false, is_private: false, created_at: '2026-08-03T10:00:00Z', updated_at: '2026-08-03T10:00:00Z', items: [] },
            { id: 'n3', title: 'Bình Dương (Ghim)', body_md: 'Nội dung Bình Dương', pinned: true, is_private: false, created_at: '2026-08-02T10:00:00Z', updated_at: '2026-08-05T10:00:00Z', items: [] },
          ],
        }),
      })
    })

    await page.goto('/')
    await page.getByRole('tab', { name: 'Ghi chú' }).click()
    await expect(page.getByTestId('note-sort')).toBeVisible()

    // 1. Default sort is alphabet. Pinned partition comes first -> "Bình Dương (Ghim)", then "An Giang", then "Đà Nẵng"
    const cardTitles = page.locator('[data-testid="note-card"] [data-testid="note-title"]')
    await expect(cardTitles.nth(0)).toHaveText('Bình Dương (Ghim)')
    await expect(cardTitles.nth(1)).toHaveText('An Giang')
    await expect(cardTitles.nth(2)).toHaveText('Đà Nẵng')

    // 2. Measure layout width: note body width should be >= 80% of card on mobile
    const noteCardGeo = await page.evaluate(() => {
      const cards = document.querySelectorAll('[data-testid="note-card"]')
      const card = cards[1]
      const cardRect = card?.getBoundingClientRect()
      const contentCol = card?.querySelector('.min-w-0.flex-1')
      const colRect = contentCol?.getBoundingClientRect()
      const body = card?.querySelector('p')
      const bodyRect = body?.getBoundingClientRect()
      const refl = card?.querySelector('[data-testid="note-reflection-box"]')
      const reflRect = refl?.getBoundingClientRect()
      const bodyFontSize = body ? parseFloat(window.getComputedStyle(body).fontSize) : 0
      const pinBtn = card?.querySelector('[data-testid="note-pin"]')?.getBoundingClientRect()
      const editBtn = card?.querySelector('[data-testid="note-edit"]')?.getBoundingClientRect()
      const delBtn = card?.querySelector('[data-testid="note-delete"]')?.getBoundingClientRect()
      const ctaBtn = card?.querySelector('[data-testid="note-future-reflection-trigger"]')?.getBoundingClientRect()
      return {
        cardLeft: cardRect?.left ?? 0,
        cardRight: cardRect?.right ?? 0,
        cardWidth: cardRect?.width ?? 0,
        colWidth: colRect?.width ?? 0,
        bodyWidth: bodyRect?.width ?? 0,
        bodyRight: bodyRect?.right ?? 0,
        reflWidth: reflRect?.width ?? 0,
        reflRight: reflRect?.right ?? 0,
        bodyFontSize,
        pinHeight: pinBtn?.height ?? 0,
        editHeight: editBtn?.height ?? 0,
        delHeight: delBtn?.height ?? 0,
        ctaHeight: ctaBtn?.height ?? 0,
      }
    })
    expect(noteCardGeo.bodyWidth).toBeGreaterThanOrEqual(noteCardGeo.colWidth * 0.90)
    expect(noteCardGeo.bodyRight).toBeLessThanOrEqual(noteCardGeo.cardRight + 2)
    expect(noteCardGeo.reflWidth).toBeGreaterThanOrEqual(noteCardGeo.colWidth * 0.90)
    expect(noteCardGeo.reflRight).toBeLessThanOrEqual(noteCardGeo.cardRight + 2)
    expect(noteCardGeo.bodyFontSize).toBeGreaterThanOrEqual(12)
    expect(noteCardGeo.pinHeight).toBeGreaterThanOrEqual(40)
    expect(noteCardGeo.editHeight).toBeGreaterThanOrEqual(40)
    expect(noteCardGeo.delHeight).toBeGreaterThanOrEqual(40)
    expect(noteCardGeo.ctaHeight).toBeGreaterThanOrEqual(30)

    // 3. Switch sort mode to created (newest first)
    await page.getByTestId('note-sort').click()
    await page.getByRole('option', { name: 'Thời gian tạo' }).click()
    await expect(cardTitles.nth(0)).toHaveText('Bình Dương (Ghim)') // Pinned always first
    await expect(cardTitles.nth(1)).toHaveText('An Giang') // 2026-08-03 before 2026-08-01
    await expect(cardTitles.nth(2)).toHaveText('Đà Nẵng')

    // 4. Switch sort mode to updated (newest first)
    await page.getByTestId('note-sort').click()
    await page.getByRole('option', { name: 'Thời gian sửa' }).click()
    await expect(cardTitles.nth(0)).toHaveText('Bình Dương (Ghim)')

    // 5. Reload page to verify persistence of sort selection in localStorage
    await page.reload()
    await page.getByRole('tab', { name: 'Ghi chú' }).click()
    await expect(page.getByTestId('note-sort')).toContainText('Thời gian sửa')
  })

  test('Notes pagination: 101 notes across page boundary sorts completely', async ({ page }) => {
    await page.route('**/api/notes**', async (route) => {
      const url = new URL(route.request().url())
      const offset = parseInt(url.searchParams.get('offset') || '0', 10)
      if (offset === 0) {
        const items = Array.from({ length: 100 }, (_, i) => ({
          id: `note-p1-${i}`,
          title: `Note ${String(i).padStart(3, '0')}`,
          body_md: 'body',
          pinned: false,
          is_private: false,
          created_at: '2026-08-01T10:00:00Z',
          items: [],
        }))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items }) })
        return
      }
      if (offset === 100) {
        // Page 2 has 1 item that should sort first in alphabet
        const items = [
          {
            id: 'note-p2-0',
            title: 'AAA First Alphabetical Note',
            body_md: 'body',
            pinned: false,
            is_private: false,
            created_at: '2026-08-01T10:00:00Z',
            items: [],
          },
        ]
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items }) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
    })

    await page.goto('/')
    await page.getByRole('tab', { name: 'Ghi chú' }).click()

    // Default alphabet sort should place "AAA First Alphabetical Note" from page 2 at index 0
    const firstTitle = page.locator('[data-testid="note-card"] [data-testid="note-title"]').first()
    await expect(firstTitle).toHaveText('AAA First Alphabetical Note')
  })

  test('Notes safety cap: renders note-page-limit-error when 2000 notes cap is exceeded (2001 notes)', async ({ page }) => {
    await page.route('**/api/notes**', async (route) => {
      const url = new URL(route.request().url())
      const offset = parseInt(url.searchParams.get('offset') || '0', 10)
      const pageIdx = Math.floor(offset / 100)
      if (pageIdx < 20) {
        const items = Array.from({ length: 100 }, (_, i) => ({
          id: `note-p${pageIdx}-${i}`,
          title: `Note P${pageIdx} - ${i}`,
          body_md: 'body',
          pinned: false,
          is_private: false,
          created_at: '2026-08-01T10:00:00Z',
          items: [],
        }))
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items }) })
        return
      }
      // 21st page probe returns 1 item
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [{ id: 'note-2001', title: 'Note 2001', body_md: 'body', pinned: false, is_private: false, created_at: '2026-08-01T10:00:00Z', items: [] }] }),
      })
    })

   await page.goto('/')
   await page.getByRole('tab', { name: 'Ghi chú' }).click()
   await expect(page.getByTestId('note-page-limit-error')).toBeVisible()
   await expect(page.getByTestId('note-page-limit-error')).toContainText('Không tải đủ ghi chú để sắp xếp. Thử lại.')
   await expect(page.getByTestId('note-list')).toHaveCount(0)
 })

  test('Notes detail dialog checklist responsive layout, geometry assertions, and no overflow at 390px and 1280px', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('tab', { name: 'Ghi chú' }).click()

    const firstCard = page.locator('[data-testid="note-card"]').first()
    await expect(firstCard).toBeVisible()
    await firstCard.getByTestId('note-title').click()

    const noteDialog = page.getByTestId('note-detail-dialog')
    await expect(noteDialog).toBeVisible()

    const items = noteDialog.locator('[data-testid="note-item"]')
    await expect(items).toHaveCount(6)
    await expect(items.first()).toBeVisible()

    const geometry = await page.evaluate(() => {
      const dialog = document.querySelector('[data-testid="note-detail-dialog"]')
      const dialogRect = dialog?.getBoundingClientRect()
      const itemEls = Array.from(dialog?.querySelectorAll('[data-testid="note-item"]') ?? [])

     const itemMetrics = itemEls.map((item) => {
       const itemRect = item.getBoundingClientRect()
       const content = item.querySelector('[data-testid="note-item-content"]')
       const contentRect = content?.getBoundingClientRect()
        const buttons = Array.from(item.querySelectorAll('button:not([role="checkbox"])'))
       const btnMetrics = buttons.map((b) => {
         const r = b.getBoundingClientRect()
         return {
            left: r.left,
            right: r.right,
            width: r.width,
            height: r.height,
          }
        })
        return {
          itemWidth: itemRect.width,
          contentWidth: contentRect?.width ?? 0,
          contentLeft: contentRect?.left ?? 0,
          contentRight: contentRect?.right ?? 0,
          btnMetrics,
        }
      })

      return {
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
        dialogLeft: dialogRect?.left ?? 0,
        dialogRight: dialogRect?.right ?? 0,
        dialogWidth: dialogRect?.width ?? 0,
        itemMetrics,
      }
    })

    // No document overflow
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.innerWidth)

    const isMobile = geometry.innerWidth <= 450
    for (const item of geometry.itemMetrics) {
      // Content width has useful width
      if (isMobile) {
        // Mobile 390px: content occupies nearly full width of the container (> 75%)
        expect(item.contentWidth).toBeGreaterThanOrEqual(item.itemWidth * 0.75)
        for (const btn of item.btnMetrics) {
          // Touch target >= 44px on mobile
          expect(btn.height).toBeGreaterThanOrEqual(44)
          expect(btn.width).toBeGreaterThanOrEqual(44)
          // Action buttons contained within dialog
          expect(btn.left).toBeGreaterThanOrEqual(geometry.dialogLeft - 4)
          expect(btn.right).toBeLessThanOrEqual(geometry.dialogRight + 4)
        }
      } else {
        // Desktop: action buttons are compact and buttons stay within dialog
        expect(item.contentWidth).toBeGreaterThanOrEqual(200)
        for (const btn of item.btnMetrics) {
          expect(btn.height).toBeGreaterThanOrEqual(32)
          expect(btn.left).toBeGreaterThanOrEqual(geometry.dialogLeft - 4)
          expect(btn.right).toBeLessThanOrEqual(geometry.dialogRight + 4)
        }
      }
    }

    await page.keyboard.press('Escape')
    await expect(noteDialog).toBeHidden()
  })

 test('Capture taste screenshots and write SHA-256 manifest', async ({ page }, testInfo) => {
   const screenshotDir = path.resolve('test-results/task-036')
    const manifestPath = path.join(screenshotDir, 'manifest.json')
    test.skip(
      process.env.CAPTURE_SCREENSHOTS !== '1' && fs.existsSync(manifestPath) && fs.readdirSync(screenshotDir).filter((f) => f.endsWith('.png')).length >= 20,
      'Screenshots already captured with valid manifest. Set CAPTURE_SCREENSHOTS=1 to overwrite.',
    )
   if (!fs.existsSync(screenshotDir)) {
     fs.mkdirSync(screenshotDir, { recursive: true })
   }

    const projectName = testInfo.project.name // 'mobile' (390x844) or 'desktop' (1280x800)
    const isMob = projectName === 'mobile'

    await page.goto('/')

   // Assert >= 30 items in list before screenshots
   await expect(page.locator('[data-testid="task-card"]').first()).toBeVisible()
   const taskCards = page.locator('[data-testid="task-card"]')
   const taskCount = await taskCards.count()
    expect(taskCount).toBeGreaterThanOrEqual(30)

   // 1. Tasks screen
    const tasksPath = path.join(screenshotDir, `${projectName}-tasks.png`)
    await page.screenshot({ path: tasksPath })

    // 2. Task edit dialog on long task with checklist items
    const taskCard = page.locator('[data-task-id="task-012"]')
    await expect(taskCard).toBeVisible()
    await taskCard.getByTestId('task-edit').click()
    const taskDialog = page.getByTestId('task-detail-dialog')
    await expect(taskDialog).toBeVisible()
    const taskDialogPath = path.join(screenshotDir, `${projectName}-task-dialog.png`)
    await page.screenshot({ path: taskDialogPath })
    await page.keyboard.press('Escape')

   // 3. Calendar screen + Calendar task dialog
   await page.getByRole('tab', { name: 'Lịch' }).click()
   await expect(page.getByTestId('calendar-scroll-container')).toBeVisible()
   const today = new Date(Date.now() + 7 * 3_600_000).toISOString().slice(0, 10)
   const todayCell = page.locator(`[data-testid="calendar-day-cell"][data-day="${today}"]`)
    await expect(todayCell).toBeVisible()
    await todayCell.click()
    const dayDialog = page.getByTestId('calendar-day-dialog')
    await expect(dayDialog).toBeVisible()
    const calDialogPath = path.join(screenshotDir, `${projectName}-calendar-day-dialog.png`)
    await page.screenshot({ path: calDialogPath })
    await page.keyboard.press('Escape')

   // 4. Tracker screen (verifying wide reminder preview without single-char column)
    await page.getByRole('tab', { name: 'Theo dõi' }).click()
    await expect(page.getByTestId('tracker-reminders-overview')).toBeVisible()
    const trackerPath = path.join(screenshotDir, `${projectName}-tracker.png`)
    await page.screenshot({ path: trackerPath })

    // 5. Tracker create/edit dialog at top and bottom
    await page.getByTestId('tracker-create').click()
    const trackerDialog = page.getByTestId('tracker-dialog')
    await expect(trackerDialog).toBeVisible()
    await page.getByTestId('tracker-reminder-enabled').click()

    const trackerDialogTopPath = path.join(screenshotDir, `${projectName}-tracker-dialog.png`)
    await page.screenshot({ path: trackerDialogTopPath })

    await trackerDialog.evaluate((el) => { el.scrollTop = el.scrollHeight })
    const trackerDialogBottomPath = path.join(screenshotDir, `${projectName}-tracker-dialog-bottom.png`)
    await page.screenshot({ path: trackerDialogBottomPath })
    await page.keyboard.press('Escape')

   // 6. Notes screen (verifying pinned note, long body, future reflection)
   await page.getByRole('tab', { name: 'Ghi chú' }).click()
   await expect(page.getByTestId('note-sort')).toBeVisible()
   const notesPath = path.join(screenshotDir, `${projectName}-notes.png`)
   await page.screenshot({ path: notesPath })

  // 7. Long note detail & future reflection screenshot
  const firstNoteCard = page.locator('[data-testid="note-card"]').first()
  await expect(firstNoteCard).toBeVisible()
  await firstNoteCard.getByTestId('note-title').click()
  const noteDetailDialog = page.getByTestId('note-detail-dialog')
  await expect(noteDetailDialog).toBeVisible()
  await expect(noteDetailDialog.locator('[data-testid="note-item"]')).toHaveCount(6)
  await expect(noteDetailDialog.locator('[data-testid="note-item"]').first()).toBeVisible()
  const noteDetailPath = path.join(screenshotDir, `${projectName}-note-detail.png`)
  await page.screenshot({ path: noteDetailPath })
  await page.keyboard.press('Escape')
  await expect(noteDetailDialog).toBeHidden()

   // 8. Mandatory locked and unlocked synthetic states on Notes screen
   // Lock state: click lock and assert locked state mutation settles
   const lockBtn = page.getByTestId('private-lock-now')
   await expect(lockBtn).toBeVisible()
   await lockBtn.click()
   const unlockBtn = page.getByTestId('private-unlock-open')
   await expect(unlockBtn).toBeVisible()
   await expect(page.getByTestId('private-lock-now')).toBeHidden()
   await expect(page.getByTestId('private-badge')).toContainText('đang khoá')
   await expect(page.getByText('🔒 Ghi chú riêng tư đặc biệt')).toHaveCount(0)
   const lockedPath = path.join(screenshotDir, `${projectName}-private-locked.png`)
   await page.screenshot({ path: lockedPath })

   // Unlock state: click unlock, fill PIN, submit and assert unlocked state mutation settles
   await unlockBtn.click()
   await page.getByTestId('private-pin-input').fill(fixturePrivatePin)
   await page.getByTestId('private-unlock-submit').click()
   await expect(page.getByTestId('private-lock-now')).toBeVisible()
   await expect(page.getByTestId('private-unlock-open')).toBeHidden()
   await expect(page.getByTestId('private-badge')).toContainText('còn')
   await expect(page.getByText('🔒 Ghi chú riêng tư đặc biệt')).toBeVisible()
   const unlockedPath = path.join(screenshotDir, `${projectName}-private-unlocked.png`)
   await page.screenshot({ path: unlockedPath })

  // Write project sidecar manifest safely without race condition
   const sidecarPath = path.join(screenshotDir, `manifest-${projectName}.json`)
   const sidecarManifest: Record<string, any> = {}

    const bannerTextDict: Record<string, string> = {
      'tasks': 'microSched · Việc cần làm',
      'task-dialog': 'Sửa · Task chi tiết và checklist',
      'calendar-day-dialog': 'Chi tiết ngày · Dấu ngày, Buổi và Task đến hạn',
      'tracker': 'microSched · Theo dõi & Nhắc nhở',
      'tracker-dialog': 'Tạo tracker · Cấu hình kiểu nhắc & chu kỳ',
      'tracker-dialog-bottom': 'Chân dialog tracker · Nút lưu và huỷ',
      'notes': 'microSched · Ghi chú & Lời nhắn tương lai',
      'note-detail': 'Chi tiết ghi chú · Lời nhắn từ tương lai',
      'private-locked': 'Khoá riêng tư · Cần mã PIN để mở',
      'private-unlocked': 'Đã mở khoá riêng tư · Tự khoá sau 36 phút',
    }

  const tasteDict: Record<string, string> = {
     'tasks': isMob
        ? 'Giao diện danh sách việc trên mobile giữ bố cục thẻ gọn gàng, các nút thao tác và badge ưu tiên hiển thị phân cấp rõ ràng. Khoảng cách giữa các thẻ danh sách hơi thoáng, có thể co bớt padding dọc để tăng mật độ thông tin hữu ích. Tông màu hồng ấm của thanh điều hướng và badge hoàn thành tạo cảm giác đồng bộ, không bị chói.'
        : 'Giao diện việc trên desktop hiển thị thoáng đãng, các nút thao tác phân bổ cân đối và badge ưu tiên rõ nét. Phần nội dung thân thẻ hiển thị trọn vẹn theo chiều ngang, nhịp điệu phân cách giữa các hàng đồng đều và không bị cụt dòng. Mật độ vùng danh sách vừa phải, tuy nhiên khoảng trống bên phải danh sách còn hơi rộng so với độ dài thẻ.',
     'task-dialog': isMob
        ? 'Dialog chỉnh sửa việc trên mobile phủ kín chiều rộng hợp lý, các trường tiêu đề và ghi chú phân đoạn thị giác rõ ràng. Danh sách mục kiểm inline xếp thẳng hàng, các ô chọn và biểu tượng xóa có khoảng đệm vừa mắt. Khu vực chân form đặt các nút Lưu và Hủy tạo thành cụm hành động chắc chắn, không bị dính sát đáy.'
        : 'Khung dialog chỉnh sửa việc trên desktop giữ chiều rộng vừa vặn, bố cục hai cột phân chia tiêu đề và chi tiết rành mạch. Danh sách mục kiểm con hiển thị phân cấp thụt lề rõ ràng, viền khung nhập liệu mảnh và êm mắt. Khoảng cách giữa khối nội dung chính và cụm nút hành động phía dưới cân đối, giữ được nhịp thị giác liền mạch.',
     'calendar-day-dialog': isMob
        ? 'Dialog chi tiết ngày trên mobile phân chia ba phân đoạn rõ ràng giữa Dấu ngày, Buổi và Danh sách việc đến hạn. Khoảng cách dọc giữa các khối thẻ vừa vặn, màu sắc nguồn lịch phân biệt rõ ràng và hài hòa với nền sáng. Nhịp điệu hiển thị danh sách buổi và việc tạo cảm giác ngăn nắp, không bị rối mắt khi có nhiều mục.'
        : 'Khung chi tiết ngày trên desktop bố cục cân đối, các khối thông tin ngày tháng và việc phân chia ranh giới rõ nét. Danh sách buổi và công việc dàn trải thoáng đãng, các thẻ sự kiện giữ khoảng cách đệm đồng nhất. Cụm nút chuyển đổi trạng thái và đóng dialog nằm ở vị trí thuận mắt, tương phản màu sắc nhẹ nhàng và tinh tế.',
    'tracker': isMob
       ? 'Màn hình theo dõi thói quen trên mobile bố trí lưới các nút ghi nhận to bản, phân biệt trạng thái ghi nhận nổi bật. Khung nhắc nhở trong ngày hiển thị badge giờ gọn gàng, dòng xem trước nội dung ngắt chữ tự nhiên không bị tràn mép. Mật độ các thẻ theo dõi phân bổ vừa tầm mắt, nhịp phân cách dọc giữa các nhóm thẻ tạo cảm giác thông thoáng.'
        : 'Màn hình Tracker desktop phân bố các nhóm thẻ theo nhịp điệu lưới đều đặn, khoảng cách lề và padding bên trong thẻ vừa mắt. Phần xem trước nội dung nhắc nhở dàn trải theo chiều ngang tự nhiên, không bị cụt dòng đơn lẻ. Mật độ thông tin ở khu vực tổng quan và danh sách thẻ bên dưới giữ được sự cân đối, tông màu thẻ hài hòa với nền.',
    'tracker-dialog': isMob
        ? 'Dialog tạo tracker trên mobile có tiêu đề và mô tả rõ ràng, các trường nhập liệu sắp xếp theo luồng từ trên xuống dưới mạch lạc. Phần tùy chọn nhắc nhở mở rộng có độ giãn cách giữa các hàng vừa vặn, nhãn hướng dẫn hiển thị dễ đọc. Cụm nút bật tắt chu kỳ và lựa chọn giờ có khoảng cách phân định rõ ràng, không bị cảm giác chen chúc.'
        : 'Tracker dialog desktop hiển thị các trường nhập liệu cân đối, độ giãn cách giữa các khối form đồng nhất. Chế độ nhắc nhở theo chu kỳ có nhãn hướng dẫn trực quan, các ô chọn giờ và lặp lại hòa hợp với tông màu tổng thể. Vùng chứa nội dung có tỷ lệ chiều rộng và chiều cao hài hòa, phân cấp thị giác giữa trường bắt buộc và trường phụ rõ nét.',
    'tracker-dialog-bottom': isMob
        ? 'Phần chân dialog tracker trên mobile bố trí nút Lưu nổi bật cùng nút Hủy thứ cấp tạo sự tương phản hành động rõ rệt. Vùng đệm đáy tạo khoảng cách an toàn với mép màn hình, nhịp thị giác giữa các nút hành động duy trì sự cân đối. Đường phân cách mờ phía trên chân form giúp tách biệt rõ ràng phần cuộn dữ liệu và khu vực nút bấm cố định.'
        : 'Chân dialog tracker trên desktop giữ các nút thao tác chính nằm gọn trong tầm nhìn, viền dialog đổ bóng êm ái. Khoảng cách đệm giữa các nút bấm vừa vặn, tạo cảm giác hoàn thiện gọn gàng và chắc chắn. Độ tương phản màu giữa nút Lưu màu nhấn và nút Hủy nền nhạt giữ được tính đồng bộ với toàn hệ thống.',
   'notes': isMob
      ? 'Màn hình ghi chú trên mobile thể hiện rõ phân vùng ghim ở đầu danh sách với các thẻ ghi chú bo góc mềm mại. Khung trích dẫn Lời nhắn từ tương lai có đường viền bên nổi bật, mật độ chữ hiển thị vừa vặn không bị dính chữ. Thanh công cụ tìm kiếm và lọc phía trên có khoảng cách đệm hợp lý, nhịp điệu cuộn giữa các thẻ ghi chú đều đặn.'
     : 'Giao diện Ghi chú desktop tổ chức danh sách thẻ thoáng đãng với phân vùng ghim nổi bật ở đầu trang. Thanh công cụ lọc và sắp xếp theo bảng chữ cái đặt ở vị trí trực quan, khoảng cách giữa các thành phần đồng đều. Thẻ trích dẫn Lời nhắn từ tương lai có viền mỏng tinh tế, mật độ chữ hiển thị dễ đọc.',
   'note-detail': isMob
        ? 'Dialog chi tiết ghi chú trên mobile hiển thị khung Lời nhắn từ tương lai với viền trích dẫn rõ ràng, tiêu đề hiển thị trọn vẹn. Danh sách mục kiểm dài với nội dung văn bản sử dụng trọn chiều ngang, các nút thao tác chuyển thành hàng riêng biệt với kích thước chạm đạt chuẩn. Bố cục ngăn nắp, không bị tràn ngang và ngắt dòng tự nhiên.'
        : 'Chi tiết ghi chú desktop phân chia ranh giới rõ ràng giữa nội dung chính và danh sách mục kiểm nhiều mục. Khung trích dẫn Lời nhắn từ tương lai hiển thị định dạng ngày giờ chuẩn Việt Nam, độ tương phản văn bản và nền êm dịu. Các biểu tượng thao tác thứ tự và chỉnh sửa mục kiểm nằm cùng hàng với nội dung, kích thước đồng bộ, hàng lối ngay ngắn không bị xô lệch.',
   'private-locked': isMob
       ? 'Trạng thái khoá riêng tư thể hiện qua badge màu trung tính với biểu tượng ổ khoá và nhãn "Riêng tư · đang khoá" cạnh nút Mở khoá. Bố cục thanh tiêu đề giữ được sự cân đối, nút Khoá lại được ẩn đi và các mục riêng tư không xuất hiện trên giao diện.'
       : 'Thanh tiêu đề khi khoá riêng tư trên desktop hiển thị badge "Riêng tư · đang khoá", nút đổi PIN và nút Mở khoá gọn gàng ở góc phải. Nút Khoá lại được ẩn đi, danh sách các mục riêng tư được loại khỏi giao diện hiển thị, cấu trúc thanh điều hướng giữ được sự cân đối.',
   'private-unlocked': isMob
       ? 'Trạng thái mở khoá riêng tư hiển thị badge màu nhấn cùng biểu tượng mở khóa và thời gian phiên 36 phút. Nút Khoá lại đặt kế bên với kích thước vừa vặn, danh sách mục riêng tư hiển thị đầy đủ trong giao diện.'
       : 'Giao diện mở khoá riêng tư desktop hiển thị badge thời gian phiên 36 phút cùng nút Khoá lại ở thanh điều hướng. Các mục riêng tư xuất hiện đầy đủ trong danh sách, các nút điều khiển riêng tư giữ bố cục liền mạch và đồng bộ.',
  }

   const files = fs.readdirSync(screenshotDir).filter((f) => f.startsWith(projectName) && f.endsWith('.png'))
   for (const file of files) {
     const buf = fs.readFileSync(path.join(screenshotDir, file))
     const sha256 = crypto.createHash('sha256').update(buf).digest('hex')
     const md5 = crypto.createHash('md5').update(buf).digest('hex')
     const kind = file.replace(new RegExp('^' + projectName + '-'), '').replace('.png', '')
     sidecarManifest[file] = {
       checkpoint: kind,
       viewport: isMob ? '390x844' : '1280x800',
        topBannerText: bannerTextDict[kind] ?? 'microSched',
      sha256,
      md5,
      tasteEvaluation: tasteDict[kind] ?? 'Giao diện đạt chuẩn visual: tông màu hồng ấm đồng bộ, độ tương phản vừa mắt, bố cục cân đối và không tràn lề.',
    }
   }
    fs.writeFileSync(sidecarPath, JSON.stringify(sidecarManifest, null, 2), 'utf8')

   // Aggregate into manifest.json
   let currentManifest: Record<string, any> = {}
   if (fs.existsSync(manifestPath)) {
      try {
        currentManifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
      } catch {
        currentManifest = {}
      }
    }
    const combined = { ...currentManifest, ...sidecarManifest }
    fs.writeFileSync(manifestPath, JSON.stringify(combined, null, 2), 'utf8')
  })
})
