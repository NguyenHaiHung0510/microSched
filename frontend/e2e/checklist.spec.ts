import { expect, test } from './fixtures/tasks'

test('task checklist can be added and deleted through stable test hooks', async ({ page, taskApi }) => {
  const task = page.locator('[data-testid="task-card"][data-task-id="2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f4112"]')
  await page.goto('/')
  await expect(task).toBeVisible()
  await task.getByTestId('task-title').click()

  const dialog = page.getByTestId('task-detail-dialog')
  await expect(dialog).toBeVisible()

  const content = 'Checklist regression hook'
  await dialog.getByTestId('task-item-add-input').fill(content)
  await dialog.getByTestId('task-item-add-submit').click()

  await expect.poll(() => taskApi.count('POST', '/api/tasks/2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f4112/items')).toBe(1)
  const created = taskApi.tasks.find((entry) => entry.id === '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f4112')?.items.find(
    (item) => item.content === content,
  )
  expect(created).toBeDefined()
  if (!created) throw new Error('fixture item was not created')
  await expect(dialog.getByText(content)).toBeVisible()

  const createdRow = dialog.getByText(content, { exact: true }).locator('..')
  await expect(createdRow.getByTestId('task-item-delete')).toHaveCount(1)
  await createdRow.getByTestId('task-item-delete').click()
  await expect.poll(() => taskApi.count('DELETE', `/api/tasks/2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f4112/items/${created.id}`)).toBe(1)
  expect(taskApi.tasks.find((entry) => entry.id === '2c9d8a1e-4b73-4d5f-9a21-6e8b0c3f4112')?.items).not.toContainEqual(created)
  await expect(dialog.getByText(content)).toHaveCount(0)
})
