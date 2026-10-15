"""H14 task-owned namespace over the existing sandbox driver. Never reuse legacy volumes."""
from pathlib import Path
import argparse, hashlib, importlib, json, subprocess, sys

TASK='h14-n1-20261015'
LANES={'microsched','mimi'}
SOURCES={
    'microsched': Path.home()/'.codex/worktrees/harness-b-verification/microsched',
    'mimi': Path.home()/'.codex/worktrees/harness-b-mimi-qa/microsched',
}
class Refusal(RuntimeError): pass

def validate_volume(payload, name, identity):
    if payload.get('Name') != name or (payload.get('Labels') or {}).get('harness.task') != identity:
        raise Refusal('Volume has no exact H14 ownership label; retain it, do not reuse/reset/delete')

def validate_fixture(payload):
    for key in ['counts_match','review_store_preserved','review_bundle_roundtrip','feedback_acknowledged']:
        if payload.get(key) is not True: raise Refusal('Synthetic fixture oracle failed: '+key)

def inspect_volume(name):
    p=subprocess.run(['docker','volume','inspect',name],capture_output=True,text=True)
    if p.returncode:
        if 'no such volume' in p.stderr.lower(): return None
        raise Refusal('Volume ownership unavailable; Docker error retained')
    return json.loads(p.stdout)[0]

def check_binding(source,binding,lane):
    p=json.loads(Path(binding).read_text(encoding='utf-8-sig'))
    source=Path(source).resolve()
    if lane not in SOURCES: raise Refusal('Unknown lane')
    if p.get('lane')!=lane: raise Refusal('Binding lane mismatch')
    if source!=SOURCES[lane].resolve(): raise Refusal('Source is not the approved checkout for lane')
    if Path(p['source']).resolve()!=source: raise Refusal('Binding checkout mismatch')
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if head!=p['head']: raise Refusal('Candidate head mismatch')
    for rel,want in p['files'].items():
        target=(source/rel).resolve()
        if not target.is_relative_to(source) or target.name.startswith('.env') and target.name!='.env.example':
            raise Refusal('Unsafe source manifest path')
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=want:
            raise Refusal('Candidate manifest changed: '+rel)
    return p

def configure(source,lane,binding):
    check_binding(source,binding,lane)
    if lane not in LANES: raise Refusal('Unknown lane')
    sys.path.insert(0,str(source/'backend'))
    d=importlib.import_module('scripts.mimi_sandbox')
    identity=f'{TASK}-{lane}'
    d.TASK_ID=identity;d.ENVIRONMENT_ID=identity+'-local'
    d.CONTAINER=identity;d.VOLUME=identity+'-db';d.CONTAINER_LABEL='microsched.synthetic='+identity
    d.DATABASE='microsched_h14_'+lane;d.POSTGRES_PORT=55456
    # Vite's inspected proxy targets 8000, so app ports are used sequentially, not changed silently.
    d.BACKEND_PORT=8000;d.FRONTEND_PORT=5173
    d.LOCAL_ROOT=source/'.local/h14-night'/lane
    d.STATE_PATH=d.LOCAL_ROOT/'runtime.json';d.DOMAIN_RECEIPT=d.LOCAL_ROOT/'domain/seed-receipt.json'
    d.REVIEW_ROOT=d.LOCAL_ROOT/'review'
    original_env=d._runtime_env
    def synthetic_env(state):
        e=original_env(state)
        e.update({'MIMI_PUBLIC_ORIGIN':'http://127.0.0.1:5173','MIMI_REAL_CHAT_ENABLED':'true','MIMI_LIVE_PROVIDER_ENABLED':'false','MIMI_CONTEXT_V1_ENABLED':'false','MIMI_WORKFLOW_PILOT_ENABLED':'false','MIMI_COLLECTION_ENABLED':'false','MIMI_NOTIFICATIONS_ENABLED':'false'})
        return e
    d._runtime_env=synthetic_env
    original_ensure=d._ensure_postgres
    def ensure(state):
        payload=inspect_volume(d.VOLUME)
        if payload is None:
            if d._docker_inspect() is not None: raise Refusal('Container exists but volume binding is missing')
            p=subprocess.run(['docker','volume','create','--label','harness.task='+identity,d.VOLUME],capture_output=True,text=True)
            if p.returncode: raise Refusal('Owned volume creation failed')
            payload=inspect_volume(d.VOLUME)
        validate_volume(payload,d.VOLUME,identity)
        image=subprocess.run(['docker','image','inspect','pgvector/pgvector:pg18'],capture_output=True,text=True)
        if image.returncode: raise Refusal('Required cached image missing; no implicit pull')
        original_ensure(state)
    d._ensure_postgres=ensure
    return d,identity

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--binding',required=True);p.add_argument('--lane',choices=sorted(LANES),required=True)
    p.add_argument('action',choices=['start','status','verify','stop'])
    a=p.parse_args();source=Path(a.source).resolve()
    d,identity=configure(source,a.lane,a.binding)
    volume=inspect_volume(d.VOLUME)
    if volume is not None: validate_volume(volume,d.VOLUME,identity)
    # Original driver checks state marker, exact labeled container, image/mount/loopback port and PID owners.
    if a.action=='start': result=d.start(with_app=True,install=False)
    elif a.action=='status': result=d.status()
    elif a.action=='verify':
        state=d._load_state();d._activate_synthetic_settings(state)
        import asyncio
        result=asyncio.run(d.verify(state))
        validate_fixture(result)
    else: result=d.stop()
    print(json.dumps(result,default=str,indent=2))

if __name__=='__main__':
    try: main()
    except Refusal as e: print('REFUSED: '+str(e),file=sys.stderr);sys.exit(2)
