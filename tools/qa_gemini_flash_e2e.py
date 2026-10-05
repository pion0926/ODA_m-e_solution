"""One development-only, cold-start Gemini Flash run using original project files.

All business mutations use authenticated service APIs, never copy analysis caches.
Checkpoint files contain credentials: keep them in the private runtime directory.
Public snapshots exclude credentials and source paths. No automatic second full run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx

from kodame_intake.db import connection, pool, tenant_context

MODEL = 'google/gemini-3.8-flash'
BASE = 'http://127.0.0.1:8100'
ROOT = Path('/app/data/qa_token_runs')


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(state, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)


def request(client, method, route, **kwargs):
    response = client.request(method,route,**kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f'{method} {route}: {response.status_code} {response.text[:1200]}')
    return response.json() if response.content else None


def usage(project_id):
    with tenant_context(project_id), connection() as conn:
        rows = conn.execute('''SELECT model,count(*) AS calls,coalesce(sum(prompt_tokens),0) AS input_tokens,
            coalesce(sum(completion_tokens),0) AS output_tokens,coalesce(sum(total_tokens),0) AS total_tokens,
            coalesce(max(id),0) AS last_event_id FROM token_usage_events WHERE project_id=%s GROUP BY model''',
            (project_id,)).fetchall()
    for row in rows:
        for key in ('calls','input_tokens','output_tokens','total_tokens','last_event_id'):
            row[key] = int(row[key])
    return {'models':rows, **{k:sum(r[k] for r in rows) for k in ('calls','input_tokens','output_tokens','total_tokens')},
            'last_event_id':max((r['last_event_id'] for r in rows),default=0)}


def snapshot(state):
    project_id = state['project_id']
    with tenant_context(project_id), connection() as conn:
        docs = conn.execute('SELECT status,count(*) AS count FROM intake_documents GROUP BY status').fetchall()
        document_models = conn.execute('''SELECT analysis_model,count(*) AS count,
            sum(greatest(attempts-1,0)) AS retry_attempts FROM intake_documents GROUP BY analysis_model''').fetchall()
        failures = conn.execute('''SELECT original_name,error_code,error_message,attempts FROM intake_documents
            WHERE status IN ('failed','waiting_llm') ORDER BY queue_position''').fetchall()
        evaluation = conn.execute("SELECT id,status,model,error_message,input_snapshot ? 'pdm_context' AS pdm_context_ready FROM evaluation_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        dac_review = conn.execute('''SELECT coalesce(analysis->'dac_fulltext'->>'status','not_started') AS status,
            count(*) AS documents,sum(coalesce(jsonb_array_length(analysis->'dac_fulltext'->'chunks'),0)) AS chunks,
            sum(ceil(coalesce((analysis->'dac_fulltext'->>'character_count')::numeric,0)/24000)) AS expected_chunks
            FROM intake_documents GROUP BY 1''').fetchall()
        generation = conn.execute('''SELECT id,status,completed_sections,failed_sections,current_part_id,message
            FROM report_generation_runs ORDER BY started_at DESC LIMIT 1''').fetchone()
        sections = conn.execute('''SELECT part_id,section_number,title,status,length(content) AS content_chars,
            generation_model,quality_score,error_message FROM report_sections ORDER BY section_number''').fetchall()
        export = conn.execute('''SELECT id,status,progress,stage,message,error_message,file_name,output_path,validation
            FROM report_exports ORDER BY created_at DESC LIMIT 1''').fetchone()
        pdm = conn.execute('SELECT model FROM pdm_models LIMIT 1').fetchone()
        token_events = conn.execute('''SELECT id,model,prompt_tokens,completion_tokens,total_tokens,created_at
            FROM token_usage_events WHERE project_id=%s ORDER BY id''',(project_id,)).fetchall()
    return {'captured_at':utc(),'project_id':project_id,'project_name':state['project_name'],'username':state['username'],
            'source_project_id':state['source_project_id'],'source_name':state['source_name'],
            'source_count':len(state['sources']),'source_bytes':sum(d['size_bytes'] for d in state['sources']),
            'model':MODEL,'phase':state.get('phase'),'checkpoints':state.get('checkpoints',[]),
            'documents':docs,'document_models':document_models,'document_failures':failures,
            'evaluation':evaluation,'dac_fulltext_progress':dac_review,'generation':generation,'token_events':token_events,
            'sections':sections,'export':export,'pdm_indicator_count':len((pdm or {}).get('model',{}).get('performance_indicators',[])),
            'usage':usage(project_id),'error':state.get('error')}


def prepare(source_id):
    with tenant_context(source_id), connection() as conn:
        project = conn.execute('SELECT name FROM projects WHERE id=%s',(source_id,)).fetchone()
        docs = conn.execute('''SELECT original_name,stored_path,media_type,size_bytes,sha256
            FROM intake_documents ORDER BY queue_position''').fetchall()
    if not project or not docs:
        raise RuntimeError('Source project must contain documents.')
    for doc in docs:
        path = Path(doc['stored_path']).resolve()
        if not path.is_relative_to(Path('/app/data').resolve()) or not path.is_file():
            raise RuntimeError('Source file missing or outside development data storage.')
        if hashlib.sha256(path.read_bytes()).hexdigest() != doc['sha256']:
            raise RuntimeError('Source integrity mismatch: '+doc['original_name'])
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    name = 'Gemini Flash 전체보고서 토큰 검증 '+stamp
    with httpx.Client(base_url=BASE,timeout=60,trust_env=False) as admin:
        request(admin,'POST','/api/v2/auth/login',json={
            'email':os.getenv('KODAME_BOOTSTRAP_EMAIL','admin@kodame.local'),
            'password':os.getenv('KODAME_BOOTSTRAP_PASSWORD','admin')})
        catalog = request(admin,'GET','/api/v2/admin/ai-models')
        if not catalog['can_assign'] or not any(m['id']==MODEL and m['available'] for m in catalog['models']):
            raise RuntimeError('Gemini Flash availability could not be confirmed.')
        created = request(admin,'POST','/api/v2/admin/projects',json={
            'name':name,'supported_locales':['ko'],'default_locale':'ko','account_ids':[]})
        project_id = created['id']
        request(admin,'PUT',f'/api/v2/admin/projects/{project_id}/ai-model',json={'llm_model':MODEL,'expected_revision':0})
        account = request(admin,'POST','/api/v2/admin/accounts',json={
            'username':'flash-'+stamp,'display_name':'Gemini Flash 실측 검증','project_id':project_id})
        state = {'project_id':project_id,'project_name':name,'source_project_id':str(source_id),
                 'source_name':project['name'],'sources':docs,'model':MODEL,'created_at':utc(),
                 'username':account['username'],'password':account['initial_password'],'account_id':account['id'],
                 'phase':'prepared','checkpoints':[],'uploaded':[], 'catalog':catalog}
        path = ROOT / (stamp+'.json')
        save(state,path)
        request(admin,'POST','/api/v2/auth/logout')
    if usage(project_id)['total_tokens'] != 0:
        raise RuntimeError('New project unexpectedly contains token usage.')
    print(json.dumps({'state_path':str(path),'project_id':project_id,'username':state['username'],
                      'source_count':len(docs),'model':MODEL,'tokens_before':0},ensure_ascii=False),flush=True)


def run(path):
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('run_started_at'):
        raise RuntimeError('This run has already started. Inspect it; do not silently run it twice.')
    state['run_started_at'] = utc(); state.pop('error',None); save(state,path)
    client = httpx.Client(base_url=BASE,timeout=httpx.Timeout(120,read=120),trust_env=False)
    last_print = 0
    def checkpoint(label):
        state['checkpoints'].append({'label':label,'at':utc(),**usage(state['project_id'])})
        save(state,path)
    def poll(label, ready, timeout=7200):
        nonlocal last_print
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            current = snapshot(state)
            if time.monotonic()-last_print>30:
                print(json.dumps({'phase':label,'documents':current['documents'],'evaluation':current['evaluation'],
                    'generation':current['generation'],'export':{k:v for k,v in (current['export'] or {}).items() if k in ('status','progress','stage','error_message')},
                    'tokens':current['usage']['total_tokens']},ensure_ascii=False,default=str),flush=True)
                last_print=time.monotonic()
            if ready(current): return current
            time.sleep(10)
        raise RuntimeError(label+' exceeded the observation timeout; submitted work is not resubmitted.')
    try:
        request(client,'POST','/api/v2/auth/login',json={'email':state['username'],'password':state['password']})
        assert request(client,'GET','/api/v2/account/settings')['llm_model'] == MODEL
        checkpoint('start')
        state['phase']='document_intake'; save(state,path)
        for index, doc in enumerate(state['sources'],1):
            with Path(doc['stored_path']).open('rb') as file:
                accepted = request(client,'POST','/api/v2/intake/uploads',files={
                    'files':(doc['original_name'],file,doc['media_type'] or 'application/octet-stream')})['accepted'][0]
            if accepted['sha256'] != doc['sha256'] or accepted.get('deduplicated'):
                raise RuntimeError('Uploaded document identity mismatch.')
            state['uploaded'].append(accepted['id']); save(state,path)
            if index==1 or index%10==0 or index==len(state['sources']):
                print(json.dumps({'uploaded':index,'total':len(state['sources'])}),flush=True)
        def documents_ready(current):
            if current['document_failures']:
                raise RuntimeError('Document processing requires attention: '+json.dumps(current['document_failures'],ensure_ascii=False))
            return sum(r['count'] for r in current['documents'] if r['status']=='completed')==len(state['sources'])
        poll('document_intake',documents_ready)
        checkpoint('document_intake_finished')
        state['phase']='pdm_dac_evaluation'; save(state,path)
        state['evaluation_request']=request(client,'POST','/api/v2/evaluations'); save(state,path)
        def evaluation_ready(current):
            row=current['evaluation'] or {}
            if row.get('status')=='failed': raise RuntimeError('Evaluation failed: '+str(row.get('error_message')))
            return row.get('status')=='completed'
        poll('pdm_dac_evaluation',evaluation_ready)
        checkpoint('pdm_dac_evaluation_finished')
        state['phase']='report_sections'; save(state,path)
        state['generation_request']=request(client,'POST','/api/v2/report/generate-all'); save(state,path)
        def report_ready(current):
            row=current['generation'] or {}
            if row.get('status') in ('failed','completed_with_errors'):
                raise RuntimeError('Report needs individual section review: '+json.dumps([r for r in current['sections'] if r['status']=='failed'],ensure_ascii=False))
            return row.get('status')=='completed'
        poll('report_sections',report_ready)
        checkpoint('report_sections_finished')
        state['phase']='hwpx_export'; save(state,path)
        state['export_request']=request(client,'POST','/api/v2/report/exports'); save(state,path)
        def export_ready(current):
            row=current['export'] or {}
            if row.get('status')=='failed': raise RuntimeError('HWPX export failed: '+str(row.get('error_message')))
            return row.get('status')=='completed'
        poll('hwpx_export',export_ready,3600)
        checkpoint('hwpx_export_finished')
        state['phase']='completed'; state['completed_at']=utc(); save(state,path)
        print(json.dumps({'completed':True,'project_id':state['project_id'],'usage':usage(state['project_id'])},ensure_ascii=False,default=str),flush=True)
    except Exception as exc:
        state['error']=str(exc); state['attention_at']=utc(); save(state,path)
        print(json.dumps({'attention':True,'phase':state['phase'],'error':str(exc)[:1500]},ensure_ascii=False),flush=True)
        raise
    finally:
        save(snapshot(state),path.with_suffix('.public.json'))
        client.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['prepare','run','snapshot'])
    parser.add_argument('--source-project',type=UUID)
    parser.add_argument('--state',type=Path)
    args=parser.parse_args()
    if args.command == 'prepare' and not args.source_project:
        parser.error('--source-project is required for prepare')
    if args.command != 'prepare' and not args.state:
        parser.error('--state is required for run/snapshot')
    if os.environ.get('SESSION_COOKIE_NAME') != 'kodame_session':
        raise SystemExit('This test is restricted to the development server.')
    pool.open(wait=True)
    try:
        if args.command=='prepare': prepare(args.source_project)
        elif args.command=='run': run(args.state)
        else:
            state=json.loads(args.state.read_text(encoding='utf-8'))
            result=snapshot(state); save(result,args.state.with_suffix('.public.json'))
            print(json.dumps(result,ensure_ascii=False,default=str))
    finally:
        pool.close()
