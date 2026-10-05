"""Queue model and cancellation tests in an isolated database."""
import os
import uuid
from urllib.parse import urlsplit, urlunsplit
from unittest.mock import patch
import psycopg
from psycopg import sql

assert os.environ.get('KODAME_INTAKE_CONTROL_TEST') == '1'
name = 'kodame_control_' + uuid.uuid4().hex[:12] + '_test'
admin_url = os.environ['ADMIN_DATABASE_URL']
with psycopg.connect(admin_url, autocommit=True) as conn:
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
for key in ('DATABASE_URL','ADMIN_DATABASE_URL'):
    os.environ[key] = urlunsplit(urlsplit(os.environ[key])._replace(path='/' + name))
os.environ['DATA_DIR'] = '/tmp/' + name
os.environ['KODAME_BOOTSTRAP_PASSWORD'] = 'IsolatedTestOnly2026!'
from fastapi.testclient import TestClient
from kodame_intake import main, worker
from kodame_intake.db import connection, tenant_context, pool
from kodame_intake.llm_models import ALLOWED_MODEL_IDS, current_llm_model
from kodame_intake.intake_control import check

def req(client, method, path, status=200, **kwargs):
    response = client.request(method,'/api/v2/'+path,**kwargs)
    assert response.status_code == status, (path,response.status_code,response.text[:500])
    return response.json()

