import { createHash } from 'node:crypto'

function check(ok, message) {
  if (!ok) throw new Error(message)
}

async function api(page, path, method = 'GET', body) {
  const result = await page.evaluate(async ({ path, method, body }) => {
    const response = await fetch(path, {
      method,
      headers: body ? { 'content-type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
    return { status: response.status, text: await response.text() }
  }, { path, method, body })
  let value = null
  if (result.text) {
    try { value = JSON.parse(result.text) } catch { value = result.text }
  }
  return { ...result, value }
}

function expect2xx(result, label) {
  check(result.status >= 200 && result.status < 300, `${label}: HTTP ${result.status}`)
  return result.value
}

function vnDate(iso) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(iso))
  const get = (type) => parts.find((part) => part.type === type)?.value
  return `${get('year')}-${get('month')}-${get('day')}`
}

function periodBounds(mode, anchor) {
  const [year, month, day] = anchor.split('-').map(Number)
  const start = new Date(Date.UTC(year, month - 1, mode === 'day' ? day : 1))
  if (mode === 'quarter') start.setUTCMonth(Math.floor((month - 1) / 3) * 3)
  if (mode === 'year') start.setUTCMonth(0)
  const end = new Date(start)
  if (mode === 'day') end.setUTCDate(end.getUTCDate() + 1)
  else end.setUTCMonth(end.getUTCMonth() + ({ month: 1, quarter: 3, year: 12 })[mode])
  const localMidnight = (date) => `${date.toISOString().slice(0, 10)}T00:00:00+07:00`
  return { from: localMidnight(start), to: localMidnight(end) }
}

async function shot(page, name, selector) {
  const png = await page.locator(selector).screenshot({ animations: 'disabled', timeout: 15_000 })
  return {
    name: `${name}.png`,
    viewport: await page.evaluate(() => ({ width: innerWidth, height: innerHeight })),
    sha256: createHash('sha256').update(png).digest('hex'),
    png_base64: png.toString('base64'),
  }
}

async function selectOption(page, testId, optionName) {
  await page.getByTestId(testId).click()
  await page.getByRole('option', { name: optionName, exact: true }).click()
}

async function rowIds(page) {
  return page.getByTestId('entry-row').evaluateAll((rows) => rows.map((row) => row.dataset.entryId))
}

async function waitForEntryIds(page, expectedIds) {
  await page.waitForFunction((ids) => {
    const actual = [...document.querySelectorAll('[data-testid="entry-row"]')].map((row) => row.dataset.entryId)
    return JSON.stringify(actual) === JSON.stringify(ids)
  }, expectedIds)
}

async function unlockThroughUI(page, pin) {
  if (await page.getByTestId('private-lock-now').isVisible()) return
  await page.getByTestId('private-unlock-open').click()
  await page.getByTestId('private-pin-input').fill(pin)
  await page.getByTestId('private-unlock-submit').click()
  await page.getByTestId('private-lock-now').waitFor()
}

async function currentVietnamDate(page) {
  return page.evaluate(() => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(new Date())
    const get = (type) => parts.find((part) => part.type === type)?.value
    return `${get('year')}-${get('month')}-${get('day')}`
  })
}

