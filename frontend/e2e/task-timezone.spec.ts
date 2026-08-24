import type { Page } from '@playwright/test'

import { expect, test, type TaskApiState } from './fixtures/tasks'

function todayInVietnam(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]))
  return `${values.year}-${values.month}-${values.day}`
}

async function assertVietnamSchedule(page: Page, taskApi: TaskApiState) {
  const day = todayInVietnam()
  const timed = taskApi.tasks.find((entry) => entry.id === 'task-011')!
  Object.assign(timed, {
    due_precision: 'datetime' as const,
    due_on: null,
    due_at: new Date(`${day}T09:30:00+07:00`).toISOString(),
  })
  const civil = taskApi.tasks.find((entry) => entry.id === 'task-013')!
  Object.assign(civil, {
    due_precision: 'date' as const,
    due_on: day,
    due_at: null,
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Task' }).click()
  const timedCard = page.locator('[data-task-id="task-011"]')
  const civilCard = page.locator('[data-task-id="task-013"]')
  await expect(timedCard).toBeVisible()
  await expect(civilCard).toBeVisible()
  await expect(timedCard).toContainText('09:30')
  await expect(civilCard).not.toContainText('00:00')
  await expect(civilCard).not.toContainText('23:59')
}

test.describe('browser timezone UTC', () => {
  test.use({ timezoneId: 'UTC' })
  test('renders the Vietnam task schedule without shifting date-only values', async ({
    page,
    taskApi,
  }) => {
    await assertVietnamSchedule(page, taskApi)
  })
})

test.describe('browser timezone America/Los_Angeles', () => {
  test.use({ timezoneId: 'America/Los_Angeles' })
  test('renders the Vietnam task schedule without shifting date-only values', async ({
    page,
    taskApi,
  }) => {
    await assertVietnamSchedule(page, taskApi)
  })
})
