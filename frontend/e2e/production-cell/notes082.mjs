import { createHash } from 'node:crypto'

function check(condition, message) {
  if (!condition) throw new Error(message)
}

async function capture(page, name, viewport) {
  const image = await page.locator('[data-testid="note-detail-dialog"]').screenshot({ animations: 'disabled', timeout: 10_000 })
  return {
    name: `${name}.png`,
    viewport,
    sha256: createHash('sha256').update(image).digest('hex'),
    png_base64: image.toString('base64'),
  }
}

export async function runNotes082(page, payload) {
  const cases = {}
  const screenshots = []
  const noteTitle = payload.fixture_labels[4]
  const itemText = payload.fixture_labels[7]
  const card = page.locator('[data-testid="note-card"]', { has: page.locator('[data-testid="note-title"]', { hasText: noteTitle }) })
  await card.waitFor()

  // Text interaction must leave the card closed and the checklist unchanged.
  const itemContent = card.locator('[data-testid="note-item-content"]', { hasText: itemText })
  await itemContent.click()
  check((await page.locator('[data-testid="note-detail-dialog"]').count()) === 0, 'subnote text opened details')
  check((await card.locator('[data-testid="note-item-checkbox"]').getAttribute('data-state')) === 'unchecked', 'text click toggled checklist')
  cases.subnote_text_click = 'PASS'

  await card.locator('[data-testid="note-title"]').click()
  const dialog = page.locator('[data-testid="note-detail-dialog"]')
  await dialog.waitFor()
  const checkbox = dialog.locator('[data-testid="note-item-checkbox"]')
  const target = await dialog.locator('[data-testid="note-item-toggle"]').first().boundingBox()
  check(target && target.width >= 44 && target.height >= 44, 'checkbox hit area under44CSSpx')
  cases.subnote_hit_area_csspx = { width: target.width, height: target.height, status: 'PASS' }
  await checkbox.focus()
  await page.keyboard.press('Space')
  await page.waitForFunction((selector) => document.querySelector(selector)?.getAttribute('data-state') === 'checked', '[data-testid="note-detail-dialog"] [data-testid="note-item-checkbox"]')
  await page.waitForFunction(() => document.activeElement?.matches('[data-testid="note-items-completed-toggle"]'))
  check(await dialog.locator('[data-testid="note-items-completed-toggle"]').evaluate((node) => node === document.activeElement), 'completed disclosure did not receive focus')
  await page.keyboard.press('Space')
  await dialog.locator('[data-testid="note-item-checkbox"]').focus()
  await page.keyboard.press('Space')
  await page.waitForFunction((selector) => document.querySelector(selector)?.getAttribute('data-state') === 'unchecked', '[data-testid="note-detail-dialog"] [data-testid="note-item-checkbox"]')
  check(await checkbox.evaluate((node) => node === document.activeElement), 'checkbox focus was not preserved')
  cases.subnote_space_focus = 'PASS'

  const temporaryText = `${itemText}\n${itemText} · mục tạm`
  const addInput = dialog.locator('[data-testid="note-item-add-input"]')
  await addInput.fill(itemText)
  await addInput.press('End')
  await addInput.press('Enter')
  await addInput.pressSequentially(`${itemText} · mục tạm`)
  check(await addInput.inputValue() === temporaryText, 'Enter did not insert a newline')
  cases.subnote_enter_newline = 'PASS'
  let observedAddFailure = false
  const failAdd = async (route) => {
    const request = route.request()
    if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/items')) {
      observedAddFailure = true
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Lỗi QA tạm thời' }) })
      return
    }
    await route.continue()
  }
  await page.context().route('**/*', failAdd)
  const failedAdd = page.waitForResponse((response) => response.status() === 503 && response.request().method() === 'POST' && response.url().endsWith('/items'))
  await dialog.locator('[data-testid="note-item-add-submit"]').click()
  await failedAdd
  check(await addInput.isVisible(), 'failed add hid its input')
  check((await addInput.inputValue()).includes('\n'), 'failed add discarded multiline input')
  await dialog.getByText('Lỗi QA tạm thời', {exact:true}).waitFor()
  check(observedAddFailure, 'forced add failure was not observed')
  await page.context().unroute('**/*', failAdd)
  cases.subnote_add_failure_retains_multiline = 'PASS'
  await dialog.locator('[data-testid="note-item-add-submit"]').click()
  await dialog.locator('[data-testid="note-item-content"]', { hasText: '· mục tạm' }).waitFor()
  cases.subnote_multiline_add = 'PASS'
  const temporaryRow = dialog.locator('[data-testid="note-item"]', { hasText: '· mục tạm' })
  await temporaryRow.locator('[data-testid="note-item-delete"]').click()
  await dialog.locator('[data-testid="note-item-content"]', { hasText: '· mục tạm' }).waitFor({ state: 'detached' })
  cases.subnote_temporary_fixture_removed = 'PASS'

  // Edit the one ledger-backed item, verify retained multiline input on a 503,
  // then save and restore its original synthetic label.
  await dialog.locator('[data-testid="note-item-edit"]').click()
  const edit = dialog.locator('[data-testid="note-item-edit-input"]')
  await edit.fill(`${itemText}\nTiếng Việt và nội dung rất dài`.repeat(3))
  let observedFailureStatus = null
  const failRoute = async (route) => {
    const requestUrl = new URL(route.request().url())
    if (requestUrl.origin === new URL(page.url()).origin && requestUrl.pathname.includes('/items/')) {
      observedFailureStatus = 503
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Lỗi QA tạm thời' }) })
      return
    }
    await route.continue()
  }
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Network.enable')
  await cdp.send('Network.setBypassServiceWorker', { bypass: true })
  await page.context().route('**/*', failRoute)
  const failedPatch = page.waitForResponse((response) => response.status() === 503 && response.url().includes('/items/'))
  await dialog.locator('[data-testid="note-item-edit-save"]').click()
  await failedPatch
  check(await edit.isVisible(), 'failed edit discarded input')
  check((await edit.inputValue()).includes('\n'), 'failed edit lost multiline input')
  await dialog.getByText('Lỗi QA tạm thời', {exact:true}).waitFor()
  check(observedFailureStatus === 503, 'forced failure response was not observed')
  await page.context().unroute('**/*', failRoute)
  await cdp.send('Network.setBypassServiceWorker', { bypass: false })
  await cdp.detach()
  cases.subnote_edit_failure_retains_multiline = 'PASS'

  await dialog.locator('[data-testid="note-item-edit-save"]').click()
  await page.locator('[data-testid="note-item-content"]', { hasText: 'nội dung rất dài' }).waitFor()
  cases.subnote_edit_save = 'PASS'

  // Parent edit/cancel and save are separate from the acknowledged item write.
  await dialog.getByRole('button', { name: 'Sửa ghi chú' }).click()
  const parentBody = dialog.locator('textarea').first()
  const oldBody = await parentBody.inputValue()
  await parentBody.fill(`${oldBody}\nBản sửa cha hủy thử`)
  await dialog.getByRole('button', { name: 'Huỷ' }).click()
  await dialog.locator('[data-testid="note-item-content"]', { hasText: 'nội dung rất dài' }).waitFor()
  cases.parent_cancel_preserves_subnote = 'PASS'

  await dialog.getByRole('button', { name: 'Sửa ghi chú' }).click()
  await dialog.locator('textarea').first().fill(`${oldBody}\nBản sửa cha đã lưu`)
  await dialog.getByRole('button', { name: 'Lưu thay đổi' }).click()
  await dialog.getByText('Bản sửa cha đã lưu').waitFor()
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('tab', { name: 'Ghi chú' }).click()
  await page.locator('[data-testid="note-card"]', { has: page.locator('[data-testid="note-title"]', { hasText: noteTitle }) }).waitFor()
  await page.locator('[data-testid="note-title"]', { hasText: noteTitle }).click()
  await dialog.getByText('Bản sửa cha đã lưu').waitFor()
  await page.locator('[data-testid="note-item-content"]', { hasText: 'nội dung rất dài' }).waitFor()
  cases.parent_save_reload_subnote_independent = 'PASS'

  await page.setViewportSize({ width: 390, height: 844 })
  cases.mobile_viewport = await page.evaluate(() => ({ innerWidth, innerHeight, scrollWidth: document.documentElement.scrollWidth }))
  check(cases.mobile_viewport.innerWidth === 390 && cases.mobile_viewport.innerHeight === 844, 'mobile viewport did not apply')
  check(cases.mobile_viewport.scrollWidth <= cases.mobile_viewport.innerWidth, 'mobile viewport has horizontal overflow')
  screenshots.push(await capture(page, 'notes-detail-mobile', { width: 390, height: 844 }))
  await page.setViewportSize({ width: 1280, height: 695 })
  cases.desktop_viewport = await page.evaluate(() => ({ innerWidth, innerHeight, scrollWidth: document.documentElement.scrollWidth }))
  check(cases.desktop_viewport.innerWidth === 1280 && cases.desktop_viewport.innerHeight === 695, 'desktop viewport did not apply')
  check(cases.desktop_viewport.scrollWidth <= cases.desktop_viewport.innerWidth, 'desktop viewport has horizontal overflow')
  screenshots.push(await capture(page, 'notes-detail-desktop', { width: 1280, height: 695 }))

  // Restore the parent body and ledger item so the remaining QA025 smoke sees
  // its original synthetic fixture values.
  await dialog.getByRole('button', { name: 'Sửa ghi chú' }).click()
  await dialog.locator('textarea').first().fill(oldBody)
  await dialog.getByRole('button', { name: 'Lưu thay đổi' }).click()
  await dialog.getByText(oldBody).waitFor()
  await dialog.locator('[data-testid="note-item-content"]', { hasText: 'nội dung rất dài' }).waitFor()
  const editedRow = dialog.locator('[data-testid="note-item"]', { hasText: 'nội dung rất dài' })
  await editedRow.locator('[data-testid="note-item-edit"]').click()
  await dialog.locator('[data-testid="note-item-edit-input"]').fill(itemText)
  await dialog.locator('[data-testid="note-item-edit-save"]').click()
  await dialog.locator('[data-testid="note-item-content"]', { hasText: itemText }).waitFor()
  check((await page.locator('[data-testid="note-title"]', { hasText: noteTitle }).count()) === 1, 'note fixture count changed')
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null)
  return {
    status: 'PARTIAL',
    cases: {
      ...cases,
      subnote_add: 'PASS',
      tracker_rename_reminder_push: 'NOT_RUN_NO_TRACKER_FIXTURE',
      finance_rhythm_golden: 'NOT_RUN_NO_TRACKER_FIXTURE',
      screenshots_saved: 'PNG_BASE64_IN_BROWSER_JSON',
    },
    screenshots,
  }
}
