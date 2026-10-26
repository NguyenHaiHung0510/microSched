import {test,expect} from './fixtures/tasks'
import type {HistoryRow,HistoryBatch} from '../src/reminder-history'
import type {Note} from '../src/note-ui'
import {appendFutureReflection} from '../src/note-ui'

test.beforeEach(async({page})=>{
 await page.route('**/api/tracker/trackers**',route=>route.fulfill({json:{items:[]}}))
})

test('098 unknown bulk ACK retains the same snapshot through dismissal and retry, but purges on scope loss',async({page,taskApi})=>{
 const row:HistoryRow={origin:'one_shot',source_kind:'task',occurrence_ref:{origin:'one_shot',id:'bulk098'},source_ref:{kind:'task',id:taskApi.tasks[0].id},occurrence_at:'2026-10-24T09:00:00Z',occurrence_on:'2026-10-24',time_precision:'datetime',time_basis:'recorded_only',status:'sent',title:'Synthetic bulk retry',body:null,handled_at:null,is_private:false,can_open:true,can_handle:true}
 const prepared:string[]=[],committed:string[]=[];let unknown=true
 await page.route('**/api/reminders**',r=>r.fulfill({json:{items:[],has_more:false,registered_devices:0}}))
 await page.route('**/api/reminder-history**',async route=>{
  const req=route.request(),url=new URL(req.url())
  if(req.method()==='GET')return route.fulfill({json:{items:[row],next_cursor:null,has_more:false,private_notice:null}})
  if(url.pathname.endsWith('/prepare')){
   const body=req.postDataJSON();prepared.push(body.batch_id)
   return route.fulfill({json:{id:body.batch_id,selected_count:1,cutoff:'2026-10-24T10:00:00Z',expires_at:'2026-10-24T10:15:00Z',filter:body.filter,scope_visible:true,result:null} satisfies HistoryBatch})
  }
  if(url.pathname.endsWith('/commit')){
   const id=url.pathname.split('/').at(-2)!;committed.push(id)
   if(unknown)return route.fulfill({status:503,json:{detail:'history_batch_commit_unknown'}})
   return route.fulfill({json:{id,selected_count:1,cutoff:'2026-10-24T10:00:00Z',expires_at:'2026-10-24T10:15:00Z',filter:{},scope_visible:true,result:{selected_count:1,new_count:0,already_count:1}} satisfies HistoryBatch})
  }
  return route.fulfill({status:404})
 })
 await page.goto('/?reminders=1');await page.getByRole('button',{name:'Lịch sử',exact:true}).click()
 const history=page.getByTestId('reminder-history'),confirm=page.getByTestId('history-bulk-confirm')
 await history.getByTestId('history-selection-toggle').click();await history.getByTestId('history-prepare-all').click()
 await page.getByTestId('history-bulk-commit').click();await expect(confirm.getByRole('alert')).toContainText('Chưa xác định')
 await expect(confirm.getByRole('button',{name:'Huỷ',exact:true})).toBeDisabled()
 await expect(confirm.getByRole('button',{name:'Đóng',exact:true})).toHaveCount(0)
 await page.keyboard.press('Escape');await expect(confirm).toBeVisible()
 await page.locator('[data-slot="dialog-overlay"]').last().click({position:{x:3,y:3},force:true});await expect(confirm).toBeVisible()
 unknown=false;await page.getByTestId('history-bulk-commit').click();await expect(confirm).toBeHidden()
 expect(prepared).toHaveLength(1);expect(committed).toEqual([prepared[0],prepared[0]])
 await expect(history.getByRole('status')).toContainText('Đã xử lý 1')
 unknown=true;await history.getByTestId('history-prepare-all').click();await page.getByTestId('history-bulk-commit').click()
 await expect(confirm.getByRole('alert')).toContainText('Chưa xác định')
 await page.evaluate(()=>window.dispatchEvent(new Event('microsched:visibility')));await expect(confirm).toBeHidden()
 expect(prepared[1]).not.toBe(prepared[0]);expect(committed).toHaveLength(3)
})

