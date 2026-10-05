"""Synthetic service integration. Run ONLY with compose.qa.yml and stopped QA workers.

Uses the real HTTP server, PostgreSQL RLS and upload pipeline; paid AI is stubbed.
Results and synthetic login are saved to /qa for browser inspection.
"""
import copy
import json
import os
import uuid
from pathlib import Path
from unittest.mock import patch
import httpx
from psycopg.types.json import Jsonb

assert os.environ.get('KODAME_QA') == '1'
assert 'qa-local-only@postgres' in os.environ['DATABASE_URL']
from kodame_intake.db import pool, connection, tenant_context
from kodame_intake import worker, workflow_queue as queue
from kodame_intake.project_lifecycle import capture_input_snapshot

BASE='http://kodame-redesign-api:8100/api/v2/'
checks=[]
def check(value,label):
    assert value,label
    checks.append(label); print('PASS '+label,flush=True)
def req(client,method,path,status=200,**kw):
    response=client.request(method,BASE+path,**kw)
    assert response.status_code==status,(path,response.status_code,response.text[:600])
    return response.json() if response.content else None
def upload(client,role,name,text,status=202,**extra):
    return req(client,'POST','intake/uploads',status,params={'role':role,**extra},files={'files':(name,text.encode(),'text/plain')})

pool.open(wait=True)
admin=httpx.Client(timeout=60)
req(admin,'POST','auth/login',json={'email':'admin','password':'qa-admin-local-only'})
tag=uuid.uuid4().hex[:6]
projects=[]; users=[]; logins=[]
for number in range(2):
    p=req(admin,'POST','admin/projects',201,json={'name':f'합성 QA {tag}-{number+1}','supported_locales':['ko'],'default_locale':'ko'})
    issued=req(admin,'POST','admin/accounts',201,json={'username':f'qa_{tag}_{number}','display_name':f'QA {number+1}','project_id':p['id']})
    client=httpx.Client(timeout=60)
    login={'email':f'qa_{tag}_{number}','password':issued['initial_password']}
    req(client,'POST','auth/login',json=login)
    projects.append(p); users.append(client); logins.append(login)
user,other=users; project=projects[0]['id']
Path('/qa/synthetic-accounts.json').write_text(json.dumps({'projects':projects,'logins':logins},ensure_ascii=False),encoding='utf-8')

upload(user,'evidence','blocked.txt','사업 기준 문서 미등록',409)
check(True,'ordinary upload blocked before both foundations complete')
PLAN='합성 보건교육 역량강화 사업계획서. 사업기간 2025~2026년. 지역 강사 6명 양성, 모의훈련 3회, 교육 참여자 30명. 예산 1억원. 종료 후 대학이 교육과정을 운영한다.'
PDM='1. 지역사회 CPCR 강사 수 (2025년 0명, 2026년 6명)\n2. 모의훈련 실시 횟수 (2026년까지 3회)'
ACTUAL='2026년 6월 30일 실적: 지역사회 CPCR 강사 6명을 양성하였다. 모의훈련 3회를 실시하였다. 교육 참여자는 30명이며 서명 명부로 확인했다. 대학 운영예산은 아직 확정되지 않았다.'
slots={'outputs_summary':'강사와 모의훈련 체계 구축','outputs_indicator':PDM,
       'outputs_mov':'1. 강사 수료증 및 서명 명부\n2. 모의훈련 실시 결과보고서'}

