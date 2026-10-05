"""Read-only production preview check. Never calls AI or starts analysis."""
import json
from kodame_intake.db import pool, connection, tenant_context
from kodame_intake.project_lifecycle import project_lifecycle, document_blocks_workflow
from kodame_intake.foundation import state
from kodame_intake.performance_review import build_plan as performance_plan
from kodame_intake.dac_review import build_plan as dac_plan

pool.open(wait=True)
try:
    with tenant_context(system=True), connection() as conn:
        projects = conn.execute('SELECT id FROM projects').fetchall()
    checks = []
    for project in projects:
        with tenant_context(project['id']), connection() as conn:
            docs = conn.execute('SELECT id,status,upload_role FROM active_intake_documents').fetchall()
            lifecycle = project_lifecycle(conn)
            performance = performance_plan(conn)
            dac = dac_plan(conn)
            excluded = {str(d['id']) for d in docs if d['status']!='completed'}
            for plan in (performance,dac):
                assert all(not excluded.intersection(i['document_ids']) for i in plan['indicators'])
            pending = sum(document_blocks_workflow(d) for d in docs)
            assert lifecycle['pending_document_count']==pending
            checks.append({'project_id':str(project['id']), 'statuses':{s:sum(d['status']==s for d in docs) for s in sorted({d['status'] for d in docs})},
                'foundations_ready':state(conn)['ready'],'pending_count':pending,
                'performance_ready':performance['ready'],'dac_ready':dac['ready'],
                'can_evaluate':lifecycle['can_evaluate'],'incomplete_document_mappings':0})
    print(json.dumps({'checks':checks,'ai_calls':0},ensure_ascii=False))
finally:
    pool.close()
