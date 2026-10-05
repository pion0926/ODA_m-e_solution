"""Run only in the isolated scope-test DB; AI is stubbed, source files are synthetic."""
import os
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

assert os.getenv('KODAME_ISOLATED_TEST') == '1'
assert urlparse(os.environ['DATABASE_URL']).path == '/kodame_scope_isolated_test'
from fastapi.testclient import TestClient
from kodame_intake.main import app
from kodame_intake import worker
from kodame_intake.db import connection, tenant_context
from kodame_intake.project_lifecycle import capture_input_snapshot


def req(client, method, path, code=200, **kwargs):
    response = client.request(method, '/api/v2'+path, **kwargs)
    assert response.status_code == code, (path,response.status_code,response.text[:600])
    return response.json()


def check(value, label):
    assert value, label
    print('PASS '+label,flush=True)


with TestClient(app) as admin:
    req(admin,'POST','/auth/login',json={'email':'admin','password':os.environ['KODAME_BOOTSTRAP_PASSWORD']})
    project = req(admin,'POST','/admin/projects',201,json={'name':'평가 제외 격리 검증','supported_locales':['ko'],'default_locale':'ko'})['id']
    name='scope_'+uuid.uuid4().hex[:8]
    issued=req(admin,'POST','/admin/accounts',201,json={'username':name,'display_name':'범위 검증','project_id':project})
    user=TestClient(app)
    req(user,'POST','/auth/login',json={'email':name,'password':issued['initial_password']})
    text=('사업설계매트릭스 영향 성과 산출물 검증지표 검증수단 가정. 목표 교육강사 10명.\n'*8)

    def upload(name, body, role='evidence'):
        return req(user,'POST',f'/intake/uploads?role={role}',202,files={'files':(name,body.encode(),'text/plain')})['accepted'][0]

    def process(doc, *, excluded=False, expect_skip=False):
        with tenant_context(project):
            row=worker.claim_next()
            assert str(row['id'])==doc['id']
        triage={'kind':'evidence','confidence':.99,'reason':'테스트 분류',
                'evaluation_scope':{'version':'intake-eligibility-v1','origin':'automatic','excluded':excluded,
                    'code':'alternate_pdm' if excluded else 'included','reason':'별도 기준 PDM 설계본' if excluded else '실적 증빙 포함'}}
        analysis={'upload_role':doc['upload_role'],'summary':'테스트 요약','section_matches':[],
                  'content_classification':{'version':'content-roles-v1','slots':{},'slot_matches':[]},'dac_criteria':[]}
        with patch.object(worker,'analyze_document',return_value=analysis) as analyze, \
             patch('kodame_intake.intake_triage.classify',return_value=triage), \
             patch('kodame_intake.dac_evidence.analyze_document',return_value={'question_ids':[]}), \
             patch('kodame_intake.foundation_facts.extract_plan_facts',return_value={'facts':[]}), \
             patch('kodame_intake.evidence_matching.match_foundations',return_value={'pdm':[],'sources':{},'registration_facts':{}}), \
             patch.object(worker,'refresh_uploaded_foundation'):
            worker.process_in_tenant(row)
            if expect_skip: analyze.assert_not_called()
        saved=req(user,'GET',f"/intake/jobs/{doc['id']}")
        check(saved['status']=='completed','upload completed: '+doc['file_name'])
        return saved

    plan=upload('기준계획서.txt','사업계획서 사업기간 2025~2026. 사업 예산 1억원. 교육 사업.', 'project_plan')
    process(plan)
    pdm=upload('기준PDM.txt',text,'pdm'); process(pdm)
    check(req(user,'GET','/intake/foundation')['ready'],'foundation gate ready')
    with tenant_context(project),connection() as conn: baseline=capture_input_snapshot(conn)

    dupe=upload('PDM 복사본.txt',text)
    saved=process(dupe,expect_skip=True)
    check(saved['evaluation_excluded'] and saved['evaluation_scope']['code']=='duplicate','binary duplicate excluded without AI')
    with tenant_context(project),connection() as conn:
        check(capture_input_snapshot(conn)==baseline,'excluded upload does not invalidate current evaluation inputs')
        record=conn.execute('SELECT stored_path FROM intake_documents WHERE id=%s',(dupe['id'],)).fetchone()
    check(Path(record['stored_path']).read_text()==text,'excluded original preserved')

    textcopy=upload('형식다른PDM.txt',text.replace(' ','  '))
    copied=process(textcopy,expect_skip=True)
    check(copied['evaluation_excluded'] and copied['has_extracted_text'],'normalized exact content excluded after parsing')
    old=upload('구버전설계.txt',text+'옛 설계 버전')
    old_saved=process(old,excluded=True,expect_skip=True)
    check(old_saved['evaluation_excluded'],'triage exclusion skips detailed analysis')
    report=upload('2024실적보고서.txt','2024년도 교육 실적 6명. 당시 4명은 미수료했다. 과거 실적은 현재 목표와 구분한다.')
    included=process(report)
    check(not included['evaluation_excluded'],'historical/adverse evidence preserved')
    with tenant_context(project),connection() as conn:
        ids={str(r['id']) for r in conn.execute('SELECT id FROM evaluation_intake_documents').fetchall()}
    check(ids=={plan['id'],pdm['id'],report['id']},'evaluation view excludes archive but retains foundations')
    check(req(user,'GET','/intake/jobs')['total']==6,'upload inventory includes archived originals')
    for endpoint in ('/pdm/analysis-plan','/evaluations/analysis-plan'):
        response=user.get('/api/v2'+endpoint)
        if response.status_code==200:
            check(all(doc['id'] not in {dupe['id'],old['id'],textcopy['id']} for doc in response.json()['documents']),endpoint+' excludes archived candidates')
        else:
            assert endpoint=='/evaluations/analysis-plan' and response.status_code==404

    foundation=req(user,'GET',f"/intake/jobs/{pdm['id']}")
    req(user,'PUT',f"/intake/jobs/{pdm['id']}/evaluation-scope",409,json={'excluded':True,'reason':'제외 시도','expected_updated_at':foundation['updated_at']})
    restored=req(user,'PUT',f"/intake/jobs/{old['id']}/evaluation-scope",json={'excluded':False,'reason':'변경 이력 검토에 사용','expected_updated_at':old_saved['updated_at']})
    check(restored['status']=='queued' and not restored['evaluation_excluded'],'manual restore queues required analysis')
    restored=process(old,excluded=True)
    check(not restored['evaluation_excluded'] and restored['evaluation_scope']['origin']=='manual','manual inclusion survives automatic exclusion suggestion')
    req(user,'PUT',f"/intake/jobs/{old['id']}/evaluation-scope",409,json={'excluded':True,'reason':'stale','expected_updated_at':old_saved['updated_at']})
    before_exclusion=restored['updated_at']
    archived=req(user,'PUT',f"/intake/jobs/{old['id']}/evaluation-scope",json={'excluded':True,'reason':'이력 검토 완료 후 제외','expected_updated_at':before_exclusion})
    check(archived['evaluation_excluded'],'manual exclusion reversible')
    other_project=req(admin,'POST','/admin/projects',201,json={'name':'격리 다른 계정','supported_locales':['ko'],'default_locale':'ko'})['id']
    other_name='scope_other_'+uuid.uuid4().hex[:8]
    other_account=req(admin,'POST','/admin/accounts',201,json={'username':other_name,'display_name':'다른 사용자','project_id':other_project})
    other=TestClient(app); req(other,'POST','/auth/login',json={'email':other_name,'password':other_account['initial_password']})
    req(other,'PUT',f"/intake/jobs/{old['id']}/evaluation-scope",404,json={'excluded':False,'reason':'침범 시도','expected_updated_at':archived['updated_at']})
    with tenant_context(other_project),connection() as conn:
        check(not conn.execute('SELECT id FROM evaluation_intake_documents').fetchall(),'evaluation view preserves tenant RLS')
    print('SCOPE INTEGRATION COMPLETE',flush=True)
