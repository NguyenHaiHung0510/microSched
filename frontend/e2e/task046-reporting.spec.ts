import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { test, expect } from './fixtures/tracker'

const shift = (month: string, delta: number) => {
  const [y,m] = month.split('-').map(Number)
  return new Date(Date.UTC(y,m-1+delta,1)).toISOString().slice(0,7)
}
const start = (month: string) => `${month}-01T00:00:00+07:00`
const expense = (month: string) => month === '2026-09' ? 642000 : month === '2026-08' ? 2480000 : month === '2026-07' ? 1820000 : 990000
function report(month: string, months: number, privateVisible: boolean, empty = false, signed = false) {
  const keys = Array.from({length: months}, (_,i) => shift(month,i-months+1))
  const value = (key: string) => empty ? 0 : signed && key === '2026-09' ? -142000 : expense(key)
  const total = keys.reduce((sum,key) => sum+value(key),0)
  const end = month === '2026-09' ? '2026-09-07T12:00:00+07:00' : start(shift(month,1))
  return {period_start: start(keys[0]), period_end: end, current_period_days: 6, prev_period_days: 31, prev_period_truncated: false, corrupted_entry_count: 0,
    report_months: months, previous_period_start: start(shift(keys[0],-months)), previous_period_end: start(keys[0]),
    f1_total:total,f2_current:total,f2_previous: keys.reduce((sum,key) => sum+value(shift(key,-months)),0),f5_net:-total,
    finance_months:keys.map(key => ({month:key,period_start:start(key),period_end:key===month?end:start(shift(key,1)),total:value(key)})),
    activity_month:month, activity_days:empty?[]:[{tracker_id:'rhythm-public',day:`${month}-01`,count:1},{tracker_id:'rhythm-public',day:`${month}-02`,count:2},...(privateVisible?[{tracker_id:'rhythm-private',day:`${month}-01`,count:1}]:[])],
    f3_groups:empty?[]:[{name:'Nhóm học tập mô phỏng',total,trackers:[{tracker_id:'rhythm-public',name:'Đọc sách',total}]}],f4_top:[],
    a2_gap:[],a3_counts:{week:3,month:5,year:70},a4_trend:{current_month:5,prev_avg:7,trend:'down'},
    f6:{monthly_burn:0,subscription_count:0,corrupted_subscription_count:0,upcoming:[]}}
}
async function capture(page: import('@playwright/test').Page, name: string, project: string) {
  if(process.env.CAPTURE_UI_046!=='1') return
  const directory=path.resolve('../output/task-046/screenshots'); mkdirSync(directory,{recursive:true})
  await page.evaluate(() => document.fonts.ready)
  const file=`${project}-${name}.png`, bytes=await page.screenshot({path:path.join(directory,file),animations:'disabled'})
  writeFileSync(path.join(directory,`${project}-${name}.json`),JSON.stringify({file,head:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),viewport:page.viewportSize(),capturedAt:new Date().toISOString(),md5:createHash('md5').update(bytes).digest('hex'),sha256:createHash('sha256').update(bytes).digest('hex')},null,2))
}

async function expectDayTargetGeometry(rhythm: import('@playwright/test').Locator) {
  const boxes = await rhythm.getByTestId('rhythm-day').evaluateAll(elements => elements.map(element => {
    const box = element.getBoundingClientRect()
    return { left: box.left, right: box.right, top: box.top, width: box.width, height: box.height }
  }))
  for (const box of boxes) {
    expect(box.width).toBeGreaterThanOrEqual(24)
    expect(box.height).toBeGreaterThanOrEqual(44)
  }
  for (let index = 1; index < boxes.length; index += 1) {
    if (Math.abs(boxes[index].top - boxes[index - 1].top) < 1) {
      expect(boxes[index].left - boxes[index - 1].right).toBeGreaterThanOrEqual(8)
    }
  }
}
test.beforeEach(async ({page,taskApi,trackerApi}) => {
  await page.clock.setFixedTime(new Date('2026-09-07T12:00:00+07:00'))
  taskApi.privateUntil='2026-09-07T12:36:00+07:00'
  trackerApi.groups=[]
  trackerApi.trackers=[{...trackerApi.trackers[0],id:'rhythm-public',name:'Đọc sách',group_id:null,is_private:false},
    {...trackerApi.trackers[0],id:'rhythm-private',name:'Nhịp riêng tư mô phỏng',group_id:null,is_private:true}]
  await page.route('**/api/tracker/trackers',route => route.fulfill({json:{items:trackerApi.trackers.filter(tracker => !tracker.is_private || Boolean(taskApi.privateUntil))}}))
})

