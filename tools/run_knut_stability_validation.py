"""Authorized production validation of PDM then DAC, using normal workflow locks."""
import json
import os
import uuid
from kodame_intake.db import open_pool, connection, tenant_context
from kodame_intake.project_ai import get_project_model
from kodame_intake.llm_models import llm_model_context
from kodame_intake.main import _reserve_project_workflow
from kodame_intake.pdm_jobs import run_refresh, serialize
from kodame_intake.evaluation_runner import run_all

assert os.environ.get('SESSION_COOKIE_NAME')=='kodame_production_session'
project_id=uuid.UUID('aa6d49a9-8a71-4749-9707-7439aa9b0839')
open_pool()
with tenant_context(system=True),connection() as conn:
    project=conn.execute('SELECT id,name FROM projects WHERE id=%s',(project_id,)).fetchone()
    account=conn.execute("SELECT a.id FROM accounts a JOIN project_members m ON m.account_id=a.id WHERE m.project_id=%s AND a.email='knut@kodame.local' AND a.is_active=true",(project_id,)).fetchone()
assert project and project['name']=='knut' and account
with tenant_context(project_id,account_id=account['id']):
    model=get_project_model()
    with llm_model_context(model):
        with connection() as conn,conn.transaction():
            _reserve_project_workflow(conn)
            pending=conn.execute("SELECT count(*) AS n FROM intake_documents WHERE status<>'completed'").fetchone()['n']
            assert not pending,'Documents still processing'
            pdm_id=uuid.uuid4()
            conn.execute('INSERT INTO pdm_refresh_runs(id,model) VALUES (%s,%s)',(pdm_id,model))
        print(json.dumps({'pdm_started':str(pdm_id),'model':model}),flush=True)
        run_refresh(pdm_id)
        with connection() as conn:
            pdm=conn.execute('SELECT * FROM pdm_refresh_runs WHERE id=%s',(pdm_id,)).fetchone()
        print(json.dumps({'pdm':serialize(pdm)},ensure_ascii=False),flush=True)
        assert pdm['status']=='completed','PDM refresh did not fully complete'
        with connection() as conn,conn.transaction():
            _reserve_project_workflow(conn)
            count=conn.execute("SELECT count(*) AS n FROM intake_documents WHERE status='completed'").fetchone()['n']
            run_id=uuid.uuid4()
            conn.execute("INSERT INTO evaluation_runs(id,status,model,document_count) VALUES (%s,'queued',%s,%s)",(run_id,model,count))
        print(json.dumps({'dac_started':str(run_id),'documents':count}),flush=True)
        run_all(run_id,project_id,model)
        with connection() as conn:
            run=conn.execute('SELECT id,status,input_snapshot FROM evaluation_runs WHERE id=%s',(run_id,)).fetchone()
            criteria=conn.execute('SELECT criterion_id,score FROM criterion_evaluations WHERE run_id=%s ORDER BY criterion_id',(run_id,)).fetchall()
        print(json.dumps({'dac_completed':str(run_id),'status':run['status'],
                          'validated_questions':len(run['input_snapshot'].get('question_checkpoints',{})),
                          'criteria':criteria},ensure_ascii=False,default=str),flush=True)
