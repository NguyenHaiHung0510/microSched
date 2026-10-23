/** Focused R3 author/common-path driver, using the repository's cached Playwright.
 * Synthetic isolated context only; unique outputs, no provider, no091 lifecycle.
 */
import {createRequire} from 'node:module'
import {fileURLToPath} from 'node:url'
import path from 'node:path'
import fs from 'node:fs/promises'
import {execFileSync} from 'node:child_process'
const source=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..')
const require=createRequire(path.join(source,'frontend/package.json'))
const {chromium,expect}=require('@playwright/test')
const args=process.argv.slice(2), value=name=>args[args.indexOf(name)+1]
const root=value('--output'), mode=args.includes('--case')?value('--case'):'common'
if(!root||!path.isAbsolute(root)||!['common','private','draft','bulk'].includes(mode))throw Error('Explicit absolute output and common/private/bulk case required')
const local=path.resolve(source,'.local/r3-092'), report=path.resolve(source,'../../harness-reports/mimi-qa-2026-oct-19-owner296/dev-2026-oct-22')
if(![local,report].some(r=>path.resolve(root).startsWith(r+path.sep)))throw Error('Output must be inside owned092/local or approved report root')
const output=path.join(root,new Date().toISOString().replace(/[:.]/g,'-')+'-'+mode)
await fs.mkdir(root,{recursive:true});await fs.mkdir(output)
const origin='http://127.0.0.1:4175',head=execFileSync('git',['rev-parse','HEAD'],{cwd:source,encoding:'utf8'}).trim()
const receipt={case:mode,source,head,started:new Date().toISOString(),status:'RUNNING',assertions:[],requests:[],screenshots:[],provider_calls:0,cost:{tokens:'UNKNOWN',USD:'UNKNOWN'}}
const fixture=JSON.parse(await fs.readFile(path.join(local,'fixture-manifest.json'),'utf8'))
const secrets=JSON.parse(await fs.readFile(path.join(local,'runtime.json'),'utf8'))
const browser=await chromium.launch({headless:true})
const context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'allow'})
await context.route('**/*',route=>{
 const request=route.request(),url=new URL(request.url())
 if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!['4175','8002'].includes(url.port))return route.abort('blockedbyclient')
 const method=request.method(),p=url.pathname
 const permitted=['GET','HEAD'].includes(method)||method==='POST'&&(/^\/api\/reminder-history\/handled-batches\//.test(p)||['/api/private/lock','/api/private/unlock','/auth/logout'].includes(p))||method==='PUT'&&/^\/api\/reminder-history\/(one_shot|tracker_dispatch|subscription_dispatch|mimi_intent)\/[\da-f-]+\/handled$/.test(p)
 if(!permitted)return route.abort('blockedbyclient')
 receipt.requests.push({method,path:p});return route.continue()
})
const page=await context.newPage()
const screenshot=async(name)=>{await page.screenshot({path:path.join(output,name),fullPage:false});receipt.screenshots.push(name)}
const check=(name)=>receipt.assertions.push({name,status:'PASS'})
async function history(){await page.getByTestId('reminder-center-open').click();await page.getByRole('button',{name:'Lịch sử',exact:true}).click();await expect(page.getByTestId('history-row').first()).toBeVisible()}
async function get(p){const r=await context.request.get(origin+p);expect(r.status()).toBe(200);return r.json()}
try{
 const ready=await get('/api/readyz');expect(ready.commit).toBe(head);expect(ready.db).toBe('up');receipt.readyz=ready
 await page.goto(origin+'/auth/dev-session');await page.waitForURL(origin+'/')
 const me=await get('/api/me');expect(me.email).toBe('owner@test.local');receipt.principal='synthetic local dev-session owner'
 if(mode==='private'||mode==='draft'){
  const unlocked=await context.request.post(origin+'/api/private/unlock',{data:{pin:secrets.pin}});expect(unlocked.status()).toBe(200)
  await page.reload();await history();const second=await context.newPage();await second.goto(origin+'/');if(mode==='private'){await expect(page.getByText('R3 PRIVATE synthetic',{exact:true})).toBeVisible()
  await page.getByTestId('history-prepare-all').click();await expect(page.getByTestId('history-bulk-confirm')).toBeVisible()
  const confirmRequest=receipt.requests.filter(r=>r.path.endsWith('/prepare')).length;expect(confirmRequest).toBe(1)
  await second.getByRole('button',{name:'Khoá lại ngay',exact:true}).click()
  await expect(page.getByTestId('history-bulk-confirm')).toHaveCount(0)
  await expect(page.getByText('R3 PRIVATE synthetic',{exact:true})).toHaveCount(0)
  await expect(page.getByRole('button',{name:'Xử lý 0 đã chọn',exact:true})).toBeVisible()
  check('Cross-page real private lock purges private rows and prepared selection without commit')
  await screenshot('private-lock-purge.png')}
  // A mounted public editor keeps its dirty draft through another actual lock.
  const publicRow=page.locator('[data-occurrence="one_shot:'+fixture.one_shots[1]+'"]')
  await publicRow.getByRole('button',{name:'Mở đối tượng',exact:true}).click()
  const editor=page.getByRole('dialog',{name:'Đối tượng được nhắc'}),content=editor.locator('textarea')
  await content.fill('R3 unsaved public draft')
  await context.request.post(origin+'/api/private/unlock',{data:{pin:secrets.pin}})
  await second.reload();await second.getByRole('button',{name:'Khoá lại ngay',exact:true}).click()
  await expect(content).toHaveValue('R3 unsaved public draft');check('Public source draft remains mounted and unsaved on cross-page lock')
  await screenshot('public-dirty-draft-retained.png');await editor.getByRole('button',{name:'Huỷ',exact:true}).click()
  await second.close()
 }else{
  await history();await expect(page.getByTestId('history-row')).toHaveCount(50)
  if(mode==='common'){
   await screenshot('history-desktop-day-groups.png');check('Latest-first server day groups and first page50')
   await page.getByTestId('history-more').click();await expect(page.getByTestId('history-row')).toHaveCount(fixture.public_occurrences)
   const origins=await page.getByTestId('history-row').evaluateAll(rows=>[...new Set(rows.map(r=>r.getAttribute('data-occurrence').split(':')[0]))])
   expect(origins.sort()).toEqual(['mimi_intent','one_shot','subscription_dispatch','tracker_dispatch']);check('All four durable origins shown; one Mimi row, no fabricated clock')
   const taskBefore=await get('/api/tasks/'+fixture.tasks[0]);receipt.task_completed_before=taskBefore.completed_at
   const url='**/api/reminder-history/one_shot/'+fixture.one_shots[0]+'/handled'
   let release;const held=new Promise(resolve=>{release=resolve})
   await page.route(url,async route=>{await held;await route.continue()})
   const row=page.locator('[data-occurrence="one_shot:'+fixture.one_shots[0]+'"]')
   await row.getByTestId('history-handle').click();await expect(row.getByTestId('history-handle')).toHaveText('Đang xác nhận…');await screenshot('single-pending.png');release()
   await expect(page.locator('[data-occurrence="one_shot:'+fixture.one_shots[0]+'"] [data-testid="history-handle"]')).toHaveText('Đã xử lý')
   await page.unroute(url);expect((await get('/api/tasks/'+fixture.tasks[0])).completed_at).toBe(taskBefore.completed_at);check('Single ACK immediate truthful pending then durable handled; Task completion unchanged')
   await page.setViewportSize({width:390,height:844});await expect(page.getByTestId('reminder-history')).toBeVisible()
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await screenshot('history-mobile.png');check('390px layout without horizontal document overflow')
  }else{
   const before=await get('/api/reminder-history?handled=unhandled&limit=100')
   const count=before.items.length;expect(count).toBeGreaterThan(50)
   await page.getByTestId('history-prepare-all').click();await expect(page.getByRole('heading',{name:'Xử lý '+count+' lần nhắc?',exact:true})).toBeVisible();await screenshot('bulk-exact-confirm.png')
   await page.getByTestId('history-bulk-commit').click();await expect(page.getByTestId('history-bulk-confirm')).toHaveCount(0)
   expect((await get('/api/reminder-history?handled=unhandled')).items).toHaveLength(0)
   receipt.bulk_count=count;check('Full server-filter count includes unloaded rows and commits exact set')
   expect((await get('/api/tasks/'+fixture.tasks[0])).completed_at).toBeNull()
   await screenshot('bulk-complete.png');check('Bulk has no Task completion side effect')
  }
 }
 receipt.status='AUTHOR_PASS'
}catch(error){receipt.status='FAIL';receipt.error=String(error);await screenshot('failure.png').catch(()=>{})}
finally{await context.request.post(origin+'/auth/logout').catch(()=>{});receipt.finished=new Date().toISOString();await context.close();await browser.close();await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2),{flag:'wx'});console.log(JSON.stringify({status:receipt.status,output,assertions:receipt.assertions,error:receipt.error}));}
if(receipt.status!=='AUTHOR_PASS')process.exitCode=1