for(const mode of ['all','unhandled']) test('098 History '+mode+' retains pages, disclosure and current/next anchor',async({page,taskApi})=>{
 const rows:HistoryRow[]=Array.from({length:125},(_,i)=>({origin:'one_shot',source_kind:'task',occurrence_ref:{origin:'one_shot',id:'h'+i},source_ref:{kind:'task',id:taskApi.tasks[0].id},occurrence_at:'2026-10-24T09:00:00Z',occurrence_on:'2026-10-'+(24-Math.floor(i/45)),time_precision:'datetime',time_basis:'recorded_only',status:'sent',title:'Lần nhắc '+i,body:'Nội dung '+i+' tiếng Việt '.repeat(25),handled_at:null,is_private:false,can_open:true,can_handle:true}))
 let firstPageReads=0, writes=0, fail=true
 await page.route('**/api/reminders**',r=>r.fulfill({json:{items:[],has_more:false,registered_devices:0}}))
 await page.route('**/api/reminder-history**',async r=>{
  const url=new URL(r.request().url())
  if(r.request().method()==='GET'){
   const offset=Number(url.searchParams.get('cursor')||0);if(!offset)firstPageReads++
   const filtered=rows.filter(row=>url.searchParams.get('handled')!=='unhandled'||!row.handled_at)
   await r.fulfill({json:{items:filtered.slice(offset,offset+50),next_cursor:offset+50<filtered.length?String(offset+50):null,has_more:offset+50<filtered.length,private_notice:null}});return
  }
  writes++
  if(fail){await r.fulfill({status:503,json:{detail:'Synthetic ACK failure'}});return}
  const id=url.pathname.split('/').at(-2)!,row=rows.find(row=>row.occurrence_ref.id===id)!
  row.handled_at='2026-10-24T10:00:00Z';row.can_handle=false
  await r.fulfill({json:{occurrence_ref:row.occurrence_ref,handled:true,handled_at:row.handled_at}})
 })
 await page.goto('/?reminders=1');await page.getByRole('button',{name:'Lịch sử',exact:true}).click()
 const history=page.getByTestId('reminder-history'),panel=page.getByTestId('reminder-center')
 if(mode==='unhandled'){await history.getByRole('combobox',{name:'Trạng thái xử lý'}).click();await page.getByRole('option',{name:'Chưa xử lý',exact:true}).click()}
 await history.getByTestId('history-more').click();await expect(history.getByTestId('history-row')).toHaveCount(100)
 await history.getByTestId('history-more').click();await expect(history.getByTestId('history-row')).toHaveCount(125)
 const index=mode==='all'?80:44
 const row=history.locator('[data-occurrence="one_shot:h'+index+'"]'),next=history.locator('[data-occurrence="one_shot:h'+(index+1)+'"]')
 await row.locator('summary').click();await row.scrollIntoViewIfNeeded()
 await row.getByTestId('history-handle').click();await expect(history.getByText('Synthetic ACK failure')).toBeVisible()
 await expect(history.getByTestId('history-row')).toHaveCount(125);await expect(row.getByTestId('history-handle')).toBeEnabled()
 await expect(row.getByTestId('history-handle')).toBeFocused()
 fail=false
 await row.getByTestId('history-handle').scrollIntoViewIfNeeded()
 const before=await row.evaluate(el=>el.getBoundingClientRect().top),reads=firstPageReads
 await row.getByTestId('history-handle').click()
 if(mode==='all'){
  await expect(row.getByTestId('history-handle')).toBeDisabled()
  await expect(history.getByTestId('history-row')).toHaveCount(125)
  await expect(row.locator('details')).toHaveAttribute('open','')
 }else{await expect(row).toHaveCount(0);await expect(history.getByTestId('history-row')).toHaveCount(124)}
 const anchor=mode==='all'?row:next
 await expect.poll(async()=>Math.abs((await anchor.evaluate(el=>el.getBoundingClientRect().top))-before)).toBeLessThan(5)
 expect(await panel.evaluate(el=>el.scrollTop)).toBeGreaterThan(100)
 expect(firstPageReads-reads).toBeLessThanOrEqual(1);expect(writes).toBe(2)
 if(mode==='unhandled'){
  await history.locator('[data-occurrence="one_shot:h124"]').getByTestId('history-handle').click()
  await expect(history.locator('[data-occurrence="one_shot:h124"]')).toHaveCount(0)
  await expect(history.locator('[data-occurrence="one_shot:h123"]')).toBeInViewport()
 }
})

