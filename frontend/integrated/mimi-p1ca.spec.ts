import { expect, test } from '@playwright/test'

type QaState = {
  database: string
  synthetic_tasks: number
  change_sets: number
  receipts: number
  provider_calls: number
  transport_calls: number
  slow_waiting: boolean
}

async function state(page: import('@playwright/test').Page): Promise<QaState> {
  const response = await page.request.get('/__qa/mimi-state')
  expect(response.ok()).toBe(true)
  const result = (await response.json()) as QaState
  expect(result.database).toBe('microsched_p1ca_accept')
  return result
}

test('P1C-A real browser → authenticated API/SSE → fake provider → PostgreSQL seam', async ({
  page,
}) => {
  const before = await state(page)
  const login = await page.goto('/auth/dev-session')
  expect(login?.ok()).toBe(true)
  await page.getByRole('tab', { name: 'Mimi' }).click()
  await page.getByRole('button', { name: 'Hội thoại' }).click()
  const createdConversation = page.waitForResponse((response) =>
    response.request().method() === 'POST' &&
    new URL(response.url()).pathname === '/api/mimi/conversations' &&
    response.status() === 201,
  )
  await page.getByRole('button', { name: 'Cuộc trò chuyện mới' }).click()
  const conversationId = ((await (await createdConversation).json()) as { id: string }).id
  expect(conversationId).toMatch(/^[0-9a-f-]{36}$/)
  await page.waitForLoadState('networkidle')

  const composer = page.getByTestId('mimi-input')
  await expect(page.getByText('Đang mở Mimi…')).toHaveCount(0)
  await expect(page.getByText('Hãy nhắn Mimi điều bạn muốn hỏi hoặc làm.')).toBeVisible()
  await expect(composer).toBeVisible()
  await composer.fill('QA_P1CA_READONLY ping')
  await expect(composer).toHaveValue('QA_P1CA_READONLY ping')
  const box = await composer.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.y + box!.height).toBeLessThanOrEqual(page.viewportSize()!.height)
  await composer.fill('Dòng đầu')
  await composer.press('Shift+Enter')
  await expect(composer).toHaveValue('Dòng đầu\n')
  await composer.fill('Dòng đầu')
  await composer.press('Alt+Enter')
  await expect(composer).toHaveValue('Dòng đầu\n')
  await composer.fill('QA_P1CA_READONLY ping')
  await composer.press('Enter')
  await expect(page.getByTestId('mimi-messages')).toContainText(
    'Mimi có thể trả lời câu hỏi này mà không tạo Task.',
  )
  const afterRead = await state(page)
  expect(afterRead.synthetic_tasks).toBe(before.synthetic_tasks)
  expect(afterRead.change_sets).toBe(before.change_sets)
  expect(afterRead.receipts).toBe(before.receipts)
  expect(afterRead.transport_calls).toBe(before.transport_calls + 1)

  await composer.fill('QA_P1CA_CLARIFY lịch tuần tới')
  await composer.press('Enter')
  await expect(page.getByTestId('mimi-messages')).toContainText(
    'Bạn muốn chọn ngày nào cho lịch này?',
  )
  const afterClarify = await state(page)
  expect(afterClarify.synthetic_tasks).toBe(before.synthetic_tasks)
  expect(afterClarify.change_sets).toBe(before.change_sets)

  await composer.fill('QA_P1CA_DRAFT phương án sắp xếp')
  await composer.press('Enter')
  await expect(page.getByTestId('mimi-messages')).toContainText('Mình đề xuất rà soát lịch trước')
  await page.getByRole('button', { name: 'Duyệt hướng' }).click()
  await expect(page.getByText('Đã duyệt hướng nháp.')).toBeVisible()
  const beforeCreate = await state(page)
  expect(beforeCreate.synthetic_tasks).toBe(before.synthetic_tasks)
  expect(beforeCreate.change_sets).toBe(before.change_sets)

  const title = `QA_P1CA synthetic Task ${Date.now()}-${page.viewportSize()!.width}`
  await composer.fill(`QA_P1CA_CREATE ${title}`)
  await composer.press('Enter')
  const preview = page.getByTestId('mimi-change-set')
  await expect(preview).toContainText(title)
  const beforeConfirm = await state(page)
  expect(beforeConfirm.synthetic_tasks).toBe(before.synthetic_tasks)
  expect(beforeConfirm.change_sets).toBe(before.change_sets + 1)
  expect(beforeConfirm.receipts).toBe(before.receipts)
  const pendingSnapshot = await page.request.get(`/api/mimi/conversations/${conversationId}`)
  expect(pendingSnapshot.ok()).toBe(true)
  const pendingDigest = ((await pendingSnapshot.json()) as {
    change_sets: Array<{ digest: string }>
  }).change_sets.at(-1)!.digest
  const digestLabel = `${pendingDigest.slice(0, 16)}…`
  await expect(preview).toContainText(digestLabel)

  await page.getByTestId('mimi-dock-toggle').click()
  await expect(page.getByTestId('mimi-side-chat').getByTestId('mimi-change-set')).toContainText(
    title,
  )
  await expect(page.getByTestId('mimi-side-chat').getByTestId('mimi-change-set')).toContainText(
    digestLabel,
  )
  if (page.viewportSize()!.width < 640) await page.keyboard.press('Escape')
  else await page.getByTestId('mimi-dock-toggle').click()
  await expect(preview).toContainText(title)

  await page.getByRole('button', { name: 'Xác nhận tạo Task' }).click()
  await expect(page.getByTestId('mimi-receipt')).toBeVisible()
  const conversationSnapshot = await page.request.get(`/api/mimi/conversations/${conversationId}`)
  expect(conversationSnapshot.ok()).toBe(true)
  const taskId = (await conversationSnapshot.json()).receipts.at(-1).task_id as string
  const afterConfirm = await state(page)
  expect(afterConfirm.synthetic_tasks).toBe(before.synthetic_tasks + 1)
  expect(afterConfirm.change_sets).toBe(before.change_sets + 1)
  expect(afterConfirm.receipts).toBe(before.receipts + 1)
  expect(afterConfirm.transport_calls).toBe(beforeCreate.transport_calls + 1)

  await composer.fill('QA_P1CA_READ kiểm tra Task STANDARD')
  await composer.press('Enter')
  await expect(page.getByTestId('mimi-messages')).toContainText(
    'Mình đã đọc Task STANDARD được cấp trong lượt này.',
  )
  const afterToolRead = await state(page)
  expect(afterToolRead.synthetic_tasks).toBe(afterConfirm.synthetic_tasks)
  expect(afterToolRead.transport_calls).toBe(afterConfirm.transport_calls + 2)

  await composer.fill('QA_P1CA_SLOW giữ run khi đổi tab và reload')
  await composer.press('Enter')
  await expect.poll(async () => (await state(page)).slow_waiting).toBe(true)
  await page.getByTestId('mimi-dock-toggle').click()
  await expect(page.getByTestId('mimi-side-chat')).toBeVisible()
  if (page.viewportSize()!.width < 640) await page.keyboard.press('Escape')
  else await page.getByTestId('mimi-dock-toggle').click()
  await page.getByRole('tab', { name: 'Task' }).click()
  expect((await state(page)).slow_waiting).toBe(true)

  await page.reload()
  await page.getByRole('tab', { name: 'Mimi' }).click()
  await page.getByRole('button', { name: 'Hội thoại' }).click()
  expect((await state(page)).slow_waiting).toBe(true)
  const released = await page.request.post('/__qa/release-slow')
  expect(released.ok()).toBe(true)
  await expect(page.getByTestId('mimi-messages')).toContainText(
    'Run vẫn tiếp tục sau khi đóng hoặc tải lại giao diện.',
  )
  await expect(page.getByTestId('mimi-receipt')).toBeVisible()
  const afterSlow = await state(page)
  expect(afterSlow.transport_calls).toBe(afterToolRead.transport_calls + 1)

  const resumedComposer = page.getByTestId('mimi-input')
  await resumedComposer.fill('QA_P1CA_UNKNOWN kiểm tra outcome chưa xác định')
  await resumedComposer.press('Enter')
  await expect(page.getByRole('button', { name: 'Reconcile provider' })).toBeVisible()
  const afterUnknown = await state(page)
  expect(afterUnknown.synthetic_tasks).toBe(afterConfirm.synthetic_tasks)
  expect(afterUnknown.transport_calls).toBe(afterSlow.transport_calls + 1)
  await page.getByRole('button', { name: 'Reconcile provider' }).click()
  await expect.poll(async () => {
    const snapshot = await page.request.get(`/api/mimi/conversations/${conversationId}`)
    return (await snapshot.json()).runs.at(-1).error_code as string
  }).toBe('provider_result_unavailable_after_reconcile')
  expect((await state(page)).transport_calls).toBe(afterUnknown.transport_calls)

  await resumedComposer.fill('QA_P1CA_RETRYABLE thử Resume có chủ đích')
  await resumedComposer.press('Enter')
  await expect(page.getByRole('button', { name: 'Resume' })).toBeVisible()
  await page.getByRole('button', { name: 'Resume' }).click()
  await expect(page.getByTestId('mimi-messages')).toContainText(
    'Mimi đã tiếp tục sau lỗi chưa gửi generation.',
  )
  const afterResume = await state(page)
  expect(afterResume.synthetic_tasks).toBe(afterConfirm.synthetic_tasks)
  expect(afterResume.transport_calls).toBe(afterUnknown.transport_calls + 2)
  const checkpointSnapshot = await page.request.get(`/api/mimi/conversations/${conversationId}`)
  expect(checkpointSnapshot.ok()).toBe(true)
  const checkpointEvents = ((await checkpointSnapshot.json()) as {
    events: Array<{ kind: string }>
  }).events
  expect(checkpointEvents.some((event) => event.kind === 'context.checkpoint.activated')).toBe(true)
  await page.getByRole('button', { name: 'Xem dữ liệu liên quan' }).click()
  await page.getByTestId('mimi-context-rail').getByRole('tab', { name: 'Run' }).click()
  await page.getByTestId('mimi-context-inspector').locator('summary').click()
  await expect(page.getByTestId('mimi-context-inspector')).toContainText('Đến message')
  await expect(page.getByTestId('mimi-context-inspector')).toContainText('Nguồn được đưa vào model')
  await page.getByRole('button', { name: 'Đóng dữ liệu' }).click()

  await resumedComposer.fill('QA_P1CA_DEADLINE hết lease sau khi provider đã bắt đầu')
  await resumedComposer.press('Enter')
  await expect.poll(async () => (await state(page)).slow_waiting).toBe(true)
  await expect.poll(async () => {
    const snapshot = await page.request.get(`/api/mimi/conversations/${conversationId}`)
    return (await snapshot.json()).runs.at(-1).state as string
  }, { timeout: 40_000 }).toBe('deadline_exceeded')
  await expect.poll(async () => (await state(page)).slow_waiting).toBe(false)
  await expect(page.getByRole('button', { name: 'Reconcile provider' })).toBeVisible()
  const afterDeadline = await state(page)
  expect(afterDeadline.transport_calls).toBe(afterResume.transport_calls + 1)
  expect(afterDeadline.synthetic_tasks).toBe(afterConfirm.synthetic_tasks)

  await resumedComposer.fill('QA_P1CA_SLOW huỷ run dài có chủ đích')
  await resumedComposer.press('Enter')
  await expect.poll(async () => (await state(page)).slow_waiting).toBe(true)
  await page.getByRole('button', { name: 'Huỷ run' }).click()
  await expect.poll(async () => {
    const snapshot = await page.request.get(`/api/mimi/conversations/${conversationId}`)
    return (await snapshot.json()).runs.at(-1).state as string
  }).toBe('cancelled')
  await expect.poll(async () => (await state(page)).slow_waiting).toBe(false)
  const afterCancel = await state(page)
  expect(afterCancel.transport_calls).toBe(afterDeadline.transport_calls + 1)
  expect(afterCancel.synthetic_tasks).toBe(afterConfirm.synthetic_tasks)

  const cleanup = await page.request.post('/__qa/cleanup', {
    data: { conversation_id: conversationId, task_id: taskId },
  })
  expect(cleanup.ok()).toBe(true)
  expect((await state(page)).synthetic_tasks).toBe(before.synthetic_tasks)
  await page.request.post('/auth/logout')
})
