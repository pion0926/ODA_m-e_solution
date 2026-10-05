"""Run the user-authorized development evaluation without changing credentials/data."""
import json
import time
from pathlib import Path

from kodame_intake.db import open_pool, connection, tenant_context
from kodame_intake.evaluation_runner import _run_all
from kodame_intake.llm_models import llm_model_context
from kodame_intake.project_ai import get_project_model
from kodame_intake.project_lifecycle import lock_project_workflow, active_workflow_jobs
from kodame_intake.main import latest_evaluations

open_pool()
with tenant_context(system=True), connection() as conn:
    rows=conn.execute("""SELECT a.id AS account_id,p.id AS project_id FROM accounts a
        JOIN project_members m ON m.account_id=a.id JOIN projects p ON p.id=m.project_id
        WHERE lower(a.email)='user01@kodame.local' AND NOT p.is_bootstrap""").fetchall()
assert len(rows)==1, 'user01 must have one unambiguous non-bootstrap project'
account_id,project_id=rows[0]['account_id'],rows[0]['project_id']
assert str(project_id)=='05460961-f12e-4fe7-ba6f-3e36e27bd23d', 'Development project guard'
output=Path('/app/data/qa/dac-20260918')
output.mkdir(parents=True,exist_ok=True)
from kodame_intake import dac_assessor
original_request=dac_assessor._request_json
response_count=0
def reviewed_request(system,prompt,title,**kwargs):
    global response_count
    result=original_request(system,prompt,title,**kwargs)
    response_count+=1
    (output/f'adjudication-{response_count}.json').write_text(json.dumps(result[0],ensure_ascii=False,indent=2),encoding='utf-8')
    return result
dac_assessor._request_json=reviewed_request
with tenant_context(project_id,account_id=account_id):
    with connection() as conn,conn.transaction():
        lock_project_workflow(conn)
        assert not active_workflow_jobs(conn), 'Another workflow is running'
    model=get_project_model(project_id)
    with llm_model_context(model):
        for label in ('first','repeat'):
            started=time.monotonic()
            run_id=_run_all()
            result=latest_evaluations()
            (output/f'{label}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            summary={'run_id':str(run_id),'seconds':round(time.monotonic()-started,1),'model':model,
                     'reused_from':result.get('reused_from_run_id'),
                     'scores':{c['id']:c['score'] for c in result['criteria']},
                     'questions':[{ 'id':q['question_id'],'score':q['score'],
                         'coverage':q['scoring_trace']['coverage'],'confidence':q['scoring_trace']['confidence'],
                         'status':q['scoring_trace']['status'], 'citations':len(q['evidence_quotes'])}
                         for c in result['criteria'] for q in c['question_assessments']]}
            print(json.dumps(summary,ensure_ascii=False),flush=True)
            if label=='first':
                first=result
            else:
                assert result['criteria']==first['criteria'], 'Identical inputs must preserve all scores and explanations'
                assert result['reused_from_run_id']==first['run_id'], 'Replay must be transparent'
                print('REPEAT_IDENTICAL_PASS',flush=True)
