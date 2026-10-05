"""Isolated PostgreSQL test; never reads/writes customer project records."""
import os
import json
import uuid
from urllib.parse import urlsplit, urlunsplit
from unittest.mock import patch
import psycopg
from psycopg import sql

assert os.environ.get('KODAME_STABILITY_TEST') == '1'
name = 'kodame_stability_' + uuid.uuid4().hex[:12] + '_test'
admin_url = os.environ['ADMIN_DATABASE_URL']
with psycopg.connect(admin_url, autocommit=True) as conn:
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
for key in ('DATABASE_URL','ADMIN_DATABASE_URL'):
    url=urlsplit(os.environ[key]);os.environ[key]=urlunsplit(url._replace(path='/'+name))
os.environ['DATA_DIR']='/tmp/'+name
os.environ['KODAME_BOOTSTRAP_PASSWORD']='IsolatedTestOnly2026!'
os.environ['KODAME_SEED_DEMO_ACCOUNTS']='false'

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from kodame_intake import main, evaluation_runner as runner, dac_assessor as dac
from kodame_intake.db import connection, tenant_context, pool
from kodame_intake.pdm_jobs import finish_refresh
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA
from kodame_intake.evaluation_recovery import restore_run
from kodame_intake.project_lifecycle import capture_input_snapshot

def req(client, method, path, status=200, **kw):
    r=client.request(method,'/api/v2/'+path,**kw)
    assert r.status_code==status,(path,r.status_code,r.text[:300])
    return r.json()

checks=[]
def check(value,label):
    assert value,label
    checks.append(label);print('PASS '+label,flush=True)

try:
    with TestClient(main.app) as admin:
        req(admin,'POST','auth/login',json={'email':'admin','password':os.environ['KODAME_BOOTSTRAP_PASSWORD']})
        projects=[req(admin,'POST','admin/projects',201,json={'name':f'Stability {i}','supported_locales':['ko'],'default_locale':'ko'}) for i in range(2)]
        users=[]
        for i,p in enumerate(projects):
            a=req(admin,'POST','admin/accounts',201,json={'username':f'stability{i}','display_name':f'Test {i}','project_id':p['id']})
            client=TestClient(main.app)
            req(client,'POST','auth/login',json={'email':f'stability{i}','password':a['initial_password']})
            users.append(client)
        a,b=users;project=projects[0]['id']
        req(a,'POST','intake/uploads',202,files={'files':('test.txt',b'Isolated evidence.','text/plain')})
        with tenant_context(project),connection() as conn:
            conn.execute("UPDATE intake_documents SET status='completed',summary='Isolated evidence'")
        # The actual endpoint queues one durable job, even after a lost/repeated POST.
        with patch.object(main,'run_refresh'):
            job=req(a,'POST','pdm/refresh',202)
            duplicate=req(a,'POST','pdm/refresh',202)
        check(job['id']==duplicate['id'],'duplicate refresh returns same active job')
        check(req(b,'GET','pdm/refresh/status')['status']=='not_run','PDM receipts are tenant isolated by PostgreSQL RLS')
        model={'performance_indicators':[{'id':'outcome-1'}],'risk_analysis':{'status':'completed'},'monitoring':{}}
        with tenant_context(project),connection() as conn,conn.transaction():
            finish_refresh(conn,job['id'],uuid.uuid4(),model)
        check(req(a,'GET','pdm/refresh/status')['status']=='completed','completed refresh is recoverable after page reload')
        # A failed enclosing transaction cannot leave a false completion receipt.
        with tenant_context(project):
            try:
                with connection() as conn,conn.transaction():
                    finish_refresh(conn,job['id'],uuid.uuid4(),{**model,'risk_analysis':{'status':'fallback'}})
                    raise RuntimeError('forced rollback')
            except RuntimeError:pass
        check(req(a,'GET','pdm/refresh/status')['status']=='completed','PDM receipt rolls back atomically on failed save')

        counts={'overview':0,'pdm':0}; calls=[]; fail=True
        def overview(run_id):
            counts['overview']+=1
            with connection() as conn:
                conn.execute('INSERT INTO project_overviews(id,run_id,model,document_count,overview,source_document_ids,conflicts) VALUES (%s,%s,%s,1,%s,%s,%s)',
                    (uuid.uuid4(),run_id,runner.current_llm_model(),Jsonb({}),Jsonb([]),Jsonb([])))
        def pdm(documents):
            counts['pdm']+=1
            return {'status':'unavailable','model':{}}
        def prepare(documents):
            for d in documents:d['fulltext_review']={'status':'completed','chunks':[]}
        def answer(system,prompt,title,**kw):
            decoder=json.JSONDecoder();data,_=decoder.raw_decode(prompt)
            qid=data['questions'][0]['question_id'];calls.append(qid)
            if fail and qid=='effectiveness-q2':raise dac.AnalysisError('forced interruption')
            criterion=EVALUATION_CRITERIA[qid.split('-q')[0]]
            raw=dac.template({**criterion,'questions':[q for q in criterion['questions'] if q['id']==qid]})
            raw['question_assessments'][0]['finding']='제공된 자료만으로 실행 및 성과를 확인할 수 없어 판정을 보류합니다.'
            return raw,'test'
        with tenant_context(project),patch.object(runner,'generate_project_overview',side_effect=overview),patch.object(runner,'refresh_pdm_context',side_effect=pdm),patch.object(runner,'prepare_documents',side_effect=prepare),patch.object(dac,'_request_json',side_effect=answer):
            try: runner._run_all()
            except dac.AnalysisError:pass
            else:raise AssertionError('forced failure did not occur')
            with connection() as conn:
                failed=conn.execute("SELECT * FROM evaluation_runs WHERE status='failed' ORDER BY started_at DESC LIMIT 1").fetchone()
                n=conn.execute('SELECT count(*) AS n FROM criterion_evaluations WHERE run_id=%s',(failed['id'],)).fetchone()['n']
            saved=len(failed['input_snapshot']['question_checkpoints'])
            check(n==2 and saved==5,'failure retains two criteria and five validated questions')
            calls.clear();fail=False;new_id=runner._run_all()
            total=sum(len(c['questions']) for c in EVALUATION_CRITERIA.values())
            check(calls[0]=='effectiveness-q2' and len(calls)==total-saved,'retry starts at failed question and skips five validated questions')
            check(counts=={'overview':1,'pdm':1},'identical-input retry reuses overview and PDM snapshot')
            with connection() as conn:
                completed=conn.execute('SELECT * FROM evaluation_runs WHERE id=%s',(new_id,)).fetchone()
            check(completed['status']=='completed' and len(completed['input_snapshot']['question_checkpoints'])==total,'resumed run completes every question')
            check(restore_run(uuid.uuid4(),'changed-input',capture_input_snapshot()) is None,'changed fingerprint cannot restore prior results')
        check(req(b,'GET','evaluations/status')['status']=='not_run','DAC recovery data is tenant isolated')
    print(json.dumps({'checks':len(checks),'status':'passed'}),flush=True)
finally:
    pool.close()
    # Delete only the UUID-named database created by THIS process, never kodame.
    assert name.startswith('kodame_stability_') and name.endswith('_test') and len(name)==34
    with psycopg.connect(admin_url,autocommit=True) as conn:
        conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
