"""Read-only inspection of the reported metric document and its analyzed roster."""
import json
from pathlib import Path
from kodame_intake.db import pool,connection,tenant_context

pool.open(wait=True)
try:
    with tenant_context(system=True), connection() as conn:
        docs=conn.execute("SELECT * FROM active_intake_documents WHERE original_name LIKE '%5차년도 지표별 실적 현황%' AND status='completed'").fetchall()
        for doc in docs:
            run=conn.execute('SELECT analysis_plan FROM pdm_refresh_runs WHERE project_id=%s ORDER BY started_at DESC LIMIT 1',(doc['project_id'],)).fetchone()
            plan=run['analysis_plan']
            ids=[key for key,values in plan['new_mappings'].items() if str(doc['id']) in values]
            print(json.dumps({'id':str(doc['id']),'project_id':str(doc['project_id']),'mapped_ids':ids,
                'indicators':[i for i in plan['indicators'] if i['id'] in ids],
                'text':Path(doc['extracted_path']).read_text(encoding='utf-8')},ensure_ascii=False))
finally:
    pool.close()
