import {
  expect,
  fixturePrivatePin,
  fixtureWrongPin,
  test,
} from './fixtures/tasks'

test('correct PIN opens private tasks and changes the badge', async ({ page, taskApi }) => {
  taskApi.privateUntil = null
  await page.goto('/')

  await expect(page.getByTestId('private-badge')).toContainText('đang khoá')
  await expect(page.getByText('Task riêng tư')).toHaveCount(0)

  await page.getByTestId('private-unlock-open').click()
  await page.getByTestId('private-pin-input').fill(fixturePrivatePin)
  await page.getByTestId('private-unlock-submit').click()

  await expect(page.getByTestId('private-badge')).toContainText('còn')
  await expect(page.getByText('Task riêng tư')).toBeVisible()
})

test('ten wrong PIN attempts produce throttle countdown and disable unlock', async ({
  page,
  taskApi,
}) => {
  taskApi.privateUntil = null
  await page.goto('/')
  await page.getByTestId('private-unlock-open').click()

  for (let attempt = 1; attempt <= 10; attempt += 1) {
    await page.getByTestId('private-pin-input').fill(fixtureWrongPin)
    await page.getByTestId('private-unlock-submit').click()
    if (attempt < 10) {
      await expect(page.getByTestId('private-error')).toContainText(
        `Còn ${10 - attempt} lần`,
      )
    }
  }

  await expect(page.getByTestId('private-badge')).toContainText(/Khoá tạm · còn [45]:[0-5][0-9]/)
  await expect(page.getByTestId('private-unlock-submit')).toBeDisabled()
})

test('lock now removes private task responses before the locked refetch', async ({
  page,
}) => {
  await page.goto('/')
  await expect(page.getByText('Task riêng tư')).toBeVisible()

  await page.getByTestId('private-lock-now').click()

  await expect(page.getByTestId('private-badge')).toContainText('đang khoá')
  await expect(page.getByText('Task riêng tư')).toHaveCount(0)
})
