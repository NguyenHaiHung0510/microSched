import {test,expect} from './fixtures/tracker'
const id='019a0e2e-0000-7000-8003-000000000096',original='2026-10-24T23:00:49.367000Z',long='Bản ghi tiếng Việt đầy đủ. '+ 'LongUnbrokenContent0123456789'.repeat(18)
test('journal entry arriving before parent metadata edits through V1 and preserves untouched timestamp',async({page,trackerApi})=>{
 const tracker=trackerApi.trackers[1],entry={id,tracker_id:tracker.id,occurred_at:original,amount:12345,quantity:null,list_amount:null,note_md:null as string|null,created_at:original,updated_at:original};trackerApi.entries=[entry]
 let release!:()=>void;const entriesRead=new Promise<void>(resolve=>{release=resolve});let reads=0;let allowOpen!:()=>void;const canonicalGate=new Promise<void>(resolve=>{allowOpen=resolve});const writes:Record<string,unknown>[]=[]
 await page.route('**/api/tracker/trackers',async route=>{await entriesRead;await route.fallback()})
 await page.route('**/api/tracker/entries?*',async route=>{await route.fulfill({json:{items:[entry]}});release()})
 await page.route('**/api/tracker/entries/'+id+'**',async route=>{if(route.request().method()==='GET'){reads++;await canonicalGate;return route.fulfill({json:{...entry,funding:{status:'none'}}})}if(route.request().method()==='PATCH'){const body=route.request().postDataJSON();writes.push(body);Object.assign(entry,body);return route.fulfill({json:entry})}return route.fallback()})
 await page.goto('/');await page.getByRole('tab',{name:'Theo dõi',exact:true}).click();await page.getByTestId('tracker-tab-journal').click();if(await page.getByTestId('tracker-entries-toggle').getAttribute('aria-expanded')!=='true')await page.getByTestId('tracker-entries-toggle').click();await page.locator('[data-entry-id="'+id+'"][data-testid="entry-row"]').getByTestId('entry-edit').click();const dialog=page.getByTestId('entry-edit-dialog');await expect(page.getByText('Đang mở bản ghi…',{exact:true})).toBeVisible();await expect(dialog).toHaveCount(0);allowOpen();await expect(dialog).toBeVisible();expect(reads).toBe(1);await dialog.locator('input[inputmode="numeric"]').first().fill('12346');await dialog.locator('textarea').fill(long);expect(await dialog.locator('form').evaluate(form=>(form as HTMLFormElement).checkValidity())).toBe(true)
 const geometry=await dialog.evaluate(element=>{const d=element.getBoundingClientRect();return [...element.querySelectorAll('form,input,textarea,[role="combobox"]')].filter(e=>{const b=e.getBoundingClientRect();return b.width>1&&b.height>1}).map(e=>{const b=e.getBoundingClientRect();return {fits:b.left>=d.left&&b.right<=d.right,width:b.width}})});expect(geometry.every(x=>x.fits)).toBe(true);await dialog.getByRole('button',{name:'Lưu',exact:true}).click();await expect(dialog).toBeHidden();await expect.poll(()=>writes.length).toBe(1);expect(writes[0]).toMatchObject({amount:12346,note_md:long});expect(writes[0]).not.toHaveProperty('occurred_at');expect(writes[0]).not.toHaveProperty('funding_entry_id');expect(entry.occurred_at).toBe(original);expect(entry.note_md).toBe(long);const target=await page.getByTestId('reminder-center-open').boundingBox();expect(target!.width).toBeGreaterThanOrEqual(44);expect(target!.height).toBeGreaterThanOrEqual(44)
})
test('unavailable canonical entry is a visible refusal before editor or mutation',async({page,trackerApi})=>{
 const entry={id,tracker_id:trackerApi.trackers[1].id,occurred_at:original,amount:12345,quantity:null,list_amount:null,note_md:null,created_at:original,updated_at:original};trackerApi.entries=[entry];let writes=0;await page.route('**/api/tracker/entries/'+entry.id+'**',route=>{if(route.request().method()!=='GET')writes++;return route.fulfill({status:404,json:{detail:'Không tìm thấy bản ghi.'}})})
 await page.goto('/');await page.getByRole('tab',{name:'Theo dõi',exact:true}).click();await page.getByTestId('tracker-tab-journal').click();if(await page.getByTestId('tracker-entries-toggle').getAttribute('aria-expanded')!=='true')await page.getByTestId('tracker-entries-toggle').click();await page.locator('[data-testid="entry-row"][data-entry-id="'+entry.id+'"]').getByTestId('entry-edit').click();await expect(page.getByText('Không tìm thấy bản ghi.',{exact:true})).toBeVisible();await expect(page.getByTestId('entry-edit-dialog')).toHaveCount(0);expect(writes).toBe(0)
})


