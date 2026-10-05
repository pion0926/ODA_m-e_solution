"""Replay one known metric sheet without changing document caches or evaluations."""
import json
import sys
from unittest.mock import patch, MagicMock
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.llm_models import llm_model_context
from kodame_intake.project_ai import get_project_model
from kodame_intake import pdm_evidence

if '--candidate' in sys.argv:
    import importlib.util
    spec=importlib.util.spec_from_file_location('kodame_intake.pdm_evidence',sys.argv[sys.argv.index('--candidate')+1])
    pdm_evidence=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pdm_evidence)

pool.open(wait=True)
try:
    with tenant_context(system=True), connection() as conn:
        doc=conn.execute("SELECT * FROM active_intake_documents WHERE original_name LIKE '%5차년도 지표별 실적 현황%' AND status='completed' ORDER BY queue_position DESC LIMIT 1").fetchone()
    with tenant_context(doc['project_id']), connection() as conn:
        snapshot=conn.execute('SELECT model FROM pdm_models ORDER BY created_at DESC LIMIT 1').fetchone()['model']
        indicators=[i for i in snapshot['performance_indicators'] if str(doc['id']) in i['evidence_document_ids']]
        original=pdm_evidence._request_measurements
        def capture(*args,**kwargs):
            if '--explain' in sys.argv:
                args=list(args)
                args[0] += ' 각 지표를 빠짐없이 검토하고 reviews 배열에 indicator_id와 해당 목표·실적 값이 있는지, 없다고 판단한 구체적 이유를 한국어로 추가한다. 표의 목표/실적 열을 구분한다. 지표의 검증수단은 우선 자료이지 유일하게 허용된 파일 종류가 아니다. 동일 지표의 실적현황표에 명시된 직접 보고 수치도 추출한다.'
            result=original(*args,**kwargs)
            print(json.dumps({'raw_measurements':result[0]},ensure_ascii=False),flush=True)
            return result
        doc['analysis']={}
        with llm_model_context(get_project_model()), patch.object(pdm_evidence,'connection',MagicMock()), patch.object(pdm_evidence,'_request_measurements',side_effect=capture):
            accepted=pdm_evidence.extract_measurements(doc,indicators,previous_evaluation={})
        print(json.dumps({'accepted':accepted,'evaluation_writes':0},ensure_ascii=False))
finally:
    pool.close()
