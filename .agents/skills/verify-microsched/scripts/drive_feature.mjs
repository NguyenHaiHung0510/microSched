/** Finite H14 browser proof. Main starts/stops runtime; each invocation owns a fresh receipt directory. */
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ORIGIN='http://127.0.0.1:5173';
const SHOWCASE_DESKTOP_ASSETS=new Set([
 "/showcase/vi/tasks-desktop.png",
 "/showcase/vi/notes-desktop.png",
 "/showcase/vi/calendar-desktop.png",
 "/showcase/vi/trackers-desktop.png",
 "/showcase/vi/spending-desktop.png",
 "/showcase/en/tasks-desktop.png",
 "/showcase/en/notes-desktop.png",
 "/showcase/en/calendar-desktop.png",
 "/showcase/en/trackers-desktop.png",
 "/showcase/en/spending-desktop.png",
]);
const ID='[0-9a-fA-F-]{36}';
export function requestAllowed(rawUrl,method,lane,source){
 let u,path;try{u=new URL(rawUrl);path=decodeURIComponent(u.pathname)}catch{return false}
 if(u.origin!==ORIGIN||u.protocol!=='http:'||u.username||u.password)return false;
 if(path.includes('\\')||path.split('/').some(x=>x==='..'||x==='.'))return false;
 const read=method==='GET'||method==='HEAD';
 // Read-only Vite modules/assets for this checkout; no general /@fs local-file permission.
 const modules=/^\/(?:src\/|node_modules\/\.vite\/deps\/).+\.(?:tsx?|jsx?|css|svg|png|webp|woff2?|map)$/.test(path);
 const assets=/^\/(?:brand|fonts)\/[a-zA-Z0-9_./-]+\.(?:svg|png|webp|woff2?)$/.test(path);
 const fonts=/^\/node_modules\/@fontsource-variable\/nunito\/files\/nunito-(?:latin|latin-ext|vietnamese)-wght-normal\.woff2$/.test(path);
 const fsRoot='/@fs/'+resolve(source,'frontend','node_modules').replaceAll('\\','/')+'/';
 const fsModule=path.startsWith(fsRoot)&&/\.(?:jsx?|css|woff2?|svg)$/.test(path);
 if(read&&(modules||assets||fonts||fsModule||(lane==='microsched'&&SHOWCASE_DESKTOP_ASSETS.has(path))||['/@vite/client','/node_modules/vite/dist/client/env.mjs','/@react-refresh','/microsched.svg','/favicon.ico','/manifest.webmanifest','/registerSW.js','/showcase/source-preview.png','/showcase/creator-preview.png'].includes(path)))return true;
 if(lane==='microsched')return read&&(path==='/home'||path==='/api/me');
 if(lane!=='mimi')return false;
 if(read&&['/','/auth/dev-session','/api/me','/api/tasks/timeline','/api/tasks','/api/notes','/api/calendar/events','/api/tracker/trackers','/api/reminders','/api/mimi/conversations','/api/mimi/conversations/current','/api/mimi/capabilities'].includes(path))return true;
 if(read&&new RegExp('^/api/mimi/conversations/'+ID+'(?:/context|/configuration)?$').test(path))return true;
 if(method==='POST'&&['/api/mimi/conversations','/auth/logout'].includes(path))return true;
 return method==='PATCH'&&new RegExp('^/api/mimi/conversations/'+ID+'$').test(path);
}

export function beginReceipt(options){
 const receipts=resolve(options.receipts);
 // Parent may already exist. The leaf must be new, so a retry cannot overwrite earlier evidence.
 mkdirSync(dirname(receipts),{recursive:true});mkdirSync(receipts);
 return {lane:options.lane,source:resolve(options.source),binding:resolve(options.binding),receipts,status:'RUNNING',phase:'preflight',started:new Date().toISOString(),actions:[],requests:[],blocked:[],disabledSockets:[],assertions:[],provider_calls:'Send/run/decision routes denied and backend provider disabled; no independent provider wire instrumentation.',cost:{tokens:'UNKNOWN',currency:'UNKNOWN',app_provider_budget:0}};
}
export function finishReceipt(receipt){
 receipt.finished=new Date().toISOString();receipt.request_count=receipt.requests.length;receipt.blocked_count=receipt.blocked.length;
 const path=join(receipt.receipts,'receipt.json');writeFileSync(path,JSON.stringify(receipt,null,2),{flag:'wx'});return path;
}
const screenshot=async(page,receipt,name)=>writeFileSync(join(receipt.receipts,name),await page.screenshot({fullPage:true}),{flag:'wx'});

