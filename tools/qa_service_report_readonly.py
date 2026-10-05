"""Verify the synthetic report through production readiness rules, without AI."""
import json,os
from pathlib import Path
assert os.getenv('KODAME_QA')=='1' and 'qa-local-only@postgres' in os.environ['DATABASE_URL']
from kodame_intake.db import pool,tenant_context,connection
from kodame_intake.report_generator import report_export_readiness
from kodame_intake.project_lifecycle import project_lifecycle
pool.open(wait=True)
project=json.loads(Path('/qa/synthetic-accounts.json').read_text())['projects'][0]['id']
with tenant_context(project):
    ready=report_export_readiness(project)
    assert ready['ready'],ready['issues']
    assert project_lifecycle()['report_current']
    with connection() as conn:
        exported=conn.execute("SELECT * FROM report_exports WHERE status='completed' ORDER BY created_at DESC LIMIT 1").fetchone()
    assert exported and Path(exported['output_path']).is_file()
    validation=exported['validation']
    assert validation['layout_contract']['ok'] and validation['semantic_coverage']['ok']
    assert validation['rhwp_toc_verified']
result={'status':'passed','readiness':True,'report_current':True,'pages':validation['rhwp_page_count'],
        'quality_warnings':ready['warnings'],'layout_and_content_preserved':True,'toc_verified':True}
Path('/qa/report-readiness.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
pool.close()