test('098 History lock purges private rows and rejects a late ACK cache resurrection',async({page,taskApi})=>{
 let release!:()=>void
 const hold=new Promise<void>(resolve=>{release=resolve})
 const row:HistoryRow={origin:'one_shot',source_kind:'task',occurrence_ref:{origin:'one_shot',id:'private098'},source_ref:{kind:'task',id:taskApi.tasks[0].id},occurrence_at:'2026-10-24T09:00:00Z',occurrence_on:'2026-10-24',time_precision:'datetime',time_basis:'recorded_only',status:'sent',title:'Synthetic private History 098',body:'Synthetic private body 098',handled_at:null,is_private:true,can_open:true,can_handle:true}
 await page.route('**/api/reminders**',r=>r.fulfill({json:{items:[],has_more:false,registered_devices:0}}))
 await page.route('**/api/reminder-history**',async route=>{
  if(route.request().method()==='GET'){await route.fulfill({json:{items:taskApi.privateUntil?[row]:[],next_cursor:null,has_more:false,private_notice:null}});return}
  await hold;await route.fulfill({json:{occurrence_ref:row.occurrence_ref,handled:true,handled_at:'2026-10-24T10:00:00Z'}})
 })
 await page.goto('/?reminders=1');await page.getByRole('button',{name:'Lịch sử',exact:true}).click()
 const history=page.getByTestId('reminder-history');await expect(history.getByTestId('history-row')).toHaveCount(1)
 await history.getByTestId('history-handle').click();await expect(history.getByTestId('history-handle')).toBeDisabled()
 await page.getByTestId('private-lock-now').evaluate((el:HTMLButtonElement)=>el.click())
 await expect(history.getByTestId('history-row')).toHaveCount(0)
 const response=page.waitForResponse(r=>r.url().endsWith('/private098/handled'))
 release();await response
 await expect(history).not.toContainText(row.title);await expect(history.getByTestId('history-row')).toHaveCount(0)
})

