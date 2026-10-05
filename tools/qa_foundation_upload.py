"""Foundation upload integration against a disposable database; no external AI calls."""
import os
import uuid
from urllib.parse import urlsplit, urlunsplit
from unittest.mock import patch
from pathlib import Path
import threading
import time
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

assert os.environ.get('KODAME_FOUNDATION_TEST') == '1'
name = 'kodame_foundation_' + uuid.uuid4().hex[:12] + '_test'
admin_url = os.environ['ADMIN_DATABASE_URL']
with psycopg.connect(admin_url, autocommit=True) as conn:
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
for key in ('DATABASE_URL', 'ADMIN_DATABASE_URL'):
    os.environ[key] = urlunsplit(urlsplit(os.environ[key])._replace(path='/' + name))
os.environ['DATA_DIR'] = '/tmp/' + name
os.environ['KODAME_BOOTSTRAP_PASSWORD'] = 'IsolatedTestOnly2026!'
os.environ['WORKER_STEP_DELAY_SECONDS'] = '0'

from fastapi.testclient import TestClient
from kodame_intake import main, worker
from kodame_intake.db import connection, tenant_context, pool, open_pool
from kodame_intake.foundation import state


def req(client, method, path, status=200, **kwargs):
    response = client.request(method, '/api/v2/' + path, **kwargs)
    assert response.status_code == status, (path, response.status_code, response.text[:500])
    return response.json()


def upload(client, role='evidence', file='document.txt', replaces='', status=202):
    result = req(client, 'POST', f'intake/uploads?role={role}&replaces={replaces}', status,
                 files={'files': (file, b'Foundation document test text', 'text/plain')})
    if status == 202:
        assert result['accepted'] and not result['rejected'], result
        return result['accepted'][0]
    return result


def finish(project, document):
    with tenant_context(project), connection() as conn:
        row = conn.execute('SELECT * FROM intake_documents WHERE id=%s', (document['id'],)).fetchone()
    role = row['upload_role']
    result = {'summary': 'test', 'section_matches': [], 'dac_criteria': [], 'upload_role': role,
              'content_classification': {'version': 'content-roles-v1', 'document_type': '보고서',
                  'is_project_plan': role == 'project_plan', 'is_pdm_source': role == 'pdm',
                  'slots': {'outcome_indicator': '1. Training completion 80%', 'outcome_mov': '1. Completion list'} if role == 'pdm' else {},
                  'slot_matches': []}}
    matches = {'version': 1, 'sources': {}, 'project_plan': [], 'pdm': []}
    if role == 'evidence':
        from kodame_intake.evidence_matching import foundation_context
        with tenant_context(project):
            matches['sources'] = foundation_context()['sources']
        matches['project_plan'] = [{'topic': 'Training', 'confidence': .9, 'rationale': 'plan match'}]
        matches['pdm'] = [{'indicator_id': 'outcome-1', 'indicator': 'Training completion 80%',
                          'tier': 'outcome', 'requirement_title': 'Completion list', 'confidence': .9, 'rationale': 'PDM match'}]
        from kodame_intake.taxonomy import SECTION_BY_ID
        number, _, title, _ = SECTION_BY_ID['project-background']
        result['section_matches'] = [{'section_id': 'project-background', 'section_number': number,
            'section_title': title, 'confidence': .9, 'rationale': 'report match', 'evidence_quote': 'test',
            'category': 'test', 'dac_criterion': 'relevance'}]
    with tenant_context(project), \
         patch('kodame_intake.intake_triage.classify', return_value={'kind':'evidence','confidence':.99,'reason':'test','needs_review':False}), \
         patch.object(worker, 'analyze_document', return_value=result) as analysis, \
         patch('kodame_intake.dac_evidence.analyze_document', return_value={'question_ids': []}) as dac, \
         patch('kodame_intake.evidence_matching.match_foundations', return_value=matches) as matching, \
         patch.object(worker, 'document_slot_matches', return_value=[]), \
         patch.object(worker, 'refresh_pdm_model') as performance, patch.object(worker, 'refresh_project_overview_if_needed') as overview:
        worker._process(row)
        assert analysis.call_args.kwargs['upload_role'] == row['upload_role']
        if row['upload_role'] == 'evidence':
            dac.assert_not_called(); performance.assert_not_called(); overview.assert_not_called()
            matching.assert_called_once()
        else:
            dac.assert_called_once(); performance.assert_called_once(); overview.assert_called_once()
            matching.assert_not_called()