export async function runTracker083(page, payload) {
  page.setDefaultTimeout(15_000)
  page.setDefaultNavigationTimeout(20_000)
  console.log(JSON.stringify({ tracker083_progress: 'setup' }))
  const cases = Object.fromEntries(Array.from({ length: 10 }, (_, i) => [`A${String(i + 1).padStart(2, '0')}`, 'NOT_RUN']))
  const screenshots = []
  const ownedEntryIds = []
  const ownedTrackerIds = []
  const expectedById = new Map()
  const fixtureLabel = payload?.fixture_labels?.[8]
  let setupError = null

  function fail(caseId, error) {
    cases[caseId] = `FAIL: ${error instanceof Error ? error.message : String(error)}`
  }

  async function runCase(caseId, action) {
    console.log(JSON.stringify({ tracker083_progress: caseId, state: 'START' }))
    try {
      await action()
      cases[caseId] = 'PASS'
    } catch (error) {
      fail(caseId, error)
    }
    console.log(JSON.stringify({ tracker083_progress: caseId, state: cases[caseId] }))
  }

  try {
    check(typeof payload?.prefix === 'string' && payload.prefix.startsWith('[QA025:'), 'synthetic QA025 prefix required')
    check(typeof fixtureLabel === 'string' && fixtureLabel === `${payload.prefix} synthetic body`, 'use only the existing synthetic label 8')
    check(/^[0-9]{6}$/.test(payload.pin ?? ''), 'synthetic cell PIN required')

    await page.keyboard.press('Escape')
    await page.getByRole('tab', { name: 'Theo dõi', exact: true }).click()
    // These labels are derived only from the run prefix and the already approved synthetic label.
    const baseName = `${payload.prefix} ${fixtureLabel.slice(payload.prefix.length).trim()} T083`
    const trackerA = expect2xx(await api(page, '/api/tracker/trackers', 'POST', {
      name: `${baseName} A`, kind: 'health', input_mode: 'event', is_private: false,
    }), 'create public tracker A')
    ownedTrackerIds.push(trackerA.id)
    const trackerB = expect2xx(await api(page, '/api/tracker/trackers', 'POST', {
      name: `${baseName} B`, kind: 'health', input_mode: 'event', is_private: false,
    }), 'create public tracker B')
    ownedTrackerIds.push(trackerB.id)

    // Sixty entries inside leap day (+07), with an equal-timestamp tie group.
    // Add exact half-open boundary neighbors, leap/year cases, and the 0/1/2/3/5 buckets.
    const planned = []
    for (let i = 0; i < 60; i += 1) {
      planned.push({ tracker: i % 2 ? trackerB : trackerA, at: i < 5 ? '2024-02-29T05:00:00Z' : new Date(Date.UTC(2024, 1, 29, 0, i)).toISOString(), tag: `leap-page-${i}` })
    }
    planned.push(
      { tracker: trackerA, at: '2024-02-28T16:59:59Z', tag: 'day-before-start' },
      { tracker: trackerA, at: '2024-02-28T17:00:00Z', tag: 'month-start' },
      { tracker: trackerB, at: '2024-02-29T16:59:59Z', tag: 'leap-day-end-minus' },
      { tracker: trackerB, at: '2024-02-29T17:00:00Z', tag: 'day-after-end' },
      { tracker: trackerA, at: '2024-03-31T16:59:59Z', tag: 'quarter-boundary-minus' },
      { tracker: trackerB, at: '2024-03-31T17:00:00Z', tag: 'quarter-boundary-plus' },
      { tracker: trackerA, at: '2023-12-31T16:59:59Z', tag: 'year-boundary-minus' },
      { tracker: trackerB, at: '2023-12-31T17:00:00Z', tag: 'year-boundary-plus' },
      { tracker: trackerA, at: '2024-01-10T17:10:00Z', tag: 'count-one' },
      { tracker: trackerB, at: '2024-01-11T17:10:00Z', tag: 'count-two-1' },
      { tracker: trackerA, at: '2024-01-11T18:10:00Z', tag: 'count-two-2' },
      ...[0, 1, 2].map((i) => ({ tracker: i % 2 ? trackerB : trackerA, at: new Date(Date.UTC(2024, 0, 12, 17, i)).toISOString(), tag: `count-three-${i}` })),
      ...[0, 1, 2, 3, 4].map((i) => ({ tracker: i % 2 ? trackerB : trackerA, at: new Date(Date.UTC(2024, 0, 13, 17, i)).toISOString(), tag: `count-five-${i}` })),
    )
    for (const [index, item] of planned.entries()) {
      const note = `${payload.prefix} ${fixtureLabel.slice(payload.prefix.length).trim()} T083 ${item.tag}`
      const entry = expect2xx(await api(page, '/api/tracker/entries', 'POST', {
        tracker_id: item.tracker.id, occurred_at: item.at, note_md: note,
      }), `create synthetic entry ${index}`)
      ownedEntryIds.push(entry.id)
      expectedById.set(entry.id, { ...entry, tag: item.tag, tracker_id: item.tracker.id })
    }

    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.getByRole('tab', { name: 'Theo dõi', exact: true }).click()
    await page.getByTestId('tracker-open-report').click()
    await page.getByTestId('tracker-entries-toggle').click()
    await page.getByTestId('records-list').waitFor()

    await runCase('A01', async () => {
      const ordered = expect2xx(await api(page, '/api/tracker/entries?limit=20&offset=0&order=desc'), 'read recent source rows').items.map((entry) => entry.id)
      check(ordered.length === 20, 'recent API did not return exactly 20 rows')
      const fullSource = expect2xx(await api(page, '/api/tracker/entries?limit=500&offset=0&order=desc'), 'read bounded recent source rows')
      const allExpected = [...fullSource.items].sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at) || a.id.localeCompare(b.id)).slice(0, 20).map((entry) => entry.id)
      check(JSON.stringify(ordered) === JSON.stringify(allExpected), 'recent API is not timestamp-descending with ascending ID tie-break')
      check(JSON.stringify(await rowIds(page)) === JSON.stringify(ordered), 'recent 20 IDs/order differ from API timestamp+ID ordering')
      await selectOption(page, 'records-tracker', `${baseName} A`)
      const filtered = expect2xx(await api(page, `/api/tracker/entries?tracker_id=${trackerA.id}&limit=20&offset=0&order=desc`), 'read tracker-filter source rows').items.map((entry) => entry.id)
      await waitForEntryIds(page, filtered)
      check(JSON.stringify(await rowIds(page)) === JSON.stringify(filtered), 'recent selected-tracker rows/order mismatch')
      check((await rowIds(page)).every((id) => expectedById.get(id)?.tracker_id === trackerA.id), 'other tracker appeared in tracker filter')
    })

    await runCase('A02', async () => {
      await selectOption(page, 'records-tracker', `${baseName} A`)
      await selectOption(page, 'records-mode', 'Theo ngày')
      await page.getByTestId('records-date').fill('2024-02-29')
      await page.getByTestId('records-date').dispatchEvent('change')
      const aDay = expect2xx(await api(page, `/api/tracker/entries?tracker_id=${trackerA.id}&from=2024-02-29T00%3A00%3A00%2B07%3A00&to=2024-03-01T00%3A00%3A00%2B07%3A00&limit=100&offset=0&order=desc`), 'read day source rows').items
        .filter((entry) => expectedById.has(entry.id))
      const aIds = aDay.map((entry) => entry.id)
      check(aIds.length === 31, `expected 31 tracker A leapday rows, received ${aIds.length}`)
      await waitForEntryIds(page, aIds.slice(0, 50))
      await selectOption(page, 'records-tracker', `${baseName} B`)
      const inside = [...expectedById.entries()].filter(([, entry]) => entry.tracker_id === trackerB.id && vnDate(entry.occurred_at) === '2024-02-29').map(([id]) => id)
      check(inside.length === 31, 'fixture period count for tracker B changed')
      await selectOption(page, 'records-tracker', 'Tất cả tracker')
      const allDayOrdered = expect2xx(await api(page, `/api/tracker/entries?from=2024-02-29T00%3A00%3A00%2B07%3A00&to=2024-03-01T00%3A00%3A00%2B07%3A00&limit=500&offset=0&order=desc`), 'read full day source ordering').items.map((entry) => entry.id)
      await waitForEntryIds(page, allDayOrdered.slice(0, 50))
      const pageOne = await rowIds(page)
      check(pageOne.length === 50, 'page one should render exactly 50 rows while the API uses one-row lookahead')
      const visiblePageOne = pageOne
      check(new Set(visiblePageOne).size === 50, 'page one contains duplicate IDs')
      await page.getByTestId('records-next').click()
      await waitForEntryIds(page, allDayOrdered.slice(50))
      const settledPageTwo = await rowIds(page)
      check(settledPageTwo.length === 12, 'page two should contain the remaining 12 rows')
      check(new Set([...visiblePageOne, ...settledPageTwo]).size === 62, 'paging contains duplicate IDs')
      const expectedDay = [...expectedById.entries()].filter(([, entry]) => vnDate(entry.occurred_at) === '2024-02-29').map(([id]) => id)
      check([...visiblePageOne, ...settledPageTwo].length === expectedDay.length && expectedDay.length === 62, 'paging total differs from independently computed Vietnam day rows')

      const observed = []
      const listener = (request) => { if (request.url().includes('/api/tracker/entries?')) observed.push(new URL(request.url()).searchParams) }
      page.on('request', listener)
      for (const mode of ['Theo tháng', 'Theo quý', 'Theo năm']) {
        const internalMode = mode === 'Theo tháng' ? 'month' : mode === 'Theo quý' ? 'quarter' : 'year'
        const expectedBounds = periodBounds(internalMode, '2024-02-29')
        const boundsRequest = page.waitForRequest((request) => {
          if (!request.url().includes('/api/tracker/entries?')) return false
          const params = new URL(request.url()).searchParams
          return params.get('from') === expectedBounds.from && params.get('to') === expectedBounds.to
        })
        await selectOption(page, 'records-mode', mode)
        await boundsRequest
        const last = observed.at(-1)
        check(last?.get('from') === expectedBounds.from && last?.get('to') === expectedBounds.to, `${internalMode} bounds are not half-open Vietnam boundaries`)
      }
      page.off('request', listener)
    })

    await runCase('A03', async () => {
      await selectOption(page, 'records-mode', 'Theo ngày')
      await selectOption(page, 'records-tracker', `${baseName} A`)
      await page.getByTestId('records-date').fill('2024-02-29')
      await selectOption(page, 'records-order', 'Cũ nhất trước')
      const expected = expect2xx(await api(page, `/api/tracker/entries?tracker_id=${trackerA.id}&from=2024-02-29T00%3A00%3A00%2B07%3A00&to=2024-03-01T00%3A00%3A00%2B07%3A00&limit=100&offset=0&order=asc`), 'read oldest-first source rows').items
        .filter((entry) => expectedById.has(entry.id)).slice(0, 50).map((entry) => entry.id)
      await waitForEntryIds(page, expected)
      check(JSON.stringify(await rowIds(page)) === JSON.stringify(expected), 'oldest-first rows do not match API timestamp+ID order')
      await selectOption(page, 'records-tracker', 'Tất cả tracker')
      await page.getByTestId('records-next').click()
      await selectOption(page, 'records-tracker', `${baseName} B`)
      check((await page.getByTestId('records-prev').isDisabled()), 'filter change did not reset page to 1')
      check((await rowIds(page)).every((id) => expectedById.get(id)?.tracker_id === trackerB.id), 'previous tracker rows remained after filter switch')
    })

    await runCase('A04', async () => {
      await selectOption(page, 'records-mode', 'Theo ngày')
      await selectOption(page, 'records-tracker', `${baseName} A`)
      await page.getByTestId('records-date').fill('2024-02-29')
      const targetId = (await rowIds(page))[0]
      await page.locator(`[data-testid="entry-edit"][data-entry-id="${targetId}"]`).click()
      const dialog = page.getByTestId('entry-edit-dialog')
      const note = dialog.locator('textarea').first()
      const before = await note.inputValue()
      await note.fill(`${before} edited`)
      await dialog.getByRole('button', { name: 'Huỷ', exact: true }).click()
      check(!(await page.getByTestId('entry-edit-dialog').count()), 'cancel left edit dialog open')
      await page.locator(`[data-testid="entry-edit"][data-entry-id="${targetId}"]`).click()
      const editDialog = page.getByTestId('entry-edit-dialog')
      await editDialog.locator('textarea').first().fill(`${fixtureLabel} T083 edited`)
      await editDialog.getByRole('button', { name: 'Lưu', exact: true }).click()
      await editDialog.waitFor({ state: 'hidden' })
      const saved = expect2xx(await api(page, `/api/tracker/entries/${targetId}`), 'read edited entry')
      check(saved.note_md === `${fixtureLabel} T083 edited`, 'saved note not visible from API')
      const delRow = page.locator(`[data-testid="entry-row"][data-entry-id="${targetId}"]`)
      await delRow.getByTestId('entry-undo').click()
      await page.getByText('Đã xoá bản ghi', { exact: true }).waitFor()
      check((await api(page, `/api/tracker/entries/${targetId}`)).status === 404, 'deleted entry remained readable')
      const restored = page.waitForResponse(response => response.url().includes(`/api/tracker/entries/${targetId}/restore`) && response.request().method() === 'POST')
      await page.getByRole('button', { name: 'Hoàn tác', exact: true }).last().click()
      check((await restored).ok(), 'restore request failed')
      expect2xx(await api(page, `/api/tracker/entries/${targetId}`), 'verify delete undo')
      check((await api(page, `/api/tracker/activity?year=2024&tracker_id=${trackerA.id}`)).status === 200, 'heatmap query failed after write/undo')
    })

    await runCase('A05', async () => {
      const activity = expect2xx(await api(page, `/api/tracker/activity?year=2024`), 'read year activity')
      const counts = new Map(activity.items.map((item) => [item.day, item.count]))
      for (const [day, count] of [['2024-01-14', 5], ['2024-01-13', 3], ['2024-01-12', 2], ['2024-01-11', 1], ['2024-01-10', 0], ['2024-02-29', 62]]) {
        check((counts.get(day) ?? 0) === count, `activity count on ${day}: expected ${count}, got ${counts.get(day) ?? 0}`)
      }
      await page.getByTestId('heatmap-year').fill('2024')
      await page.getByTestId('heatmap-month').fill('2024-01')
      const dayButtons = page.getByTestId('heatmap-day')
      for (const [day, count, level] of [['2024-01-14', '5', '3'], ['2024-01-13', '3', '3'], ['2024-01-12', '2', '2'], ['2024-01-11', '1', '1'], ['2024-01-10', '0', '0']]) {
        const cell = page.locator(`[data-testid="heatmap-day"][data-day="${day}"]`)
        check(await cell.getAttribute('data-count') === count && await cell.getAttribute('data-level') === level, `visible heatmap bucket mismatch for ${day}`)
      }
      for (const label of ['0 lần', '1 lần', '2 lần', '≥3 lần']) check((await page.getByLabel('Thang màu heatmap').innerText()).includes(label), `fixed legend missing ${label}`)
      check((await page.locator('[data-testid="heatmap-year-overview"] svg rect').count()) === 366, '2024 overview must be read-only 366-day sparse count picture')
    })

    await runCase('A06', async () => {
      await unlockThroughUI(page, payload.pin)
      const privateTracker = expect2xx(await api(page, '/api/tracker/trackers', 'POST', {
        name: `${baseName} private`, kind: 'health', input_mode: 'event', is_private: true,
      }), 'create private tracker')
      ownedTrackerIds.push(privateTracker.id)
      const privateEntry = expect2xx(await api(page, '/api/tracker/entries', 'POST', {
        tracker_id: privateTracker.id, occurred_at: '2024-02-29T08:00:00Z', note_md: `${payload.prefix} ${fixtureLabel.slice(payload.prefix.length).trim()} private T083`,
      }), 'create private entry')
      ownedEntryIds.push(privateEntry.id)
      expectedById.set(privateEntry.id, { ...privateEntry, tracker_id: privateTracker.id, tag: 'private' })

      await page.reload({ waitUntil: 'domcontentloaded' })
      await page.getByRole('tab', { name: 'Theo dõi', exact: true }).click()
      await page.getByTestId('tracker-open-report').click()
      await page.getByTestId('tracker-heatmap').waitFor()
      await page.getByTestId('heatmap-year').fill('2024')
      await page.getByTestId('heatmap-month').fill('2024-02')
      await page.getByTestId('heatmap-tracker').waitFor()
      const privateIncluded = expect2xx(await api(page, `/api/tracker/activity?year=2024&tracker_id=${privateTracker.id}`), 'private tracker aggregate while unlocked')
      check(privateIncluded.items.some((item) => item.day === '2024-02-29' && item.count === 1), 'unlocked private activity absent')

      // Hold an in-flight private aggregate; lock through the real PrivateGate control, then release it.
      let releaseResponse
      let seenRequest
      const deferred = new Promise((resolve) => { releaseResponse = resolve })
      const seen = new Promise((resolve) => { seenRequest = resolve })
      const privateUrl = `**/api/tracker/activity?year=2024&tracker_id=${privateTracker.id}`
      await page.route(privateUrl, async (route) => {
        seenRequest()
        await deferred
        try { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: privateIncluded.items }) }) } catch { /* aborted request is itself part of the lock race */ }
      })
      await selectOption(page, 'heatmap-tracker', `${baseName} private`)
      await Promise.race([seen, page.waitForTimeout(3_000).then(() => { throw new Error('deferred private response was not requested') })])
      await page.getByTestId('private-lock-now').click()
      await page.getByTestId('private-badge').filter({ hasText: 'đang khoá' }).waitFor()
      const publicOnly = expect2xx(await api(page, '/api/tracker/activity?year=2024'), 'locked visibility aggregate')
      check(publicOnly.items.find((item) => item.day === '2024-02-29')?.count === 62, 'locked aggregate included private activity or lost a public entry')
      const privateLocked = expect2xx(await api(page, `/api/tracker/activity?year=2024&tracker_id=${privateTracker.id}`), 'locked private tracker aggregate')
      check(privateLocked.items.length === 0, 'locked private tracker leaked aggregated days')
      releaseResponse()
      await page.unroute(privateUrl)
      await page.getByTestId('heatmap-tracker').waitFor()
      await page.getByTestId('heatmap-year').fill('2024')
      await page.getByTestId('heatmap-month').fill('2024-02')
      const lockedDayCell = page.locator('[data-testid="heatmap-day"][data-day="2024-02-29"]')
      await page.waitForFunction(() => document.querySelector('[data-testid="heatmap-day"][data-day="2024-02-29"]')?.getAttribute('data-count') === '62')
      check(await lockedDayCell.getAttribute('data-count') === '62', 'deferred private response repainted a private count after lock')
      check((await api(page, '/api/tracker/trackers')).value.items.every((tracker) => !tracker.is_private), 'private tracker remained visible after lock')
      check((await page.getByTestId('heatmap-tracker').innerText()).includes('Tất cả tracker'), 'heatmap tracker selection did not reset on lock')
      check(await page.getByTestId('tracker-entries-toggle').getAttribute('aria-expanded') === 'false', 'records view selection did not reset on lock')
      await unlockThroughUI(page, payload.pin)
      const rawPrivate = await api(page, `/api/tracker/entries?tracker_id=${privateTracker.id}&limit=10`)
      check(rawPrivate.status === 200 && rawPrivate.value.items.some((entry) => entry.id === privateEntry.id), 'synthetic private fixture cannot be read again after unlock')
    })

    await runCase('A07', async () => {
      await page.getByTestId('heatmap-year').fill('2024')
      await page.getByTestId('heatmap-month').fill('2024-02')
      const target = page.locator('[data-testid="heatmap-day"][data-day="2024-02-29"]')
      await target.focus()
      await page.keyboard.press('Space')
      await page.getByTestId('records-date').waitFor()
      check(await page.getByTestId('records-date').inputValue() === '2024-02-29', 'Space day-jump did not select exact day')
      check((await page.getByTestId('records-tracker').innerText()).includes('Tất cả tracker'), 'day-jump did not carry tracker selection')
      const today = await currentVietnamDate(page)
      const tomorrowDate = new Date(`${today}T00:00:00Z`)
      tomorrowDate.setUTCDate(tomorrowDate.getUTCDate() + 1)
      const tomorrow = tomorrowDate.toISOString().slice(0, 10)
      await page.getByTestId('heatmap-year').fill(tomorrow.slice(0, 4))
      await page.getByTestId('heatmap-month').fill(tomorrow.slice(0, 7))
      await page.locator(`[data-testid="heatmap-day"][data-day="${tomorrow}"]`).waitFor()
      check(await page.locator(`[data-testid="heatmap-day"][data-day="${tomorrow}"]`).isDisabled(), 'tomorrow heatmap day enabled')
      const calls = []
      const listener = (request) => { if (request.url().includes('/api/tracker/activity?')) calls.push(request.url()) }
      page.on('request', listener)
      await page.getByTestId('heatmap-year').fill('9999')
      check((await page.getByRole('alert').filter({ hasText: 'Chọn năm' }).count()) === 1, 'invalid year lacks bounded validation message')
      check(calls.length === 0, 'invalid year sent an activity API request')
      page.off('request', listener)
      const yearValue = await page.getByTestId('heatmap-year').inputValue()
      check(yearValue === '9999', 'invalid year was silently coerced')
      await page.getByTestId('heatmap-year').fill(today.slice(0, 4))
      await page.getByTestId('heatmap-month').fill(today.slice(0, 7))
      await page.locator(`[data-testid="heatmap-day"][data-day="${today}"]`).focus()
      await page.keyboard.press('Enter')
      check(await page.getByTestId('records-date').inputValue() === today, 'Enter day-jump did not select exact current Vietnam day')
    })

    await runCase('A08', async () => {
      await page.route('**/api/tracker/entries?*', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"synthetic T083 read failure"' }))
      await selectOption(page, 'records-mode', 'Theo ngày')
      await page.getByTestId('records-date').fill('1900-01-01')
      await page.getByText('Không tải được bản ghi.', { exact: true }).waitFor()
      check((await page.getByRole('alert').count()) > 0 && (await page.getByText('Không có bản ghi trong lựa chọn này.').count()) === 0, 'read error was presented as empty success')
      await page.unroute('**/api/tracker/entries?*')
      await page.getByRole('button', { name: 'Thử lại', exact: true }).click()
      await page.getByText('Không có bản ghi trong lựa chọn này.', { exact: true }).waitFor()
      const requests = []
      const listener = (request) => { if (request.url().includes('/api/tracker/activity?')) requests.push(request.url()) }
      page.on('request', listener)
      await page.route('**/api/tracker/activity?*', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"synthetic T083 heatmap failure"' }))
      await page.getByTestId('heatmap-year').fill('2022')
      await page.getByText('Không tải được heatmap.', { exact: true }).waitFor()
      check((await page.getByTestId('heatmap-summary').count()) === 0 && (await page.getByText('Chưa có bản ghi trong năm này.').count()) === 0, 'heatmap error was presented as zero')
      await page.unroute('**/api/tracker/activity?*')
      await page.getByRole('button', { name: 'Thử lại', exact: true }).last().click()
      await page.getByTestId('heatmap-summary').waitFor()
      page.off('request', listener)
      check(requests.length >= 2, 'heatmap retry did not make a bounded recovery request')
      await page.route('**/api/tracker/entries?*', (route) => route.continue())
      await page.unroute('**/api/tracker/entries?*')
    })

    await runCase('A09', async () => {
      // Reuse this run's own fixture; long Vietnamese text must remain readable.
      const longNote = `${fixtureLabel} T083 Chi tiết bản ghi tiếng Việt có dấu, nội dung nhiều dòng để kiểm tra bố cục và khả năng đọc trên cửa sổ thông thường.\nDòng thứ hai vẫn được giữ nguyên và tự xuống dòng.`
      const sampleId = [...expectedById.entries()].find(([, entry]) => entry.tag === 'leap-page-0')[0]
      expect2xx(await api(page, `/api/tracker/entries/${sampleId}`, 'PATCH', { note_md: longNote }), 'prepare owned long-note fixture')
      await selectOption(page, 'records-mode', 'Theo ngày')
      await page.getByTestId('records-date').fill('2024-02-29')
      await page.reload({ waitUntil: 'domcontentloaded' })
      await page.getByRole('tab', { name: 'Theo dõi', exact: true }).click()
      await page.getByTestId('tracker-open-report').click()
      await page.getByTestId('tracker-entries-toggle').click()
      await selectOption(page, 'records-mode', 'Theo ngày')
      await page.getByTestId('records-date').fill('2024-02-29')
      await page.getByTestId('records-list').getByText(longNote, { exact: true }).waitFor()
      for (const viewport of [{ width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 1280, height: 695 }]) {
        await page.setViewportSize(viewport)
        const metrics = await page.evaluate(() => ({
          width: innerWidth, height: innerHeight, pageWidth: document.documentElement.scrollWidth,
          bodyWidth: document.body.scrollWidth,
        }))
        check(metrics.width === viewport.width && metrics.height === viewport.height, `viewport mismatch ${viewport.width}: ${JSON.stringify(metrics)}`)
        check(metrics.pageWidth <= metrics.width && metrics.bodyWidth <= metrics.width, `horizontal page overflow at ${viewport.width}: ${JSON.stringify(metrics)}`)
        const heatmap = page.getByTestId('tracker-heatmap')
        const buttons = await heatmap.getByTestId('heatmap-day').evaluateAll((nodes) => nodes.map((node) => {
          const rect = node.getBoundingClientRect()
          return { width: rect.width, height: rect.height, font: parseFloat(getComputedStyle(node).fontSize) }
        }))
        check(buttons.every((button) => button.width >= 44 && button.height >= 44 && button.font >= 12), `day target/font below floor at ${viewport.width}`)
        const records = page.getByTestId('tracker-records')
        const recordMetrics = await records.locator('button,input,[role="combobox"]').evaluateAll(nodes => nodes.filter(node => node.getClientRects().length).map(node => {
          const r = node.getBoundingClientRect()
          return { width: r.width, height: r.height, right: r.right, left: r.left, font: parseFloat(getComputedStyle(node).fontSize), tag: node.tagName }
        }))
        check(recordMetrics.length > 5 && recordMetrics.every(item => item.width >= 44 && item.height >= 44 && item.font >= 12 && item.left >= 0 && item.right <= viewport.width), `Records control target/font/clipping failed at ${viewport.width}`)
        const actionGaps = await records.getByTestId('entry-row').evaluateAll(rows => rows.map(row => {
          const edit = row.querySelector('[data-testid="entry-edit"]').getBoundingClientRect()
          const remove = row.querySelector('[data-testid="entry-undo"]').getBoundingClientRect()
          return remove.left - edit.right
        }))
        check(actionGaps.length > 0 && actionGaps.every(gap => gap >= 8), `Records adjacent touch gap below 8px at ${viewport.width}`)
        const recordTextSizes = await records.locator('h3,p,span,label').evaluateAll(nodes => nodes.filter(node => node.getClientRects().length).map(node => parseFloat(getComputedStyle(node).fontSize)))
        check(recordTextSizes.length > 0 && recordTextSizes.every(size => size >= 12), `Records text below 12px at ${viewport.width}`)
        const noteMetrics = await records.getByText(longNote, { exact: true }).evaluate(node => ({ client: node.clientWidth, scroll: node.scrollWidth, wrap: getComputedStyle(node).whiteSpace }))
        check(noteMetrics.scroll <= noteMetrics.client + 1 && noteMetrics.wrap === 'pre-wrap', `Records long Vietnamese note clipped or lost wrapping at ${viewport.width}`)
        const gridMetrics = await heatmap.getByTestId('heatmap-month-grid').evaluate((grid) => {
          const scroller = grid.parentElement
          return {
            minWidth: parseFloat(getComputedStyle(grid).minWidth),
            gap: parseFloat(getComputedStyle(grid).columnGap),
            ownOverflow: scroller.scrollWidth > scroller.clientWidth,
          }
        })
        if (viewport.width === 390) {
          check(gridMetrics.minWidth >= 356 && gridMetrics.ownOverflow, 'mobile month grid must use its own min-356px horizontal scroller')
          check(Math.abs(gridMetrics.gap - 8) <= 1, 'mobile calendar column gap is not 8px')
          check((await heatmap.innerText()).includes('Vuốt ngang'), 'mobile horizontal swipe instruction missing')
        }
        const typeSizes = await heatmap.locator('h3,p,span,label,button').evaluateAll((nodes) => nodes.filter((node) => node.getClientRects().length).map((node) => parseFloat(getComputedStyle(node).fontSize)))
        check(typeSizes.every((size) => size >= 12), `heatmap text below 12px at ${viewport.width}`)
        if (viewport.width === 390) {
          screenshots.push(await shot(page, 'tracker083-heatmap-390x844', '[data-testid="tracker-heatmap"]'))
          screenshots.push(await shot(page, 'tracker083-records-390x844', '[data-testid="tracker-records"]'))
        }
        if (viewport.width === 768) screenshots.push(await shot(page, 'tracker083-records-768x1024', '[data-testid="tracker-records"]'))
        if (viewport.width === 1280) {
          screenshots.push(await shot(page, 'tracker083-heatmap-1280x695', '[data-testid="tracker-heatmap"]'))
          screenshots.push(await shot(page, 'tracker083-records-1280x695', '[data-testid="tracker-records"]'))
        }
      }
      await page.keyboard.press('Tab')
      const focus = await page.evaluate(() => {
        const element = document.activeElement
        return element ? { visible: !!element.getClientRects().length, outline: getComputedStyle(element).outlineStyle, ring: getComputedStyle(element).boxShadow } : null
      })
      check(focus?.visible && (focus.outline !== 'none' || focus.ring !== 'none'), 'keyboard focus indicator not visible')
    })

  } catch (error) {
    setupError = error
  } finally {
    const cleanup = []
    // Restore visibility only to remove this runner's own private fixture; no foreign ID is queried or mutated.
    try {
      const open = await api(page, '/api/me')
      if (open.status === 200) {
        const unlocked = await api(page, '/api/private/unlock', 'POST', { pin: payload.pin })
        if (unlocked.status < 200 || unlocked.status >= 300) cleanup.push(`private unlock HTTP ${unlocked.status}`)
      }
    } catch (error) { cleanup.push(`visibility restore: ${error.message}`) }
    for (const id of [...ownedEntryIds].reverse()) {
      try {
        const deleted = await api(page, `/api/tracker/entries/${id}`, 'DELETE')
        if (![204, 404].includes(deleted.status)) cleanup.push(`owned entry cleanup HTTP ${deleted.status}`)
      } catch (error) { cleanup.push(`owned entry cleanup: ${error.message}`) }
    }
    for (const id of [...ownedTrackerIds].reverse()) {
      try {
        const deleted = await api(page, `/api/tracker/trackers/${id}`, 'DELETE')
        if (![204, 404].includes(deleted.status)) cleanup.push(`owned tracker cleanup HTTP ${deleted.status}`)
      } catch (error) { cleanup.push(`owned tracker cleanup: ${error.message}`) }
    }
    cases.A10 = cleanup.length ? `FAIL: ${cleanup.join('; ')}` : 'PASS'
  }

  if (setupError) {
    for (const id of Object.keys(cases)) if (cases[id] === 'NOT_RUN') cases[id] = `NOT_RUN: setup aborted (${setupError.message})`
  }
  const failed = Object.values(cases).some((value) => value.startsWith('FAIL'))
  const inFunctionComplete = Object.entries(cases).every(([, value]) => value === 'PASS')
  return {
    status: setupError || failed ? 'FAIL' : inFunctionComplete ? 'PASS' : 'INCOMPLETE',
    cases,
    screenshots,
    fixture_ownership: { created_entry_ids: [...ownedEntryIds], created_tracker_ids: [...ownedTrackerIds] },
    temporary_fixture_cleanup: cases.A10,
    outer_teardown: 'NOT_RUN: QA025 caller owns browser context and disposable-cell teardown receipts',
    acceptance: 'T3 evidence only; T1 reconciles and accepts',
  }
}