test('098 Note preview budgets and reader B retain full content, groups, icons and return context',async({page},info)=>{
 const long=Array.from({length:100},(_,i)=>'Dòng '+i+' tiếng Việt ế ữ ộ ằ 📚').join('\n')
 const item:Note={id:'n098',title:'Kế hoạch đọc sách',body_md:appendFutureReflection(long,long),is_private:false,pinned:false,created_at:'2026-10-26T00:00:00Z',updated_at:null,items:Array.from({length:15},(_,i)=>({id:'i'+i,content:i===2||i===3?'Mục ngắn '+i:long,position:i,is_completed:i%4===0}))}
 let moves=0
 await page.route('**/api/notes**',async route=>{
  const req=route.request()
  if(req.method()==='GET'){await route.fulfill({json:{items:Number(new URL(req.url()).searchParams.get('offset'))?[]:[item]}});return}
  if(req.url().endsWith('/move-to-top')){
   moves++;const target=req.url().split('/').at(-2)!,entry=item.items.find(i=>i.id===target)!,group=item.items.filter(i=>i.is_completed===entry.is_completed),ordered=[entry,...group.filter(i=>i.id!==target)];let n=0
   item.items=item.items.map(i=>i.is_completed===entry.is_completed?ordered[n++]:i).map((i,position)=>({...i,position}))
   await route.fulfill({json:item.items});return
  }
  await route.fulfill({status:404})
 })
 await page.goto('/');await page.getByRole('tab',{name:'Ghi chú',exact:true}).click()
 expect(await page.evaluate(async()=> (await document.fonts.load('16px "Nunito Variable"','Tiếng Việt ế ữ ộ ằ')).length)).toBeGreaterThan(0)
 const card=page.getByTestId('note-card')
 await expect(card.getByTestId('note-body-preview')).toHaveCSS('-webkit-line-clamp','6')
 await expect(card.getByTestId('note-reflection-box').locator('p').last()).toHaveCSS('-webkit-line-clamp','4')
 await expect(card.getByTestId('note-item-content').filter({visible:true})).toHaveCount(3)
 await expect(card.getByTestId('note-item-content').filter({visible:true}).first()).toHaveCSS('-webkit-line-clamp','4')
 expect(await card.getByTestId('note-item-content').filter({visible:true}).first().evaluate(el=>el.getBoundingClientRect().height<=parseFloat(getComputedStyle(el).lineHeight)*4+1)).toBe(true)
 await card.getByTestId('note-items-completed-toggle').click();await expect(card.locator('[data-note-item-id="i0"]')).toBeVisible()
 await card.getByTestId('note-expand').click();await card.getByTestId('note-expand').click()
 await expect(card.locator('[data-note-item-id="i0"]')).toBeHidden();await expect(card.getByTestId('note-item-content').filter({visible:true})).toHaveCount(3)
 await page.getByTestId('note-find').fill('đọc sách')
 const opener=card.getByTestId('note-open-full');await opener.scrollIntoViewIfNeeded()
 const beforeClickTop=await opener.evaluate(el=>el.getBoundingClientRect().top)
 await opener.evaluate(el=>el.addEventListener('pointerdown',()=>{(el as HTMLElement).dataset.pointerOriginTop=String(el.getBoundingClientRect().top)},{once:true}))
 await card.getByTestId('note-open-full').click();const reader=page.getByTestId('note-detail-dialog')
 const openerTop=Number(await opener.getAttribute('data-pointer-origin-top'))
 expect(Number.isFinite(openerTop)).toBe(true)
 expect((await reader.boundingBox())!.width).toBeGreaterThan(info.project.name==='desktop'?1200:380)
 expect(await reader.locator('[data-reader-section]').evaluateAll(els=>els.map(el=>el.getAttribute('data-reader-section')))).toEqual(['body','checklist','reflections'])
 await expect(reader.locator('[data-reader-section="body"]')).toContainText('Dòng 99')
 await page.screenshot({path:info.outputPath('reader-B-body.png')})
 await reader.getByRole('button',{name:/^Checklist /}).click()
 const first=reader.locator('[data-note-item-id="i1"]'),second=reader.locator('[data-note-item-id="i5"]')
 await expect(first.getByTestId('note-item-top')).toBeDisabled()
 expect(await second.getByRole('button').allTextContents()).toEqual(['','',''])
 await second.getByTestId('note-item-top').evaluate((el:HTMLButtonElement)=>{el.click();el.click()})
 await expect.poll(()=>moves).toBe(1)
 await expect(reader.getByTestId('note-item').first()).toHaveAttribute('data-note-item-id','i5')
 await expect(reader.locator('[data-note-item-id="i5"]').getByTestId('note-item-top')).toBeDisabled()
 await expect(reader.locator('[data-note-item-id="i5"]').getByTestId('note-item-edit')).toBeInViewport()
 expect(await reader.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true)
 await page.screenshot({path:info.outputPath('reader-B.png')})
 await reader.getByTestId('note-reader-back').click();await expect(reader).toBeHidden()
 await expect(page.getByTestId('note-find')).toHaveValue('đọc sách')
 await expect(card.getByTestId('note-open-full')).toBeFocused()
 console.log('098 return geometry',info.project.name,{beforeClickTop,pointerOriginTop:openerTop,...await opener.evaluate(el=>({actualTop:el.getBoundingClientRect().top,y:scrollY,maxY:document.documentElement.scrollHeight-innerHeight,height:document.documentElement.scrollHeight,viewport:innerHeight}))})
 await expect.poll(async()=>Math.abs((await opener.evaluate(el=>el.getBoundingClientRect().top))-openerTop)).toBeLessThan(5)
 await expect(opener).toBeInViewport()
})

