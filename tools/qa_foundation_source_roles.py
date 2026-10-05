"""Verify deployed overview selection against real projects without AI/writes."""
import json
from kodame_intake.db import pool, connection, tenant_context
from kodame_intake.project_overview import _documents, latest_plan_overview

pool.open(wait=True)
try:
    with tenant_context(system=True), connection() as conn:
        projects = conn.execute('SELECT id FROM projects').fetchall()
    checks = []
    for project in projects:
        with tenant_context(project['id']), connection() as conn:
            expected = conn.execute("SELECT id FROM active_intake_documents WHERE status='completed' AND upload_role='project_plan' ORDER BY queue_position DESC LIMIT 1").fetchone()
            selected = _documents()
            assert [d['id'] for d in selected] == ([str(expected['id'])] if expected else [])
            overview = latest_plan_overview(conn)
            assert not overview or overview['source_document_ids'] == [str(expected['id'])]
            checks.append({'has_plan':bool(expected),'overview_source_count':len(selected),'valid_current_overview':bool(overview)})
    print(json.dumps({'projects':checks,'plan_only':True,'ai_calls':0}))
finally:
    pool.close()