test('cached public entry remains editable offline without requiring a new GET', async ({ page, trackerApi }) => {
  const entry = { id, tracker_id: trackerApi.trackers[1].id, occurred_at: original, amount: 12345, quantity: null, list_amount: null, note_md: null, created_at: original, updated_at: original }
  trackerApi.entries = [entry]
  let reads = 0
  await page.route('**/api/tracker/entries/' + id + '**', route => {
    if (route.request().method() === 'GET') reads++
    return route.fallback()
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi', exact: true }).click()
  await page.getByTestId('tracker-tab-journal').click()
  const edit = page.locator('[data-entry-id="' + id + '"][data-testid="entry-row"]').getByTestId('entry-edit')
  await edit.click()
  const dialog = page.getByTestId('entry-edit-dialog')
  await expect(dialog).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  expect(reads).toBe(1)
  await page.context().setOffline(true)
  await edit.click()
  await expect(dialog).toBeVisible()
  expect(reads).toBe(1)
  await page.context().setOffline(false)
})


test('held private canonical GET cannot reopen editor after UI lock and preserves public draft', async ({ page, trackerApi, taskApi }, testInfo) => {
  test.skip(testInfo.project.name === 'mobile', 'One desktop held-GET representative; mobile layout is covered separately')
  taskApi.privateUntil = new Date(Date.now() + 60_000).toISOString()
  const publicTracker = trackerApi.trackers[1]
  const privateTracker = { ...publicTracker, id: '019a0e2e-0000-7000-8003-000000000196', name: 'Private synthetic tracker', is_private: true }
  trackerApi.trackers.push(privateTracker)
  const entry = { id, tracker_id: privateTracker.id, occurred_at: original, amount: 12345, quantity: null, list_amount: null, note_md: null, created_at: original, updated_at: original }
  trackerApi.entries = [entry]
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  let heldGet = false, fulfilled = false, mutations = 0
  await page.route('**/api/tracker/entries/' + id + '**', async route => {
    if (route.request().method() !== 'GET') { mutations++; return route.fallback() }
    heldGet = true
    await held
    await route.fulfill({ json: entry })
    fulfilled = true
  })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Theo dõi', exact: true }).click()
  const publicCard = page.locator('[data-testid="tracker-card"][data-tracker-id="' + publicTracker.id + '"]')
  await publicCard.getByTestId('tracker-button').click()
  await publicCard.getByTestId('tracker-amount-input').fill('97531')
  await page.getByTestId('tracker-tab-journal').click()
  await page.locator('[data-entry-id="' + id + '"][data-testid="entry-row"]').getByTestId('entry-edit').click()
  await expect.poll(() => heldGet).toBe(true)
  await expect(page.getByText('Đang mở bản ghi…', { exact: true })).toBeVisible()
  const locked = page.waitForResponse(response => new URL(response.url()).pathname === '/api/private/lock' && response.request().method() === 'POST')
  await page.getByTestId('private-lock-now').click()
  expect((await locked).status()).toBe(204)
  release()
  await expect.poll(() => fulfilled).toBe(true)
  await expect(page.getByTestId('entry-edit-dialog')).toHaveCount(0)
  expect(mutations).toBe(0)
  await page.getByTestId('tracker-tab-capture').click()
  await expect(publicCard.getByTestId('tracker-amount-input')).toHaveValue('97531')
  await expect(page.getByTestId('tracker-grid')).toHaveAttribute('data-update-dirty', 'true')
  await publicCard.getByRole('button', { name: 'Huỷ', exact: true }).click()
  await expect(page.getByTestId('tracker-grid')).not.toHaveAttribute('data-update-dirty', 'true')
  expect(mutations).toBe(0)
})