test('098 shared Task title wraps, autogrows and retains Input Enter/paste/IME semantics',async({page,taskApi})=>{
 const original='ĐỀ CƯƠNG ế ữ ộ ằ 📚 '.repeat(30)+'A'.repeat(70)
 const task=taskApi.tasks[0];task.title=original
 await page.goto('/');const card=page.locator('[data-task-id="'+task.id+'"]')
 await card.getByTestId('task-edit').click()
 const title=page.getByTestId('task-title-input');await expect(title).toHaveValue(original)
 let writes=0;page.on('request',request=>{if(request.method()==='PATCH'&&new URL(request.url()).pathname.endsWith('/tasks/'+task.id))writes++})
 await title.fill('   ');await title.press('Enter');await expect(title).toBeVisible();expect(writes).toBe(0)
 await title.fill(original)
 expect((await title.boundingBox())!.height).toBeGreaterThan(60)
 expect(await title.evaluate(el=>el.scrollHeight<=el.clientHeight+2)).toBe(true)
 await title.fill('  Ghi chú 📚 ');await title.evaluate(el=>{const input=el as HTMLTextAreaElement;input.focus();input.setSelectionRange(2,2)})
 await title.evaluate(el=>{const input=el as HTMLTextAreaElement;input.setRangeText('A\r\nB',input.selectionStart,input.selectionEnd,'end');input.dispatchEvent(new Event('input',{bubbles:true}))})
 await expect(title).not.toHaveValue(/\n|\r/)
 await expect(title).toHaveValue('  ABGhi chú 📚 ')
 await title.evaluate(el=>{(el as HTMLTextAreaElement).style.fieldSizing='fixed'})
 await title.fill(original);expect(await title.evaluate(el=>el.scrollHeight<=el.clientHeight+2)).toBe(true)
 await title.fill('Tiêu đề IME')
 await title.dispatchEvent('compositionstart');await title.press('Enter');await expect(title).toBeVisible();await title.dispatchEvent('compositionend')
 await title.fill('Tiêu đề đã lưu');await title.press('Enter');await expect(title).toBeHidden()
 await expect.poll(()=>taskApi.tasks[0].title).toBe('Tiêu đề đã lưu')
})

test('098 month day and agenda edit use the shared wrapping title without rewriting legacy values',async({page,taskApi})=>{
 const task=taskApi.tasks[0],day=new Date(Date.now()+7*3600000).toISOString().slice(0,10)
 task.title='Dòng cũ\nđược giữ nguyên';task.due_precision='date';task.due_on=day;task.due_at=null
 await page.route('**/api/calendar/**',r=>r.fulfill({json:{items:[]}}))
 await page.goto('/');await page.getByRole('tab',{name:'Lịch',exact:true}).click()
 await page.locator('[data-testid="calendar-day-cell"][data-day="'+day+'"]').click({position:{x:5,y:5}})
 await page.getByTestId('calendar-day-task-edit-trigger').filter({hasText:'Dòng cũ'}).click()
 const title=page.getByTestId('task-title-input');await expect(title).toHaveValue('Dòng cũđược giữ nguyên')
 await page.getByLabel('Nội dung',{exact:true}).fill('Chỉ đổi body')
 await page.getByRole('button',{name:'Lưu thay đổi',exact:true}).click();await expect(title).toBeHidden()
 await expect.poll(()=>taskApi.tasks[0].title).toBe('Dòng cũ\nđược giữ nguyên')
 await page.keyboard.press('Escape')
 await page.getByTestId('calendar-mode-toggle-agenda').click()
 await page.getByTestId('calendar-agenda-task-edit-trigger').filter({hasText:'Dòng cũ'}).click()
 await title.fill('Tiêu đề lịch tự wrap '.repeat(20));expect((await title.boundingBox())!.height).toBeGreaterThan(60)
 await title.press('Enter');await expect(title).toBeHidden()
 await expect.poll(()=>taskApi.tasks[0].body_md).toBe('Chỉ đổi body')
})