try:
    with TestClient(main.app) as admin:
        req(admin,'POST','auth/login',json={'email':'admin','password':os.environ['KODAME_BOOTSTRAP_PASSWORD']})
        project = req(admin,'POST','admin/projects',201,json={'name':'Queue QA','supported_locales':['ko'],'default_locale':'ko'})['id']
        account = req(admin,'POST','admin/accounts',201,json={'username':'queueqa','display_name':'Queue QA','project_id':project})
        user = TestClient(main.app)
        req(user,'POST','auth/login',json={'email':'queueqa','password':account['initial_password']})
        document = req(user,'POST','intake/uploads?role=project_plan',202,files={'files':('plan.txt',b'Queue test only','text/plain')})['accepted'][0]['id']
        path = f'intake/jobs/{document}'
        req(user,'POST',path+'/cancel',202)
        with tenant_context(system=True):
            assert worker.claim_next() is None
        req(user,'POST',path+'/retry',202)
        first, second = list(ALLOWED_MODEL_IDS)[:2]
        with tenant_context(system=True), connection() as conn:
            conn.execute('UPDATE projects SET llm_model=%s WHERE id=%s',(second,project))
            conn.execute('UPDATE intake_documents SET analysis_model=%s WHERE id=%s',(first,document))
        with tenant_context(system=True):
            row = worker.claim_next()
        assert str(row['id']) == document
        def cancel_during_analysis(row):
            assert current_llm_model() == second
            worker.update_stage(row['id'],'analyzing',55,'test')
            result = req(user,'POST',path+'/cancel',202)
            assert result['cancel_requested'] and result['status']=='processing'
            req(user,'POST',path+'/retry',409)
            check()
            raise AssertionError('Cancelled result must never be applied')
        with tenant_context(project), patch.object(worker,'_process',side_effect=cancel_during_analysis):
            worker.process(row)
        result = req(user,'GET',path)
        assert result['status']=='cancelled' and result['analysis_model']==second
        req(user,'POST',path+'/retry',202)
        with tenant_context(system=True), connection() as conn:
            conn.execute('UPDATE projects SET llm_model=%s WHERE id=%s',(first,project))
        with tenant_context(system=True):
            next_row = worker.claim_next()
        # A stale previous attempt cannot affect the newly claimed request.
        with tenant_context(project), patch.object(worker,'_process') as stale:
            worker.process(row)
            stale.assert_not_called()
        def finish(row):
            assert current_llm_model() == first
            check()
            with connection() as conn:
                check(conn,lock=True)
                conn.execute("UPDATE intake_documents SET status='completed',progress=100 WHERE id=%s",(row['id'],))
        with tenant_context(project), patch.object(worker,'_process',side_effect=finish):
            worker.process(next_row)
        assert req(user,'GET',path)['status']=='completed'
        req(user,'POST',path+'/cancel',409)
        print('PASS queue cancellation, live model at start/retry, in-flight discard, retry fence, stale attempt isolation, completed protection',flush=True)
        from playwright.sync_api import sync_playwright, expect
        with tenant_context(system=True), connection() as conn:
            conn.execute("UPDATE intake_documents SET status='queued',cancel_requested=false WHERE id=%s",(document,))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True,args=['--no-sandbox'])
            page = browser.new_page()
            page.set_content('<div id="trayLive"></div><div id="trayJobs"></div>')
            page.expose_function('control', lambda id, action: req(user,'POST',f'intake/jobs/{id}/{action}',202))
            page.add_script_tag(path='/workspace/assets/service-job-tray.js')
            page.evaluate('''() => ServiceJobTray.configure(async(id,action)=>{
                const result=await control(id,action);ServiceJobTray.syncIntake([result]);})''')
            page.evaluate('(doc)=>ServiceJobTray.syncIntake([doc])',req(user,'GET',path))
            page.get_by_role('button',name='중지',exact=True).click()
            expect(page.locator('#trayJobs')).to_contain_text('중지됨')
            page.get_by_role('button',name='재요청',exact=True).click()
            expect(page.locator('#trayJobs')).to_contain_text('재시도 대기')
            expect(page.get_by_role('button',name='중지',exact=True)).to_be_enabled()
            browser.close()
        print('PASS browser tray stop and re-request use real APIs',flush=True)
        # Exercise real worker routing for ambiguous uploads and artifact registration.
        from kodame_intake import intake_triage
        from kodame_intake.openrouter import AnalysisError
        mixed = {'kind':'mixed','confidence':.65,'reason':'책과 사업 실적이 섞임','needs_review':True,
                 'title':'Chapter','summary':'제출된 책 일부','is_excerpt':'yes'}
        with tenant_context(system=True), connection() as conn:
            conn.execute("UPDATE intake_documents SET upload_role='evidence',status='queued',intake_mode='auto',triage=NULL,analysis=NULL,extracted_path=NULL WHERE id=%s",(document,))
        with tenant_context(system=True):
            row = worker.claim_next()
        with tenant_context(project), patch.object(intake_triage,'classify',return_value=mixed), patch.object(worker,'analyze_document') as full:
            worker.process(row)
            full.assert_not_called()
        result=req(user,'GET',path)
        assert result['status']=='awaiting_review' and result['triage']['kind']=='mixed'
        req(user,'PUT',path+'/mode',409,json={'mode':'artifact','expected_updated_at':'old'})
        req(user,'PUT',path+'/mode',202,json={'mode':'artifact','expected_updated_at':result['updated_at']})
        with tenant_context(system=True):
            row=worker.claim_next()
        with tenant_context(project), patch.object(worker,'analyze_document') as full, \
             patch('kodame_intake.evidence_matching.match_foundations',side_effect=AnalysisError('invalid quote')), \
             patch.object(intake_triage,'_request_json',return_value=({'dac_slots':[{'slot_id':'effectiveness-outputs','confidence':.9,'reason':'test','evidence_quote':'invented quotation'}],'report_sections':[]},'test')):
            worker.process(row)
            full.assert_not_called()
        result=req(user,'GET',path)
        assert result['status']=='completed' and result['intake_mode']=='artifact', result
        assert result['registration']['is_excerpt']=='yes' and not result['registration']['project_production_verified']
        assert len(result['intake_warnings'])>=3
        with tenant_context(project),connection() as conn:
            assert not conn.execute('SELECT 1 FROM document_slot_assignments WHERE document_id=%s',(document,)).fetchone()
        req(user,'PUT',path+'/mode',202,json={'mode':'evidence','expected_updated_at':result['updated_at']})
        with tenant_context(system=True):
            row=worker.claim_next()
        with tenant_context(project), patch.object(worker,'analyze_document',return_value={'summary':'test','section_matches':[],'content_classification':{'version':'content-roles-v1','slot_matches':[]}}) as full, \
             patch('kodame_intake.evidence_matching.match_foundations',return_value={'sources':{},'project_plan':[],'pdm':[]}):
            worker.process(row)
            full.assert_called_once()
        assert req(user,'GET',path)['intake_mode']=='evidence'
        print('PASS ambiguous triage pauses; explicit mode change; artifact skips full analysis and survives bad quotes; evidence override restores analysis',flush=True)
        # Real scheduler + DB claiming with four simultaneous, isolated attempts.
        import threading
        import time
        from kodame_intake.db import current_project_id, current_account_id
        second_project=req(admin,'POST','admin/projects',201,json={'name':'Parallel QA','supported_locales':['ko'],'default_locale':'ko'})['id']
        second_account=req(admin,'POST','admin/accounts',201,json={'username':'parallelqa','display_name':'Parallel QA','project_id':second_project})
        expected={}
        identifiers=[uuid.uuid4() for _ in range(6)]
        with tenant_context(system=True),connection() as conn:
            conn.execute('UPDATE projects SET llm_model=%s WHERE id=%s',(second,second_project))
            for index,identifier in enumerate(identifiers):
                owner_project,owner,model=(project,account['id'],first) if index%2==0 else (second_project,second_account['id'],second)
                role='project_plan' if index==4 else 'evidence'
                expected[str(identifier)]=(owner_project,owner,model,index)
                conn.execute('''INSERT INTO intake_documents(id,project_id,uploaded_by_account_id,original_name,stored_path,extension,size_bytes,sha256,upload_role)
                    VALUES(%s,%s,%s,'parallel.txt','/tmp/isolated-parallel.txt','.txt',1,%s,%s)''',(identifier,owner_project,owner,str(identifier).replace('-','').ljust(64,'0'),role))
        stop=threading.Event(); barrier=threading.Barrier(4,timeout=15); guard=threading.Lock()
        active=set(); seen=[]; maximum=[0]; errors=[]
        def parallel_analysis(row):
            identity=str(row['id']); owner_project,owner,model,index=expected[identity]
            assert str(current_project_id())==owner_project
            assert str(current_account_id())==owner
            assert current_llm_model()==model
            with guard:
                active.add(identity); seen.append(identity); maximum[0]=max(maximum[0],len(active))
                if index==4: assert len(active)==1 and len(seen)==5
                if index==5: assert str(identifiers[4]) in seen and len(active)==1
            if index<4: barrier.wait()
            time.sleep(.05)
            check()
            with connection() as conn:
                check(conn,lock=True)
                conn.execute("UPDATE intake_documents SET status='completed',progress=100 WHERE id=%s",(row['id'],))
            with guard: active.remove(identity)
            if index==5: stop.set()
        def queue_runner():
            try: worker.run_queue(stop,concurrency=4)
            except BaseException as exc: errors.append(exc); stop.set()
        with patch.object(worker,'_process',side_effect=parallel_analysis),patch.object(worker,'WORKER_POLL_SECONDS',.05):
            scheduler=threading.Thread(target=queue_runner,daemon=True); scheduler.start(); scheduler.join(25)
            stop.set(); scheduler.join(5)
        assert not scheduler.is_alive() and not errors, errors
        assert maximum[0]==4 and len(seen)==6 and len(set(seen))==6, (maximum,seen)
        with tenant_context(system=True),connection() as conn:
            assert conn.execute("SELECT count(*) n FROM intake_documents WHERE id=ANY(%s) AND status='completed'",(identifiers,)).fetchone()['n']==6
        assert req(user,'GET','intake/jobs')['worker_concurrency']==4
        print('PASS actual four-thread concurrency, tenant/account/model isolation, no duplicate claims, exclusive foundation barrier and advertised capacity',flush=True)
        # Permission checks apply to both controls.
        with tenant_context(system=True), connection() as conn:
            conn.execute("UPDATE accounts SET menu_permissions='{" + '"evidence_upload":false' + "}'::jsonb WHERE id=%s",(account['id'],))
        req(user,'POST',path+'/cancel',403)
        req(user,'POST',path+'/retry',403)
        print('PASS upload permission required for cancellation and retry',flush=True)
finally:
    pool.close()
    with psycopg.connect(admin_url,autocommit=True) as conn:
        conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
