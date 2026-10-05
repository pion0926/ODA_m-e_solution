"""Probe a single live user01 question against the saved source index."""
import json
import sys
from pathlib import Path
from kodame_intake.db import pool, connection, tenant_context
from kodame_intake.evaluation_runner import _load_documents, _corpus
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA
from kodame_intake.assessment_context import assessment_scope
from kodame_intake.dac_assessor import assess_criterion
from kodame_intake.llm_models import llm_model_context
from kodame_intake.project_ai import get_project_model
from kodame_intake import openrouter
from kodame_intake import dac_assessor

original_request=dac_assessor._request_json
response_number=0
def saved_request(*args,**kwargs):
    global response_number
    result=original_request(*args,**kwargs)
    response_number+=1
    Path(f'/app/data/qa/dac-20260918/probe-response-{response_number}.json').write_text(
        json.dumps(result[0],ensure_ascii=False,indent=2),encoding='utf-8')
    return result
dac_assessor._request_json=saved_request

original_client=openrouter.httpx.Client
def diagnostic_client(**kwargs):
    def inspect(response):
        if response.status_code>=400:
            response.read()
            print('PROVIDER_ERROR '+response.text[:6000],flush=True)
    return original_client(**kwargs,event_hooks={'response':[inspect]})
openrouter.httpx.Client=diagnostic_client

pool.open()
project='05460961-f12e-4fe7-ba6f-3e36e27bd23d'
account='3241f771-5346-47a9-a472-4018f8d62809'
qid=sys.argv[1] if len(sys.argv)>1 else 'relevance-q1'
cid=qid.split('-q')[0]
with tenant_context(project,account_id=account),llm_model_context(get_project_model(project)):
    with connection() as conn:
        pdm=conn.execute('SELECT input_snapshot FROM evaluation_runs ORDER BY started_at DESC LIMIT 1').fetchone()['input_snapshot']['pdm_context']
        overview=conn.execute('SELECT overview FROM project_overviews ORDER BY created_at DESC LIMIT 1').fetchone()['overview']
    docs=_load_documents()
    for doc in docs:
        doc['fulltext_review']=doc['dac_fulltext_cache']
    corpus,_=_corpus(cid,docs)
    criterion=EVALUATION_CRITERIA[cid]
    criterion={**criterion,'questions':[q for q in criterion['questions'] if q['id']==qid]}
    result=assess_criterion(cid,criterion,corpus,assessment_scope(overview),pdm)
    path=Path('/app/data/qa/dac-20260918')/f'probe-{qid}.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'qid':qid,'score':result['score'],'path':str(path)},ensure_ascii=False))
