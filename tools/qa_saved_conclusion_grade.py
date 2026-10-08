"""Read-only regression against the saved failed conclusion; no AI call."""
from kodame_intake.db import pool,connection,tenant_context
from kodame_intake.report_generator import _validate_reader_content

pool.open(wait=True)
try:
    with tenant_context(system=True),connection() as conn:
        rows=conn.execute("SELECT generation_metadata FROM report_sections WHERE part_id='conclusion' AND status='failed'").fetchall()
    candidates=[r['generation_metadata']['last_failure']['candidate'] for r in rows
                if r['generation_metadata'].get('last_failure',{}).get('candidate')]
    assert candidates
    for content in candidates:
        issues=_validate_reader_content('conclusion',content,'우즈베키스탄',{'commissioning_agency':'교육부'})
        assert not any('KOICA·코이카' in issue for issue in issues),issues
    print('Saved failed conclusion: grade validation passed',flush=True)
finally:
    pool.close()