test('absolute report controls load all supported windows and keep labels and colors honest',async({page,taskApi},info) => {
  const requests: number[]=[]
  await page.route('**/api/tracker/dashboard?*', route => {const query=new URL(route.request().url()).searchParams;const months=Number(query.get('months')??1);requests.push(months);return route.fulfill({json:report(query.get('month')??'2026-09',months,Boolean(taskApi.privateUntil))})})
  await page.goto('/');await page.getByRole('tab',{name:'Theo dõi'}).click()
  const overview=page.getByTestId('tracker-finance-overview')
  const controls=overview.getByRole('group',{name:'Khoảng báo cáo'})
  await expect(controls.getByRole('button',{name:'1 tháng',exact:true})).toHaveAttribute('aria-pressed','true')
  await expect(page.getByTestId('tracker-finance-total')).toContainText('642.000')
  const monthField=page.getByTestId('tracker-report-month')
  expect(await monthField.evaluate(el => el.getBoundingClientRect().top-el.parentElement!.querySelector('span')!.getBoundingClientRect().bottom)).toBeGreaterThanOrEqual(8)
  await page.getByTestId('tracker-open-report').click()
  await expect(page.getByTestId('finance-month-bar')).toHaveCount(2)
  await expect(page.getByTestId('dashboard-f2-compare')).toContainText('1.838.000')
  await capture(page,'finance-one-month',info.project.name)
  for(const months of [3,6,12]) {
    await controls.getByRole('button',{name:months===12?'1 năm':`${months} tháng`,exact:true}).click()
    await expect.poll(()=>requests.at(-1)).toBe(months)
    await expect(page.getByTestId('dashboard-f1-total')).toContainText(report('2026-09',months,true).f1_total.toLocaleString('vi-VN'))
    const table=page.getByTestId('finance-month-table')
    await expect(table.locator('tbody tr')).toHaveCount(months)
    if(months>=6) {
      await expect(page.getByTestId('finance-line-chart')).toBeVisible()
      await expect(page.getByTestId('finance-axis-label')).toHaveCount(months)
      const fontSizes=await page.getByTestId('finance-axis-label').evaluateAll(elements=>elements.map(el=>parseFloat(getComputedStyle(el).fontSize)))
      expect(fontSizes.every(size=>size>=12)).toBe(true)
    }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  }
  await page.getByTestId('dashboard-finance-comparison').scrollIntoViewIfNeeded()
  await capture(page,'finance-year',info.project.name)
  await monthField.fill('2026-08')
  await expect(page.getByTestId('dashboard-finance-comparison')).not.toContainText('chưa trọn tháng')
})

test('rhythm selection survives focus, changes month cleanly and hides private rows on lock',async({page,taskApi},info)=>{
  await page.route('**/api/tracker/dashboard?*',route=>{const q=new URL(route.request().url()).searchParams;return route.fulfill({json:report(q.get('month')??'2026-09',Number(q.get('months')??1),Boolean(taskApi.privateUntil))})})
  await page.goto('/');await page.getByRole('tab',{name:'Theo dõi'}).click();await page.getByTestId('tracker-open-report').click()
  const rhythm=page.getByTestId('tracker-rhythm')
  const day=rhythm.getByRole('button',{name:'Đọc sách, 02/09/2026: 2 lần ghi',exact:true})
  await day.focus();await page.keyboard.press('Enter')
  await expect(day).toBeFocused();await expect(page.getByTestId('rhythm-detail')).toContainText('2 lần ghi')
  await expectDayTargetGeometry(rhythm)
  const scroll = rhythm.getByTestId('rhythm-week-scroll')
  await scroll.evaluate(element => { element.scrollLeft = element.scrollWidth })
  const rightmost = await scroll.evaluate(element => {
    const button = element.querySelector('[role="row"]:nth-child(2) [role="cell"]:last-child button')!
    const target = button.getBoundingClientRect(), frame = element.getBoundingClientRect()
    return target.left >= frame.left && target.right <= frame.right + 1
  })
  expect(rightmost).toBe(true)
  await scroll.evaluate(element => { element.scrollLeft = 0 })
  await rhythm.scrollIntoViewIfNeeded();await capture(page,'rhythm-week',info.project.name)
  await rhythm.getByRole('button',{name:'Một tracker',exact:true}).click()
  await expect(rhythm.getByRole('button',{name:'Đọc sách, 08/09/2026: chưa tới',exact:true})).toBeDisabled()
  await expectDayTargetGeometry(rhythm)
  await capture(page,'rhythm-month',info.project.name)
  await page.getByTestId('tracker-report-month').fill('2026-08')
  await expect(page.getByTestId('rhythm-detail')).toContainText('Chọn một chấm')
  await expect(rhythm).not.toContainText('02/09/2026')
  await page.getByTestId('private-lock-now').click()
  await page.getByTestId('tracker-open-report').click()
  await expect(page.getByTestId('tracker-rhythm')).toBeVisible()
  await expect(page.getByTestId('tracker-rhythm')).not.toContainText('Nhịp riêng tư mô phỏng')
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})

test('empty and signed reports never invent bars or an activity completion rate',async({page,taskApi})=>{
  let empty=true
  await page.route('**/api/tracker/dashboard?*',route=>{const q=new URL(route.request().url()).searchParams;return route.fulfill({json:report(q.get('month')??'2026-09',Number(q.get('months')??1),Boolean(taskApi.privateUntil),empty,!empty)})})
  await page.goto('/');await page.getByRole('tab',{name:'Theo dõi'}).click();await page.getByTestId('tracker-open-report').click()
  await expect(page.getByTestId('dashboard-f1-total')).toContainText('0')
  await expect(page.getByTestId('rhythm-empty')).toBeVisible()
  const widths=await page.getByTestId('finance-month-bar').locator('[aria-hidden="true"] > span').evaluateAll(elements=>elements.map(el=>el.getBoundingClientRect().width))
  expect(widths.every(width=>width===0)).toBe(true)
  empty=false
  await page.getByTestId('tracker-report-month').fill('2026-08');await page.getByTestId('tracker-report-month').fill('2026-09')
  await expect(page.getByTestId('dashboard-f1-total')).toContainText('-142.000')
  await expect(page.getByTestId('dashboard-finance-comparison')).toContainText('Có số âm')
  await expect(page.getByTestId('tracker-rhythm')).not.toContainText('%')
})
