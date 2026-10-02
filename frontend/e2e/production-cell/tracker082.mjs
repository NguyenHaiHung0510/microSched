import {createHash} from 'node:crypto'
function check(ok, message) { if(!ok) throw new Error(message) }
async function api(page,path,method='GET',body) {
  const r=await page.evaluate(async ({path,method,body})=>{
    const r=await fetch(path,{method,headers:body?{'content-type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});return {status:r.status,text:await r.text()}
  },{path,method,body})
  check(r.status>=200 && r.status<300, `fixture API ${method} ${path} status${r.status}`)
  return r.text?JSON.parse(r.text):null
}
async function shot(page,name,selector) {
  const png=await page.locator(selector).screenshot({animations:'disabled'})
  return {name,viewport:await page.evaluate(()=>({width:innerWidth,height:innerHeight})),sha256:createHash('sha256').update(png).digest('hex'),png_base64:png.toString('base64')}
}
export async function runTracker082(page,payload) {
  const cases={}, screenshots=[], entries=[], trackers=[], groups=[]
  const labels=payload.fixture_labels
  let failure
  try {
    await page.keyboard.press('Escape')
    await page.getByRole('tab',{name:'Theo dõi',exact:true}).click()
    const reminder={reminder_time:'08:00:00',reminder_mode:'fixed',reminder_interval_days:1,reminder_action:'confirm_event',reminder_text:labels[8]}
    const health=await api(page,'/api/tracker/trackers','POST',{name:labels[8],kind:'health',input_mode:'event',is_private:false,...reminder});trackers.push(health.id)
    const g1=await api(page,'/api/tracker/groups','POST',{name:labels[4],kind:'finance'});groups.push(g1.id)
    const g2=await api(page,'/api/tracker/groups','POST',{name:labels[2],kind:'finance'});groups.push(g2.id)
    for(const [group,name,amount] of [[g1,labels[5],300],[g2,labels[6],100]]) {
      const t=await api(page,'/api/tracker/trackers','POST',{name,kind:'finance',input_mode:'money',direction:'out',group_id:group.id,is_private:false});trackers.push(t.id)
      const e=await api(page,'/api/tracker/entries','POST',{tracker_id:t.id,amount,note_md:labels[8]});entries.push(e.id)
    }
    await page.reload({waitUntil:'domcontentloaded'})
    await page.getByRole('tab',{name:'Theo dõi',exact:true}).click()
    await page.getByRole('button',{name:'Mở rộng tất cả',exact:true}).click()
    await page.locator(`[data-testid="tracker-edit"][data-tracker-id="${health.id}"]`).click()
    await page.evaluate(()=>{
      window.__notes082PermissionCalls=0
      Object.defineProperty(Notification,'requestPermission',{configurable:true,value:async()=>{window.__notes082PermissionCalls++;return 'denied'}})
    })
    const dialog=page.getByTestId('tracker-dialog')
    await dialog.getByTestId('tracker-name-input').fill(labels[0])
    const saved=page.waitForResponse(r=>r.request().method()==='PATCH' && r.url().endsWith(`/tracker/trackers/${health.id}`))
    await dialog.getByRole('button',{name:'Lưu thay đổi',exact:true}).click()
    check((await saved).status()===200,'rename did not save')
    await dialog.waitFor({state:'hidden'})
    check(await page.evaluate(()=>window.__notes082PermissionCalls)===0,'unchanged rename requested push permission')
    const after=await api(page,'/api/tracker/trackers')
    const row=after.items.find(t=>t.id===health.id)
    check(row?.name===labels[0],'rename not persisted')
    for(const key of Object.keys(reminder)) check(row[key]===health[key],`rename changed ${key}`)
    cases.rename_unchanged_reminder_without_push='PASS'

    await page.getByTestId('tracker-open-report').click()
    const composition=page.getByTestId('dashboard-finance-composition')
    await composition.waitFor()
    const bars=await composition.locator('[data-testid="dashboard-f3-group"] summary [aria-hidden="true"] > span.absolute').evaluateAll(nodes=>nodes.map(n=>parseFloat(n.style.width)))
    check(bars.length===2 && bars.some(v=>Math.abs(v-75)<.01) && bars.some(v=>Math.abs(v-25)<.01),'finance bars not75/25')
    cases.finance_real_groups_share='PASS'
    const rhythm=page.getByTestId('tracker-rhythm')
    await rhythm.waitFor()
    const today=await page.evaluate(()=>{
      const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date())
      const v=t=>parts.find(p=>p.type===t)?.value;return `${v('day')}/${v('month')}/${v('year')}`
    })
    await rhythm.getByRole('button',{name:new RegExp(today)}).first().waitFor()
    cases.rhythm_current_vietnam_week='PASS'
    for(const viewport of [{width:390,height:844},{width:1280,height:695}]) {
      await page.setViewportSize(viewport)
      const measured=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth}))
      check(measured.width===viewport.width&&measured.height===viewport.height&&measured.scrollWidth<=measured.width,'tracker responsive overflow')
      screenshots.push(await shot(page,`finance-${viewport.width}.png`,'[data-testid="dashboard-finance-composition"]'))
      screenshots.push(await shot(page,`rhythm-${viewport.width}.png`,'[data-testid="tracker-rhythm"]'))
    }
  } catch(err) { failure=err }
  finally {
    for(const id of entries.reverse()) await api(page,`/api/tracker/entries/${id}`,'DELETE')
    for(const id of trackers.reverse()) await api(page,`/api/tracker/trackers/${id}`,'DELETE')
    for(const id of groups.reverse()) await api(page,`/api/tracker/groups/${id}`,'DELETE')
  }
  if(failure) throw failure
  const beforeNotes=await api(page,'/api/notes'); const originalNote=beforeNotes.items.find(n=>n.title===labels[4]); check(originalNote,'note fixture missing'); const originalBody=originalNote.body_md
  try {
  await page.getByRole('tab',{name:'Ghi chú',exact:true}).click()
  const card=page.locator('[data-testid="note-card"]',{has:page.getByTestId('note-title').filter({hasText:labels[4]})})
  await card.getByTestId('note-future-reflection-trigger').click()
  const reflection=page.getByTestId('note-future-reflection-dialog')
  await reflection.getByTestId('note-future-reflection-input').fill(labels[8])
  await reflection.getByTestId('note-future-reflection-submit').click()
  await reflection.waitFor({state:'hidden'})
  const golden=card.getByTestId('note-reflection-box')
  await golden.waitFor()
  const bg=await golden.evaluate(n=>getComputedStyle(n).backgroundColor)
  check(bg==='rgb(253, 245, 223)','reflection rendered color not golden')
  screenshots.push(await shot(page,'golden.png','[data-testid="note-reflection-box"]'))
  cases.golden_rendered_token='PASS'
  // Restore exact original body, leaving the existing fixture ledger unchanged.
  } finally { await api(page,`/api/notes/${originalNote.id}`,'PATCH',{body_md:originalBody}) }
  return {status:'PASS',cases,screenshots,temporary_fixture_cleanup:'PASS'}
}