try:
    with TestClient(main.app) as admin:
        req(admin, 'POST', 'auth/login', json={'email': 'admin', 'password': os.environ['KODAME_BOOTSTRAP_PASSWORD']})
        users, projects = [], []
        for index in range(2):
            project = req(admin, 'POST', 'admin/projects', 201, json={'name': f'Foundation QA {index}', 'supported_locales': ['ko'], 'default_locale': 'ko'})
            account = req(admin, 'POST', 'admin/accounts', 201, json={'username': f'foundation{index}', 'display_name': 'QA', 'project_id': project['id']})
            client = TestClient(main.app)
            req(client, 'POST', 'auth/login', json={'email': f'foundation{index}', 'password': account['initial_password']})
            users.append(client); projects.append(project['id'])
        a, b = users
        upload(a, status=409)
        plan = upload(a, 'project_plan', 'plan.txt')
        upload(a, status=409)
        finish(projects[0], plan)
        upload(a, status=409)
        pdm = upload(a, 'pdm', 'pdm.txt')
        upload(a, status=409)
        finish(projects[0], pdm)
        assert req(a, 'GET', 'intake/foundation')['ready']
        evidence = upload(a)
        finish(projects[0], evidence)
        with tenant_context(projects[0]), connection() as conn:
            saved = conn.execute('SELECT analysis FROM intake_documents WHERE id=%s', (evidence['id'],)).fetchone()['analysis']
            assert 'dac_fulltext' not in saved and 'pdm_measurements' not in saved
            assert saved['evidence_matches']['project_plan'] and saved['evidence_matches']['pdm']
            assert saved['evidence_matches']['report_sections'] and not saved['evidence_matches']['dac_slots']
            assert conn.execute('SELECT document_id FROM pdm_document_assignments WHERE document_id=%s', (evidence['id'],)).fetchone()
            assert not conn.execute('SELECT id FROM pdm_models').fetchone()
            assert not conn.execute('SELECT id FROM evaluation_runs').fetchone()
        print('PASS ordinary upload stores independent matches without performance or DAC analysis', flush=True)

        # Exercise the real button endpoints and runners; stub only AI outputs.
        from kodame_intake import pdm_monitoring as monitor, evaluation_runner as runner
        def measurements(document, indicators, **kwargs):
            assert str(document['id']) == evidence['id']
            return [{'indicator_id':indicators[0]['id'],'kind':kind,'value':value,'quote':value,'period':'2025',
                     'document_id':str(document['id']),'file_name':document['original_name']} for kind,value in [('target','80%'),('actual','60%')]]
        with patch('kodame_intake.pdm_evidence.extract_measurements', side_effect=measurements) as performance_ai, \
             patch.object(monitor, '_attach_performance_risk_analysis', return_value={'status': 'completed'}), \
             patch('kodame_intake.dac_evidence._request_json') as dac_ai:
            req(a, 'POST', 'pdm/refresh', 409)
            review = req(a, 'GET', 'pdm/analysis-plan')
            performance_ai.assert_not_called()
            req(a, 'POST', 'pdm/refresh', 409, json={'revision': '0'*64, 'mappings': {'outcome-1': []}})
            req(a, 'POST', 'pdm/refresh', 422, json={'revision': review['revision'], 'mappings': {'outcome-1': [str(uuid.uuid4())]}})
            req(a, 'POST', 'pdm/refresh', 202, json={'revision': review['revision'],
                'mappings': {item['id']: item['document_ids'] for item in review['indicators']}})
            assert req(a, 'GET', 'pdm/refresh/status')['status'] == 'completed'
            performance_ai.assert_called_once(); dac_ai.assert_not_called()
        before_pdm = req(a, 'GET', 'pdm')
        with patch.object(runner, 'generate_project_overview'), \
             patch('kodame_intake.dac_evidence._request_json', return_value=({'evidence': []}, 'test')) as dac_ai, \
             patch.object(runner, 'assess_criterion', return_value={'score': 3, 'summary': 'test', 'score_reason': 'test',
                 'question_assessments': [], 'evidence_gaps': []}), \
             patch.object(monitor, 'refresh_pdm_model') as forbidden_performance:
            dac_plan = req(a, 'GET', 'evaluations/analysis-plan')
            req(a, 'POST', 'evaluations', 202, json={'revision':dac_plan['revision'],
                'mappings':{q['id']:[d['id'] for d in dac_plan['documents']] for q in dac_plan['indicators']}})
            assert req(a, 'GET', 'evaluations/status')['status'] == 'completed'
            assert dac_ai.call_count == 3
            forbidden_performance.assert_not_called()
        assert req(a, 'GET', 'pdm')['performance_indicators'] == before_pdm['performance_indicators']
        print('PASS performance button runs measurements only; DAC button runs fulltext/scoring without updating performance', flush=True)
        assert not req(b, 'GET', 'intake/foundation')['ready']
        upload(b, status=409)
        print('PASS empty/partial/pending/completed gates and tenant isolation', flush=True)

        upload(a, 'project_plan', 'new-plan.txt', status=409)
        upload(a, 'project_plan', 'new-plan.txt', replaces=str(uuid.uuid4()), status=409)
        new = upload(a, 'project_plan', 'new-plan.txt', replaces=plan['id'])
        upload(a, status=409)
        upload(a, 'project_plan', 'concurrent.txt', replaces=new['id'], status=409)
        with tenant_context(projects[0]), connection() as conn:
            assert conn.execute('SELECT id FROM active_intake_documents WHERE id=%s', (plan['id'],)).fetchone()
            conn.execute("UPDATE intake_documents SET status='failed' WHERE id=%s", (new['id'],))
        assert not req(a, 'GET', 'intake/foundation')['ready']
        req(a, 'POST', f"intake/jobs/{new['id']}/retry", 202)
        finish(projects[0], new)
        assert req(a, 'GET', 'intake/foundation')['ready']
        with tenant_context(projects[0]), connection() as conn:
            assert not conn.execute('SELECT id FROM active_intake_documents WHERE id=%s', (plan['id'],)).fetchone()
            assert conn.execute('SELECT superseded_at FROM intake_documents WHERE id=%s', (plan['id'],)).fetchone()['superseded_at']
        download = a.get(f"/api/v2/intake/jobs/{plan['id']}/download")
        assert download.status_code == 200
        print('PASS confirmation, stale confirmation, concurrent replacement, failure/retry and retained originals', flush=True)
        duplicate = upload(a, 'project_plan', 'new-plan.txt', replaces=new['id'])
        assert duplicate['deduplicated']
        reverted = upload(a, 'project_plan', 'plan.txt', replaces=new['id'])
        finish(projects[0], reverted)
        # Restart migration remains idempotent even with duplicate historical files.
        open_pool()
        assert req(a, 'GET', 'intake/foundation')['ready']
        assert req(b, 'GET', 'intake/jobs')['count'] == 0
        print('PASS deduplication, historical re-upload, idempotent migration and view RLS', flush=True)

        # Exercise the actual HTML and live controller against the same isolated API.
        import uvicorn
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse
        from playwright.sync_api import sync_playwright, expect
        main.app.mount('/assets', StaticFiles(directory='/workspace/assets'), name='qa-assets')
        @main.app.get('/')
        def shell():
            return FileResponse('/workspace/frontend/index.html')
        server = uvicorn.Server(uvicorn.Config(main.app, host='127.0.0.1', port=8199, lifespan='off', log_level='error'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 1440, 'height': 1080})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                logged = page.request.post('http://127.0.0.1:8199/api/v2/auth/login', data={
                    'email': 'foundation1', 'password': account['initial_password']})
                assert logged.status == 200
                page.goto('http://127.0.0.1:8199/#/evidence')
                expect(page.locator('#foundationPanel')).to_be_visible()
                expect(page.locator('#bulkFileInput')).to_be_disabled()
                for role, filename in [('project_plan', 'browser-plan.txt'), ('pdm', 'browser-pdm.txt')]:
                    with page.expect_file_chooser() as chooser:
                        page.locator(f'[data-foundation-role="{role}"]').click()
                    chooser.value.set_files({'name': filename, 'mimeType': 'text/plain', 'buffer': b'Foundation browser test'})
                    expect(page.locator('#foundationDocuments')).to_contain_text(filename)
                    expect(page.locator('#bulkFileInput')).to_be_disabled()
                    with tenant_context(projects[1]):
                        doc = state()['documents'][role]
                    finish(projects[1], doc)
                    expect(page.locator(f'[data-foundation-role="{role}"]')).to_be_enabled(timeout=15000)
                expect(page.locator('#bulkFileInput')).to_be_enabled(timeout=15000)
                page.locator('#bulkFileInput').set_input_files({'name': 'browser-evidence.txt', 'mimeType': 'text/plain', 'buffer': b'General evidence'})
                expect(page.locator('#fileRows')).to_contain_text('browser-evidence.txt')
                expect(page.locator('#trayJobs')).to_contain_text('browser-evidence.txt')
                expect(page.locator('#trayJobs')).to_contain_text('분석 대기')
                with tenant_context(projects[1]), connection() as conn:
                    browser_evidence = conn.execute("SELECT id FROM active_intake_documents WHERE original_name='browser-evidence.txt'").fetchone()
                finish(projects[1], {'id': str(browser_evidence['id'])})
                expect(page.locator('#fileRows')).to_contain_text('Training', timeout=15000)
                expect(page.locator('#fileRows')).to_contain_text('보고서')
                matching = page.locator(f'details[data-document-matches="{browser_evidence["id"]}"]')
                expect(matching).not_to_have_attribute('open', '')
                expect(matching.locator('summary')).to_contain_text('매칭')
                matching.locator('summary').click()
                expect(matching).to_have_attribute('open', '')
                page.wait_for_timeout(4000)
                expect(matching).to_have_attribute('open', '')
                matching.locator('summary').click()
                expect(matching).not_to_have_attribute('open', '')
                expect(page.locator('#trayJobs')).to_contain_text('분석 완료')
                page.evaluate("location.hash='#/project/indicators'")
                expect(page.locator('#indRefresh')).to_have_text('✦ 성과지표 분석')
                page.locator('#indRefresh').click()
                review_dialog = page.locator('#performanceReviewDialog')
                expect(review_dialog).to_be_visible()
                expect(review_dialog.locator('[data-review-rows]')).to_contain_text('browser-evidence.txt')
                with tenant_context(projects[1]), connection() as conn:
                    assert not conn.execute('SELECT id FROM pdm_refresh_runs').fetchone()
                review_dialog.locator('[data-review-close]').first.click()
                expect(review_dialog).not_to_be_visible()
                page.locator('#indRefresh').click()
                expect(review_dialog).to_be_visible()
                expect(review_dialog.locator('[data-review-rows]')).to_contain_text('browser-evidence.txt')
                review_dialog.locator(f'[data-review-remove="{browser_evidence["id"]}"]').click()
                with tenant_context(projects[1]):
                    plan_doc = state()['documents']['project_plan']['id']
                review_dialog.locator('select').select_option(plan_doc)
                review_dialog.locator('[data-review-add]').click()
                expect(review_dialog.locator('.performance-document')).to_contain_text('browser-plan.txt')
                with page.expect_file_chooser() as chooser:
                    review_dialog.locator('[data-review-upload]').click()
                chooser.value.set_files({'name': 'performance-extra.txt', 'mimeType': 'text/plain', 'buffer': b'Extra evidence'})
                expect(review_dialog.locator('[data-review-rows]')).to_contain_text('performance-extra.txt')
                expect(review_dialog.locator('[data-review-run]')).to_be_disabled()
                with tenant_context(projects[1]), connection() as conn:
                    extra = conn.execute("SELECT id FROM active_intake_documents WHERE original_name='performance-extra.txt'").fetchone()
                finish(projects[1], {'id': str(extra['id'])})
                expect(review_dialog.locator('[data-review-run]')).to_be_enabled(timeout=15000)
                expected_ids={plan_doc, str(extra['id'])}
                def reviewed_measurements(document, indicators, **kwargs):
                    assert str(document['id']) in expected_ids
                    return []
                output = Path('/qa-output'); output.mkdir(exist_ok=True)
                review_dialog.screenshot(path=str(output / 'performance-review-desktop.png'))
                page.set_viewport_size({'width':390,'height':844})
                review_dialog.screenshot(path=str(output / 'performance-review-mobile.png'))
                page.set_viewport_size({'width':1440,'height':1080})
                with patch('kodame_intake.pdm_evidence.extract_measurements', side_effect=reviewed_measurements) as reviewed_ai, \
                     patch.object(monitor, '_attach_performance_risk_analysis', return_value={'status':'completed'}):
                    review_dialog.locator('[data-review-run]').click()
                    expect(review_dialog).not_to_be_visible(timeout=15000)
                    for _ in range(100):
                        with tenant_context(projects[1]), connection() as conn:
                            run = conn.execute('SELECT status,analysis_plan FROM pdm_refresh_runs ORDER BY started_at DESC LIMIT 1').fetchone()
                        if run and run['status'] not in ('queued','running'):
                            break
                        page.wait_for_timeout(100)
                    assert run['status'] == 'completed', run
                    assert set(run['analysis_plan']['mappings']['outcome-1']) == expected_ids
                    assert reviewed_ai.call_count == 2
                with tenant_context(projects[1]):
                    from kodame_intake.performance_review import build_plan
                    assert set(build_plan()['indicators'][0]['retained_document_ids']) == expected_ids
                    assert build_plan()['indicators'][0]['document_ids'] == []
                print('PASS browser review opens without analysis; mapping add/remove, inline upload/wait, exact reviewed execution and persisted mappings', flush=True)
                page.evaluate("location.hash='#/evidence'")
                # Cancelling the second confirmation must not submit a replacement.
                page.once('dialog', lambda dialog: dialog.dismiss())
                with page.expect_file_chooser() as chooser:
                    page.locator('[data-foundation-role="project_plan"]').click()
                with page.expect_event('dialog'):
                    chooser.value.set_files({'name': 'cancelled.txt', 'mimeType': 'text/plain', 'buffer': b'Cancelled'})
                expect(page.locator('#foundationFileInput')).to_have_value('')
                expect(page.locator('#bulkFileInput')).to_be_enabled(timeout=15000)
                with tenant_context(projects[1]):
                    assert state()['documents']['project_plan']['original_name'] == 'browser-plan.txt'
                page.once('dialog', lambda dialog: dialog.accept())
                with page.expect_file_chooser() as chooser:
                    page.locator('[data-foundation-role="project_plan"]').click()
                with page.expect_event('dialog'):
                    chooser.value.set_files({'name': 'confirmed.txt', 'mimeType': 'text/plain', 'buffer': b'Confirmed'})
                expect(page.locator('#foundationDocuments')).to_contain_text('confirmed.txt')
                expect(page.locator('#bulkFileInput')).to_be_disabled()
                expect(page.locator('#cntAll')).to_have_text('5건')
                expect(page.locator('#fileRows')).to_contain_text('Training completion 80%')
                output = Path('/qa-output'); output.mkdir(exist_ok=True)
                page.evaluate('window.scrollTo(0, 0)')
                page.screenshot(path=str(output / 'foundation-upload-desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                page.evaluate('window.scrollTo(0, 0)')
                page.screenshot(path=str(output / 'foundation-upload-mobile.png'), full_page=True)
                assert not errors, errors
                # A mixed book waits for an explicit choice in the actual upload UI.
                with tenant_context(projects[1]), connection() as conn:
                    conn.execute("UPDATE intake_documents SET status='awaiting_review',triage=%s WHERE id=%s", (Jsonb({'kind':'mixed','reason':'책과 실적이 함께 있어 선택이 필요합니다.','needs_review':True,'title':'Book chapter','is_excerpt':'yes'}), browser_evidence['id']))
                choice = page.locator(f'[data-triage="{browser_evidence["id"]}"]')
                expect(choice).to_have_attribute('open','',timeout=15000)
                expect(choice).to_contain_text('선택이 필요')
                choice.locator('[data-intake-mode="artifact"]').click()
                expect(choice.locator('summary')).to_contain_text('산출물 등록')
                with tenant_context(projects[1]), connection() as conn:
                    selected = conn.execute('SELECT intake_mode,status FROM intake_documents WHERE id=%s',(browser_evidence['id'],)).fetchone()
                    assert selected['intake_mode']=='artifact' and selected['status']=='queued', selected
                print('PASS browser uncertain triage shows reason and explicit artifact selection queues correct mode',flush=True)
                browser.close()
                print('PASS browser upload gates, independent file matching display, replacement cancel/confirm, desktop/mobile rendering', flush=True)
        finally:
            server.should_exit = True
            thread.join(timeout=10)
finally:
    pool.close()
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
