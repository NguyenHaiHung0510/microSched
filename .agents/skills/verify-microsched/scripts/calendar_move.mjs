/** R4 bounded actual synthetic app proof. Private mode never captures pixels/raw errors. */
import fs from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { randomUUID } from 'node:crypto'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
const execute = promisify(execFile)
const wt = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
const require = createRequire(path.join(wt, 'frontend/package.json'))
const { chromium, expect } = require('@playwright/test')
const args = process.argv.slice(2)
function arg(name) { const i = args.indexOf(name); if (i < 0 || !args[i + 1]) throw Error('EXPLICIT_ARGUMENT_REQUIRED'); return args[i + 1] }
const origin = new URL(arg('--origin')).origin, mode = arg('--case'), output = path.resolve(arg('--output'))
if (origin !== 'http://127.0.0.1:4177' || !['desktop', 'mobile', 'private', 'touch', 'diagnostic'].includes(mode)) throw Error('OWN_094_CASE_ORIGIN_REQUIRED')
const roots = [path.join(wt, '.local/r4-094'), path.resolve(wt, '../../harness-reports/mimi-qa-2026-oct-19-owner296/dev-2026-oct-22/techlead/r4-094-dev328')]
if (!roots.some(root => output.startsWith(root + path.sep))) throw Error('OWN_UNIQUE_OUTPUT_REQUIRED')
const python = arg('--python'), oracle = path.resolve(arg('--oracle'))
if (oracle !== path.join(wt, '.local/r4-094/oracle.py')) throw Error('OWN_ORACLE_REQUIRED')
let previous
let dateProof
if (args.includes('--resume')) {
  const priorPath = path.resolve(arg('--resume'))
  if (!roots.some(root => priorPath.startsWith(root + path.sep))) throw Error('OWN_RESUME_REQUIRED')
  previous = JSON.parse(await fs.readFile(priorPath, 'utf8'))
  needResume(previous)
}
if (args.includes('--date-proof')) {
  const proofPath = path.resolve(arg('--date-proof'))
  if (!roots.some(root => proofPath.startsWith(root + path.sep))) throw Error('OWN_DATE_PROOF_REQUIRED')
  dateProof = JSON.parse(await fs.readFile(proofPath, 'utf8'))
  if (!previous || dateProof.status !== 'PASS_NATIVE_POINTER_AND_UNDO' || dateProof.id !== previous.fixture.tasks[0]) throw Error('MATCHING_NATIVE_DATE_PROOF_REQUIRED')
}
function needResume(prior) {
  if (mode === 'touch' && prior.mode === 'mobile' && prior.fixture.scope === 'R4_094_OWN_PUBLIC' && prior.outcomes.some(x => x.label === 'single-day-undo' && x.status === 'PASS')) return
  if (mode === 'diagnostic' && prior.mode === 'desktop' && prior.status === 'AUTHOR_PASS' && prior.fixture.scope === 'R4_094_OWN_PUBLIC') return
  if (mode !== 'desktop' || prior.mode !== mode || prior.fixture.scope !== 'R4_094_OWN_PUBLIC' ||
      !prior.outcomes.some(x => x.label === 'clock-undo' && x.status === 'PASS')) throw Error('SETTLED_CLOCK_PROOF_REQUIRED_FOR_CONTINUATION')
}
await fs.mkdir(output, { recursive: false })
const record = path.join(output, 'receipt.json'), shared = path.join(wt, '.local/r4-094/fixture-manifest.json')
const prefix = previous?.fixture.prefix ?? 'R4-094-' + randomUUID().slice(0, 8)
const day = previous ? previous.anchor_day ?? previous.outcomes.find(x => x.label === 'baseline').api.tasks.find(x => x.id === previous.fixture.tasks[0]).due_on : new Date(Date.now() + 7 * 3600000 + 86400000).toISOString().slice(0, 10)
const addDays = (value, delta) => new Date(Date.parse(value + 'T00:00:00Z') + delta * 86400000).toISOString().slice(0, 10)
const r = { status: 'IN_PROGRESS', pid: process.pid, started: new Date().toISOString(), mode, origin, anchor_day: day, role: 'synthetic-owner', step: 'plan', outcomes: [], screenshots: [],
  fixture: { scope: mode === 'private' ? 'R4_094_OWN_PRIVATE_NO_CAPTURE' : 'R4_094_OWN_PUBLIC', prefix, tasks: [], annotations: [], sources: [], events: [], reminders: [], retention: 'RETAIN_WITH_MANIFEST' } }