def finish_upload(document,role,text,matches=None):
    with tenant_context(system=True):
        with connection() as conn:
            excluded=[d['id'] for d in conn.execute('SELECT id FROM intake_documents WHERE id<>%s',(document['id'],)).fetchall()]
        row=worker.claim_next(exclude_ids=excluded)
    assert row and str(row['id'])==document['id']
    result={'summary':'합성 QA 문서 기본 요약','section_matches':[],'dac_criteria':[],
            'upload_role':role,'content_classification':{'version':'content-roles-v1','document_type':'합성 보고서',
            'is_project_plan':role=='project_plan','is_pdm_source':role=='pdm','slots':slots if role=='pdm' else {},'slot_matches':[]}}
    with patch.object(worker,'analyze_document',return_value=result), \
         patch('kodame_intake.intake_triage.classify',return_value={'kind':'evidence','confidence':.99,'reason':'합성 실적보고서','needs_review':False}), \
         patch('kodame_intake.dac_evidence.analyze_document',return_value={'question_ids':[]}), \
         patch('kodame_intake.foundation_facts.extract_plan_facts',return_value={'facts':[], 'coverage':[]}), \
         patch('kodame_intake.evidence_matching.match_foundations',return_value=matches), \
         patch.object(worker,'refresh_pdm_model'), patch.object(worker,'refresh_project_overview_if_needed'):
        worker.process_in_tenant(row)
    with tenant_context(project), connection() as conn:
        saved=conn.execute('SELECT * FROM intake_documents WHERE id=%s',(document['id'],)).fetchone()
    check(saved['status']=='completed',f'{role}: original, extraction, analysis and save complete')
    check(Path(saved['stored_path']).is_file() and Path(saved['extracted_path']).read_text()==text,f'{role}: original and extracted text retained')
    return saved

plan=upload(user,'project_plan','사업계획서_QA.txt',PLAN)['accepted'][0]
finish_upload(plan,'project_plan',PLAN)
upload(user,'evidence','blocked2.txt','PDM 아직 미등록',409)
pdm=upload(user,'pdm','PDM_QA.txt',PDM)['accepted'][0]
finish_upload(pdm,'pdm',PDM)
check(req(user,'GET','intake/foundation')['ready'],'foundation gate opens only after both completed')
upload(user,'pdm','PDM_교체.txt',PDM+' 교체',409)
check(True,'foundation replacement requires explicit current document identity')

preview=req(user,'GET','pdm/analysis-plan')
indicators=preview['indicators']; check(len(indicators)==2,'PDM roster has two exact indicators')
from kodame_intake.evidence_matching import foundation_context
with tenant_context(project): context=foundation_context()
facts={'version':'intake-facts-v1','summary':'사업계획의 강사 양성과 모의훈련 달성을 보고하며 지속가능성의 예산 미확정을 확인하는 자료이다.',
       'facts':[{'id':'qa-fact','statement':'CPCR 강사 6명 양성','kind':'reported_actual','value':'6','unit':'명','period':'2026-06-30','population':'지역사회 강사',
                 'evidence_quote':'지역사회 CPCR 강사 6명을 양성하였다.','pdm_indicator_ids':[indicators[0]['id']],'dac_question_ids':['effectiveness-q1']}], 'scope':'full_text'}
matches={'version':2,'sources':context['sources'],'project_plan':[],
         'pdm':[{'indicator_id':i['id'],'indicator':i['text'],'tier':i['tier'],'requirement_title':i['mov'],'confidence':.99,'rationale':'원문 실적 확인','evidence_quote':ACTUAL} for i in indicators],
         'registration_facts':facts}
doc=upload(user,'evidence','실적현황_QA.txt',ACTUAL)['accepted'][0]
saved=finish_upload(doc,'evidence',ACTUAL,matches)
check(saved['summary']==facts['summary'] and len(saved['analysis']['registration_facts']['facts'])==1,'context summary and grounded registration facts persist')
check('pdm_measurements' not in saved['analysis'] and 'dac_fulltext' not in saved['analysis'],'ordinary registration does not run final performance/DAC analysis')
dupe=upload(user,'evidence','실적현황_QA.txt',ACTUAL)['accepted'][0]
check(dupe['id']==doc['id'] and dupe['deduplicated'],'upload replay deduplicates original file')
check(req(other,'GET','intake/jobs')['total']==0,'second account cannot list first project documents')
req(other,'GET',f"intake/jobs/{doc['id']}",404)
with tenant_context(project),connection() as conn:
    count=conn.execute('SELECT count(*) AS n FROM intake_documents').fetchone()['n']
with tenant_context(projects[1]['id']),connection() as conn:
    check(count==3 and conn.execute('SELECT count(*) AS n FROM intake_documents').fetchone()['n']==0,'PostgreSQL RLS isolates documents independently of HTTP')

