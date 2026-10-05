"""Opt-in real-provider check of the two reported failed windows.

Reads existing project files. Does not overwrite document caches/evaluations;
normal provider token usage is recorded against the project owner.
"""
import os
from pathlib import Path
from unittest.mock import patch
from kodame_intake.db import connection,pool,tenant_context
from kodame_intake.llm_models import llm_model_context
from kodame_intake import dac_evidence
from kodame_intake.evaluation_criteria import EVALUATION_CRITERIA

assert os.environ.get('KODAME_DAC_LIVE_RECOVERY')=='1'
pool.open(wait=True)
try:
    with tenant_context(system=True),connection() as conn:
        run=conn.execute("SELECT * FROM evaluation_runs WHERE status='failed' AND error_message LIKE '%%DAC%%' ORDER BY started_at DESC LIMIT 1").fetchone()
        assert run,'No failed DAC run'
        owner=conn.execute('SELECT owner_account_id FROM projects WHERE id=%s',(run['project_id'],)).fetchone()['owner_account_id']
    with tenant_context(run['project_id'],account_id=owner),llm_model_context(run['model']):
        for keyword,start,end in [('5차년도 사업계획서',36000,41000),('현장실습기록지작성',23000,48000)]:
            with connection() as conn:
                row=conn.execute("SELECT * FROM active_intake_documents WHERE original_name LIKE %s AND status='completed' ORDER BY queue_position DESC LIMIT 1",('%'+keyword+'%',)).fetchone()
            assert row,'Reported document missing'
            text=Path(row['extracted_path']).read_text(encoding='utf-8')
            assert len(text)>=end,'Original failed range unavailable'
            questions={q['id']:{'mode':'focused','ranges':[[start,end]]}
                       for c in EVALUATION_CRITERIA.values() for q in c['questions']}
            doc={'id':str(row['id']),'name':'reported-window','assigned_criteria':list(EVALUATION_CRITERIA),
                 'extracted_path':row['extracted_path'],'scope_text':text,'question_scopes':questions,
                 'sha256':row['sha256']}
            with patch.object(dac_evidence,'connection'):
                result=dac_evidence.analyze_document(doc)
            assert result['status']=='completed'
            evidence=[e for c in result['chunks'] for e in c['evidence']]
            assert all(e.get('source_id') and len(e['quote'])<=800 for e in evidence)
            print(f'PASS real provider {run["model"]} range={start}:{end} chunks={len(result["chunks"])} evidence={len(evidence)}',flush=True)
finally:
    pool.close()
