"""Exercise two-phase remapping on the current synthetic QA fixture only, no AI."""
import json,os,tempfile
from pathlib import Path
assert os.getenv('KODAME_QA')=='1' and 'qa-local-only@postgres' in os.environ['DATABASE_URL']
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.evidence_matching import foundation_context
from kodame_intake.remap_evidence_purpose import stamp,apply_project
pool.open(wait=True)
project=json.loads(Path('/qa/synthetic-accounts.json').read_text())['projects'][0]['id']
with tenant_context(project), connection() as c:
    docs=c.execute("SELECT * FROM evaluation_intake_documents WHERE status='completed' AND upload_role='evidence'").fetchall()
    assert all(d['original_name'].endswith('_QA.txt') for d in docs)
    before=c.execute('SELECT id,model FROM pdm_models ORDER BY created_at DESC LIMIT 1').fetchone()
    context=foundation_context()
    with tempfile.TemporaryDirectory() as name:
        root=Path(name)
        for d in docs:
            m=d['analysis']['evidence_matches']
            m['registration_facts']=d['analysis']['registration_facts']
            (root/(str(d['id'])+'.json')).write_text(json.dumps({'stamp':stamp(d),'sources':context['sources'],'matches':m},default=str))
        # Valid prepared records can apply without invoking the provider.
        apply_project(project,root)
        try:apply_project(project,root)
        except RuntimeError:pass
        else:raise AssertionError('Changed inputs must reject stale candidates')
    after=c.execute('SELECT id,model FROM pdm_models ORDER BY created_at DESC LIMIT 1').fetchone()
    assert before==after,'mapping migration changed evaluation history'
    rows=c.execute("SELECT analysis FROM intake_documents WHERE upload_role='evidence' AND status='completed'").fetchall()
    assert all(r['analysis']['mapping_history'] and r['analysis']['pdm_mapping_overrides']['version']==3 for r in rows)
print(json.dumps({'status':'passed','checks':['purpose migration applies','stale candidate rejected','PDM evaluation unchanged','prior mapping audited']}))
pool.close()