if (previous) {
  r.fixture = previous.fixture
  if (mode === 'desktop') r.inherited_clock_proof = { from: arg('--resume'), labels: ['baseline', 'clock-move', 'clock-undo'] }
  else r.owned_fixture_from = arg('--resume')
}
async function save() {
  await fs.writeFile(record, JSON.stringify(r, null, 2))
  const m = JSON.parse(await fs.readFile(shared, 'utf8'))
  m.status = 'OWN_FIXTURES_RETAINED'
  m.cases ??= {}; m.cases[output] = r.fixture
  await fs.writeFile(shared, JSON.stringify(m, null, 2))
}
await save()
let browser, context, page
let releasePending = () => {}
const need = (value, code) => { if (!value) throw Error(code) }
async function call(route, method = 'GET', body) {
  const response = await context.request.fetch(origin + route, { method, data: body })
  return { status: response.status(), body: response.status() === 204 ? null : await response.json() }
}
async function create(route, body, category) {
  const response = await call(route, 'POST', body)
  if (response.body?.id) { r.fixture[category].push(response.body.id); await save() }
  need(response.status === 201, 'OWN_FIXTURE_CREATE_FAILED')
  return response.body
}
async function snapshot(label) {
  r.step = label; await save()
  const { stdout } = await execute(python, ['-B', oracle, record], { windowsHide: true, timeout: 12000 })
  const pg = JSON.parse(stdout), api = { tasks: [], annotations: [] }
  for (const id of r.fixture.tasks) {
    const response = await call('/api/tasks/' + id); need(response.status === 200, 'OWN_TASK_ORACLE_FAILED')
    const row = response.body, stored = pg.tasks.find(x => x.id === id)
    need(stored && row.due_precision === stored.due_precision && row.due_on === stored.due_on &&
      (row.due_at ? Date.parse(row.due_at) === Date.parse(stored.due_at) : stored.due_at === null), 'TASK_API_PG_MISMATCH')
    api.tasks.push({ id, due_precision: row.due_precision, due_on: row.due_on, due_at: row.due_at })
  }
  const marks = await call(`/api/calendar/annotations?from=${day.slice(0, 7)}-01&to=${addDays(day, 70)}`)
  for (const id of r.fixture.annotations) {
    const row = marks.body.items.find(x => x.id === id), stored = pg.annotations.find(x => x.id === id)
    need(row && stored && row.starts_on === stored.starts_on && row.ends_on === stored.ends_on, 'ANNOTATION_API_PG_MISMATCH')
    api.annotations.push({ id, starts_on: row.starts_on, ends_on: row.ends_on })
  }
  r.outcomes.push({ label, status: 'PASS', api, pg }); await save()
  return { api, pg }
}
const cell = value => page.locator(`[data-testid="calendar-day-cell"][data-day="${value}"]`)
async function openMove(kind, id, value) {
  const activate = locator => ['mobile', 'touch', 'private'].includes(mode) ? locator.tap() : locator.click()
  await cell(value).scrollIntoViewIfNeeded(); await activate(cell(value))
  const row = kind === 'task' ? page.locator(`[data-testid="calendar-day-task"][data-task-id="${id}"]`)
    : page.locator(`[data-testid="calendar-annotation-detail"][data-annotation-id="${id}"]`)
  await activate(row.getByTestId(kind === 'task' ? 'calendar-task-move' : 'calendar-annotation-move'))
  await expect(page.getByRole('dialog')).toHaveCount(1)
}
async function dialogMove(value) {
  const dialog = page.getByTestId('calendar-move-dialog')
  await dialog.locator('input[type=date]').fill(value)
  if (mode === 'touch') await dialog.getByRole('button', { name: 'Chuyển ngày', exact: true }).tap()
  else await dialog.locator('input[type=date]').press('Enter')
  await dialog.waitFor({ state: 'hidden', timeout: 30000 })
}
async function until(predicate) { await expect.poll(predicate, { timeout: 30000 }).toBe(true) }
async function annotationRow(id) { return (await call(`/api/calendar/annotations?from=${day.slice(0, 7)}-01&to=${addDays(day, 70)}`)).body.items.find(x => x.id === id) }
async function undo(predicate) {
  const button = page.getByRole('button', { name: 'Hoàn tác', exact: true }).last()
  if (mode === 'touch') await button.tap(); else await button.click()
  await until(predicate)
}
async function nativeDrag(source, target) {
  await source.scrollIntoViewIfNeeded(); await target.scrollIntoViewIfNeeded()
  const a = await source.boundingBox(), b = await target.boundingBox()
  need(a && b, 'VISIBLE_NATIVE_DRAG_TARGETS_REQUIRED')
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2); await page.mouse.down()
  await page.mouse.move(a.x + a.width / 2 + 10, a.y + a.height / 2, { steps: 5 })
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 15 })
  await page.mouse.move(b.x + b.width / 2 + 2, b.y + b.height / 2 + 2, { steps: 2 }); await page.mouse.up()
}
async function capture(label, dialog = false) {
  need(mode !== 'private', 'NO_PRIVATE_PIXELS')
  const name = label + '.png'
  await (dialog ? page.getByTestId('calendar-move-dialog') : page).screenshot({ path: path.join(output, name) })
  r.screenshots.push(name); await save()
}
try {
  need(require('@playwright/test/package.json').version === '1.62.1', 'REVIEWED_CACHED_BROWSER_REQUIRED')
  browser = await chromium.launch({ headless: true })
  const desktop = ['desktop', 'diagnostic'].includes(mode)
  context = await browser.newContext({ viewport: desktop ? { width: 1280, height: 800 } : { width: 390, height: 844 }, isMobile: !desktop, hasTouch: !desktop, reducedMotion: 'reduce', serviceWorkers: 'allow' })
  context.setDefaultTimeout(12000)
  await context.route('**/*', route => { const u = new URL(route.request().url()); return u.protocol === 'http:' && u.hostname === '127.0.0.1' && ['4177', '8004'].includes(u.port) ? route.continue() : route.abort('blockedbyclient') })
  page = await context.newPage(); await page.goto(origin + '/auth/dev-session'); await page.waitForURL(origin + '/')
  const me = await call('/api/me'); need(me.status === 200 && me.body.email === 'owner@test.local', 'SYNTHETIC_ROLE_REQUIRED')
  if (mode === 'touch' || mode === 'diagnostic') {
    await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
    const task = (await call('/api/tasks/' + r.fixture.tasks[0])).body
    need(!task.is_private && task.due_precision === 'date', 'OWN_PUBLIC_DATE_TASK_REQUIRED')
    const from = task.due_on, to = addDays(from, 1)
    if (mode === 'touch') {
      await openMove('task', task.id, from)
      await capture('native-touch-move-dialog', true)
      const controls = await page.getByTestId('calendar-move-dialog').locator('input,button').evaluateAll(items => items.filter(x => x.textContent?.includes('Chuyển ngày') || x.textContent === 'Huỷ' || x.tagName === 'INPUT').map(x => ({ height: x.getBoundingClientRect().height })))
      need(controls.every(x => x.height >= 44), 'NEW_TOUCH_TARGET_TOO_SMALL')
      await dialogMove(to); const moved = await snapshot('actual-touch-move')
      need(moved.api.tasks.find(x => x.id === task.id).due_on === to, 'TOUCH_DATE_NOT_SAVED')
      await undo(async () => (await call('/api/tasks/' + task.id)).body.due_on === from)
      await snapshot('actual-touch-undo')
      need(await page.getByTestId('calendar-quick-task-input').count() === 0, 'MOBILE_DESKTOP_ONLY_QUICK_BAR_POLICY_CHANGED')
      r.mobile_quick_bar = 'NOT_APPLICABLE_DESKTOP_ONLY_EXISTING_POLICY'
      r.inherited_mobile_movement = arg('--resume')
    } else {
      let held = false
      const gate = new Promise(resolve => { releasePending = resolve })
      const taskPattern = '**/api/tasks/' + task.id
      const hold = async route => { if (route.request().method() === 'PATCH' && !held) { held = true; await gate } await route.continue() }
      await context.route(taskPattern, hold)
      await nativeDrag(page.locator(`[data-testid="calendar-day-chip-task"][data-task-id="${task.id}"]`), cell(to))
      await until(() => held)
      await expect(page.getByTestId('calendar-move-pending')).toBeVisible()
      await expect(cell(to).locator(`[data-task-id="${task.id}"]`)).toHaveCount(1)
      const pending = await snapshot('held-task-request-before-ACK')
      need(pending.api.tasks.find(x => x.id === task.id).due_on === from, 'PENDING_WAS_FAKE_CONFIRMED')
      need(await page.getByText('Đã chuyển ngày', { exact: true }).count() === 0, 'SUCCESS_BEFORE_ACK')
      await capture('honest-pending-before-ACK')
      releasePending(); await until(async () => (await call('/api/tasks/' + task.id)).body.due_on === to)
      await page.getByTestId('calendar-move-pending').waitFor({ state: 'hidden' })
      await snapshot('task-canonical-ACK')
      await context.unroute(taskPattern, hold)
      await undo(async () => (await call('/api/tasks/' + task.id)).body.due_on === from)
      await snapshot('task-pending-diagnostic-undo')
      const id = r.fixture.annotations[1], before = await annotationRow(id), target = addDays(before.starts_on, 1)
      let writes = 0, rejected = false
      const pattern = '**/api/calendar/annotations/' + id
      const fault = async route => {
        if (route.request().method() === 'PATCH') {
          writes++
          if (!rejected) { rejected = true; return route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'Ngày chưa hợp lệ. Hãy chọn lại.' }) }) }
        }
        return route.continue()
      }
      await context.route(pattern, fault)
      await openMove('annotation', id, before.starts_on)
      let dialog = page.getByTestId('calendar-move-dialog')
      await dialog.locator('input[type=date]').fill('')
      await dialog.getByRole('button', { name: 'Chuyển ngày', exact: true }).click()
      need(writes === 0, 'EMPTY_DAY_SENT_HTTP')
      await dialog.getByRole('button', { name: 'Huỷ', exact: true }).click()
      await expect(cell(before.starts_on)).toBeFocused()
      await snapshot('empty-and-canceled-no-write')
      await openMove('annotation', id, before.starts_on); dialog = page.getByTestId('calendar-move-dialog')
      await dialog.locator('input[type=date]').fill(target)
      await dialog.getByRole('button', { name: 'Chuyển ngày', exact: true }).click()
      await expect(dialog.getByTestId('calendar-move-error')).toBeVisible()
      await expect(dialog.locator('input[type=date]')).toHaveValue(target)
      await expect(dialog.locator('input[type=date]')).toBeFocused()
      const rejectedState = await snapshot('expected-own-annotation-422')
      need(rejectedState.api.annotations.find(x => x.id === id).starts_on === before.starts_on, 'REJECTED_CANONICAL_ROW_CHANGED')
      await capture('retained-draft-after-own-422', true)
      await context.unroute(pattern, fault)
      await dialog.getByRole('button', { name: 'Chuyển ngày', exact: true }).click()
      await dialog.waitFor({ state: 'hidden' }); await snapshot('corrected-retry-ACK')
      await undo(async () => (await annotationRow(id))?.starts_on === before.starts_on)
      await snapshot('annotation-failure-diagnostic-undo')
      r.known_failure = { injected_own_response: 422, empty_and_cancel_http: 0, draft_retained: true, canonical_unchanged: true, corrected_retry: true }
    }
  } else if (mode === 'private') {
    const runtime = JSON.parse(await fs.readFile(path.join(wt, '.local/r4-094/runtime.json'), 'utf8'))
    need((await call('/api/private/unlock', 'POST', { pin: runtime.pin })).status === 200, 'OWN_SYNTHETIC_UNLOCK_FAILED')
    const hidden = prefix + '-' + randomUUID()
    const task = await create('/api/tasks', { title: hidden, status: 'open', due_precision: 'date', due_on: day, due_at: null, is_private: true }, 'tasks')
    await page.reload(); await page.getByRole('tab', { name: 'Lịch', exact: true }).click(); await openMove('task', task.id, day)
    let patches = 0
    const listener = request => { if (request.method() === 'PATCH' && new URL(request.url()).pathname === '/api/tasks/' + task.id) patches++ }
    context.on('request', listener); await context.setOffline(true)
    await page.getByTestId('calendar-move-dialog').locator('input[type=date]').fill(addDays(day, 1))
    await page.getByTestId('calendar-move-dialog').getByRole('button', { name: 'Chuyển ngày', exact: true }).click()
    await expect(page.getByTestId('calendar-move-error')).toBeVisible(); need(patches === 0, 'PRIVATE_OFFLINE_ADMISSION_MUST_BE_ZERO')
    await context.setOffline(false)
    const other = await context.newPage(); await other.goto(origin)
    await other.getByTestId('private-lock-now').click()
    await page.getByTestId('calendar-move-dialog').waitFor({ state: 'hidden' })
    need(!(await page.locator('body').innerText()).includes(hidden), 'PRIVATE_RAM_PURGE_REQUIRED')
    r.outcomes.push({ label: 'private-offline-refused-and-purged', status: 'PASS', mutation_http: 0, pixels: 0, raw_private_output: false })
  } else {
    // Keep the desktop drag fixture away from the clock/event day and its four-chip fold.
    const plannedDateDay = mode === 'desktop' ? addDays(day, 4) : day
    const date = previous ? (await call('/api/tasks/' + r.fixture.tasks[0])).body : await create('/api/tasks', { title: prefix + ' · Việc theo ngày', status: 'open', due_precision: 'date', due_on: plannedDateDay, due_at: null, is_private: false }, 'tasks')
    const clock = previous ? (await call('/api/tasks/' + r.fixture.tasks[1])).body : await create('/api/tasks', { title: prefix + ' · ' + 'A'.repeat(70), status: 'open', due_precision: 'datetime', due_on: null, due_at: day + 'T23:30:45.123+07:00', is_private: false }, 'tasks')
    const middle = day.slice(0, 8) + '27', start = day.slice(0, 8) + '26', end = day.slice(0, 8) + '28'
    const marker = previous ? await annotationRow(r.fixture.annotations[0]) : await create('/api/calendar/annotations', { label: prefix + ' · Dấu ngày tiếng Việt dài giữ nguyên độ dài và nội dung khi chuyển qua cuối tháng', starts_on: start, ends_on: end, is_private: false }, 'annotations')
    const single = previous ? await annotationRow(r.fixture.annotations[1]) : await create('/api/calendar/annotations', { label: prefix + ' · Mốc một ngày', starts_on: day, ends_on: day, is_private: false }, 'annotations')
    if (!previous) {
    const source = await create('/api/calendar/sources', { name: prefix, kind: 'manual' }, 'sources')
    await create('/api/calendar/events', { source_id: source.id, title: prefix + ' · Buổi lịch nguồn', starts_at: day + 'T10:00:00+07:00', ends_at: day + 'T11:00:00+07:00' }, 'events')
    for (const [task, body] of [[clock, { mode: 'relative', offset_minutes: -60 }], [date, { mode: 'absolute', due_at: addDays(day, 10) + 'T08:00:00+07:00' }]]) {
      const response = await call('/api/reminders/task/' + task.id, 'PUT', body)
      need(response.status === 200, 'OWN_REMINDER_CREATE_FAILED'); r.fixture.reminders.push(response.body.id); await save()
    }
    }
    await page.reload(); await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
    let dateDay = plannedDateDay
    if (previous) {
      r.resume_visibility = { original_task_chip_count: await page.locator(`[data-testid="calendar-day-chip-task"][data-task-id="${date.id}"]`).count() }
      need([day, addDays(day, 4)].includes(date.due_on) && Date.parse(clock.due_at) === Date.parse(day + 'T23:30:45.123+07:00'), 'RESUME_CANONICAL_BASELINE_MISMATCH')
      dateDay = addDays(day, 4)
      if (date.due_on !== dateDay) {
        const adjusted = await call('/api/tasks/' + date.id, 'PATCH', { due_precision: 'date', due_on: dateDay, due_at: null })
        need(adjusted.status === 200, 'OWN_FIXTURE_VISIBILITY_ADJUSTMENT_FAILED')
        r.fixture_preparation = { id: date.id, before_day: day, after_day: dateDay, purpose: 'Disjoint visible native-drag cell; old rows preserved', status: 200 }
      } else r.fixture_preparation = { id: date.id, after_day: dateDay, status: 'ALREADY_PREPARED_NO_WRITE' }
      if (dateProof) { need(dateProof.undo.due_on === dateDay, 'DATE_PROOF_BASELINE_MISMATCH'); r.inherited_date_proof = arg('--date-proof') }
      await save(); await page.reload(); await page.getByRole('tab', { name: 'Lịch', exact: true }).click()
    }
    const before = await snapshot('baseline')
    if (!previous) {
    await openMove('task', clock.id, day); await capture('clock-move-dialog', true)
    await dialogMove(addDays(day, 2)); const moved = await snapshot('clock-move')
    need(Date.parse(moved.api.tasks.find(x => x.id === clock.id).due_at) === Date.parse(addDays(day, 2) + 'T23:30:45.123+07:00'), 'VN_CLOCK_PRECISION_CHANGED')
    const relative = id => id.pg.reminders.find(x => x.task_id === clock.id)
    const absolute = id => id.pg.reminders.find(x => x.task_id === date.id)
    need(Date.parse(relative(moved).due_at) - Date.parse(relative(before).due_at) === 2 * 86400000, 'RELATIVE_REMINDER_NOT_SHIFTED')
    need(Date.parse(absolute(moved).due_at) === Date.parse(absolute(before).due_at), 'ABSOLUTE_REMINDER_CHANGED')
    await undo(async () => Date.parse((await call('/api/tasks/' + clock.id)).body.due_at) === Date.parse(clock.due_at)); const restored = await snapshot('clock-undo')
    need(Date.parse(restored.api.tasks.find(x => x.id === clock.id).due_at) === Date.parse(clock.due_at), 'FULL_UNDO_CLOCK_MISMATCH')
    }
    if (!dateProof) {
    if (mode === 'desktop') {
      r.step = 'date-native-drag'; await save()
      await nativeDrag(page.locator(`[data-testid="calendar-day-chip-task"][data-task-id="${date.id}"]`), cell(addDays(dateDay, 1)))
      await until(async () => (await call('/api/tasks/' + date.id)).body.due_on === addDays(dateDay, 1))
    } else { await openMove('task', date.id, day); await dialogMove(addDays(day, 1)) }
    const dateMoved = await snapshot('date-only-move')
    need(dateMoved.api.tasks.find(x => x.id === date.id).due_on === addDays(dateDay, 1) && dateMoved.api.tasks.find(x => x.id === date.id).due_at === null, 'DATE_PRECISION_CHANGED')
    need(Date.parse(dateMoved.pg.reminders.find(x => x.task_id === date.id).due_at) === Date.parse(before.pg.reminders.find(x => x.task_id === date.id).due_at), 'ABSOLUTE_SOURCE_MOVE_CHANGED_REMINDER')
    await undo(async () => (await call('/api/tasks/' + date.id)).body.due_on === dateDay); await snapshot('date-only-undo')
    }
    const last = new Date(Date.UTC(Number(day.slice(0, 4)), Number(day.slice(5, 7)), 0)).toISOString().slice(0, 10)
    if (mode === 'desktop') {
      r.step = 'range-native-drag'; await save()
      await nativeDrag(page.locator(`[data-testid="calendar-day-cell"][data-day="${middle}"] [data-annotation-id="${marker.id}"]`), cell(last))
      await until(async () => (await annotationRow(marker.id))?.starts_on === addDays(last, -1))
    } else { await openMove('annotation', marker.id, middle); await capture('range-move-dialog', true); await dialogMove(last) }
    const shifted = await snapshot('middle-range-cross-month')
    const mark = shifted.api.annotations.find(x => x.id === marker.id)
    need(mark.starts_on === addDays(last, -1) && mark.ends_on === addDays(last, 1), 'MIDDLE_GRAB_DURATION_CHANGED')
    await undo(async () => (await annotationRow(marker.id))?.starts_on === start); await snapshot('range-undo')
    await openMove('annotation', single.id, day); await dialogMove(addDays(day, 1)); const singleMoved = await snapshot('single-day-move')
    need(singleMoved.api.annotations.find(x => x.id === single.id).starts_on === addDays(day, 1) && singleMoved.api.annotations.find(x => x.id === single.id).ends_on === addDays(day, 1), 'SINGLE_DAY_DURATION_CHANGED')
    await undo(async () => (await annotationRow(single.id))?.starts_on === day); await snapshot('single-day-undo')
    await expect(page.getByTestId('calendar-day-chip-event').first()).not.toHaveAttribute('draggable', 'true')
    await capture('full-calendar-' + mode)
    const quick = page.getByTestId('calendar-quick-task-input')
    if (mode === 'desktop') {
    await expect(quick).toBeVisible()
    await quick.fill(prefix + ' · tạo nhanh')
    const quickResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/tasks')
    await page.getByTestId('calendar-quick-task-submit').click()
    const quickCreated = await quickResponse, quickRow = await quickCreated.json()
    if (quickRow.id) { r.fixture.tasks.push(quickRow.id); await save() }
    need(quickCreated.status() === 201, 'QUICK_CREATE_FAILED')
    await expect(page.getByText(prefix + ' · tạo nhanh', { exact: true }).first()).toBeVisible()
    } else {
      need(await quick.count() === 0, 'MOBILE_DESKTOP_ONLY_QUICK_BAR_POLICY_CHANGED')
      r.mobile_quick_bar = 'NOT_APPLICABLE_DESKTOP_ONLY_EXISTING_POLICY'
    }
    r.outcomes.push({ label: 'session-no-move-handles-and-public-preview', status: 'PASS', viewport: mode })
  }
  r.status = 'AUTHOR_PASS'; r.finished = new Date().toISOString()
} catch (error) {
  r.status = 'AUTHOR_FAIL'; r.error = mode === 'private' ? 'PRIVATE_CASE_FAILED_DETAILS_SUPPRESSED' : /^[A-Z0-9_]+$/.test(error.message) ? error.message : 'AUTHOR_UI_STEP_FAILED_DETAILS_SUPPRESSED'
  r.finished = new Date().toISOString(); process.exitCode = 1
  if (mode !== 'private') { r.error_type = error.name; r.error_first_line = error.message.split('\n')[0].replace(/https?:\/\/\S+/g, '[loopback]') }
} finally {
  releasePending()
  await save()
  try { if (context) { await context.setOffline(false); if (mode === 'private') await context.request.post(origin + '/api/private/lock'); await context.request.post(origin + '/auth/logout') } }
  finally { await context?.close(); await browser?.close() }
  console.log(JSON.stringify({ status: r.status, mode, output, step: r.step, error: r.error }))
}
