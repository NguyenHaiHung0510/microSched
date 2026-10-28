/** Reusable direct Playwright primitives. Builder smoke is not independent QA. */
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
const sourceRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..')
const require=createRequire(path.join(sourceRoot,'frontend/package.json'))
const {chromium,expect}=require('@playwright/test')
const version=require('@playwright/test/package.json').version
export const DEFAULT_ORIGIN='http://127.0.0.1:4180'
function localOrigin(origin) {
  const url=new URL(origin)
  if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.port!=='4180')throw new Error('Only own R6b097 loopback preview4180')
  return url.origin
}
export async function uniqueAttempt(outputRoot,label='attempt') {
  if(!path.isAbsolute(outputRoot)||!/^[a-z0-9-]+$/i.test(label))throw new Error('Explicit absolute output root and safe label required')
  const resolved=path.resolve(outputRoot)
  const base=path.resolve(sourceRoot,'../../harness-reports/mimi-qa-2026-oct-19-owner296/dev-2026-oct-22')
  const local=path.join(sourceRoot,'.local','r6b-097')
  if(![base,local].some(parent=>resolved===parent||resolved.startsWith(parent+path.sep)))throw new Error('Output outside approved own receipt roots')
  await fs.mkdir(resolved,{recursive:true})
  const folder=path.join(resolved,new Date().toISOString().replace(/[:.]/g,'-')+'-'+label+'-'+randomUUID().slice(0,8))
  await fs.mkdir(folder)
  return folder
}
export async function createOwnedContext({origin=DEFAULT_ORIGIN,viewport={width:390,height:844},touch=false}={}) {
  origin=localOrigin(origin)
  if(version!=='1.62.1')throw new Error('Reviewed Playwright1.62.1 required; no CLI/cache repair')
  const browser=await chromium.launch({headless:true})
  const context=await browser.newContext({viewport,hasTouch:touch,isMobile:touch,serviceWorkers:'allow'})
  await context.route('**/*',route=>{
    const url=new URL(route.request().url())
    if(url.protocol==='http:'&&url.hostname==='127.0.0.1'&&['4180','8008'].includes(url.port))return route.continue()
    return route.abort('blockedbyclient')
  })
  return {browser,context,origin,version,executable:chromium.executablePath()}
}
export async function loginSynthetic(page,origin=DEFAULT_ORIGIN) {
  origin=localOrigin(origin)
  await page.goto(origin+'/auth/dev-session',{waitUntil:'domcontentloaded'})
  await page.waitForURL(origin+'/',{timeout:20000})
  const session=await page.evaluate(async()=>{const r=await fetch('/api/me');return {status:r.status,data:await r.json()}})
  if(session.status!==200||session.data.email!=='owner@test.local')throw new Error('Post-selection synthetic role mismatch')
  return {role:'synthetic-owner',authenticated:true}
}
export async function waitForController(page) {
  await page.evaluate(async()=>{await navigator.serviceWorker.ready})
  await page.waitForFunction(()=>!!navigator.serviceWorker.controller,{timeout:20000})
}
export async function collectQueue(page) {
  return page.evaluate(async()=>{
    const name='microsched-outbox-v1'
    const databases=await indexedDB.databases()
    if(!databases.some(d=>d.name===name))return {exists:false,rows:[]}
    return await new Promise((resolve,reject)=>{
      const open=indexedDB.open(name)
      open.onupgradeneeded=()=>{open.transaction.abort();reject(new Error('Unexpected schema create'))}
      open.onerror=()=>reject(open.error)
      open.onsuccess=()=>{
        const db=open.result
        if(!db.objectStoreNames.contains('rows')){db.close();resolve({exists:true,unsupported:true,rows:[]});return}
        const tx=db.transaction('rows','readonly'),request=tx.objectStore('rows').getAll()
        let rows=[]
        request.onsuccess=()=>{rows=request.result.map(row=>({
          id:row.id,operation_id:row.operation_id,version:row.version,kind:row.kind,principal:row.principal,
          entity:row.entity,parent:row.parent,aggregate:row.aggregate,predecessor:row.predecessor,dependency:row.dependency,
          state:row.state,attempted:row.attempted,attempt:row.attempt,next_due:row.next_due,
          requires_private:row.requires_private,digest:row.digest,envelope_digest:row.envelope_digest,byte_length:row.byte_length,
        }))}
        tx.oncomplete=()=>{db.close();resolve({exists:true,rows})}
        tx.onabort=()=>{db.close();reject(tx.error)}
      }
    })
  })
}
/** Poll the durable store from Node; do not infer ACK from a transient DOM state. */
export async function waitForQueueCount(page,count,{timeout=40000}={}) {
  if(!Number.isInteger(count)||count<0||timeout<1||timeout>120000)throw new Error('Finite queue count/timeout required')
  await expect.poll(async()=>{const state=await collectQueue(page);return state.exists&&!state.unsupported?state.rows.length:-1},{timeout}).toBe(count)
  return collectQueue(page)
}
export async function readCanonical(page,path) {
  if(!/^\/api\/(?:tasks(?:\/[0-9a-f-]+)?|tracker\/entries(?:\?[a-z0-9_=&%:.+-]+)?|readyz)$/.test(path))throw new Error('Only scoped canonical GET paths')
  return page.evaluate(async path=>{const r=await fetch(path);return {status:r.status,body:await r.json()}},path)
}
/** Context scope includes API traffic initiated after a production SW reload. No bodies/cookies. */
export function captureWire(context) {
  const requests=[],responses=[],failures=[]
  const allowed=url=>/^\/api\/(?:tasks|tracker\/entries|readyz|me)(?:[/?]|$)/.test(new URL(url).pathname)
  const request=r=>{if(allowed(r.url()))requests.push({method:r.method(),path:new URL(r.url()).pathname,at:Date.now()})}
  const response=r=>{if(allowed(r.url()))responses.push({method:r.request().method(),path:new URL(r.url()).pathname,status:r.status(),at:Date.now()})}
  const failure=r=>{if(allowed(r.url()))failures.push({method:r.method(),path:new URL(r.url()).pathname,error:r.failure()?.errorText,at:Date.now()})}
  context.on('request',request);context.on('response',response);context.on('requestfailed',failure)
  return {requests,responses,failures,stop(){context.off('request',request);context.off('response',response);context.off('requestfailed',failure)}}
}
export async function collectPwa(page) {
  return page.evaluate(async()=>{
    const registrations=await navigator.serviceWorker.getRegistrations()
    return {url:location.origin,viewport:{width:innerWidth,height:innerHeight},controller:navigator.serviceWorker.controller?.scriptURL??null,online:navigator.onLine,
      registrations:registrations.map(r=>({scope:r.scope,active:r.active?.state??null,waiting:r.waiting?.state??null})),
      cache_names:await caches.keys(),databases:await indexedDB.databases(),
      ready:await fetch('/api/readyz').then(r=>r.json()).catch(()=>null)}
  })
}
export async function nativeTouchDrag(page,start,end,steps=8) {
  if(!Number.isInteger(steps)||steps<1||steps>20)throw new Error('Finite gesture steps')
  const session=await page.context().newCDPSession(page)
  try {
    await session.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:start.x,y:start.y,id:1}]})
    for(let i=1;i<=steps;i++){
      await session.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:start.x+(end.x-start.x)*i/steps,y:start.y+(end.y-start.y)*i/steps,id:1}]})
      await page.waitForTimeout(16)
    }
    await session.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
  } finally {await session.detach()}
}
export async function saveState(page,folder,label='state') {
  if(!/^[a-z0-9-]+$/i.test(label))throw new Error('Unsafe label')
  const suffix=randomUUID().slice(0,8)
  await page.screenshot({path:path.join(folder,label+'-'+suffix+'.png'),fullPage:false})
  const result={pwa:await collectPwa(page),queue:await collectQueue(page)}
  await fs.writeFile(path.join(folder,label+'-'+suffix+'.json'),JSON.stringify(result,null,2))
  return result
}
export async function closeOwned({browser,context},page) {
  try {
    if(page&&!page.isClosed()&&page.url().startsWith(DEFAULT_ORIGIN)) {
      await page.evaluate(async()=>{await fetch('/auth/logout',{method:'POST'})})
    }
  } finally {await context.close();await browser.close()}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const args=process.argv.slice(2)
  const output=args[args.indexOf('--output-root')+1]
  if(!args.includes('--output-root')||!output)throw new Error('--output-root absolute path required')
  const folder=await uniqueAttempt(output,'readiness')
  let owned,page
  try {
    owned=await createOwnedContext()
    page=await owned.context.newPage()
    const role=await loginSynthetic(page,owned.origin)
    await waitForController(page)
    const state=await saveState(page,folder,'readiness')
    await fs.writeFile(path.join(folder,'receipt.json'),JSON.stringify({role,version,executable:owned.executable,folder,state},null,2))
    process.stdout.write(JSON.stringify({folder,role:role.role,playwright:version,controlled:!!state.pwa.controller})+'\n')
  } finally {if(owned)await closeOwned(owned,page)}
}