export function preflight(options){
 if(!['microsched','mimi'].includes(options.lane))throw Error('Unknown lane');
 const helper=join(dirname(fileURLToPath(import.meta.url)),'h14_sandbox.py');
 const py=join(options.source,'backend','.venv','Scripts','python.exe');
 const call=(action)=>{
  const result=spawnSync(py,['-B',helper,'--source',options.source,'--binding',options.binding,'--lane',options.lane,action],{encoding:'utf8'});
  if(result.error)throw Error('Doctor executable unavailable: '+result.error.code);
  // Retain sanitized structured failure, not arbitrary process/env output.
  if(result.status!==0){const error=Error(action+' refused (exit '+result.status+')');const known=result.stderr.split(/\r?\n/).find(line=>line.startsWith('REFUSED: '));error.diagnostic={action,exit:result.status,refusal:known?.slice(0,600)??'Unclassified helper failure; Main preserves sanitized raw diagnostic before retry'};throw error;}
  return JSON.parse(result.stdout);
 };
 const doctor=call('status');
 for(const k of ['state_present','container_present','postgres_running','backend_running','backend_ready','frontend_running','frontend_ready'])if(doctor[k]!==true)throw Error('Doctor not ready: '+k);
 const fixture=call('verify');const bound=JSON.parse(readFileSync(options.binding,'utf8').replace(/^\uFEFF/,''));
 if(bound.lane!==options.lane||resolve(bound.source)!==resolve(options.source))throw Error('Browser source/lane binding mismatch');
 return {doctor,fixture,head:bound.head};
}

export async function runAttempt(options,operations){
 const receipt=beginReceipt(options); // Existing output is refused before any preflight or browser action.
 try{
  Object.assign(receipt,await operations.preflight(options));
  receipt.phase='drive';await operations.drive(receipt);receipt.status='WORKER_PASS';
 }catch(error){receipt.status=receipt.phase==='preflight'?'BLOCKED':'FAIL';receipt.error=String(error);if(error.diagnostic)receipt.preflight_diagnostic=error.diagnostic;}
 const path=finishReceipt(receipt);return {receipt,path};
}

