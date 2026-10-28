import type { QueryClient } from '@tanstack/react-query'
import { ApiError, apiRequest, UnauthenticatedError } from '@/api'
import { uuidv7 } from '@/lib/uuidv7'
import { byOrder, db, removeAndSplice, semanticTree } from './store'
import { canonical, decode, hash, KINDS, retryDelay, route, TOMBSTONES, validatePayload, type Command, type Fields, type Kind } from './protocol'
import { offlineBootstrap, purgePublicCache, restorePublicQueries, saveBootstrap } from './public-cache'
import type { BootstrapSession } from './types'
import { maskPrivateQueries } from './private-visibility'
import { fundingReference, needsFunding, withoutFunding } from './funding'

type Context = {principal:string;verified:boolean;expires:number;privateUntil:number}
export type Snapshot = {rows:Command[];context:Context;error:string;capability:string;reconciling:string[];revision:number;admitting:number;authRequired:boolean}
let context:Context = {principal:'',verified:false,expires:0,privateUntil:0}
let snapshot:Snapshot = {rows:[],context,error:'',capability:'Đang kiểm tra',reconciling:[],revision:0,admitting:0,authRequired:false}
let client:QueryClient | undefined, timer:ReturnType<typeof setTimeout> | undefined, privateTimer:ReturnType<typeof setTimeout> | undefined
let authHeld = false
let authEpoch = 0, privateEpoch = 0, lockRequested = false
let capabilityAttempt = 0
let generation = 0, checkedGeneration = -1, capable = false, started = false, running = false
let legacy = false, channel:BroadcastChannel | undefined
let fundingCapable = false
const listeners = new Set<() => void>()
const confirmed = new Map<string,Fields>()
const cancelled = new Map<string,Command[]>()
let admitting = 0
const reconciling = new Map<string,Command[]>()
export const getSnapshot = () => snapshot
export const subscribe = (fn:() => void) => { listeners.add(fn); return () => listeners.delete(fn) }
export const unlocked = () => context.privateUntil > Date.now()
function publish(patch:Partial<Snapshot> = {}) {
  snapshot = {...snapshot,...patch,context:{...context},reconciling:[...reconciling.keys()],revision:snapshot.revision+1}
  for (const fn of listeners) fn()
}
async function refresh() {
  try {
    const raw = (await db.rows.toArray()).sort(byOrder)
    if(raw.some(row => !row.principal))legacy=true
    const rows = await Promise.all(raw.map(async row => {
      try { await decode(row); return row }
      catch { return {...row,kind:KINDS.includes(row.kind)?row.kind:'task.update',payload:'{}',
        requires_private:true,invalid:true,state:'held',reason:'Định dạng/toàn vẹn cần kiểm tra'} as Command }
    }))
    publish({rows,error:''})
  }
  catch { publish({error:'Chưa đọc được bộ nhớ cục bộ. Chưa lưu; giữ nguyên nội dung.'}) }
}
async function changed() { await refresh(); channel?.postMessage({type:'rows'}); wake() }

