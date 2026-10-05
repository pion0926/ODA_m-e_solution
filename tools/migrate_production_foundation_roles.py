"""Adopt the existing, completed latest foundation PDFs for the legacy project.

This changes role metadata only. Existing PDM models, evaluations, report
sections, source files and analysis results are not regenerated or replaced.
"""
import json
import re
import sys
from pathlib import Path
from psycopg.types.json import Jsonb
from kodame_intake.db import pool, connection, tenant_context

project = 'aa6d49a9-8a71-4749-9707-7439aa9b0839'
targets = {
    '4918d988-25a4-439f-82af-f04f6ecdd13f': ('project_plan', '사업기본자료_5차년도 사업계획서'),
    '081a6e40-56d3-4618-9114-449d5af20f8a': ('pdm', 'DAC_PDM_최신 PDM'),
}
pool.open(wait=True)
try:
    with tenant_context(project), connection() as conn, conn.transaction():
        result = []
        for document_id, (role, name) in targets.items():
            row = conn.execute('SELECT id,original_name,status,upload_role,analysis,extracted_path FROM active_intake_documents WHERE id=%s FOR UPDATE', (document_id,)).fetchone()
            assert row and name in row['original_name'] and row['status'] == 'completed'
            text = Path(row['extracted_path']).read_text(encoding='utf-8')
            compact = re.sub(r'\s+', '', text)
            if '--apply' in sys.argv:
                assert ('사업계획서' in compact if role == 'project_plan' else all(
                    heading in compact for heading in ('NarrativeSummary', 'ObjectivelyVerifiableIndicators', 'MeansofVerification', 'ImportantAssumptions')))
            assert not conn.execute('SELECT id FROM active_intake_documents WHERE upload_role=%s AND id<>%s', (role,document_id)).fetchone(), 'Existing foundation must never be replaced by migration'
            if '--apply' in sys.argv and row['upload_role'] != role:
                analysis = dict(row['analysis'] or {})
                analysis['upload_role'] = role
                analysis['foundation_role_migration'] = {'release':'V2.2.9','basis':'existing completed latest foundation document; content checked','previous_role':row['upload_role']}
                conn.execute('UPDATE intake_documents SET upload_role=%s,analysis=%s WHERE id=%s', (role,Jsonb(analysis),document_id))
            result.append({'role':role,'completed':True,'text_chars':len(text),'opening':text[:220] if '--apply' not in sys.argv else None})
        print(json.dumps({'applied':'--apply' in sys.argv,'documents':result},ensure_ascii=False),flush=True)
finally:
    pool.close()