queued=upload(user,'evidence','중단_QA.txt','추가 자료')['accepted'][0]
req(user,'POST',f"intake/jobs/{queued['id']}/cancel",202)
req(user,'POST',f"intake/jobs/{queued['id']}/retry",202)
req(user,'POST',f"intake/jobs/{queued['id']}/cancel",202)
check(True,'queued upload cancellation and explicit retry work')

review=req(user,'GET','pdm/analysis-plan')
selected={i['id']:[doc['id']] for i in review['indicators']}
job=req(user,'POST','pdm/refresh',202,json={'revision':review['revision'],'mappings':selected})
replay=req(user,'POST','pdm/refresh',202,json={'revision':review['revision'],'mappings':selected})
check(job['id']==replay['id'],'duplicate performance POST returns one active receipt')
with tenant_context(project),connection() as conn:
    tasks=conn.execute('SELECT * FROM workflow_tasks').fetchall()
    check(len(tasks)==1 and tasks[0]['status']=='queued','HTTP response persists exactly one workflow outbox item')
with tenant_context(projects[1]['id']),connection() as conn:
    check(not conn.execute('SELECT * FROM workflow_tasks').fetchall(),'workflow tasks enforce tenant RLS')
# Forced failure rolls back the receipt and its outbox entry together.
try:
    with tenant_context(project),connection() as conn,conn.transaction():
        rid=uuid.uuid4()
        conn.execute("INSERT INTO pdm_refresh_runs(id,model,status) VALUES (%s,'test','completed')",(rid,))
        queue.enqueue(conn,'pdm',[rid],'test')
        raise RuntimeError('forced rollback')
except RuntimeError: pass
with tenant_context(project),connection() as conn:
    check(conn.execute('SELECT count(*) AS n FROM workflow_tasks').fetchone()['n']==1,'transaction failure rolls back task and receipt together')

# Actual performance engine, with deterministic external AI response only.
def measures(document,roster,**kw):
    return [{'indicator_id':i['id'],'kind':'actual','value':'6명' if n==0 else '3회',
             'quote':ACTUAL,'period':'2026-06-30','document_id':str(document['id']),'file_name':document['original_name']} for n,i in enumerate(roster)]
with patch('kodame_intake.pdm_evidence.extract_measurements',side_effect=measures), \
     patch('kodame_intake.pdm_monitoring.analyze_performance_risks',return_value={'items':[]}):
    queue.dispatch(tasks[0])
with tenant_context(project),connection() as conn:
    queue.finish_task(conn,tasks[0])
state=req(user,'GET','pdm/refresh/status')
check(state['status'] in ('completed','partial'),'real performance runner saves a terminal result')
model=req(user,'GET','pdm')
check(model['performance_indicators'][0]['target']=='6명','PDM dated target becomes 6명')
check(model['performance_indicators'][0]['actual']=='6명','performance uses the mapped document observation')
after=req(user,'GET','pdm/analysis-plan')
check(all(doc['id'] not in i['document_ids'] for i in after['indicators']),'already analyzed document/indicator pairs omitted from next proposal')

req(user,'POST','report/generate-all',409)
check(True,'report generation requires a completed current DAC evaluation')
for path in ['dashboard','project-overview','pdm','project/lifecycle','intake/jobs','evaluations','evaluations/status','evaluations/analysis-plan','report/sections','report/job-tray']:
    req(user,'GET',path)
check(True,'all principal project read APIs return valid responses')
other_session=httpx.Client(timeout=60); req(other_session,'POST','auth/login',json=logins[0])
req(other_session,'POST','auth/logout',204)
check(req(user,'GET','auth/me')['has_project'],'logging out a second session does not end the first session')

Path('/qa/integration.json').write_text(json.dumps({'status':'passed','checks':checks,'project_id':project},ensure_ascii=False,indent=2),encoding='utf-8')
pool.close()
print(json.dumps({'status':'passed','checks':len(checks),'project_id':project}),flush=True)
