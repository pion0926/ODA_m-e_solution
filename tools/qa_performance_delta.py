"""Incremental performance acceptance test in a disposable DB, no external AI."""
import os
import uuid
import json
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
from unittest.mock import patch
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

assert os.environ.get('KODAME_DELTA_TEST')=='1'
name='kodame_delta_'+uuid.uuid4().hex[:12]+'_test'
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
                    VALUES(%s,%s,%s,%s,'.txt',1,%s,'completed',%s,%s,now())''',(ids[key],key+'.txt',str(path),str(path),key.ljust(64,'0'),role,Jsonb(analysis)))
        insert('plan','project_plan');insert('pdm','pdm');insert('A',indicator='outcome-1');insert('B',indicator='outcome-2')
        calls=[]
        def measurement(doc,indicators,*,previous_evaluation=None):
            key=doc['original_name'][0];targets=[i['id'] for i in indicators]
            calls.append((key,targets,previous_evaluation))
            values={'A':('60명','2024') if targets==['outcome-1'] else ('40명','2025'),'B':('30명','2024'),'C':('70명','2025')}
            if key=='D':raise pdm_evidence.AnalysisError('test failure')
            value,period=values[key]
            return [{'indicator_id':i['id'],'kind':kind,'value':v,'period':period,'quote':v,'document_id':str(doc['id']),'file_name':doc['original_name']}
                    for i in indicators for kind,v in [('target','100명'),('actual',value)]]
        with patch.object(pdm_evidence,'extract_measurements',side_effect=measurement),patch.object(pdm_monitoring,'analyze_performance_risks',return_value={'items':[],'model':'test'}):
            plan=req(user,'GET','pdm/analysis-plan')
            assert len(plan['indicators'])==2,plan
            req(user,'POST','pdm/refresh',202,json={'revision':plan['revision'],'mappings':{'outcome-1':[ids['A']],'outcome-2':[ids['B']]}})
            assert req(user,'GET','pdm/refresh/status')['status']=='completed'
            calls.clear();insert('C',indicator='outcome-1')
            plan=req(user,'GET','pdm/analysis-plan')
            assert plan['indicators'][0]['document_ids']==[ids['C']], plan
            assert plan['indicators'][1]['document_ids']==[]
            assert plan['indicators'][0]['retained_document_ids']==[ids['A']]
            # Exercise actual review JS: old mapped documents are hidden; A may be newly mapped to 1-2.
            from playwright.sync_api import sync_playwright,expect
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True,args=['--no-sandbox'])
                page=browser.new_page();page.set_content('<div></div>')
                def bridge(path,options):
                    response=user.request(options.get('method','GET'),path,json=json.loads(options['body']) if options.get('body') else None)
                    return {'status':response.status_code,'data':response.json()}
                page.expose_function('bridge',bridge)
                page.add_script_tag(path='/workspace/assets/performance-analysis-review.js')
                page.evaluate('''async()=>{const request=async(path,options={})=>{const r=await bridge(path,options);if(r.status>=400)throw Error(r.data.detail);return r.data;};
                    window.review=PerformanceAnalysisReview.create({request,start:body=>request('/api/v2/pdm/refresh',{method:'POST',body:JSON.stringify(body)}),refreshIntake:async()=>{},notify:()=>{},escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')});await review.open();}''')
                expect(page.locator('[data-review-rows] .performance-document a')).to_have_text(['C.txt'])
                row=page.locator('[data-review-indicator="outcome-2"]')
                row.locator('select').select_option(ids['A']);row.locator('[data-review-add]').click()
                expect(page.locator('[data-review-rows] .performance-document a')).to_have_text(['C.txt','A.txt'])
                page.locator('[data-review-run]').click()
                expect(page.locator('#performanceReviewDialog')).not_to_be_visible()
                browser.close()
            assert {(key,tuple(indicators)) for key,indicators,_ in calls}=={('C',('outcome-1',)),('A',('outcome-2',))},calls
            assert next(ctx for key,_,ctx in calls if key=='C')['outcome-1']['actual']=='60명'
            assert next(ctx for key,_,ctx in calls if key=='A')['outcome-2']['actual']=='30명'
            with tenant_context(project),connection() as conn:
                model=conn.execute('SELECT model FROM pdm_models').fetchone()['model']
            assert [i['actual'] for i in model['performance_indicators']]==['70명','40명']
            assert [i['achievement_rate'] for i in model['performance_indicators']]==[70,40]
            assert len(model['monitoring']['pair_results'])==4
            plan=req(user,'GET','pdm/analysis-plan')
            assert not any(i['document_ids'] for i in plan['indicators'])
            req(user,'POST','pdm/refresh',409,json={'revision':plan['revision'],'mappings':{'outcome-1':[],'outcome-2':[]}})
            calls.clear();insert('D',indicator='outcome-1')
            plan=req(user,'GET','pdm/analysis-plan')
            req(user,'POST','pdm/refresh',202,json={'revision':plan['revision'],'mappings':{'outcome-1':[ids['D']],'outcome-2':[]}})
            assert req(user,'GET','pdm/refresh/status')['status']=='partial'
            plan=req(user,'GET','pdm/analysis-plan')
            assert plan['indicators'][0]['document_ids']==[ids['D']]
            assert len(calls)==1 and calls[0][0]=='D'
            with tenant_context(project),connection() as conn:
                model=conn.execute('SELECT model FROM pdm_models').fetchone()['model']
            assert [i['actual'] for i in model['performance_indicators']]==['70명','40명']
        print('PASS browser C->1-1 and A->1-2 only; old pairs excluded; prior evaluation supplied; cumulative results; no-op blocked; failed pairs remain pending',flush=True)
finally:
    pool.close()
    with psycopg.connect(admin_url,autocommit=True) as conn:
        conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
