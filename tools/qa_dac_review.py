"""Incremental performance acceptance test in a disposable DB, no external AI."""
import os
import uuid
import json
import hashlib
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
from unittest.mock import patch
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

assert os.environ.get('KODAME_DAC_REVIEW_TEST')=='1'
name='kodame_dac_review_'+uuid.uuid4().hex[:12]+'_test'
admin_url=os.environ['ADMIN_DATABASE_URL']
with psycopg.connect(admin_url,autocommit=True) as conn:
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
for key in ('DATABASE_URL','ADMIN_DATABASE_URL'):
    os.environ[key]=urlunsplit(urlsplit(os.environ[key])._replace(path='/'+name))
os.environ['DATA_DIR']='/tmp/'+name
os.environ['KODAME_BOOTSTRAP_PASSWORD']='IsolatedTestOnly2026!'
from fastapi.testclient import TestClient
from kodame_intake import main,pdm_evidence,pdm_monitoring
from kodame_intake.db import connection,tenant_context,pool

def req(client,method,path,status=200,**kwargs):
    response=client.request(method,'/api/v2/'+path,**kwargs)
    assert response.status_code==status,(path,response.status_code,response.text[:500])
    return response.json()

try:
    with TestClient(main.app) as admin:
        req(admin,'POST','auth/login',json={'email':'admin','password':os.environ['KODAME_BOOTSTRAP_PASSWORD']})
        project=req(admin,'POST','admin/projects',201,json={'name':'Delta QA','supported_locales':['ko'],'default_locale':'ko'})['id']
        account=req(admin,'POST','admin/accounts',201,json={'username':'deltaqa','display_name':'Delta QA','project_id':project})
        user=TestClient(main.app)
        req(user,'POST','auth/login',json={'email':'deltaqa','password':account['initial_password']})
        ids={key:str(uuid.uuid4()) for key in ('plan','pdm','A','B','C','D')}
        root=Path(os.environ['DATA_DIR']);root.mkdir(parents=True,exist_ok=True)
        def insert(key,role='evidence',indicator=None):
            path=root/(key+'.txt');path.write_text('2024 60명 30명 100명 2025 70명 40명',encoding='utf-8')
            analysis={'upload_role':role,'evidence_matches':{'sources':{'pdm':{'id':ids['pdm']}},'pdm':([{'indicator_id':indicator}] if indicator else [])}}
            if role=='pdm': analysis['content_classification']={'version':'content-roles-v1','is_pdm_source':True,'is_project_plan':False,'slots':{'outcome_indicator':'1. Training people\n2. Service people','outcome_mov':'1. Completion list\n2. Service list'}}
            with tenant_context(project),connection() as conn:
                conn.execute('''INSERT INTO intake_documents(id,original_name,stored_path,extracted_path,extension,size_bytes,sha256,status,upload_role,analysis,completed_at)
                    VALUES(%s,%s,%s,%s,'.txt',1,%s,'completed',%s,%s,now())''',(ids[key],key+'.txt',str(path),str(path),hashlib.sha256(path.read_bytes()).hexdigest(),role,Jsonb(analysis)))
        insert('plan','project_plan');insert('pdm','pdm');insert('A',indicator='outcome-1');insert('B',indicator='outcome-2')
        from kodame_intake import evaluation_runner, dac_evidence
        calls=[]
        def extract(system,prompt,*args,**kwargs):
            data=json.loads(prompt);calls.append(data)
            return {'evidence':[]},'test'
        def adjudicate(cid,criterion,corpus,*args,**kwargs):
            assert all(item['document_id']==ids['A'] for item in corpus),corpus
            return {'score':None,'summary':'검증용 보류','score_reason':'근거 부족',
                    'question_assessments':[], 'evidence_gaps':['근거 부족']}
        with patch.object(evaluation_runner,'generate_project_overview'),patch.object(evaluation_runner,'refresh_pdm_context',return_value={'status':'unavailable','model':{}}),patch.object(evaluation_runner,'assess_criterion',side_effect=adjudicate),patch.object(dac_evidence,'_request_json',side_effect=extract):
            plan=req(user,'GET','evaluations/analysis-plan')
            assert len(plan['indicators'])==11
            assert not calls
            req(user,'POST','evaluations',409)
            mappings={q['id']:[] for q in plan['indicators']}
            bad={**mappings,'effectiveness-q1':[str(uuid.uuid4())]}
            req(user,'POST','evaluations',422,json={'revision':plan['revision'],'mappings':bad})
            from playwright.sync_api import sync_playwright,expect
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True,args=['--no-sandbox'])
                page=browser.new_page();page.set_content('<div></div>')
                def bridge(path,options):
                    response=user.request(options.get('method','GET'),path,json=json.loads(options['body']) if options.get('body') else None)
                    return {'status':response.status_code,'data':response.json()}
                page.expose_function('bridge',bridge)
                page.add_script_tag(path='/workspace/assets/dac-analysis-review.js')
                page.evaluate('''async()=>{const request=async(path,options={})=>{const r=await bridge(path,options);if(r.status>=400)throw Error(r.data.detail);return r.data;};
                    window.review=DacAnalysisReview.create({request,start:body=>request('/api/v2/evaluations',{method:'POST',body:JSON.stringify(body)}),refreshIntake:async()=>{},notify:()=>{},escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')});await review.open();}''')
                expect(page.locator('[data-review-indicator]')).to_have_count(11)
                assert not calls
                while page.locator('[data-review-remove]').count():
                    page.locator('[data-review-remove]').first.click()
                row=page.locator('[data-review-indicator="effectiveness-q1"]')
                row.locator('select').select_option(ids['A']);row.locator('[data-review-add]').click()
                expect(row.locator('.performance-document a')).to_have_text(['A.txt'])
                row.locator('details summary').click()
                expect(row.locator('details')).to_have_attribute('open','')
                page.locator('[data-review-run]').click()
                expect(page.locator('#dacReviewDialog')).not_to_be_visible()
                browser.close()
            status=req(user,'GET','evaluations/status')
            assert status['status']=='completed',status
            assert len(calls)==1,calls
            assert calls[0]['file_name']=='A.txt'
            assert [q['id'] for q in calls[0]['criteria']['effectiveness']['questions']]==['effectiveness-q1']
            with tenant_context(project),connection() as conn:
                saved=conn.execute('SELECT input_snapshot FROM evaluation_runs ORDER BY started_at DESC LIMIT 1').fetchone()['input_snapshot']
            assert saved['review_plan']['mappings']['effectiveness-q1']==[ids['A']]
            next_plan=req(user,'GET','evaluations/analysis-plan')
            assert next(q for q in next_plan['indicators'] if q['id']=='effectiveness-q1')['document_ids']==[ids['A']]
            assert not next(q for q in next_plan['indicators'] if q['id']=='relevance-q1')['document_ids']
        print('PASS review opens without AI; 11 questions; mapping add/remove; original scope preview; reviewed scope only; foreign document and unreviewed execution blocked; plan persisted',flush=True)
finally:
    pool.close()
    with psycopg.connect(admin_url,autocommit=True) as conn:
        conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
