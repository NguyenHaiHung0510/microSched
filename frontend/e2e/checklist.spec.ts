import { expect, test } from './fixtures/tasks'

test('task checklist can be added and deleted through stable test hooks', async ({ page, taskApi }) => {
  const task = page.locator('[data-testid="task-card"][data-task-id="task-012"]')
  await page.goto('/')
  await expect(task).toBeVisible()
  await task.getByTestId('task-title').click()

  const dialog = page.getByTestId('task-detail-dialog')
  await expect(dialog).toBeVisible()

  const content = 'Checklist regression hook'
  await dialog.getByTestId('task-item-add-input').fill(content)
  await dialog.getByTestId('task-item-add-submit').click()

  await expect.poll(() => taskApi.count('POST', '/api/tasks/task-012/items')).toBe(1)
  const created = taskApi.tasks.find((entry) => entry.id === 'task-012')?.items.find(
    (item) => item.content === content,
  )
  expect(created).toBeDefined()
  if (!created) throw new Error('fixture item was not created')
  await expect(dialog.getByText(content)).toBeVisible()

  const createdRow = dialog.getByText(content, { exact: true }).locator('..')
  await expect(createdRow.getByTestId('task-item-delete')).toHaveCount(1)
  await createdRow.getByTestId('task-item-delete').click()
  await expect.poll(() => taskApi.count('DELETE', `/api/tasks/task-012/items/${created.id}`)).toBe(1)
  expect(taskApi.tasks.find((entry) => entry.id === 'task-012')?.items).not.toContainEqual(created)
  await expect(dialog.getByText(content)).toHaveCount(0)
})