function remember(value:unknown) {
  if (Array.isArray(value)) { for (const row of value) remember(row); return }
  if (!value || typeof value !== 'object') return
  const row = value as Fields
  if (typeof row.id === 'string') {
    const task = 'due_precision' in row && Array.isArray(row.items)
    const tracker = 'input_mode' in row && 'is_private' in row
    const entry = 'tracker_id' in row && 'occurred_at' in row
    if (task || tracker || entry) {
      const hidden = row.is_private === true || entry && confirmed.get('tracker:'+row.tracker_id)?.is_private !== false
      if (!hidden || unlocked()) confirmed.set((task?'task:':tracker?'tracker:':'entry:')+row.id,row)
      if (task && Array.isArray(row.items) && (!hidden || unlocked()))
        for (const child of row.items as Fields[]) confirmed.set('item:'+child.id,{...child,task_id:row.id})
    }
  }
  if (Array.isArray(row.items)) for (const item of row.items) remember(item)
}
export function cancelledParent(id:string):string|undefined { return cancelled.get(id)?.[0]?.parent }
export function known(type:'task'|'tracker'|'entry'|'item',id:string):Fields | undefined {
  return confirmed.get(type+':'+id)
}
export function effectivePrivate(row:Pick<Command,'kind'|'parent'|'requires_private'> & Partial<Pick<Command,'payload'>>):boolean {
  const parent = known(row.kind.startsWith('entry.')?'tracker':'task',row.parent)
  const pendingParent = snapshot.rows.find(r => r.kind==='task.create' && r.entity===row.parent && r.principal===context.principal)
  const ref = row.payload ? fundingReference({...row,payload:row.payload}) : null
  const source = ref ? known('entry',ref) : undefined
  const sourceCreate = ref ? snapshot.rows.find(r => r.kind==='entry.create' && r.entity===ref && r.principal===context.principal) : undefined
  const sourceParent = known('tracker',String(source?.tracker_id??sourceCreate?.parent??''))
  return row.requires_private || Boolean(ref && sourceParent?.is_private !== false) || (parent ? parent.is_private !== false : row.kind==='task.create' ? false : !pendingParent)
}
export function visibleCommands():Command[] {
  return [...snapshot.rows,...[...reconciling.values()].flat()].filter(row =>
    !row.invalid && row.state!=='held' && row.principal === context.principal && (!effectivePrivate(row) || unlocked()))
}
export function lockLocal(broadcast = true) {
  privateEpoch++
  context.privateUntil = 0
  for (const [id,rows] of cancelled) if (rows.some(r => r.requires_private)) cancelled.delete(id)
  for (const [key,row] of confirmed) if (row.is_private !== false &&
    (!key.startsWith('entry:') || confirmed.get('tracker:'+row.tracker_id)?.is_private !== false)) confirmed.delete(key)
  for (const [key,row] of confirmed) if (key.startsWith('entry:')) confirmed.set(key,withoutFunding(row))
  for (const [aggregate,rows] of reconciling) if (rows.some(effectivePrivate)) reconciling.delete(aggregate)
  if (client) maskPrivateQueries(client)
  window.dispatchEvent(new Event('microsched:visibility'))
  void purgePublicCache(true).catch(() => {})
  if (broadcast) channel?.postMessage({type:'lock',pending:lockRequested})
  publish()
}
export async function bindSession(session:BootstrapSession, expectedEpoch = authEpoch, expectedPrivateEpoch = privateEpoch):Promise<void> {
  const previous = context.principal, wasVerified = context.verified
  const principal = session.offline_bootstrap ? session.principal! : await hash(session.email.trim().toLowerCase())
  if(expectedEpoch !== authEpoch) throw new UnauthenticatedError('Session generation changed')
  if(previous && previous!==principal) {
    authEpoch++; expectedEpoch++
    channel?.postMessage({type:'principal',principal})
  }
  if (!session.offline_bootstrap) await saveBootstrap(session,() => expectedEpoch===authEpoch).catch(() => {})
  if(expectedEpoch !== authEpoch) throw new UnauthenticatedError('Session generation changed')
  if (previous && previous !== principal) {
    confirmed.clear(); cancelled.clear(); reconciling.clear()
    client?.removeQueries({predicate:q => q.queryKey[0]!=='session'})
  }
  context = {principal,verified:!session.offline_bootstrap,expires:Date.parse(session.expires_at),
    privateUntil:session.offline_bootstrap || lockRequested || expectedPrivateEpoch!==privateEpoch?0:Date.parse(session.private_until??'')||0}
  if(context.verified)authHeld=false
  if(!unlocked())context.privateUntil=0
  clearTimeout(privateTimer)
  if (unlocked()) privateTimer = setTimeout(() => lockLocal(),Math.max(0,context.privateUntil-Date.now()))
  if(previous!==principal || !wasVerified && context.verified){ checkedGeneration=-1;capable=false }
  publish({authRequired:!context.verified && authHeld});wake()
}
export async function sessionRequest():Promise<BootstrapSession> {
  const epoch = authEpoch, visibility = privateEpoch
  try {
    const session = await apiRequest<BootstrapSession>('/api/me')
    await bindSession(session,epoch,visibility)
    return {...session,private_until:unlocked()?new Date(context.privateUntil).toISOString():null}
  } catch (error) {
    if (error instanceof UnauthenticatedError) {
      context.verified = false; lockLocal(); await purgePublicCache().catch(() => {}); throw error
    }
    if (error instanceof ApiError) throw error
    const fallback = await offlineBootstrap().catch(() => null)
    if (!fallback || epoch!==authEpoch) throw error
    await bindSession(fallback,epoch)
    return fallback
  }
}
export async function logoutBoundary() {
  authEpoch++;authHeld=true
  context = {principal:'',verified:false,expires:0,privateUntil:0}
  confirmed.clear();cancelled.clear();reconciling.clear();lockLocal();await purgePublicCache().catch(() => {})
}
async function inspectLegacy():Promise<boolean> {
  const names = await indexedDB.databases()
  return names.some(d => /outbox/i.test(d.name??'') && d.name !== db.name)
}
export async function startOutbox(queryClient:QueryClient):Promise<void> {
  if (started) return
  started = true; client = queryClient
  try {
    legacy = await inspectLegacy()
    await db.open()
    const bootstrap = await offlineBootstrap()
    if (bootstrap) await bindSession(bootstrap)
    await restorePublicQueries(client)
    for (const q of client.getQueryCache().getAll()) remember(q.state.data)
    client.getQueryCache().subscribe(event => {
      if (event.type === 'updated' && event.action.type === 'success') remember(event.query.state.data)
    })
    if ('BroadcastChannel' in window) {
      channel = new BroadcastChannel('microsched-outbox-v1')
      channel.onmessage = event => {
        if (event.data?.type === 'principal' && event.data.principal!==context.principal) {
          authEpoch++;generation++;capable=false;context.verified=false;authHeld=true
          lockLocal(false);confirmed.clear();cancelled.clear()
          client?.removeQueries({predicate:q => q.queryKey[0]!=='session'})
          void client?.invalidateQueries({queryKey:['session']})
          publish({capability:'Phiên đã đổi; cần xác minh',authRequired:true})
        } else if (event.data?.type === 'lock') { lockRequested=event.data.pending===true;lockLocal(false) }
        else void refresh().then(wake)
      }
    }
    window.addEventListener('microsched:api',event => {
      const {path,body} = (event as CustomEvent<{path:string;body:unknown}>).detail
      if(path==='/api/tracker/trackers' && body && typeof body==='object' && 'items' in body && Array.isArray(body.items)) {
        const ids=new Set(body.items.map((row:Fields) => String(row.id)))
        for(const [key,row] of confirmed)
          if(key.startsWith('tracker:') && !ids.has(String(row.id)) || key.startsWith('entry:') && !ids.has(String(row.tracker_id))) confirmed.delete(key)
      }
      if (path.startsWith('/api/tasks') || path.startsWith('/api/tracker/')) remember(body)
      if (path === '/api/private/lock') { lockRequested=false;lockLocal() }
      if (path === '/api/private/unlock') { lockRequested=false;privateEpoch++;checkedGeneration=-1; wake() }
    })
    window.addEventListener('microsched:auth-lost',() => { authEpoch++;authHeld=true;context.verified=false;capable=false;lockLocal();void purgePublicCache().catch(() => {});publish({capability:'Cần đăng nhập lại',authRequired:true}) })
    window.addEventListener('microsched:private-lock',event => {
      if ((event as CustomEvent<{requested?:boolean}>).detail?.requested) lockRequested=true
      lockLocal()
    })
    window.addEventListener('offline',() => { generation++; capable=false; context.verified=false; publish({capability:'Chờ kết nối'}) })
    window.addEventListener('online',() => { generation++; wake() })
    window.addEventListener('focus',() => { if(context.privateUntil && !unlocked())lockLocal();wake() })
    window.addEventListener('pageshow',() => wake())
    document.addEventListener('visibilitychange',() => { if (!document.hidden) wake() })
    await refresh()
    publish({capability:legacy?'Có dữ liệu hàng đợi cũ cần kiểm tra':'Đang kiểm tra'})
  } catch { publish({error:'Bộ nhớ cục bộ chưa sẵn sàng. Giữ nội dung; chưa gửi thay thế qua mạng.'}) }
}
function createdEntities(row:Command):string[] {
  if (!row.kind.endsWith('.create')) return []
  const body = JSON.parse(row.payload) as Fields
  return [row.entity,...(row.kind==='task.create'?body.item_ids as string[]:[])]
}
export async function admit(kind:Kind,entity:string,parent:string,body:Fields):Promise<Command> {
  admitting++;publish({admitting})
  try { return await admitIntent(kind,entity,parent,body) }
  catch(error) { throw error instanceof ApiError ? error : new ApiError(0,error instanceof Error&&error.name==='Error'?error.message:'Chưa lưu được vào bộ nhớ cục bộ. Nội dung vẫn được giữ; hãy thử lại.') }
  finally { admitting--;publish({admitting}) }
}
async function admitIntent(kind:Kind,entity:string,parent:string,body:Fields):Promise<Command> {
  if (authHeld || !context.principal || !Number.isFinite(context.expires) || context.expires<=Date.now()) throw new Error('Cần phiên đăng nhập đã xác minh; nội dung chưa lưu.')
  if (legacy) throw new Error('Hàng đợi cũ đang giữ. Giữ nội dung để kiểm tra; chưa lưu lệnh mới.')
  const owner = context.principal
  validatePayload(kind,entity,parent,body)
  const payload = canonical(body), digest = await hash(payload)
  const aggregate = kind.startsWith('entry.')?'tracker:'+parent:'task:'+parent
  const id=uuidv7()
  const envelope_digest=await hash(canonical({version:1,id,principal:owner,kind,entity,parent,aggregate,payload}))
  let admitted:Command | undefined
  try {
    await db.transaction('rw',db.rows,async () => {
      if (context.principal!==owner) throw new Error('Phiên đã đổi')
      const all = (await db.rows.where('principal').equals(owner).toArray()).sort(byOrder)
      const root = all.find(r => r.kind.endsWith('.create') && createdEntities(r).includes(entity))
      const undoTarget = kind.endsWith('.delete') ? root : kind.endsWith('.restore')
        ? [...all].reverse().find(r => r.entity===entity && r.kind.endsWith('.delete')) : undefined
      const current = known(kind.startsWith('entry.')?'tracker':'task',parent)
      const fundingId = typeof body.funding_entry_id === 'string' ? body.funding_entry_id : null
      const fundingCreator = fundingId ? all.find(r => r.kind==='entry.create' && r.entity===fundingId) : undefined
      const source = fundingId ? known('entry',fundingId) : undefined
      const sourceTracker = fundingId ? known('tracker',String(source?.tracker_id??fundingCreator?.parent??'')) : undefined
      if (fundingId && (!sourceTracker || sourceTracker.direction!=='in' || !source && !fundingCreator)) throw new Error('Chưa xác minh nguồn thu. Giữ nội dung và kết nối để chọn lại.')
      if (kind==='entry.delete' && all.some(r => fundingReference(r)===entity)) throw new Error('Khoản chi đang chờ còn gắn nguồn này. Đợi lưu hoặc bỏ liên kết trước khi xoá nguồn thu.')
      const remembered = kind.endsWith('.restore') ? cancelled.get(entity) : undefined
      const requiresPrivate = remembered?.some(r => r.requires_private) ?? (Boolean(fundingId && sourceTracker?.is_private !== false) || body.is_private === true || (kind==='task.create' ? false : current?.is_private !== false &&
        !all.some(r => r.kind==='task.create' && r.entity===parent && !r.requires_private)) ||
        all.some(r => r.aggregate===aggregate && r.requires_private))
      if (requiresPrivate && !unlocked()) throw new Error('Cần mở khoá riêng tư; nội dung chưa lưu.')
      if (requiresPrivate && (!navigator.onLine || !context.verified))
        throw new Error('Cần kết nối và phiên đã xác minh để lưu thay đổi riêng tư; nội dung chưa lưu.')

      if (remembered) {
        const remapped = new Map(remembered.map(r => [r.id,r.id]))
        let predecessor = [...all].reverse().find(r => r.aggregate===aggregate)?.id??null
        for (const original of remembered.sort(byOrder)) {
          const restored:Command = {...original,id:remapped.get(original.id)!,operation_id:undefined,
            expires_at:context.expires,predecessor,dependency:original.dependency?remapped.get(original.dependency)??null:null,
            state:'pending',attempted:false,attempt:0,next_due:0,reason:''}
          restored.operation_id = await db.rows.add(restored)
          predecessor = restored.id
          admitted ??= restored
        }
        cancelled.delete(entity)
        return
      }
      if (undoTarget) {
        const tree = semanticTree(undoTarget,all)
        if (tree.every(r => !r.attempted)) {
          await removeAndSplice(tree)
          if (undoTarget.kind.endsWith('.create')) cancelled.set(entity,tree)
          admitted = {...undoTarget,kind,state:'pending'}
          return
        }
      }
      const predecessor = [...all].reverse().find(r => r.aggregate===aggregate)?.id??null
      const creator = root ?? all.find(r => r.kind==='task.create' && r.entity===parent)
      if (creator && fundingCreator && creator.id!==fundingCreator.id && creator.dependency!==fundingCreator.id)
        throw new Error('Đợi bản ghi đang tạo được lưu rồi chọn nguồn thu mới. Nội dung vẫn được giữ.')
      admitted = {version:1,id,principal:owner,kind,entity,parent,aggregate,predecessor,
        dependency:creator?.id??fundingCreator?.id??null,created_at:new Date().toISOString(),expires_at:context.expires,
        payload,digest,envelope_digest,byte_length:new TextEncoder().encode(payload).length,requires_private:requiresPrivate,
        state:'pending',attempted:false,attempt:0,next_due:Math.max(0,...all.map(r => r.transport_until??0)),reason:''}
      admitted.operation_id = await db.rows.add(admitted)
    })
  } catch (error) {
    publish({error:'Chưa lưu. Giữ nội dung và kiểm tra bộ nhớ/phiên.'})
    throw error
  }
  await changed()
  return admitted!
}
export async function discardRejected(id:string):Promise<void> {
  await db.transaction('rw',db.rows,async () => {
    const all = await db.rows.toArray(), root = all.find(r => r.id===id && r.principal===context.principal)
    if (!root || root.state!=='rejected') throw new Error('Không bỏ lệnh chưa rõ kết quả')
    await removeAndSplice(semanticTree(root,all))
  })
  await changed()
}
export async function barrier(aggregate:string):Promise<void> {
  const rows = await db.rows.where('aggregate').equals(aggregate).toArray()
  if (rows.some(r => r.principal===context.principal) || reconciling.has(aggregate))
    throw new Error('Đối tượng còn thay đổi đang chờ. Kết nối và đợi cập nhật trước thao tác này.')
}
async function capability():Promise<boolean> {
  if (checkedGeneration === generation) return capable
  checkedGeneration = generation; capable = false; fundingCapable = false
  const epoch = authEpoch, visibility = privateEpoch
  try {
    const session = await apiRequest<BootstrapSession>('/api/me')
    await bindSession(session,epoch,visibility)
    const ready = await apiRequest<{outbox_protocols?:number[];db:string;entry_funding_version?:number}>('/api/readyz')
    if(ready.db!=='up')throw new Error('Database not ready')
    checkedGeneration=generation
    capabilityAttempt=0
    capable = ready.db==='up' && ready.outbox_protocols?.includes(1)===true
    fundingCapable = ready.entry_funding_version===1
    publish({capability:capable?'Sẵn sàng':'Máy chủ chưa hỗ trợ V1; đang giữ'})
  } catch (error) {
    if(error instanceof UnauthenticatedError || error instanceof ApiError && error.status===401) {
      context.verified=false;capable=false;checkedGeneration=generation
      publish({capability:'Cần đăng nhập lại; đang giữ'})
      return false
    }
    checkedGeneration=-1
    const until=Date.now()+retryDelay(++capabilityAttempt,error instanceof ApiError?error.headers.get('Retry-After'):null)
    await db.transaction('rw',db.rows,async () => {
      for(const row of await db.rows.where('principal').equals(context.principal).toArray())
        await db.rows.update(row.operation_id!,{next_due:Math.max(until,row.next_due),transport_until:until})
    })
    schedule(until)
    publish({capability:'Chưa xác minh kết nối/phiên; đang giữ'})
  }
  return capable
}
function schedule(at:number) {
  clearTimeout(timer)
  if (Number.isFinite(at)) timer=setTimeout(wake,Math.max(50,at-Date.now()))
}
export function wake() { queueMicrotask(() => { void flush() }) }
export async function retry() {
  generation++
  await db.transaction('rw',db.rows,async () => {
    for (const row of await db.rows.where('principal').equals(context.principal).toArray())
      if (row.state!=='rejected' && row.state!=='held') await db.rows.update(row.operation_id!,{next_due:Math.max(0,row.transport_until??0)})
  })
  await changed()
}
async function hold(row:Command,reason:string,state:Command['state']='held') {
  await db.rows.update(row.operation_id!,{state,reason})
}
async function reconcile(row:Command,response:unknown,owner:string,privateAllowed:boolean) {
  if (context.principal!==owner || effectivePrivate(row) && (!privateAllowed || !unlocked())) return
  remember(response)
  const prior = reconciling.get(row.aggregate)??[]
  reconciling.set(row.aggregate,[...new Map([...prior,row].map(r => [r.id,r])).values()]); publish()
  // No speculative canonical cache merge: projection remains in RAM until a fresh response.
  const prefix = row.kind.startsWith('entry.')?'tracker':'tasks'
  const active = client?.getQueryCache().findAll({predicate:q =>
    (q.queryKey[0]===prefix || !row.kind.startsWith('entry.') && q.queryKey[0]==='calendar') && q.isActive()})
  await client?.invalidateQueries({predicate:q => q.queryKey[0]===prefix || prefix==='tasks' && q.queryKey[0]==='calendar'})
  if (context.principal===owner && active?.length && active.every(q => q.state.status==='success' && !q.state.isInvalidated)) {
    reconciling.delete(row.aggregate);publish()
  }
}
export async function flush():Promise<void> {
  if (running || !navigator.onLine || !snapshot.rows.length || legacy || !context.principal) return
  if (!navigator.locks) { publish({capability:'Trình duyệt chưa hỗ trợ đồng bộ an toàn; đang giữ'}); return }
  running = true
  try {
    await navigator.locks.request('microsched-outbox-flush',{ifAvailable:true},async lock => {
      if (!lock) return
      const current = await db.rows.where('principal').equals(context.principal).toArray()
      if(!current.length)return
      const notBefore=Math.max(0,...current.map(r => r.transport_until??0))
      if(notBefore>Date.now()){schedule(notBefore);return}
      if(!await capability())return
      while (navigator.onLine && context.verified && capable) {
        const owner = context.principal
        const all = (await db.rows.toArray()).sort(byOrder)
        const dangling = all.filter(r => r.principal===owner && (r.predecessor && !all.some(p => p.id===r.predecessor) || r.dependency && !all.some(p => p.id===r.dependency)))
        for (const broken of dangling) await hold(broken,'Thiếu lệnh tiền nhiệm; cần kiểm tra')
        const ids = new Set(all.map(r => r.id))
        const row = all.find(r => r.principal===owner && r.state!=='rejected' && r.state!=='held' &&
          (!needsFunding(r) || fundingCapable) &&
          (!r.predecessor || !ids.has(r.predecessor)) && (!r.dependency || !ids.has(r.dependency)) &&
          r.next_due<=Date.now() && (!effectivePrivate(r) || unlocked()))
        if (!row) {
          if (!fundingCapable && all.some(needsFunding)) publish({capability:'Máy chủ chưa hỗ trợ nguồn thu; đang giữ khoản chi. Thử đồng bộ lại sau khi cập nhật.'})
          const due = all.filter(r => r.principal===owner && r.next_due>Date.now() && r.state!=='held' && r.state!=='rejected').map(r => r.next_due)
          if (due.length) schedule(Math.min(...due))
          break
        }
        let body:Fields
        try { body=await decode(row) } catch { await hold(row,'Định dạng/toàn vẹn chưa được hỗ trợ');await changed();continue }
        if (row.expires_at<=Date.now()) { await hold(row,'Lệnh hết hạn; cần đối chiếu, không tự xoá');await changed();continue }
        const claim = await db.transaction('rw',db.rows,async () => {
          const current = await db.rows.get(row.operation_id!)
          if (!current || current.id!==row.id || current.state==='rejected' || current.state==='held') return false
          await db.rows.update(row.operation_id!,{state:'sending',attempted:true,attempt:row.attempt+1})
          return true
        })
        if (!claim) continue
        await refresh()
        try {
          const target = route(row)
          const response = await apiRequest<unknown>(target.path,{method:target.method,
            headers:{'X-MicroSched-Outbox-Principal':row.principal,'X-MicroSched-Outbox-Protocol':'1'},
            ...(Object.keys(body).length?{body:row.payload}:{})})
          const privateAllowed = unlocked()
          // Set reconciling before durable ACK removes the visible pending effect.
          if (context.principal===owner && (!effectivePrivate(row) || privateAllowed)) {
            reconciling.set(row.aggregate,[...(reconciling.get(row.aggregate)??[]),row]);publish()
          }
          await db.transaction('rw',db.rows,async () => { await removeAndSplice([row]) })
          await changed()
          void reconcile(row,response,owner,privateAllowed)
        } catch (error) {
          if (error instanceof ApiError && error.status===404 && TOMBSTONES[row.kind] &&
              error.headers.get('X-MicroSched-Error-Code')===TOMBSTONES[row.kind]) {
            await db.transaction('rw',db.rows,async () => { await removeAndSplice([row]) })
            await changed();void reconcile(row,undefined,owner,unlocked());continue
          }
          if (error instanceof UnauthenticatedError || error instanceof ApiError && error.status===401) {
            context.verified=false; capable=false;await hold(row,'Cần đăng nhập lại','unknown');lockLocal();break
          }
          if (error instanceof ApiError && error.headers.get('X-MicroSched-Error-Code')==='PRIVATE_UNLOCK_REQUIRED') {
            lockLocal();await db.rows.update(row.operation_id!,{state:'unknown',requires_private:true,reason:'Cần mở khoá'});continue
          }
          if (error instanceof ApiError && [404,409].includes(error.status)) {
            await hold(row,'Cần đối chiếu nguồn; chưa rõ kết quả');await db.rows.update(row.operation_id!,{requires_private:true});await changed();continue
          }
          if (error instanceof ApiError && [400,422].includes(error.status)) {
            await hold(row,'Nội dung cần kiểm tra','rejected');await changed();continue
          }
          const delay=retryDelay(row.attempt+1,error instanceof ApiError?error.headers.get('Retry-After'):null)
          const until=Date.now()+delay
          await db.transaction('rw',db.rows,async () => {
            await db.rows.update(row.operation_id!,{state:'unknown',attempted:true,attempt:row.attempt+1,next_due:until,reason:'Đang xác minh lần gửi trước'})
            // Shared transport failures pace all aggregates; local admission remains independent.
            if (!(error instanceof ApiError) || error.status===429 || error.status===503)
              for (const other of await db.rows.where('principal').equals(owner).toArray())
                if (other.state!=='rejected' && other.state!=='held') await db.rows.update(other.operation_id!,{next_due:Math.max(until,other.next_due),transport_until:until})
          })
          await changed();schedule(until)
        }
      }
    })
  } catch { publish({error:'Chưa xác minh được lưu/ACK cục bộ. Giữ lệnh để phục hồi.'}) }
  finally { running=false;await refresh() }
}