async function drive(receipt){
 const require=createRequire(join(receipt.source,'frontend','package.json'));const {chromium,expect}=require('@playwright/test');
 let browser,context,page;const record=(action)=>receipt.actions.push({time:new Date().toISOString(),action});
 const assert=async(name,operation)=>{try{await operation();receipt.assertions.push({name,result:'PASS'})}catch(error){receipt.assertions.push({name,result:'FAIL',error:String(error)});throw error}};
 try{
  browser=await chromium.launch({headless:true});context=await browser.newContext({viewport:{width:1280,height:800},serviceWorkers:'block'});
  if(typeof context.routeWebSocket!=='function')throw Error('Browser capability lacks WebSocket blocking; do not drive');
  await context.routeWebSocket('**/*',ws=>{receipt.disabledSockets.push({protocol:'websocket',action:'closed before connection'});ws.close();});
  await context.route('**/*',async route=>{
   const req=route.request();let u;try{u=new URL(req.url())}catch{}
   const entry={method:req.method(),origin:u?.origin??'INVALID',path:u?.pathname??'INVALID'}; // Query/body/auth intentionally omitted.
   if(!requestAllowed(req.url(),req.method(),receipt.lane,receipt.source)){receipt.blocked.push(entry);await route.abort();return}
   receipt.requests.push(entry);await route.continue();
  });
  page=await context.newPage();
  const ensureConversationListOpen=async()=>{
   const toggle=page.getByRole('button',{name:/^(?:Thu gọn hội thoại|Hội thoại \(\d+\))$/});
   await expect(toggle).toBeVisible();
   const create=page.getByTestId('mimi-left-rail').getByRole('button',{name:'Cuộc trò chuyện mới',exact:true});
   if(await create.isVisible())record('Conversation list already open; preserve current rail state');
   else{
    record('Open closed conversation list');await page.getByRole('button',{name:/^Hội thoại \(\d+\)$/}).click();
    await expect(create).toBeVisible();
   }
   return create;
  };
  if(receipt.lane==='microsched'){
   const observeShowcase=async language=>{
    const paths=[...SHOWCASE_DESKTOP_ASSETS].filter(path=>path.startsWith('/showcase/'+language+'/'));
    await page.waitForFunction(expected=>expected.every(path=>[...document.images].some(img=>new URL(img.currentSrc||img.src).pathname===path&&img.complete&&img.naturalWidth>0)),paths);
    const images=await page.locator('.public-showcase-stage img').evaluateAll(nodes=>nodes.map(img=>({path:new URL(img.currentSrc||img.src).pathname,complete:img.complete,width:img.naturalWidth,height:img.naturalHeight})));
    if(images.length!==paths.length||images.some(img=>!paths.includes(img.path)||!img.complete||img.width===0||img.height===0))throw Error('Showcase image decode incomplete: '+language);
    (receipt.showcase_assets??=[]).push({language,images});record('Showcase '+language+' desktop images decoded: '+images.length);
   };
   record('Open public Vietnamese homepage');await page.goto(ORIGIN+'/home?lang=vi');
   await assert('guest login link visible',()=>expect(page.getByTestId('login-link')).toBeVisible());
   await observeShowcase('vi');
   const initial=await page.locator('#public-title').innerText();await screenshot(page,receipt,'before.png');
   record('Select English');await page.getByRole('button',{name:'English',exact:true}).click();
   await assert('English changed hero text',()=>expect(page.locator('#public-title')).not.toHaveText(initial));
   await observeShowcase('en');
   await assert('Vietnamese switch reachable',()=>expect(page.getByRole('button',{name:'Tiếng Việt',exact:true})).toBeVisible());
   record('Select Tiếng Việt');await page.getByRole('button',{name:'Tiếng Việt',exact:true}).click();
   await assert('Vietnamese hero restored',()=>expect(page.locator('#public-title')).toHaveText(initial));
   await observeShowcase('vi');
   const href=await page.getByTestId('login-link').getAttribute('href');if(!href?.startsWith('/auth/'))throw Error('Unexpected login href');
   receipt.assertions.push({name:'relative login destination',result:'PASS',href});
   await assert('guest sees no application tabs',()=>expect(page.getByRole('tab')).toHaveCount(0));
  }else{
   record('Synthetic local login');await page.goto(ORIGIN+'/auth/dev-session');
   record('Open Mimi and ensure conversation list');await page.getByRole('tab',{name:'Mimi',exact:true}).click();
   const create=await ensureConversationListOpen();
   const creation=page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname==='/api/mimi/conversations');
   record('Create STANDARD conversation');await create.click();
   const createdResponse=await creation;if(!createdResponse.ok())throw Error('Conversation creation failed');
   const created=await createdResponse.json();if(created.sensitivity!=='standard'||typeof created.title!=='string')throw Error('Expected new STANDARD conversation metadata');
   const title='H14 synthetic conversation '+created.id;
   receipt.created_conversation={id:created.id,sensitivity:created.sensitivity,title};
   await assert('new conversation composer visible',()=>expect(page.getByTestId('mimi-input')).toBeVisible());await screenshot(page,receipt,'before.png');
   record('Rename newly created conversation from its actual menu');await page.getByTestId('mimi-left-rail').getByRole('button',{name:'Tùy chọn '+created.title,exact:true}).click();await page.getByRole('menuitem',{name:'Đổi tên',exact:true}).click();
   await page.getByRole('textbox',{name:'Tên hội thoại',exact:true}).fill(title);await page.getByRole('button',{name:'Lưu tên',exact:true}).click();
   await assert('renamed title visible',()=>expect(page.getByTestId('mimi-left-rail').getByText(title,{exact:true})).toBeVisible());
   record('Reload and ensure conversation history open');await page.reload();await page.getByRole('tab',{name:'Mimi',exact:true}).click();await ensureConversationListOpen();
   await assert('metadata persisted through reload',()=>expect(page.getByTestId('mimi-left-rail').getByText(title,{exact:true})).toBeVisible());await page.getByTestId('mimi-left-rail').getByText(title,{exact:true}).click();
   await assert('conversation reopens',()=>expect(page.getByTestId('mimi-input')).toBeVisible());
  }
  if(receipt.blocked.length)throw Error('Forbidden request attempted; inspect canonical receipt');
  receipt.viewport=await page.evaluate(()=>({width:innerWidth,height:innerHeight}));await screenshot(page,receipt,'after.png');record('Proof complete');
 }catch(error){if(page)await screenshot(page,receipt,'failure.png').catch(()=>{});throw error}
 finally{
  // A synthetic authenticated attempt is logged out even if its assertions fail; then close only owned context.
  let cleanupError;
  if(page&&receipt.lane==='mimi')try{
   const status=await page.evaluate(async()=>{const response=await fetch('/auth/logout',{method:'POST'});return response.status});
   if(status<200||status>=400)throw Error('Synthetic logout did not succeed');record('Synthetic app logout observed');
  }catch(error){receipt.logout_error=String(error);cleanupError=error}
  if(context)await context.close();if(browser)await browser.close();record('Owned isolated context closed; Main exact-owner runtime stop required');
  if(cleanupError)throw cleanupError;
 }
}

async function main(){
 const args=process.argv.slice(2);if(args.includes('--help')){console.log('node drive_feature.mjs --source SOURCE --binding BINDING --lane microsched|mimi --receipts FRESH_PRIVATE_RUN_DIRECTORY');return}
 const get=k=>{const i=args.indexOf('--'+k);if(i<0||!args[i+1])throw Error('Required --'+k);return args[i+1]};
 const result=await runAttempt({source:resolve(get('source')),binding:resolve(get('binding')),lane:get('lane'),receipts:resolve(get('receipts'))},{preflight,drive});
 console.log(JSON.stringify({status:result.receipt.status,assertions:result.receipt.assertions.length,receipt:result.path,runtime_cleanup:'Main exact-owner stop required; evidence retained'}));
 if(result.receipt.status!=='WORKER_PASS')process.exitCode=1;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)main().catch(error=>{console.error('REFUSED: '+String(error));process.exitCode=2});
